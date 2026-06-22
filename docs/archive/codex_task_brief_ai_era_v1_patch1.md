# Codex 任务书补丁 v1.1

> 母任务书：`docs/codex_task_brief_ai_era_v1.md`
> 计划补丁：`docs/development_plan_ai_era_v1_patch1.md`
> 本补丁新增 / 替换以下 task。母任务书未提到的 task 保持原样。

---

## 新增 Task Group H —— 结构化研报输出层

### TASK-H1：MacroBrief schema（L4 docs+code）

**新增**：`src/app_backend/schemas/macro_brief.py`

包含计划补丁 §2.1 列出的所有 dataclass：
- `MacroBriefSection`（枚举）
- `FactStatement(text, source_url, source_label, value_date)`
- `JudgmentStatement(text, evidence_refs)`
- `MarketStateBlock`, `InflationRatesBlock`, `GeopoliticsBlock`, `GrowthLaborBlock`, `CreditFincondBlock`, `EquityMainlineBlock`
- `ModuleTableRow(module, status, judgment)` —— 6 行固定模块名校验
- `ScenarioCard(name, trigger_conditions, transmission_path, evidence_supports, return_band|None)`
- `ScenarioSet(base, bullish, bearish, systemic)`
- `ForwardIndicator(name, release_date, release_time_et, why_matters, threshold_to_change_view)`
- `SourceRef(label, url, accessed_date)`
- `MacroBrief`（顶层，所有字段必填）

**校验逻辑**（Pydantic v2 validator）：
- `core_conclusion` 长度 50–500 字
- `module_table` 必须恰好 6 行，模块名必须在固定集合内
- `scenarios` 4 个键必须全有
- `forward_indicators` 长度恰好 5
- 任何 block 的 `facts` 至少 1 条，每条 `source_url` 必填
- `boundary_notice` 必须含全部 5 个否定字段（非概率/非操作/非个股/非择时/非胜率）的关键词

**测试**：`tests/ai/test_macro_brief_schema.py`，≥20 用例覆盖每个校验路径。

**DoD**：测试通过；schema 文档化在 `docs/macro_brief_schema.md`。

---

### TASK-H2：MacroBrief prompt 模板

**新增**：`src/app_backend/services/macro_brief_prompt.py`

提供 `build_macro_brief_system_prompt() -> str` 和 `build_macro_brief_user_prompt(user_question, context_manifest) -> str`。

system prompt 必须包含：
- 9 节固定模板（与 `docs/codex_ai_chat_page_prompt.md` 对齐）
- "已确认事实 / 判断" 两段强制结构
- "事实用显示/报道/公布，判断用说明/意味着/判断" 措辞规则
- 5 个禁止输出
- 末尾来源列表要求
- `MacroBrief` JSON schema 嵌入（function calling response_format）

**测试**：`tests/ai/test_macro_brief_prompt.py`，对 prompt 内容做关键字断言。

---

### TASK-H3：MacroBrief output parser + 校验

**新增**：`src/app_backend/services/macro_brief_parser.py`

输入 = agent 返回的 JSON 字符串 或 markdown 文本（兼容两种）。
输出 = `MacroBrief` 实例 + `ValidationResult(passed, findings[])`。

校验链：
1. JSON parse / markdown → block 拆分
2. Pydantic 校验（H1 schema）
3. 链接可达性校验（仅校验 url 形式 + 域名白名单，**不实际 HTTP 请求**）
4. 数字-来源对齐校验（每个 fact 必须有 url；判断段不得含 `[来源]` 标记）
5. 边界用语校验（禁止概率/操作建议/胜率/择时/个股关键词）

**测试**：`tests/ai/test_macro_brief_parser.py`，含 GPT 样例输出 + 当前 DeepSeek 样例输出两个 fixture（前者通过，后者按预期失败并报缺失节）。

---

## 新增 Task Group B+（B 阶段扩展）

### TASK-B6：Realtime quote service

**新增**：`src/app_backend/services/realtime_quote_service.py`

复用现有 `data_providers/` 中的 Alpha Vantage 和 FRED 通道。
**禁止**：新增 httpx 调用、新增 provider 文件。

API：
- `quote_etf(symbols: list[str]) -> list[QuoteSnapshot]`
- `treasury_curve(date: str | None = None) -> TreasuryCurveSnapshot`
- `tips_curve(date: str | None = None) -> TipsCurveSnapshot`

`QuoteSnapshot` 含 `symbol, last_price, change_pct, market_state, trading_date_us, snapshot_time_utc, source`。

`market_state` 枚举：`pre_market / regular / after_hours / closed`，必须基于美东时间计算并参照 NYSE 交易日历（用 `data/nyse_trading_calendar.json` 静态文件，由 ingest 维护）。

**测试**：`tests/ai/test_realtime_quote_service.py`，全部用 fixture，不命中网络。

---

### TASK-B7：Commodity quote 工具

**新增**：`src/app_backend/services/commodity_quote_service.py`

油价（Brent/WTI）目前没在 G2/G3 中，**走 Tavily 限定域名搜索**：
- 限定 `reuters.com`、`bloomberg.com`、`oilprice.com`
- 解析正则提取价格数字（成功率不保证 100% → 失败时返回 `unavailable` 并降级）

**测试**：`tests/ai/test_commodity_quote_service.py`，mock Tavily 返回 3 类典型新闻页 snippet。

---

## 新增 Task Group C+（C 阶段扩展）

### TASK-C3：经济日历服务

**新增**：
- `src/app_backend/services/economic_calendar_service.py`
- `scripts/ingest_economic_calendar.py` —— 每月运行一次，从 BLS/BEA/Fed 公开日历页面爬下来写入 SQLite

数据表 `economic_calendar`：
```sql
CREATE TABLE economic_calendar (
  id INTEGER PRIMARY KEY,
  event_name TEXT NOT NULL,           -- "CPI", "PCE", "FOMC", "NFP" 等
  release_date TEXT NOT NULL,         -- ISO 日期
  release_time_et TEXT,               -- "08:30 ET"
  source_url TEXT NOT NULL,
  ingest_at TEXT NOT NULL
);
```

API：
- `next_releases(window_days: int = 30) -> list[CalendarEvent]`
- `events_by_name(name: str, limit: int = 5) -> list[CalendarEvent]`

**Agent 工具注册**：`calendar_lookup`，schema 含 `window_days` 与 `event_filter`。

**测试**：`tests/ai/test_economic_calendar_service.py`，用 fixture 库；`tests/scripts/test_ingest_economic_calendar.py` 用 mock 页面。

---

## 修订 Task Group E

### TASK-E3 修订：ScenarioNarrative 字段

**修改** `src/app_backend/services/scenario_return_band_service.py`：

`ScenarioReturnBand` 输出新增 `narrative: ScenarioNarrative` 字段，含：
- `trigger_conditions: list[str]` —— "如果 X 且 Y 则进入本情景"
- `transmission_path: str` —— 一段话解释 X→Y 的传导
- `evidence_supports: bool | str` —— `True / False / "insufficient"`
- `evidence_supports_reason: str`

对应 4 个情景全部必填。

**修改** 现有 contract 测试 `tests/contracts/test_scenario_return_band_contract.py`，新增 ≥12 用例覆盖 narrative 字段。

---

## 修订 Task Group F

### TASK-F1 修订：Tool registry 增加 4 个工具

在原 6 个工具基础上新增：
| Tool | 后端服务 |
|---|---|
| `quote_etf` | `realtime_quote_service` |
| `treasury_curve` | `realtime_quote_service` |
| `commodity_quote` | `commodity_quote_service` |
| `calendar_lookup` | `economic_calendar_service` |
| `finalize_macro_brief` | 终止工具，把 MacroBrief 写入 session |

共 11 个工具。

### TASK-F3 修订：Agent runtime 强制 MacroBrief schema

**修改** `src/app_backend/services/agent_runtime.py`：

- 调用 DeepSeek 时附带 `response_format={"type": "json_schema", "json_schema": MacroBrief.model_json_schema()}`
- 注入 `macro_brief_prompt` 作为 system prompt
- 主循环最后一步必须是 `finalize_macro_brief` 工具调用
- agent 输出后过一遍 `macro_brief_parser`；校验失败则 trace 标记 `schema_violation` 并重试一次（max 1 次重试）

Budget 上调：
- `max_steps=18`（原 6）
- `max_search_calls=8`（原 3）
- `max_rag_calls=5`（不变）
- `max_tokens_total=40000`（原 20000）

**测试**：`tests/ai/test_agent_runtime_macro_brief.py`，含完整 mock loop。

### TASK-F5 替换：MacroBriefView 前端

**替换** 原 `AgentChatPage.tsx` 的渲染层。新增：

- `app_frontend/src/components/MacroBriefView.tsx` —— 9 节卡片化渲染（计划补丁 §2.6）
- `app_frontend/src/components/macro_brief/CoreConclusionCard.tsx`
- `app_frontend/src/components/macro_brief/MarketStateCard.tsx`
- `app_frontend/src/components/macro_brief/FactJudgmentCard.tsx`（§2–§6 通用）
- `app_frontend/src/components/macro_brief/ModuleTable.tsx`
- `app_frontend/src/components/macro_brief/ScenarioCardSet.tsx`
- `app_frontend/src/components/macro_brief/ForwardIndicatorTimeline.tsx`
- `app_frontend/src/components/macro_brief/SourceList.tsx`

样式规则：
- core_conclusion: 顶部高亮卡，加粗 16px
- § 1 ETF 4 卡横向布局，每卡显示价格 + 涨跌幅 + market_state 标签
- § 2–§ 6 卡片：上半"已确认事实"区（小字+source icon），下半"判断"区（正文字号）
- § 7 表用现有 `EvidenceTable` 风格
- § 8 4 卡按基准/利好/利空/系统性配色（绿/蓝/橙/红）
- § 9 时间线，每项显示距今天数（用 `currentDate=2026-06-22`）
- 末尾 source 列表带域名 favicon

`AgentChatPage.tsx` 流式渲染过程：
- agent 完成每节 → 立刻渲染该节
- 未完成节显示骨架屏
- 所有节完成 → 切换为 `MacroBriefView`

**测试**：
- `app_frontend` 不强制 unit test，但 `npx tsc --noEmit` 必须全绿
- 后端 `tests/api/test_agent_route_macro_brief.py` 含完整 mock 输出 happy path

---

## 修订 Task Group G

### TASK-G1 修订：E2E 测试新增"GPT 输出基准对照"

**新增** `tests/e2e/test_macro_brief_vs_gpt_baseline.py`：

输入：与本次对比相同的 user prompt。
fixture：mock 全部联网搜索为预录的 fixture 响应（不命中网络）。
断言：agent 输出 MacroBrief 必须满足计划补丁 §6 的 12 项验收基线全部通过。

GPT 原始输出存为 `tests/fixtures/macro_brief/gpt_baseline_2026_06_22.md`，用作 parser 测试的金样本（不要求 DS 一字一句复制，只要求节结构和验收项一致）。

---

## 修订执行顺序

```
A1 (用户审核) → A2 → A3 → B1-B5 → B6 → B7 → C1 → C2 → C3
                                                            ↘
D1 → D2 → D3 → D4
              ↘
H1 → H2 → H3                       (可与 D 并行)
              ↘
E1 (用户审核) → E2 → E3 (修订) → E4
                                  ↘
F1 (修订) → F2 → F3 (修订) → F4 → F5 (替换)
                                       ↘
G1 (修订) → G2 → G3
```

H 阶段在 D 完成前即可开始（schema 与 prompt 不依赖 RAG）。
F5 必须等 H1+H2 完成（前端依赖 MacroBrief 类型）。

---

## 验证清单（H 阶段专用追加）

- [ ] `MacroBrief` 强类型校验拒绝缺失节
- [ ] parser 能消化 GPT 样例并返回 `passed=True`
- [ ] parser 拒绝当前 DS 样例（应报缺 § 1/§ 8/§ 9）
- [ ] prompt 输出必须含 9 节模板与 5 禁止
- [ ] agent runtime 输出经 parser 校验，失败时正确重试
- [ ] 前端 9 节卡片在 fixture 数据下正确渲染
- [ ] 12 项验收基线在 mock 联网下全部通过
