# Data Pipeline Coverage Audit

This note documents the local-only audit for Dashboard v1 data credibility semantics.
The audit does not call providers, DeepSeek, Tavily, search, or portfolio holdings detail readers.

## Audit Script

Run:

```powershell
python scripts/audit_data_pipeline_coverage.py
```

The script reads only the same compact local report files used by the Dashboard service and prints a compact JSON summary to stdout.

Optional local artifact output:

```powershell
python scripts/audit_data_pipeline_coverage.py --save
```

`--save` writes ignored artifacts:

- `outputs/reports/data_pipeline_coverage.json`
- `outputs/reports/data_pipeline_coverage.md`

These generated output files must not be committed.

## Coverage Summary Fields

- `total_rows`
- `rows_with_value`
- `rows_missing_value`
- `rows_with_value_and_complete_metadata`
- `rows_with_value_but_blocked`
- `ok_count`
- `watch_count`
- `pressure_count`
- `missing_count`
- `research_needed_count`
- `insufficient_history_count`
- `stale_count`
- `unknown_count`
- `source_badge_missing_count`
- `provenance_missing_count`
- `freshness_unknown_count`
- `freshness_missing_or_unknown_count`
- `observation_date_missing_count`
- `date_missing_count`
- `ai_context_allowed_true_count`
- `ai_context_allowed_false_count`
- `last_good_metric_count`
- `last_good_usable_count`
- `last_good_stale_count`
- `last_good_expired_count`
- `last_good_error_count`
- `last_good_not_used_count`

## Provenance Completeness

A row with value has complete provenance when:

- `source_badge` is present and not `missing`
- `freshness_status` is present and not unknown, missing, stale, or insufficient_history
- either `observation_date` or `generated_at` is present

D0.1 repairs existing metric provenance propagation only. It does not add providers, run live checks, or infer official status when the compact report cannot support it.

Dashboard may use compact metadata from:

- the metric payload itself
- `data_quality.market_data_quality.<metric_key>`
- optional local `llm_context_pack.json` metadata, when present, as a metadata-only fallback

The optional metadata fallback is not returned raw to the API response.

## Blocked Reason Counts

`blocked_reason_counts` aggregates why rows cannot enter the AI factual context layer.

Common reasons include:

- `value_missing`
- `source_badge_missing`
- `freshness_unknown`
- `date_missing`
- `dependency_metadata_incomplete`
- `source_badge_proxy`
- `source_badge_search-derived`

Each metadata anomaly includes a machine-readable `reason` field.

## Source Badge Distribution

`source_badge_distribution` counts evidence rows by source badge:

- `official`
- `official_fallback`
- `unofficial_fallback`
- `local`
- `derived`
- `proxy`
- `search-derived`
- `missing`
- `research_needed`

This distribution is used to verify that proxy/search-derived rows are not silently promoted into official evidence.

## AI Context By Module

`ai_context_allowed_by_module` reports true/false counts per Dashboard module.
It is intended for quick regression checks after provenance or dependency changes.

## Module Coverage Fields

Each Dashboard module reports:

- `module`
- `row_count`
- `ok_count`
- `watch_count`
- `pressure_count`
- `missing_count`
- `research_needed_count`
- `insufficient_history_count`
- `stale_count`
- `usable_fact_count`
- `ai_context_allowed_count`
- `module_coverage_status`

`module_coverage_status` is one of:

- `usable`
- `partial`
- `weak`
- `unavailable`

## Module Coverage Summary Fields

`module_coverage_summary` is a machine-readable per-module rollup for fast gap
triage:

- `usable_row_count_by_module`
- `missing_count_by_module`
- `research_needed_count_by_module`
- `insufficient_history_count_by_module`
- `official_count_by_module`
- `derived_or_proxy_count_by_module`
- `ai_context_allowed_count_by_module`
- `coverage_status_by_module`

The top-level audit also reports:

- `top_missing_metrics`
- `top_research_needed_metrics`
- `top_insufficient_history_metrics`
- `dashboard_overall_degraded_reasons`
- `data_sufficiency_assessment`

`data_sufficiency_assessment.daily_macro_monitoring` can be
`partial_but_usable` when every main dashboard module has at least one AI
factual row. This does not mean the data is sufficient for crisis confirmation,
valuation judgment, or market-breadth judgment.
`insufficient_for_crisis_confirmation` remains `true` because systemic crisis
confirmation requires broader funding, labor, earnings, and multi-signal credit
evidence than the compact dashboard provides.

## Portfolio Compact Fields

The audit includes a `portfolio_compact` block for the local
`portfolio_deviation` module:

- `portfolio_compact_available`: required aggregate compact fields have values
- `portfolio_deviation_value_count`: compact rows with values
- `portfolio_deviation_missing_count`: compact rows without values
- `portfolio_deviation_ai_context_allowed_count`: compact rows eligible for AI factual context
- `portfolio_has_raw_holdings_leak`: must remain `false`
- `portfolio_cash_excluded_from_target`: cash reserve exclusion is visible in compact context
- `portfolio_stale_status`: freshness status from the holdings update row

Recommendations are conditional:

- missing compact fields add `fill_portfolio_deviation_compact`
- stale holdings add `update_holdings_snapshot`
- any raw holdings leak adds `privacy_blocker`

## Last-good Cache Fields

The audit reads the local per-key last-good cache without writing new entries.

Top-level `last_good_cache` fields:

- `last_good_cache_available`: whether any cache files were found
- `last_good_metric_count`: count of readable non-error last-good metrics
- `last_good_usable_count`: cache entries still inside their freshness window
- `last_good_stale_count`: cache entries past `stale_after` but not hard expired
- `last_good_expired_count`: cache entries past the conservative expiry window
- `last_good_error_count`: unreadable or invalid cache entries
- `metrics_with_last_good`: metric keys with readable last-good entries
- `metrics_missing_but_last_good_available`: current missing metrics that have last-good available
- `last_good_not_used_count`: number of missing current metrics with last-good available

Each module coverage item also includes:

- `last_good_available_count`
- `missing_but_last_good_available_count`

Last-good cache availability is informational only.
The audit does not treat last-good as the current live value and does not replace Dashboard rows with cached values.

Recommendations are conditional:

- corrupted last-good JSON adds `clear_or_rebuild_last_good_cache`
- stale or expired last-good entries add `refresh_market_snapshot`

## Market Historical Store Fields

The audit reads the local market historical SQLite store without writing to it.
If the database is absent, the audit does not fail.

Top-level `historical_store` fields:

- `market_history_available`: whether the store has observations
- `market_history_db_exists`: whether the SQLite file exists
- `market_history_schema_version`: applied schema version, or `0` when absent
- `market_history_metric_count`: number of metrics with observations
- `market_history_observation_count`: total observation count
- `observations_by_metric`: observation counts keyed by metric
- `latest_observation_by_metric`: latest observation date keyed by metric
- `dashboard_metrics_with_history_count`: Dashboard evidence rows whose metric has historical observations
- `insufficient_history_rows_count`: current Dashboard rows with `insufficient_history`
- `metrics_insufficient_history_but_store_empty`: insufficient-history metrics with no store observations
- `recommended_history_actions`: history-specific setup or ingest recommendations

When the database is missing, recommended actions include:

- `initialize_market_history_store`
- `ingest_market_history_from_dashboard`

The audit does not use historical observations to rewrite Dashboard values or derived metrics.

## Historical Derived Metrics Fields

The audit also evaluates candidate historical derived metrics from the local market history store.
This is read-only and does not update Dashboard current values.

Top-level `historical_derived` fields:

- `historical_derived_available`: whether any candidate derived metric is currently `ok`
- `derived_metric_count`: total supported candidate metrics
- `derived_metric_ok_count`: candidates with sufficient history
- `derived_metric_insufficient_history_count`: candidates still blocked by history
- `derived_metric_missing_dependency_count`: candidates blocked by missing dependency observations
- `derived_metrics_by_module`: candidate counts and status counts grouped by Dashboard module
- `derived_metric_details`: compact detail rows for each candidate
- `dashboard_insufficient_history_potentially_resolvable_count`: current insufficient-history Dashboard metrics with an OK historical candidate
- `dashboard_insufficient_history_still_blocked_count`: current insufficient-history Dashboard metrics still blocked by history

When the market history DB is absent, recommended actions include:

- `initialize_and_ingest_market_history`

When candidate windows are still insufficient, recommended actions include:

- `ingest_more_history`
- `run_yfinance_history_ingest_live`

Historical derived candidates use `source_badge=derived`.
`insufficient_history` candidates are not eligible for AI factual context.

## yfinance History Fields

The audit includes a read-only `yfinance_history` block for the optional yfinance batch history ingestion path.
It does not call yfinance, access the network, or write the market history database.

Top-level `yfinance_history` fields:

- `yfinance_history_configured`: whether enabled yfinance history symbols are configured
- `yfinance_enabled_symbol_count`: enabled symbols in `configs/yfinance_history.yaml`
- `yfinance_observation_count`: yfinance observations currently present in the market history store
- `yfinance_observations_by_metric`: yfinance observation counts keyed by metric
- `yfinance_latest_observation_by_metric`: latest yfinance observation date keyed by metric
- `yfinance_proxy_metric_count`: configured ETF proxy metric count
- `yfinance_unofficial_fallback_metric_count`: configured unofficial index fallback metric count
- `historical_store_proxy_observation_count`: stored yfinance proxy observations
- `historical_store_unofficial_observation_count`: stored yfinance unofficial fallback observations
- `insufficient_history_potentially_resolvable_by_yfinance`: current insufficient-history derived metrics whose dependencies are configured for yfinance history
- `recommendations`: yfinance-specific follow-up actions

Recommendations may include:

- `run_yfinance_history_ingest_live`
- `integrate_historical_derived_metrics`
- `keep_proxy_out_of_official_layer`

yfinance observations are informational historical inputs.
They are never treated as official facts and do not replace Dashboard current values.

## Proxy Breadth Fields

The audit includes a `proxy_breadth` block for local-only SPY/RSP/QQQ/HYG/LQD proxy-derived metrics.
It does not call yfinance, does not fetch live data, and does not treat proxy rows as official market breadth or valuation data.

Top-level `proxy_breadth` fields:

- `breadth_proxy_available`: whether SPY-vs-RSP proxy breadth rows are available
- `breadth_proxy_metric_count`: number of proxy breadth/concentration rows in Evidence Table
- `breadth_proxy_ok_count`: proxy rows with sufficient history
- `breadth_proxy_insufficient_history_count`: proxy rows blocked by insufficient history
- `concentration_proxy_available`: whether QQQ-vs-SPY or SPY-vs-RSP concentration proxy rows are available
- `credit_proxy_available`: whether HYG-vs-LQD credit proxy rows are available
- `proxy_metrics_ai_context_allowed_count`: proxy-derived rows eligible for AI factual context under proxy-only semantics

These fields report proxy evidence only.
They do not satisfy true valuation, true advance/decline breadth, or systemic-crisis confirmation.

## Dashboard Derived Integration Fields

The audit includes a `dashboard_derived_integration` block for values that are actually surfaced in Dashboard evidence rows from historical derived metrics.
This is separate from `historical_derived`, which reports all supported candidates whether or not the Dashboard uses them.

Top-level `dashboard_derived_integration` fields:

- `equity_derived_integrated_count`: selected `equity_trend` rows now using historical derived values
- `equity_derived_still_insufficient_count`: selected `equity_trend` rows still blocked by insufficient history
- `historical_derived_used_in_dashboard_count`: Dashboard rows using local market history derived values
- `dashboard_insufficient_history_remaining_count`: current Dashboard evidence rows still insufficient
- `dashboard_equity_trend_value_count`: selected equity trend rows with values
- `integrated_metric_keys`: integrated equity metric keys
- `still_insufficient_metric_keys`: eligible equity metric keys still insufficient

The integration only covers:

- `sp500_30d_return`
- `sp500_60d_return`
- `nasdaq100_30d_return`
- `nasdaq100_60d_return`
- `nasdaq_vs_sp500_30d`
- `breadth_concentration_proxy` rows for SPY/RSP/QQQ/HYG/LQD proxy returns and relative returns

Rate historical derived candidates remain reported in `historical_derived`.
Oil historical derived candidates may be integrated into Dashboard current values
only when their dependencies are official FRED/EIA history rows.
Proxy breadth candidates may be integrated only when their dependencies are stored proxy observations.

## Energy History Fields

The audit includes an `energy_history` block for official WTI/Brent history
coverage and Dashboard status checks:

- `energy_history_available`: whether both `wti` and `brent` have local history observations
- `wti_history_observation_count`
- `brent_history_observation_count`
- `wti_30d_change_status`
- `brent_30d_change_status`
- `real_yield_pressure_status_status`
- `dgs30_breakout_confirmed_status`
- `ppi_final_demand_status`
- `recommended_history_actions`

WTI/Brent history should be filled through `scripts/ingest_official_energy_history.py`.
The script writes compact FRED/EIA observations into `market_history`; it must not
commit the SQLite DB.
`ppi_final_demand_status` remains `research_needed` until a verified official
series is configured.

## Official Macro Pack Fields

The audit includes an `official_macro_pack` block for configured official macro metadata.
It is read-only and does not call FRED, BLS, BEA, Treasury, yfinance, DeepSeek, Tavily, or search.

Top-level `official_macro_pack` fields:

- `official_macro_configured_count`: configured official macro rows, including the `ppi_final_demand` research boundary
- `official_macro_available_count`: configured rows with an OK value, official source badge, source, date metadata, and non-bad freshness
- `official_macro_missing_count`: configured rows not currently available from compact local evidence
- `available_metric_keys`: available metric keys
- `missing_metric_keys`: missing or research-needed metric keys
- `real_yield_available`: whether `dfii10` and `t10yie` are both available
- `inflation_core_available`: whether `core_cpi_yoy` and `core_pce_yoy` are both available
- `labor_available`: whether `unemployment_rate` and `initial_jobless_claims` are both available
- `labor_missing_count`: count of missing labor metrics in the official macro pack
- `official_macro_missing_reasons`: compact missing reasons by metric key
- `ppi_final_demand_status`: remains `research_needed` until a verified official series is configured
- `details`: compact per-metric source, series, frequency, dashboard, and missing status metadata

The official macro pack does not treat PPIACO as final demand PPI.
Labor metrics are surfaced as `labor_macro` Evidence Table rows for audit visibility and are not added to the Dashboard homepage.

## Provider Health Fields

The audit includes a `provider_health` block derived from the compact provider-health cache.

- `overall_status`: provider-health status such as `ok`, `degraded`, `error`, or `not_run_yet`
- `provider_health_transient_error_count`: transient network/SSL errors such as a single FRED SSL EOF
- `official_fallback_ok_count`: successful official fallback checks, such as U.S. Treasury, BLS, BEA, or New York Fed
- `official_fallback_ok_providers`: successful official fallback provider names

A transient FRED request error should degrade provider health without implying that all official data failed when official fallback checks are OK.

## Metadata Anomaly Types

The audit detects:

- value exists but `source_badge` is missing
- value exists but `freshness_status` is unknown or missing
- value exists but both `observation_date` and `generated_at` are missing
- `ai_context_allowed=true` with missing `source_badge`
- `ai_context_allowed=true` with unknown, missing, or stale freshness
- `ai_context_allowed=true` while status is missing, research_needed, not_available, insufficient_history, or stale
- `ai_context_allowed=true` while source_badge is missing, research_needed, or search-derived
- proxy/search-derived rows without a clear `interpretation_hint`
- missing/research_needed rows without `missing_reason`

## Derived Dependency Anomaly Types

The audit checks for:

- `dgs30_distance_to_5pct` OK/value while DGS30 is missing or unavailable
- `dgs30_breakout_confirmed` OK/value while DGS30 or required history evidence is missing
- `nasdaq_vs_sp500_30d` OK/value while S&P 500 or Nasdaq 100 30D return is missing or insufficient
- `wti_30d_change` or `brent_30d_change` OK/value without clear 30 day history semantics
- module status OK while most core metrics are missing, research_needed, or insufficient_history

## Module Status Aggregation

Dashboard module status is a data-quality status, not just an API-health status.

- All core metrics unavailable means the module must not be OK.
- Partial core coverage keeps the module out of green OK unless the available core metrics clearly support the status.
- Stale core metrics make the module stale or unknown.
- `portfolio_deviation` is not OK when only `holdings_updated_at` exists and compact deviation fields are missing.
- `provider_health=not_run_yet` is not a provider failure, but it can degrade overall dashboard data quality.

## AI Context Gate

Rows do not enter the future AI factual context layer when:

- status is missing, research_needed, not_available, insufficient_history, or stale
- freshness is unknown, missing, stale, or insufficient_history
- source_badge is missing, research_needed, or search-derived
- source_badge is proxy without explicit allowed-proxy semantics
- source_badge is derived without a clear interpretation/dependency hint
- both `observation_date` and `generated_at` are missing

Local portfolio context may be eligible only when compact non-holdings fields are present. Raw holdings details are not returned.

## Derived Metric Dependency Metadata

Derived rows may enter AI factual context only when:

- the dependency source has complete metadata
- the derived row has a clear dependency or calculation hint
- the row has date metadata from the dependency or compact report

For D0.1, `dgs10_5d_avg` is treated as `derived` and allowed only when its compact metadata says it is an average of latest available FRED daily observations or equivalent dependency wording.

## Local `holdings_updated_at`

`holdings_updated_at` is a local provenance fact:

- `source_badge=local`
- `freshness_status` comes from `holdings_freshness_status`
- `observation_date` is the holdings update date
- it may enter AI factual context only as the update-date fact
- holdings rows, amounts, tickers, and raw holdings payloads are not returned

## Provider Health `not_run_yet`

Missing `provider_health_check.json` means:

- `overall_status=not_run_yet`
- this is not interpreted as provider broken
- the next action is `python scripts/run_provider_health_check.py --save`
- Dashboard overall status may be degraded because the health check has not run

## Later Data Foundation Phases

Pick one focused next phase at a time:

- Portfolio Deviation Compact Fields
- Per-key Last-good Cache
- Market Historical Store Foundation
- Historical Derived Metrics
- user-run yfinance batch history ingestion
- official macro pack
