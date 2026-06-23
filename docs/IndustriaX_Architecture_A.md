# IndustriaX 系统架构设计说明书(A 级)

> 配套 PRD v1。本文档把 PRD §5 框图落成系统架构级蓝图:进程拓扑、组件职责、MCP 接口契约、端到端数据流、Temporal 边界、AGE 索引策略、router 与数据边界过滤。**不含代码**——代码骨架属 B 级,在本文档对齐后按模块单独出。

---

## 1. 范围与读者

- **读者:** 内部工程团队,进开发前对齐用。
- **范围:** 系统架构级——组件、接口、数据流、部署拓扑。
- **不含:** 具体实现、代码、配置文件、详细 schema 字段。

## 2. 约束回顾(决定拓扑的硬前提)

1. **私有化 / 可离线:** 整套在客户内网跑,默认可断网;镜像、模型权重、依赖全部随包交付,运行期不拉外网。
2. **单机 GPU 基线:** RTX 4090 24GB 单机起步——这直接约束模型层怎么排布(见 §3.3)。
3. **MCP 粘合:** 能力间走 MCP,任何一块可替换。
4. **入库即打标:** 数据分类(`data_level` / `data_domain`)在入库时完成,运行期只读标签,不临时判断(PRD §6.8)。
5. **知识/记忆分离:** 权威知识(策展、可追溯)与 agent 记忆(低可信)物理可共库,语义必须分隔。

---

## 3. 进程拓扑与部署

### 3.1 四层 tier

```
┌─────────────────────────────────────────────────────────────────────┐
│  Presentation / Access Tier                                          │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │ API Gateway (鉴权·租户/角色·限流·流式·统一审计入口)            │   │
│  └──────────────────────────────────────────────────────────────┘   │
│  ┌─────────────┐  ┌──────────────────┐  ┌────────────────────────┐   │
│  │ 参考前端(薄)│  │ Admin / 运维 UI   │  │ 业务监控台(Temporal)   │   │
│  │ 对话/任务   │  │ 配置·数据治理·   │  │ 流程视图               │   │
│  │ +出处+转人工│  │ 审计·监控·图策展  │  │                        │   │
│  └─────────────┘  └──────────────────┘  └────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────┘
            │ 全部经 API Gateway,不直连内核
            ▼
┌─────────────────────────────────────────────────────────────────────┐
│  Orchestration Tier                                                   │
│  ┌────────────────┐   ┌────────────────┐                              │
│  │ Temporal Server │   │ Temporal UI    │  (持久 · 可恢复 · 审计)       │
│  └────────────────┘   └────────────────┘                              │
└─────────────────────────────────────────────────────────────────────┘
            ▲ 调度 activity                      ▲ 业务监控台数据源
            │
┌─────────────────────────────────────────────────────────────────────┐
│  Application Tier (无状态,可多实例)                                    │
│  ┌──────────────────┐  ┌──────────────┐  ┌────────────────────────┐   │
│  │ Harness          │  │ Temporal     │  │ MCP Servers            │   │
│  │ (Pydantic AI)    │  │ Workers      │  │ memory / doc / graph / │   │
│  │ agent loop       │  │ 跑 workflow   │  │ skill-tools            │   │
│  │ + Router         │  │ + activity    │  │                        │   │
│  │ + Skill Loader   │  └──────────────┘  └────────────────────────┘   │
│  └──────────────────┘                                                 │
└─────────────────────────────────────────────────────────────────────┘
            │ MCP / 内部调用              │ 模型调用(OpenAI 兼容)
            ▼                            ▼
┌──────────────────────────────┐  ┌──────────────────────────────────┐
│  Data Tier (有状态)           │  │  Model Tier (GPU)                 │
│  ┌─────────────────────────┐ │  │  ┌────────────────────────────┐  │
│  │ Postgres                │ │  │  │ Qwen3 LLM (Ollama/vLLM)    │  │
│  │  ├ pgvector (向量)       │ │  │  │ Qwen3-Embedding            │  │
│  │  ├ Apache AGE (合规图)   │ │  │  │ Qwen3-Reranker             │  │
│  │  └ Mem0 backend         │ │  │  └────────────────────────────┘  │
│  └─────────────────────────┘ │  │  (escalation: local_large 见 3.3)│
│  ┌─────────────────────────┐ │  └──────────────────────────────────┘
│  │ RAGFlow 内部栈           │ │
│  │ MySQL/Redis/MinIO/ES    │ │
│  └─────────────────────────┘ │
│  ┌─────────────────────────┐ │
│  │ Skill Registry (SKILL.md │ │
│  │ 文件目录)                │ │
│  └─────────────────────────┘ │
└──────────────────────────────┘
```

### 3.2 拆分原则

| 拆分决策 | 说明 |
|---|---|
| Model Tier 独立 | GPU 资源独占,模型服务化(OpenAI 兼容口),与应用层解耦,可单独扩 GPU |
| Data Tier 独立 | 有状态,生命周期独立于应用;Postgres 一个实例承载向量+图+Mem0(分 database/schema 隔离) |
| RAGFlow 自带栈隔离 | RAGFlow 依赖 MySQL/Redis/MinIO/ES,作为独立服务簇,不与主 Postgres 混 |
| Temporal Server 独立 | 自带持久化(独立 Postgres database),与业务库分开 |
| App Tier 无状态 | Harness / Workers / MCP servers 无状态,可水平多实例;状态全在 Data/Orchestration tier |
| MCP servers 进程独立 | 每个 MCP server 独立进程,便于单独替换(贴"任何一块可换") |
| Presentation Tier 经 Gateway 收口 | 三个界面全部走 API Gateway,不直连 Harness/DB;Gateway 是唯一边界与唯一审计入口 |

### 3.3 单机 GPU 预算与 escalation 的拓扑后果(关键)

4090 24GB 上常驻:Qwen3-14B(Q4,~9GB)+ Embedding + Reranker(~4-6GB),余量紧但可行。

**但 `local_large` escalation 在单机上不是免费的:** 更大的本地模型(如 Qwen3-32B)放不进剩余显存。三个选项,部署时按客户拍:

| 方案 | 代价 |
|---|---|
| 加第二块 GPU / 更大显存 | 硬件成本上升 |
| 模型热切换(卸小载大) | escalation 有秒级延迟 + 影响并发 |
| 不部署 local_large,只 external_api / human | 受 §6.8 数据边界限制 |

**这条要写进每个客户的交付清单——escalation_target 的选择和硬件配置是绑定的,不是软件开关随便切。**

**最佳实践:把 escalation 能力做成硬件 SKU,客户选 SKU 决定能力(产品化部署,不给每客户定制工程):**

| SKU | 硬件 | local_large | 默认 escalation |
|---|---|---|---|
| Standard | 单 4090 | 无 | human / external_api |
| Plus | 双 GPU(或单卡 48GB+) | 可用,常驻无切换 | local_large / human / external_api |
| Sealed-Plus | 双 GPU,密封 | 可用 | 仅 local_large / human(external 全关) |

默认建议不部署 local_large(Standard)——工业硬 case 转人工比内网常驻大模型更省更安全。真要 local_large,优先双 GPU 常驻,**避免热切换**(切换期小模型下线、全流量卡顿,仅极低频 escalation 的小部署可接受)。

### 3.4 私有化 / 离线打包

- 全部组件 docker-compose 编排,单机一键起。
- 模型权重、容器镜像、Python/系统依赖随交付包内置;运行期零外网拉取。
- `external_api` 模式是唯一的出网口,且受 §9 数据边界过滤管控;其余全内网闭环。

---

## 4. 组件清单与职责

| 组件 | Tier | 职责 | 后端/依赖 | 可替换性 |
|---|---|---|---|---|
| API Gateway | Access | 鉴权、租户/角色、限流、流式回传、路由进 Harness/Temporal、统一审计入口 | — | 自建 |
| 参考前端 | Access | 薄:对话/任务、流式看推理、出处展示、转人工交接 | API Gateway | 自建(客户可替换) |
| Admin/运维 UI | Access | 配置、数据治理、审计合规台、运行监控、Skill/图策展 | API Gateway | 自建(必做) |
| 业务监控台 | Access | Temporal 流程业务视图(可后做) | Temporal | 自建 |
| Harness (Pydantic AI) | App | agent loop、类型安全 I/O、调 MCP、内嵌 Router 与 Skill Loader | Qwen3(经模型层) | 中(核心壳) |
| Router | App(在 Harness 内) | 难度判定、escalation 决策、数据边界过滤 | 客户配置 | 自建 |
| Skill Loader | App(在 Harness 内) | 读 SKILL.md 渐进加载、注册 skill 工具 | Skill Registry | 自建 |
| memory-mcp | App | 包 Mem0,暴露记忆读写工具 | Postgres(Mem0 backend) | 高 |
| doc-mcp | App | 包 RAGFlow 检索,暴露文档混合检索 | RAGFlow 栈 | 高 |
| graph-mcp | App | 包 AGE,暴露合规图遍历 | Postgres/AGE | 高(可换 Neo4j) |
| skill-tools-mcp | App | 暴露 skill 专属工具(BOM 解析、ECN 比对等) | 自建逻辑 | 自建 |
| Temporal Workers | App | 跑 workflow/activity,AI 步骤调 Harness | Temporal Server | 低 |
| Qwen3 模型服务 | Model | LLM 推理(OpenAI 兼容口) | GPU | 中 |
| Embedding/Reranker | Model | 向量化、重排 | GPU | 高 |
| Postgres | Data | 向量 + 合规图 + Mem0 后端 | — | 低(数据底座) |
| RAGFlow 栈 | Data | 文档解析与索引 | MySQL/Redis/MinIO/ES | 中 |
| Temporal Server | Orch | 持久编排引擎 | 独立 Postgres | 低 |
| Skill Registry | Data | SKILL.md 包文件目录 | 文件系统 | 自建内容 |

### 4.5 Presentation/Access 三面职责(产品范围)

**产品范围决策:API-first + 标准参考前端 + 必做 Admin UI。** 三面服务三类人,职责严格分离,全部经 API Gateway,不直连内核。

**API Gateway(唯一边界):** 鉴权、租户/角色、限流、流式回传(SSE/WebSocket)、路由、统一审计入口。**对外契约即一套 API,前端只是其消费者之一**——工业客户常要把能力嵌进自有 MES/PLM/工单系统,API-first 是硬需求。

**① 终端调用层(客户业务人员):**
- 一套对外 API(REST + 流式)+ 一个**薄参考前端**:发起请求、流式看 agent 推理、**显性渲染出处(可追溯是核心卖点,前端必须把 source 展示出来)**、human escalation 时的转人工交接。
- 纪律:前端不碰任何业务逻辑,逻辑全在后端;参考前端客户可替换。

**② Admin/运维 UI(交付团队 + 客户 IT)——必做,是私有化交付与反项目制的命门:**
- **配置管理:** escalation_target/SKU、数据分类策略(§6.8 客户化覆盖)、客户启用的 skill 子集(§11.6)、模型/检索参数。前面所有"客户可配置"全靠此 UI 落地。
- **数据治理:** 看入库打标结果、**人工确认核心数据**(§11.3)、复核分类。
- **审计合规台:** escalation/外发/工具副作用日志查询——既是 ops,也是客户应对数据安全监管的证据界面(规上/重点客户的采购加分项)。
- **运行监控:** 各 MCP/模型服务/Postgres/RAGFlow 健康、GPU 占用、弃权率/escalation 率/转人工率等质量指标。
- **Skill/知识管理:** 文档上传触发入库、skill 包版本管理。
- **⚠ 图策展界面(之前架构的隐藏缺口):** 合规属性图是人工策展的,**必须有界面让人录入/审校零件↔变更↔证书的边**。没有它,核心资产建不起来。这是 Admin UI 里最关键、之前完全没提的一块。

**③ 业务监控台(客户业务方):** Temporal 流程的业务语义视图(变更申请→评审→生效),先用 Temporal 自带 UI 套权限,后做定制(PRD §6.4)。

---

## 5. MCP 接口契约(系统级)

> 工具签名为架构级示意,精确字段进 B 级。所有检索类工具的返回项**必带** `data_level`、`data_domain`、`source`(来源文档+版本+章节)三个元字段——这是 router 过滤和可追溯的基础。

### 5.1 memory-mcp(包 Mem0)

| 工具 | 入参 | 出参 | 副作用 |
|---|---|---|---|
| `memory.recall` | agent_id, query, scope | 记忆条目[]（含元字段) | 无 |
| `memory.write` | agent_id, content, scope | ack | 写库(轻抽取) |
| `memory.forget` | agent_id, filter | ack | 删库 |

注:整合/去重/冲突消解走离线批处理,不在此同步接口内。

### 5.2 doc-mcp(包 RAGFlow)

| 工具 | 入参 | 出参 | 副作用 |
|---|---|---|---|
| `doc.search` | query, filters, top_k | 文档块[]（含元字段+出处) | 无 |
| `doc.get` | doc_id, version | 文档元数据+内容 | 无 |

### 5.3 graph-mcp(包 AGE)

| 工具 | 入参 | 出参 | 副作用 |
|---|---|---|---|
| `graph.traverse` | start_node, edge_pattern, max_hops | 路径/节点[]（含元字段) | 无 |
| `graph.neighbors` | node_id, edge_type | 邻接节点[] | 无 |
| `graph.impact` | change_id | 受影响零件/证书/规格[] | 无 |

注:`graph.impact` 是 ECN/PCN 核心查询的预封装;多跳由图遍历算好,小模型只读结果。

### 5.4 skill-tools-mcp(skill 专属工具)

| 工具 | 入参 | 出参 | 副作用 |
|---|---|---|---|
| `bom.parse` | doc_id | 结构化 BOM | 无 |
| `ecn.compare` | rev_a, rev_b | 差异项[] | 无 |
| `fa.analyze` | case_id | 根因候选[] | 无 |
| … | (按 skill 扩展) | | |

> SKILL.md 是**指令/playbook**(教 agent 怎么做),由 Skill Loader 加载进上下文;skill 的**动作**经此 MCP 暴露为工具。两者分离:同一个 skill = 一段 SKILL.md + 若干 MCP 工具。

---

## 6. 端到端数据流

### 6.1 请求生命周期

```
请求
 │
 ▼
[Harness] 意图分类(小模型)──► 选定场景/skill
 │
 ▼
[Skill Loader] 渐进加载对应 SKILL.md
 │
 ▼
[检索] 并行:
   doc-mcp.search   ─┐
   graph-mcp.impact ─┼─► 上下文 bundle(每项带 data_level/domain/source)
   memory-mcp.recall─┘
 │
 ▼
[推理] 小模型抽取式生成 + 套模板 + 带出处
 │
 ├─ 置信足够 ────────────────────────► 输出(带出处)──► 审计日志
 │
 └─ 命中硬 case ──► [Router] escalation 决策(见 §9)
                       │
                       ├─ local_large ─► 内网大模型 ─► 输出
                       ├─ external_api ─► 数据边界过滤 ─► 脱敏 ─► 外部API ─► 输出
                       └─ human ────────► 转人工
```

### 6.2 两条打标路径(分清)

| 路径 | 发生时机 | 谁打标 | 用途 |
|---|---|---|---|
| **入库打标** | 文档解析 / 图节点策展 / 记忆写入时 | 入库管线(可配置分类策略) | 给每条数据落 `data_level`+`data_domain` |
| **运行时强制** | escalation 决策时 | Router | 读上下文 bundle 各项标签,算 `max(data_level)` 决定能否外发 |

**关键:Router 不判断数据敏感度,只读入库时打好的标签。** 分类逻辑集中在入库管线一处,避免运行期重复判断与漏判。

---

## 7. Temporal 与 Agent Loop 的边界

**外层(Temporal workflow):** 业务流程状态机——ECN/PCN 的"提交→评审→生效",持久、可恢复、全程审计。流程由工程师 code-first 定义。

**内层(Agent loop):** 单个需要 AI 的步骤。Temporal **activity** 调用 Harness 跑 agent loop(检索+推理+工具)。

```
Temporal Workflow: ECN 变更管理
  ├─ Activity: 解析变更单 ───► Harness(agent loop)──► doc-mcp / skill-tools-mcp
  ├─ Activity: 影响分析 ─────► Harness ──► graph-mcp.impact
  ├─ Activity: 合规校验 ─────► Harness ──► doc-mcp + 推理(可能 escalation)
  ├─ (人工评审节点:Temporal 等待外部信号)
  └─ Activity: 生成变更通知 ─► Harness
```

**边界纪律:**
- Temporal 保"流程崩了能续";Agent 保"这一步推理对"。职责不混。
- Temporal activity 是 **at-least-once** 语义——包 AI 调用的 activity 必须容忍重试:有副作用的 MCP 工具调用要么幂等,要么由 activity 层做去重。这条是详细设计必须落实的点。
- 人工节点(评审/转人工)用 Temporal 的 signal 机制等待,不阻塞 worker。

---

## 8. AGE 索引策略

AGE 默认不建索引,且带/不带 WHERE 走不同索引路径——这是图层唯一会真出问题的点,架构阶段先定策略:

1. **入口属性必建索引:** 所有作为遍历起点的 ID(`part_id`、`cert_id`、`ecn_id`、`spec_id`)在对应 vlabel 上建属性索引。
2. **边表索引:** 高频遍历的 elabel(如 `affects`、`certifies`、`supersedes`)按端点建索引。
3. **热路径物化:** `graph.impact` 这类高频多跳查询,若性能不足,预计算成物化视图定期刷新——反正小模型只读结果,预算好正合适。
4. **深度封顶:** 遍历 max_hops 设上限(合规图业务上 2–4 跳够),防止退化成全图扫描。
5. **查询写法规范:** 团队统一用走索引的 Cypher 写法(属性匹配 vs WHERE 的差异写进开发规范)。

**边界提醒:** AGE 表不能用 Citus 分片、大版本升级要单独 dump/load——这两条进运维手册,不影响架构,但部署/升级流程要覆盖。

---

## 9. Router 与数据边界过滤(架构级)

Router 是 Harness 内的组件,位于模型调用前。

**输入:** 难度信号(意图分类器/置信度)、上下文 bundle(带标签)、客户配置(`escalation_target` + 分类策略)。

**决策流:**

```
小模型置信足够? ──是──► 本地答,结束
        │否
        ▼
读 escalation_target:
  human       ──► 转人工
  local_large ──► 内网大模型
  external_api──► 数据边界过滤:
                    context_max_level = max(各上下文项 data_level)
                    if context_max_level ≥ 重要 ──► 拒绝外发
                                                   └─► 回退 local_large / human(按配置)
                    else ──► 脱敏 ──► 外部 API
所有 escalation 写审计日志
```

**子组件:数据边界过滤器**
- 输入:上下文 bundle(已带 data_level)、客户分类策略。
- 逻辑:取 `max(data_level)` → 查策略表 → 放行/拒绝/脱敏。
- 不重新分类,只读标签 + 查策略(策略默认值见 PRD §6.8 表,客户可配置)。

**重点企业默认:** 名录内客户交付时 `escalation_target` 默认 `local_large`/`human`,external_api 整体关闭(PRD §6.8)。

---

## 10. 横切关注点

| 关注点 | 方案 |
|---|---|
| 可观测性 | Pydantic AI 内置 OTel + Temporal 内置可观测;统一接客户内网的采集端(可选 Grafana) |
| 审计 | escalation、外发、工具副作用调用全量审计日志(合规证据 + ops) |
| RBAC | 接入层鉴权;数据分级标签驱动访问控制(高级别数据限角色) |
| 离线 | 唯一出网口是 external_api,受 §9 管控;其余全闭环 |
| 多客户隔离 | 单客户单部署(私有化),实例间天然隔离;同实例内 Mem0 按 agent/session 隔离 |

---

## 11. 关键设计决策(已定)

> 原开放问题已收口为下列决策,作为 B 级详细设计的输入。

**11.1 Postgres 拆分**
单机阶段一个实例 + schema 隔离 + 按角色调参(PgBouncer 连接池、按 workload 设 `work_mem`/`statement_timeout`),先不拆——单机拆库无益,仍抢同机 RAM/IO。监控缓存驱逐:**当向量 HNSW 索引逼近 shared_buffers、且观测到驱逐拖慢图查询时,第一个拆出向量库**,图+Mem0 继续同居,通常与上多机同时发生。Temporal 库始终独立(高频写状态,不与业务查询争)。

**11.2 AI activity 幂等**
在副作用边界去重,不在 AI 调用处。activity 拆两段:(a) 读+推理(可安全重试)、(b) 带幂等键的写。幂等键确定性派生自 `workflow_id + activity_id`(与 attempt 无关)。DB 写用 `ON CONFLICT DO NOTHING`,外部动作用幂等账本表 check-before-act。**所有有副作用的 MCP 工具签名加 `idempotency_key` 入参**(`memory.write` 及 skill 写类工具);只读工具不加。可选:幂等键缓存 LLM 结果省重试成本。

**11.3 入库分类管线**
domain 按来源/路径/文档类型确定性打(不用 LLM)。level 三步:domain→默认级别映射 → 规则升级器(出现客户标识/零件号/证书号/个人信息则升级)→ **存疑一律往高判**(风险不对称,判低=泄露)。核心数据必须人工确认并对齐客户已备案目录。分类策略从客户已备案目录播种,客户拥有分类、产品提供机制。版本变更重新评级。**LLM 最多建议,不拍板高敏感级。**

**11.4 local_large 部署形态**
做成硬件 SKU(Standard/Plus/Sealed-Plus,见 §3.3),客户选 SKU 决定 escalation 能力。默认不部署 local_large(转人工兜底更省更安全);真要上优先双 GPU 常驻,避免热切换。escalation_target 绑定 SKU,模糊配置变商技捆绑。

**11.5 数据边界脱敏**
脱敏是"一般数据"档的纵深防御附加层,**不是放行重要/核心数据的手段**——真正控制是级别拦截,安全默认是不发。一般数据外发时剥直接标识(客户名/零件号/证书号/人名/厂区),换请求内一致占位符,映射表本地持有、绝不外发,回来还原。每次外发审计前后差异(或哈希+类别)。明确纪律:不允许靠脱敏把重要数据推出去。

**11.6 Skill Loader / SKILL.md 加载**
三级渐进披露:① 常驻所有 skill 元数据(名+一句描述)② 触发时载选中 SKILL.md 正文 ③ 按需载脚本/资源。靠意图分类(小模型)选 skill,不全量塞上下文。硬上下文预算 + 单 skill 优先(工业任务通常单场景)。Registry 为文件目录(一 skill 一文件夹),启动扫描建元数据索引。**skill 版本化 + 按客户给子集——这是 60–75% 复用的落点。** SKILL.md 显式声明依赖的 MCP 工具,loader 确保可用。

### 仍待 B 级落实(实现细节,非架构决策)
- 幂等账本表 schema 与外部动作的去重粒度。
- 规则升级器的具体标识匹配规则(正则/词典/NER)。
- 脱敏占位符映射的存储与生命周期。
- 意图分类器的 skill 路由阈值与多命中排序。

---

*A 级 · 系统架构蓝图 · 下一步按模块出 B 级(Router 过滤逻辑、MCP 工具定义、入库打标管线、Skill Loader 优先)*
