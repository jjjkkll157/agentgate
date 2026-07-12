import pytest
from agentgate.resilience.concurrency import ConcurrencyLimiter


class TestConcurrencyLimiter:
    @pytest.mark.asyncio
    async def test_acquire_and_release(self):
        cc = ConcurrencyLimiter(max_concurrent=2)
        assert await cc.acquire()
        assert await cc.acquire()
        assert not await cc.acquire(timeout=0.01)
        cc.release()
        assert await cc.acquire(timeout=0.01)

    @pytest.mark.asyncio
    async def test_available_count(self):
        cc = ConcurrencyLimiter(max_concurrent=5)
        assert cc.available == 5
        await cc.acquire()
        assert cc.available == 4


class TestRetryAfter:
    def test_retry_after_overrides_backoff(self):
        from agentgate.resilience.retry import RetryPolicy
        rp = RetryPolicy(max_attempts=3, backoff="exponential", initial_delay=1.0)
        normal = rp.delay_for(1)
        with_ra = rp.delay_for(1, retry_after_seconds=42.0)
        assert with_ra == 42.0
        assert normal < 42.0

    def test_retry_after_capped_by_max_delay(self):
        from agentgate.resilience.retry import RetryPolicy
        rp = RetryPolicy(max_attempts=3, max_delay=30.0)
        assert rp.delay_for(1, retry_after_seconds=99) == 30.0


class TestMetricsCollector:
    def test_record_and_render(self):
        from agentgate.telemetry.metrics import MetricsCollector
        mc = MetricsCollector()
        mc.record({"tool": "web_search", "latency_ms": 120, "error": "", "cached": False})
        mc.record({"tool": "web_search", "latency_ms": 30, "error": "", "cached": True})
        mc.record({"tool": "send", "latency_ms": 5000, "error": "timeout", "cached": False})
        out = mc.render()
        assert "agentgate_requests_total 3" in out
        assert "agentgate_cache_hits_total 1" in out
        assert "agentgate_errors_total 1" in out
        assert "agentgate_latency_seconds_web_search_bucket" in out


class TestMiddleware:
    @pytest.mark.asyncio
    async def test_run_hooks_passes(self):
        from agentgate.core.middleware import run_hooks

        async def add_prefix(params, ctx):
            params["q"] = "prefix_" + params.get("q", "")
            return params

        result = await run_hooks([add_prefix], {"q": "hello"}, {})
        assert result["q"] == "prefix_hello"

    @pytest.mark.asyncio
    async def test_run_hooks_chain(self):
        from agentgate.core.middleware import run_hooks

        async def a(p, c): p["x"] = 1; return p
        async def b(p, c): p["x"] += 1; return p

        result = await run_hooks([a, b], {}, {})
        assert result["x"] == 2
