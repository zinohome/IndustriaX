# IndustriaX P1 — 数据底座 + 入库打标管线 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在 P0 冻结契约之上建起 IndustriaX 的数据底座与入库打标管线，使四条验收锚点成立——**文档进得来、打标正确、合规图建得起、索引生效可验证**。其中"整栈 `docker compose up` + `smoke_health.sh` 全绿"是从 P0 顺延的第一件事（P0 在共享开发节点因 docker.io 拉取超时未在本机跑齐，按 Issue 收口选项"乙"并入 P1）。

**Architecture:** P1 在 `industriax` 单仓内分两类能力落地，刻意拆开以便无栈环境也能跑大部分单测：

- **纯确定性逻辑（可无栈单测）**：入库打标引擎放在新包 `industriax.ingest.*`——domain 确定性分类器（按来源/路径/文档类型）、level 三步定级器（默认映射 → 规则升级器 → 存疑往高 + 核心需人工确认）、解析→打标转换器。全部是纯函数 / 纯 Pydantic，**输入用注入的假解析结果**，产出严格等于 P0 冻结的 `MetaFields`，零运行期依赖。
- **数据层与图层（需容器/DB）**：Postgres 三库 schema 隔离（DDL/迁移）、AGE vlabel/elabel + 索引策略与走索引 Cypher 规范、合规图边写入路径骨架。这些任务的 TDD 循环需要一个跑着的 Postgres(AGE+pgvector) 实例（即 P0 的自定义镜像 `industriax/postgres-age-pgvector:pg16`）。

打标产出是数据层与契约层之间的接缝：管线把每条入库数据落成带 `data_level`/`data_domain`/`source` 三元标签的记录，运行期（P2/P3）只读标签、不重判。

**Tech Stack:** Python 3.12 · Pydantic v2 · pytest · ruff · mypy · Postgres16 + Apache AGE 1.6.0 + pgvector 0.8.3（P0 自定义镜像）· RAGFlow v0.20.5-slim · Temporal（库独立）· docker-compose

## Global Constraints

- **本环境无 `uv`。** 所有测试/检查命令一律用项目内置 venv：`./.venv/bin/pytest`、`./.venv/bin/ruff check .`、`./.venv/bin/mypy industriax`。**不要写 `uv run`**（这是与 P0 模板的关键差异，P0 模板的 `uv run` 写法在本环境不适用）。
- 命名一律 **IndustriaX**（无 l）；Python 包名 `industriax`。
- **License 只用 Apache/MIT**（或更宽松，如 PostgreSQL License）：Pydantic(MIT)、Apache AGE(Apache2)、pgvector(PostgreSQL License)、RAGFlow(Apache2)、Temporal(MIT)。禁引入 copyleft（不得用 Neo4j）。
- **打标产出的元字段必须与 P0 冻结的契约完全一致**：`industriax.contracts.meta` 的 `MetaFields`（`data_level: DataLevel`、`data_domain: DataDomain`、`source: Provenance`）。`DataLevel ∈ {"一般","重要","核心"}`（即 `GENERAL/IMPORTANT/CORE`，已定义 `GENERAL < IMPORTANT < CORE` 顺序）；`DataDomain ∈ {"研发","生产","运维","管理","外部"}`（`RND/PRODUCTION/OPS/MANAGEMENT/EXTERNAL`）。**打标器的输出必须能直接构造出合法的 `MetaFields`**，每个产出任务加一条"产物 validates as MetaFields"的断言。**禁止改动 P0 已冻结契约的签名/取值。**
- **数据分类 = 工信部三级**（一般/重要/核心）映射到 `DataLevel`。**打标是纯确定性逻辑**（架构 §11.3：domain 不用 LLM；level 三步皆规则；**LLM 最多建议，不拍板高敏感级**），必须单元可测、**不依赖运行中的 RAGFlow/LLM**。
- **存疑一律往高判**（风险不对称：判低=泄露）。**核心数据必须人工确认**并对齐"客户已备案目录"——管线对疑似核心只能产出"建议级别 + `needs_human_confirmation` 标记"，不得自动拍板为核心。
- **AGE 索引策略落地（架构 §8）**：入口属性索引（`part_id`/`cert_id`/`ecn_id`/`spec_id`）、高频 elabel 边表索引（`affects`/`certifies`/`supersedes`）、深度封顶、统一走索引的 Cypher 写法规范。"索引生效可验证" = **EXPLAIN 显示走了索引（index scan / index hit）**，而非仅"索引对象存在"。
- **部署规范（CLAUDE.md）**：docker-compose 网络用 `1panel-network`；数据卷挂载到 `/data/industriax/`；compose `name: industriax`（沿用 P0，本计划不重写 compose 骨架，只在 Task 1 起栈、Task 2 接 Postgres 初始化、Task 1 补 RAGFlow server 运行时接线）。
- **依赖：P1 依赖 P0**（main HEAD=`bf23e44`，契约 + MCP 骨架 + compose 全栈 + 自定义 Postgres 镜像已就绪并加固）。Task 内部依赖：Task 1（起栈）与 Task 2（schema）为后续需 DB 的任务提供运行底座；纯逻辑 Task 3/4 无 DB 依赖、可并行；Task 5 消费 Task 3/4；Task 6/7 需 DB（依赖 Task 2 的 schema）；Task 8 横切，依赖前序全部。
- **每个任务 TDD**：先写失败测试 → 看它失败 → 最小实现 → 看它通过 → 提交并 push origin/main（CLAUDE.md DoD：push 才算完成，Issue 评论附 commit hash）。

### 任务的"纯逻辑 vs 需栈"标注（便于无栈环境分流）

| Task | 类型 | TDD 循环是否需跑着的栈/DB |
|---|---|---|
| 1 整栈起绿 + RAGFlow 运行时接线 | 集成 | **需**（公网通畅节点上的整栈，非单元可测） |
| 2 Postgres 三库 schema 隔离 | 数据层 | **需** Postgres(AGE+pgvector) |
| 3 domain 确定性分类器 | 纯逻辑 | 否（纯函数单测） |
| 4 level 三步定级器 | 纯逻辑 | 否（纯函数单测） |
| 5 入库打标管线（解析骨架→打标→落库） | 混合 | parse→tag→transform 段 **否**（注入假解析结果）；DB 写段 **需**（薄接缝，独立标记） |
| 6 AGE 图 schema + 索引策略 | 图层 | **需** Postgres(AGE) |
| 7 合规图边写入路径骨架 | 图层 | **需** Postgres(AGE) |
| 8 横切集成测试场景 | 集成 | **需** 整栈（合成样例端到端） |

---

### Task 1: 整栈起绿冒烟（顺延自 P0）+ RAGFlow server 运行时接线

> 这是 Issue 收口选项"乙"约定的 P1 第一步：P0 代码已完整加固（main HEAD=`bf23e44`，自定义 `Dockerfile.postgres` = AGE+pgvector、ragflow 改 slim、TEI reranker 在 .163），但"整栈 `docker compose up` + `smoke_health.sh` 全绿"因开发节点 GTRDev-CY（192.168.66.41）拉 docker.io 反复超时未跑齐。本 Task 在**一台公网通畅的节点**上把整栈起到全绿，并补上 P0 没接完的 **RAGFlow server 真实运行时配置接线**（其自带 MySQL/Valkey/MinIO/Infinity 栈的连接与初始化）——这是 P1 才落的活，使 doc 检索后端在 P2 可直接接入。

**类型：集成任务（非单元可测）。** 验收锚点是脚本退出码与各服务 healthcheck，不是 pytest 断言。

**Files:**
- Modify: `deploy/docker-compose.yml`（补全 RAGFlow server 服务的运行时 env / depends_on / 卷接线与 healthcheck；不动 P0 已稳的 postgres/mysql/valkey 骨架）
- Modify: `deploy/.env.example`（补 RAGFlow server 所需运行时变量占位）
- Create: `deploy/RAGFLOW.md`（RAGFlow 自带栈接线说明 + 首次解析模型落卷说明）
- Modify: `scripts/smoke_health.sh`（把 ragflow server 纳入健康轮询；保持单卡串行起栈语义）

**Interfaces:**
- Consumes: P0 的 `deploy/docker-compose.yml`、`industriax/postgres-age-pgvector:pg16` 镜像、`/data/industriax/{postgres,mysql,valkey}` 已保留的数据卷。
- Produces: 在公网通畅节点上 `docker compose -f deploy/docker-compose.yml up -d` 起全栈；`scripts/smoke_health.sh` 退出 0；**ragflow server healthcheck 绿**（doc 检索后端就绪）。

- [ ] **Step 1: 写失败测试（配置层静态校验，可无栈跑）**

```python
# tests/deploy/test_ragflow_wiring.py
import subprocess, pathlib, yaml

COMPOSE = pathlib.Path("deploy/docker-compose.yml")

def test_ragflow_server_is_wired():
    out = subprocess.run(
        ["docker", "compose", "-f", str(COMPOSE), "config"],
        capture_output=True, text=True,
    )
    assert out.returncode == 0, out.stderr
    spec = yaml.safe_load(out.stdout)
    services = spec["services"]
    assert "ragflow" in services, "ragflow server service missing"
    rf = services["ragflow"]
    # 必须接上自带栈、有 healthcheck、依赖元数据库与缓存就绪
    assert "healthcheck" in rf
    deps = rf.get("depends_on", {})
    for backend in ["mysql", "valkey"]:
        assert backend in deps, f"ragflow must depend_on {backend}"
```

- [ ] **Step 2: 运行测试确认失败**

Run: `./.venv/bin/pytest tests/deploy/test_ragflow_wiring.py -v`
Expected: FAIL — ragflow server 服务尚未在 compose 中接线 / 无 healthcheck / 无 depends_on。

- [ ] **Step 3: 最小实现**

在 `deploy/docker-compose.yml` 内补 `ragflow` server 服务（slim 镜像 `infiniflow/ragflow:v0.20.5-slim`），接上其自带栈（mysql/valkey/minio/infinity）的连接 env，`depends_on` 上述后端 `service_healthy`，挂 `/data/industriax/ragflow` 卷（解析模型首次下载落卷），加 healthcheck（探 ragflow server 端口）。在 `deploy/.env.example` 补 RAGFlow 运行时变量占位。`scripts/smoke_health.sh` 的健康轮询天然按 `docker compose ps` 全量探测，确认 ragflow 已纳入即可（必要时补它的等待窗口；保持单卡串行起栈语义与现有 600s deadline）。`deploy/RAGFLOW.md` 记录：自带栈角色、运行时变量、首次解析 deepdoc 模型落卷（~1.5–2GB）与离线预置方式。

> 注：RAGFlow slim 镜像把内嵌模型剥离、Embedding/Rerank 走外部（.163 TEI），运行时配置以所装 ragflow 版本的官方 compose 为准；以"`ragflow` 服务在 compose 内、有 healthcheck、依赖其自带栈、`smoke_health.sh` 把它探绿"为验收锚点接线，不照搬过期字段名。

- [ ] **Step 4: 运行测试确认通过 + 整栈集成冒烟**

Run（配置静态校验，可无栈）: `./.venv/bin/pytest tests/deploy/test_ragflow_wiring.py -v` → PASS。
集成冒烟（**需在公网通畅节点执行**，见末尾开放决策"Task 1 跑在哪个节点"）：
```bash
docker compose -f deploy/docker-compose.yml up -d
bash scripts/smoke_health.sh        # 期望退出 0：postgres/mysql/valkey/temporal/minio/infinity/ragflow/4×MCP 全 healthy
```
Expected: `smoke_health.sh` 退出 0；`docker compose ps` 无 `starting`/`unhealthy`；ragflow server healthy。

- [ ] **Step 5: 提交并推送**

```bash
git add deploy/docker-compose.yml deploy/.env.example deploy/RAGFLOW.md scripts/smoke_health.sh tests/deploy/test_ragflow_wiring.py
git commit -m "feat(deploy): wire RAGFlow server runtime + bring full stack to green (P1 Task1)"
git push
```
并在 Issue 评论记录：执行节点、`smoke_health.sh` 退出码、各服务健康截屏/输出、commit hash。

---

### Task 2: Postgres 三库 schema 隔离（向量 / 图 / Mem0 同实例分 schema；Temporal 库独立）

> 架构 §3.2 / §11.1：单机阶段一个 Postgres 实例承载向量 + 图 + Mem0，用 **schema 隔离**（不拆库——单机拆库无益、仍抢同机 RAM/IO）；**Temporal 库始终独立**（高频写状态，不与业务查询争，由 temporal auto-setup 自管，本 Task 不动它，仅在文档与测试中声明边界）。pgvector 扩展进向量 schema 可见域，AGE 扩展进图可见域。

**类型：数据层（需跑着的 Postgres(AGE+pgvector)）。**

**Files:**
- Create: `deploy/init/schemas.sql`（建三个 schema + 在向量 schema 装/可见 `vector`、图 schema 可见 `age`；最小权限/search_path 约定）
- Create: `industriax/data/__init__.py`
- Create: `industriax/data/schema.py`（schema 名常量 + 一个用 DSN 连接、断言三 schema 与扩展就位的校验函数 `verify_schemas(conn) -> dict`）
- Test: `tests/data/test_schema_isolation.py`（需 DB；用环境变量 DSN，DB 不可用时 `pytest.skip`）

**Interfaces:**
- Consumes: Task 1 的 Postgres 实例（`industriax/postgres-age-pgvector:pg16`）。
- Produces:
  - 三个隔离 schema（命名见**开放决策**，下文用占位 `<vector_schema>`/`<graph_schema>`/`<mem0_schema>`）。
  - `industriax.data.schema`：常量 + `verify_schemas(conn)` 返回 `{"schemas": [...], "vector_ext": bool, "age_ext": bool, "isolated": bool}`。
  - 隔离断言：在一个 schema 建表不污染另一个；扩展在预期可见域内。

- [ ] **Step 1: 写失败测试**

```python
# tests/data/test_schema_isolation.py
import os, pytest, psycopg

DSN = os.environ.get("INDUSTRIAX_PG_DSN")  # e.g. postgresql://postgres:...@localhost:5432/industriax

@pytest.fixture
def conn():
    if not DSN:
        pytest.skip("INDUSTRIAX_PG_DSN not set — schema test needs a running Postgres")
    with psycopg.connect(DSN) as c:
        yield c

def test_three_schemas_exist(conn):
    from industriax.data.schema import VECTOR_SCHEMA, GRAPH_SCHEMA, MEM0_SCHEMA
    with conn.cursor() as cur:
        cur.execute("select schema_name from information_schema.schemata")
        names = {r[0] for r in cur.fetchall()}
    for s in (VECTOR_SCHEMA, GRAPH_SCHEMA, MEM0_SCHEMA):
        assert s in names, f"missing schema {s}"

def test_extensions_present(conn):
    with conn.cursor() as cur:
        cur.execute("select extname from pg_extension")
        ext = {r[0] for r in cur.fetchall()}
    assert "vector" in ext and "age" in ext

def test_schema_isolation(conn):
    # 在向量 schema 建临时表，确认它不出现在图 schema
    from industriax.data.schema import VECTOR_SCHEMA, GRAPH_SCHEMA
    with conn.cursor() as cur:
        cur.execute(f'create table if not exists "{VECTOR_SCHEMA}".iso_probe(id int)')
        cur.execute(
            "select count(*) from information_schema.tables "
            "where table_schema=%s and table_name='iso_probe'", (GRAPH_SCHEMA,))
        assert cur.fetchone()[0] == 0
        cur.execute(f'drop table "{VECTOR_SCHEMA}".iso_probe')

def test_verify_schemas_helper(conn):
    from industriax.data.schema import verify_schemas
    r = verify_schemas(conn)
    assert r["vector_ext"] and r["age_ext"] and r["isolated"]
    assert len(r["schemas"]) == 3
```

- [ ] **Step 2: 运行测试确认失败**

Run: `./.venv/bin/pytest tests/data/test_schema_isolation.py -v`
Expected: 无 DSN 时 SKIP；接上 DB 后 FAIL — schema 未建 / `industriax.data.schema` 不存在。

- [ ] **Step 3: 最小实现**

`deploy/init/schemas.sql`（在 P0 `age.sql` 之后随 `docker-entrypoint-initdb.d` 跑）：建 `<vector_schema>`/`<graph_schema>`/`<mem0_schema>` 三 schema；`CREATE EXTENSION IF NOT EXISTS vector`、`CREATE EXTENSION IF NOT EXISTS age`（扩展在 DB 级，约定各 schema 的 `search_path` 使用边界）；按角色 `GRANT` 最小权限。`industriax/data/schema.py` 定义 `VECTOR_SCHEMA`/`GRAPH_SCHEMA`/`MEM0_SCHEMA` 常量与 `verify_schemas(conn)`（查 `information_schema.schemata` + `pg_extension`，跑一次建表/查表隔离探针）。Temporal 库独立这一点在 `schema.py` docstring 与测试注释中声明：**Temporal 自带 DB 不在此实例的业务 schema 内**。

> 注：AGE 扩展是 DB 级安装，"图归属 `<graph_schema>`"通过 AGE graph 创建在该 schema 下 + search_path 约定实现（详见 Task 6）。本 Task 只保证三 schema 与两扩展就位且互不污染。

- [ ] **Step 4: 运行测试确认通过**

Run（接上 DB，设 `INDUSTRIAX_PG_DSN`）: `./.venv/bin/pytest tests/data/test_schema_isolation.py -v`
Expected: PASS（4 passed）。

- [ ] **Step 5: 提交并推送**

```bash
git add deploy/init/schemas.sql industriax/data/ tests/data/test_schema_isolation.py
git commit -m "feat(data): three-schema isolation (vector/graph/mem0) + verify helper"
git push
```

---

### Task 3: 打标引擎 — domain 确定性分类器（纯逻辑）

> 架构 §11.3：domain 按来源/路径/文档类型**确定性**打，**不用 LLM**。产出 `DataDomain`（研发/生产/运维/管理/外部）。这是纯函数，无栈可单测。

**类型：纯逻辑（无 DB/RAGFlow/LLM）。**

**Files:**
- Create: `industriax/ingest/__init__.py`
- Create: `industriax/ingest/types.py`（入库描述符：解析入口的来源/路径/文档类型，作为打标输入的稳定契约）
- Create: `industriax/ingest/domain.py`（确定性分类器）
- Test: `tests/ingest/test_domain.py`

**Interfaces:**
- Consumes: `industriax.contracts.meta.DataDomain`。
- Produces:
  - `IngestDescriptor(BaseModel)`：`source_system: str | None`、`path: str`、`doc_type: str`（如 `ecn`/`pcn`/`bom`/`fa`/`cert`/`spec`/`memo`…）、可选 `tenant_hint`。**这是 P1 新增的输入类型；它不改动任何 P0 契约。**
  - `classify_domain(d: IngestDescriptor) -> DataDomain`：按确定性规则（来源系统 → 路径前缀 → 文档类型）映射到 `DataDomain`，给出明确的 fallback（如未命中归 `RND` 或由开放决策定）。

- [ ] **Step 1: 写失败测试**

```python
# tests/ingest/test_domain.py
import pytest
from industriax.ingest.types import IngestDescriptor
from industriax.ingest.domain import classify_domain
from industriax.contracts.meta import DataDomain

@pytest.mark.parametrize("doc_type,path,expected", [
    ("ecn", "/rnd/changes/ecn-001.pdf", DataDomain.RND),
    ("bom", "/production/bom/x.csv", DataDomain.PRODUCTION),
    ("fa", "/ops/failure/case-7.pdf", DataDomain.OPS),
    ("cert", "/external/certs/iso.pdf", DataDomain.EXTERNAL),
])
def test_classify_by_type_and_path(doc_type, path, expected):
    d = IngestDescriptor(source_system=None, path=path, doc_type=doc_type)
    assert classify_domain(d) == expected

def test_source_system_takes_precedence():
    # 来源系统优先于路径（确定性顺序）
    d = IngestDescriptor(source_system="MES", path="/misc/x", doc_type="memo")
    assert classify_domain(d) == DataDomain.PRODUCTION

def test_deterministic_same_input_same_output():
    d = IngestDescriptor(source_system=None, path="/rnd/a", doc_type="spec")
    assert classify_domain(d) == classify_domain(d)

def test_unmatched_falls_back():
    d = IngestDescriptor(source_system=None, path="/unknown", doc_type="unknown")
    assert isinstance(classify_domain(d), DataDomain)  # 必有确定 fallback，不抛异常
```

- [ ] **Step 2: 运行测试确认失败**

Run: `./.venv/bin/pytest tests/ingest/test_domain.py -v`
Expected: FAIL — `ModuleNotFoundError: industriax.ingest.domain`。

- [ ] **Step 3: 最小实现**

`industriax/ingest/types.py` 定义 `IngestDescriptor`。`industriax/ingest/domain.py` 实现 `classify_domain`：确定性优先级链（① `source_system` 词典命中 → ② `path` 前缀规则 → ③ `doc_type` 词典 → ④ fallback）。规则用模块级常量字典/前缀表表达，便于审阅与开放决策调整。**纯函数，无 IO。**

- [ ] **Step 4: 运行测试确认通过**

Run: `./.venv/bin/pytest tests/ingest/test_domain.py -v`
Expected: PASS。

- [ ] **Step 5: 提交并推送**

```bash
git add industriax/ingest/__init__.py industriax/ingest/types.py industriax/ingest/domain.py tests/ingest/test_domain.py
git commit -m "feat(ingest): deterministic domain classifier (source/path/doc_type)"
git push
```

---

### Task 4: 打标引擎 — level 三步定级器（默认映射 → 规则升级器 → 存疑往高 + 核心需人工确认）（纯逻辑）

> 架构 §11.3 三步：domain→默认级别映射 → 规则升级器（出现客户标识/零件号/证书号/个人信息则升级）→ **存疑一律往高**。**核心数据必须人工确认**并对齐"客户已备案目录"——本引擎对疑似核心**只建议、不拍板**，输出 `needs_human_confirmation` 标记；"客户已备案目录"作为**注入依赖**（catalog），保持纯单测。产出严格等于 P0 冻结的 `DataLevel`。

**类型：纯逻辑（catalog 注入，无 DB/LLM）。**

**Files:**
- Create: `industriax/ingest/level.py`（三步定级器 + 升级规则 + 备案目录注入接口）
- Test: `tests/ingest/test_level.py`

**Interfaces:**
- Consumes: `industriax.contracts.meta.DataLevel`、`DataDomain`；Task 3 的 `IngestDescriptor`。
- Produces:
  - `CoreCatalog`（协议/简单可注入容器）：`is_registered_core(descriptor_or_key) -> bool`，由客户已备案目录播种（格式见**开放决策**）；默认空目录用于纯单测。
  - `LevelDecision(BaseModel)`：`level: DataLevel`、`needs_human_confirmation: bool`、`reasons: list[str]`（哪几条规则触发，供数据治理 UI 复核）。
  - `decide_level(descriptor: IngestDescriptor, text_signals: TextSignals, *, catalog: CoreCatalog) -> LevelDecision`，其中 `TextSignals` 是从解析结果抽出的确定性命中布尔位（`has_customer_id`/`has_part_no`/`has_cert_no`/`has_personal_info`…，由 Task 5 的规则升级器从解析文本算出、此处只消费布尔位以保持纯逻辑）。
  - 三步语义：①`DEFAULT_DOMAIN_LEVEL[domain]` 取默认级别 → ② 任一升级信号命中 → 升一级（至少到重要）→ ③ 不确定/边界一律取较高级别；命中备案核心或疑似核心 → `level` 建议为 `CORE`/次高且 `needs_human_confirmation=True`。
  - **产物对齐**：`LevelDecision.level` 直接喂给 `MetaFields(data_level=...)` 合法。

- [ ] **Step 1: 写失败测试**

```python
# tests/ingest/test_level.py
import pytest
from industriax.ingest.types import IngestDescriptor
from industriax.ingest.level import decide_level, LevelDecision, TextSignals, CoreCatalog
from industriax.contracts.meta import DataLevel, DataDomain, MetaFields, Provenance

EMPTY = CoreCatalog()  # 空备案目录
NONE_SIG = TextSignals()  # 全 False

def desc(doc_type="memo", path="/rnd/x", src=None):
    return IngestDescriptor(source_system=src, path=path, doc_type=doc_type)

def test_default_mapping_no_signal():
    d = decide_level(desc(), NONE_SIG, catalog=EMPTY)
    assert isinstance(d, LevelDecision)
    assert d.level == DataLevel.GENERAL  # 假设研发 memo 默认一般
    assert d.needs_human_confirmation is False

def test_rule_upgrades_on_part_or_cert():
    sig = TextSignals(has_part_no=True)
    d = decide_level(desc(), sig, catalog=EMPTY)
    assert d.level >= DataLevel.IMPORTANT
    assert d.reasons  # 记录了触发原因

def test_personal_info_upgrades():
    sig = TextSignals(has_personal_info=True)
    d = decide_level(desc(), sig, catalog=EMPTY)
    assert d.level >= DataLevel.IMPORTANT

def test_doubt_rounds_up():
    # 边界/存疑信号 → 取较高级别（判低=泄露，风险不对称）
    sig = TextSignals(ambiguous=True)
    d = decide_level(desc(), sig, catalog=EMPTY)
    assert d.level >= DataLevel.IMPORTANT

def test_registered_core_needs_confirmation():
    cat = CoreCatalog(keys={"/rnd/x|memo"})  # 已备案核心（key 形态见实现）
    d = decide_level(desc(), NONE_SIG, catalog=cat)
    assert d.level == DataLevel.CORE
    assert d.needs_human_confirmation is True   # 核心必须人工确认，引擎不拍板

def test_suspected_core_suggests_but_flags_human():
    # 多个高敏感信号叠加但未在备案目录 → 建议高 + 需人工确认，不自动定核心
    sig = TextSignals(has_customer_id=True, has_cert_no=True, has_part_no=True)
    d = decide_level(desc(), sig, catalog=EMPTY)
    assert d.needs_human_confirmation is True
    assert d.level >= DataLevel.IMPORTANT

def test_output_constructs_valid_metafields():
    d = decide_level(desc(), TextSignals(has_part_no=True), catalog=EMPTY)
    mf = MetaFields(
        data_level=d.level, data_domain=DataDomain.RND,
        source=Provenance(doc_id="x", version="v1", section=None),
    )
    assert mf.data_level == d.level  # 产物严格符合 P0 冻结契约
```

- [ ] **Step 2: 运行测试确认失败**

Run: `./.venv/bin/pytest tests/ingest/test_level.py -v`
Expected: FAIL — `ModuleNotFoundError: industriax.ingest.level`。

- [ ] **Step 3: 最小实现**

`industriax/ingest/level.py`：
- `TextSignals(BaseModel)`：确定性布尔命中位（`has_customer_id`/`has_part_no`/`has_cert_no`/`has_personal_info`/`ambiguous`…全默认 False）。
- `CoreCatalog`：可注入的已备案核心键集合（`keys: set[str]`），`is_registered_core(key) -> bool`。
- `DEFAULT_DOMAIN_LEVEL: dict[DataDomain, DataLevel]`（默认映射表，**取值见开放决策**）。
- `decide_level(...)`：① 取默认级别 → ② 任一升级信号 → 升级并记 `reasons` → ③ `ambiguous` 或多信号叠加 → 取较高（存疑往高）→ 备案核心或疑似核心 → 建议 `CORE`/次高 + `needs_human_confirmation=True`。**全程纯逻辑、无 IO、无 LLM。** 利用 P0 已实现的 `DataLevel` 顺序比较（`>=`/`<`）做"往高"逻辑。

- [ ] **Step 4: 运行测试确认通过**

Run: `./.venv/bin/pytest tests/ingest/test_level.py -v`
Expected: PASS（含"存疑往高""核心需确认""产物=MetaFields"边界）。

- [ ] **Step 5: 提交并推送**

```bash
git add industriax/ingest/level.py tests/ingest/test_level.py
git commit -m "feat(ingest): three-step level grader (default->upgrade->round-up, core needs human)"
git push
```

---

### Task 5: 入库打标管线（RAGFlow 解析入口骨架 → 调打标 → 落库带三元标签）

> 把 Task 3/4 串成管线：解析入口（RAGFlow）产出 chunk + 元信息 → 规则升级器从文本算 `TextSignals` → `classify_domain` + `decide_level` → 组装 `MetaFields` → 落库（带三元标签）。**解析与 DB 写都做成可注入的薄接缝**：parse→tag→transform 段用注入的假解析结果纯单测；DB 写段是独立、薄、需 DB 的接缝，单独标记与测试。

**类型：混合。** 转换段纯逻辑（注入假解析结果，无栈）；落库段需 DB（薄接缝）。

**Files:**
- Create: `industriax/ingest/signals.py`（从解析文本确定性抽 `TextSignals` 的规则升级器：正则/词典命中客户标识/零件号/证书号/个人信息——具体规则形态见开放决策，本 Task 给可测骨架）
- Create: `industriax/ingest/pipeline.py`（编排：`ParseResult`→`TaggedRecord` 转换 + `parse_via_ragflow` 注入点 + `sink` 落库注入点）
- Create: `industriax/ingest/sink.py`（DB 落库薄接缝：把 `TaggedRecord` 写入向量/图/Mem0 对应 schema 的入库表）
- Test: `tests/ingest/test_pipeline.py`（转换段纯单测）
- Test: `tests/ingest/test_sink_db.py`（落库段，需 DB，无 DSN 时 skip）

**Interfaces:**
- Consumes: Task 3 `classify_domain`/`IngestDescriptor`；Task 4 `decide_level`/`TextSignals`/`CoreCatalog`；Task 2 `industriax.data.schema`。
- Produces:
  - `ParseResult(BaseModel)`：RAGFlow 解析入口的最小契约（`doc_id`/`version`/`section`/`text`/`chunks`）——**注入边界**，真实硬化随真样本在后续迭代（架构 §2.1 合成样例先行）。
  - `extract_signals(text: str) -> TextSignals`（规则升级器，纯函数）。
  - `TaggedRecord(BaseModel)`：`chunk: str` + `meta: MetaFields`（三元标签随每条数据落库）。
  - `tag_parse_result(parse: ParseResult, descriptor: IngestDescriptor, *, catalog: CoreCatalog) -> list[TaggedRecord]`（纯转换，无 IO）。
  - `run_ingest(descriptor, *, parse_fn, sink_fn, catalog)`（编排，解析/落库都注入，便于无栈测；默认 `parse_fn=parse_via_ragflow`、`sink_fn=db_sink`）。
  - `db_sink(records, *, conn)`（落库薄接缝，写带三元标签的行）。

- [ ] **Step 1: 写失败测试**

```python
# tests/ingest/test_pipeline.py  (纯逻辑，无栈)
from industriax.ingest.types import IngestDescriptor
from industriax.ingest.pipeline import ParseResult, TaggedRecord, tag_parse_result, run_ingest
from industriax.ingest.signals import extract_signals
from industriax.ingest.level import CoreCatalog, TextSignals
from industriax.contracts.meta import MetaFields, DataLevel

def test_extract_signals_hits_part_no():
    sig = extract_signals("零件号 PN-12345 见附件")
    assert isinstance(sig, TextSignals)
    assert sig.has_part_no is True

def test_tag_produces_metafields_per_chunk():
    parse = ParseResult(doc_id="d1", version="v1", section="3",
                        text="客户 ACME 证书号 CERT-9",
                        chunks=["客户 ACME 证书号 CERT-9"])
    d = IngestDescriptor(source_system=None, path="/external/certs/x", doc_type="cert")
    recs = tag_parse_result(parse, d, catalog=CoreCatalog())
    assert recs and all(isinstance(r.meta, MetaFields) for r in recs)
    assert recs[0].meta.data_level >= DataLevel.IMPORTANT  # 证书号触发升级
    assert recs[0].meta.source.doc_id == "d1"

def test_run_ingest_with_injected_parse_and_sink():
    fake_parse = ParseResult(doc_id="d2", version="v1", section=None,
                            text="一般备忘", chunks=["一般备忘"])
    written = []
    run_ingest(
        IngestDescriptor(source_system=None, path="/rnd/m", doc_type="memo"),
        parse_fn=lambda d: fake_parse,
        sink_fn=lambda recs, **kw: written.extend(recs),
        catalog=CoreCatalog(),
    )
    assert written and isinstance(written[0], TaggedRecord)
```

```python
# tests/ingest/test_sink_db.py  (需 DB)
import os, pytest, psycopg
DSN = os.environ.get("INDUSTRIAX_PG_DSN")

@pytest.mark.skipif(not DSN, reason="needs running Postgres")
def test_db_sink_writes_tagged_rows():
    from industriax.ingest.sink import db_sink
    from industriax.ingest.pipeline import TaggedRecord
    from industriax.contracts.meta import MetaFields, DataLevel, DataDomain, Provenance
    rec = TaggedRecord(chunk="x", meta=MetaFields(
        data_level=DataLevel.IMPORTANT, data_domain=DataDomain.RND,
        source=Provenance(doc_id="d", version="v1", section=None)))
    with psycopg.connect(DSN) as c:
        db_sink([rec], conn=c)
        # 断言写入行带三元标签（表名/schema 见实现）
```

- [ ] **Step 2: 运行测试确认失败**

Run: `./.venv/bin/pytest tests/ingest/test_pipeline.py -v`
Expected: FAIL — `industriax.ingest.pipeline` 不存在。

- [ ] **Step 3: 最小实现**

`signals.py`：`extract_signals(text)` 用模块级正则/词典命中客户标识/零件号/证书号/个人信息 → `TextSignals`（纯函数，规则可调）。`pipeline.py`：`ParseResult`/`TaggedRecord` 模型；`tag_parse_result` = 逐 chunk 调 `extract_signals` → `classify_domain` → `decide_level` → 组 `MetaFields`（`source` 取自 `ParseResult`）→ `TaggedRecord`；`parse_via_ragflow(descriptor)` 是 RAGFlow 解析入口骨架（最小可测，真硬化随真样本，**默认实现可先 raise NotImplemented 或薄 client 调用，测试一律注入假 parse_fn**）；`run_ingest` 编排注入点。`sink.py`：`db_sink(records, *, conn)` 把带三元标签的记录写入 Task 2 各 schema 的入库表（最小列：chunk + data_level + data_domain + source 三字段）。

- [ ] **Step 4: 运行测试确认通过**

Run（纯逻辑）: `./.venv/bin/pytest tests/ingest/test_pipeline.py -v` → PASS。
Run（落库段，设 DSN）: `./.venv/bin/pytest tests/ingest/test_sink_db.py -v` → PASS（无 DSN 时 SKIP）。

- [ ] **Step 5: 提交并推送**

```bash
git add industriax/ingest/signals.py industriax/ingest/pipeline.py industriax/ingest/sink.py tests/ingest/test_pipeline.py tests/ingest/test_sink_db.py
git commit -m "feat(ingest): parse->tag->sink pipeline with injectable parse & db sink"
git push
```

---

### Task 6: AGE 图 schema + 索引策略（vlabel/elabel + 入口属性索引 + 边表索引 + 走索引 Cypher 规范）

> 架构 §8：AGE 默认不建索引、带/不带 WHERE 走不同路径——图层唯一会真出问题的点。本 Task 在 `<graph_schema>` 下建 AGE graph、定义合规图 vlabel/elabel，建**入口属性索引**（`part_id`/`cert_id`/`ecn_id`/`spec_id`）与**高频 elabel 边表索引**（`affects`/`certifies`/`supersedes`），写**走索引 Cypher 规范文档**，并用 EXPLAIN 验证**索引命中**（"索引生效可验证" = index scan，非仅"索引存在"）。

**类型：图层（需跑着的 Postgres(AGE)）。**

**Files:**
- Create: `deploy/init/age_graph.sql`（建 graph、vlabel/elabel、入口属性索引、边表索引、深度封顶约定注释）
- Create: `industriax/graph/__init__.py`
- Create: `industriax/graph/schema.py`（graph 名 + vlabel/elabel 常量 + `verify_indexes(conn) -> dict`：列出已建索引；`explain_uses_index(conn, cypher) -> bool`：跑 EXPLAIN 断言 index scan）
- Create: `docs/IndustriaX_AGE_Cypher_Guidelines.md`（走索引 Cypher 写法规范：属性匹配 vs WHERE 的差异、max_hops 封顶、热路径物化预案——对齐架构 §8）
- Test: `tests/graph/test_age_indexes.py`（需 DB；无 DSN skip）

**Interfaces:**
- Consumes: Task 2 `<graph_schema>`、AGE 扩展。
- Produces:
  - 合规图 vlabel（如 `Part`/`Change`/`Cert`/`Spec`）与 elabel（`affects`/`certifies`/`supersedes`）。
  - 入口属性索引：`part_id`/`cert_id`/`ecn_id`/`spec_id` 在对应 vlabel。
  - 边表索引：高频 elabel 按端点建索引。
  - `industriax.graph.schema`：常量 + `verify_indexes(conn)` + `explain_uses_index(conn, cypher)`。
  - `docs/IndustriaX_AGE_Cypher_Guidelines.md`：团队统一走索引写法。

- [ ] **Step 1: 写失败测试**

```python
# tests/graph/test_age_indexes.py
import os, pytest, psycopg
DSN = os.environ.get("INDUSTRIAX_PG_DSN")

@pytest.fixture
def conn():
    if not DSN:
        pytest.skip("needs running Postgres(AGE)")
    with psycopg.connect(DSN) as c:
        yield c

def test_entry_property_indexes_exist(conn):
    from industriax.graph.schema import verify_indexes
    idx = verify_indexes(conn)
    for key in ["part_id", "cert_id", "ecn_id", "spec_id"]:
        assert any(key in name for name in idx["entry_property"]), f"missing entry index {key}"

def test_edge_indexes_exist(conn):
    from industriax.graph.schema import verify_indexes
    idx = verify_indexes(conn)
    for el in ["affects", "certifies", "supersedes"]:
        assert any(el in name for name in idx["edge"]), f"missing edge index {el}"

def test_entry_lookup_uses_index(conn):
    # 索引"生效"= EXPLAIN 走 index scan，而非仅存在
    from industriax.graph.schema import explain_uses_index, ENTRY_LOOKUP_CYPHER
    assert explain_uses_index(conn, ENTRY_LOOKUP_CYPHER) is True
```

- [ ] **Step 2: 运行测试确认失败**

Run: `./.venv/bin/pytest tests/graph/test_age_indexes.py -v`
Expected: 无 DSN SKIP；接 DB 后 FAIL — graph/索引未建 / `industriax.graph.schema` 不存在。

- [ ] **Step 3: 最小实现**

`deploy/init/age_graph.sql`：`SELECT create_graph('<graph_name>')`（建在 `<graph_schema>` 下）；创建 vlabel/elabel；在 AGE vertex 属性的物化列/表上建入口属性 B-tree 索引（按 AGE 实际存储形态，对 `agtype` 属性用表达式索引/属性提取索引——以"EXPLAIN 命中"为锚点选具体写法）；高频 elabel 按端点建索引；注释写明 max_hops 封顶（2–4）与热路径物化预案。`industriax/graph/schema.py`：graph/label 常量、`verify_indexes(conn)`（查 `pg_indexes` 过滤 graph schema）、`explain_uses_index(conn, cypher)`（跑 `EXPLAIN` 解析计划文本，断言出现 index scan 而非 seq scan），并提供 `ENTRY_LOOKUP_CYPHER` 范例。`docs/IndustriaX_AGE_Cypher_Guidelines.md`：属性匹配 vs WHERE、走索引写法、深度封顶、物化视图预案（对齐架构 §8 五条）。

> 注：AGE 在 `agtype` 上建可命中索引的写法依 AGE 1.6.0 版本而定（属性提取表达式索引）；以 `explain_uses_index` 返回 True（index scan）为硬验收锚点调整索引 DDL，策略不变。

- [ ] **Step 4: 运行测试确认通过**

Run（设 DSN）: `./.venv/bin/pytest tests/graph/test_age_indexes.py -v`
Expected: PASS（入口索引存在 + 边索引存在 + EXPLAIN 命中）。

- [ ] **Step 5: 提交并推送**

```bash
git add deploy/init/age_graph.sql industriax/graph/ docs/IndustriaX_AGE_Cypher_Guidelines.md tests/graph/test_age_indexes.py
git commit -m "feat(graph): AGE vlabel/elabel + entry & edge indexes + index-hit verification + Cypher guidelines"
git push
```

---

### Task 7: 合规图边写入路径最小骨架（part↔change↔cert 边录入 API）

> 架构 §4.5 标注的隐藏缺口：合规属性图是**人工策展**的，需要录入零件↔变更↔证书的边。本 Task 只做**写入路径/API 骨架**（供后续 Admin UI 图策展界面接入），**显式把 Admin UI 图策展界面本身延后到 P5**。范围严格限于"合规图建得起"这条锚点所需的最小边写入。

**类型：图层（需跑着的 Postgres(AGE)）。**

**Files:**
- Create: `industriax/graph/curate.py`（边写入路径：`upsert_part`/`upsert_change`/`upsert_cert` + `link_affects`/`link_certifies`/`link_supersedes`，走 Task 6 的 graph/label，写索引友好的 Cypher）
- Test: `tests/graph/test_curate.py`（需 DB；无 DSN skip）

**Interfaces:**
- Consumes: Task 6 `industriax.graph.schema`（graph/label 常量、走索引 Cypher 规范）。
- Produces: 节点 upsert 与三类边的录入函数；写入后可被 `graph.impact`（P2 接）遍历到。**仅写入路径，不含 UI、不含鉴权（P5 经 API Gateway 接）。**

- [ ] **Step 1: 写失败测试**

```python
# tests/graph/test_curate.py
import os, pytest, psycopg
DSN = os.environ.get("INDUSTRIAX_PG_DSN")

@pytest.fixture
def conn():
    if not DSN:
        pytest.skip("needs running Postgres(AGE)")
    with psycopg.connect(DSN) as c:
        yield c

def test_curate_part_change_cert_edges(conn):
    from industriax.graph import curate
    curate.upsert_part(conn, part_id="PN-1")
    curate.upsert_change(conn, ecn_id="ECN-1")
    curate.upsert_cert(conn, cert_id="CERT-1")
    curate.link_affects(conn, ecn_id="ECN-1", part_id="PN-1")
    curate.link_certifies(conn, cert_id="CERT-1", part_id="PN-1")
    # 录入后可遍历到：从 ECN-1 经 affects 找到 PN-1
    hops = curate.neighbors_via(conn, start_id="ECN-1", edge="affects")
    assert "PN-1" in hops
```

- [ ] **Step 2: 运行测试确认失败**

Run: `./.venv/bin/pytest tests/graph/test_curate.py -v`
Expected: 无 DSN SKIP；接 DB 后 FAIL — `industriax.graph.curate` 不存在。

- [ ] **Step 3: 最小实现**

`industriax/graph/curate.py`：节点 upsert（按入口属性 `part_id`/`ecn_id`/`cert_id`/`spec_id` 走索引匹配，存在则更新、否则建）、三类边录入（`affects`/`certifies`/`supersedes`），一个最小 `neighbors_via` 辅助用于测试可遍历性。全部用 Task 6 规范的走索引 Cypher。**不含 UI / 鉴权 / 审计——那些在 P5 经 API Gateway + Admin UI 图策展界面落地。**

- [ ] **Step 4: 运行测试确认通过**

Run（设 DSN）: `./.venv/bin/pytest tests/graph/test_curate.py -v`
Expected: PASS（边录入 + 可遍历）。

- [ ] **Step 5: 提交并推送**

```bash
git add industriax/graph/curate.py tests/graph/test_curate.py
git commit -m "feat(graph): minimal compliance-graph edge write path (part/change/cert)"
git push
```

---

### Task 8: 横切集成测试场景（合成样例端到端证明四条锚点）

> 架构 §2.1：先用合成样例。本 Task 用合成 ECN/BOM/证书样例跑端到端：解析骨架 → 打标 → 落库 → 建合规图边 → 索引命中遍历，在一个测试套件里同时证明四条 P1 验收锚点：**文档进得来、打标正确、合规图建得起、索引生效可验证**。

**类型：集成（需整栈/DB）。**

**Files:**
- Create: `tests/integration/__init__.py`
- Create: `tests/integration/fixtures/`（合成 ECN/BOM/证书样例，结构贴近真实，无真实客户数据）
- Create: `tests/integration/test_p1_anchors.py`（需 DB；无 DSN skip；标 `@pytest.mark.integration`）

**Interfaces:**
- Consumes: Task 2–7 全部产物。
- Produces: 一个端到端测试，逐锚点断言：① 合成文档经管线进库（行存在）；② 三元标签符合预期（含一条"证书号→升级”“疑似核心→需人工确认"用例）；③ 合规图边建起且可遍历；④ 入口查询 EXPLAIN 命中索引。

- [ ] **Step 1: 写失败测试**

```python
# tests/integration/test_p1_anchors.py
import os, pytest, psycopg
DSN = os.environ.get("INDUSTRIAX_PG_DSN")
pytestmark = pytest.mark.integration

@pytest.fixture
def conn():
    if not DSN:
        pytest.skip("integration needs running Postgres(AGE+pgvector)")
    with psycopg.connect(DSN) as c:
        yield c

def test_anchor_doc_in_and_tagged(conn):
    # 文档进得来 + 打标正确
    from industriax.ingest.pipeline import run_ingest, ParseResult
    from industriax.ingest.types import IngestDescriptor
    from industriax.ingest.level import CoreCatalog
    from industriax.ingest.sink import db_sink
    from industriax.contracts.meta import DataLevel
    # 合成证书样例：含证书号，应升级
    ...  # 用 fixtures 里的合成 cert，断言落库行 data_level >= 重要

def test_anchor_graph_built_and_index_hit(conn):
    # 合规图建得起 + 索引生效可验证
    from industriax.graph import curate, schema
    ...  # 录入 ECN/Part/Cert 边，遍历得到、EXPLAIN 命中入口索引
```

- [ ] **Step 2: 运行测试确认失败**

Run: `./.venv/bin/pytest tests/integration/test_p1_anchors.py -v`
Expected: 无 DSN SKIP；接 DB 后 FAIL — 样例/断言未就绪。

- [ ] **Step 3: 最小实现**

造合成 ECN/BOM/证书 fixtures（结构贴近真实、无真实客户数据）；实现端到端断言：管线落库行存在且三元标签符合预期（含升级与"疑似核心需人工确认"用例）、合规图边建起可遍历、入口查询 EXPLAIN 命中索引。

- [ ] **Step 4: 运行测试确认通过**

Run（设 DSN，在 Task 1 起绿的节点上）: `./.venv/bin/pytest tests/integration/test_p1_anchors.py -v`
Expected: PASS（四锚点全绿）。

- [ ] **Step 5: 提交并推送**

```bash
git add tests/integration/
git commit -m "test(integration): P1 four-anchor end-to-end on synthetic samples"
git push
```

---

## P1 验收（全部满足才算 P1 完成）

四条锚点 ↔ Task 映射：

| 验收锚点 | 由哪些 Task 证明 |
|---|---|
| **文档进得来** | Task 1（RAGFlow server 起绿 + 解析入口）+ Task 5（parse→tag→落库管线）+ Task 8 ① |
| **打标正确** | Task 3（domain 确定性）+ Task 4（level 三步/存疑往高/核心需确认）+ Task 5（产物=MetaFields）+ Task 8 ② |
| **合规图建得起** | Task 6（vlabel/elabel）+ Task 7（边写入路径）+ Task 8 ③ |
| **索引生效可验证** | Task 6（入口/边索引 + EXPLAIN 命中）+ Task 8 ④ |

- [ ] `./.venv/bin/pytest`（纯逻辑部分：ingest domain/level/pipeline，无需 DB）全绿。
- [ ] 接上 Postgres(AGE+pgvector) 后，`./.venv/bin/pytest`（含 data/graph/integration）全绿（无 DSN 的环境这些 SKIP，属预期）。
- [ ] `./.venv/bin/ruff check .` 与 `./.venv/bin/mypy industriax` 无错。
- [ ] **在公网通畅节点** `docker compose up -d` + `scripts/smoke_health.sh` 退出 0（含 ragflow server healthy）。
- [ ] 打标产出严格对齐 P0 冻结契约：`MetaFields`/`DataLevel`/`DataDomain` 取值未改；每个产出任务有"产物 validates as MetaFields"断言。
- [ ] 入库打标为纯确定性逻辑：domain/level/signals 单测不依赖运行中的 RAGFlow/LLM；核心数据走 `needs_human_confirmation`、引擎不自动拍板。
- [ ] AGE 索引"生效可验证"= EXPLAIN 命中（非仅存在）；走索引 Cypher 规范文档已成文。
- [ ] 所有 commit 已 push origin/main；Issue 评论附 commit hash；配置变更（compose、init SQL、smoke 脚本）一并提交。

## Self-Review 记录

- **Spec 覆盖**：本计划覆盖 spec §5 表 P1 行的全部交付物——RAGFlow 解析硬化骨架（Task 1/5）、Postgres 三库 schema 隔离（Task 2）、入库即打标管线含 domain 确定性 + level 三步 + 存疑往高 + 核心人工确认（Task 3/4/5）、AGE vlabel/elabel + 索引策略落地（架构 §8，Task 6），并补合规图边写入路径（Task 7，§4.5 缺口的最小骨架）与横切集成（Task 8）。**范围不扩大**：Admin UI 图策展界面、graph.impact/doc.search 等 MCP 工具实现、Router/Harness 均不在 P1，留 P2/P3/P5。
- **与 P0 契约一致性**：打标产出严格用 P0 冻结的 `MetaFields`/`DataLevel`/`DataDomain`/`Provenance`（`industriax/contracts/meta.py`），未改其签名/取值；P1 新增的 `IngestDescriptor`/`TextSignals`/`LevelDecision`/`ParseResult`/`TaggedRecord` 都是新输入/中间类型，不触碰契约层。
- **环境差异已处理**：全部命令用 `./.venv/bin/pytest`（非 P0 模板的 `uv run`，本环境无 uv）。
- **纯逻辑 vs 需栈已分流**：Task 3/4 及 Task 5 转换段无栈可测；Task 1/2/6/7/8 及 Task 5 落库段需 DB，且需 DB 的测试统一用 `INDUSTRIAX_PG_DSN` + 无 DSN SKIP，使无栈环境仍能跑大部分单测。
- **依赖标注**：P1 依赖 P0（HEAD `bf23e44`）；整栈起绿是顺延的第一步（Task 1，需公网通畅节点）；Task 内部依赖与并行性见 Global Constraints。
- **占位符扫描**：无 TBD/TODO 残留；AGE/RAGFlow 版本相关写法处给出"EXPLAIN 命中 / healthcheck 绿"为验收锚点以应对版本差异，非占位。真正待用户拍板的设计分叉集中列入下节。

---

## 开放决策（待张俊确认）

以下每条都是会改变实现的真实分叉，需用户拍板后再进对应 Task：

1. **三个 schema 的命名**（Task 2）：向量/图/Mem0 三 schema 用什么名？建议 `iax_vector` / `iax_graph` / `iax_mem0`（或中文/无前缀）。涉及 init SQL、`industriax.data.schema` 常量、所有跨层引用。

2. **"客户已备案目录"的播种来源与格式**（Task 4/8）：核心数据备案目录从哪来（客户提供的 CSV / 既有 PLM 导出 / 人工录入）？键的形态是什么（按 doc_type+path？按零件号/证书号清单？）？这决定 `CoreCatalog` 的加载器与 `is_registered_core` 的匹配键设计。

3. **默认 domain→level 映射表的取值**（Task 4）：`DEFAULT_DOMAIN_LEVEL` 每个 domain 的默认级别需对齐客户分类策略。建议默认值：研发/管理=一般，生产/运维=重要，外部=一般——但这是策略默认，需客户已备案目录校准后定稿（架构 §11.3 "分类策略从客户已备案目录播种"）。

4. **规则升级器的标识匹配规则形态**（Task 5，对齐架构 §8 待 B 级项）：客户标识/零件号/证书号/个人信息用正则、词典还是 NER？P1 先用正则+词典骨架，是否够？还是需要可配置规则源（按客户覆盖）？

5. **合规图策展边写入 API 的最小形态**（Task 7）：本计划做成 Python 函数级写入路径（`curate.*`）。是否在 P1 就要暴露为 HTTP/MCP 接口供早期联调，还是纯库函数等 P5 经 API Gateway 包？建议纯库函数（最小骨架），但请确认。

6. **RAGFlow 解析骨架的注入边界**（Task 1/5）：`parse_via_ragflow` 在 P1 是真连 RAGFlow server（需起栈）还是先留薄 client + 注入假 parse（解析硬化随真样本迭代）？建议默认薄 client、测试一律注入假 parse，真实解析硬化随脱敏真样在后续迭代——请确认这个边界。

7. **Task 1 在哪个节点跑**（Task 1）：开发节点 GTRDev-CY（192.168.66.41）拉 docker.io 反复超时，整栈起绿需一台公网通畅节点（那张 4090 / 一台专用机）。请指定执行节点；数据卷复用 `/data/industriax/`（postgres/mysql/valkey 卷已在该节点保留——若换节点，是否需要迁卷或重新初始化）。
