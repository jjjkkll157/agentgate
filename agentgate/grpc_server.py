"""gRPC server adapter for AgentGate — architectural scaffold.

To activate: pip install grpcio grpcio-tools, compile the .proto, then:
    agentgate serve --grpc 50051

Protocol (proto/agentgate.proto):
    service AgentGate {
      rpc CallTool(CallToolRequest) returns (CallToolResponse);
      rpc HealthCheck(Empty) returns (HealthResponse);
    }
"""

import logging

logger = logging.getLogger("agentgate.grpc")


class GRPCServer:
    """gRPC server wrapping the AgentGate pipeline.

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
        # Wire generated stubs here with _GRPCServicer(pipeline, config, client)
        logger.info("gRPC scaffold ready (port %d) — compile proto + wire stubs", self._port)

    async def stop(self):
        if self._server:
            await self._server.stop(0)


class _GRPCServicer:
    """Replace with generated gRPC stubs after proto compilation."""

    def __init__(self, pipeline, config, client):
        self.pipeline = pipeline
        self.config = config
        self.client = client
