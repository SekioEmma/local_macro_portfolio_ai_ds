# Phase F — Agent + 9 节前端开发计划

> **当前状态（2026-07-01）**：主体实现 `implemented`；工程收口 `implementation complete; controlled live verification passed; awaiting explicit user acceptance`；用户验收 `not user_accepted`；生产可用 `not production_ready`。
> **Release gate**：以 [`docs/infra/phase_f_release_checklist.md`](infra/phase_f_release_checklist.md) 为准，必须通过 fixture controlled smoke、关键测试、人工 checklist；live controlled smoke 可手动执行 `python scripts/run_phase_f_controlled_agent_smoke.py --mode live`。
> **Historical implementation log - non-authoritative**：下方 F0–F8 内容保留为原始开发计划与实现追踪；不得再用“F0–F2 已完成，F3 开始”判断当前状态。
> **前置**：E 阶段暂停于 framework（5 个 commit 已推送，不阻塞 F）
> **依赖**：现有 `deepseek_real_transport` / `tavily_real_transport` / `RAGRetrievalService` / `dashboard_service` / `realtime_quote_service` / `economic_calendar_service` / `portfolio_engine`
> **本文档是 CLAUDE.md §Era 2 F-Phase 授权的唯一依据**

---

## 0. 目标

**给一个宏观研究问题（如"当前美国宏观环境综合评估"），agent 自动调度本地数据 + 实时报价 + 检索工具 + 联网搜索，10-18 步内产出结构化的 10 节 MacroBrief。前端流式渲染，每节完成立即显示。**

输入：自然语言问题 + 可选持仓上下文
输出：10 节固定 schema 的 MacroBrief（核心结论、市场状态、事实+判断、模块表、风险评估、前瞻指标、4 情景、来源列表、边界提示）
对比基准：用户 2026-06-29 提供的 GPT 输出（接近度目标 ≥ 75%）

---

## 1. 用户决策快照（2026-06-29 批准）

| # | 决策 | 实现要点 |
|---|---|---|
| 1 | **持仓注入策略** | 前端 toggle 默认关闭。打开后注入**真实金额 + 持仓明细**到 system prompt，前后端均增加持仓相关功能 |
| 2 | **主力 LLM** | `deepseek-v4-pro`（context 1M / output 384K / input ¥3 / output ¥6 per 1M） |
| 3 | **DXY 工具** | 新增 `quote_dxy`，从 FRED `DTWEXBGS` 读取 |
| 4 | **搜索深度** | Tavily `search_depth="advanced"`，`max_search_calls=5` |
| 5 | **升级/降级触发条件** | schema § 6 加 `upgrade_triggers` / `downgrade_triggers` |
| 6 | **AI 自判断信息缺口 → 搜索** | ReAct 模式 via function calling；prompt 强制"宁可搜，不要猜" |
| 7 | **HY OAS** | 保留手动月度，brief 标注 `as_of_month` |
| 8 | **多 provider 抽象层** | `LLMProviderAdapter` 接口，DeepSeek/Claude/GPT 三实现；当前只接 DeepSeek |

**重要边界变更**：决策 1 突破 CLAUDE.md 现有红线（"Do NOT send holdings/account/position/transaction data"）。F0 已完成 **CLAUDE.md F-Phase Holdings Exception** 条款；后续实现必须严格受该例外约束。

### 当前开发状态（2026-06-29）

- F0 治理文档前置：已完成（CLAUDE.md + GOVERNANCE.md Phase F holdings exception）。
- F1 Tool Registry：已完成到 F1-5，包含 11 工具、`quote_dxy`、dispatch redaction、8KB cap、MacroNewsRelevanceFilter。
- F2 MacroBrief Schema + Parser：已完成到 F2-3，包含 10 节 Pydantic schema、cross-section validators、`MacroBriefValidationError` parser wrapper。
- F3 Prompt 模板 + ReAct 引导：当前开发入口。

---

## 2. 必须同步更新的治理文档（F0 — 前置）

### CLAUDE.md 新增条款

```
### Era 2 Phase F Holdings Injection Exception

- The Phase F MacroBrief agent runtime (`agent_runtime.py`) MAY inject
  the user's real portfolio holdings — including ticker, share count,
  dollar amount, account name, and cost basis — into the DeepSeek
  system prompt, but ONLY when ALL of the following conditions hold:
    1. The user has explicitly toggled `include_holdings=true` in the
       frontend MacroBrief request UI.
    2. The toggle is OFF by default and is not persisted across logout.
    3. The agent_trace_service.py records `holdings_included=true` and
       `holdings_snapshot_sha256` in the session trace.
    4. The injection happens server-side; raw holdings never reach the
       browser console or network response visible to the user.
- This exception applies only to `agent_runtime.py` and only when invoked
  through `/api/agent/run`. All other AI endpoints (research-deepseek,
  preview-*, context-preview) remain forbidden from receiving holdings.
- Transaction history, order book, and raw provider account responses
  remain forbidden in all paths.
```

### GOVERNANCE.md 新增章节

收益区间 / 投资判断章节需写明：

1. MacroBrief 五个否定关键词：**非个股操作 / 非概率胜率 / 非收益预测 / 非动态择时 / 非黑盒最优化**
2. Holdings 注入审计要求：每个 session 必须可通过 trace 复盘是否注入持仓
3. Agent budget 上限（max_steps=18, max_search_calls=5, max_rag_calls=5, max_tokens_total=40000）

---

## 3. 技术栈（零新依赖）

| 层 | 技术 | 状态 |
|---|---|---|
| LLM | `deepseek-v4-pro`（OpenAI 兼容 schema）| ⚠️ 需在 `deepseek_real_transport` 加 `tool_calls` 解析 |
| Provider 抽象 | `LLMProviderAdapter` interface（DeepSeek/Claude/GPT 三实现，当前只接 DeepSeek） | ❌ 新建 |
| Agent runtime | 自研 200 行主循环，不用 LangChain/CrewAI | ❌ 新建 |
| Schema 校验 | Pydantic v2（项目标准）| ✅ |
| Trace | JSONL → `outputs/agent_traces/<session_id>.jsonl` | ❌ 新建 |
| 后端 API | FastAPI POST `/api/agent/run` SSE 流式 | ✅ 栈现成 |
| 前端 | React 18 + Vite 5 + TS 5.5（SSE）| ✅ 栈现成 |
| 安全 guard | `ai_external_runtime_policy` + `SearchRuntimePolicy` + `guard_response` | ✅ 复用 |

**为什么不用 LangChain / LlamaIndex / CrewAI**：
1. 11 工具规模小，主循环 < 200 行
2. 22 旗 runtime policy + 域名白名单 + budget 与这些框架的安全模型不兼容
3. 学习价值：手写 function calling 比框架黑盒更能掌握本质
4. 调试可控：每一步 tool call / token / cost 完全透明

---

## 4. 11 工具清单

| Tool | 后端调用 | 数据范围 | 安全约束 |
|---|---|---|---|
| `dashboard_query` | `dashboard_service.build_dashboard_summary` | 本地 dashboard 摘要 | 无外部网络 |
| `evidence_lookup` | `dashboard_service.build_evidence_table` | 本地 evidence 表 | 无外部网络 |
| `search_tavily` | `TavilySearchExecutionService.execute` | Tavily 域名白名单 | `confirm_external_search=True`，sanitizer + budget |
| `rag_retrieve` | `RAGRetrievalService` | 本地 4428 chunks（73 治理 + 28 MEMO）| `external_llm_context_allowed=True` 过滤 |
| `quote_etf` | `RealtimeQuoteService.get_etf_quote` | SPY/QQQ/SHY/GLD 等 | 复用 B5 read-only 路径 |
| `treasury_curve` | `RealtimeQuoteService.get_treasury_curve` | DGS 系列 | 复用 B5 read-only 路径 |
| `quote_dxy` ⭐ | 新增；FRED `DTWEXBGS` | 美元指数（广义贸易加权）| 复用 fred_provider，read-only |
| `commodity_quote` | `CommodityQuoteService` | Reuters/Bloomberg/Oilprice 三域 | 复用 B6 |
| `calendar_lookup` | `EconomicCalendarService` | 本地经济日历 SQLite | 无外部网络 |
| `portfolio_overlay` | `portfolio_engine.compute_overlay` | 本地持仓 overlay | **不通过 LLM 暴露持仓金额**，仅返回偏差摘要 |
| `finalize_macro_brief` | 终止信号（无后端实现）| — | agent 调用此工具即停止主循环 |

⭐ = 本阶段新增

---

## 5. 10 节 MacroBrief Schema

| § | 节名 | Pydantic 字段 | 强制规则 |
|---|---|---|---|
| 1 | `core_conclusion` | `str` | 段落叙述，禁含数字以外的概率词（"X% 概率"）|
| 2 | `market_state` | `list[ETFStateCard]` | 4 ETF（SPY/QQQ/SHY/GLD），每张含 price + change + as_of |
| 3 | `confirmed_facts` | `list[ConfirmedFact]` | 每条含 `value` + `source_id` + `as_of` |
| 4 | `judgments` | `list[Judgment]` | 每条 `claim` + `evidence_supports: list[fact_id]`（至少 1）|
| 5 | `module_table` | `list[ModuleRow]` × **恰好 6** | 6 行固定：权益趋势 / 利率压力 / 真实利率压力 / 通胀能源 / 信用压力 / 地缘风险；status ∈ {`benign`,`watch`,`pressure`,`stress`,`crisis`} |
| 6 | `risk_assessment` | `RiskAssessment` | 含 `current_label` + **`upgrade_triggers: list[str]`** + **`downgrade_triggers: list[str]`** ⭐ |
| 7 | `forward_indicators` | `list[ForwardIndicator]` × **恰好 5** | 每条 `name` + `release_date` + `relevance` |
| 8 | `scenarios` | `dict[ScenarioKey, ScenarioBlock]` × **恰好 4 键** | base/bullish/bearish/systemic；每块含 `trigger_conditions` + `transmission_path` |
| 9 | `source_list` | `list[SourceItem]` | 每条 `id` + (`url` 或 `rag_doc_id`) + `accessed_at` |
| 10 | `boundary_notice` | `str` | 必须含 5 关键词（validator 强制）：非个股操作 / 非概率胜率 / 非收益预测 / 非动态择时 / 非黑盒最优化 |

⭐ = 决策 5 新增

**校验失败处理**：抛 `MacroBriefValidationError`，agent 自动重试 1 次，把 validation error 文本回传给 LLM。

---

## 6. ReAct 主循环（决策 6 核心）

```python
# 伪代码
def run_agent(user_question: str, include_holdings: bool) -> MacroBrief:
    messages = [
        system_prompt(include_holdings_snapshot if include_holdings else None),
        user_prompt(user_question),
    ]
    budget = AgentBudget(max_steps=18, max_search=5, max_rag=5, max_tokens=40000)

    for step in range(budget.max_steps):
        response = provider.chat(
            model="deepseek-v4-pro",
            messages=messages,
            tools=tool_registry.openai_schema(),
            tool_choice="auto",
        )
        budget.consume_tokens(response.usage)

        if response.tool_calls:
            for call in response.tool_calls:
                if call.name == "finalize_macro_brief":
                    return parse_brief(call.arguments)
                budget.check(call.name)  # raises BudgetExceeded
                result = tool_registry.dispatch(call)
                messages.append({"role": "tool", "tool_call_id": call.id,
                                 "content": json.dumps(result)[:8000]})
            continue

        if budget.exhausted():
            messages.append({"role": "user",
                             "content": "Budget exhausted. Call finalize_macro_brief now."})
            continue

        # LLM returned plain text without tool_calls → force finalize
        break

    raise AgentIncomplete("Agent did not call finalize_macro_brief")
```

**Prompt 引导关键句**：

```
你的任务是产出一份 10 节 MacroBrief。
- 若某节信息不足，必须调 search_tavily 或 rag_retrieve 补充；禁止用通用知识猜测最新数字
- 每个数字必须在 § 9 source_list 中有对应来源
- 事实必须先于判断；judgment 必须引用 confirmed_fact 的 id
- 完成后必须调用 finalize_macro_brief（这是唯一退出方式）
```

---

## 7. 安全约束矩阵

| 红线 | F 阶段表现 |
|---|---|
| 不新增 `/api/chat` / `/api/ai/deepseek` / `/api/ai/external` 路由 | Agent 用 `/api/agent/run` 新路径 |
| 不直接调 `httpx`/`requests` | 复用 `deepseek_real_transport` + `tavily_real_transport` |
| 不 hardcode 22 旗 runtime policy | 沿用 `_build_runtime_policy` 派生模式 |
| **Holdings 默认不送外部** | toggle 开启 + trace 记录 + UI 警示 |
| 不广播 AI Context Manifest | Agent 用 tool result 替代，不读 manifest |
| 工具结果含 secrets/paths/raw provider payload | Tool handler 一律 redact 后再返 LLM |
| Search query 含原 question | 走 `query_sanitizer`（已有）|
| 不能 weaken `guard_response` | `external_model_called=True` 时 guard 必须能 fail-closed |
| 不再 hardcode AI-2 runtime policy gates | F4 abstraction 保持 derived-from-state |

---

## 8. 7 段开发计划

总计 **26 commit / ~50 小时编码 / 5-7 周完成**。每段独立测试 + commit，可暂停。

### F0 — 治理文档前置（2 commit / ~1h）

| Commit | 文件 | 内容 |
|---|---|---|
| F0-1 | `CLAUDE.md` | 加 F-Phase Holdings Injection Exception 条款（§2）|
| F0-2 | `docs/GOVERNANCE.md` | 加 MacroBrief 五否定 + holdings 审计 + budget |

**验收**：用户阅读条款并确认；后续 F1+ 必须严格按此条款实现。

---

### F1 — Tool Registry（5 commit / ~6h）

| Commit | 文件 | 内容 |
|---|---|---|
| F1-1 | `agent_tool_registry.py` 骨架 + 5 只读工具 | `dashboard_query` / `evidence_lookup` / `quote_etf` / `treasury_curve` / `calendar_lookup` |
| F1-2 | + 网络工具 3 个 | `search_tavily` / `rag_retrieve` / `commodity_quote` |
| F1-3 | + 持仓 + 新增 + 终止 3 个 | `portfolio_overlay` / `quote_dxy` ⭐ / `finalize_macro_brief` |
| F1-4 | 工具结果 redact + 8KB 截断 + JSON-serializable 强制 | 防止 secrets / pydantic 对象进 LLM |
| F1-5 ⭐ | `MacroNewsRelevanceFilter` 内嵌 `search_tavily` handler | 借鉴 TradingAgents-CN 规则过滤；24h 内 +25 分；高价值词 +15；投机性词 -10；信任域名加分 |

⭐ = 借鉴外部项目（见 §13）

**`MacroNewsRelevanceFilter` 核心逻辑**：

```python
HIGH_VALUE = ["fed", "fomc", "pce", "cpi", "treasury", "powell",
              "rate cut", "rate hike", "hy oas", "yield curve"]
MEDIUM_VALUE = ["stock", "bond", "spread", "vix", "dollar", "oil"]
SPECULATION = ["expert says", "could rise", "analyst predicts",
                "forecast", "may surge", "set to"]
TRUSTED_DOMAIN = {"reuters.com": 15, "bloomberg.com": 15,
                  "wsj.com": 12, "ft.com": 12, "federalreserve.gov": 20,
                  "bls.gov": 18, "bea.gov": 18, "fred.stlouisfed.org": 18}

def score(title, snippet, url, published_at) -> int:
    score = 0
    if (now - published_at).days < 1: score += 25
    elif (now - published_at).days < 7: score += 15
    for kw in HIGH_VALUE:
        if kw in title.lower(): score += 15
        elif kw in snippet.lower(): score += 8
    for kw in MEDIUM_VALUE:
        if kw in title.lower(): score += 6
    for kw in SPECULATION:
        if kw in title.lower(): score -= 10
    score += TRUSTED_DOMAIN.get(extract_domain(url), 0)
    return max(0, min(100, score))

# 默认阈值 30；低于阈值的结果不返回给 LLM
```

**关键设计**：
- 每个 `ToolSpec`：`name` / `description` / `parameters_schema` / `handler`
- Handler 输入：dict；输出：JSON-serializable dict
- 异常包成 `{"status": "error", "code": "...", "message": "..."}` 返给 LLM（不抛）
- `quote_dxy`：FRED `DTWEXBGS` 月末值；和 `quote_etf` 共享 `RealtimeQuoteService`

**测试**：
- Schema 符合 OpenAI function calling JSON Schema 规范
- 每工具 1-2 个单测（mock 底层 service，验参数透传 + 异常包装）
- Redact 单测：注入含 API key / 本地路径 / SHA-256 hash 的假结果，验证已脱敏

---

### F2 — MacroBrief Schema + Parser（3 commit / ~4h）

| Commit | 文件 | 内容 |
|---|---|---|
| F2-1 | `src/app_backend/schemas/macro_brief.py` | 10 节 Pydantic 模型 + Literal 约束 |
| F2-2 | + 自定义 validator | 6 行模块表、4 键情景、5 关键词边界、5 条前瞻指标 + release_date |
| F2-3 | `macro_brief_parser.py` | LLM 输出 JSON → Pydantic 校验 + `MacroBriefValidationError`（含 missing/error 列表）|

**关键 validator**：
- `module_table` 必须包含 6 个固定 `module_key`（权益趋势 / 利率压力 / 真实利率压力 / 通胀能源 / 信用压力 / 地缘风险）
- `scenarios` 必须有且仅有 4 键（`base` / `bullish` / `bearish` / `systemic`）
- `forward_indicators` 长度 = 5，每条 `release_date` 必须是 ISO date
- `boundary_notice` 必须 substring 包含 5 关键词
- `judgments[*].evidence_supports` 非空，且每个 id 必须在 `confirmed_facts[*].id` 中存在

**测试**：
- 合规 brief → pass
- 每条 validator 单独失败 → 对应 error
- 数字 + source_id 交叉引用一致性

---

### F3 — Prompt 模板 + ReAct 引导（4 commit / ~6h）

| Commit | 文件 | 内容 |
|---|---|---|
| F3-1 ⭐ | `macro_brief_prompt.py` 元 system prompt 框架 | `current_date` + `tool_names` + `instrument_context` + 终止信号（借鉴 TradingAgents）+ 10 节 schema |
| F3-2 ⭐ | + 反幻觉 5 条规则 + 反保守偏好 prompt | 借鉴 TradingAgents market_analyst + research_manager |
| F3-3 | + Few-shot reference brief | 1-2 个脱敏的参考 brief（参考用户 2026-06-29 GPT 输出格式）|
| F3-4 | + ReAct 引导句 + holdings 注入逻辑 | "宁可搜不要猜" + holdings snapshot 拼接 |

⭐ = 借鉴外部项目（见 §13）

**元 system prompt 框架（F3-1，借鉴 TradingAgents）**：

```
You are a senior macro strategist producing a single-shot research brief.

Today's date is {current_date}; treat it as 'now' for all analysis
and tool-call date ranges.

You have access to these tools: {tool_names}.

{user_holdings_context}   # 仅在 include_holdings=true 时注入

Your output MUST be valid JSON matching the MacroBrief schema (10 sections).
You MUST call finalize_macro_brief() to terminate — this is the only exit.

If information is insufficient, call search_tavily or rag_retrieve.
NEVER guess from training knowledge for any post-2025 data.

<schema>...10 节 JSON schema...</schema>
<reference_brief>...few-shot 例子（F3-3 加入）...</reference_brief>
```

**反幻觉 5 条规则（F3-2，借鉴 TradingAgents market_analyst）**：

```
For every numerical claim in your brief:

1. The number MUST originate from a tool call result
   (quote_etf, treasury_curve, search_tavily, rag_retrieve, etc.)

2. The number MUST be referenced in section 9 (source_list) by source_id.

3. If two tool outputs conflict, write both in confirmed_facts and
   FLAG the discrepancy in judgments. Do NOT silently reconcile.

4. Do NOT cite specific percentages, dates, or price levels unless
   they appear in a tool output. Use qualitative language otherwise.

5. Do NOT claim "historically X has led to Y" unless rag_retrieve
   returned evidence with specific dates.
```

**反保守偏好 prompt（F3-2，借鉴 TradingAgents research_manager）**：

```
For each row in module_table (§5):
- Commit to the clearest status the evidence supports
- Reserve 'watch' for situations where evidence is genuinely mixed
- Reserve 'crisis' for documented systemic events (2008 Sep, 2020 Mar)
- Do NOT default to 'watch' as a safe middle ground

For scenarios (§8):
- 'base' scenario should reflect the most evidence-supported path,
  not the "middle" between bullish and bearish
- Each scenario must have non-trivial trigger_conditions distinct from
  base case
```

**绝对禁止（保留）**：

```
<absolute_prohibitions>
  1. 禁止个股操作建议
  2. 禁止概率胜率（"X% 概率"）
  3. 禁止收益预测（"预期收益 X%"）
  4. 禁止动态择时
  5. 禁止黑盒最优化
</absolute_prohibitions>
```

**Holdings 注入格式**：
```
用户当前持仓（用户已显式同意发送给 LLM）：
- SPY: 250 股 / $182,247（账户 IBKR-US）
- QQQ: 100 股 / $70,652（账户 IBKR-US）
- SHY: 800 股 / $65,432（账户 IBKR-US）
- GLD: 150 股 / $35,891（账户 IBKR-US）
- 总市值: $354,222
- 资产类别比例: 51.4% SPY / 19.9% QQQ / 18.5% SHY / 10.1% GLD
- 计价货币: 人民币（QDII 净值规则）
```

**测试**：
- Prompt 总 byte < 8000（留 context 给 tool result）
- 5 个禁止词在 system prompt 中出现
- response_format 字段正确
- Holdings 注入仅在 toggle=true 时出现

---

### F4 — DeepSeek + Provider 抽象层（3 commit / ~5h）

| Commit | 文件 | 内容 |
|---|---|---|
| F4-1 | `LLMProviderAdapter` 接口 + `DeepSeekProviderAdapter` 实现 | 抽象 chat / function calling / streaming / token usage |
| F4-2 | 扩 `deepseek_real_transport.py` | 加 `tools` / `tool_choice` 参数；解析 `tool_calls` 数组；多轮 message history |
| F4-3 | Claude/GPT adapter skeleton（不接真实 API）| 接口实现 + `NotImplementedError` 占位；future-proof |

**Provider 抽象 schema**：

```python
class LLMProviderAdapter(Protocol):
    name: Literal["deepseek", "claude", "gpt"]
    def chat(
        self,
        model: str,
        messages: list[Message],
        tools: list[ToolSpec] | None,
        tool_choice: str = "auto",
        response_format: dict | None = None,
        max_tokens: int = 4000,
    ) -> ChatResponse: ...

    def stream_chat(self, ...) -> Iterator[ChatChunk]: ...

class ChatResponse(BaseModel):
    content: str | None
    tool_calls: list[ToolCall]
    usage: TokenUsage
    finish_reason: Literal["stop", "tool_calls", "length", "content_filter"]
```

**测试**：
- DeepSeek transport：mock + 真实 transport 各跑一次
- Multi-turn：user → assistant tool_calls → tool result → assistant content
- tool_calls JSON 解析失败的 graceful degradation
- 22 旗 runtime policy guard 仍在请求路径上

---

### F5 — Agent Runtime（5 commit / ~11h，核心）

| Commit | 文件 | 内容 |
|---|---|---|
| F5-1 | `agent_runtime.py` 主循环骨架 | dispatch loop + budget + 终止条件 |
| F5-2 | `AgentBudget` + 降级策略 | 各类 budget 单独 enforcement + 退化策略 |
| F5-3 | 重试逻辑 + brief 校验集成 | Brief 校验失败 → 1 次重试（附 error 给 LLM）|
| F5-4 | 异常处理 + 工具失败容忍 | 工具单次失败重试 → 连续 3 次失败 disable + warning |
| F5-5 ⭐ | 两阶段模式开关（research → writing） | 借鉴 TradingAgents trader 模式；默认开启，budget tight 可关 |

⭐ = 借鉴外部项目（见 §13）

**两阶段模式（F5-5）**：

```
阶段 1（research）：步数 1 .. N-1
  - System prompt: 元框架 + 反幻觉规则 + "调用工具收集信息"
  - Tools 全部可用
  - LLM 一边调工具一边累积上下文，但 NOT 写 brief

阶段 2（writing）：步数 N（最后一步）
  - System prompt 切换为 "基于上面 messages 中的所有 tool result，
    立即调用 finalize_macro_brief 生成完整 10 节 brief"
  - Tools 只保留 finalize_macro_brief
  - LLM 强制收敛到结构化输出

切换触发条件（满足任一）：
- 剩余 budget < 30%
- 步数已达 max_steps - 2
- LLM 连续 2 步无 tool_calls（认为信息已收集完）
- 用户传 force_writing_phase=true
```

**两阶段配置**：

```python
@dataclass
class AgentRuntimeConfig:
    two_phase_mode: bool = True       # 默认开启
    research_max_steps: int = 12      # 阶段 1 上限
    writing_max_steps: int = 2        # 阶段 2 上限（重试 1 次）
```

**好处**：
- 分析和写作责任分离，brief 结构化输出质量提升
- 收尾确定性更强（不依赖 LLM 自决定何时 finalize）
- 调试可观测（trace 明确标记 phase 切换）

**坏处**：
- 步数 +1 ~ +2
- Token 略增（writing 阶段重新拼 system prompt）

**AgentBudget**：

```python
@dataclass
class AgentBudget:
    max_steps: int = 18
    max_search_calls: int = 5
    max_rag_calls: int = 5
    max_tokens_total: int = 40000
    consumed_steps: int = 0
    consumed_search: int = 0
    consumed_rag: int = 0
    consumed_tokens: int = 0

    def check(self, tool_name: str) -> None:
        if tool_name == "search_tavily" and self.consumed_search >= self.max_search_calls:
            raise BudgetExceeded("max_search_calls")
        # ...
```

**降级策略矩阵**：

| 触发 | 行为 |
|---|---|
| Budget exhausted | 注入 user message "调 finalize 立即结束"，强制下一步收敛 |
| 工具单次失败 | 返回 `{"status": "error", "message": ...}`，agent 自决定 |
| 工具连续 3 次失败 | 标记 disabled，从 tool list 移除，继续 |
| Brief 校验失败 第 1 次 | 注入校验错误，重试 1 次 |
| Brief 校验失败 第 2 次 | 返回 partial brief + warning 给前端 |
| Provider API 5xx | 重试 2 次，指数 backoff |
| Provider API 4xx（非 rate limit）| 立即失败，trace 记录 |

**测试**：
- Mock LLM 返回固定 tool call 序列，验证 dispatch
- Budget 各类型独立 trigger
- 重试逻辑 + 二次失败行为
- 工具 disable 触发后 brief 仍能完成

---

### F6 — Trace 与可观测性（2 commit / ~3h）

| Commit | 文件 | 内容 |
|---|---|---|
| F6-1 | `agent_trace_service.py` + JSONL 写入 | 每事件一行，session_id 命名 |
| F6-2 | Sensitive data 过滤 + 可重放接口 | grep guard + replay 函数 |

**Trace event schema**：

```jsonl
{"ts": "...", "type": "session_start", "session_id": "...", "user_question_sha256": "...", "holdings_included": false, "holdings_snapshot_sha256": null}
{"ts": "...", "type": "tool_call", "step": 1, "tool": "dashboard_query", "args_summary": {...}}
{"ts": "...", "type": "tool_result", "step": 1, "duration_ms": 142, "status": "ok"}
{"ts": "...", "type": "llm_completion", "step": 2, "tokens_in": 1234, "tokens_out": 567, "cost_cny": 0.012}
{"ts": "...", "type": "brief_validation", "attempt": 1, "status": "ok"}
{"ts": "...", "type": "session_end", "final_status": "ok", "total_cost_cny": 0.05}
```

**绝对不记录**：
- raw prompt 全文
- raw LLM response 全文
- API key
- 持仓详细金额（仅记 sha256 hash）
- search query 全文（仅记 sanitized 后的 sha256）
- 引用 URL **会**记录（合规要求）

**测试**：
- Trace 文件大小 < 100KB / session
- 自动 grep 检查不含敏感字段
- replay：从 trace 重建 messages history → debug 模式

---

### F7 — 前端 + API + 持仓 toggle（7 commit / ~15h）

| Commit | 文件 | 内容 |
|---|---|---|
| F7-1 | `POST /api/agent/run` SSE 流式 endpoint | 每节完成发一个 SSE event |
| F7-2 | `GET /api/agent/trace/<session_id>` debug endpoint | 读 trace 给前端 |
| F7-3 | TypeScript types 与 Pydantic schema 对齐 | `app_frontend/src/types/macro_brief.ts` |
| F7-4 | `MacroBriefView.tsx` 顶层 + 持仓 toggle UI | 默认关闭 + 警示文案 + localStorage 偏好（不持久化登录态）|
| F7-5 | 子组件：`CoreConclusionCard` / `MarketStateCard` / `FactJudgmentCard` | 流式接入 |
| F7-6 | 子组件：`ModuleTable` / `ScenarioCardSet`（4 色）/ `ForwardIndicatorTimeline`（含距今天数）| 表格 + 时间轴 |
| F7-7 | 子组件：`SourceList` / `BoundaryNoticeBanner` + skeleton loaders | 完成 brief 展示 + 移动端 `compact` prop |

**前端 toggle UI 设计**：

```
┌─────────────────────────────────────────────┐
│ 生成 Macro Brief                             │
│ ┌─────────────────────────────────────────┐ │
│ │ 输入研究问题...                          │ │
│ └─────────────────────────────────────────┘ │
│                                             │
│ [⚠️] □ 使用我的真实持仓（默认关闭）          │
│      勾选后，你的持仓股数、金额、账户        │
│      名称将被发送给 DeepSeek。每次会话       │
│      独立确认，不会跨会话记住。              │
│                                             │
│              [ 生成 Brief ]                  │
└─────────────────────────────────────────────┘
```

**测试**：
- SSE 流式：brief 部分失败时正确推送 error event
- 每个 Card 单测（render with mock data）
- E2E：从 user prompt → 看到完整 brief（手动验收）
- 持仓 toggle：默认 false + localStorage 不持久化登录

---

## 9. 验收基线

完成 F 后，agent 对 **"分析当前美国宏观环境，未来 3 个月组合该如何看待"** 必须输出：

| 验收项 | 目标 |
|---|---|
| 10 节齐全 + schema 校验 pass | 100% |
| § 5 模块表恰好 6 行 + 每行有 evidence 引用 | 100% |
| § 8 4 情景齐全 + 每情景有 trigger_conditions | 100% |
| § 7 5 条前瞻指标 + 每条 release_date | 100% |
| § 10 边界提示含 5 关键词 | 100% |
| 总 tokens < 40000 | 95% 的请求 |
| 总步数 < 18 | 95% 的请求 |
| 总成本 < ¥1（约 $0.15） | 95% 的请求 |
| 完整 trace 可查 | 100% |
| 接近度（用户主观打分 vs 2026-06-29 GPT 输出） | ≥ 75% |

---

## 10. 风险与缓解

| 风险 | 概率 | 缓解 |
|---|---|---|
| DeepSeek-V4 function calling 行为与 OpenAI 不完全一致 | 中 | F4-2 mock + 真实 transport 都测；保留向后兼容旧 API |
| LLM 过度搜索（每个细节都搜）| 中 | Budget enforcement + prompt 引导 "1 个搜索覆盖多个问题" |
| LLM 不搜直接用训练知识 | 高 | Prompt 强制 + 后处理校验每数字是否在 source_list |
| Brief 校验失败重试也失败 | 低 | F5-3 partial brief + warning 给前端 |
| 持仓泄露到 trace / 日志 / 前端控制台 | 高（影响大）| F6-1 grep guard 自动检查 + 服务端 redact + 端到端审计 |
| 跨会话 toggle 误打开 | 中 | F7-4 localStorage 不持久化登录态，每次会话独立确认 |
| 搜索结果质量差导致 brief 不准 | 中 | Tavily 域名白名单 + advanced search + RAG 优先 |
| F4 抽象层导致 DeepSeek 实现复杂 | 低 | Skeleton 模式，Claude/GPT 留空，只接 DeepSeek |
| 成本失控（用户高频调用）| 低 | Budget enforce 单次 ≤ ¥1；前端可加每日上限 |

---

## 11. 开发前置 checklist（历史记录，已由 release gate 取代）

本节及上方 F0-F8 开发计划均为 Historical implementation log - non-authoritative。
它们保留原 F1 编码前置项的历史意图，但不再作为当前 Phase F 的发布状态来源。
当前 authoritative release gate 以
[`docs/infra/phase_f_release_checklist.md`](infra/phase_f_release_checklist.md)
和 [`docs/infra/phase_f_dod_audit.md`](infra/phase_f_dod_audit.md) 为准。

| 原前置项 | 当前处置 |
|---|---|
| 本文档推送到 `app-mvp` 并获用户批准 | 已进入实现后 remediation；用户验收仍保持 `not user_accepted`，由 release checklist 人工确认 |
| CLAUDE.md F-Phase Holdings Injection Exception | 治理权威已迁移到 `GOVERNANCE.md` 与 ADR-0002；`CLAUDE.md` 不再作为新增治理例外的权威来源 |
| GOVERNANCE.md MacroBrief 5 否定 + holdings 审计 + budget | 由 `GOVERNANCE.md`、ADR-0002、ADR-0004、ADR-0005 与 release checklist 覆盖 |
| DeepSeek API key 已配置在 `.env` | 私有运行环境事项；fixture release gate 不依赖 `.env`，live controlled smoke 仅在用户批准后手动执行 |
| Tavily API key 已配置 | 本轮 Phase F release gate 不启用 Tavily、后台搜索或自动搜索 |
| RAG chunks 已灌入 | 由 RAG generation contract、BM25/vector 一致性测试与 `validate_local_rag.py` 验证取代固定 chunk 数字 |
| FRED `DTWEXBGS` 本地历史确认可用 | 由当前数据 provider / unavailable 语义与受控 run 证据取代单一前置检查 |
| 用户阅读并理解 holdings 注入风险 | 保留为 release checklist 的人工验收项；在此之前状态不得提升为 `user_accepted` |

---

## 12. 时间预算

| 段 | Commit | 估算 |
|---|---|---|
| F0 治理 | 2 | 1h |
| F1 工具注册（含 news filter）| 5 | 6h |
| F2 Schema | 3 | 4h |
| F3 Prompt（含元框架 + 反幻觉 + 反保守偏好）| 4 | 6h |
| F4 Provider 抽象 | 3 | 5h |
| F5 Agent runtime（含两阶段模式）| 5 | 11h |
| F6 Trace | 2 | 3h |
| F7 前端 + API | 7 | 15h |
| 调试 + 验收 | — | 5h |
| **合计** | **31** | **~56h** |

按每周 10h 节奏，约 **5-7 周完成**。

---

## 13. 借鉴的外部项目

本计划在以下 5 处借鉴了 TauricResearch/TradingAgents（Apache 2.0）和
hsliuping/TradingAgents-CN（部分 Apache 2.0）的设计。借鉴方式为
**思想 / 接口模式**，不直接复制代码。

### 借鉴点清单

| 借鉴点 | 来源 | 应用位置 | 标记 |
|---|---|---|---|
| 元 system prompt 框架（`current_date` / `tool_names` / `instrument_context` / 终止信号） | TauricResearch/TradingAgents `tradingagents/agents/analysts/news_analyst.py` 等所有 agent | F3-1 | ⭐ |
| 反幻觉 5 条规则（source-of-truth 强制、冲突 flag 不调和、不许 claim 无证据数据） | TauricResearch/TradingAgents `tradingagents/agents/analysts/market_analyst.py` | F3-2 | ⭐ |
| 反保守偏好 prompt（不许默认选 'watch'/'Hold'） | TauricResearch/TradingAgents `tradingagents/agents/managers/research_manager.py` | F3-2 | ⭐ |
| 两阶段模式（research → writing 责任分离） | TauricResearch/TradingAgents `tradingagents/agents/trader/trader.py`（trader 不再调工具，专门做最终输出） | F5-5 | ⭐ |
| 新闻规则过滤评分（关键词加分 / 投机词扣分 / 信任域名加权） | hsliuping/TradingAgents-CN `docs/features/NEWS_FILTERING_SOLUTION_DESIGN.md` 方案 1 | F1-5 | ⭐ |

### 没有借鉴（明确决策）

| 不借鉴 | 来源 | 原因 |
|---|---|---|
| LangGraph state machine | TradingAgents 全栈使用 | 与 22 旗 runtime policy + budget enforcement 不兼容 |
| 多 agent debate / bull/bear researcher | TradingAgents `agents/researchers/` | 延后到 Phase I（era2_plan §11）|
| BUY/HOLD/SELL 终止信号 | TradingAgents 共用元 prompt | 硬约束"非个股操作" |
| Sentence-transformers 语义新闻分类 | TradingAgents-CN 方案 2 | 规则过滤足够；语义检索由 RAG 承担 |
| Transformers 中文新闻分类器 | TradingAgents-CN 方案 3 | 过度工程；增加 ~500MB 模型依赖 |
| Reddit / StockTwits 数据 | TradingAgents `dataflows/` | 噪音大，不符合 reuters/bls/bea/fred 白名单 |
| MongoDB / Redis 双库 | TradingAgents-CN | 单用户 SQLite 够用 |
| 多用户权限管理 / 配置中心 | TradingAgents-CN | 单用户场景不需要 |

### License 合规

- **TauricResearch/TradingAgents**：Apache 2.0，可读源码、可借鉴思想、可改写
- **hsliuping/TradingAgents-CN**：核心 `app/` 和 `frontend/` 商业授权，其他 Apache 2.0。**本计划仅借鉴 `docs/` 设计文档思想，不复制 `app/` 或 `frontend/` 代码**
- **本项目代码**：自研，不 fork 任何外部 repo

---

## 14. 后续可选升级（不在 F 阶段范围）

以下功能在完成 F 阶段 baseline 后，可在 Phase H / I 评估引入：

- **Bull/Bear 辩论模式**（Phase I）：参考 TradingAgents `bull_researcher` + `bear_researcher` + `research_manager` 三段式
- **Risk manager reflection step**（Phase I）：参考 TradingAgents `risk_mgmt/` 三档辩论
- **语义新闻过滤**（Phase H 优化）：在规则过滤基础上叠加 sentence-transformers
- **多模型 A/B 评估**（Phase H）：DeepSeek vs Claude vs GPT 在同一 brief 任务上对比

---

*本文档保留 Phase F baseline 设计与历史实施计划。2026-07-01 之后的当前状态、发布门禁与人工验收，以 release checklist、DoD audit、GOVERNANCE 与 ADR 为准；Phase F 工程收口为 `implementation complete; controlled live verification passed; awaiting explicit user acceptance`，尚未 `user_accepted` / `production_ready`。*
