from __future__ import annotations
from mcp import types
from industriax.mcp.base import new_server, make_health

# Tool signature types from contracts (imported for reference; used in schema)
from industriax.contracts.tools import DocSearchRequest, DocSearchItem  # noqa: F401

NAME = "doc"
health = make_health(NAME)


def build_server():
    """Build and return the doc MCP server with stubbed tools."""
    srv = new_server(NAME)

    @srv.list_tools()
    async def list_tools() -> list[types.Tool]:
        return [
            types.Tool(
                name="doc_search",
                description="Search document chunks via RAGFlow (stub; backend wired in P2)",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "query": {"type": "string"},
                        "top_k": {"type": "integer", "default": 8},
                        "filters": {"type": "object"},
                    },
                    "required": ["query"],
                },
            )
        ]

    @srv.call_tool()
    async def call_tool(name: str, arguments: dict) -> list:
        # Stub: all tools return empty results until P2 backend is wired
        return []

    return srv
