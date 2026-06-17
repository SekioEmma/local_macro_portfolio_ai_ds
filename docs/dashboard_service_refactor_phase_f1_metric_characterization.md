# Dashboard Service Refactor Phase F1 - Metric Characterization

## Scope

Add characterization tests before extracting metric builder logic.

Phase F1 is tests and documentation only. It does not move production metric
builder functions.

## What Is Locked

- `_build_metric` missing/current/stale behavior
- source/source_badge/source_series/freshness/observation_date/generated_at derivation
- official macro missing behavior
- PPI Final Demand / PPIACO boundary
- inflation YoY index-level guard
- `_key_metrics_for_module` special routing
- derived-first / portfolio-compact-first order
- dependency unusable behavior
- AI context gate outcomes
- legacy `dashboard_service` callable surface

## What Does Not Move Yet

- `_build_metric`
- `_key_metrics_for_module`
- historical derived functions
- portfolio compact functions
- metric specs/constants

## Why

Phase F2 will extract `dashboard_metric_builder.py`. These tests provide a
safety net before that production refactor.

## Validation

- `PYTHONIOENCODING=utf-8 python -m pytest -q tests/dashboard/test_dashboard_metric_builder_characterization.py`: passed, 27 tests
- `PYTHONIOENCODING=utf-8 python -m pytest -q tests/dashboard/test_dashboard_metric_builder_characterization.py tests/dashboard/test_dashboard_module_builder.py tests/api/test_app_backend_dashboard_key_metrics.py tests/dashboard/test_dashboard_historical_derived_integration.py`: passed, 61 tests, 1 existing Starlette/httpx deprecation warning
- `PYTHONIOENCODING=utf-8 python -m pytest -q tests/api/test_app_backend_dashboard_summary.py tests/api/test_app_backend_dashboard_evidence_table.py tests/api/test_app_backend_dashboard_metadata_semantics.py tests/api/test_app_backend_dashboard_provenance.py tests/api/test_app_backend_dashboard_portfolio_deviation.py tests/dashboard/test_dashboard_model_pipeline.py tests/dashboard/test_dashboard_context_cache.py tests/dashboard/test_dashboard_evidence_policy.py`: passed, 64 tests, 1 existing Starlette/httpx deprecation warning
- `PYTHONIOENCODING=utf-8 python -m pytest -q tests/ai/test_ai_context_manifest.py tests/ai/test_ai_memo_contract.py tests/ai/test_stage9_2_security_closeout.py tests/contracts/test_golden_output_contract.py`: passed, 93 tests, 1 existing Starlette/httpx deprecation warning
- `PYTHONIOENCODING=utf-8 python -m pytest -q`: passed, 1472 tests, 1 existing Starlette/httpx deprecation warning
- `python scripts/benchmark_dashboard_pipeline.py`: passed; evidence rows 219, included facts 119, included model outputs 63
- `python scripts/audit_data_pipeline_coverage.py`: passed; overall status degraded for existing portfolio deviation pressure
- `python scripts/run_historical_validation.py --format text`: passed; 11 events, 0 boundary violations
- `python scripts/dev_check_validator_boundaries.py`: passed; allowed=9 blocked=8 regression=17
- `git diff --check`: passed with Windows CRLF normalization warning only

## Next

Phase F2 extract `dashboard_metric_builder.py`, using wrappers/aliases in
`dashboard_service.py`. Do not mark Phase F2 complete until that extraction is
implemented and validated separately.
