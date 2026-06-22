# Era 2 开发计划补丁 v1.1（基于 GPT vs DeepSeek 输出对比）

> 对比依据：GPT 联网搜索版输出 与 当前 DeepSeek SANITIZED 输出。
> 母文件：`docs/development_plan_ai_era_v1.md`（保留，本文件为增量调整）。
> 配套任务书：`docs/codex_task_brief_ai_era_v1_patch1.md`。

---

## 1. 差距诊断

| 维度 | GPT 输出 | 当前 DeepSeek 输出 | 差距 |
|---|---|---|---|
| 章节结构 | 0–9 共 10 节固定模板，每节有标题+小标题 | 单层"研究备忘"+5 个段落 | DS 缺固定模板与渲染锚点 |
| 实时市场数据 | SPY/QQQ/TLT/GLD 盘前报价含交易日标注 | 完全没有 | 缺实时报价工具与日期上下文 |
| 官方数据链接 | 每个关键数字配 inline markdown 链接 + 末尾汇总 | 仅 `证据来源：xxx.xxx` 内部 key 引用 | 缺联网数据 + 官方 url 注入 |
| 日期化前瞻 | 列 5 个事件，含"6 月 25 日 08:30 ET"等精确日期 | 仅泛指"需要后续证据" | 缺经济日历数据 |
| 情景分析 | 4 个独立段落（基准/利好/利空/系统性），含触发条件 | 没有情景章节 | 缺情景生成器 |
| 分模块汇总表 | 6 行 markdown 表（模块/状态/判断） | 散落在段落中 | 缺表格化输出 |
| 事实-判断分离 | 每节"已确认事实"+"判断"两段标志清楚 | 段落混杂"证据来源"标记 | 需要 prompt 模板硬性区分 |
| 边界声明 | § 8 开头一句话边界 + 末尾结论 | 末尾边界 + 反向证据段 | DS 边界更全，但位置不利于阅读 |

**核心结论**：当前 DS 的本地证据层比 GPT 的随机搜索更可信，但缺少 5 类外部信息 → 需要联网搜索补齐，并用固定输出模板把两者熔合。

---

## 2. 新增/调整项

### 2.1 新增 Phase H —— 结构化研报输出层（在 Phase E 之后插入）

**目标**：定义"宏观研报"的强类型 schema，覆盖 GPT 输出的 0–9 共 10 节，让 agent 必须按节填充。

**新增 schema**：`src/app_backend/schemas/macro_brief.py`

```python
class MacroBriefSection(str, Enum):
    CORE_CONCLUSION = "core_conclusion"        # § 0
    MARKET_STATE = "market_state"              # § 1
    INFLATION_RATES = "inflation_rates"        # § 2
    GEOPOLITICS_ENERGY = "geopolitics_energy"  # § 3
    GROWTH_LABOR = "growth_labor"              # § 4
    CREDIT_FINCOND = "credit_fincond"          # § 5
    EQUITY_MAINLINE = "equity_mainline"        # § 6
    MODULE_TABLE = "module_table"              # § 7
    SCENARIOS = "scenarios"                    # § 8
    FORWARD_INDICATORS = "forward_indicators"  # § 9

class MacroBrief:
    core_conclusion: str                       # 2-3 句加粗
    market_state: MarketStateBlock
    inflation_rates: InflationRatesBlock
    geopolitics_energy: GeopoliticsBlock
    growth_labor: GrowthLaborBlock
    credit_fincond: CreditFincondBlock
    equity_mainline: EquityMainlineBlock
    module_table: list[ModuleTableRow]         # 6 行固定
    scenarios: ScenarioSet                     # base/bull/bear/systemic 4 个
    forward_indicators: list[ForwardIndicator] # 5 个，含 release_date
    sources: list[SourceRef]                   # 末尾汇总
    boundary_notice: str                       # 强制字段
```

每个 block 都包含：`facts: list[FactStatement]`（必须含 source url）+ `judgment: str`（明确语气："说明/意味着/判断"）。

### 2.2 Phase B 增项 —— 实时市场数据工具

原 Phase B 只有 Tavily 通用搜索。新增 3 个专用工具：

| Tool | 数据源 | 输出 |
|---|---|---|
| `quote_etf` | Yahoo Finance / Alpha Vantage（已在 G2/G3） | SPY/QQQ/TLT/GLD/VIX 的 last price、change pct、market state（open/pre/post/closed）、对应交易日 |
| `treasury_curve` | Treasury XML feed | 当日 2Y/10Y/20Y/30Y 名义 + 5Y/10Y/30Y TIPS 实际利率 |
| `commodity_quote` | Tavily search → 限定 reuters.com/bloomberg.com | Brent + WTI 最新价 + 24h 变动 |

**新增**：`src/app_backend/services/realtime_quote_service.py`，复用 G2/G3 已接入的 Alpha Vantage + FRED 通道，**不走 Tavily 通用搜索**（更可靠、更便宜）。

### 2.3 Phase C 增项 —— 经济日历

GPT 能写出"6 月 25 日 08:30 ET"是因为它隐式知道发布日历。我们必须显式建：

**新增**：`src/app_backend/services/economic_calendar_service.py`
- 数据源：BLS schedule、BEA schedule、Fed FOMC calendar 三个公开页面（每月 ingest 一次）。
- 本地表 `economic_calendar(event_name, release_date, release_time_et, source_url, last_value, next_consensus)`。
- 工具 `next_releases(window_days=30)` 返回未来 30 天的关键发布。

**新增 Agent 工具**：`calendar_lookup` → § 9 前瞻指标必备。

### 2.4 Phase E 调整 —— 情景生成器结构对齐

原 E3 `scenario_return_band_service` 只输出收益区间。补充：

**修改**：`src/app_backend/services/scenario_return_band_service.py` 输出新增 `ScenarioNarrative` 字段：
```python
class ScenarioNarrative:
    scenario_name: str          # base / bullish / bearish / systemic
    trigger_conditions: list[str]   # 触发条件，明确"如果 X 则 Y"
    transmission_path: str          # 传导路径解释
    return_band: ScenarioReturnBand # 收益区间（仅当 portfolio 提供时）
    evidence_supports: bool         # 当前证据是否支持该情景成立
```

systemic 情景必须强制写"当前证据是否支持"，对齐 GPT 输出第 § 8 "证据不足"措辞。

### 2.5 Phase F 调整 —— Agent 输出强制按 MacroBrief schema

**修改** F3 Agent runtime：
- 系统 prompt 内嵌 `MacroBrief` JSON schema 作为 function-calling 的 `response_format`。
- 最后一步必须返回 `MacroBrief` 对象，否则 trace 标记 `schema_violation`。
- 新增中间步骤：每完成一节即写入 partial state，前端可流式渲染。

**新增工具**：`finalize_macro_brief(brief: MacroBrief)` —— 终止工具，agent 调用即结束 loop。

### 2.6 Phase F 前端调整 —— 9 节卡片化渲染

原 F5 `AgentChatPage.tsx` 是通用聊天。改为：

**新增组件**：`app_frontend/src/components/MacroBriefView.tsx`
- 顶部高亮卡：core_conclusion
- 9 节按顺序渲染独立卡片，每卡含"已确认事实"区块（小字+链接图标）和"判断"区块（正文字号）
- § 7 模块表用现有 `EvidenceTable` 样式
- § 8 情景 4 张卡，按 base/bull/bear/systemic 配色（绿/蓝/橙/红）
- § 9 前瞻指标用时间线组件，含 countdown（距下次发布天数）
- 末尾来源列表带 favicon

`AgentChatPage.tsx` 在 agent 完成时切换到 `MacroBriefView`，过程中显示流式进度。

### 2.7 Prompt 模板硬约束 —— 事实-判断分离

**新增**：`src/app_backend/services/macro_brief_prompt.py`

prompt 模板的强制段：
```
对每一节，必须按以下结构输出：

**已确认事实：**
- 事实1（含数字 + [来源](url)）
- 事实2

**判断：**
（一段话，必须以"说明/意味着/判断/反映"开头）
```

agent runtime 在 schema 验证时拒绝缺少 facts 或 judgment 的 block。

---

## 3. 工具调用编排（更新版）

完整宏观分析场景的 agent 调用顺序：

```
Step 1: calendar_lookup(window=30)                    → § 9 锚定
Step 2: quote_etf(["SPY","QQQ","TLT","GLD"])          → § 1
Step 3: treasury_curve(date="latest")                 → § 2
Step 4: dashboard_query("growth_inflation_context")   → § 2, § 4 本地证据
Step 5: search_tavily("FOMC June 2026 statement")     → § 2 补充
Step 6: search_tavily("CPI May 2026 release")         → § 2 补充
Step 7: commodity_quote(["BRENT","WTI"])              → § 3
Step 8: search_tavily("Hormuz Iran latest")           → § 3 新闻
Step 9: dashboard_query("liquidity_funding_stress")   → § 5
Step 10: rag_retrieve("FactSet earnings insight Q2")  → § 6
Step 11: dashboard_query("scenario_stress_matrix")    → § 8 框架
Step 12: portfolio_overlay() + scenario_return_band() → § 8 收益区间（可选）
Step 13: finalize_macro_brief(brief)                  → 结束
```

Budget 上调（原 `max_search_calls=3` 不够）：
- `max_steps=12` → `max_steps=18`
- `max_search_calls=3` → `max_search_calls=8`
- `max_tokens_total=20000` → `max_tokens_total=40000`

---

## 4. 不变项（明确保留）

- 22-flag SearchRuntimePolicy、fail-closed 守门、域名白名单 → 全部保留
- D10–D19 / Stage 8 financial semantics → 全部保留
- 禁止概率/操作建议/胜率/择时 → 全部保留（写入 MacroBrief schema 的 boundary_notice 强制字段）
- agent trace、budget 控制 → 全部保留
- 个股推荐禁令 → 保留
- 本地优先：实时报价走 Alpha Vantage/FRED（已 ingest），不依赖 Tavily 抓行情

---

## 5. 修订后阶段总览

```
A  治理与边界 (docs)              ~1 周   [不变]
B  Tavily + 实时报价/曲线工具       ~2 周   [+0.5 周]
C  分类持久化 + 经济日历             ~1.5 周 [+0.5 周]
D  RAG                            ~2 周   [不变]
E  情景区间 + ScenarioNarrative    ~1.5 周 [不变]
F  Agent + 9 节卡片化前端          ~2.5 周 [+0.5 周]
G  闭环                            ~1 周
H  结构化输出 schema + prompt 模板  ~1 周   [新增]
```

总计 ~12 周（原 ~10 周）。

---

## 6. 验收基线（用 GPT 输出当 reference）

完成 H + F5 后，agent 对"分析当前宏观环境"问题的输出必须满足：

- [ ] 含 § 0 加粗核心结论 2-3 句
- [ ] § 1 含 4 个 ETF 实时报价 + 当日交易状态
- [ ] § 2 含 CPI/PCE/FOMC/收益率/TIPS 各至少 1 个数字 + inline 链接
- [ ] § 3 含 Brent + WTI 价格 + 至少 2 个地缘事件链接
- [ ] § 4 含 NFP + 失业率 + GDP/GDPNow
- [ ] § 5 含 VIX + NFCI + 至少 1 个信用利差
- [ ] § 6 含标普盈利预期同比增长数字
- [ ] § 7 6 行模块表完整
- [ ] § 8 4 个情景独立段落，systemic 含"证据支持/不支持"措辞
- [ ] § 9 5 条前瞻，至少 4 条含精确日期
- [ ] 末尾来源列表 ≥ 10 条
- [ ] boundary_notice 含五个否定字段

未通过的项进 backlog，按差距程度排优先级。
