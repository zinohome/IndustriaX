from __future__ import annotations
from mcp.server import Server


def make_health(name: str):
    """Return a plain-Python health() callable for the given server name."""
    def health() -> dict:
        return {"status": "ok", "server": name}
    return health


def new_server(name: str) -> Server:
    """Create a new MCP Server instance with the given name."""
    return Server(name)
