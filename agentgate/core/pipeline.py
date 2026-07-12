"""Request pipeline: orchestrates resilience layers around a single tool call."""

import asyncio
import logging
from typing import Any

import httpx

from agentgate.config import Config, ToolConfig
from agentgate.core.context import RequestContext
from agentgate.resilience.retry import RetryPolicy
from agentgate.resilience.ratelimit import RateLimiter
from agentgate.resilience.circuit import CircuitBreaker
from agentgate.cache import Cache
from agentgate.validation import format_error, format_success

logger = logging.getLogger("agentgate.proxy")


class Pipeline:
    """Runs one tool invocation through retry, rate-limit, circuit-breaker, cache."""

    def __init__(self, config: Config, cache: Cache | None = None):
        self._config = config
        self._cache = cache or Cache()
        self._limiters: dict[str, RateLimiter] = {}
        self._breakers: dict[str, CircuitBreaker] = {}

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

        # --- retry loop ---
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
                # cache on success
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
                await retry.wait(attempt)

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

        # Surface HTTP errors with status code so retry logic can act on them.
        if resp.status_code >= 400:
            err = RuntimeError(f"{resp.status_code} {resp.reason_phrase}")
            err.status_code = resp.status_code  # type: ignore
            # Try to grab a text snippet for error formatting
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
