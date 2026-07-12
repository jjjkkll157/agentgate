"""MCP (Model Context Protocol) server adapter.

Exposes AgentGate's registered tools as MCP tools so any MCP-compatible
client (Claude Desktop, VS Code Copilot, etc.) can call them through
AgentGate's reliability layer.

Phase 3 feature — not wired into the default CLI yet.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from agentgate.config import Config

logger = logging.getLogger("agentgate.mcp")


class MCPServer:
    """Minimal MCP-compatible tool server wrapping AgentGate's config.

    Usage:
        mcp = MCPServer(config)
        tools = await mcp.list_tools()
        result = await mcp.call_tool("web_search", {"q": "test"})
    """

    def __init__(self, config: Config):
        self._config = config
        self._pipeline: Any = None  # lazily created, shared across calls

    def _ensure_pipeline(self):
        if self._pipeline is None:
            from agentgate.core.pipeline import Pipeline
            self._pipeline = Pipeline(self._config)

    async def list_tools(self) -> list[dict[str, Any]]:
        """Return the tool list in MCP format."""
        tools = []
        for name, tool_cfg in self._config.tools.items():
            tools.append({
                "name": name,
                "description": tool_cfg.description or f"AgentGate tool: {name}",
                "inputSchema": tool_cfg.schema_in or {
                    "type": "object",
                    "properties": {},
                },
            })
        return tools

    async def call_tool(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        """Execute a tool and return MCP-compatible content."""
        import httpx
        self._ensure_pipeline()
        async with httpx.AsyncClient() as client:
            result = await self._pipeline.run(name, arguments, client)

        if result.get("error"):
            return {
                "content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False)}],
                "isError": True,
            }
        return {
            "content": [
                {"type": "text", "text": json.dumps(result.get("data", result), ensure_ascii=False)}
            ],
        }
