import subprocess, pathlib, yaml, os

COMPOSE = pathlib.Path("deploy/docker-compose.yml")


def test_compose_is_valid_and_conformant():
    # Ensure POSTGRES_PASSWORD is set so docker compose config resolves the variable
    env = os.environ.copy()
    env.setdefault("POSTGRES_PASSWORD", "test-password")

    # docker compose config 校验语法 + 解析变量
    out = subprocess.run(
        ["docker", "compose", "-f", str(COMPOSE), "config"],
        capture_output=True, text=True, env=env,
    )
    assert out.returncode == 0, out.stderr
    spec = yaml.safe_load(out.stdout)
    # 部署规范：name=industriax、网络含 1panel-network、卷在 /data/industriax
    assert spec.get("name") == "industriax"
    assert "1panel-network" in spec.get("networks", {})
    services = spec["services"]
    for required in ["postgres", "temporal", "ollama", "doc-mcp", "graph-mcp", "memory-mcp", "skill-tools-mcp"]:
        assert required in services, f"missing service {required}"
    # 每个服务必须有 healthcheck
    for name, svc in services.items():
        assert "healthcheck" in svc, f"{name} missing healthcheck"
