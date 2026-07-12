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
        rl = RateLimiter(max_per_minute=600)  # 10/sec
        for _ in range(20):
            await rl.acquire()
        assert not await rl.acquire()
        await asyncio.sleep(0.15)  # ~1.5 tokens refilled
        assert await rl.acquire()

    def test_update_from_headers(self):
        rl = RateLimiter(max_per_minute=100)
        rl.update_from_headers(5)
        # Should cap local tokens at 5
        for _ in range(5):
            assert rl._tokens <= 5.0
