"""Integration tests — exercise the full FastAPI app via TestClient."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi.testclient import TestClient
import tempfile
import os


@pytest.fixture
def app_client():
    """Create a TestClient backed by a real FastAPI app with a temp config."""
    yaml = """tools:
  echo:
    endpoint: http://localhost:19999/echo
    method: POST
    retry:
      max_attempts: 1
      backoff: fixed
      initial_delay: 0.01
      max_delay: 0.1
"""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        f.write(yaml)
        path = f.name
    try:
        from agentgate.app import create_app
        app = create_app(path)
        with TestClient(app) as client:
            yield client
    finally:
        os.unlink(path)


class TestHealthEndpoint:
    def test_health_returns_ok(self, app_client):
        resp = app_client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert "tools" in data
        assert "version" in data

    def test_version_endpoint(self, app_client):
        resp = app_client.get("/version")
        assert resp.status_code == 200
        assert resp.json()["version"] == "0.2.0"


class TestToolEndpoint:
    def test_unknown_tool_returns_404(self, app_client):
        resp = app_client.post("/tool/nonexistent", json={})
        assert resp.status_code == 404

    def test_metrics_endpoint(self, app_client):
        resp = app_client.get("/metrics")
        assert resp.status_code == 200
        assert "agentgate_requests_total" in resp.text


class TestDashboard:
    def test_dashboard_index(self, app_client):
        resp = app_client.get("/dashboard/")
        assert resp.status_code == 200
        assert "text/html" in resp.headers["content-type"]

    def test_dashboard_api_log(self, app_client):
        resp = app_client.get("/dashboard/api/log")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    def test_dashboard_api_stats(self, app_client):
        resp = app_client.get("/dashboard/api/stats")
        assert resp.status_code == 200
        data = resp.json()
        assert "total_requests" in data


class TestErrorRecovery:
    """Verify the proxy returns structured errors on upstream failure."""

    @pytest.mark.asyncio
    async def test_tool_call_catches_exceptions(self, app_client):
        """Pipeline failures must return error JSON, not crash the server."""
        # Make the pipeline raise an unexpected exception
        with patch(
            "agentgate.app.Pipeline.run",
            AsyncMock(side_effect=RuntimeError("upstream exploded")),
        ):
            resp = app_client.post("/tool/echo", json={"msg": "test"})
            # Pipeline failures are caught and returned as 502 with error JSON.
            assert resp.status_code == 502
            data = resp.json()
            assert data["error"] is True
            assert data["reason"] == "internal_error"
            # Health check must still work
            health = app_client.get("/health")
            assert health.status_code == 200
