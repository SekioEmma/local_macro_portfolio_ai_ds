# Foundation Stabilization Backlog

Stage 8.5 closeout accepted this backlog as non-blocking future work. M7/M8 are
important before complex Stage 9 implementation, but they are not required
before Stage 9 preparation. Do not resolve M7-M12 inside the Stage 8.5 closeout
task. Stage 9.0 AI Readiness Design should cross-reference M12 and keep AI
Context Manifest contract hardening active during all later Stage 9 work.

This backlog documents maintainability risks and future work without converting
orchestration or adding Stage 9 features now.

## M7 Dashboard Orchestration Cleanup

### M7/M8-A — COMPLETED 2026-06-15 (behavior-preserving extraction, commit on app-mvp)

Extraction summary:
- Created `src/app_backend/services/dashboard_model_pipeline.py` with
  `build_dashboard_model_rows(*, base_rows, db_path, build_evidence_row)` and
  `DashboardModelPipelineResult(rows, row_groups)`.
- The D13→D14→D10→D11→D17→D18→D15→D19→D16→Stage8 sequence is now in one named
  function outside `dashboard_service.py`.
- Removed 10 thin private wrapper functions and 10 data_quality imports from
  `dashboard_service.py` (3521 → 3320 lines).
- `dashboard_service.py` remains the public entry point; it calls
  `build_dashboard_model_rows` and passes `_evidence_row` as a callable to
  avoid circular imports.
- Behavior-preservation confirmed: benchmark row count 219, included facts 119,
  included model outputs 63 — identical to Stage 8.5 baseline. All 586 tests
  pass. Validator boundaries unchanged (allowed=9 blocked=8 regression=17).
- Audit documented in `docs/dashboard_orchestration_audit.md`.
- Tests added in `tests/test_dashboard_model_pipeline.py` (14 tests).

Not done in M7/M8-A (remains for M7/M8-B):
- `_evidence_row` and AI eligibility helpers stay in `dashboard_service.py`
  (moving them requires a shared utility module to avoid circular imports).
- `AI_BLOCKED_*` constants remain in `dashboard_service.py` (used in
  `_build_metric` and `_labor_history_fallback_needed`).
- Pipeline is not yet registry-driven; build order is still explicit.
- No cross-request caching guard added (M11 overlap).

### M7/M8-B — remaining work

- Move `_evidence_row` and its helpers (`_ai_context_allowed`,
  `_ai_context_blocked_reason`, `AI_BLOCKED_*` constants) to a shared module
  (e.g., `dashboard_ai_gates.py`) to eliminate the `build_evidence_row: Callable`
  parameter from `build_dashboard_model_rows`.
- Evaluate registry-driven row ordering once all models have stable public output
  keys in `ModelRegistry`.
- Consider adding a CI row-count threshold guard (M11 overlap).
- Validation needed: same as M7/M8-A plus the callable parameter removal.

---

Original M7 risk note (still partially applies to M7/M8-B):

- Original risk: `dashboard_service.py` still contains a long sequential chain
  that builds base rows, D13, D14, D10, D11, D17, D18, D15, D19, D16, and Stage
  8 rows in one function.
- Why it matters: future Stage 9 surfaces could accidentally call summary,
  evidence, and manifest paths separately and rebuild the same chain.

## M8 Registry-driven Model Row Builder

### M8-A — covered by M7/M8-A above

The D13→Stage8 sequence is now in `build_dashboard_model_rows`. Row construction
is still hand-ordered (not registry-driven), but is now in one testable location.

### M8-B — remaining work

- Introduce `build_registered_model_rows` for modules whose dependencies are
  explicit and stable, beginning with pure row-to-row builders.
- Not-now boundary: do not convert all orchestration before Stage 9.3 is scoped.
- Validation needed: generated row count, public output keys, source badges,
  AI-context eligibility, and golden output contract equality.

## M9 Audit Registry Decoupling

- Current risk: audit sections remain coupled to specific module names,
  public-key sets, and bespoke dictionaries.
- Affected files/functions: `scripts/audit_data_pipeline_coverage.py`,
  `scripts/audit_sections/module_audits.py`, and
  `scripts/audit_sections/manifest_audit.py`.
- Why it matters: adding future modules can drift audit configuration away from
  ModelRegistry and MetricLookup.
- Proposed future task: let audit sections read configured public outputs and
  boundary policies from ModelRegistry where the contract is already stable.
- Not-now boundary: do not redesign audit output schema in Stage 8.5.
- Validation needed: audit structural tests, exact top-level keys, and Stage 8
  configured/missing public-output checks.

## M10 Frontend/Backend Registry Drift Guard

- Current risk: frontend labels and interpretation boundaries live in
  `app_frontend/src/utils/moduleRegistry.ts` and `metricRegistry.ts`, separate
  from backend ModelRegistry and MetricLookup.
- Affected files/functions: frontend registry files, `src/modeling/`, and
  `tests/test_golden_output_contract.py`.
- Why it matters: Stage 8 labels, boundaries, or keys could drift between API
  payloads and UI rendering.
- Proposed future task: add a generated or checked contract artifact comparing
  backend model public keys to frontend registry keys.
- Not-now boundary: do not generate frontend code or add a new frontend page in
  Stage 8.5.
- Validation needed: frontend typecheck/build and registry consistency tests.

## M11 Performance Regression Guard

- Current risk: benchmark output confirms DashboardPipelineContext reuse within
  one call chain, but separate frontend HTTP requests can still rebuild summary
  and evidence independently.
- Affected files/functions: `scripts/benchmark_dashboard_pipeline.py`,
  `src/app_backend/services/dashboard_context.py`,
  `src/app_backend/services/dashboard_service.py`, and
  `src/app_backend/services/ai_context_service.py`.
- Why it matters: Stage 9 could introduce repeated manifest or evidence builds
  if it bypasses shared context.
- Proposed future task: add a CI-friendly benchmark threshold or structural
  guard for reuse flags and rebuild counts.
- Not-now boundary: do not add cross-request caching or process-level cache in
  Stage 8.5.
- Validation needed: benchmark script run, reuse flags true, no new live
  fetch/query source introduced, and documented remaining hotspots.

## M12 AI Context Manifest Contract Hardening

- Current risk: manifest inclusion/exclusion behavior is policy-critical and
  future AI surfaces may be tempted to broaden eligibility.
- Affected files/functions: `src/app_backend/services/ai_context_service.py`,
  `tests/test_ai_context_manifest.py`, and Stage 8-specific manifest tests.
- Why it matters: Stage 8 private-input-excluded or insufficient-evidence rows
  must not become factual/model support, and search-derived/proxy/stale rows
  must remain blocked according to policy.
- Proposed future task: keep manifest contract tests close to each new model or
  AI surface and require explicit negative fixtures for blocked rows.
- Not-now boundary: do not broaden AI context eligibility to make Stage 9 easier.
- Validation needed: manifest tests for included/excluded model outputs, risk
  boundaries, privacy policies, and D15/D16/D19 non-interference.
