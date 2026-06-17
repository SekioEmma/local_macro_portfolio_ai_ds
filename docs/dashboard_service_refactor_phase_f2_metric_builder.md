# Dashboard Service Refactor Phase F2 - Metric Builder Extraction

## Scope

Phase F2 extracts dashboard metric object construction and metric metadata
helpers from `dashboard_service.py` into
`src/app_backend/services/dashboard_metric_builder.py`.

The extraction is behavior-preserving. `dashboard_service.py` keeps the legacy
private callable surface through direct aliases or thin wrappers, and injects
local callbacks/configuration into the new builder module.

## Moved Helpers

- metric object construction and missing metric construction
- metric lookup and nested metric payload lookup
- status, freshness, source, source_series, source_badge, date, and generated
  timestamp helpers
- quality metadata lookup helpers
- value formatting and numeric conversion helpers
- inflation YoY index-level guard helpers
- metric interpretation hint helpers
- derived dependency usability helper

## Compatibility Surface

`dashboard_service.py` still exposes the existing private names used by local
tests and downstream internal callers. Helpers that need local configuration,
such as source badge normalization and interpretation hints, remain thin
wrappers. Simple helpers such as `_format_value`, `_metric_status`, and
`_metric_freshness` are direct aliases to `dashboard_metric_builder`.

Constants moved to `dashboard_metric_builder.py` are re-exported by
`dashboard_service.py` through imports:

- `ALLOWED_METRIC_STATUSES`
- `ALLOWED_SOURCE_BADGES`
- `SOURCE_BADGE_ALIASES`
- `INFLATION_YOY_METRIC_KEYS`
- `INDEX_LEVEL_YOY_MISSING_REASON`

The new builder module does not import `dashboard_service.py`.

## Boundaries Preserved

Phase F2 does not change dashboard public APIs, module keys, metric keys,
`DashboardMetric` schema, source_badge/freshness/AI-context semantics, PPI
Final Demand / PPIACO boundaries, cache behavior, `write_last_good`, providers,
endpoints, frontend UI, external AI, Tavily/search, live fetches, live writes,
prediction/probability outputs, return estimates, allocation outputs, or
trading advice.

Phase F2 does not move `_key_metrics_for_module`, historical-derived metric
builders, portfolio compact metric builders, `METRIC_SPECS`, `CORE_METRIC_KEYS`,
`DERIVED_METRIC_KEYS`, `LABOR_METRIC_SPECS`, portfolio constants, or last-good
write logic.

## Validation

- `PYTHONIOENCODING=utf-8 python -m pytest -q tests/dashboard/test_dashboard_metric_builder_characterization.py`: passed, 29 tests
- `PYTHONIOENCODING=utf-8 python -m pytest -q tests/dashboard/test_dashboard_metric_builder_characterization.py tests/dashboard/test_dashboard_module_builder.py tests/api/test_app_backend_dashboard_key_metrics.py tests/dashboard/test_dashboard_historical_derived_integration.py`: passed, 63 tests, 1 existing Starlette/httpx deprecation warning
- `PYTHONIOENCODING=utf-8 python -m pytest -q tests/api/test_app_backend_dashboard_summary.py tests/api/test_app_backend_dashboard_evidence_table.py tests/api/test_app_backend_dashboard_metadata_semantics.py tests/api/test_app_backend_dashboard_provenance.py tests/api/test_app_backend_dashboard_portfolio_deviation.py tests/dashboard/test_dashboard_model_pipeline.py tests/dashboard/test_dashboard_context_cache.py tests/dashboard/test_dashboard_evidence_policy.py`: passed, 64 tests, 1 existing Starlette/httpx deprecation warning
- `PYTHONIOENCODING=utf-8 python -m pytest -q tests/ai/test_ai_context_manifest.py tests/ai/test_ai_memo_contract.py tests/ai/test_stage9_2_security_closeout.py tests/contracts/test_golden_output_contract.py`: passed, 93 tests, 1 existing Starlette/httpx deprecation warning
- `PYTHONIOENCODING=utf-8 python -m pytest -q`: passed, 1474 tests, 1 existing Starlette/httpx deprecation warning
- `python scripts/benchmark_dashboard_pipeline.py`: passed; evidence rows 219, included facts 119, included model outputs 63
- `python scripts/audit_data_pipeline_coverage.py`: passed; overall status remains degraded for existing `portfolio_deviation: module_status=pressure`
- `python scripts/run_historical_validation.py --format text`: passed; 11 events, 0 boundary violations
- `python scripts/dev_check_validator_boundaries.py`: passed; allowed=9 blocked=8 regression=17

## Next

Manual review / Phase F3 route decision. If Phase F3 proceeds, characterize
historical-derived and portfolio-compact metric helper behavior before any
extraction.
