import pytest
import os
import tempfile
from pathlib import Path


@pytest.fixture(autouse=True)
def isolate_env(monkeypatch):
    """Prevent tests from accidentally reading real env vars."""
    for var in ("BRAVE_API_KEY", "RESEND_API_KEY", "EXTRACT_API_KEY", "MY_API_KEY"):
        monkeypatch.delenv(var, raising=False)


@pytest.fixture
def tmp_config():
    """Write a minimal tools.yaml to a temp file and return its path."""
    content = """
tools:
  echo:
    endpoint: http://localhost:9999/echo
    method: POST
    retry:
      max_attempts: 2
      backoff: fixed
      initial_delay: 0.01
      max_delay: 0.1
    ratelimit:
      max_per_minute: 100
    circuit_breaker:
      failure_threshold: 3
      cooldown_seconds: 1
    timeout: 5.0
    cache:
      ttl_seconds: 0
"""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        f.write(content)
        path = f.name
    yield path
    os.unlink(path)


@pytest.fixture
def config(tmp_config):
    from agentgate.config import Config
    return Config(tmp_config)
