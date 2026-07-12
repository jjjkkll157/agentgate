"""Async semaphore-based concurrency limiter for tool calls."""

import asyncio


class ConcurrencyLimiter:
    """Caps in-flight requests for a tool at `max_concurrent`.

    When the limit is hit, the caller blocks until a slot frees up
    or the optional timeout expires.
    """

    def __init__(self, max_concurrent: int):
        if max_concurrent < 1:
            raise ValueError("max_concurrent must be >= 1")
        self._sem = asyncio.Semaphore(max_concurrent)

    async def acquire(self, timeout: float | None = 30.0) -> bool:
        """Try to grab a slot. False on timeout, True on success.
        Caller MUST call release() after True."""
        if timeout is None:
            await self._sem.acquire()
            return True
        try:
            await asyncio.wait_for(self._sem.acquire(), timeout=timeout)
            return True
        except asyncio.TimeoutError:
            return False

    def release(self):
        """Return a slot to the pool."""
        try:
            self._sem.release()
        except ValueError:
            pass  # already released

    @property
    def available(self) -> int:
        """Number of free slots."""
        return self._sem._value
