# Era 2 AI Workbench Development Plan v1

本文档为 Era 2（AI / Agent / MCP）的完整开发计划，基于以下需求决策：

| 维度 | 选择 |
|---|---|
| 联网搜索提供方 | **Tavily 优先**（单一 provider，adapter 层预留 fallback 扩展位） |
| 收益预测范围 | **情景化收益区间**（base / bear / bull，不出概率，不出操作建议） |
| Agent 起点 | **单 Agent + 工具调用**（DeepSeek function calling，多工具自主路由） |
| 搜索结果处理 | **混合策略**：新闻/会议/政策类一次性进 prompt；专业研报、指数/PPI/CPI 等历史金融数据入库 + RAG |

## 0. 必须先做的政策修订

当前 `docs/short_term_development_plan.md` 与 `CLAUDE.md` 明确冻结以下项，本计划要求**正式解冻并修订**：

- 解冻 Tavily/搜索（受新的 search runtime policy 与 22-flag 守门链等价物约束）
- 解冻 return estimates（限定为"情景化区间 + 非概率 + 非操作建议"，写入新的 boundary clause）
- 解冻 Chat UI 多轮（受 agent budget + trace 约束）

**仍保持冻结**：auto trading、portfolio optimizer、brokerage sync、event odds 概率模型、full-account DeepSeek context、holdings line items 上行外部模型。

修订需在 Phase A1 完成，后续阶段才能合入实现代码。

---

## 1. 阶段总览

```
Phase A  治理与边界 (docs + schema)         →  ~1 周
Phase B  Tavily 联网搜索接入                 →  ~1.5 周
Phase C  搜索数据分类与持久化                →  ~1 周
Phase D  RAG 知识库层                        →  ~2 周
Phase E  情景化收益区间引擎                  →  ~1.5 周
Phase F  单 Agent + Tool Calling 运行时       →  ~2 周
Phase G  端到端闭环、性能、文档              →  ~1 周
```

总计 ~10 周开发周期（单人 / Codex 辅助）。每个 Phase 内部任务可串行执行。

---

## 2. Phase A —— 治理与边界修订

### A1. 解冻政策文档（L4 任务，需明确批准记录）

**目标**：在 `docs/short_term_development_plan.md` 与 `CLAUDE.md` 中正式修订冻结条款。

**Deliverables**：
- `docs/era2_unfreeze_policy.md`（新）—— 列出本次解冻的范围、保留冻结的范围、引用本计划作为依据。
- `docs/short_term_development_plan.md` 的 "Frozen" 与 "Not Now" 段落更新，明确划出"已解冻 / 仍冻结"。
- `CLAUDE.md` 的 Security Constraints 段落更新，把 `/api/search`、`/api/ai/external`、`/api/ai/tavily` 等条目改为"受 SearchRuntimePolicy 约束允许"，但仍禁止 `/api/chat` 走 raw 用户输入。
- `docs/persistent_boundaries_v2.md`（新）—— 写出"情景化收益区间"的精确边界：必须含 base/bear/bull 三档、必须给出敏感度驱动因子、不得给出操作建议、不得给出概率/期望值数字、不得给出胜率。

### A2. SearchRuntimePolicy schema

**目标**：为联网搜索新增与 ExternalAIRuntimePolicy 等价的运行时策略守门链。

**新增模块**：
- `src/app_backend/schemas/search_external.py` —— `SearchRuntimePolicy`、`SearchRequest`、`SearchResponse`、`SearchGuardResult`。
- `src/app_backend/services/search_runtime_policy.py` —— `guard_search_runtime_policy(policy)`，复制 `ai_external_runtime_policy.py` 的 fail-closed 模式。

**Required-True 守门位**（≥8 个）：
- `search_enabled`、`provider_network_enabled`、`user_controlled_switch_enabled`、`single_request_user_approved`、`query_sanitizer_passed`、`domain_allowlist_enforced`、`response_guard_required`、`human_review_optional`（这一位为 True 表示走人审旁路时仍允许）。

**Required-False 守门位**（≥6 个）：
- `save_raw_query`、`save_raw_html`、`allow_holdings_in_query`、`allow_position_in_query`、`allow_account_in_query`、`allow_local_path_in_query`。

### A3. 配置框架

**新增配置文件**（git-ignored）：
- `configs/external_search.yaml` —— Tavily endpoint、超时、域名白名单、域名黑名单、每次调用 max_results、每日预算上限。

**Loader**：`src/app_backend/services/search_config_loader.py`，不读 `os.environ`，只读受控 yaml；API key 必须通过 `.env` 注入但仅在 transport 边界处单点读取（与 deepseek 相同模式）。

### A4. Tests

- `tests/ai/test_search_runtime_policy.py` —— 22+ fail-closed 用例。
- `tests/ai/test_search_config_loader.py` —— 含缺省/缺字段/超额预算用例。

---

## 3. Phase B —— Tavily 联网搜索接入

### B1. Tavily provider contract

**新增**：
- `src/app_backend/services/tavily_provider_contract.py` —— `build_tavily_provider_payload(SearchRequest) -> TavilyProviderPayload`，纯函数，无网络。
- `src/app_backend/services/tavily_transport_contract.py` —— `TavilyTransport` 抽象、`TavilyTransportError`、`build_transport_request_from_provider_payload`。

参照 `deepseek_provider_contract.py` 与 `deepseek_transport_contract.py` 的分层。

### B2. Tavily real transport

**新增**：`src/app_backend/services/tavily_real_transport.py`
- 仅在此文件 import `httpx`。
- 调用前调 `guard_search_runtime_policy`，未通过抛 `BlockedAdapterError`。
- 强制 `timeout=30s`、`follow_redirects=False`、域名白名单二次校验返回结果中的 url。

### B3. Search adapter & guard chain

**新增**：`src/app_backend/services/tavily_adapter.py`，提供 `TavilyAdapter`、`FakeTavilyAdapter`。

Guard 链：
1. 入参 `query_sanitizer.sanitize_query(query)` —— 拒绝包含金额、ticker:weight、账号、本地路径、个人姓名等模式。
2. transport 前 `guard_search_runtime_policy`。
3. 出参 `guard_search_response(result)` —— 去掉超长 raw_content、不在白名单的 url、含敏感字段的 snippet。

### B4. API endpoint

**新增路由**（`src/app_backend/main.py`）：
- `POST /api/search/tavily` —— 接收 `SearchRequest`，返回 `SearchResponse`。默认 `enabled=False`，需前端显式开关。

### B5. Tests

- `tests/ai/test_tavily_provider_contract.py`
- `tests/ai/test_tavily_adapter_mocked_transport.py`（不命中网络）
- `tests/ai/test_tavily_real_transport.py`（mock httpx）
- `tests/ai/test_query_sanitizer.py`（≥30 个敏感模式用例）

---

## 4. Phase C —— 搜索数据分类与持久化

### C1. 搜索结果分类器

**新增**：`src/app_backend/services/search_result_classifier.py`

输入：单条搜索结果（url、title、snippet、published_date）。
输出：`ResultCategory` ∈ {`one_shot_news`, `policy_doc`, `research_report`, `historical_data`, `discard`}。

分类规则：
- 域名为 fred.stlouisfed.org / bls.gov / bea.gov / treasury.gov → `historical_data`，触发 C2 ingest 路径。
- 域名为 federalreserve.gov / imf.org / worldbank.org 且含 "speech|minutes|statement" → `policy_doc` 入 RAG。
- pdf 文件 + 域名为知名研究机构 → `research_report` 入 RAG。
- 一般新闻媒体（reuters/bloomberg/ft 等） → `one_shot_news`，仅当轮 prompt 使用。

### C2. 历史金融数据 ingest 路径

复用现有 `market_history` SQLite store + `data_providers/` 模块。

- 新增 `src/data_providers/from_search_url_provider.py`（可选）—— 若搜索命中 FRED/BLS 的可识别 series id，转发到现有 FRED/BLS provider 路径，**不直接抓网页**。
- 拒绝任何非官方 url 的"历史数据"写入。

### C3. 研报/政策文档库

**新增 SQLite 表**（`data/knowledge_base.sqlite`，git-ignored）：
- `documents(id, url, title, source_domain, doc_type, fetched_at, content_sha256, raw_text_path)`
- `document_chunks(id, doc_id, chunk_index, text, embedding_vector_id)`

**新增服务**：`src/app_backend/services/knowledge_base_service.py`，提供 ingest / lookup / mark_stale 方法。

### C4. Tests

- `tests/ai/test_search_result_classifier.py`（含 ≥40 url 用例）
- `tests/ai/test_knowledge_base_service.py`

---

## 5. Phase D —— RAG 知识库层

### D1. Chunk + Embedding pipeline

**新增**：`src/llm/embedding_service.py`
- 默认模型：`BAAI/bge-small-zh-v1.5`（本地推理，sentence-transformers）。
- chunk 策略：500 token / 100 overlap，按段落优先切。
- 嵌入只在本地，不发外部。

### D2. 向量存储

选型：**Chroma**（持久化、Python 友好、零运维）。

**新增**：
- `data/vector_store/`（git-ignored）—— Chroma 持久目录。
- `src/llm/vector_store.py` —— `add_documents`、`query(text, k, filter)`。

### D3. 混合检索

**新增**：`src/app_backend/services/rag_retrieval_service.py`
- BM25（rank_bm25 库）+ 向量召回，RRF 融合。
- 输出 `RetrievedChunk(text, source_url, score, doc_type, published_date)`。

### D4. RAG Context Builder

**新增**：`src/app_backend/services/rag_context_builder.py`
- 与现有 `ai_context_service.AIContextManifest` 对齐：把 RAG 召回的 chunk 包装为新的 `manifest.rag_evidence` 段。
- 受 manifest eligibility 守门（不得把 holdings/account 字段送入 query 文本）。

### D5. Tests

- `tests/ai/test_embedding_service.py`
- `tests/ai/test_rag_retrieval_service.py`
- `tests/ai/test_rag_context_builder.py`（含 manifest 兼容契约）

---

## 6. Phase E —— 情景化收益区间引擎

### E1. Scenario→Return 映射设计文档

**新增**：`docs/scenario_return_band_design.md`

核心方法（确定性，不黑盒）：
1. 取 D16 Scenario Stress Matrix 当前的 base/bear/bull 情景。
2. 每个情景对应一组宏观因子冲击（已在 D16 中定义）。
3. 用 Stage 8 Portfolio Exposure Overlay 给出的 sanitized 风险敞口（asset class 层面，不是 line item）。
4. 用历史回归得到的 asset class × factor 敏感度矩阵（**新计算**），把因子冲击翻译为 asset class 收益区间。
5. 加权得到组合层面 base/bear/bull 收益区间。

**禁止**：任何概率加权、期望值输出、ML 模型、个股层面输出。

### E2. Sensitivity matrix computation

**新增**：`src/modeling/factor_sensitivity.py`
- 输入：market_history 中的 asset class proxy 时序、因子时序（rate/credit/vol/growth/inflation）。
- 输出：rolling 5Y OLS β 矩阵，含 R²、t-stat、覆盖度元数据。
- **失败模式**：覆盖度不足或 R² < 阈值时输出 `insufficient_history` 标记，下游必须显示，不得回退默认值。

### E3. Return band engine

**新增**：`src/app_backend/services/scenario_return_band_service.py`
- 输出 schema：`ScenarioReturnBand(scenario, asset_class_breakdown[], portfolio_band_low, portfolio_band_mid, portfolio_band_high, drivers[], boundary_notice)`。
- `boundary_notice` 强制包含"非概率、非操作建议、非个股、非择时"五个否定字段。

### E4. API + 前端展示

- 新增路由：`POST /api/portfolio/scenario_return_band`。
- 前端新增页面：`app_frontend/src/components/ScenarioReturnBandPage.tsx`，三档卡片 + driver 表。

### E5. Tests + golden contract

- `tests/portfolio/test_factor_sensitivity.py`
- `tests/portfolio/test_scenario_return_band_service.py`
- `tests/contracts/test_scenario_return_band_contract.py`（≥20 contract 用例）

---

## 7. Phase F —— 单 Agent + Tool Calling

### F1. Tool registry

**新增**：`src/app_backend/services/agent_tool_registry.py`

工具集（首批 6 个）：
| Tool | 描述 | 后端服务 |
|---|---|---|
| `dashboard_query` | 查询某个 D 模块当前 evidence | `dashboard_service` |
| `evidence_lookup` | 查询某个 metric 的历史/百分位 | `dashboard_service` |
| `search_tavily` | 联网搜索 | `tavily_adapter` |
| `rag_retrieve` | 本地知识库检索 | `rag_retrieval_service` |
| `scenario_return_band` | 计算情景化收益区间 | `scenario_return_band_service` |
| `portfolio_overlay` | 取 sanitized portfolio exposure | `portfolio_overlay_service` |

每个工具都声明 JSON schema（OpenAI function calling 格式，DeepSeek 兼容）。

### F2. DeepSeek function-calling adapter

**修改**：`src/app_backend/services/deepseek_adapter.py`
- 扩展 `ExternalAIRequest` 增加 `tools[]` 与 `tool_choice` 字段。
- transport 层支持解析 `tool_calls` 返回结构。

### F3. Agent runtime

**新增**：`src/app_backend/services/agent_runtime.py`

主循环：
```
loop:
  response = deepseek.invoke(messages, tools=registry.schemas())
  if response.tool_calls:
    for call in response.tool_calls:
      result = registry.dispatch(call.name, call.args)
      messages.append(tool_message(result))
  else:
    return response.content
  if step_count > max_steps: break
```

**Budget 控制**：
- `max_steps=6`、`max_tokens_total=20000`、`max_search_calls=3`、`max_rag_calls=5`。
- 每步落 trace 到 `outputs/agent_traces/<session_id>.jsonl`（git-ignored）。

### F4. Agent chat 前端

**新增**：`app_frontend/src/components/AgentChatPage.tsx`
- 多轮对话窗口。
- 每个 tool call 渲染为可折叠卡片（显示工具名、入参、出参摘要、用时）。
- 显式开关：是否允许联网、是否允许 RAG、是否带 portfolio overlay。
- session trace 可下载为 markdown。

### F5. Trace + 审计

**新增**：`src/app_backend/services/agent_trace_service.py`
- 每个 session：input、tool_calls、tokens、cost、最终输出、所有引用 url。
- 不持久化原始 LLM prompt 与 raw response（仍受 22-flag 策略约束）。

### F6. Tests

- `tests/ai/test_agent_tool_registry.py`
- `tests/ai/test_agent_runtime_mocked.py`（mock DeepSeek + 所有工具）
- `tests/ai/test_agent_budget_control.py`

---

## 8. Phase G —— 端到端闭环

### G1. E2E 测试

- `tests/e2e/test_agent_full_loop.py` —— 三个典型 query：
  1. "最近美联储议息会议对组合的影响" → 触发 search → 一次性使用。
  2. "我的组合在 stagflation 情景下收益区间" → 触发 portfolio_overlay → scenario_return_band。
  3. "高通胀环境历史上股债表现" → 触发 rag_retrieve。

### G2. 性能 + 成本

- benchmark：单次 agent loop p50 < 15s、p95 < 40s。
- 每月 Tavily 调用预算 + DeepSeek token 预算上限写入配置。

### G3. 文档收尾

- `docs/era2_closeout.md` —— 列出所有新增/修改模块、所有解锁/保留的边界、剩余 backlog。
- 更新 `docs/INDEX.md`，把 Era 2 状态由 "current" 改为 "completed"。

---

## 9. 风险与依赖

| 风险 | 缓解 |
|---|---|
| Tavily API 不稳定 / 限流 | adapter 层留 fallback 接口，未来可加 Brave |
| Embedding 模型本地推理慢 | 改用 GPU / 切换 `bge-large-zh` 仅在文档侧、query 侧仍用 small |
| Agent 失控调用 / 烧 token | F3 budget 控制 + trace 强制；每步检查预算 |
| 情景区间被误读为预测 | E3 强制 `boundary_notice`、E4 前端永远显示 "区间非概率、非操作建议" |
| Vector store 体量膨胀 | C3 加 `mark_stale` + 定期清理脚本 |

## 10. 出文件清单

新增 Python 模块 ~22 个，新增前端组件 ~2 个，新增表/库 2 个（knowledge_base.sqlite、vector_store/），新增配置 1 个，新增 docs ~6 篇。详见各 Phase 章节。

## 11. 与现有路线衔接

- Era 1 已完成（前端美化）。
- AI-1 / AI-1.5 / AI-2 本地及单轮 DeepSeek 端点保留，Phase F 的 agent runtime **复用** AI-2 的 DeepSeek transport 与 guard 链，不替换。
- Stage 8 Portfolio Overlay 保留，Phase E 在其之上叠加 sensitivity 层。
- D 系模型语义全部不变。
