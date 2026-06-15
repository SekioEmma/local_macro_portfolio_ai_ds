# Dashboard Orchestration Audit

Performed as M7/M8-A on 2026-06-15 against commit 57e77b1.

## Scope

`src/app_backend/services/dashboard_service.py` (3521 lines).

---

## Responsibilities inventory

### Report loading
- `_load_dashboard_reports` / `_load_report` — reads market_snapshot, market_temperature,
  portfolio_snapshot, provider_health, and optionally llm_context_pack from the reports
  directory. Safe to keep in `dashboard_service.py`; no model logic here.

### Summary / module assembly
- `build_dashboard_summary` — public entry point for the summary API.
- `_build_modules`, `_market_module`, `_portfolio_module`, `_module` — assemble
  `DashboardModule` objects from report states. Depend heavily on report-shape helpers and
  the metric-spec constants. Safe to keep in `dashboard_service.py`.

### Base evidence row construction
- `_evidence_rows_from_summary` — converts summary modules to evidence rows using the
  shared `_evidence_row` factory.
- `_labor_macro_evidence_rows` — builds labor metric rows with optional market-history
  fallback. Uses `LABOR_METRIC_SPECS`, `LABOR_HISTORICAL_DERIVED_METRIC_KEYS`.
- Both call `_evidence_row`, which applies the AI eligibility and freshness gate logic.
  These should remain in `dashboard_service.py` because they couple tightly to report
  loading and module helpers.

### Model row builder responsibilities (the 10-step pipeline)
Sequence in `build_dashboard_evidence_table`:
1. D13 — `_historical_risk_percentile_evidence_rows` (db_path only)
2. D14 — `_liquidity_funding_stress_evidence_rows` (db_path only)
3. D10 — `_financial_stress_composite_evidence_rows` (consumes base + D13 + D14)
4. D11 — `_pullback_systemic_checklist_evidence_rows` (consumes all above)
5. D17 — `_growth_inflation_macro_pack_evidence_rows` (consumes all above)
6. D18 — `_valuation_equity_structure_evidence_rows` (consumes all above)
7. D15 — `_macro_regime_review_evidence_rows` (consumes all above)
8. D19 — `_historical_validation_evidence_rows` (db_path only)
9. D16 — `_scenario_stress_evidence_rows` (consumes all above)
10. Stage 8 — `_portfolio_exposure_overlay_evidence_rows` (consumes all above except D16)

Each wrapper is 4–6 lines: convert rows to dicts, call data_quality builder, wrap in
`_evidence_row`. **This entire sequence is a candidate for extraction (M7/M8-A).**

### AI eligibility / source / freshness gate responsibilities
- `_evidence_row` — central factory; applies `_evidence_ai_context_allowed`,
  `_evidence_value_text`, and `_ai_context_blocked_reason`.
- `_evidence_ai_context_allowed`, `_ai_context_allowed`, `_ai_context_blocked_reason`,
  `_ppi_observation_date_blocked_reason` — pure functions; policy-critical.
- Constants: `AI_BLOCKED_METRIC_STATUSES`, `AI_BLOCKED_FRESHNESS_STATUSES`,
  `AI_BLOCKED_SOURCE_BADGES`.
- These should **not** move to the pipeline module to avoid a back-import into
  `dashboard_service.py` (which still uses `AI_BLOCKED_*` in `_build_metric` and
  `_labor_history_fallback_needed`). Passed into the pipeline as a callable.

### Filter / response assembly
- `apply_evidence_filters`, `_evidence_filters`, `_last_good_write_allowed`,
  `_save_last_good_candidates` — post-assembly steps. Stay in `dashboard_service.py`.

---

## What is safe to move now (M7/M8-A)

- The 10 thin model-row wrapper calls (D13 → D14 → D10 → D11 → D17 → D18 → D15
  → D19 → D16 → Stage 8) plus the final `rows` and `row_groups` assembly.
- `_model_to_dict` — trivial 3-line helper, safe to copy into the pipeline module.
- All 10 `data_quality.*` imports that are only used by these wrappers.

## What should remain in `dashboard_service.py` for now

- `_evidence_row` and all its gate helpers (`_ai_context_allowed`,
  `_ai_context_blocked_reason`, `AI_BLOCKED_*` constants).
- All report-loading helpers (`_load_dashboard_reports`, `_load_report`).
- All module-assembly helpers (`_build_modules`, `_market_module`, etc.).
- All base-row builders (`_evidence_rows_from_summary`, `_labor_macro_evidence_rows`).
- All filter, freshness, and last-good-cache logic.
- `ReportState`, `PortfolioDeviationCompact`, `METRIC_SPECS`, `CORE_METRIC_KEYS`, etc.

## Risks for Stage 9.3 using manifest/evidence without shared context

- `build_dashboard_evidence_table` caches its result in `DashboardPipelineContext`
  only when all filters are `None` and `write_last_good=False`. A Stage 9 surface
  that calls evidence with any filter active will rebuild the full pipeline.
- The model pipeline currently receives `base_rows` as input. If a Stage 9 path
  calls `build_dashboard_model_rows` separately from the base-row build it will get
  a divergent `base_rows` snapshot. The shared-context guard in
  `build_dashboard_evidence_table` prevents this for the existing HTTP paths, but
  a future direct call to the pipeline helper would bypass it.
- Recommended: Stage 9.3 should always go through `build_dashboard_evidence_table`
  (or `build_ai_context_manifest`) rather than calling `build_dashboard_model_rows`
  directly, to keep the shared context guarantee.

---

## M7/M8-B remaining work (future)

- Make `_evidence_row` importable (rename or re-export) so the pipeline module
  can own the eligibility conversion without the callable parameter pattern.
- Consider moving `AI_BLOCKED_*` constants and `_evidence_row` helpers to a shared
  `dashboard_ai_gates.py` to eliminate the callable argument.
- Evaluate registry-driven row ordering once all models have stable public output
  key sets in `ModelRegistry`.
- Add a CI-friendly row-count threshold guard (M11 overlap).
