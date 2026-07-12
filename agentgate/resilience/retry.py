"""Exponential backoff retry with configurable jitter and rate-limit-awareness."""

import asyncio
import random
import time
from typing import Any


class RetryPolicy:
    """Decides whether and when to retry a failed tool call."""

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
            return True  # connection error — retry
        return status_code in self.RETRYABLE_STATUSES

    def delay_for(self, attempt: int) -> float:
        if self.backoff == "exponential":
            raw = self.initial_delay * (2 ** (attempt - 1))
        elif self.backoff == "linear":
            raw = self.initial_delay * attempt
        else:
            raw = self.initial_delay
        capped = min(raw, self.max_delay)
        jitter = capped * 0.3 * random.random()
        return capped + jitter

    async def wait(self, attempt: int):
        delay = self.delay_for(attempt)
        await asyncio.sleep(delay)
