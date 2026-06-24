# Era 2 开发计划：AI Agent 宏观研究工作台

> 唯一权威源。前几版 `development_plan_ai_era_v1.md` 与 `_patch1.md` 已废弃。
> 配套任务书：`docs/era2_codex_brief.md`。

## 0. 用户决策快照

| 维度 | 决策 |
|---|---|
| 联网搜索 provider | Tavily（adapter 层预留 fallback） |
| 投资组合标的 | 固定 4 ETF：SPY 50% / QQQ 20% / 短债 20% / GLD 10%（目标配置） |
| 持仓更新方式 | 手动导入 csv |
| 计价货币 | 人民币（USDCNH 必须建模） |
| 收益区间口径 | 3 个月、不含股息、人民币 |
| 个股层边界 | 可点名持仓 + 解释风险敷口；禁止操作建议 |
| RAG 冷启动 | 专业研报 + 会议政策 + 历史金融数据 |
| Agent 起点 | 单 Agent + 工具调用（function calling） |
| 多 Agent 时机 | 单 agent 输出质量稳定后（Phase I 触发条件见 §10） |
| MCP | 不做 |
| 报告归档 | 做（含历史对比） |
| 使用模式 | 被动优先（用户问 → agent 答）；自动化推迟到 Era 3 |
| 移动端 | Era 3 做，本期 API 设计需 mobile-friendly |
| 质量评估 | 金标准对比 + 人工打分 |
| 学习注释 | 不写教学注释，代码最简化 |
| Tavily 预算 | 免费档够用 |
| DeepSeek token | 管够 |

## 1. 目标输出形态

Agent 对"分析当前宏观环境"类问题输出 `MacroBrief` 强类型 JSON，包含 10 节固定结构（§ 0 核心结论 / § 1 市场状态 / § 2 通胀利率 / § 3 地缘能源 / § 4 增长就业 / § 5 信用条件 / § 6 美股主线 / § 7 6 行模块表 / § 8 4 情景卡 / § 9 5 前瞻指标 + 来源汇总）。每个 block 必含 "已确认事实" 与 "判断" 两段，事实必带 source url。

参考样例：`docs/era2_macro_brief_baseline.md`（用 GPT 联网版输出作 reference）。

## 2. 阶段总览

```
A 治理与边界           ~1 周    docs only + L4 人审
B 联网搜索 + 实时报价   ~2 周
C 分类持久化 + 经济日历 ~1.5 周
D RAG 知识库            ~2 周
E 收益区间引擎           ~2 周   E1 docs 是 L4 人审
F Agent + 9 节前端       ~2.5 周
G 报告归档与历史对比      ~1 周
H 质量评估闭环           ~1 周
I （可选）多 Agent 拆分   ~2 周   触发条件 §10
```

总 ~12 周（不含 I）。两个 L4 人审节点：A1、E1。

## 3. Phase A — 治理与边界

### A1 解冻政策文档（L4）

- 新增 `docs/era2_unfreeze.md`：列出 Tavily/搜索、return estimates、Chat UI 多轮全部解冻；保留冻结 auto trading、portfolio optimizer、event odds 概率模型、full-account DeepSeek context、holdings line items 上行外部模型。
- 修订 `docs/GOVERNANCE.md` Persistent Boundaries 段：写出"情景化收益区间"五个否定字段（非概率、非操作、非个股推荐、非择时、非胜率）。注意：可点名持仓 + 描述风险敷口允许，但禁止"应减仓 X"措辞。
- 修订 `CLAUDE.md` Security Constraints：把 `/api/search`、`/api/ai/tavily` 改为受 SearchRuntimePolicy 约束允许；`/api/chat` 仍禁用原始用户输入直送。

### A2 SearchRuntimePolicy

- 新增 `src/app_backend/schemas/search_external.py` 与 `services/search_runtime_policy.py`。
- ≥ 8 个 required-true 守门位（search_enabled / provider_network_enabled / user_controlled_switch_enabled / single_request_user_approved / query_sanitizer_passed / domain_allowlist_enforced / response_guard_required / budget_within_limit）。
- ≥ 6 个 required-false 守门位（save_raw_query / save_raw_html / allow_holdings_in_query / allow_position_in_query / allow_account_in_query / allow_local_path_in_query）。
- fail-closed，纯函数，无 IO。

### A3 配置框架

- `configs/external_search.yaml.example`：Tavily endpoint、超时、域名白/黑名单、单次 max_results、每日预算上限。
- `src/app_backend/services/search_config_loader.py`：不读 `os.environ`，仅读 yaml；API key 在 transport 边界单点读 `.env`。

### A4 失败降级策略（我设计）

写入 `docs/era2_degradation.md`：

| 出口 | 失败检测 | 降级行为 |
|---|---|---|
| Tavily | timeout / 5xx / 域名校验失败 | agent 跳过 search 步骤，输出节标注 "联网数据不可用"，仅本地证据 |
| DeepSeek | 限流 / 超时 / 内容守门拒绝 | 降级到 AI-1 deterministic preview，标注 "AI 不可用，本地预览" |
| Alpha Vantage / FRED 实时报价 | 限速 / 数据缺 | 用 market_history SQLite 最近一笔，标注 stale 时间戳 |
| 经济日历 ingest | 公开页面格式变更 | 用上次 ingest 缓存，标注过期天数 |
| 嵌入服务 | 模型加载失败 | RAG 仅 BM25，向量召回跳过 |
| 多工具同时失败 | budget 守门 | 单步报错不中断，agent 继续；连续 3 步失败终止 loop |

## 4. Phase B — 联网搜索 + 实时报价

### B1 Tavily 接入

- `tavily_provider_contract.py`：纯函数 build payload。
- `tavily_transport_contract.py`：Protocol + Error 类型。
- `tavily_real_transport.py`：唯一允许 import httpx 的搜索文件；强制 timeout=30、follow_redirects=False；返回 url 二次校验域名白名单。
- `tavily_adapter.py`：含 FakeAdapter。
- `query_sanitizer.py`：拒绝金额、ticker:weight、账号、本地路径、长 token 串（≥ 30 用例）。

### B2 实时报价（不走 Tavily）

- `realtime_quote_service.py`：复用已 ingest 的 Alpha Vantage + FRED 通道。
- API：`quote_etf(["SPY","QQQ","SHY","GLD","VIX"])`、`treasury_curve(date)`、`tips_curve(date)`、`fx_rate("USDCNH")`。
- `QuoteSnapshot` 含 `market_state` 枚举（pre_market/regular/after_hours/closed），基于美东时区 + NYSE 静态日历 `data/nyse_trading_calendar.json`。

### B3 商品报价

- `commodity_quote_service.py`：油价（Brent/WTI）走 Tavily 限定域名（reuters.com/bloomberg.com/oilprice.com）+ 正则提取，失败返回 unavailable 不抛错。

### B4 API 路由

- `POST /api/search/tavily`、`GET /api/quote/etf`、`GET /api/quote/treasury_curve`、`GET /api/quote/fx`。
- 全部受策略守门，默认 fail-closed。

## 5. Phase C — 分类持久化 + 经济日历

### C1 搜索结果分类器

- `search_result_classifier.py`：单条结果 → `{one_shot_news, policy_doc, research_report, historical_data, discard}`。
- 规则：fred.stlouisfed.org/bls.gov/bea.gov/treasury.gov 域名 → historical_data；federalreserve.gov/imf.org/worldbank.org 含 speech|minutes|statement → policy_doc；pdf + 知名研究机构 → research_report；reuters/bloomberg/ft 等通用新闻 → one_shot_news。

### C2 历史金融数据 ingest

- 已识别 FRED/BLS series id 转发到现有 provider 路径，不直接抓网页。
- 拒绝任何非官方 url 写入 market_history。

### C3 Knowledge base

- 新表 `data/knowledge_base.sqlite`（git-ignored）：`documents(id, url, title, source_domain, doc_type, fetched_at, content_sha256, raw_text_path)` + `document_chunks(id, doc_id, chunk_index, text, embedding_vector_id)`。
- `knowledge_base_service.py`：ingest/lookup/mark_stale/list_recent。

### C4 经济日历

- C4a offline foundation 已完成：fixed event contracts, SQLite schema, synthetic fixture-only seed, local service.
- C4d read path boundary hardening 已完成：所有 public method 在 DB access 前校验 symlink ancestor chain.
- C4b guarded BLS/BEA manual official acquisition 已完成：
  - BLS ICS (`https://www.bls.gov/schedule/news_release/bls.ics`) → `consumer_price_index`, `employment_situation`
  - BEA JSON (`https://apps.bea.gov/API/signup/release_dates.json`) → `personal_income_and_outlays`, `gross_domestic_product`
  - 仅 `scripts/ingest_official_economic_calendar.py --live --write` 才 fetch + write
  - 默认 planned，无网络
  - `fomc_statement` exact-time acquisition deferred（schema 要求精确 `HH:MM`，不可推断）
- C4c 未开始。

## 6. Phase D — RAG

### D1 Embedding

- `src/llm/embedding_service.py`：默认 `BAAI/bge-small-zh-v1.5`，本地 sentence-transformers。
- chunk 策略：500 token / 100 overlap，段落优先。

### D2 向量库

- Chroma 持久化，目录 `data/vector_store/`（git-ignored）。
- `src/llm/vector_store.py`：add_documents / query。

### D3 混合检索

- `rag_retrieval_service.py`：BM25（rank_bm25）+ 向量召回 + RRF 融合。
- 输出 `RetrievedChunk(text, source_url, score, doc_type, published_date)`。

### D4 RAG context builder

- `rag_context_builder.py`：把 RAG 结果包装为 `manifest.rag_evidence` 段，对接 `ai_context_service`。
- 守门：query 文本不得含 holdings/account 字段。

### D5 冷启动数据

- 文档：`docs/era2_rag_seed_corpus.md` 列出第一批入库源（建议清单）：
  - Fed FOMC 历次声明 + 议息纪要（2020 起）
  - BLS CPI/Employment Situation 历史发布稿（2020 起）
  - BEA GDP/PCE 历史发布稿（2020 起）
  - IMF World Economic Outlook（最近 5 期）
  - 桥水/高盛/摩根大通公开 white paper（手工整理列表）
  - 用户私人收藏笔记（可选，git-ignored 目录 `data/private_notes/`）
- `scripts/seed_knowledge_base.py`：一键灌库脚本。

## 7. Phase E — 情景化收益区间

### E1 设计文档（L4）

`docs/era2_return_band_design.md`：

- 投资组合固定 4 ETF + RMB 计价的特殊处理；
- 因子集：rate（10Y nominal）、real_yield（10Y TIPS）、credit_spread（HY OAS）、equity_vol（VIX）、growth（ISM/GDPNow）、inflation（CPI YoY）、oil（Brent）、usdcnh；
- 敏感度方法：5Y rolling OLS，输出 β、R²、t-stat、覆盖度；
- 收益区间 = 各情景因子冲击 × β → asset class 美元收益 → 经 USDCNH 折算 → 4 ETF 加权组合 RMB 收益；
- 时间窗：3 个月；
- 失败模式：覆盖度不足或 R² 阈值不达时输出 `insufficient_history`，不得回退默认；
- 五个否定字段强制写入输出。

### E2 Sensitivity matrix

- `src/modeling/factor_sensitivity.py`：rolling 5Y OLS 计算 4×8 矩阵（4 ETF × 8 因子）。
- `tests/portfolio/test_factor_sensitivity.py`。

### E3 ReturnBand service

- `scenario_return_band_service.py`：输出 `ScenarioReturnBand(scenario, eth_breakdown, portfolio_band_low/mid/high_rmb, drivers, boundary_notice, narrative)`。
- `ScenarioNarrative` 含 `trigger_conditions / transmission_path / evidence_supports`。

### E4 API + 前端

- `POST /api/portfolio/scenario_return_band`。
- 前端 `ScenarioReturnBandPage.tsx` 3 档卡 + driver 表 + 永久 boundary 提示。

## 8. Phase F — Agent + 9 节前端

### F1 Tool registry（11 工具）

| Tool | 后端 |
|---|---|
| dashboard_query | dashboard_service |
| evidence_lookup | dashboard_service |
| search_tavily | tavily_adapter |
| rag_retrieve | rag_retrieval_service |
| quote_etf | realtime_quote_service |
| treasury_curve | realtime_quote_service |
| commodity_quote | commodity_quote_service |
| calendar_lookup | economic_calendar_service |
| portfolio_overlay | portfolio_overlay_service |
| scenario_return_band | scenario_return_band_service |
| finalize_macro_brief | 终止工具 |

### F2 MacroBrief schema

- `src/app_backend/schemas/macro_brief.py`：10 节强类型、Pydantic 校验。
- `module_table` 必须恰好 6 行（权益趋势/利率压力/真实利率压力/通胀能源/信用压力/地缘风险）。
- `scenarios` 必须 4 个键（base/bullish/bearish/systemic）。
- `forward_indicators` 必须 5 条，每条含 release_date。
- `boundary_notice` 必须含 5 个否定关键词。

### F3 Prompt 模板

- `macro_brief_prompt.py`：system prompt 内嵌 10 节模板、"已确认事实+判断" 强制结构、5 个禁止、JSON schema response_format。

### F4 DeepSeek function calling

- `deepseek_real_transport.py` 解析 `tool_calls` 返回；`ExternalAIRequest` 加 `tools/tool_choice`。

### F5 Agent runtime

- `agent_runtime.py`：主循环 tool dispatch；最后必须调 `finalize_macro_brief`；输出过 `macro_brief_parser`，失败重试 1 次。
- Budget：max_steps=18 / max_search_calls=8 / max_rag_calls=5 / max_tokens_total=40000。
- 触发降级策略（见 §3.A4）。

### F6 Trace

- `agent_trace_service.py`：每 session 落 `outputs/agent_traces/<session_id>.jsonl`。
- 记录 input、tool_calls、tokens、cost、最终输出、引用 url。
- 不记录 raw prompt/response 全文。

### F7 前端 9 节卡片化

- `app_frontend/src/components/MacroBriefView.tsx` 顶层。
- 子组件：`CoreConclusionCard / MarketStateCard / FactJudgmentCard / ModuleTable / ScenarioCardSet / ForwardIndicatorTimeline / SourceList`。
- § 1 ETF 4 卡横向。
- § 8 4 卡按 base/bull/bear/systemic 配色（绿/蓝/橙/红）。
- § 9 时间线含距今天数。
- 流式渲染：每节完成立即显示，未完成显示骨架屏。
- API 路由 `POST /api/agent/run`、`GET /api/agent/trace/<session_id>`。
- 移动端预留：MacroBriefView 与 API 解耦，所有数据由 JSON 渲染；Card 组件接受 `compact` prop 用于窄屏。

## 9. Phase G — 报告归档与历史对比

### G1 Archive schema

- 新表 `data/macro_brief_archive.sqlite`（git-ignored）：`briefs(session_id, created_at, user_question, brief_json, finish_reason)`。
- 服务 `macro_brief_archive_service.py`：save / list / get_by_id / diff(id_a, id_b)。

### G2 历史对比页

- 前端 `MacroBriefArchivePage.tsx`：列表 + 选择两份 brief 看 diff。
- Diff 维度：module_table 状态变化、scenarios 措辞变化、新增/消失的 forward_indicators。

### G3 API

- `GET /api/agent/archive`、`GET /api/agent/archive/<id>`、`GET /api/agent/archive/diff?a=&b=`。

## 10. Phase H — 质量评估闭环

### H1 金标准库

- `tests/fixtures/macro_brief/golden/`：手工维护的高质量 MacroBrief JSON（首批种子用 GPT 输出转格式）。
- 每次发版/重大 prompt 改动跑一次对照。

### H2 自动评分

- `scripts/score_macro_brief.py`：对单个 brief 输出评分卡：
  - schema 完整度（每节是否齐全）
  - source 多样性（独立域名数）
  - 数据新鲜度（fact 日期距今）
  - 判断与事实分离度（关键字打分）
  - 边界违规检测（5 禁止关键词扫描）

### H3 人工打分入口

- 前端 `MacroBriefView` 末尾新增评分组件：用户 1-5 星 + 自由评论。
- 数据写入 `macro_brief_archive.briefs.human_score / human_comment`。
- 后端 `GET /api/agent/quality_dashboard`：返回最近 30 份评分聚合。

## 11. Phase I — 多 Agent（可选，触发条件未满足则不做）

**触发条件**（全部满足才启动）：

1. Phase H 自动评分连续 4 周 ≥ 80/100；
2. 人工打分连续 4 周 ≥ 4 星；
3. 单一典型 query 的 9 节完整度 ≥ 95%。

**未触发时**：留在 backlog。

**若触发**：拆三 agent — Research（找证据 + 联网搜索 + RAG）、Critic（事实一致性 + 边界检查）、Writer（按 schema 出最终 brief）。框架建议 LangGraph 或自建 state machine（不引入 LangChain 完整栈）。

## 12. 验收基线

完成 Phase F 后，agent 对"分析当前宏观环境"问题输出必须满足：

- [ ] § 0 加粗核心结论 2-3 句
- [ ] § 1 含 4 ETF + USDCNH 实时报价 + market_state
- [ ] § 2 含 CPI/PCE/FOMC/收益率/TIPS 各至少 1 个数字 + inline 链接
- [ ] § 3 含 Brent + WTI + ≥ 2 地缘事件链接
- [ ] § 4 含 NFP + 失业率 + GDP/GDPNow
- [ ] § 5 含 VIX + NFCI + ≥ 1 信用利差
- [ ] § 6 含标普盈利预期同比
- [ ] § 7 6 行模块表完整
- [ ] § 8 4 情景，systemic 含"证据支持/不支持"
- [ ] § 9 5 前瞻指标，至少 4 条精确日期
- [ ] 末尾来源 ≥ 10 条
- [ ] boundary_notice 含 5 否定字段
- [ ] portfolio_overlay 触发时输出 4 ETF + RMB 折算
- [ ] 历史对比页能跑通 diff

## 13. 不变项

- D10–D19 / Stage 8 financial semantics 全保留。
- 22-flag SearchRuntimePolicy fail-closed。
- 禁止概率 / 操作建议 / 胜率 / 择时 / 个股推荐措辞。
- 个股可点名仅限于"解释风险敷口"，禁止操作动词（"应/建议/减仓/加仓"）。
- 隐私：holdings/account/position 字段不得进入外部 query 文本。

## 14. 风险与依赖

| 风险 | 缓解 |
|---|---|
| Tavily 限流 | adapter 留 fallback；命中即降级（§ 3.A4） |
| Embedding 本地推理慢 | 用 bge-small；query 侧用 small，文档侧可换 large |
| Agent 烧 token | F5 budget + trace 强制 |
| 收益区间被误读为预测 | boundary_notice 强制 + 前端永显 |
| Vector store 体量 | C3 mark_stale + 定期清理 |
| 静态日历过期 | scripts/ingest_economic_calendar.py 月度运行 |
| 4 ETF 简化破坏未来扩展 | factor_sensitivity 计算保留 N×M 通用形态，仅 portfolio 应用层固定 4 |

## 15. 与现有路线衔接

- AI-1 / AI-1.5 / AI-2 保留：单 agent runtime 复用 AI-2 transport 与 guard 链。
- Stage 8 Portfolio Overlay 保留：Phase E 在其之上叠 sensitivity 层。
- Dashboard 13 路由全保留。
- 前端 AppShell 路由扩展，不替换现有页面。
