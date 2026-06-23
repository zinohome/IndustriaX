from __future__ import annotations
from mcp import types
from industriax.mcp.base import new_server, make_health

# Tool signature types from contracts (imported for reference)
from industriax.contracts.tools import GraphImpactRequest, GraphImpactResult  # noqa: F401

NAME = "graph"
health = make_health(NAME)


def build_server():
    """Build and return the graph MCP server with stubbed tools."""
    srv = new_server(NAME)

    @srv.list_tools()
    async def list_tools() -> list[types.Tool]:
        return [
            types.Tool(
                name="graph_impact",
                description="Compute impact graph for a change (stub; backend wired in P1)",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "change_id": {"type": "string"},
                        "max_hops": {"type": "integer", "default": 4},
                    },
                    "required": ["change_id"],
                },
            )
        ]

    @srv.call_tool()
    async def call_tool(name: str, arguments: dict) -> list:
        # Stub: returns empty results until P1 backend is wired
        return []

    return srv
