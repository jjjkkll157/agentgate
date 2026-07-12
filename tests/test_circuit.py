import pytest
import asyncio
from agentgate.resilience.circuit import CircuitBreaker, CircuitState


class TestCircuitBreaker:
    @pytest.mark.asyncio
    async def test_starts_closed(self):
        cb = CircuitBreaker()
        assert cb.state == CircuitState.CLOSED
        assert await cb.before_request()

    @pytest.mark.asyncio
    async def test_opens_after_threshold(self):
        cb = CircuitBreaker(failure_threshold=3, cooldown_seconds=60)
        for _ in range(3):
            await cb.on_failure()
        assert cb.state == CircuitState.OPEN
        assert not await cb.before_request()

    @pytest.mark.asyncio
    async def test_half_open_after_cooldown(self):
        cb = CircuitBreaker(failure_threshold=2, cooldown_seconds=0.1)
        await cb.on_failure()
        await cb.on_failure()
        assert cb.state == CircuitState.OPEN
        await asyncio.sleep(0.15)
        assert await cb.before_request()
        assert cb.state == CircuitState.HALF_OPEN

    @pytest.mark.asyncio
    async def test_half_open_success_closes(self):
        cb = CircuitBreaker(failure_threshold=2, cooldown_seconds=0.1)
        await cb.on_failure()
        await cb.on_failure()
        await asyncio.sleep(0.15)
        await cb.before_request()
        await cb.on_success()
        assert cb.state == CircuitState.CLOSED

    @pytest.mark.asyncio
    async def test_half_open_failure_reopens(self):
        cb = CircuitBreaker(failure_threshold=2, cooldown_seconds=0.1)
        await cb.on_failure()
        await cb.on_failure()
        await asyncio.sleep(0.15)
        await cb.before_request()
        await cb.on_failure()
        assert cb.state == CircuitState.OPEN

    @pytest.mark.asyncio
    async def test_half_open_only_one_probe(self):
        """Second concurrent call must be rejected while probe is in flight."""
        cb = CircuitBreaker(failure_threshold=2, cooldown_seconds=0.1)
        await cb.on_failure()
        await cb.on_failure()
        await asyncio.sleep(0.15)
        # first call gets the probe
        assert await cb.before_request()
        # second call must be blocked
        assert not await cb.before_request()
