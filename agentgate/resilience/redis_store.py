"""Redis-backed state for circuit breakers, rate limiters, and cache.

Usage:
    from agentgate.resilience.redis_store import RedisStore
    store = RedisStore(redis_url="redis://localhost:6379")
    await store.save_breaker("web_search", "open", 30)
    state = await store.load_breaker("web_search")
"""

import asyncio
import json
import logging
from typing import Any

logger = logging.getLogger("agentgate.redis")


class RedisStore:
    """Persist AgentGate state to Redis for multi-instance HA."""

    def __init__(self, redis_url: str = ""):
        self._redis = None
        self._url = redis_url
        self._prefix = "agentgate:"

    async def _connect(self):
        if self._redis is not None or not self._url:
            return
        try:
            import redis.asyncio as aioredis
            self._redis = aioredis.from_url(self._url, decode_responses=True)
            await self._redis.ping()
            logger.info("connected to Redis at %s", self._url)
        except ImportError:
            logger.debug("redis package not installed; state is in-memory only")
        except Exception as exc:
            logger.warning("Redis unavailable: %s; using in-memory fallback", exc)
            self._redis = None

    async def save_breaker(self, tool: str, state: str, retry_after: float):
        await self._connect()
        key = f"{self._prefix}breaker:{tool}"
        payload = json.dumps({"state": state, "retry_after": retry_after})
        if self._redis:
            await self._redis.set(key, payload, ex=300)
        logger.debug("redis: save breaker %s → %s", tool, state)

    async def load_breaker(self, tool: str) -> dict | None:
        await self._connect()
        if not self._redis:
            return None
        raw = await self._redis.get(f"{self._prefix}breaker:{tool}")
        return json.loads(raw) if raw else None

    async def save_tokens(self, tool: str, tokens: float):
        await self._connect()
        if self._redis:
            await self._redis.set(f"{self._prefix}tokens:{tool}", str(tokens), ex=60)

    async def load_tokens(self, tool: str) -> float | None:
        await self._connect()
        if not self._redis:
            return None
        raw = await self._redis.get(f"{self._prefix}tokens:{tool}")
        return float(raw) if raw else None

    async def save_cache(self, cache_key: str, value: Any, ttl: int):
        await self._connect()
        if self._redis:
            await self._redis.set(f"{self._prefix}cache:{cache_key}",
                                  json.dumps(value, ensure_ascii=False), ex=ttl)

    async def load_cache(self, cache_key: str) -> Any | None:
        await self._connect()
        if not self._redis:
            return None
        raw = await self._redis.get(f"{self._prefix}cache:{cache_key}")
        return json.loads(raw) if raw else None

    @property
    def available(self) -> bool:
        return self._redis is not None
