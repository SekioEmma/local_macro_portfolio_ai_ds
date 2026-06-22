# Codex 执行任务书 —— Era 2 AI Workbench v1

> 配套开发计划：`docs/development_plan_ai_era_v1.md`
> 执行原则：每个 Task 必须独立可提交（单一 commit / PR），完成定义（DoD）明确，测试先于实现。
> 全局命令：所有 Python 命令前置 `cd src && `；测试用 `python -m pytest ../tests/<path> -x -q`。

---

## 全局约束（每个 Task 都必须遵守）

1. **不得读** `.env`、`configs/external_llm.yaml`、`*.sqlite`、`data/holdings/`、`data/private/`、`outputs/`、`cache/`、原始 provider payload。
2. **不得在 transport 边界以外** import `httpx` / `requests` / `aiohttp`；不得读 `os.environ`/`os.getenv`。
3. **不得修改** D10–D19 / Stage 8 financial semantics、AI Context Manifest eligibility。
4. **不得弱化** `guard_response` / `guard_external_ai_runtime_policy`。
5. 新增网络出口必须新建 `*RuntimePolicy` 守门链，fail-closed。
6. 完成 task 后运行：`cd src && python -m pytest ../tests/ -x -q` 全绿才能提交。
7. 任何 L4 任务（解冻边界、新增外部出口、修改 Persistent Boundaries）需用户二次确认才能合并。

---

## Task Group A —— 治理与边界

### TASK-A1：撰写解冻策略文档（L4，docs only）

**输入**：本任务书 + `docs/short_term_development_plan.md` + `CLAUDE.md`。
**产出**：
- 新文件 `docs/era2_unfreeze_policy.md`，按计划 §2.A1 写明已解冻 / 保留冻结清单。
- 新文件 `docs/persistent_boundaries_v2.md`，写明"情景化收益区间"五个否定字段（非概率、非操作建议、非个股、非择时、非胜率）。
- 修改 `docs/short_term_development_plan.md` 的 "Frozen" 与 "Not Now" 段，附变更说明区块。
- 修改 `CLAUDE.md` 的 Security Constraints 段，把 `/api/search`、`/api/ai/tavily` 改为"受 SearchRuntimePolicy 约束允许"。

**DoD**：纯文档；无代码改动；用户确认后才合入。

---

### TASK-A2：SearchRuntimePolicy schema + guard

**新增**：
- `src/app_backend/schemas/search_external.py`
  - `SearchRuntimePolicy`（≥8 个 required-true + ≥6 个 required-false 字段，详见计划 §2.A2）
  - `SearchRequest(query: str, max_results: int=5, allowed_domains: list[str]|None=None)`
  - `SearchResponse(results: list[SearchResultItem], blocked: bool, findings: list[str])`
  - `SearchGuardResult(passed: bool, findings: list[str])`
- `src/app_backend/services/search_runtime_policy.py`
  - `guard_search_runtime_policy(policy) -> SearchGuardResult`
  - `assert_search_runtime_policy_allowed(policy)` 抛 `BlockedAdapterError`
  - 参照 `ai_external_runtime_policy.py` 的写法，fail-closed、纯函数、无 IO。

**测试**：`tests/ai/test_search_runtime_policy.py`，≥22 用例，覆盖每个 flag 单点失败。

**DoD**：所有新增测试通过；`cd src && python -m pytest ../tests/ai/ -x -q` 全绿。

---

### TASK-A3：搜索配置 loader

**新增**：
- `src/app_backend/services/search_config_loader.py` —— 读取 `configs/external_search.yaml`，返回 `SearchAdapterConfig` Pydantic 模型。**不得读 `.env` 或 `os.environ`**。
- 示例配置（不提交真实值）：`configs/external_search.yaml.example`，包含 `tavily_endpoint`、`timeout_seconds`、`domain_allowlist`、`domain_blocklist`、`max_results_per_call`、`daily_call_budget`。

**测试**：`tests/ai/test_search_config_loader.py`，覆盖缺字段、超额预算、空白名单等场景。

**DoD**：上面测试通过；运行 `cd src && python -c "from app_backend.services.search_config_loader import load_search_config; print(load_search_config('configs/external_search.yaml.example'))"` 成功。

---

## Task Group B —— Tavily 接入

### TASK-B1：Tavily provider/transport contract（无网络）

**新增**：
- `src/app_backend/services/tavily_provider_contract.py` —— `build_tavily_provider_payload(SearchRequest) -> TavilyProviderPayload`，纯函数。
- `src/app_backend/services/tavily_transport_contract.py` —— `TavilyTransport`（Protocol）、`TavilyTransportError`、`TavilyTransportResponse`、`build_transport_request_from_provider_payload`。

**测试**：`tests/ai/test_tavily_provider_contract.py`。

**DoD**：测试通过；模块 import 时**不得**触发网络。

---

### TASK-B2：Query sanitizer

**新增**：`src/app_backend/services/query_sanitizer.py`
- `sanitize_query(text: str) -> SanitizedQuery(text, blocked: bool, findings: list[str])`
- 拒绝模式：金额、ticker:weight、账号号码、本地路径（`C:\` / `/Users/` 等）、个人姓名（白名单姓氏匹配）、长 token 串（疑似 key）。

**测试**：`tests/ai/test_query_sanitizer.py`，≥30 用例。

**DoD**：所有用例通过。

---

### TASK-B3：Tavily adapter + Fake transport

**新增**：
- `src/app_backend/services/tavily_adapter.py` —— `TavilyAdapter`、`FakeTavilyAdapter`（确定性返回 fixture）。
- 调用流程：sanitize → guard policy → transport → guard response。

**测试**：`tests/ai/test_tavily_adapter_mocked_transport.py`，全部使用 FakeTransport，**不命中网络**。

**DoD**：测试通过；导入模块不触发网络。

---

### TASK-B4：Tavily real transport

**新增**：`src/app_backend/services/tavily_real_transport.py`
- 唯一允许 import `httpx` 的搜索侧文件。
- 强制 `timeout=30`、`follow_redirects=False`。
- 返回结果中的 url 必须二次校验在 `domain_allowlist` 内，否则丢弃该条。

**测试**：`tests/ai/test_tavily_real_transport.py`，用 `respx` 或 monkeypatch 模拟 httpx。

**DoD**：mock 测试通过；真实网络调用不在测试中触发。

---

### TASK-B5：API 路由

**修改**：`src/app_backend/main.py`
- 新增 `POST /api/search/tavily`，入参 `SearchRequest + SearchRuntimePolicy`，出参 `SearchResponse`。
- 默认 policy 失败关闭；调用前必须 sanitize + guard。

**测试**：`tests/api/test_search_route.py`，含 happy path（FakeAdapter）与 4 个 fail-closed 用例。

**DoD**：测试通过；`/api/search/tavily` 在 policy 缺省下返回 4xx。

---

## Task Group C —— 搜索结果分类与持久化

### TASK-C1：分类器

**新增**：`src/app_backend/services/search_result_classifier.py`
- 函数 `classify(result: SearchResultItem) -> ResultCategory`
- 类别枚举：`one_shot_news` / `policy_doc` / `research_report` / `historical_data` / `discard`
- 规则见计划 §4.C1。

**测试**：`tests/ai/test_search_result_classifier.py`，≥40 url 用例。

---

### TASK-C2：Knowledge base 服务

**新增**：
- SQLite schema 文件：`src/app_backend/services/knowledge_base_schema.sql`
- 服务：`src/app_backend/services/knowledge_base_service.py`，提供 `ingest_document`、`lookup_by_url`、`mark_stale`、`list_recent`。
- DB 路径：`data/knowledge_base.sqlite`（git-ignored，加进 `.gitignore` 若未在）。

**测试**：`tests/ai/test_knowledge_base_service.py`，用 tmp_path 创建测试库。

**DoD**：测试通过；`.gitignore` 已包含 `data/knowledge_base.sqlite` 与 `data/vector_store/`。

---

## Task Group D —— RAG

### TASK-D1：Embedding 服务

**新增**：`src/llm/embedding_service.py`
- 默认模型 `BAAI/bge-small-zh-v1.5`，本地加载。
- 函数 `embed_texts(texts: list[str]) -> np.ndarray`，仅本地推理。

**测试**：`tests/ai/test_embedding_service.py`（小 fixture 文本，断言 shape 与稳定性）。

**依赖**：`requirements.txt` 增加 `sentence-transformers`、`numpy`（若未有）。

---

### TASK-D2：向量库

**新增**：`src/llm/vector_store.py`，封装 Chroma。
- `add_documents(chunks, embeddings, metadata)`
- `query(text, k, filter=None) -> list[Hit]`

**依赖**：`requirements.txt` 增加 `chromadb`。

**测试**：`tests/ai/test_vector_store.py`，tmp_path 持久目录。

---

### TASK-D3：混合检索

**新增**：`src/app_backend/services/rag_retrieval_service.py`
- BM25（`rank_bm25`）+ 向量召回，RRF 融合，top-k。
- 输出 `RetrievedChunk(text, source_url, score, doc_type, published_date)`。

**测试**：`tests/ai/test_rag_retrieval_service.py`。

---

### TASK-D4：RAG context builder

**新增**：`src/app_backend/services/rag_context_builder.py`
- 把 RAG 结果包装为 `manifest.rag_evidence` 段，对接 `ai_context_service`。
- **不得**把 holdings 字段送入 query。

**测试**：`tests/ai/test_rag_context_builder.py`，含 manifest 兼容契约。

---

## Task Group E —— 情景化收益区间

### TASK-E1：设计文档（L4，docs only）

**新增**：`docs/scenario_return_band_design.md`，按计划 §6.E1 详写方法。

**DoD**：用户确认后才进入 E2。

---

### TASK-E2：因子敏感度

**新增**：`src/modeling/factor_sensitivity.py`
- 输入 asset class 与因子时序，输出 rolling 5Y OLS β、R²、覆盖度。
- 覆盖度不足时输出 `insufficient_history`，**不得回退默认值**。

**测试**：`tests/portfolio/test_factor_sensitivity.py`。

---

### TASK-E3：Return band service

**新增**：`src/app_backend/services/scenario_return_band_service.py`
- 输出 schema 包含 `boundary_notice` 五字段。
- 输入 = 当前 D16 scenario + Stage 8 sanitized exposure + E2 敏感度矩阵。

**测试**：
- `tests/portfolio/test_scenario_return_band_service.py`
- `tests/contracts/test_scenario_return_band_contract.py`（≥20 contract）

---

### TASK-E4：API + 前端

**修改**：`src/app_backend/main.py` 增加 `POST /api/portfolio/scenario_return_band`。
**新增**：`app_frontend/src/components/ScenarioReturnBandPage.tsx`，三档卡片 + driver 表 + 永久显示 boundary_notice。
**修改**：`app_frontend/src/api/client.ts`、`app_frontend/src/types.ts`、`app_frontend/src/components/AppShell.tsx`（加入导航）。

**测试**：
- `tests/api/test_scenario_return_band_route.py`
- 前端 `cd app_frontend && npx tsc --noEmit` 全绿。

---

## Task Group F —— 单 Agent + Tool Calling

### TASK-F1：Tool registry

**新增**：`src/app_backend/services/agent_tool_registry.py`
- 注册 6 个工具（计划 §7.F1 表格）。
- 每工具：name、description、JSON schema、handler 函数。
- 提供 `schemas()` 返回 OpenAI/DeepSeek function-calling 兼容数组。
- 提供 `dispatch(name, args) -> dict`。

**测试**：`tests/ai/test_agent_tool_registry.py`。

---

### TASK-F2：DeepSeek function calling 扩展

**修改**：
- `src/app_backend/schemas/ai_external.py` —— `ExternalAIRequest` 增加 `tools: list[dict] | None`、`tool_choice: str | None`。
- `src/app_backend/services/deepseek_provider_contract.py` —— payload 透传 tools。
- `src/app_backend/services/deepseek_real_transport.py` —— 解析 `choices[0].message.tool_calls`。

**测试**：扩展 `tests/ai/test_deepseek_adapter_mocked_transport.py` 覆盖 tool_calls 路径。

**DoD**：现有 DeepSeek 单轮路径不回归。

---

### TASK-F3：Agent runtime

**新增**：`src/app_backend/services/agent_runtime.py`
- `run_agent(session_id, user_message, policy, budget) -> AgentSessionResult`
- 主循环见计划 §7.F3。
- Budget：`max_steps=6`、`max_tokens_total=20000`、`max_search_calls=3`、`max_rag_calls=5`。
- 超额 → 立即终止 + trace 记录原因。

**测试**：
- `tests/ai/test_agent_runtime_mocked.py`（mock DeepSeek + 所有工具）
- `tests/ai/test_agent_budget_control.py`（含每个 budget 边界用例）

---

### TASK-F4：Agent trace service

**新增**：`src/app_backend/services/agent_trace_service.py`
- 每 session 落 `outputs/agent_traces/<session_id>.jsonl`（git-ignored）。
- 记录 input、每步 tool_call、tokens、cost、最终输出、引用 url。
- **不记录** raw LLM prompt 与 raw response 全文（仍受 22-flag 策略约束）。

**测试**：`tests/ai/test_agent_trace_service.py`。

---

### TASK-F5：Agent chat 前端

**新增**：`app_frontend/src/components/AgentChatPage.tsx`
- 多轮对话窗口。
- 每个 tool call 渲染为可折叠卡片。
- 顶部开关：允许联网 / 允许 RAG / 携带 portfolio overlay。
- 底部按钮：下载 session trace 为 markdown。
- 强制显示 boundary_notice。

**修改**：`AppShell.tsx`（加导航）、`client.ts`、`types.ts`。

**新增 API 路由**：`POST /api/agent/run`、`GET /api/agent/trace/<session_id>`。

**测试**：
- `tests/api/test_agent_route.py`
- 前端 `cd app_frontend && npx tsc --noEmit` 全绿。

---

## Task Group G —— 闭环

### TASK-G1：E2E 测试

**新增**：`tests/e2e/test_agent_full_loop.py`
- 三个典型 query（计划 §8.G1）。
- 全部使用 Fake transport，禁止真实网络。

---

### TASK-G2：Benchmark + 预算

**新增**：`scripts/benchmark_agent_loop.py`
- p50 / p95 / token 用量 / 调用次数统计。
**新增配置**：`configs/agent_budget.yaml.example`。

---

### TASK-G3：收尾文档

**新增**：`docs/era2_closeout.md`。
**修改**：`docs/INDEX.md`、`docs/short_term_development_plan.md`，Era 2 状态由 current → completed。

---

## 提交顺序与依赖

```
A1 (用户审核) → A2 → A3
                       ↘
B1 → B2 → B3 → B4 → B5
                       ↘
C1 → C2
       ↘
D1 → D2 → D3 → D4
                ↘
E1 (用户审核) → E2 → E3 → E4
                            ↘
F1 → F2 → F3 → F4 → F5
                        ↘
G1 → G2 → G3
```

A1 与 E1 是 L4 文档审核节点，**必须等用户确认**才能继续下游。其他 task 串行执行，每个 task 单独 commit 并跑全量测试。

## 每个 Task 的 commit 模板

```
<task-id>: <one-line summary>

- What: <new modules / modified files>
- Why: 引用计划 §<n>
- Tests: <new test file names>, <count> cases, all pass
- Boundary: <which guards / policies still hold>

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
```

## 验证清单（每个 task 完成时）

- [ ] `cd src && python -m pytest ../tests/ -x -q` 全绿
- [ ] `cd app_frontend && npx tsc --noEmit` 全绿（若动前端）
- [ ] 无新增 `httpx`/`requests`/`os.environ` 调用（除明确允许的 transport 文件）
- [ ] 无 D10–D19 / Stage 8 语义改动（除非 task 明确允许）
- [ ] 无 `.env` / SQLite / outputs / cache 提交
- [ ] commit message 按模板
