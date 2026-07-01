# Roadmap

> 项目当前路线唯一权威源。
> 历史 `short_term_development_plan.md`、`ROADMAP_CURRENT.md`、`PROJECT_STATUS.md`、`current_project_state.md`、`modeling_roadmap.md` 已归档到 `docs/archive/`。
> 详细 Era 2 计划见 [`era2_plan.md`](era2_plan.md)，任务书见 [`era2_codex_brief.md`](era2_codex_brief.md)。

## 当前阶段

**Era 2：AI Agent 宏观研究工作台**（进行中）

目标：在现有 D10–D19 + Stage 8 数据底座之上，叠加联网搜索（Tavily）、知识库（RAG）、情景化收益区间引擎、单 Agent + 工具调用运行时，输出 10 节固定结构 `MacroBrief` 强类型研报。

## Era 0：数据基座（完成）

- D7–D9：drawdowns / curves / cross-asset / labor mini-pack
- D10–D19：金融压力、回撤分类、历史风险归一、流动性、宏观体制、情景压力矩阵、增长通胀、估值、历史回放
- Stage 8：Portfolio Exposure Overlay（sanitized）
- DF-1 至 DF-4c：数据源补全 + 元数据
- G1/G2/G3：本地刷新 + 官方源补全（FRED / BLS / BEA / Alpha Vantage / OFR）

## Era 1：前端美化（完成）

Tag：`era1-frontend-redesign-complete`。

## Era 2：AI Agent（当前）

### 已完成

- AI-1 / AI-1.5：本地确定性研究预览
- AI-2：单轮 DeepSeek V4 Pro 研究端点（7 节中文输出 + 全守门链）
- UI-0：前端信息架构审计
- Phase A：搜索与收益区间治理边界已获用户批准并正式生效
- Phase B1–B7：Tavily 搜索边界、read-only quote service、商品价与本地 API routes
  - B4 Tavily transport 已实现
  - B5 ETF/VIX/Treasury/TIPS quote contracts 已完成
  - B6 guarded Brent/WTI commodity quote service 已完成
  - B7 本地 API routes 已实现：`POST /api/search/tavily`（fail-closed，需 confirm）+ 只读 `GET /api/quote/{etf,treasury_curve,fx,commodity}`
  - native USDCNH 仍明确 unavailable，等待独立数据源批准
  - 无前端控制、无自动刷新、无后台/启动时搜索或报价调用
- Phase C1：search result classifier 已完成（deterministic 文档类型分类）
- Phase C2：official historical data ingest 已完成（manual CLI，默认 dry-run，`--live --write` 才写入）
- Phase C3：guarded local knowledge base store 已完成（本地 SQLite metadata + raw-text root；无 RAG / embedding / API）
- Phase C4a：offline economic calendar schema/service/fixture 已完成（synthetic fixture-only；无官方抓取 / API / 自动刷新）
- C4d：calendar read path boundary 已加固（所有 public method 均在 DB access 前校验完整 symlink ancestor chain）
- C4b：guarded BLS/BEA manual official acquisition 已完成（手动 CLI，默认 planned，`--live --write` 才写入；FOMC exact-time acquisition deferred）
- C4c：acquisition result boundary hardening 已完成（transport output 与 writer result 均视为不可信；malformed payload/result fail-closed；raw body/exception 不进入公开 summary）
- C4e：exception-total payload/writer hardening 已完成（payload guard 对所有 ordinary `Exception` fail-closed；strict built-in `str` 防止恶意 str subclass；writer result 用 exact-type 检查 + captured primitive counts 消除 TOCTOU；FOMC exact-time acquisition 仍 deferred）
- Phase C 在当前 BLS/BEA + FOMC-deferred scope 内已完成
- D0：RAG evidence governance contracts 已完成（纯内存、metadata-only admission contract；不读 raw text、不 chunk、不 embed、不建 vector store、不 retrieval、不接入 AI context；`historical_data` / `one_shot_news` / stale 文档为固定排除；`eligible` 仅是未来 RAG pipeline 的候选信号，不授权读取内容）
- Phase D：RAG 知识库已完成（D-1 EmbeddingService lazy-load；D-2 VectorStore Chroma；D-3 文档分块器；D-4 BM25Index 中英双语；D-5 RAGRetrievalService RRF 融合；D-6 ChunkTextStore + seed_knowledge_base 脚本；D-7 RAGContextBuilder 4000 字上限）
- Phase F remediation checkpoint：RAG doc_type filter 已贯穿 BM25/vector/fusion；agent `current_date` 改为服务端纽约日期；MacroBrief evidence_ids / claim_status / temporal cutoff schema 与 run evidence ledger foundation 已实现；runtime 已支持注入 `RunEvidenceLedger` 并在 finalize 时执行 claim-evidence gate、source_list 服务端重建、temporal envelope 写回与自动 tool-result ledger registration；runtime budget 已从工具名硬编码推进到 `ToolBudgetClass` 分类；holdings consent token 与 server-side injected snapshot foundation 已实现（默认 snapshot provider 仍 fail-closed）；trace 已具备日期分层、index、summary、hash chain 与 overflow graceful degradation；后端 `POST /api/agent/run/stream` SSE lifecycle foundation、cancel registry 与 runtime cancellation checks 已实现；前端已使用 `fetch + ReadableStream` 接入 POST-SSE，支持进度、取消、验证后 brief section 局部渲染与 E-Ink/Paper 风格。
- Phase F holdings stream checkpoint：`POST /api/agent/run/stream` 已复用一次性 holdings consent token 与 server-side snapshot injection，并验证 SSE response 不泄露详细 holdings 正文；默认 snapshot provider 仍保持 fail-closed。
- Phase F runtime timeout checkpoint：agent runtime 已加入 wall-clock / provider-call / tool-call timeout budget；默认 DeepSeek transport 复用 provider-call timeout；SSE bridge 已加入 bounded queue 与 sanitized queue-overflow error，避免慢客户端或事件洪峰造成无界内存增长；provider typed retry 已按 timeout / connection_failed / rate_limited / server_error 分类重试，并对 client_error / malformed_response / provider_refusal / missing_key fail-closed；provider call 已按剩余 token 与 phase cap 做 preflight；writing phase 已追加专用系统指令；mixed finalize call 已 fail-closed 且不执行同轮其他工具。
- Phase F RAG generation checkpoint：curated RAG ingest 已写入 `index_generation.json`（generation_id、source hash、chunk/document counts、embedding model/dim）；local RAG runtime cache 已纳入 generation_id；`scripts/validate_local_rag.py` 已将 generation metadata 与 embedding compatibility 纳入一致性 gate。
- Phase F quality checkpoint：已新增 `scripts/run_phase_f_controlled_agent_smoke.py` fixture-mode 受控 agent run（无外部 API、无 holdings、无 `.env`、无 `outputs`），并以 [`docs/infra/phase_f_release_checklist.md`](infra/phase_f_release_checklist.md) 作为 release gate；本轮 controlled live verification 已通过，Phase F 工程收口为 `implementation complete; controlled live verification passed; awaiting explicit user acceptance`，尚未 `user_accepted` / `production_ready`。
- Phase F hardening closeout：curated RAG ingest 写入前已 fail-closed 校验既有 index generation / chunk store / vector store compatibility；reported numeric claims 已要求绑定同一条 ledger atomic observation 的 value/unit/as_of。详细 holdings UI/API 仍保持 disabled/fail-closed，等待 Phase G+ 的真实 holdings snapshot provider 与披露策略。

### 进行中

按 [`era2_plan.md`](era2_plan.md) 9 个 Phase（A→I）执行：

| Phase | 主题 | 预计周 | L4 人审 |
|---|---|---|---|
| A | 治理与边界（解冻 Tavily + 收益区间） | 已完成 | ✅ A1 |
| B | Tavily + 实时报价 + 商品价 + 本地 API routes | 已完成（B1–B7） | — |
| C | 搜索分类持久化 + 经济日历 | 已完成（C1–C4e；FOMC exact-time deferred） | — |
| D | RAG 知识库 | 已完成（D0 governance contracts；D-1~D-7 embedding/vector/BM25/RRF/seed；需安装 sentence-transformers + chromadb + rank-bm25；用户需向 data/knowledge_base/input/ 放置文件） | — |
| E | 情景化收益区间引擎 | 已暂停于 framework（不阻塞 F） | ✅ E1 |
| F | Agent + 9 节前端 | implementation complete; controlled live verification passed; awaiting explicit user acceptance；尚未 user_accepted / production_ready | Phase F holdings exception 与 ADR-0001~0006 已批准 |
| G | 报告归档 + 历史对比 | 1 | — |
| H | 质量评估闭环 | 1 | — |
| I | 多 Agent 拆分 | 2 | 条件触发 |

总计约 12 周（不含 I）。

### Era 2 决策快照

- 联网搜索 = Tavily
- 组合 = SPY/QQQ/SHY/GLD 固定 4 ETF（5:2:2:1，RMB 计价）
- 收益区间 = 3 个月 / 人民币 / 不含股息
- 个股层 = 可点名 + 描述风险敷口；禁止操作动词
- Agent 起点 = 单 Agent + function calling
- MCP = 不做
- 移动端 = Era 3
- 自动化 / 推送 = Era 3

## Era 3：扩展（未来）

- 中国数据底座（A 股、港股、人民币宏观）
- 移动端 + 远程访问
- 自动化推送 / 定时 brief
- 多 Agent 协作（若 Era 2 Phase I 触发条件满足，提前到 Era 2 末）

## Phase G/H Backlog

- 接入真实 holdings snapshot provider 前，详细 holdings UI/API 保持 disabled/fail-closed；同时完成披露策略、用户确认文案与不外泄测试。
- 加强 holdings 自然语言数字泄露检测，覆盖模型把数量、市值、成本、盈亏改写成自然语言的输出路径。
- 增加 trace hash-chain integrity verifier，用于审计长期 trace 是否缺行、乱序或被篡改。
- 评估 generation-scoped Chroma collection 与 atomic active-generation pointer 迁移，降低 collection-per-generation 与缓存切换风险。
- 将市场日历升级为 exchange-holiday-grade calendar，避免交易日年龄与节假日边界误判。

## 持续保留的冻结边界

跨 Era 永久冻结，不会因任何阶段解锁：

- 自动交易
- 真实下单 / 真实资金移动
- Portfolio optimizer（黑盒最大化）
- 个股操作建议（买卖 / 加仓 / 减仓动词）
- 概率胜率措辞（"70% 概率上涨"）
- Event odds 概率模型
- Full-account DeepSeek context（账户余额 / 持仓行项 / 交易历史外送）
- 新闻情绪量化交易

## 已完成 Stage 历史索引

详见 `docs/archive/`：DF-0 至 DF-4c、HF-1/HF-2、P-M1 至 P-M4-D、S0 至 S3、Stage 9.0 至 9.3-B-2d、R1、Dashboard Service Refactor Phase E/F1/F2/F-G、UI-0、Data Foundation Gap Fill v1、G1、G2/G3。

## 命名约定

- 阶段编号（Era 2 / Phase A / TASK-A1）用于路线层。
- 模型模块用人话名（Financial Stress Composite / Macro Regime Review），D 编号保留为 traceability alias。
- 详细命名规范见 [`GOVERNANCE.md`](GOVERNANCE.md) §6。
