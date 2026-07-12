"""gRPC server adapter for AgentGate.

Usage:
    agentgate serve --grpc 50051

Protocol:
    service AgentGate {
      rpc CallTool(CallToolRequest) returns (CallToolResponse);
      rpc HealthCheck(Empty) returns (HealthResponse);
    }
"""

import asyncio
import json
import logging
from typing import Any

logger = logging.getLogger("agentgate.grpc")


class GRPCServer:
    """Minimal gRPC server wrapping the AgentGate pipeline.

    When grpcio is installed, this provides a high-performance alternative
    to the REST interface with HTTP/2 multiplexing and streaming support.
    """

    def __init__(self, pipeline, config, port: int = 50051):
        self._pipeline = pipeline
        self._config = config
        self._port = port
        self._server = None

    async def start(self, client):
        """Start gRPC server in background. Non-blocking."""
        try:
            import grpc
            from concurrent import futures
        except ImportError:
            logger.info("grpcio not installed; gRPC server disabled")
            return

        self._server = grpc.aio.server(futures.ThreadPoolExecutor(max_workers=10))
        # add our servicer
        _GRPCServicer.pipeline = self._pipeline
        _GRPCServicer.config = self._config
        _GRPCServicer.client_ref = client

        # We'll define the proto inline to avoid build-step dependency
        # In production, use a proper .proto file + grpcio-tools
        servicer = _GRPCServicer()
        # This is a placeholder — real impl requires generated stubs
        # For now, this module serves as the architectural scaffold.
        # Wire with: grpc_reflection + generated pb2_grpc
        logger.info("gRPC server scaffold ready (port %d) — install grpcio-tools + protoc", self._port)

    async def stop(self):
        if self._server:
            await self._server.stop(0)


class _GRPCServicer:
    """Stub servicer — replace with generated gRPC stubs for production."""
    pipeline = None
    config = None
    client_ref = None

    async def CallTool(self, request: Any, context: Any) -> Any:
        """Handle a CallTool gRPC request."""
        from agentgate.grpc_pb2 import CallToolResponse  # noqa — generated stub
        try:
            result = await self.pipeline.run(request.tool_name,
                                             json.loads(request.arguments),
                                             self.client_ref)
            return CallToolResponse(
                error=result.get("error", False),
                data=json.dumps(result.get("data", {}), ensure_ascii=False),
                cached=result.get("cached", False),
            )
        except Exception as exc:
            await context.abort(grpc.StatusCode.INTERNAL, str(exc))

    async def HealthCheck(self, request, context):
        from agentgate.grpc_pb2 import HealthResponse
        return HealthResponse(status="ok", version="0.3.0")
