"""Exponential backoff retry with Retry-After header awareness."""

import asyncio
import random


class RetryPolicy:
    """Decides whether and when to retry a failed tool call.

    If the upstream returns a ``Retry-After`` header the policy
    uses that value instead of the configured backoff for that
    one attempt.  This avoids hammering an API that explicitly
    told us to wait.
    """

    RETRYABLE_STATUSES = {429, 500, 502, 503, 504}

    def __init__(
        self,
        max_attempts: int = 3,
        backoff: str = "exponential",
        initial_delay: float = 1.0,
        max_delay: float = 60.0,
    ):
        self.max_attempts = max_attempts
        self.backoff = backoff
        self.initial_delay = initial_delay
        self.max_delay = max_delay

    def should_retry(self, status_code: int | None, attempt: int) -> bool:
        if attempt >= self.max_attempts:
            return False
        if status_code is None:
            return True  # connection / network error — worth retrying
        if status_code == 0:
            return False  # non-HTTP error (schema violation, timeout) — not transient
        return status_code in self.RETRYABLE_STATUSES

    def delay_for(self, attempt: int, retry_after_seconds: float | None = None) -> float:
        """Compute delay, bounded by ``max_delay``.  If ``retry_after_seconds``
        is provided (from a Retry-After header), use that value directly."""
        if retry_after_seconds is not None and retry_after_seconds > 0:
            return min(retry_after_seconds, self.max_delay)
        if self.backoff == "exponential":
            raw = self.initial_delay * (2 ** (attempt - 1))
        elif self.backoff == "linear":
            raw = self.initial_delay * attempt
        else:
            raw = self.initial_delay
        capped = min(raw, self.max_delay)
        jitter = capped * 0.3 * random.random()
        return capped + jitter

    async def wait(self, attempt: int, retry_after_seconds: float | None = None):
        delay = self.delay_for(attempt, retry_after_seconds)
        await asyncio.sleep(delay)
