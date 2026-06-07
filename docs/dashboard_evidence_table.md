# Dashboard Evidence Table

The dashboard evidence table is a local, read-only audit view for the key metrics shown on the market dashboard. It is not a trading system, does not run providers, and does not call DeepSeek or Tavily.

## API

`GET /api/dashboard/evidence-table`

The response is derived from `GET /api/dashboard/summary` and its `modules.*.key_metrics` rows.

## Response Fields

`DashboardEvidenceTableResponse`:

- `generated_at`: compact dashboard generation time when available.
- `overall_status`: dashboard status.
- `row_count`: number of returned rows after optional API filters.
- `modules`: available dashboard modules.
- `rows`: evidence rows.
- `filters`: available and applied filter metadata.
- `next_actions`: local commands that can regenerate missing cache files.

`DashboardEvidenceRow`:

- `row_id`: `{module}:{metric_key}`.
- `module`: dashboard module key.
- `metric_key`: stable metric identifier.
- `display_name`: UI label.
- `value`: compact typed value only.
- `value_text`: UI-safe value text. Unexplained `--` is not allowed.
- `unit`: optional unit.
- `status`: metric status.
- `source`: compact source label when available.
- `source_badge`: source tier such as `official`, `unofficial_fallback`, `proxy`, `derived`, `local`, `missing`, or `research_needed`.
- `observation_date`: observation date when available.
- `generated_at`: cache generation time when available.
- `freshness_status`: freshness marker.
- `missing_reason`: explicit missing/research/insufficient-history reason.
- `interpretation_hint`: financial boundary or interpretation note.
- `ai_context_allowed`: whether the row may enter a future AI factual context layer.

## AI Context Rules

Rows are excluded from AI factual context when:

- `status` is `missing`, `research_needed`, `insufficient_history`, `not_available`, or `stale`.
- `freshness_status` is `stale`.
- `source_badge` is `search-derived`.
- no source exists and the row is not local portfolio context.

Local `portfolio_deviation` rows may be eligible only as compact local context. They must not include holdings line items.

## Source Badge Rules

- `official`: official source series.
- `official_fallback`: official source fallback.
- `unofficial_fallback`: non-official fallback, not treated as official.
- `proxy`: proxy data, not treated as official.
- `search-derived`: blocked from AI factual context in this phase.
- `derived`: calculated from compact metric values.
- `local`: local portfolio summary context only.
- `missing` or `research_needed`: not evidence for factual AI context.

## Missing And Research Needed

Missing, research-needed, insufficient-history, stale, and not-available states must be explicit. The UI and API must not use unexplained `--` for these rows.

## Financial Boundaries

- DGS Treasury series are daily, not intraday.
- `dgs2`, `dgs30`, `dfii10`, `t10yie`, `core_cpi_yoy`, `core_pce_yoy`, `ppiaco_yoy`, `unemployment_rate`, and `initial_jobless_claims` use official macro-pack metadata when compact local values are present.
- Labor metrics appear as `labor_macro` evidence rows for audit coverage; they are not homepage cards.
- `investment_grade_spread` can use FRED `BAMLC0A0CM` through the existing financial-conditions provider path. HYG/LQD remain proxy history only and must not be marked official.
- `credit_stress_status` is derived from credit spread evidence plus VIX; VIX alone must not confirm crisis or systemic credit stress.
- `wti_30d_change` and `brent_30d_change` may use existing FRED oil compact aliases or local market-history derived rows only when dependency history is official FRED/EIA daily oil history. They remain derived energy-pressure inputs, not real-time oil quotes, inflation forecasts, or commodity trading signals.
- `real_yield_pressure_status` is derived from DFII10 and T10YIE when both are available. It describes a valuation and opportunity-cost mechanism, not a sole driver or trading instruction.
- DGS breakout confirmation requires explicit compact evidence. Without a clear rule and sufficient DGS30 history it remains `research_needed`.
- PPIACO is not final demand PPI.
- PPI final demand remains `research_needed` until a verified official series id is configured.
- Core CPI/Core PCE/PPI `*_yoy` rows must represent actual YoY rates; index levels must be blocked as insufficient history instead of displayed as impossible percentages.
- Cash reserve status is not a target allocation.
- Portfolio deviation is local context and is not attributed to market factors.
- Dashboard status and evidence rows are not buy/sell instructions.

## Privacy Boundaries

The evidence table must not return:

- raw `market_snapshot`
- raw `portfolio_snapshot`
- raw `llm_context_pack`
- holdings line items
- API keys
- raw prompts
- raw outputs
- full project root

The first version does not implement Show All Drawer, charting, AI Chat injection, Tavily, or provider live refresh.
