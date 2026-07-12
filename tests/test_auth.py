"""Tests for auth module."""
import pytest
from agentgate.core.auth import TokenAuth, load_auth


class TestTokenAuth:
    def test_no_tokens_allows_all(self):
        auth = TokenAuth([])
        assert not auth.enabled
        assert auth.validate(None)
        assert auth.validate("Bearer anything")

    def test_correct_token_passes(self):
        auth = TokenAuth(["sk-abc"])
        assert auth.enabled
        assert auth.validate("Bearer sk-abc")

    def test_wrong_token_fails(self):
        auth = TokenAuth(["sk-abc"])
        assert not auth.validate("Bearer sk-xyz")
        assert not auth.validate(None)

    def test_multiple_tokens(self):
        auth = TokenAuth(["sk-a", "sk-b"])
        assert auth.validate("Bearer sk-a")
        assert auth.validate("Bearer sk-b")
        assert not auth.validate("Bearer sk-c")


class TestLoadAuth:
    def test_disabled_by_default(self):
        auth = load_auth({})
        assert not auth.enabled

    def test_enabled_with_tokens(self):
        auth = load_auth({"auth": {"enabled": True, "tokens": ["t1"]}})
        assert auth.enabled
        assert auth.validate("Bearer t1")
