# Dashboard Service Refactor Phase E - Module Builder Extraction

## Scope

Phase E extracts `DashboardModule` construction helpers from
`dashboard_service.py` into `dashboard_module_builder.py`.

## What Moved

- `build_modules` adapter target
- `market_module`
- `portfolio_module`
- `module`
- `module_status_with_coverage`
- `summary_with_coverage_note`
- historical-derived availability helpers
- `latest_metric_generated_at`

## What Stayed in `dashboard_service.py`

- public `build_dashboard_summary` / `build_dashboard_evidence_table`
- default report and market-history constants
- `_SHARED_DASHBOARD_CONTEXT_CACHE`
- `_key_metrics_for_module`
- `_build_metric`
- historical derived application functions
- portfolio compact functions
- `write_last_good` functions
- legacy underscore compatibility wrappers and aliases

## Dependency Strategy

`dashboard_module_builder.py` does not import `dashboard_service.py`.
`dashboard_service.py` injects key metric construction, portfolio compact
construction, portfolio compact status, core metric keys, AI-blocked statuses,
and historical-derived metric-key sets as callbacks/configuration.

This avoids a circular dependency while preserving the old
`dashboard_service._build_modules(...)` surface.

## Behavior Boundaries

No dashboard public API, model semantics, public output keys, module keys, key
metric semantics, AI context eligibility, cache semantics, `write_last_good`
behavior, route behavior, frontend behavior, external AI behavior, live
fetch/write behavior, prediction output, probability output, return estimate,
allocation output, or trading advice changed.

Phase E extracts DashboardModule construction only. It does not move
`_build_metric`, `_key_metrics_for_module`, historical derived application
logic, portfolio compact builders, `METRIC_SPECS`, `CORE_METRIC_KEYS`,
`DERIVED_METRIC_KEYS`, `LABOR_METRIC_SPECS`, portfolio constants, or last-good
write logic.

## Compatibility

The following legacy names remain available on `dashboard_service.py`:

- `_build_modules`
- `_market_module`
- `_portfolio_module`
- `_module`
- `_module_status_with_coverage`
- `_summary_with_coverage_note`
- `_equity_historical_derived_metrics_available`
- `_proxy_historical_derived_metrics_available`
- `_market_stress_historical_derived_metrics_available`
- `_latest_metric_generated_at`

## Line Count

- `dashboard_service.py` before Phase E: 2913 lines
- `dashboard_service.py` after Phase E: 2704 lines
- `dashboard_module_builder.py`: 469 lines

## Validation

- `PYTHONIOENCODING=utf-8 python -m pytest -q tests/dashboard/test_dashboard_module_builder.py tests/api/test_app_backend_dashboard_summary.py tests/api/test_app_backend_dashboard_key_metrics.py`: passed, 22 tests
- `PYTHONIOENCODING=utf-8 python -m pytest -q tests/dashboard/test_dashboard_module_builder.py tests/api/test_app_backend_dashboard_summary.py tests/api/test_app_backend_dashboard_key_metrics.py tests/dashboard/test_dashboard_historical_derived_integration.py tests/dashboard/test_dashboard_model_pipeline.py tests/dashboard/test_dashboard_context_cache.py tests/dashboard/test_dashboard_evidence_policy.py tests/api/test_app_backend_dashboard_evidence_table.py tests/api/test_app_backend_dashboard_metadata_semantics.py tests/api/test_app_backend_dashboard_provenance.py tests/api/test_app_backend_dashboard_portfolio_deviation.py`: passed, 98 tests
- `PYTHONIOENCODING=utf-8 python -m pytest -q`: passed, 1445 tests, 1 existing Starlette/httpx deprecation warning
- `python scripts/benchmark_dashboard_pipeline.py`: passed; evidence rows 219, included facts 119, included model outputs 63
- `python scripts/audit_data_pipeline_coverage.py`: passed; overall status degraded for existing portfolio deviation pressure
- `python scripts/run_historical_validation.py --format text`: passed; 11 events, 0 boundary violations
- `python scripts/dev_check_validator_boundaries.py`: passed; allowed=9 blocked=8 regression=17
- `git diff --check`: passed with Windows CRLF normalization warning only

## Next Recommended Task

Phase F1 dashboard metric characterization tests before metric builder
extraction. Do not jump directly into moving `_build_metric` without those
characterization tests.
