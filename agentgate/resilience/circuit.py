"""Circuit breaker: three-state machine (closed → open → half-open → closed)."""

import asyncio
import time
from enum import Enum


class CircuitState(Enum):
    CLOSED = "closed"        # normal — requests pass through
    OPEN = "open"            # failing — requests are rejected immediately
    HALF_OPEN = "half_open"  # testing — one probe request allowed


class CircuitBreaker:
    """Fails fast when a tool is unhealthy so the agent doesn't waste turns."""

    def __init__(self, failure_threshold: int = 5, cooldown_seconds: float = 30):
        self.failure_threshold = failure_threshold
        self.cooldown_seconds = cooldown_seconds
        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._last_failure_time = 0.0
        self._lock = asyncio.Lock()

    @property
    def state(self) -> CircuitState:
        return self._state

    async def before_request(self) -> bool:
        """Return True if the request should proceed."""
        async with self._lock:
            if self._state == CircuitState.CLOSED:
                return True
            if self._state == CircuitState.OPEN:
                if time.monotonic() - self._last_failure_time >= self.cooldown_seconds:
                    self._state = CircuitState.HALF_OPEN
                    return True
                return False
            # HALF_OPEN — allow one probe
            return True

    async def on_success(self):
        async with self._lock:
            self._failure_count = 0
            if self._state == CircuitState.HALF_OPEN:
                self._state = CircuitState.CLOSED

    async def on_failure(self):
        async with self._lock:
            self._failure_count += 1
            self._last_failure_time = time.monotonic()
            if self._failure_count >= self.failure_threshold:
                self._state = CircuitState.OPEN

    def retry_after(self) -> float:
        """Seconds until the circuit may close again. 0 if already closed."""
        if self._state != CircuitState.OPEN:
            return 0
        remaining = self.cooldown_seconds - (time.monotonic() - self._last_failure_time)
        return max(0.0, remaining)
