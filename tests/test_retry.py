import pytest
from agentgate.resilience.retry import RetryPolicy


class TestRetryPolicy:
    def test_should_retry_429(self):
        rp = RetryPolicy(max_attempts=3)
        assert rp.should_retry(429, attempt=1)

    def test_should_retry_5xx(self):
        rp = RetryPolicy(max_attempts=3)
        for code in (500, 502, 503, 504):
            assert rp.should_retry(code, attempt=1)

    def test_should_not_retry_400(self):
        rp = RetryPolicy(max_attempts=3)
        assert not rp.should_retry(400, attempt=1)

    def test_should_not_retry_exhausted(self):
        rp = RetryPolicy(max_attempts=3)
        assert not rp.should_retry(500, attempt=3)

    def test_exponential_delay(self):
        rp = RetryPolicy(initial_delay=1.0, max_delay=60.0)
        d1 = rp.delay_for(1)
        d2 = rp.delay_for(2)
        d3 = rp.delay_for(3)
        assert d1 < d2 < d3
        assert d1 >= 1.0
        assert d3 <= 60.0 + 60.0 * 0.3  # max_delay + max jitter

    def test_linear_delay(self):
        rp = RetryPolicy(initial_delay=2.0, backoff="linear")
        d1 = rp.delay_for(1)
        d2 = rp.delay_for(3)
        assert d2 > d1
