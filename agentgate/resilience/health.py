"""Background health-check probes for registered tools.

Each tool may define an optional `health` block in tools.yaml.
The HealthMonitor runs periodic GET requests to the health URL and
feeds results into the circuit breaker so unhealthy tools trip faster.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import httpx

from agentgate.config import Config

logger = logging.getLogger("agentgate.health")


class HealthMonitor:
    """Periodically probes tool health endpoints and syncs circuit breakers."""

    def __init__(self, config: Config, interval: float = 30.0):
        self._config = config
        self._interval = interval
        self._task: asyncio.Task | None = None
        self._breakers: dict[str, Any] = {}  # injected after Pipeline init

    async def start(self, client: httpx.AsyncClient):
        """Begin background probing.  Call stop() to cancel."""
        if self._task is not None:
            return
        self._task = asyncio.create_task(self._loop(client))

    async def stop(self):
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

    async def _loop(self, client: httpx.AsyncClient):
        while True:
            await asyncio.sleep(self._interval)
            for name, tool in self._config.tools.items():
                health_cfg = tool.health
                if not health_cfg:
                    continue
                url = health_cfg.get("endpoint", "")
                if not url:
                    continue
                try:
                    resp = await client.get(url, timeout=min(health_cfg.get("timeout", 5.0), 10.0))
                    breaker = self._breakers.get(name)
                    if resp.status_code < 400:
                        logger.debug("health ok: %s (%d)", name, resp.status_code)
                        if breaker is not None:
                            await breaker.on_success()
                    else:
                        logger.warning("health fail: %s (%d)", name, resp.status_code)
                        if breaker is not None:
                            await breaker.on_failure()
                except Exception:
                    logger.debug("health unreachable: %s", name, exc_info=True)
                    breaker = self._breakers.get(name)
                    if breaker is not None:
                        await breaker.on_failure()

    @property
    def running(self) -> bool:
        return self._task is not None and not self._task.done()
