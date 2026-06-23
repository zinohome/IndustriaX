from __future__ import annotations
from industriax.mcp.base import new_server, make_health

NAME = "skill-tools"
health = make_health(NAME)


def build_server():
    """Build and return the skill-tools MCP server.

    Specific skill tools (bom.parse / ecn.compare / fa.analyze) are added in P2+
    when the Skill packages are available.
    """
    srv = new_server(NAME)
    # No tools registered at skeleton stage; tools are extended in P2+
    return srv
