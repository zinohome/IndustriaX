# IndustriaX 平台总体设计（Brainstorming 收口版）

> 本文档是 PRD v1 + 架构 A 级在 Issue YAN-74 brainstorming 讨论后的收口产物，作为后续逐 Phase 实现计划（writing-plans）的输入。
> 配套源文档：`docs/IndustrialX_PRD_v1.md`、`docs/IndustrialX_Architecture_A.md`。
> 讨论记录：Issue YAN-74。

- 状态：设计已获用户张俊"认可"（2026-06-23）
- 下一步：逐 Phase 写实现计划

---

## 1. 产品定位（一句话）

IndustriaX 是一个**小模型驱动、可私有化部署、松散可组合的完整工业 AI 生产底座**：把杂乱的工业文档与流程，转化为可靠、可追溯、可审计的 agent 工作流；核心资产（工业文档解析硬化、合规/变更属性图、工业 Skill 库）跨客户复用（目标 60–75%），整套运行在客户防火墙内、数据不出厂、可断网。

楔子场景：ECN/PCN 变更管理。终局：选型/报价 ↔ 变更管理 ↔ 市场准入/合规 三边决策图。

## 2. 范围决策（brainstorming 关键澄清）

**IndustriaX 的开发范围 = 完整可组合平台，不是某个场景。** 架构 A 级图里的每个组件都要建到位、功能完整。

- **场景 = 集成测试镜头，不是开发边界。** ECN/PCN、BOM、FA、合规查询等被打包为 Skill 包 + 端到端集成测试套件，用来验证平台功能被完整覆盖，而非限定开发范围。
- 该决策纠正了 brainstorming 第 1 轮中"按单场景切薄片"的理解偏差；依据 PRD §0（"底座"）与 §2 非目标（"松散可组合、不做低代码平台"）。

### 2.1 已敲定的项目级决策（B/C/D）

| 项 | 决策 |
|---|---|
| **命名** | 统一 **IndustriaX**（无 l）。包名/镜像名/品牌一律用此名；两份源文档标题里的 `IndustrialX` 后续在仓库内统一更正。 |
| **硬件基线** | 本地验证 = 单张 **RTX 4090（Standard SKU）**先这么定。SKU/escalation 配置机制仍作为平台功能建入 Router（不砍），只是验证期默认跑 Standard 档。 |
| **测试语料** | 先用**合成样例**（ECN/PCN/BOM/FA/合规证书各造数份结构贴近真实的样本喂 RAGFlow）；解析硬化的真实反馈待有脱敏真样再补。 |

## 3. 已锁定的技术选型（来自 PRD/架构，不重开）

- **Harness（薄壳）**：Pydantic AI —— agent loop、类型安全 I/O、加载 Skill、调 MCP 工具，原生驱动本地 Qwen3。
- **粘合**：MCP —— Memory/RAG/Graph/Skill/外部工具全包成 MCP server，任一可替换。
- **推理**：Qwen3 本地（7B/14B 级，4090），弃权优先；escalation 三档 `local_large` / `external_api` / `human`。
- **RAG**：RAGFlow（解析）+ Postgres/pgvector（向量）+ Apache AGE（合规属性图）。
- **记忆**：Mem0（低可信、非权威、非人格化、非时序推理）。
- **编排**：Temporal（持久、可恢复、可审计；工程师 code-first 定义流程）。
- **License**：全栈 Apache/MIT，无 copyleft（绕开 Neo4j GPL → 用 AGE；Dify 已砍）。

## 4. 核心设计原则（贯穿所有 Phase）

1. **智能压进结构，不押注模型**：解析/多跳/编排尽量搬到专用模型/图遍历/确定性代码/离线批处理；推理时小模型只留最薄一层。
2. **松散可组合**：每个能力是独立服务、走 MCP、可单独替换、可按客户重组。
3. **知识与记忆分离**：权威知识（合规/规格/证书=ground truth）人工策展进 RAG/KB；agent 低可信信息进 Memory。信任级别不可混。
4. **借水管，建资产**：会复用的自建（解析硬化、合规图、Skill）；不会复用的全借。
5. **宁可弃权，不要猜**：抽取式 + 可追溯 + "查不到就转人工"。
6. **入库即打标**：`data_level`/`data_domain` 在入库时打，运行期只读标签，Router 不临时判断敏感度。

## 5. Phase 分解（自底向上按依赖排序，组件全覆盖）

**原则：按能力层切，不按场景切。** 每个 Phase 交付一层完整且带测试的平台能力并冻结其 MCP 契约；场景作为贯穿式集成测试套件，每跨一层把端到端覆盖推高一截。终态 = 架构 A 级图全部组件建成、可组合、可替换。

| Phase | 平台能力（建什么） | 关键交付物 | 依赖 |
|---|---|---|---|
| **P0 基础设施 + 契约骨架** | docker-compose 编排全栈（Postgres+pgvector+AGE / RAGFlow 自带栈 / Temporal / Qwen3+Embedding+Reranker 经 Ollama 或 vLLM / 各 MCP server 进程骨架）；私有化离线打包基线 | 一键起、健康检查全绿；**MCP 接口契约冻结**（三元字段 `data_level`/`data_domain`/`source` + 写类工具 `idempotency_key` 约定） | — |
| **P1 数据底座 + 入库打标管线** | RAGFlow 解析硬化骨架；Postgres 三库 schema 隔离；入库即打标管线（domain 确定性打 + level 三步 + 存疑往高 + 核心人工确认）；AGE vlabel/elabel + 索引策略落地（架构 §8） | 文档进得来、打标正确、合规图建得起、索引生效可验证 | P0 |
| **P2 MCP 能力层** | memory-mcp(Mem0) / doc-mcp(RAGFlow 检索) / graph-mcp(AGE 遍历含 `graph.impact`) / skill-tools-mcp；工具集完整、返回带元字段、写类带幂等键 | 四个 MCP 独立可调、契约一致、可单独替换 | P1 |
| **P3 Harness 内核** | Pydantic AI agent loop 驱动本地 Qwen3、类型安全 I/O；Router（难度判定 + escalation 三档 + 数据边界过滤 + 审计 + SKU 配置位）；Skill Loader（自建 SKILL.md 三级渐进披露 + Registry 扫描） | 弃权优先生效、escalation 决策与边界过滤正确、SKILL.md 加载器自建完成 | P2 |
| **P4 编排层** | Temporal workflow/worker；activity 调 Harness；at-least-once 幂等（副作用边界去重 + 幂等账本）；signal 人工评审/转人工节点 | 长流程持久、崩溃可恢复、全程审计 | P3 |
| **P5 接入面 + 治理面** | API Gateway（鉴权/租户角色/限流/流式/统一审计入口）；参考前端（出处展示 + 转人工）；Admin/运维 UI（配置 / 数据治理 / 审计合规台 / 运行监控 / 图策展界面 / skill 管理）；业务监控台 | API-first 对外契约成型；三面齐全；图策展界面让核心资产可人工录入校审 | P3/P4 |
| **横切·集成测试场景** | ECN/PCN 影响分析、BOM 解析、FA 根因、合规查询打包为 Skill 包 + 端到端集成测试套件 | 每 Phase 完成即用相应场景跑集成测试，证明功能完整覆盖 | 贯穿 P1→P5 |

要点：
1. **无组件被砍**——Memory/RAG/Graph/推理/Skill/编排/Router/Gateway/Admin UI/图策展全部在计划内，分期只是依赖排序，不是范围裁剪。
2. **场景 = 测试不是范围**：场景随平台层数增加而扩大端到端覆盖；Skill 库本身是要做厚的可复用资产（PRD §6.6）。
3. **单 4090 现实**：全栈不会在一张卡上同时跑热（RAGFlow 栈 + Temporal + Postgres + Qwen3 14B + Embedding + Reranker 显存/内存吃紧），验证期按场景**串行**跑即可；并发压测留到 Plus SKU 硬件。

## 6. P0 契约冻结范围（已获认可）

P0 即把 **MCP 工具签名定稿**（入参 / 出参 / 副作用 / 三元元字段 / 幂等键），因为契约是后面所有 Phase 的接缝，晚定会全局返工。冻结对象（架构 §5）：

- `memory-mcp`：`memory.recall` / `memory.write`(写, 加 `idempotency_key`) / `memory.forget`(写)
- `doc-mcp`：`doc.search` / `doc.get`（只读）
- `graph-mcp`：`graph.traverse` / `graph.neighbors` / `graph.impact`（只读）
- `skill-tools-mcp`：`bom.parse` / `ecn.compare` / `fa.analyze` …（按 skill 扩展；写类加幂等键）

约束：所有检索类工具返回项**必带** `data_level`、`data_domain`、`source`（来源文档+版本+章节）；所有有副作用的工具签名加 `idempotency_key`，只读工具不加。

## 7. 横切关注点（贯穿全平台）

| 关注点 | 方案 |
|---|---|
| 可观测性 | Pydantic AI 内置 OTel + Temporal 内置可观测；统一接客户内网采集端（可选 Grafana） |
| 审计 | escalation、外发、工具副作用调用全量审计日志（合规证据 + ops） |
| RBAC | 接入层鉴权；数据分级标签驱动访问控制 |
| 离线 | 唯一出网口 `external_api`，受数据边界过滤管控；其余全闭环 |
| 多客户隔离 | 单客户单部署；同实例内 Mem0 按 agent/session 隔离 |
| 数据分类 | 工信部三级（一般/重要/核心）；核心/重要禁外发，一般脱敏可外发；入库打标、外发留审计、级别客户可配置；重点企业默认关 external_api |

## 8. 已知风险与待 B 级落实项

**关键路径风险（排 Phase 时已计入）：**
- **AGE 索引调优**（架构 §8）：图层唯一会真出问题的点，P1 当正事做（入口属性索引、边表索引、热路径物化、深度封顶、走索引 Cypher 写法规范）。AGE 不能 Citus 分片、大版本升级需 dump/load —— 进运维手册。
- **SKILL.md 加载器**：Pydantic AI 不原生支持，P3 自建（三级渐进披露 + Registry 扫描 + 版本化 + 按客户子集）。
- **小模型真实上限**：无预结构化长链多跳 / 合规判断 / 长篇合成做不好；router 升级口触发边界与成本在集成测试阶段量化。
- **Temporal at-least-once 幂等**：副作用边界去重 + 幂等键确定性派生自 `workflow_id + activity_id`，P4 落实。

**仍待 B 级落实（实现细节，非架构决策）：**
- 幂等账本表 schema 与外部动作去重粒度。
- 规则升级器具体标识匹配规则（正则/词典/NER）。
- 脱敏占位符映射的存储与生命周期。
- 意图分类器的 skill 路由阈值与多命中排序。

## 9. 成功标准（平台级，对齐 PRD §9）

- **私有化可跑**：客户内网、断网条件下跑通完整工业工作流（ECN/PCN 首发）。
- **小模型够用**：本地 Qwen3 在结构化/模板化任务上达工业可接受准确率，硬 case 走升级口 < 一定比例。
- **可追溯**：合规相关答案 100% 可回溯到来源文档+版本+章节。
- **复用率**：第二个客户落地核心资产复用 ≥ 60%，差异主要在组合。
- **不猜**：无来源支撑时正确弃权/转人工，而非编造。

---

*Brainstorming 收口版 · 下一步：逐 Phase 写实现计划（writing-plans），P0 优先。*
