# Dashboard Show All Detail

Dashboard Phase 1.3 adds a module-level detail drawer on the home dashboard. It is a read-only frontend view built from existing compact dashboard data.

## Data Sources

The drawer uses only:

- `GET /api/dashboard/summary`
- `GET /api/dashboard/evidence-table`

It does not add a backend API, does not run providers, does not run DeepSeek or Tavily, and does not read holdings CSV content.

## Drawer Sections

Each module drawer shows:

- Header with module label, module key, status, source badge, and update time.
- Status Summary from the dashboard module summary.
- Key Metrics from `modules.*.key_metrics`.
- Evidence Rows filtered from `/api/dashboard/evidence-table` by module.
- Interpretation Boundary from the dashboard financial spec.
- Missing / Research Needed rows for `missing`, `research_needed`, `insufficient_history`, `not_available`, and `stale`.
- AI Factual Context Eligibility counts and blocked reasons.

## Interpretation Boundaries

- `credit_stress`: VIX升高不是系统性危机的充分条件；信用压力模块用于区分普通回调和系统性风险，不能单独生成交易建议。
- `rate_pressure`: DGS是日度观测，不是盘中高点；5%是启发式心理阈值，不是交易信号；没有confirmed boolean不得写站稳或突破确认。
- `real_yield_pressure`: 实际利率是机制解释，不是黄金或成长股的唯一/主要驱动，不是交易信号。
- `inflation_energy_pressure`: CPI/PCE/PPI是低频数据；没有consensus不得写超预期；PPIACO不是final demand PPI；油价变化不能机械推断通胀失控。
- `equity_trend`: 指数回撤不是系统性危机的充分条件；没有breadth/concentration数据不得确认市场集中恶化。
- `portfolio_deviation`: 组合偏离不能归因于宏观市场因素；只描述风险暴露；现金备用金不参与目标配置；不得输出交易指令。

## AI Factual Context Eligibility

Rows are shown as not eligible for future AI factual context when:

- status is `missing`, `research_needed`, `insufficient_history`, `not_available`, or `stale`
- freshness is `stale`
- source badge is `search-derived`
- source is missing and the row is not local context
- both observation date and generated time are missing

The drawer may show a disabled later-phase AI Chat action, but it must not send context or call a model in this phase.

## Privacy Boundaries

The drawer must not display:

- raw market snapshot
- raw portfolio snapshot
- raw llm context pack
- holdings line items
- API keys
- raw prompts
- raw outputs
- full project root

This phase does not add charts, search, account editing, Tauri, trading suggestions, or live refresh.
