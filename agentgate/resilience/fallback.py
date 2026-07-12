"""Standalone fallback executor for tool chains.

The pipeline already handles fallback inline (_try_fallbacks).  This module
lets external callers test or drive fallback resolution directly, and serves
as the canonical place for future mode-aware fallback logic (strict vs
best-effort, health-aware routing, etc.).
"""

from __future__ import annotations

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

logger = logging.getLogger("agentgate.fallback")


class FallbackRunner:
    """Walk a fallback chain and return the first successful result."""

    def __init__(self, config: Config):
        self._config = config

    async def run(
        self,
        tool: ToolConfig,
        params: dict,
        client: httpx.AsyncClient,
        ctx: RequestContext | None = None,
    ) -> dict:
        """Try each fallback in order; return first success or raise on exhaustion."""
        ctx = ctx or RequestContext(tool_name=tool.name)
        for fb_name in tool.fallback:
            try:
                fb_tool = self._config.get(fb_name)
            except KeyError:
                logger.debug(
                    "fallback %s for %s not found in config, skipping",
                    fb_name, tool.name,
                    extra={"request_id": ctx.request_id},
                )
                continue

            ctx.tool_name = fb_tool.name
            logger.info(
                "fallback to %s", fb_name,
                extra={"request_id": ctx.request_id},
            )
            try:
                return await self._call_one(fb_tool, params, client, ctx)
            except Exception as exc:
                logger.warning(
                    "fallback %s failed: %s", fb_name, exc,
                    extra={"request_id": ctx.request_id},
                )
                continue

        raise RuntimeError(
            f"all {len(tool.fallback)} fallback(s) exhausted for {tool.name!r}"
        )

    # ------------------------------------------------------------------
    async def _call_one(
        self,
        tool: ToolConfig,
        params: dict,
        client: httpx.AsyncClient,
        ctx: RequestContext,
    ) -> dict:
        url = tool.endpoint
        request_kwargs: dict[str, Any] = {
            "method": tool.method,
            "url": url,
            "timeout": tool.timeout,
        }
        if tool.method in ("POST", "PUT", "PATCH"):
            request_kwargs["json"] = {**tool.body_template, **params}
        elif tool.method == "GET":
            request_kwargs["params"] = {**tool.params, **params}

        resp = await client.request(**request_kwargs)
        if resp.status_code >= 400:
            err = RuntimeError(f"{resp.status_code} {resp.reason_phrase}")
            err.status_code = resp.status_code  # type: ignore
            raise err

        try:
            return format_success(resp.json(), attempt=ctx.attempt)
        except Exception:
            return format_success({"text": resp.text}, attempt=ctx.attempt)
