"""Test that configured headers are actually sent to upstream APIs."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import httpx
from agentgate.config import Config
from agentgate.core.pipeline import Pipeline


class TestHeadersForwarding:
    """Verify that tool.headers from config are sent in actual requests."""

    @pytest.mark.asyncio
    async def test_headers_sent_to_upstream(self, tmp_config):
        """Headers configured in tools.yaml must appear in the upstream request."""
        cfg = Config(tmp_config)
        cfg.tools["echo"].headers = {"X-API-Key": "test-key-123", "Authorization": "Bearer token456"}
        
        pipeline = Pipeline(cfg)
        
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"result": "ok"}
        mock_response.headers = {}
        
        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.request = AsyncMock(return_value=mock_response)
        
        await pipeline.run("echo", {"msg": "test"}, mock_client)
        
        # Verify headers were passed to the request
        call_args = mock_client.request.call_args
        assert call_args is not None, "client.request was not called"
        
        kwargs = call_args.kwargs
        assert "headers" in kwargs, "headers not in request kwargs"
        assert kwargs["headers"]["X-API-Key"] == "test-key-123"
        assert kwargs["headers"]["Authorization"] == "Bearer token456"

    @pytest.mark.asyncio
    async def test_get_method_with_params(self, tmp_config):
        """GET requests should forward both configured and user params."""
        cfg = Config(tmp_config)
        cfg.tools["echo"].method = "GET"
        cfg.tools["echo"].params = {"fixed_param": "from_config"}
        
        pipeline = Pipeline(cfg)
        
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"ok": True}
        mock_response.headers = {}
        
        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.request = AsyncMock(return_value=mock_response)
        
        await pipeline.run("echo", {"user_param": "from_request"}, mock_client)
        
        call_kwargs = mock_client.request.call_args.kwargs
        assert "params" in call_kwargs
        params = call_kwargs["params"]
        assert params["fixed_param"] == "from_config"
        assert params["user_param"] == "from_request"

    @pytest.mark.asyncio
    async def test_post_method_with_headers(self, tmp_config):
        """POST requests must include configured headers."""
        cfg = Config(tmp_config)
        cfg.tools["echo"].method = "POST"
        cfg.tools["echo"].headers = {"Content-Type": "application/json", "X-Custom": "value"}
        
        pipeline = Pipeline(cfg)
        
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"status": "ok"}
        mock_response.headers = {}
        
        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.request = AsyncMock(return_value=mock_response)
        
        await pipeline.run("echo", {"data": "test"}, mock_client)
        
        call_kwargs = mock_client.request.call_args.kwargs
        assert "headers" in call_kwargs
        assert call_kwargs["headers"]["Content-Type"] == "application/json"
        assert call_kwargs["headers"]["X-Custom"] == "value"
