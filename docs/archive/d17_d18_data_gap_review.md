# DF-3 D17/D18 Data Gap and Source-gate Review

## Scope

DF-3 audits the existing D17 Growth / Inflation Macro Pack and D18 Valuation /
Equity Structure modules against the current project boundaries, with focus on
data coverage, source gates, proxy / research_needed / insufficient_history
handling, and AI Context Manifest entry rules.

DF-3 does not add a new provider, hard-fill valuation / earnings / true-breadth
gaps, rewrite D17, rewrite D18, add endpoints, add frontend UI, reopen external
AI, add Tavily/search, add persistence, run live fetches, or add prediction,
probability, return, allocation, or trading outputs.

## D17 Audit

### Current outputs

D17 public outputs (`growth_inflation_macro_pack`) are limited to the registry
contract defined in `modeling/metric_lookup.py:D17_PUBLIC_OUTPUT_KEYS`:

- `growth_macro_status`
- `growth_macro_supporting_evidence`
- `growth_macro_missing_inputs`
- `growth_macro_interpretation_boundary`
- `inflation_macro_status`
- `inflation_macro_supporting_evidence`
- `inflation_macro_missing_inputs`
- `inflation_macro_interpretation_boundary`
- `policy_constraint_status`
- `policy_constraint_supporting_evidence`
- `policy_constraint_missing_inputs`
- `policy_constraint_interpretation_boundary`
- `stagflation_watch_status`
- `stagflation_watch_supporting_evidence`
- `stagflation_watch_missing_inputs`
- `stagflation_watch_interpretation_boundary`
- `growth_inflation_macro_pack_model_version`
- `growth_inflation_macro_pack_formula_version`
- `growth_inflation_macro_pack_as_of_date`

### Available evidence

D17 reads source-gated evidence rows for the following groups:

- Growth current keys: `unemployment_rate`, `unemployment_rate_3m_avg`,
  `initial_jobless_claims`, `initial_claims_4w_avg`, `continuing_claims`,
  `continuing_claims_4w_avg`, `nonfarm_payrolls`, `labor_deterioration_status`.
- Inflation core keys: `core_cpi_yoy`, `core_pce_yoy`, `ppiaco_yoy`,
  `ppi_final_demand_yoy`.
- Inflation auxiliary keys: `wti_30d_change`, `brent_30d_change`, `t10yie`.
- Rates / policy keys: `dgs10`, `dgs30`, `dfii10`, `t10yie`,
  `real_yield_pressure_status`.

### Missing / limited inputs

D17 keeps the following groups visible as `research_needed` even when no
evidence row is present, so the gap is never silently filled:

- Survey indicators: `ism_manufacturing_pmi`, `ism_services_pmi`,
  `ism_new_orders`, `ism_employment`, `ism_prices_paid`.
- Real activity: `retail_sales_mom`, `retail_sales_yoy`,
  `retail_sales_control_group`, `industrial_production_yoy`,
  `capacity_utilization`, `housing_starts`, `building_permits`,
  `new_home_sales`, `mortgage_30y_rate`.
- Inflation decomposition: `core_cpi_goods_yoy`, `core_cpi_services_yoy`,
  `core_pce_goods_yoy`, `core_pce_services_yoy`,
  `ppi_final_demand_goods_yoy`, `ppi_final_demand_services_yoy`,
  `gasoline_price_context`.

When no inflation core series is present and only auxiliary energy or
breakeven rows are present, inflation status is downgraded to `missing` and
the core keys are added to the missing inputs list. This keeps the
`oil_alone_cannot_trigger_inflation_pressure` hard gate honest.

### Source gates

- `_usable(index, key)` in `growth_inflation_macro_pack.py` relies on
  `EvidenceIndex.is_usable_for_support`, which excludes
  `research_needed`, `insufficient_history`, `missing`, `stale`, `unknown`,
  blocked, and `ai_context_allowed=False` rows from support.
- D17 derives its rows with `source_badge="derived"` and
  `ai_context_policy="fact_or_excluded_by_row"`, so D17 rows enter AI Context
  Manifest only when their per-row `ai_context_allowed` is `True`.
- Rows tagged `research_needed`, `missing`, `insufficient_evidence`, or
  `unknown` set `ai_context_allowed=False`. This excludes them from factual
  context and from model-output context.

### Boundary risks

- Hard gates verified in code:
  - `oil_alone_cannot_trigger_inflation_pressure`
  - `low_frequency_inflation_data_boundary`
  - `cpi_alone_cannot_trigger_stagflation_watch_pressure`
  - `requires_inflation_growth_and_policy_constraint`
  - `labor_watch_alone_not_business_cycle_call`
  - `broad_growth_pack_missing_until_source_gated`
  - `rates_and_inflation_required_for_policy_constraint`
- D17 boundary text (`BOUNDARY` constant) explicitly states the module is "not
  a forecast, business-cycle call, event-odds model, allocation directive, or
  return estimate", and that "CPI/PCE/PPI are low-frequency data".
- Sahm-rule, ISM, retail sales, IP, and housing starts remain `research_needed`.
  D17 does not consume any Sahm-rule proxy row to issue a recession call.
- Energy pass-through (`wti_30d_change`, `brent_30d_change`) remains an
  auxiliary inflation context input only. It cannot create an
  `inflation_macro_status == "pressure"` row without core CPI/PCE/PPI support.

### Required fixes, if any

None. D17 production code passes DF-3 compliance review.

## D18 Audit

### Current outputs

D18 public outputs (`valuation_equity_structure`) are limited to the registry
contract defined in `modeling/metric_lookup.py:D18_PUBLIC_OUTPUT_KEYS`:

- `valuation_context_status`
- `valuation_pressure_hint`
- `valuation_metric_source_quality`
- `valuation_missing_inputs`
- `valuation_interpretation_boundary`
- `earnings_context_status`
- `earnings_missing_inputs`
- `earnings_interpretation_boundary`
- `equity_structure_status`
- `equity_structure_supporting_evidence`
- `equity_structure_missing_inputs`
- `equity_structure_interpretation_boundary`
- `breadth_concentration_context_status`
- `breadth_concentration_supporting_evidence`
- `breadth_concentration_missing_inputs`
- `breadth_concentration_interpretation_boundary`
- `valuation_equity_structure_model_version`
- `valuation_equity_structure_formula_version`
- `valuation_equity_structure_as_of_date`

### Available evidence

D18 reads source-gated evidence rows for the following groups:

- Valuation fact keys: `sp500_trailing_pe`, `sp500_forward_pe`,
  `cape_shiller_pe`, `earnings_yield`, `equity_risk_premium_proxy`. These are
  only counted when `_source_gated` passes, that is, when the row's
  `source_badge` is one of `official`, `official_fallback`, or `derived`.
- Earnings fact keys: `earnings_revision`, `eps_growth`, with the same
  source-gate requirement.
- Equity structure proxy keys: `qqq_vs_spy_30d`, `qqq_vs_spy_60d`,
  `nasdaq_vs_sp500_30d`, `nasdaq100_drawdown_3m`, `nasdaq100_drawdown_6m`,
  `sp500_drawdown_3m`, `sp500_drawdown_6m`. These are read as proxies via
  `_usable_proxy`, never as source-gated facts.
- Breadth/concentration proxy keys: `spy_vs_rsp_30d`, `spy_vs_rsp_60d`,
  `qqq_vs_spy_30d`, `qqq_vs_spy_60d`. Proxy-only.

### Missing / limited inputs

D18 keeps the following groups visible as `research_needed` regardless of
evidence availability:

- Valuation source gates: `sp500_trailing_pe_source_gate`,
  `sp500_forward_pe_source_gate`, `sp500_cape_source_gate`,
  `sp500_erp_source_gate`, `sp500_top10_weight_source_gate`,
  `mag7_concentration_source_gate`.
- Earnings source gates: `earnings_revision_source_gate`,
  `eps_growth_source_gate`.
- True-breadth source gates: `true_breadth_source_gate`,
  `constituent_breadth_source_gate`.

These source-gate placeholders are unioned into every D18 missing-inputs row.
A user cannot read a D18 output without seeing that valuation, earnings, and
true-breadth gaps are still open.

### Proxy-only areas

- `equity_structure` and `breadth_concentration` rely on proxy ratios
  (SPY/RSP, QQQ/SPY, drawdown). Single-proxy pressure cannot escalate:
  `single_proxy_cannot_create_pressure` requires two proxies in pressure or
  watch before the row escalates beyond `limited_proxy_context`.
- HY/IG proxy spreads (HYG/LQD-style) are not consumed by D18 as
  valuation/earnings context; they remain auxiliary credit context for D10 /
  D11 / D14 / D15.
- AI-mega-cap concentration proxy is gated by
  `ai_mega_cap_context_requires_credit_funding_labor_confirmation_for_systemic_review`,
  so no single proxy escalates concentration into systemic interpretation.

### Source gates

- `_source_gated(index, metric_key)` in `valuation_equity_structure.py`
  requires `source_badge in {"official", "official_fallback", "derived"}` AND
  `EvidenceIndex.is_usable_for_support` to pass. Proxy and `search-derived`
  badges are rejected as valuation facts.
- D18 sets `trigger_eligibility="auxiliary_only"` on every model-output row,
  so D18 cannot be used as a primary trigger downstream.
- Missing-input rows always set `ai_context_allowed=False`. Status values
  `research_needed`, `not_available`, and `insufficient_evidence` also
  produce `ai_context_allowed=False`.

### Boundary risks

- Hard gates verified in code:
  - `valuation_cannot_trigger_macro_regime`
  - `valuation_cannot_trigger_systemic_review`
  - `proxy_breadth_not_true_breadth`
  - `proxy_only_context_cannot_create_strong_label`
  - `forward_pe_requires_reliable_source_gate`
  - `valuation_high_is_vulnerability_context_only`
  - `missing_valuation_not_low_or_high`
  - `earnings_revisions_require_reliable_source_gate`
  - `missing_earnings_not_low_or_high`
  - `nasdaq_underperformance_is_equity_structure_context_only`
  - `ai_mega_cap_context_requires_credit_funding_labor_confirmation_for_systemic_review`
  - `single_proxy_cannot_create_pressure`
  - `spy_rsp_qqq_proxy_auxiliary_only`
  - `proxy_breadth_does_not_replace_true_breadth`
- D18 boundary text (`BOUNDARY` constant) explicitly states the module is
  "not a forecast, timing model, event-odds model, allocation directive, or
  return estimate", and that "proxy breadth/concentration does not replace
  true breadth".
- D18 does not consume any web-scraped, search-derived, or AI-generated
  valuation, earnings, or breadth row.

### Required fixes, if any

None. D18 production code passes DF-3 compliance review.

## Source-gate Table

The table classifies the indicators called out in the DF-3 task brief
according to the current production behavior of D17, D18, and the shared
evidence pipeline. `current source gate` is the highest-confidence treatment
the indicator may receive today. `production routing` indicates how a passing
row may reach D17 / D18 today. Indicators marked `not_allowed_currently`
remain explicitly outside the production context until a dedicated future
task gates them with a documented provider, freshness rule, and audit.

### D17 indicators

| Indicator | Current source gate | Production routing |
|---|---|---|
| `core_cpi_yoy` | official_allowed | D17 inflation core, low-frequency boundary preserved |
| `core_pce_yoy` | official_allowed | D17 inflation core, low-frequency boundary preserved |
| `ppi_final_demand_yoy` | official_allowed | D17 inflation core |
| `ppiaco_yoy` | official_allowed | D17 inflation core |
| `wti_30d_change` | derived_allowed | D17 inflation auxiliary, oil-alone gate enforced |
| `brent_30d_change` | derived_allowed | D17 inflation auxiliary, oil-alone gate enforced |
| `t10yie` | official_allowed | D17 inflation auxiliary and rates/policy context |
| `t5yie` | not_allowed_currently | not in D17 keys; future inflation expectations backlog |
| `unemployment_rate` | official_allowed | D17 growth current |
| `initial_jobless_claims` | official_allowed | D17 growth current |
| `continuing_claims` | official_allowed | D17 growth current |
| `nonfarm_payrolls` | official_allowed | D17 growth current (payroll revision limitations preserved by row freshness) |
| `sahm_rule_proxy_status` | not_allowed_currently | excluded from D17; not a recession trigger |
| `ism_manufacturing_pmi` | research_needed | always surfaced in `growth_macro_missing_inputs` |
| `ism_services_pmi` | research_needed | always surfaced in `growth_macro_missing_inputs` |
| `retail_sales_*` | research_needed | always surfaced in `growth_macro_missing_inputs` |
| `industrial_production_yoy` | research_needed | always surfaced in `growth_macro_missing_inputs` |
| `housing_starts` / `building_permits` / `new_home_sales` | research_needed | always surfaced in `growth_macro_missing_inputs` |
| `mortgage_30y_rate` | research_needed | always surfaced in `growth_macro_missing_inputs` |
| `core_cpi_goods_yoy` / `core_cpi_services_yoy` | research_needed | always surfaced in `inflation_macro_missing_inputs` |
| `core_pce_goods_yoy` / `core_pce_services_yoy` | research_needed | always surfaced in `inflation_macro_missing_inputs` |
| `ppi_final_demand_goods_yoy` / `ppi_final_demand_services_yoy` | research_needed | always surfaced in `inflation_macro_missing_inputs` |
| `ism_prices_paid` | research_needed | always surfaced in `inflation_macro_missing_inputs` |
| `gasoline_price_context` | research_needed | always surfaced in `inflation_macro_missing_inputs` |

### D18 indicators

| Indicator | Current source gate | Production routing |
|---|---|---|
| `sp500_drawdown_3m` | derived_allowed | D18 equity structure proxy, single-proxy gate enforced |
| `nasdaq100_drawdown_3m` | derived_allowed | D18 equity structure proxy, single-proxy gate enforced |
| `spy_vs_rsp_30d` / `spy_vs_rsp_60d` | proxy_auxiliary_only | D18 breadth/concentration proxy, single-proxy gate enforced |
| `qqq_vs_spy_30d` / `qqq_vs_spy_60d` | proxy_auxiliary_only | D18 equity structure and breadth/concentration proxy |
| `hyg_vs_lqd_30d` and similar HY/IG proxy | not_allowed_currently for D18 | not consumed by D18 valuation/earnings/breadth; remains credit context |
| `valuation_context` (composite) | research_needed | always surfaced as `valuation_missing_inputs` source gates |
| `sp500_trailing_pe` / `sp500_forward_pe` | research_needed | source-gate placeholder; only consumed when `source_badge in {official, official_fallback, derived}` |
| `cape_shiller_pe` | research_needed | source-gate placeholder; same source-gate requirement |
| `earnings_yield` | research_needed | source-gate placeholder |
| `equity_risk_premium_proxy` | research_needed | source-gate placeholder |
| `earnings_revision` | research_needed | source-gate placeholder; never AI-filled |
| `eps_growth` | research_needed | source-gate placeholder; never AI-filled |
| `advance_decline_line` | research_needed | true-breadth source gate, always surfaced as missing |
| `percent_above_200dma` | research_needed | true-breadth source gate, always surfaced as missing |
| `new_highs_new_lows` | research_needed | true-breadth source gate, always surfaced as missing |
| `true_breadth` (composite) | research_needed | always surfaced; cannot be replaced by proxy concentration |
| `sp500_top10_weight` | research_needed | concentration source gate, always surfaced |
| `mag7_concentration` | research_needed | concentration source gate, always surfaced |

### Allowed pathways summary

- `official` / `official_fallback`: may enter factual evidence when metadata
  (source, observation date, freshness, source_badge) is complete and
  `ai_context_allowed` is `True`.
- `derived`: may enter model-output context when produced deterministically
  from qualifying inputs, including D17 and D18 own rows.
- `proxy`: auxiliary only; cannot strong-trigger valuation, earnings, or
  true-breadth labels; cannot replace official inputs.
- `research_needed`: excluded from factual context; surfaces in the
  module-specific `*_missing_inputs` row with `ai_context_allowed=False`.
- `missing`, `insufficient_history`, `stale`, `unknown`, blocked: excluded
  from factual context; surfaces as missing input or blocked input.
- `search-derived`: not an allowed source gate for D17 or D18 production.
- `not_allowed_currently`: indicator is documented but is not part of any
  D17 / D18 source-gate path; future enablement requires a dedicated task.

## AI Context / Model Interaction

### Compliant

- D17 and D18 enter AI Context Manifest only when their per-row
  `ai_context_allowed` is `True`. The registry policy
  `ai_context_policy="fact_or_excluded_by_row"` enforces row-level filtering.
- D17 / D18 `_missing_inputs` rows and rows with status
  `research_needed`, `not_available`, `unknown`, or `insufficient_evidence`
  set `ai_context_allowed=False` and are excluded from facts.
- D17 / D18 interpretation boundaries are written into both the row payload
  and the registry, so they remain visible to D15 / D16 / D19 consumers and
  to the AI memo renderer.
- D15 references D17 / D18 missing inputs as constraints. The D15 hard gate
  `missing_stale_blocked_research_needed_insufficient_history_cannot_support_label`
  blocks silent filling.
- D16 references D17 / D18 supporting evidence and missing inputs while
  preserving uncertainty bands. D16 cannot upgrade severity using
  proxy-only or research-needed D17 / D18 rows.
- D19 replay treats D17 / D18 gaps as missing or limited input notes, not as
  backtest errors or accuracy metrics.
- AI memo contract continues to reject investment-advice expansion of D17 or
  D18 output (no recession call, no timing call, no allocation directive).

### Documentation-only risk

- Stage R1 research recovery notes (`docs/research/...`,
  `docs/historical_percentile_method_note.md`,
  `docs/metric_interpretation_boundaries.md`) are docs-only background. They
  must not be used to authorize a production CAPE / forward PE / earnings
  revision / true breadth provider integration without a dedicated task.

### Test coverage gap

- Before DF-3, D17 and D18 had module-specific tests
  (`tests/test_growth_inflation_macro_pack.py`,
  `tests/test_valuation_equity_structure.py`) and golden output / AI
  context / AI memo contract tests, but there was no single DF-3 audit test
  file collecting the data-gap and source-gate guarantees. DF-3 adds
  `tests/test_d17_d18_data_gap_review.py` to make the boundary package
  explicit.

### Scoped source-gate fix needed

None.

### Future backlog

- DF-4 may add D13 reliability / divergence metadata.
- D18 source-gated valuation / earnings / true-breadth providers remain
  future backlog. They must be brought in only through a future dedicated
  task with a documented provider, freshness rule, audit, and a fresh DF
  compliance review.
- Sahm-rule, ISM, retail sales, industrial production, housing starts, and
  payroll revision provider integration remain future backlog. None of them
  may be replaced by AI-filled values.

### Not allowed currently

- Network-scraped CAPE, forward PE, or earnings revision.
- AI-filled valuation, earnings, or true-breadth facts.
- Treating proxy breadth/concentration as confirmed true breadth.
- Treating D17 as a recession call or D18 as a timing model.
- Re-opening DeepSeek Chat, Tavily/search, frontend AI UI, persistent chat /
  memo / report storage, or any external AI productization in scope of DF-3.

## Final Decision

DF-3 audit passed without production code changes.

## Next Step

DF-4 D13 reliability / divergence metadata is the next optional engineering
task. No DF-3b scoped source-gate fix is required.
