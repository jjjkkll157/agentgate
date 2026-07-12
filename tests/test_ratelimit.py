import asyncio
import pytest
from agentgate.resilience.ratelimit import RateLimiter


class TestRateLimiter:
    @pytest.mark.asyncio
    async def test_acquire_up_to_limit(self):
        rl = RateLimiter(max_per_minute=10)
        for _ in range(10):
            assert await rl.acquire()
        assert not await rl.acquire()

    @pytest.mark.asyncio
    async def test_refills_over_time(self):
        rl = RateLimiter(max_per_minute=20)  # 20 tokens total
        for _ in range(20):
            await rl.acquire()
        # bucket should be empty now
        assert not await rl.acquire()
        await asyncio.sleep(3.2)  # ~1 token refilled at 20/min rate
        assert await rl.acquire()

    @pytest.mark.asyncio
    async def test_update_from_headers(self):
        rl = RateLimiter(max_per_minute=100)
        await rl.update_from_headers(5)
        assert rl._tokens <= 5.0
