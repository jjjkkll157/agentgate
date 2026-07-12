"""Request pipeline: orchestrates resilience layers around a single tool call."""

import asyncio
import logging
from typing import Any

import httpx

from agentgate.config import Config, ToolConfig
from agentgate.core.context import RequestContext
from agentgate.core.middleware import resolve_hook, run_hooks
from agentgate.resilience.retry import RetryPolicy
from agentgate.resilience.ratelimit import RateLimiter
from agentgate.resilience.circuit import CircuitBreaker
from agentgate.resilience.concurrency import ConcurrencyLimiter
from agentgate.cache import Cache
from agentgate.validation import format_error, format_success, validate_input, validate_output

logger = logging.getLogger("agentgate.proxy")


class Pipeline:
    """Runs one tool invocation through retry, rate-limit, circuit-breaker,
    concurrency control, middleware hooks, and cache."""

    def __init__(self, config: Config, cache: Cache | None = None):
        self._config = config
        self._cache = cache or Cache()
        self._limiters: dict[str, RateLimiter] = {}
        self._breakers: dict[str, CircuitBreaker] = {}
        self._concurrency: dict[str, ConcurrencyLimiter] = {}
        # resolved middleware hooks (lazy)
        self._before_hooks: dict[str, list] = {}
        self._after_hooks: dict[str, list] = {}

    def _get_limiter(self, tool: ToolConfig) -> RateLimiter:
        if tool.name not in self._limiters:
            self._limiters[tool.name] = RateLimiter(tool.ratelimit["max_per_minute"])
        return self._limiters[tool.name]

    def _get_breaker(self, tool: ToolConfig) -> CircuitBreaker:
        if tool.name not in self._breakers:
            self._breakers[tool.name] = CircuitBreaker(
                failure_threshold=tool.circuit_breaker["failure_threshold"],
                cooldown_seconds=tool.circuit_breaker["cooldown_seconds"],
            )
        return self._breakers[tool.name]

    def _get_concurrency(self, tool: ToolConfig) -> ConcurrencyLimiter | None:
        max_cc = tool.concurrency.get("max_concurrent", 0)
        if max_cc <= 0:
            return None
        if tool.name not in self._concurrency:
            self._concurrency[tool.name] = ConcurrencyLimiter(max_cc)
        return self._concurrency[tool.name]

    def _resolve_before_hooks(self, tool: ToolConfig) -> list:
        if tool.name not in self._before_hooks:
            self._before_hooks[tool.name] = [
                resolve_hook(p) for p in tool.middleware.get("before", [])
            ]
        return self._before_hooks[tool.name]

    def _resolve_after_hooks(self, tool: ToolConfig) -> list:
        if tool.name not in self._after_hooks:
            self._after_hooks[tool.name] = [
                resolve_hook(p) for p in tool.middleware.get("after", [])
            ]
        return self._after_hooks[tool.name]

    async def _try_fallbacks(self, tool: ToolConfig, ctx: RequestContext, params: dict, client: httpx.AsyncClient) -> dict:
        """Walk the fallback chain and return the first success."""
        for fb_name in tool.fallback:
            try:
                fb_tool = self._config.get(fb_name)
            except KeyError:
                continue
            ctx.tool_name = fb_tool.name
            logger.info("fallback to %s", fb_name, extra={"request_id": ctx.request_id})
            try:
                return await self._execute_one(fb_tool, ctx, params, client)
            except Exception:
                continue
        raise RuntimeError(f"all fallbacks exhausted for {tool.name!r}")

    async def run(self, tool_name: str, params: dict, client: httpx.AsyncClient) -> dict:
        tool = self._config.get(tool_name)
        ctx = RequestContext(tool_name=tool_name)
        logger.info("request %s tool=%s", ctx.request_id, tool_name)

        # --- before hooks ---
        before_hooks = self._resolve_before_hooks(tool)
        if before_hooks:
            context = {"tool": tool_name, "request_id": ctx.request_id}
            params = await run_hooks(before_hooks, params, context)

        # --- input schema validation ---
        schema_err = validate_input(params, tool.schema_in)
        if schema_err is not None:
            ctx.finish()
            return schema_err

        # --- cache check ---
        ttl = tool.cache.get("ttl_seconds", 0)
        cached = self._cache.get(tool.name, tool.method, params, ttl)
        if cached is not None:
            ctx.cached = True
            ctx.finish()
            logger.debug("cache hit %s tool=%s", ctx.request_id, tool_name)
            return format_success(cached, cached=True, attempt=0)

        # --- rate limit ---
        limiter = self._get_limiter(tool)
        if not await limiter.acquire():
            waited = await limiter.wait_until_ready()
            if not waited:
                ctx.error = "rate_limit_timeout"
                ctx.finish()
                return format_error("rate_limit_timeout", "queue wait exhausted")

        # --- circuit breaker ---
        breaker = self._get_breaker(tool)
        if not await breaker.before_request():
            ctx.error = "circuit_open"
            ctx.finish()
            retry_after = breaker.retry_after()
            return format_error("circuit_open", f"circuit open for {tool.name!r}", retry_after=retry_after, circuit_open=True)

        # --- concurrency control ---
        cc = self._get_concurrency(tool)
        if cc is not None:
            if not await cc.acquire(timeout=30.0):
                ctx.finish()
                return format_error("concurrency_limit", "too many concurrent requests")

        try:
            result = await self._run_retry_loop(tool, ctx, params, client, breaker)
        finally:
            if cc is not None:
                cc.release()

        # --- after hooks ---
        after_hooks = self._resolve_after_hooks(tool)
        if after_hooks:
            context = {"tool": tool_name, "request_id": ctx.request_id}
            result = await run_hooks(after_hooks, result, context)

        return result

    async def _run_retry_loop(self, tool: ToolConfig, ctx: RequestContext, params: dict, client: httpx.AsyncClient, breaker: CircuitBreaker) -> dict:
        retry = RetryPolicy(
            max_attempts=tool.retry["max_attempts"],
            backoff=tool.retry["backoff"],
            initial_delay=tool.retry["initial_delay"],
            max_delay=tool.retry["max_delay"],
        )

        last_error = None
        for attempt in range(1, retry.max_attempts + 1):
            ctx.attempt = attempt
            try:
                result = await self._execute_one(tool, ctx, params, client)
                await breaker.on_success()
                # output schema validation
                out_err = validate_output(result.get("data", {}), tool.schema_out)
                if out_err is not None:
                    last_error = RuntimeError(out_err["detail"])
                    last_error.status_code = 0  # type: ignore
                    await breaker.on_failure()
                    if not retry.should_retry(None, attempt):
                        break
                    await retry.wait(attempt)
                    continue
                # cache on success (skip if TTL is 0)
                if ttl > 0:
                    self._cache.set(tool.name, tool.method, params, result["data"])
                ctx.finish()
                logger.info(
                    "ok %s tool=%s attempt=%d latency=%.0fms",
                    ctx.request_id, tool.name, attempt, ctx.latency_ms,
                )
                return result
            except Exception as exc:
                last_error = exc
                ctx.error = str(exc)
                logger.warning(
                    "fail %s tool=%s attempt=%d err=%s",
                    ctx.request_id, tool.name, attempt, exc,
                )
                await breaker.on_failure()

                if not retry.should_retry(getattr(exc, "status_code", None), attempt):
                    break
                ra = getattr(exc, "retry_after_seconds", None)
                await retry.wait(attempt, ra)

        # --- all retries exhausted, try fallbacks ---
        if tool.fallback:
            try:
                result = await self._try_fallbacks(tool, ctx, params, client)
                await breaker.on_success()
                ctx.finish()
                return result
            except Exception:
                pass

        ctx.finish()
        return format_error(
            "all_retries_failed",
            str(last_error),
            retry_after=breaker.retry_after(),
            circuit_open=breaker.state.value == "open",
            status_code=getattr(last_error, "status_code", 0) if last_error else 0,
        )

    # ---------- internal ----------

    async def _execute_one(self, tool: ToolConfig, ctx: RequestContext, params: dict, client: httpx.AsyncClient) -> dict:
        url = tool.endpoint
        headers = {**tool.headers}
        request_kwargs: dict[str, Any] = {
            "method": tool.method,
            "url": url,
            "timeout": tool.timeout,
        }

        if tool.method in ("POST", "PUT", "PATCH"):
            body = {**tool.body_template, **params}
            request_kwargs["json"] = body
        elif tool.method == "GET":
            request_kwargs["params"] = {**tool.params, **params}

        resp = await client.request(**request_kwargs)

        ctx.status_code = resp.status_code

        # Sync rate-limit headers back to the local token bucket.
        remaining_raw = resp.headers.get("X-RateLimit-Remaining")
        if remaining_raw is not None:
            try:
                self._get_limiter(tool).update_from_headers(int(remaining_raw.split("/")[0]))
            except (ValueError, KeyError):
                pass

        # Surface HTTP errors with status code so retry logic can act on them.
        if resp.status_code >= 400:
            err = RuntimeError(f"{resp.status_code} {resp.reason_phrase}")
            err.status_code = resp.status_code  # type: ignore
            # Carry Retry-After if present (seconds or HTTP-date).
            ra = resp.headers.get("Retry-After")
            if ra is not None:
                try:
                    err.retry_after_seconds = float(ra)  # type: ignore
                except ValueError:
                    err.retry_after_seconds = 0  # type: ignore
            try:
                body_text = resp.text[:500]
            except Exception:
                body_text = ""
            err.body = body_text  # type: ignore
            raise err

        # Parse response — try JSON, fall back to text-wrapped object.
        try:
            data = resp.json()
            return format_success(data, attempt=ctx.attempt)
        except Exception:
            text = resp.text
            return format_success({"text": text}, attempt=ctx.attempt)
