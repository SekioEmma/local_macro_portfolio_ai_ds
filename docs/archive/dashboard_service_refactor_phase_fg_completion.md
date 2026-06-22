# Dashboard Service Refactor Phase F/G - Completion

## Scope

Phase F/G completes the remaining `dashboard_service.py` refactor after Phase
F2 metric builder extraction.

Phase F extracts the remaining metric-adjacent behavior into focused modules:

- `dashboard_historical_derived.py`: historical-derived candidate application,
  PPIFIS history fallback, labor history fallback, and compact DGS fallback
  observations.
- `dashboard_portfolio_compact.py`: sanitized portfolio compact parsing,
  portfolio deviation metrics, stale/freshness handling, and local portfolio
  compact status helpers.
- `dashboard_derived_metrics.py`: credit stress status, real-yield pressure
  status, DGS30 distance/breakout checks, Nasdaq-vs-S&P spread, dependency
  blocking, and derived metric response helpers.

Phase G moves static metric catalog data and key-metric routing out of the
service facade:

- `dashboard_metric_catalog.py`: dashboard module keys, metric specs, core
  metric keys, derived key sets, aliases, and static missing-reason constants.
- `dashboard_key_metrics.py`: key-metric routing with callback/configuration
  injection.

## Compatibility

`dashboard_service.py` remains the public orchestration facade. Existing public
functions, constants, and legacy private helper names are still available from
`dashboard_service.py` through imports or thin wrappers.

The extracted modules do not import `dashboard_service.py`; configuration and
callbacks are injected from the facade where needed. This preserves existing
monkeypatch surfaces such as `_build_metric`, `_apply_historical_derived_metrics`,
`_apply_ppi_final_demand_history`, and `_compact_dgs_fallback_observations`.

## Boundaries Preserved

Phase F/G does not change dashboard public APIs, module keys, metric keys,
`DashboardMetric` schema, source_badge/freshness/AI-context semantics, PPI
Final Demand / PPIACO boundaries, historical-derived gating, portfolio compact
privacy boundaries, cache behavior, `write_last_good`, providers, endpoints,
frontend UI, external AI, Tavily/search, live fetches, live writes,
prediction/probability outputs, return estimates, allocation outputs, or
trading advice.

## Validation

- `python -m pytest -q tests/dashboard/test_dashboard_metric_builder_characterization.py tests/dashboard/test_dashboard_historical_derived_integration.py tests/api/test_app_backend_dashboard_portfolio_deviation.py tests/dashboard/test_dashboard_module_builder.py tests/api/test_app_backend_dashboard_key_metrics.py`:
  69 passed, 1 warning.
- `python -m pytest -q tests/api/test_app_backend_dashboard_summary.py tests/api/test_app_backend_dashboard_evidence_table.py tests/api/test_app_backend_dashboard_metadata_semantics.py tests/api/test_app_backend_dashboard_provenance.py tests/api/test_app_backend_dashboard_portfolio_deviation.py tests/dashboard/test_dashboard_model_pipeline.py tests/dashboard/test_dashboard_context_cache.py tests/dashboard/test_dashboard_evidence_policy.py`:
  64 passed, 1 warning.
- `python -m pytest -q tests/ai/test_ai_context_manifest.py tests/ai/test_ai_memo_contract.py tests/ai/test_stage9_2_security_closeout.py tests/contracts/test_golden_output_contract.py`:
  93 passed, 1 warning.
- `python -m pytest -q`: 1477 passed, 1 warning.
- `python scripts/benchmark_dashboard_pipeline.py`: passed; evidence rows 219,
  included facts 119, included model outputs 63, shared context reuse true.
- `python scripts/audit_data_pipeline_coverage.py`: passed with
  `overall_status=degraded`; degraded reason remained
  `portfolio_deviation: module_status=pressure`.
- `python scripts/run_historical_validation.py --format text`: passed with
  `status=available`, 11 events total, and 0 boundary violations.
- `python scripts/dev_check_validator_boundaries.py`: passed with allowed=9,
  blocked=8, regression=17.

## Next

Manual review / route decision. Do not automatically proceed to Stage 9
productization, external AI, Chat UI, Tavily/search, live provider writes, or
financial advice surfaces.
