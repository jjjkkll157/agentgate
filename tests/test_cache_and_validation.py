import pytest
from agentgate.cache import Cache
from agentgate.validation import format_error, format_success, validate_input, validate_output


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


class TestSchemaValidator:
    def test_input_missing_required(self):
        schema = {"required": ["q"], "properties": {"q": {"type": "string"}}}
        err = validate_input({}, schema)
        assert err is not None
        assert err["reason"] == "schema_violation"
        assert "q" in err["detail"]

    def test_input_wrong_type(self):
        schema = {"properties": {"limit": {"type": "integer"}}}
        err = validate_input({"limit": "not_an_int"}, schema)
        assert err is not None
        assert "integer" in err["detail"]

    def test_input_passes(self):
        schema = {"required": ["q"], "properties": {"q": {"type": "string"}}}
        assert validate_input({"q": "hello"}, schema) is None

    def test_input_no_schema(self):
        assert validate_input({"anything": 1}, None) is None

    def test_output_missing_required(self):
        schema = {"required": ["results"]}
        err = validate_output({"status": "ok"}, schema)
        assert err is not None
        assert "results" in err["detail"]

    def test_output_passes(self):
        schema = {"required": ["results"]}
        assert validate_output({"results": [1, 2]}, schema) is None

    def test_output_no_schema(self):
        assert validate_output({"anything": 1}, None) is None
