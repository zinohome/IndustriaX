import pytest
from industriax.mcp import doc_server, graph_server, memory_server, skill_tools_server


@pytest.mark.parametrize("mod,name", [
    (doc_server, "doc"),
    (graph_server, "graph"),
    (memory_server, "memory"),
    (skill_tools_server, "skill-tools"),
])
def test_server_builds_and_health(mod, name):
    srv = mod.build_server()
    assert srv is not None
    assert mod.health()["status"] == "ok"
    assert mod.health()["server"] == name
