# Data Foundation Gap Fill v1

Status: completed.

This task cleans up source-gated data foundation gaps before frontend work. It
is an offline registry, audit, test, and governance-doc pass. It does not fetch
provider data, write local market history, change dashboard APIs, change model
semantics, or add frontend behavior.

## Scope

Included:

- Reclassified `data_quality.ppi_final_demand` from `research_needed` to
  `official_or_public_data_api` now that the project already uses FRED
  `PPIFIS` for PPI final demand.
- Added `scripts/audit_data_foundation_gaps.py`, a read-only source-governance
  audit for current source registry gaps.
- Added data-quality tests for PPI Final Demand / PPIACO separation,
  valuation/FedWatch fact-layer blocking, BAA reference-only guardrails, and
  D14 liquidity/funding source mappings.
- Updated governance docs so the immediate route reflects this completed
  source-gated cleanup.

Excluded:

- No production model-code changes.
- No frontend, API, endpoint, schema, or AI-context behavior changes.
- No live provider fetches and no local market-history writes.
- No `.env`, `configs/external_llm.yaml`, provider payload, cache, output, or
  private data changes.
- No valuation, earnings, FedWatch, consensus, or true-breadth source
  promotion.

## Source Registry Decisions

### PPI Final Demand

`ppi_final_demand` is source-verified as FRED `PPIFIS` in:

- `fred_series.ppi_final_demand`
- `deepseek_market_data_package.inflation_indicators.ppi_final_demand`
- `official_macro_pack.OFFICIAL_MACRO_METRICS["ppi_final_demand"]`

The registry now treats `data_quality.ppi_final_demand` as
`official_or_public_data_api`. This is the headline final demand PPI index and
remains distinct from `PPIACO`. The index level must not be treated as YoY;
`ppi_final_demand_yoy` remains history-gated and requires at least 13 monthly
`PPIFIS` observations.

### D14 Liquidity / Funding Stress

The audited D14 source mappings are:

| Metric | Source series | Source badge |
|---|---|---|
| `sofr` | `SOFR` | `official` |
| `effr` | `EFFR` | `official` |
| `iorb` | `IORB` | `official` |
| `on_rrp` | `RRPONTSYD` | `official` |
| `commercial_paper_rate` | `DCPF3M` | `official_fallback` |
| `stl_fsi` | `STLFSI4` | `official_fallback` |
| `nfci` | `NFCI` | `official_fallback` |
| `anfci` | `ANFCI` | `official_fallback` |

`ofr_fsi` remains `research_needed` with
`missing_reason=source_mapping_required` and
`ai_context_allowed_rule=never_until_source_mapping_verified`.

### Fact-layer Blocks

The following remain intentionally outside the audited factual layer:

- `valuation_proxy`
- `fedwatch_probability`

They stay `not_available` until a stable, auditable source is explicitly
selected in a future approved task.

`BAA10Y` / `BAA10YM` remain long-history credit proxy/reference series only.
They must not be used as HY/IG OAS aliases.

## Audit CLI

`scripts/audit_data_foundation_gaps.py` is read-only and network-free. It
checks:

- inconsistent source tiers;
- research-needed items that must remain gated;
- not-available factual-layer blocks;
- official mapping candidates;
- forbidden BAA alias risks;
- source-badge policy;
- missing metadata on blocked / research-needed / not-available rows.

The CLI exits nonzero only on `error` findings.

## Validation

Final local validation for this task:

- `python -m pytest -q tests/data_quality/test_data_foundation_source_registry.py tests/data_quality/test_liquidity_funding_source_registry.py tests/data_quality/test_liquidity_funding_stress.py tests/dashboard/test_dashboard_metric_builder_characterization.py tests/dashboard/test_dashboard_historical_derived_integration.py`:
  73 passed, 1 existing Starlette/TestClient deprecation warning.
- `python -m pytest -q tests/api/test_app_backend_dashboard_summary.py tests/api/test_app_backend_dashboard_evidence_table.py tests/api/test_app_backend_dashboard_key_metrics.py tests/ai/test_ai_context_manifest.py tests/contracts/test_golden_output_contract.py`:
  36 passed, 1 existing Starlette/TestClient deprecation warning.
- `python scripts/audit_data_foundation_gaps.py`: PASS, 12 findings, 0 errors.
- `python scripts/audit_data_pipeline_coverage.py`: exit 0,
  `overall_status=degraded`, `hard_failures=0`,
  degraded reason `portfolio_deviation: module_status=pressure` (existing
  baseline behavior).
- `python scripts/run_historical_validation.py --format text`: passed; 11
  events total, 2 available, 3 limited, 6 insufficient, 0 boundary violations.
- `python scripts/dev_check_validator_boundaries.py`: passed; allowed=9,
  blocked=8, regression=17.
- `python -m pytest -q`: 1488 passed, 1 existing Starlette/TestClient
  deprecation warning.
- `python scripts/benchmark_dashboard_pipeline.py`: passed; 219 evidence rows,
  119 included facts, 63 included model outputs, shared context available,
  estimated rebuilds avoided=2.

## Next Route

Recommended next step after G0:

- manual local data refresh only with explicit user approval; or
- UI-0/UI-1 frontend data-display work using existing backend APIs and source
  gates.

Do not treat this task as approval for live provider writes, Stage 9
productization, Chat UI, Tavily/search, external AI, prediction/probability
outputs, or trading/allocation language.
