# Governance

> 治理唯一权威源。整合自旧 `task_governance_policy.md`、`coding_agent_protocol.md`、`daily_workflow.md`、`PROJECT_STATUS.md`。
> 项目级硬安全约束见根目录 [`CLAUDE.md`](../CLAUDE.md)。

## 1. 文档分层

```
docs/
  INDEX.md              一页项目入口
  ROADMAP.md            当前路线（唯一）
  GOVERNANCE.md         治理与约束（本文件）
  ADR/                  已批准的架构/治理决策
  era2_plan.md          Era 2 完整计划
  era2_codex_brief.md   Era 2 codex 任务书

  dashboard/             服务架构、pipeline、证据表（7 个）
  models/                D10–D19 模型模块、指标、语义（12 个）
  data/                  数据源、provider、基础设施（11 个）
  ai/                    AI context、manifest、研究预览（7 个）
  frontend/              UI 开发与架构（3 个）
  infra/                 运维、缓存、性能、runbook（4 个）
  archive/               历史 task 收尾、旧路线图、旧补丁
  knowledge/             知识库文档（ERA 2 D 阶段）
  research/              研究资料
```

任何新文档若不属于上述类别，先问自己是否能合入已有文档；不能再新建。

## 2. 隐私红线（永久）

**禁读 / 禁改 / 禁提交**：

- `.env*`
- `configs/external_llm.yaml`、`configs/external_search.yaml`
- `data/holdings/`
- `data/private/`、`data/private_notes/`
- `data/app_state/*.sqlite3`
- `data/market_history/*.sqlite3`
- `data/knowledge_base.sqlite`
- `data/macro_brief_archive.sqlite`
- `data/vector_store/`
- `data/cache/`
- `outputs/`
- 任何 raw provider payload、API key、本地日志

**C3 狭窄例外**：

- `data/knowledge_base.sqlite` 与 `data/knowledge_base/raw/` 默认仍禁止人工读取、打印、复制或提交。
- 仅 `src/app_backend/services/knowledge_base_service.py` 的显式 public method 可在运行时访问该路径。
- C3 不解锁 network、provider、AI、Tavily、DeepSeek、private notes、embedding、vector store、RAG、API、前端、scheduler、background task 或 automatic ingest。
- raw text 不得离开 local store，不得进入 API、模型、日志、错误消息、公开 return object 或 `documents` 表。
- C3 tests 必须使用 `tmp_path`，不得在真实 `data/` 下创建样例 DB/raw text。

**C4a 狭窄例外**：

- `data/economic_calendar.sqlite` 默认仍禁止人工读取、打印、复制或提交。
- 仅 `src/app_backend/services/economic_calendar_service.py` 的显式 public method 可在运行时访问该路径。
- C4a 不解锁 BLS/BEA/Federal Reserve 网络请求、网页抓取、Tavily、provider payload、API、前端、CLI、scheduler、automatic refresh、startup seed、page-load seed 或 background task。
- `data/economic_calendar_seed.json` 是 tracked synthetic fixture-only 数据，仅测试显式读取，production service 不得自动加载，也不得解释为真实经济日程。
- C4a 不包含 actual、forecast、previous、surprise、value、score、probability、trading signal、RAG、embedding、vector store 或 Agent。
- 其它隐私、网络、AI、持久化、D10-D19 / Stage 8 禁止项保持不变。

**C4b 狭窄例外**：

- `src/data_providers/official_calendar_real_transport.py` 可 import `httpx`，仅 GET 两个固定 BLS/BEA URL。
- 仅用户手动 `scripts/ingest_official_economic_calendar.py --live` 时允许 fetch。默认 planned，不 fetch，不写 DB。
- 写入需 `--live --write`。任一 source 失败整批取消。
- 无 API key、无 env、无 config、无 redirect、无 retry、无 credentials。
- raw response 仅驻留进程内，不落盘、不进 SQLite、不进 log、不进 CLI output、不进公开 result。
- 仅 BLS 和 BEA；不抓 Fed；不推断 FOMC statement 发布时间。
- 不新增 API、前端、scheduler、background、自动刷新、RAG、embedding、vector store 或 Agent。

**Phase F MacroBrief Agent + Holdings 例外**（见 `docs/ADR/ADR-0002-phase-f-holdings-external-context.md`）：

- 详细 holdings 仅可通过 `POST /api/agent/holdings-consent` 签发一次性本地 token 后，在 `POST /api/agent/run` 或 `POST /api/agent/run/stream` 且 `include_holdings=true` + `holdings_consent_token` 校验通过时使用。
- consent token 默认 10 分钟有效，只能被一个 agent session 消费一次；`holdings-consent` endpoint 不得返回 holdings 正文。
- 持仓快照必须由 server-side 注入的 snapshot provider 提供；默认 provider 未接线时必须 fail-closed。不得由前端 localStorage、请求正文或 debug endpoint 传入详细 holdings。
- 当前允许进入 MacroBrief prompt 的详细 holdings 范围仅限经 policy 过滤后的账户/证券/资产类别/数量/价格/市值/权重/偏离/组合风险摘要字段。其他所有 AI / RAG / search / preview / context 路径继续禁止接触 holdings / account / position 数据。
- account number、broker login、手机号、邮箱、证件、银行卡、API key、access token、cookie、密码、验证码、raw provider payload、订单簿、逐笔订单、成交/交易历史、充值提现、设备标识、本地路径、数据库路径、环境变量在任何路径上仍然禁止离开本地。
- 持仓注入必须 server-side 完成。raw holdings 不得进入 SSE 流、前端 console、前端 state、网络响应正文。
- 每个 agent session 必须在 trace 中仅记录 `holdings_included` 与 `holdings_snapshot_sha256`。raw snapshot 本身不记录。
- agent endpoint 仅 `POST /api/agent/holdings-consent`、`POST /api/agent/run` 与只读的 `GET /api/agent/trace/<session_id>`。`/api/chat`、`/api/ai/deepseek`、`/api/ai/external`、`/api/ai/tavily` 继续禁止。
- agent 仅复用已审计的 `deepseek_real_transport.py`（`deepseek-v4-pro` 加 `tools`/`tool_choice` 扩展）和 `tavily_real_transport.py`（经 `TavilySearchExecutionService` + `confirm_external_search=true`）。不新增 transport、不新增 httpx import。
- agent 仍走现有 `ExternalAIRuntimePolicy`（22 gates 派生自实状态，fail-closed）+ `SearchRuntimePolicy` + `guard_response`，不弱化 `external_model_called=True` 时的 blocking。
- agent 工具结果回灌 LLM 前必须 redact API key / 本地路径 / 内部 sha256 / raw provider payload / env 值；单工具结果 8KB 上限。
- agent budget：`max_steps=18`（或 two-phase 模式 `research_max_steps=12` + `writing_max_steps=2`），`max_search_calls=5`，`max_rag_calls=5`，`max_tokens_total=40000`。超限强制进入 writing-finalize 步骤并记录 trace。
- `data/macro_brief_archive.sqlite`（Phase G 规划）保持禁止人工读取 / 复制 / 提交；Phase F 不创建该 archive。
- 所有 D10-D19 / Stage 8 / AI Context Manifest / 其他既有 Era 2 禁止项不变。

**禁 import**（除明确允许的 transport 边界文件）：
- `httpx` / `requests` / `aiohttp`
- 直接读 `os.environ` / `os.getenv`

允许的 transport 边界例外（已显式 allowlist）：
- `src/app_backend/services/deepseek_real_transport.py`
- `src/app_backend/services/tavily_real_transport.py`
- `src/data_providers/official_calendar_real_transport.py`
- `src/data_providers/` 下已审计的 provider 文件

## 3. 持久输出边界

公开输出**可以**描述：证据、支持带、冲突、缺失输入、当前评审边界。

公开输出**不得**包含：
- 操作建议、买卖动词、加仓减仓措辞
- 概率数字（"70% 概率上涨"）、胜率、期望收益
- 个股推荐（"应买入 NVDA"）
- 择时信号（"现在是买入时机"）
- Event odds 概率模型

情景化收益区间允许输出（Era 2 已解禁），但必须满足：
- 必须含 base/bull/bear/systemic 4 档
- 必须含 boundary_notice，包含五个否定关键词：非概率、非操作、非个股推荐、非择时、非胜率
- 个股可点名 + 描述风险敷口；禁止操作动词

**Phase F MacroBrief 输出契约**（Era 2 F 阶段解禁，单 agent 多工具）：

- 10 节固定 schema，Pydantic 校验失败 → 自动重试 1 次 → 二次失败返回 partial brief + warning
- § 5 `module_table` 恰好 6 行：权益趋势 / 利率压力 / 真实利率压力 / 通胀能源 / 信用压力 / 地缘风险
- § 7 `forward_indicators` 恰好 5 条，每条含 `release_date` (ISO date)
- § 8 `scenarios` 恰好 4 键：`base` / `bullish` / `bearish` / `systemic`，每键含 `trigger_conditions` + `transmission_path`
- § 9 `source_list` 强制：brief 内每个数字必须能找到对应 `source_id`（URL 或 RAG doc_id）
- `confirmed_facts[*]` 必须含当前 run 的 `evidence_ids` 与 `claim_status`（`observed` / `reported` / `unavailable`）；`unavailable` 不得携带数值。
- MacroBrief 必须能表达 report / market / policy / macro / public-news cutoff；不同日期来源不得被静默拼接成同一“当前”状态。
- § 10 `boundary_notice` 必须文本中包含 5 关键词：非个股操作 / 非概率胜率 / 非收益预测 / 非动态择时 / 非黑盒最优化
- 工具结果与 LLM 输出之间的数字一致性必须保留（不得"调和"冲突，必须 flag）
- 每个 brief session 必须有可查 trace，trace 不含 raw prompt / raw response / raw holdings 金额 / API key / raw search query

## 4. 任务级 L1–L4 体系

每个 task 选最低适配的级别。

### L1 微修复

例：typo / 注释 / 格式化 / 私有 helper rename。
验证：targeted test + `git diff --check` + `git status --short -uall`。
不更新治理文档。

### L2 文档 / 审计 / 元数据

例：docs-only audit / closeout / INDEX 更新 / 解释性元数据字段。
验证：L1 + 相关 targeted test + `python scripts/dev_check_validator_boundaries.py`（如动边界文档）。
仅当当前路线 / 完成阶段 / 公开契约真实变化时更新治理文档。

### L3 边界生产改动

例：D10–D19 / Stage 8 模型代码、AI Context Manifest 资格、源闸 / 徽章、触发资格级联、公开输出 key、模型注册表、golden 契约。
验证：
- targeted module test
- 全量 pytest
- `python scripts/benchmark_dashboard_pipeline.py`
- `python scripts/audit_data_pipeline_coverage.py`
- D19/historical replay 改动加跑 `python scripts/run_historical_validation.py --format text`
- `python scripts/dev_check_validator_boundaries.py`
- `git diff --check` + `git status --short -uall`
更新治理文档（ROADMAP + closeout）。

### L4 产品面 / 外部 AI / 隐私敏感

例：新 API endpoint、前端 AI 面 / holdings 渲染、DeepSeek / Tavily 集成、持久 chat / memo / report 存储、holdings / account / position 上下文扩展、live provider fetch / write。

**必须先获用户明确批准**。

验证：
- 完整后端测试
- 前端 typecheck + build（如动前端）
- 安全 closeout 测试
- 路由面测试
- 隐私 + 禁止输出测试
- closeout 文档总结路由 / 持久化 / 禁止面扫描

## 5. Coding Agent 协议（Codex / Claude）

### 必做前置

```bash
git fetch origin
git status --short --untracked-files=all
git branch -vv
git log --oneline -12
```

报告结果再改文件。

### 立即停止条件

- 当前分支不是预期分支
- 工作树有未解释的脏文件 / 未跟踪文件
- 本地分支与 origin 不同步
- `git status` 出现 `.env` / SQLite / outputs / cache / holdings / private / API key / raw provider
- task 要求范围外的文件
- 必须验证命令失败且原因未知

### 金融/数学决策窗口

以下改动必须先征得用户同意：

- 新增金融标签 / 阈值 / 分数 / 加权 / 触发条件
- 修改 D10–D19 解释边界
- 把 proxy / search-derived / research-needed / stale / missing / insufficient-history 行升级为官方证据
- 引入估值 / 盈利 / 真实广度 / 情景 / 宏观体制逻辑
- 引入概率措辞 / 交易动词 / 方向确定性 / 期望收益措辞

### 最终报告格式

- 改动文件
- 摘要
- 跑的测试
- benchmark / audit 结果
- 隐私检查
- 剩余风险
- commit message 建议

未明确要求不 commit / push。

## 6. 命名规范

### 提交信息

人话优先，避免深嵌套阶段码。

好：`Speed up DB-backed test fixtures` / `Add Era 2 search runtime policy` / `Refine Scenario Stress Matrix explanations`。

避免：`DF-4d` / `S2b` / `Stage 9.3-B-2e` / `Refine D16`。

### 模型模块

任务标题 / 文档 / commit 用人话模块名，D ID 仅作 alias 在括号里。

| 人话名 | 旧 D ID |
|---|---|
| Financial Stress Composite | D10 |
| Pullback vs Systemic Risk Review | D11 |
| Historical Risk Normalization | D13 |
| Liquidity & Funding Stress | D14 |
| Macro Regime Review | D15 |
| Scenario Stress Matrix | D16 |
| Growth & Inflation Context | D17 |
| Valuation & Equity Structure Context | D18 |
| Historical Validation Replay | D19 |
| Portfolio Exposure Overlay | Stage 8 |

生产标识符（`module_key` / `model_key` / `metric_key` / 注册表 key / 公开输出 key）保持不变。

## 7. 治理文档更新触发

仅当下列至少一项成立时更新治理文档：

- 当前路线变化
- 阶段完成
- 公开契约变化（模型注册表 / golden 契约 / AI context schema / 禁止语策略）
- 外部或产品边界变化

权威源顺序：

1. [`INDEX.md`](INDEX.md) — 入口
2. [`ROADMAP.md`](ROADMAP.md) — 当前路线
3. [`GOVERNANCE.md`](GOVERNANCE.md) — 本文件
4. [`era2_plan.md`](era2_plan.md) — Era 2 详细计划
5. 模块技术文档 + closeout（archive/）

若冲突，上面优先。

## 8. 代码风格约束

- 不写学习注释 / 教学注释
- docstring 最多 1 行
- 不写"WHAT 已经在变量名里说了"的注释
- 仅在 WHY 非显然时写注释：隐藏约束 / 微妙不变量 / bug workaround / 反直觉行为
- 不为不会发生的场景加 error handling / fallback
- 不为假想未来需求做抽象
- 三行相似代码 > 早抽象

## 9. 测试命令

```bash
# 全量
cd src && python -m pytest ../tests/ -x -q

# 单模块
cd src && python -m pytest ../tests/dashboard/ -x -q
cd src && python -m pytest ../tests/contracts/ -x -q

# 前端 typecheck
cd app_frontend && npx tsc --noEmit
```

PYTHONPATH 必须含 `src/`。

## 10. 与 CLAUDE.md 的关系

`CLAUDE.md` 是项目级硬约束（被 Claude Code / Codex 自动加载）。本文件展开 task 级 / agent 级流程。

若 `CLAUDE.md` 与本文件冲突，`CLAUDE.md` 优先。
