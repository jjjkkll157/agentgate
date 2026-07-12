"""Token-bucket rate limiter and response-header-aware throttle."""

import asyncio
import time


class RateLimiter:
    """Per-tool rate limit that can wait rather than reject."""

    def __init__(self, max_per_minute: int = 60):
        self._tokens = float(max_per_minute)
        self._max = float(max_per_minute)
        self._refill_rate = max_per_minute / 60.0
        self._last_refill = time.monotonic()
        self._lock = asyncio.Lock()

    async def acquire(self) -> bool:
        async with self._lock:
            self._refill()
            if self._tokens >= 1.0:
                self._tokens -= 1.0
                return True
            return False

    async def wait_until_ready(self, timeout: float = 120.0) -> bool:
        """Block until a token is available or timeout."""
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            async with self._lock:
                self._refill()
                if self._tokens >= 1.0:
                    self._tokens -= 1.0
                    return True
            await asyncio.sleep(1.0 / self._refill_rate)
        return False

    def _refill(self):
        now = time.monotonic()
        elapsed = now - self._last_refill
        self._tokens = min(self._max, self._tokens + elapsed * self._refill_rate)
        self._last_refill = now

    def update_from_headers(self, remaining: int | None):
        """Read X-RateLimit-Remaining from API response to tighten local estimate."""
        if remaining is not None:
            self._tokens = min(self._tokens, float(remaining))
