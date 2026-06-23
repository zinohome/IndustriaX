from __future__ import annotations
from mcp import types
from industriax.mcp.base import new_server, make_health

# Tool signature types from contracts (imported for reference)
from industriax.contracts.tools import (  # noqa: F401
    MemoryRecallRequest,
    MemoryItem,
    MemoryWriteRequest,
)

NAME = "memory"
health = make_health(NAME)


def build_server():
    """Build and return the memory MCP server with stubbed tools."""
    srv = new_server(NAME)

    @srv.list_tools()
    async def list_tools() -> list[types.Tool]:
        return [
            types.Tool(
                name="memory_recall",
                description="Recall memories for an agent (stub; backend wired in P2)",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "agent_id": {"type": "string"},
                        "query": {"type": "string"},
                        "scope": {"type": "string"},
                    },
                    "required": ["agent_id", "query", "scope"],
                },
            ),
            types.Tool(
                name="memory_write",
                description="Write a memory entry for an agent (stub; backend wired in P2)",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "idempotency_key": {"type": "string"},
                        "agent_id": {"type": "string"},
                        "content": {"type": "string"},
                        "scope": {"type": "string"},
                    },
                    "required": ["idempotency_key", "agent_id", "content", "scope"],
                },
            ),
        ]

    @srv.call_tool()
    async def call_tool(name: str, arguments: dict) -> list | dict:
        # Stub: returns empty/ack results until P2 backend is wired
        if name == "memory_write":
            return {"ack": True, "idempotency_key": arguments.get("idempotency_key", "")}
        return []

    return srv
