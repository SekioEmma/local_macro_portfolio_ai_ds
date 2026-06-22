# P-M3 Historical Risk Normalization Metadata Helper Split

## Scope

Behavior-preserving metadata helper extraction from Historical Risk
Normalization.

## What Moved

- reliability metadata
- divergence metadata
- method agreement / alignment
- credit OAS coverage metadata
- provider rebuild status
- OAS substitution policy
- current-level availability

## What Did Not Change

- percentile formula
- z-score formula
- robust-z formula
- 5Y/3Y gates
- exact 1095-day fallback gate
- output fields
- `AUXILIARY_CONTEXT_FIELDS`
- AI context eligibility
- trigger eligibility
- BAA10Y proxy/reference policy
- provider/endpoint/frontend/external AI

## Compatibility

Historical Risk Normalization keeps the same payload fields and public
behavior. `historical_percentile_metrics.py` keeps private compatibility
aliases for reliability/divergence and credit OAS coverage helpers.

The new metadata module duplicates small stable status constants to avoid a
circular import. Tests assert those values still align with
`historical_percentile_metrics.py`.

## Validation

- `PYTHONIOENCODING=utf-8 python -m pytest -q tests/test_historical_percentile_metadata_helpers.py tests/test_historical_percentile_metrics.py tests/test_d13_reliability_divergence_metadata.py tests/test_d13_credit_oas_coverage_metadata.py`
- `PYTHONIOENCODING=utf-8 python -m pytest -q tests/test_s1_d16_scenario_refinement.py tests/test_golden_output_contract.py tests/test_ai_context_manifest.py tests/test_ai_memo_contract.py`
- `PYTHONIOENCODING=utf-8 python -m pytest -q`
- `python scripts/benchmark_dashboard_pipeline.py`
- `python scripts/audit_data_pipeline_coverage.py`
- `python scripts/run_historical_validation.py --format text`
- `python scripts/dev_check_validator_boundaries.py`
- `git diff --check`

## Status

P-M3 Historical Risk Normalization metadata helper split: completed.

Next recommended task: P-M4 M11 cross-request shared context cache design, or
pause for manual review before cache work.
