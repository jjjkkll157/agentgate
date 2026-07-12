"""Tests covering bugs 1/5/8/9 — ttl, Retry-After HTTP-date, schema types, bool/int."""
import asyncio
import pytest
import tempfile
import os


class TestBug1CacheTTLInRetryLoop:
    """Bug 1: _run_retry_loop referenced undefined `ttl` variable."""

    @pytest.mark.asyncio
    async def test_ttl_passed_to_retry_loop(self):
        import httpx
        from agentgate.config import Config
        from agentgate.core.pipeline import Pipeline

        yaml = "tools:\n echo:\n  endpoint: http://localhost:19999/echo\n  method: POST\n  cache:\n   ttl_seconds: 60\n  retry:\n   max_attempts: 1\n  circuit_breaker:\n   failure_threshold: 10\n"
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write(yaml); p = f.name
        try:
            cfg = Config(p)
            pipe = Pipeline(cfg)
            # Cache a value so the next call hits
            pipe._cache.set("echo", "POST", {"x": 1}, {"cached": True})
            async with httpx.AsyncClient() as c:
                result = await pipe.run("echo", {"x": 1}, c)
            assert result["cached"] is True
            assert result["data"] == {"cached": True}
        finally:
            os.unlink(p)


class TestBug5RetryAfterHttpDate:
    """Bug 5: Retry-After HTTP-date format was silently turned into 0."""

    def test_parse_http_date_future(self):
        from agentgate.core.pipeline import _parse_retry_after_http_date
        import time
        future = time.time() + 120
        from email.utils import formatdate
        ra = _parse_retry_after_http_date(formatdate(future, usegmt=True))
        assert ra > 60  # at least a minute

    def test_parse_http_date_past(self):
        from agentgate.core.pipeline import _parse_retry_after_http_date
        assert _parse_retry_after_http_date("Thu, 01 Jan 2000 00:00:00 GMT") == 0.0

    def test_parse_http_date_garbage(self):
        from agentgate.core.pipeline import _parse_retry_after_http_date
        assert _parse_retry_after_http_date("not-a-date") == 0.0


class TestBug8ArrayObjectSchema:
    """Bug 8: validate_input didn't support array/object types."""

    def test_array_rejects_string(self):
        from agentgate.validation import validate_input
        err = validate_input({"items": "not_a_list"}, {"properties": {"items": {"type": "array"}}})
        assert err is not None

    def test_array_accepts_list(self):
        from agentgate.validation import validate_input
        assert validate_input({"items": [1, 2]}, {"properties": {"items": {"type": "array"}}}) is None

    def test_object_rejects_list(self):
        from agentgate.validation import validate_input
        err = validate_input({"data": [1, 2]}, {"properties": {"data": {"type": "object"}}})
        assert err is not None

    def test_object_accepts_dict(self):
        from agentgate.validation import validate_input
        assert validate_input({"data": {"k": "v"}}, {"properties": {"data": {"type": "object"}}}) is None


class TestBug9BoolInteger:
    """Bug 9: isinstance(True, int) = True, so booleans passed integer checks."""

    def test_true_rejected_for_integer(self):
        from agentgate.validation import validate_input
        err = validate_input({"count": True}, {"properties": {"count": {"type": "integer"}}})
        assert err is not None
        assert "integer" in err["detail"]

    def test_false_rejected_for_integer(self):
        from agentgate.validation import validate_input
        err = validate_input({"count": False}, {"properties": {"count": {"type": "integer"}}})
        assert err is not None

    def test_int_passes_integer(self):
        from agentgate.validation import validate_input
        assert validate_input({"count": 42}, {"properties": {"count": {"type": "integer"}}}) is None
