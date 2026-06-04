# Dashboard Financial Spec v1

## Positioning

Dashboard v1 is a risk monitoring and evidence panel for a local macro portfolio app. It is not a trading system and must not present buy/sell instructions.

The first screen shows compact evidence only. It should make missing, stale, research-needed, and insufficient-history states explicit instead of displaying unexplained placeholders.

## Fixed Modules

- `credit_stress`
- `rate_pressure`
- `real_yield_pressure`
- `inflation_energy_pressure`
- `equity_trend`
- `portfolio_deviation`

## DashboardMetric

Each module exposes 3 to 5 key metrics. A metric has:

- `metric_key`
- `display_name`
- `value`
- `value_text`
- `unit`
- `status`
- `source`
- `source_badge`
- `observation_date`
- `generated_at`
- `freshness_status`
- `missing_reason`
- `interpretation_hint`
- `ai_context_allowed`

Allowed metric statuses:

- `ok`
- `watch`
- `pressure`
- `stress`
- `missing`
- `stale`
- `unknown`
- `research_needed`
- `insufficient_history`
- `not_available`

Allowed source badges:

- `official`
- `official_fallback`
- `unofficial_fallback`
- `proxy`
- `search-derived`
- `missing`
- `research_needed`
- `local`
- `derived`

## Home Key Metrics

`credit_stress`

- `high_yield_spread`
- `investment_grade_spread`
- `vix`
- `credit_stress_status`

`rate_pressure`

- `dgs10`
- `dgs30`
- `dgs30_distance_to_5pct`
- `dgs10_5d_avg`
- `dgs30_breakout_confirmed`

`real_yield_pressure`

- `dfii10`
- `t10yie`
- `real_yield_pressure_status`

`inflation_energy_pressure`

- `core_cpi_yoy`
- `core_pce_yoy`
- `ppiaco_yoy`
- `wti_30d_change`
- `brent_30d_change`

`equity_trend`

- `sp500_30d_return`
- `sp500_60d_return`
- `nasdaq100_30d_return`
- `nasdaq100_60d_return`
- `nasdaq_vs_sp500_30d`

`portfolio_deviation`

- `max_deviation_asset`
- `max_deviation_pp`
- `equity_total_deviation_pp`
- `cash_reserve_status`
- `holdings_updated_at`

## Source Badge Rules

Official sources can be marked `official` only when the report explicitly carries official source metadata. Fallback official sources use `official_fallback`. Unofficial market-data fallback sources use `unofficial_fallback`.

Proxy and search-derived data must not be labeled official. Search-derived data is not allowed in factual AI context.

Local portfolio context can use `local` when it comes from a local compact portfolio snapshot and does not expose holdings rows or full amounts.

Derived calculations can use `derived` only when the underlying metric is already present in the compact report.

## Missing And Research Needed Rules

Missing data must be shown as:

- `missing`
- `research_needed`
- `insufficient_history`
- `stale`
- `not_available`

Do not use unexplained `--` on the dashboard first screen.

If breakout confirmation, consensus surprise, or return history is absent, display a missing or insufficient-history metric. Do not infer confirmation, surprise, or trend from unrelated fields.

## AI Context Rules

`ai_context_allowed` is true only when:

- the metric has a source,
- it has observation or generation timing,
- it is not missing, research-needed, not-available, or stale,
- it is not search-derived.

Portfolio deviation may be allowed as local context, but it must not include holdings detail, fund-level rows, raw amounts, or market-factor attribution.

## Financial Boundaries

- FRED DGS10 and DGS30 are daily series, not intraday yields.
- Do not show "breakout confirmed" unless the compact report provides explicit confirmation.
- Do not show "above/below consensus" without consensus fields.
- PPIACO is not final demand PPI; any PPIACO metric must state this.
- Cash reserve is not part of target allocation.
- Portfolio deviation is not attributed to market factors in v1.
- Module status is risk context, not a trading signal.

## Not In v1

- Show All detail drawer
- Evidence Table full page
- Chart library or sparklines presented as real trends
- DeepSeek chat
- Tavily
- Account editing
- Tauri packaging
- Provider live refresh
