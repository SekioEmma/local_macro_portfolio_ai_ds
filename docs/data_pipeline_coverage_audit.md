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
- yfinance batch history
- official macro pack
