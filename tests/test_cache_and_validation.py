import pytest
from agentgate.cache import Cache
from agentgate.validation import format_error, format_success


class TestCache:
    def test_set_and_get(self):
        c = Cache()
        c.set("search", "POST", {"q": "test"}, {"results": [1, 2]})
        val = c.get("search", "POST", {"q": "test"}, ttl=60)
        assert val == {"results": [1, 2]}

    def test_miss_on_different_params(self):
        c = Cache()
        c.set("search", "POST", {"q": "test"}, [])
        assert c.get("search", "POST", {"q": "other"}, ttl=60) is None

    def test_ttl_expiry(self):
        import time
        c = Cache()
        c.set("x", "GET", {}, "val")
        c._store[c._key("x", "GET", {})] = (time.monotonic() - 999, "val")
        assert c.get("x", "GET", {}, ttl=1) is None

    def test_clear(self):
        c = Cache()
        c.set("x", "GET", {}, "val")
        c.clear()
        assert c.get("x", "GET", {}, ttl=60) is None


class TestErrorFormatter:
    def test_format_error_minimal(self):
        e = format_error("timeout")
        assert e["error"] is True
        assert e["reason"] == "timeout"

    def test_format_error_full(self):
        e = format_error("circuit_open", circuit_open=True, retry_after=30, status_code=503)
        assert e["circuit_open"]
        assert e["retry_after"] == 30
        assert e["status"] == 503

    def test_format_success(self):
        s = format_success({"answer": 42}, cached=False, attempt=2)
        assert s["error"] is False
        assert s["data"] == {"answer": 42}
        assert s["attempt"] == 2
        assert s["cached"] is False
