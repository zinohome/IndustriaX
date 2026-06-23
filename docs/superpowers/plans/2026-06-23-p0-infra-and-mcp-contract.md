# IndustriaX P0 — 基础设施 + MCP 契约冻结 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 建立 IndustriaX 项目骨架，docker-compose 一键起全栈并健康检查全绿，且把四个 MCP server 的工具签名（含三元元字段与幂等键）冻结为可被后续所有 Phase 复用的类型契约。

**Architecture:** 单仓 Python monorepo，`industriax` 顶层包。契约层（`industriax.contracts`）是纯 Pydantic 模型，无运行期依赖、单元可测，作为四个 MCP server 的共享接缝；MCP server 骨架（`industriax.mcp.*`）用官方 MCP Python SDK 暴露工具桩 + 健康检查；基础设施层用 docker-compose 编排 Postgres(pgvector+AGE)/RAGFlow 栈/Temporal/Ollama(Qwen3+Embedding+Reranker)/四个 MCP server，用冒烟脚本轮询各服务健康。

**Tech Stack:** Python 3.12 · uv（依赖管理）· Pydantic v2 · MCP Python SDK（`mcp`）· pytest · ruff · mypy · docker-compose · Postgres16+pgvector+Apache AGE · RAGFlow · Temporal · Ollama

## Global Constraints

- 命名一律 **IndustriaX**（无 l）；Python 包名 `industriax`；镜像/compose `name: industriax`；源文档标题里的 `IndustrialX` 在本计划 Task 1 一并更正为 `IndustriaX`。
- **License 只用 Apache/MIT**：Pydantic(MIT)、mcp(MIT)、pgvector(PostgreSQL License)、Apache AGE(Apache2)、RAGFlow(Apache2)、Temporal(MIT)、Ollama(MIT)。禁引入 copyleft（不得用 Neo4j）。
- **私有化/离线**：运行期零外网拉取；镜像、模型权重、依赖随交付包内置。
- **部署规范（CLAUDE.md）**：docker-compose 网络用 `1panel-network`；数据卷挂载到 `/data/industriax/`；compose `name` 字段填 `industriax`。
- **检索类 MCP 工具返回项必带** `data_level`、`data_domain`、`source`（来源文档+版本+章节）三元字段。
- **有副作用的 MCP 工具签名必须有 `idempotency_key`（必填）；只读工具禁止有该字段。**
- **硬件基线**：单张 RTX 4090（Standard SKU）；全栈不在一张卡上同时跑热，冒烟测试按服务串行。
- 每个任务 TDD：先写失败测试 → 看它失败 → 最小实现 → 看它通过 → 提交。提交后 push origin/main（CLAUDE.md DoD：push 才算完成）。

---

### Task 1: 项目骨架与工具链

**Files:**
- Create: `pyproject.toml`
- Create: `industriax/__init__.py`
- Create: `tests/__init__.py`
- Create: `tests/test_smoke.py`
- Create: `.gitignore`
- Create: `ruff.toml`
- Modify: `docs/IndustrialX_PRD_v1.md` → 重命名为 `docs/IndustriaX_PRD_v1.md`
- Modify: `docs/IndustrialX_Architecture_A.md` → 重命名为 `docs/IndustriaX_Architecture_A.md`

**Interfaces:**
- Produces: 可导入的 `industriax` 包；`pytest`、`ruff`、`mypy` 可运行；`industriax.__version__` 字符串。

- [ ] **Step 1: 写失败测试**

```python
# tests/test_smoke.py
import industriax

def test_package_imports_and_has_version():
    assert isinstance(industriax.__version__, str)
    assert industriax.__version__  # 非空
```

- [ ] **Step 2: 运行测试确认失败**

Run: `uv run pytest tests/test_smoke.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'industriax'`

- [ ] **Step 3: 最小实现**

```toml
# pyproject.toml
[project]
name = "industriax"
version = "0.0.1"
description = "IndustriaX — 工业 AI 生产底座"
requires-python = ">=3.12"
dependencies = ["pydantic>=2.7", "mcp>=1.2"]

[project.optional-dependencies]
dev = ["pytest>=8", "ruff>=0.5", "mypy>=1.10"]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.pytest.ini_options]
testpaths = ["tests"]
```

```python
# industriax/__init__.py
__version__ = "0.0.1"
```

```python
# tests/__init__.py
```

```
# ruff.toml
line-length = 100
target-version = "py312"
```

```
# .gitignore
__pycache__/
*.pyc
.venv/
.env
*.pem
*.crt
.pytest_cache/
.mypy_cache/
```

并重命名两份文档（git 保留历史）：

```bash
git mv docs/IndustrialX_PRD_v1.md docs/IndustriaX_PRD_v1.md
git mv docs/IndustrialX_Architecture_A.md docs/IndustriaX_Architecture_A.md
```

- [ ] **Step 4: 运行测试确认通过**

Run: `uv run pytest tests/test_smoke.py -v`
Expected: PASS

- [ ] **Step 5: 提交并推送**

```bash
git add pyproject.toml industriax/ tests/ ruff.toml .gitignore
git add -A docs/
git commit -m "chore: scaffold industriax package + rename docs to IndustriaX"
git push
```

---

### Task 2: 契约核心 — 数据分类与来源元字段

**Files:**
- Create: `industriax/contracts/__init__.py`
- Create: `industriax/contracts/meta.py`
- Test: `tests/contracts/test_meta.py`

**Interfaces:**
- Produces:
  - `DataLevel(str, Enum)`: `GENERAL="一般"`, `IMPORTANT="重要"`, `CORE="核心"`，并定义可比较顺序 `GENERAL < IMPORTANT < CORE`（用 `order` 属性或 `__lt__`）。
  - `DataDomain(str, Enum)`: `RND="研发"`, `PRODUCTION="生产"`, `OPS="运维"`, `MANAGEMENT="管理"`, `EXTERNAL="外部"`。
  - `Provenance(BaseModel)`: `doc_id: str`, `version: str`, `section: str | None`。
  - `MetaFields(BaseModel)`: `data_level: DataLevel`, `data_domain: DataDomain`, `source: Provenance`。
  - `max_level(items: list[MetaFields]) -> DataLevel`：取上下文 bundle 的最高级别（Router 数据边界过滤用）。

- [ ] **Step 1: 写失败测试**

```python
# tests/contracts/test_meta.py
import pytest
from industriax.contracts.meta import (
    DataLevel, DataDomain, Provenance, MetaFields, max_level,
)

def test_level_ordering():
    assert DataLevel.GENERAL < DataLevel.IMPORTANT < DataLevel.CORE

def test_metafields_requires_source():
    with pytest.raises(Exception):
        MetaFields(data_level=DataLevel.GENERAL, data_domain=DataDomain.RND)

def test_max_level_picks_highest():
    items = [
        MetaFields(data_level=DataLevel.GENERAL, data_domain=DataDomain.EXTERNAL,
                   source=Provenance(doc_id="d1", version="v1", section="1")),
        MetaFields(data_level=DataLevel.IMPORTANT, data_domain=DataDomain.RND,
                   source=Provenance(doc_id="d2", version="v1", section="2")),
    ]
    assert max_level(items) == DataLevel.IMPORTANT

def test_max_level_empty_defaults_general():
    assert max_level([]) == DataLevel.GENERAL
```

- [ ] **Step 2: 运行测试确认失败**

Run: `uv run pytest tests/contracts/test_meta.py -v`
Expected: FAIL — `ModuleNotFoundError: industriax.contracts.meta`

- [ ] **Step 3: 最小实现**

```python
# industriax/contracts/__init__.py
```

```python
# industriax/contracts/meta.py
from __future__ import annotations
from enum import Enum
from pydantic import BaseModel

class DataLevel(str, Enum):
    GENERAL = "一般"
    IMPORTANT = "重要"
    CORE = "核心"

    @property
    def _rank(self) -> int:
        return {"一般": 0, "重要": 1, "核心": 2}[self.value]

    def __lt__(self, other: "DataLevel") -> bool:  # type: ignore[override]
        if not isinstance(other, DataLevel):
            return NotImplemented
        return self._rank < other._rank

class DataDomain(str, Enum):
    RND = "研发"
    PRODUCTION = "生产"
    OPS = "运维"
    MANAGEMENT = "管理"
    EXTERNAL = "外部"

class Provenance(BaseModel):
    doc_id: str
    version: str
    section: str | None = None

class MetaFields(BaseModel):
    data_level: DataLevel
    data_domain: DataDomain
    source: Provenance

def max_level(items: list[MetaFields]) -> DataLevel:
    level = DataLevel.GENERAL
    for it in items:
        if level < it.data_level:
            level = it.data_level
    return level
```

- [ ] **Step 4: 运行测试确认通过**

Run: `uv run pytest tests/contracts/test_meta.py -v`
Expected: PASS（4 passed）

- [ ] **Step 5: 提交并推送**

```bash
git add industriax/contracts/ tests/contracts/
git commit -m "feat(contracts): data classification + provenance meta fields"
git push
```

---

### Task 3: 契约 — 四个 MCP server 的工具签名模型

**Files:**
- Create: `industriax/contracts/tools.py`
- Test: `tests/contracts/test_tools.py`

**Interfaces:**
- Consumes: `industriax.contracts.meta`（`MetaFields`）。
- Produces（请求/响应 Pydantic 模型，写类含必填 `idempotency_key`，只读类不含）：
  - 只读：`DocSearchRequest`/`DocSearchItem`（含 `MetaFields`）、`GraphImpactRequest`/`GraphImpactResult`、`MemoryRecallRequest`/`MemoryItem`。
  - 写类：`MemoryWriteRequest(idempotency_key: str, ...)`、`MemoryForgetRequest(idempotency_key: str, ...)`。
  - 约束基类 `WriteToolRequest(BaseModel)`：声明 `idempotency_key: str`（必填，min_length=1）。所有写类继承它。
  - 模块级 `READ_ONLY_REQUESTS` / `WRITE_REQUESTS` 两个集合，供契约一致性测试遍历。

- [ ] **Step 1: 写失败测试**

```python
# tests/contracts/test_tools.py
import pytest
from pydantic import ValidationError
from industriax.contracts import tools
from industriax.contracts.tools import (
    DocSearchItem, MemoryWriteRequest, WriteToolRequest,
)
from industriax.contracts.meta import DataLevel, DataDomain, Provenance

def test_read_item_carries_meta():
    item = DocSearchItem(
        chunk="x", data_level=DataLevel.GENERAL, data_domain=DataDomain.EXTERNAL,
        source=Provenance(doc_id="d", version="v1", section="1"),
    )
    assert item.data_level == DataLevel.GENERAL

def test_write_requires_idempotency_key():
    with pytest.raises(ValidationError):
        MemoryWriteRequest(agent_id="a", content="c", scope="session")  # 缺 key

def test_write_idempotency_key_nonempty():
    with pytest.raises(ValidationError):
        MemoryWriteRequest(agent_id="a", content="c", scope="session", idempotency_key="")

def test_every_write_request_has_idempotency_key():
    for model in tools.WRITE_REQUESTS:
        assert issubclass(model, WriteToolRequest)
        assert "idempotency_key" in model.model_fields

def test_no_readonly_request_has_idempotency_key():
    for model in tools.READ_ONLY_REQUESTS:
        assert "idempotency_key" not in model.model_fields
```

- [ ] **Step 2: 运行测试确认失败**

Run: `uv run pytest tests/contracts/test_tools.py -v`
Expected: FAIL — `ModuleNotFoundError: industriax.contracts.tools`

- [ ] **Step 3: 最小实现**

```python
# industriax/contracts/tools.py
from __future__ import annotations
from pydantic import BaseModel, Field
from industriax.contracts.meta import MetaFields

class WriteToolRequest(BaseModel):
    """所有有副作用工具的请求基类——强制幂等键。"""
    idempotency_key: str = Field(min_length=1)

# ---- doc-mcp (只读) ----
class DocSearchRequest(BaseModel):
    query: str
    top_k: int = 8
    filters: dict | None = None

class DocSearchItem(MetaFields):
    chunk: str

# ---- graph-mcp (只读) ----
class GraphImpactRequest(BaseModel):
    change_id: str
    max_hops: int = 4

class GraphImpactResult(MetaFields):
    node_id: str
    node_kind: str

# ---- memory-mcp ----
class MemoryRecallRequest(BaseModel):
    agent_id: str
    query: str
    scope: str

class MemoryItem(MetaFields):
    content: str

class MemoryWriteRequest(WriteToolRequest):
    agent_id: str
    content: str
    scope: str

class MemoryForgetRequest(WriteToolRequest):
    agent_id: str
    filter: dict

READ_ONLY_REQUESTS = (DocSearchRequest, GraphImpactRequest, MemoryRecallRequest)
WRITE_REQUESTS = (MemoryWriteRequest, MemoryForgetRequest)
```

- [ ] **Step 4: 运行测试确认通过**

Run: `uv run pytest tests/contracts/test_tools.py -v`
Expected: PASS（5 passed）

- [ ] **Step 5: 提交并推送**

```bash
git add industriax/contracts/tools.py tests/contracts/test_tools.py
git commit -m "feat(contracts): freeze MCP tool signatures with idempotency invariant"
git push
```

---

### Task 4: 四个 MCP server 骨架 + 健康检查

**Files:**
- Create: `industriax/mcp/__init__.py`
- Create: `industriax/mcp/base.py`
- Create: `industriax/mcp/doc_server.py`
- Create: `industriax/mcp/graph_server.py`
- Create: `industriax/mcp/memory_server.py`
- Create: `industriax/mcp/skill_tools_server.py`
- Test: `tests/mcp/test_servers.py`

**Interfaces:**
- Consumes: `industriax.contracts.tools`。
- Produces: 每个 server 提供 `build_server() -> mcp.server.Server`，注册其工具桩（返回类型化空结果）与一个 `health` 工具返回 `{"status": "ok", "server": <name>}`。桩实现不连真实后端（后端在 P1/P2 接），仅冻结接口与可启动性。

- [ ] **Step 1: 写失败测试**

```python
# tests/mcp/test_servers.py
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
```

- [ ] **Step 2: 运行测试确认失败**

Run: `uv run pytest tests/mcp/test_servers.py -v`
Expected: FAIL — `ModuleNotFoundError: industriax.mcp.doc_server`

- [ ] **Step 3: 最小实现**

```python
# industriax/mcp/__init__.py
```

```python
# industriax/mcp/base.py
from __future__ import annotations
from mcp.server import Server

def make_health(name: str):
    def health() -> dict:
        return {"status": "ok", "server": name}
    return health

def new_server(name: str) -> Server:
    return Server(name)
```

每个 server 同构（以 doc 为例，其余把 `name` 与桩工具替换）：

```python
# industriax/mcp/doc_server.py
from __future__ import annotations
from industriax.mcp.base import new_server, make_health
from industriax.contracts.tools import DocSearchRequest, DocSearchItem

NAME = "doc"
health = make_health(NAME)

def build_server():
    srv = new_server(NAME)
    # 工具桩：签名以契约为准，实现待 P2 接 RAGFlow
    @srv.call_tool()
    async def doc_search(req: DocSearchRequest) -> list[DocSearchItem]:
        return []
    return srv
```

```python
# industriax/mcp/graph_server.py
from __future__ import annotations
from industriax.mcp.base import new_server, make_health
from industriax.contracts.tools import GraphImpactRequest, GraphImpactResult

NAME = "graph"
health = make_health(NAME)

def build_server():
    srv = new_server(NAME)
    @srv.call_tool()
    async def graph_impact(req: GraphImpactRequest) -> list[GraphImpactResult]:
        return []
    return srv
```

```python
# industriax/mcp/memory_server.py
from __future__ import annotations
from industriax.mcp.base import new_server, make_health
from industriax.contracts.tools import MemoryRecallRequest, MemoryItem, MemoryWriteRequest

NAME = "memory"
health = make_health(NAME)

def build_server():
    srv = new_server(NAME)
    @srv.call_tool()
    async def memory_recall(req: MemoryRecallRequest) -> list[MemoryItem]:
        return []
    @srv.call_tool()
    async def memory_write(req: MemoryWriteRequest) -> dict:
        return {"ack": True, "idempotency_key": req.idempotency_key}
    return srv
```

```python
# industriax/mcp/skill_tools_server.py
from __future__ import annotations
from industriax.mcp.base import new_server, make_health

NAME = "skill-tools"
health = make_health(NAME)

def build_server():
    srv = new_server(NAME)
    # 具体 skill 工具（bom.parse / ecn.compare / fa.analyze）随 Skill 包在 P2+ 扩展
    return srv
```

> 注：`@srv.call_tool()` 的精确装饰器签名以所装 `mcp` SDK 版本为准；执行时若 SDK API 不同，以"每个 server 可 `build_server()` 且 `health()` 返回约定结构"为验收锚点调整桩写法，契约类型不变。

- [ ] **Step 4: 运行测试确认通过**

Run: `uv run pytest tests/mcp/test_servers.py -v`
Expected: PASS（4 passed）

- [ ] **Step 5: 提交并推送**

```bash
git add industriax/mcp/ tests/mcp/
git commit -m "feat(mcp): four MCP server skeletons with health + typed tool stubs"
git push
```

---

### Task 5: docker-compose 全栈编排 + 健康冒烟

**Files:**
- Create: `deploy/docker-compose.yml`
- Create: `deploy/.env.example`
- Create: `deploy/init/age.sql`
- Create: `deploy/Dockerfile.mcp`
- Create: `scripts/smoke_health.sh`
- Test: `tests/deploy/test_compose_config.py`

**Interfaces:**
- Produces: 一键 `docker compose -f deploy/docker-compose.yml up -d` 起全栈；`scripts/smoke_health.sh` 轮询各服务健康全绿退出 0。

- [ ] **Step 1: 写失败测试**

```python
# tests/deploy/test_compose_config.py
import subprocess, pathlib, yaml

COMPOSE = pathlib.Path("deploy/docker-compose.yml")

def test_compose_is_valid_and_conformant():
    # docker compose config 校验语法 + 解析变量
    out = subprocess.run(
        ["docker", "compose", "-f", str(COMPOSE), "config"],
        capture_output=True, text=True,
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
```

- [ ] **Step 2: 运行测试确认失败**

Run: `uv run pytest tests/deploy/test_compose_config.py -v`
Expected: FAIL — compose 文件不存在 / `returncode != 0`

- [ ] **Step 3: 最小实现**

```yaml
# deploy/docker-compose.yml
name: industriax

networks:
  1panel-network:
    external: true

volumes:
  pgdata:
  ollama:

services:
  postgres:
    image: apache/age:PG16_latest   # Postgres16 + Apache AGE；pgvector 经 init 装
    environment:
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
    volumes:
      - /data/industriax/postgres:/var/lib/postgresql/data
      - ./init/age.sql:/docker-entrypoint-initdb.d/age.sql:ro
    networks: [1panel-network]
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U postgres"]
      interval: 10s
      timeout: 5s
      retries: 10

  temporal:
    image: temporalio/auto-setup:1.24
    environment:
      DB: postgres12
      POSTGRES_SEEDS: postgres
      POSTGRES_PWD: ${POSTGRES_PASSWORD}
    depends_on:
      postgres:
        condition: service_healthy
    networks: [1panel-network]
    healthcheck:
      test: ["CMD", "tctl", "--address", "temporal:7233", "cluster", "health"]
      interval: 15s
      timeout: 10s
      retries: 10

  ollama:
    image: ollama/ollama:latest
    volumes:
      - /data/industriax/ollama:/root/.ollama
    networks: [1panel-network]
    deploy:
      resources:
        reservations:
          devices:
            - driver: nvidia
              count: 1
              capabilities: [gpu]
    healthcheck:
      test: ["CMD-SHELL", "ollama list || exit 1"]
      interval: 15s
      timeout: 10s
      retries: 10

  doc-mcp:    { extends: { file: mcp.partial.yml, service: mcp-base }, command: ["python","-m","industriax.mcp.doc_server"] }
  graph-mcp:  { extends: { file: mcp.partial.yml, service: mcp-base }, command: ["python","-m","industriax.mcp.graph_server"] }
  memory-mcp: { extends: { file: mcp.partial.yml, service: mcp-base }, command: ["python","-m","industriax.mcp.memory_server"] }
  skill-tools-mcp: { extends: { file: mcp.partial.yml, service: mcp-base }, command: ["python","-m","industriax.mcp.skill_tools_server"] }
```

> 若 `extends` 跨文件不便，可将四个 mcp 服务直接内联展开（同一 `build: { context: .., dockerfile: deploy/Dockerfile.mcp }` + 各自 `healthcheck` 调用 `python -c "import industriax.mcp.<x> as m; assert m.health()['status']=='ok'"`）。执行时以"四个 mcp 服务都在 compose 内且各有 healthcheck"为验收锚点。

```sql
-- deploy/init/age.sql
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS age;
LOAD 'age';
```

```dockerfile
# deploy/Dockerfile.mcp
FROM python:3.12-slim
WORKDIR /app
COPY pyproject.toml ./
COPY industriax ./industriax
RUN pip install --no-cache-dir .
# 健康检查由 compose healthcheck 调 health() 完成
```

```bash
# deploy/.env.example
POSTGRES_PASSWORD=change-me
```

```bash
# scripts/smoke_health.sh
#!/usr/bin/env bash
set -euo pipefail
COMPOSE="deploy/docker-compose.yml"
echo "[smoke] starting stack..."
docker compose -f "$COMPOSE" up -d
echo "[smoke] waiting for healthchecks (single-4090: services come up serially)..."
deadline=$((SECONDS+600))
while [ $SECONDS -lt $deadline ]; do
  unhealthy=$(docker compose -f "$COMPOSE" ps --format '{{.Name}} {{.Health}}' | grep -E 'starting|unhealthy' || true)
  if [ -z "$unhealthy" ]; then echo "[smoke] all healthy"; exit 0; fi
  sleep 10
done
echo "[smoke] TIMEOUT — still unhealthy:"; docker compose -f "$COMPOSE" ps
exit 1
```

- [ ] **Step 4: 运行测试确认通过**

Run: `uv run pytest tests/deploy/test_compose_config.py -v`
Expected: PASS（compose config 校验通过、服务与 healthcheck 齐全）
集成冒烟（需 4090 节点，由张俊环境执行）：`bash scripts/smoke_health.sh` → 退出 0。

- [ ] **Step 5: 提交并推送**

```bash
git add deploy/ scripts/ tests/deploy/
git commit -m "feat(deploy): full-stack docker-compose with per-service healthchecks + smoke script"
git push
```

---

### Task 6: 私有化离线打包基线

**Files:**
- Create: `scripts/offline_bundle.sh`
- Create: `deploy/OFFLINE.md`
- Test: `tests/deploy/test_offline_manifest.py`

**Interfaces:**
- Consumes: `deploy/docker-compose.yml`。
- Produces: `scripts/offline_bundle.sh` 生成离线交付包清单（镜像 tar + 模型权重 + manifest）；`deploy/OFFLINE.md` 记录运行期零外网拉取的约束与还原步骤。

- [ ] **Step 1: 写失败测试**

```python
# tests/deploy/test_offline_manifest.py
import subprocess, pathlib

def test_bundle_script_lists_all_images(tmp_path):
    # dry-run 模式只打印将打包的镜像清单，不真正 docker save
    out = subprocess.run(
        ["bash", "scripts/offline_bundle.sh", "--dry-run"],
        capture_output=True, text=True,
    )
    assert out.returncode == 0, out.stderr
    for img in ["apache/age", "temporalio/auto-setup", "ollama/ollama"]:
        assert img in out.stdout
    # 模型权重清单需含三件套
    for w in ["qwen3", "embedding", "reranker"]:
        assert w in out.stdout.lower()
```

- [ ] **Step 2: 运行测试确认失败**

Run: `uv run pytest tests/deploy/test_offline_manifest.py -v`
Expected: FAIL — 脚本不存在

- [ ] **Step 3: 最小实现**

```bash
# scripts/offline_bundle.sh
#!/usr/bin/env bash
set -euo pipefail
DRY=0; [ "${1:-}" = "--dry-run" ] && DRY=1
IMAGES=$(grep -E '^\s+image:' deploy/docker-compose.yml | awk '{print $2}')
MODELS="qwen3:14b qwen3-embedding qwen3-reranker"
echo "== images to bundle =="; echo "$IMAGES"
echo "== model weights to bundle =="; echo "$MODELS"
if [ "$DRY" = "1" ]; then exit 0; fi
mkdir -p dist/images
for img in $IMAGES; do docker pull "$img"; done
docker save $IMAGES -o dist/images/industriax-images.tar
echo "$IMAGES" > dist/manifest-images.txt
echo "$MODELS" > dist/manifest-models.txt
echo "[offline] bundle written to dist/"
```

```markdown
# deploy/OFFLINE.md
## 离线交付约束
- 运行期零外网拉取：镜像、模型权重、Python 依赖全部随包内置。
- 唯一出网口是 `external_api`（受 Router 数据边界过滤管控，P3 接入），其余全内网闭环。

## 还原步骤（客户内网）
1. `docker load -i dist/images/industriax-images.tar`
2. 把 `dist/models/` 下权重放入 ollama 卷 `/data/industriax/ollama/`
3. `cp deploy/.env.example deploy/.env` 并改密码
4. `docker compose -f deploy/docker-compose.yml up -d`
5. `bash scripts/smoke_health.sh` 验证全绿
```

- [ ] **Step 4: 运行测试确认通过**

Run: `uv run pytest tests/deploy/test_offline_manifest.py -v`
Expected: PASS

- [ ] **Step 5: 提交并推送**

```bash
git add scripts/offline_bundle.sh deploy/OFFLINE.md tests/deploy/test_offline_manifest.py
git commit -m "feat(deploy): offline bundle baseline + manifest test"
git push
```

---

## P0 验收（全部满足才算 P0 完成）

- [ ] `uv run pytest` 全绿（契约 + MCP 骨架 + compose config + offline manifest 单元/配置测试）。
- [ ] `uv run ruff check .` 与 `uv run mypy industriax` 无错。
- [ ] 在 4090 节点 `docker compose up -d` + `scripts/smoke_health.sh` 退出 0（集成冒烟，张俊环境）。
- [ ] MCP 契约冻结：三元元字段在所有检索类返回项、`idempotency_key` 在且仅在写类工具，有契约一致性测试守护。
- [ ] 命名统一 IndustriaX；文档已重命名；compose `name=industriax`、网络 `1panel-network`、卷 `/data/industriax`。
- [ ] 所有 commit 已 push origin/main。

## Self-Review 记录

- **Spec 覆盖**：本计划覆盖 spec §5 表中 P0 行（基础设施 + 契约骨架）与 §6（P0 契约冻结范围：四个 MCP server 工具签名 + 三元字段 + 幂等键）。P1–P5 不在本计划内，各自单独出计划。
- **占位符扫描**：无 TBD/TODO；MCP SDK 装饰器与 RAGFlow/AGE 镜像 tag 处给出了"验收锚点"以应对版本差异，非占位。
- **类型一致性**：`MetaFields`/`DataLevel`/`WriteToolRequest`/`build_server`/`health` 在 Task 2–4 间签名一致；`max_level` 在 Task 2 定义、Router（P3）消费。
