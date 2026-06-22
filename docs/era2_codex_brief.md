# Era 2 Codex 执行任务书

> 唯一权威源。前几版 `codex_task_brief_ai_era_v1.md`、`_patch1.md`、`codex_ai_chat_page_prompt.md` 已废弃。
> 配套计划：`docs/era2_plan.md`。

## 全局约束

每个 task 必须遵守：

1. 禁读：`.env`、`configs/external_llm.yaml`、`*.sqlite`、`data/holdings/`、`data/private/`、`outputs/`、`cache/`、raw provider payload。
2. 禁 import `httpx`/`requests`/`aiohttp` —— transport 边界文件除外。
3. 禁读 `os.environ` / `os.getenv` —— 单点 secrets loader 除外。
4. 禁改 D10–D19 / Stage 8 financial semantics、AI Context Manifest eligibility。
5. 禁弱化 `guard_response` / `guard_external_ai_runtime_policy` / `guard_search_runtime_policy`。
6. 新增网络出口必须新建 `*RuntimePolicy` 守门链，fail-closed。
7. 完成后 `cd src && python -m pytest ../tests/ -x -q` 全绿才能提 commit。
8. 不写学习注释、不写多段 docstring（最多 1 行）。
9. L4 task（A1、E1）需用户二次确认才合并。
10. commit 模板见 §末。

---

## TASK-A1：治理文档解冻 + 边界修订（L4，docs only）

**新增**：
- `docs/era2_unfreeze.md`：列已解冻 / 仍冻结清单。
- `docs/era2_degradation.md`：失败降级表（计划 §3.A4 全部 6 行）。

**修改**：
- `docs/GOVERNANCE.md`（已统一治理）Persistent Boundaries 段：写情景化收益区间 5 否定字段；明确"个股可点名 + 描述敷口，禁止操作动词"。
- `CLAUDE.md` Security Constraints：把 `/api/search`、`/api/ai/tavily` 改为受策略允许；`/api/chat` 仍禁。

**DoD**：用户审核通过后合入；无代码改动。

---

## TASK-A2：SearchRuntimePolicy

**新增**：
- `src/app_backend/schemas/search_external.py`：`SearchRuntimePolicy` ≥ 8 required-true + ≥ 6 required-false；`SearchRequest / SearchResponse / SearchGuardResult`。
- `src/app_backend/services/search_runtime_policy.py`：`guard_search_runtime_policy(policy)` 纯函数 fail-closed；`assert_search_runtime_policy_allowed` 抛 BlockedAdapterError。

**测试**：`tests/ai/test_search_runtime_policy.py` ≥ 22 用例。

**DoD**：测试全绿。

---

## TASK-A3：搜索配置 loader

**新增**：
- `src/app_backend/services/search_config_loader.py`：读 yaml，返回 `SearchAdapterConfig`；不读 os.environ。
- `configs/external_search.yaml.example`：含 tavily_endpoint / timeout_seconds / domain_allowlist / domain_blocklist / max_results_per_call / daily_call_budget。

**测试**：`tests/ai/test_search_config_loader.py` 覆盖缺字段/超额预算/空白名单。

**DoD**：测试全绿；example 文件不含真实 key。

---

## TASK-B1：Tavily provider/transport contract（无网络）

**新增**：
- `src/app_backend/services/tavily_provider_contract.py`：`build_tavily_provider_payload(SearchRequest)` 纯函数。
- `src/app_backend/services/tavily_transport_contract.py`：`TavilyTransport`(Protocol) / `TavilyTransportError` / `TavilyTransportResponse` / `build_transport_request_from_provider_payload`。

**测试**：`tests/ai/test_tavily_provider_contract.py`。

**DoD**：import 不触发网络。

---

## TASK-B2：Query sanitizer

**新增**：`src/app_backend/services/query_sanitizer.py`
- `sanitize_query(text) -> SanitizedQuery(text, blocked, findings)`
- 拒绝模式：金额（含 $/USD/¥/RMB）、ticker:weight、账号号码、本地路径（`C:\` `/Users/` `/home/`）、长 token 串（≥ 30 字符无空格）、姓名（白名单姓氏）。

**测试**：`tests/ai/test_query_sanitizer.py` ≥ 30 用例。

---

## TASK-B3：Tavily adapter + Fake

**新增**：`src/app_backend/services/tavily_adapter.py` — `TavilyAdapter`、`FakeTavilyAdapter`。
调用链：sanitize → guard policy → transport → guard response。

**测试**：`tests/ai/test_tavily_adapter_mocked_transport.py` 全 Fake，不命中网络。

---

## TASK-B4：Tavily real transport

**新增**：`src/app_backend/services/tavily_real_transport.py`
- 唯一允许 import httpx 的搜索文件。
- timeout=30、follow_redirects=False。
- 返回 url 二次校验域名白名单，不在则丢弃。

**测试**：`tests/ai/test_tavily_real_transport.py` 用 respx 或 monkeypatch。

---

## TASK-B5：Realtime quote service（不走 Tavily）

**新增**：`src/app_backend/services/realtime_quote_service.py`
- 复用 `data_providers/` 中 Alpha Vantage + FRED 通道，**禁止**新加 httpx import。
- API：
  - `quote_etf(symbols: list[str]) -> list[QuoteSnapshot]`（含 SPY/QQQ/SHY/GLD/VIX）
  - `treasury_curve(date: str | None) -> TreasuryCurveSnapshot`（2Y/10Y/20Y/30Y）
  - `tips_curve(date: str | None) -> TipsCurveSnapshot`（5Y/10Y/30Y real yield）
  - `fx_rate(pair: str = "USDCNH") -> FxSnapshot`
- `QuoteSnapshot.market_state` 枚举 pre_market/regular/after_hours/closed，基于美东时区 + `data/nyse_trading_calendar.json` 静态日历。

**测试**：`tests/ai/test_realtime_quote_service.py` 全 fixture。

---

## TASK-B6：Commodity quote

**新增**：`src/app_backend/services/commodity_quote_service.py`
- Brent / WTI 走 Tavily 限定域名（reuters.com / bloomberg.com / oilprice.com）。
- 正则提取价格；失败返回 `unavailable` 不抛错。

**测试**：`tests/ai/test_commodity_quote_service.py` mock Tavily 返回 3 类新闻 snippet。

---

## TASK-B7：API 路由

**修改**：`src/app_backend/main.py`
- `POST /api/search/tavily`、`GET /api/quote/etf`、`GET /api/quote/treasury_curve`、`GET /api/quote/fx`、`GET /api/quote/commodity`。
- 默认 fail-closed；含至少 4 个 fail-closed 路由测试。

**测试**：`tests/api/test_search_route.py`、`tests/api/test_quote_route.py`。

---

## TASK-C1：搜索结果分类器

**新增**：`src/app_backend/services/search_result_classifier.py`
- `classify(result) -> ResultCategory ∈ {one_shot_news, policy_doc, research_report, historical_data, discard}`
- 规则见计划 §5.C1。

**测试**：`tests/ai/test_search_result_classifier.py` ≥ 40 url 用例。

---

## TASK-C2：Knowledge base 服务

**新增**：
- `src/app_backend/services/knowledge_base_schema.sql`
- `src/app_backend/services/knowledge_base_service.py`：ingest_document / lookup_by_url / mark_stale / list_recent。
- DB 路径 `data/knowledge_base.sqlite`（加 `.gitignore` 若未加）。

**测试**：`tests/ai/test_knowledge_base_service.py` 用 tmp_path。

---

## TASK-C3：经济日历

**新增**：
- 表 schema 写入 `src/app_backend/services/economic_calendar_schema.sql`。
- `src/app_backend/services/economic_calendar_service.py`：`next_releases(window_days=30)`、`events_by_name(name, limit=5)`。
- `scripts/ingest_economic_calendar.py`：月度运行，爬 BLS / BEA / Fed 公开日历。
- 默认 fixture 数据 `data/economic_calendar_seed.json` 用于离线测试。

**测试**：
- `tests/ai/test_economic_calendar_service.py` fixture 库。
- `tests/scripts/test_ingest_economic_calendar.py` mock 页面。

---

## TASK-D1：Embedding 服务

**新增**：`src/llm/embedding_service.py`
- `BAAI/bge-small-zh-v1.5`，本地 sentence-transformers。
- `embed_texts(texts: list[str]) -> np.ndarray`。
- chunk 工具 `chunk_text(text, max_tokens=500, overlap=100)`。

**依赖**：`requirements.txt` 加 `sentence-transformers`、`numpy`。

**测试**：`tests/ai/test_embedding_service.py` 小 fixture 文本，断言 shape + 稳定性。

---

## TASK-D2：向量库

**新增**：`src/llm/vector_store.py` 封装 Chroma：`add_documents / query`。

**依赖**：`requirements.txt` 加 `chromadb`。

**测试**：`tests/ai/test_vector_store.py` tmp_path 持久目录。

---

## TASK-D3：混合检索

**新增**：`src/app_backend/services/rag_retrieval_service.py`
- BM25（`rank_bm25`）+ 向量召回 + RRF 融合。
- 输出 `RetrievedChunk(text, source_url, score, doc_type, published_date)`。

**测试**：`tests/ai/test_rag_retrieval_service.py`。

---

## TASK-D4：RAG context builder

**新增**：`src/app_backend/services/rag_context_builder.py`
- 包装为 `manifest.rag_evidence`，对接 `ai_context_service`。
- 守门：query 文本不得含 holdings/account 字段。

**测试**：`tests/ai/test_rag_context_builder.py` 含 manifest 契约。

---

## TASK-D5：冷启动 seed 脚本

**新增**：
- `docs/era2_rag_seed_corpus.md`：第一批入库源清单（FOMC 声明 / BLS CPI / BEA GDP / IMF WEO / 公开 white paper）。
- `scripts/seed_knowledge_base.py`：一键灌库，下载 → 分类 → chunk → embed → 入 Chroma。
- 支持 `--source fomc` / `--source bls` 等分源运行。
- 私人笔记目录 `data/private_notes/`（git-ignored）可选 ingest。

**测试**：`tests/scripts/test_seed_knowledge_base.py` mock 下载。

---

## TASK-E1：收益区间设计文档（L4）

**新增**：`docs/era2_return_band_design.md`（计划 §7.E1 全部要点）。

**DoD**：用户审核通过才进入 E2。

---

## TASK-E2：因子敏感度

**新增**：`src/modeling/factor_sensitivity.py`
- 输入：asset class proxy 时序 + 因子时序（rate / real_yield / credit_spread / equity_vol / growth / inflation / oil / usdcnh）。
- 输出：rolling 5Y OLS β 矩阵 + R² + t-stat + 覆盖度。
- 覆盖度不足或 R² < 阈值 → `insufficient_history`，不得回退默认。
- 计算保留 N×M 通用形态（不写死 4 ETF），portfolio 应用层再固定。

**测试**：`tests/portfolio/test_factor_sensitivity.py`。

---

## TASK-E3：ReturnBand service

**新增**：`src/app_backend/services/scenario_return_band_service.py`
- 输入：D16 scenario + Stage 8 sanitized exposure + E2 β 矩阵 + USDCNH 汇率。
- 输出 schema：
  ```python
  class ScenarioReturnBand:
      scenario: str  # base/bullish/bearish/systemic
      etf_breakdown: list[EtfBand]  # 4 行 ETF
      portfolio_band_low_rmb: float
      portfolio_band_mid_rmb: float
      portfolio_band_high_rmb: float
      drivers: list[FactorDriver]
      narrative: ScenarioNarrative
      boundary_notice: str  # 含 5 否定关键词
      horizon_months: int = 3
      currency: str = "RMB"
      includes_dividends: bool = False
  ```
- `ScenarioNarrative`：`trigger_conditions / transmission_path / evidence_supports`。
- systemic 情景必须填 `evidence_supports`。

**测试**：
- `tests/portfolio/test_scenario_return_band_service.py`
- `tests/contracts/test_scenario_return_band_contract.py` ≥ 20 用例。

---

## TASK-E4：API + 前端

**修改**：`src/app_backend/main.py` 加 `POST /api/portfolio/scenario_return_band`。

**新增前端**：
- `app_frontend/src/components/ScenarioReturnBandPage.tsx`：3 档卡 + ETF 明细表 + 因子驱动表 + 永久 boundary 提示。
- 修改 `app_frontend/src/api/client.ts`、`types.ts`、`AppShell.tsx` 加导航。

**测试**：
- `tests/api/test_scenario_return_band_route.py`
- `cd app_frontend && npx tsc --noEmit` 全绿。

---

## TASK-F1：Tool registry

**新增**：`src/app_backend/services/agent_tool_registry.py`
- 11 工具（计划 §8.F1 表）。
- 每工具：name / description / JSON schema / handler。
- `schemas()` 返回 function-calling 兼容数组；`dispatch(name, args) -> dict`。

**测试**：`tests/ai/test_agent_tool_registry.py`。

---

## TASK-F2：MacroBrief schema

**新增**：`src/app_backend/schemas/macro_brief.py`
- 10 节强类型 Pydantic v2。
- 校验：core_conclusion 50–500 字；module_table 恰好 6 行（固定模块名集合）；scenarios 4 键全；forward_indicators 恰好 5；boundary_notice 含 5 关键词；每 block 的 facts ≥ 1，每条 source_url 必填。

**测试**：`tests/ai/test_macro_brief_schema.py` ≥ 20 用例。

---

## TASK-F3：MacroBrief prompt + parser

**新增**：
- `src/app_backend/services/macro_brief_prompt.py`：system + user prompt 构造器；含 9 节模板（计划 §1）、"已确认事实+判断" 强制结构、5 禁止、JSON schema response_format。
- `src/app_backend/services/macro_brief_parser.py`：JSON / markdown → MacroBrief；含 4 层校验（pydantic / url 形式 / 数字-来源对齐 / 边界用语关键词）。

**测试**：
- `tests/ai/test_macro_brief_prompt.py` 关键字断言。
- `tests/ai/test_macro_brief_parser.py` 含 GPT 样例 fixture（通过）+ 旧 DS 样例 fixture（按预期失败报缺节）。

**Fixture**：`tests/fixtures/macro_brief/gpt_baseline_2026_06_22.md`、`ds_legacy_sample.md`。

---

## TASK-F4：DeepSeek function calling 扩展

**修改**：
- `src/app_backend/schemas/ai_external.py`：`ExternalAIRequest` 加 `tools: list[dict] | None`、`tool_choice: str | None`。
- `src/app_backend/services/deepseek_provider_contract.py`：payload 透传 tools。
- `src/app_backend/services/deepseek_real_transport.py`：解析 `choices[0].message.tool_calls`。

**测试**：扩展 `tests/ai/test_deepseek_adapter_mocked_transport.py` 加 tool_calls 路径。
**回归**：原单轮路径不破。

---

## TASK-F5：Agent runtime

**新增**：`src/app_backend/services/agent_runtime.py`
- `run_agent(session_id, user_message, policy, budget) -> AgentSessionResult`
- 主循环：DeepSeek → tool_calls → dispatch → tool_message → repeat。
- 终止条件：调用 `finalize_macro_brief` 或 budget 超限或连续 3 步失败。
- 输出过 `macro_brief_parser`，schema 失败重试 1 次。
- Budget：max_steps=18 / max_search_calls=8 / max_rag_calls=5 / max_tokens_total=40000。
- 降级策略（计划 §3.A4 6 行表全部实现）。

**测试**：
- `tests/ai/test_agent_runtime_mocked.py` 完整 mock loop。
- `tests/ai/test_agent_budget_control.py` 每个 budget 边界。
- `tests/ai/test_agent_degradation.py` 6 个降级路径。

---

## TASK-F6：Agent trace service

**新增**：`src/app_backend/services/agent_trace_service.py`
- 落 `outputs/agent_traces/<session_id>.jsonl`（git-ignored）。
- 字段：input / 每步 tool_call name+args 摘要+result 摘要 / tokens / cost / 最终 brief / 引用 url。
- 禁记录 raw LLM prompt 或 response 全文。

**测试**：`tests/ai/test_agent_trace_service.py`。

---

## TASK-F7：MacroBriefView 前端

**新增**：
- `app_frontend/src/components/MacroBriefView.tsx`（顶层）
- `app_frontend/src/components/macro_brief/`：`CoreConclusionCard.tsx`、`MarketStateCard.tsx`、`FactJudgmentCard.tsx`、`ModuleTable.tsx`、`ScenarioCardSet.tsx`、`ForwardIndicatorTimeline.tsx`、`SourceList.tsx`
- `app_frontend/src/components/AgentChatPage.tsx`：输入框 + 流式 MacroBriefView 渲染。
- 修改 `App.tsx`、`AppShell.tsx`、`client.ts`、`types.ts`。

**样式**：
- core_conclusion 顶部高亮卡，加粗 16px。
- § 1 4 ETF 横向卡。
- § 8 4 卡按 base/bull/bear/systemic 配色（绿/蓝/橙/红）。
- § 9 时间线含 countdown（基于 `currentDate`）。
- 移动端预留：Card 组件接受 `compact` prop；MacroBriefView 不耦合具体路由。

**新增 API**：`POST /api/agent/run`、`GET /api/agent/trace/<session_id>`。

**测试**：
- `tests/api/test_agent_route.py`
- `cd app_frontend && npx tsc --noEmit` 全绿。

---

## TASK-G1：归档 schema + 服务

**新增**：
- 表 schema：`src/app_backend/services/macro_brief_archive_schema.sql`
- 服务：`src/app_backend/services/macro_brief_archive_service.py`：save / list / get_by_id / diff(id_a, id_b)。
- DB 路径 `data/macro_brief_archive.sqlite`（git-ignored）。

**测试**：`tests/ai/test_macro_brief_archive_service.py`。

---

## TASK-G2：历史对比页

**新增**：`app_frontend/src/components/MacroBriefArchivePage.tsx`
- 列表 + 选两份 brief 看 diff。
- Diff 维度：module_table 状态变化 / scenarios 措辞 / forward_indicators 增删。

**新增 API**：`GET /api/agent/archive`、`GET /api/agent/archive/<id>`、`GET /api/agent/archive/diff?a=&b=`。

**测试**：
- `tests/api/test_archive_route.py`
- `cd app_frontend && npx tsc --noEmit` 全绿。

---

## TASK-H1：金标准库

**新增**：
- 目录 `tests/fixtures/macro_brief/golden/`：手工维护的 ≥ 3 份高质量 MacroBrief JSON（首批从 GPT 输出转格式）。
- `docs/era2_quality_golden_index.md`：列出每份 golden 的来源、日期、覆盖场景。

---

## TASK-H2：自动评分脚本

**新增**：`scripts/score_macro_brief.py`
- 输入：MacroBrief JSON 或 session_id。
- 评分维度：
  - schema_completeness（每节齐全度，0-100）
  - source_diversity（独立域名数）
  - data_freshness（fact 日期距今天数中位数）
  - fact_judgment_separation（关键字打分）
  - boundary_violation（5 禁止扫描，违规扣分）
- 总分 0-100，输出 markdown 报告。

**测试**：`tests/scripts/test_score_macro_brief.py` 用 golden + bad sample。

---

## TASK-H3：人工打分 + quality dashboard

**修改**：
- `MacroBriefView` 末尾加评分组件：1-5 星 + 自由评论。
- `macro_brief_archive_service` 新增 `set_human_score(id, score, comment)`。

**新增 API**：
- `POST /api/agent/archive/<id>/score`
- `GET /api/agent/quality_dashboard` 返回最近 30 份评分聚合（自动分 + 人工分）。

**测试**：`tests/api/test_quality_dashboard_route.py`。

---

## TASK-I1（条件触发）：多 Agent 拆分设计

仅在 Phase H 评分连续 4 周达标后启动。设计文档 + 三 agent 拆分 + state machine 实现。

**触发未达标时此 task 不动**。

---

## 依赖顺序

```
A1 [L4 user] → A2 → A3
                       ↘
B1 → B2 → B3 → B4 → B5 → B6 → B7
                                    ↘
C1 → C2 → C3
              ↘
D1 → D2 → D3 → D4 → D5            (可与 C/E 并行)
                  ↘
E1 [L4 user] → E2 → E3 → E4
                            ↘
F1 → F2 → F3 → F4 → F5 → F6 → F7
                                  ↘
G1 → G2
        ↘
H1 → H2 → H3
              ↘
I1 (conditional)
```

## Commit 模板

```
<task-id>: <one-line summary>

- What: <new/modified files>
- Why: 引用 era2_plan.md §<n>
- Tests: <test files>, <count> cases all pass
- Boundary: <guards/policies still hold>

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
```

## 每 task 完成验证清单

- [ ] `cd src && python -m pytest ../tests/ -x -q` 全绿
- [ ] `cd app_frontend && npx tsc --noEmit` 全绿（如动前端）
- [ ] 无新增 `httpx`/`requests`/`os.environ` 调用（除明确允许文件）
- [ ] 无 D10–D19 / Stage 8 语义改动（除非 task 明确允许）
- [ ] 无 `.env` / SQLite / outputs / cache 提交
- [ ] 无超过 1 行的 docstring，无教学注释
- [ ] commit message 按模板
