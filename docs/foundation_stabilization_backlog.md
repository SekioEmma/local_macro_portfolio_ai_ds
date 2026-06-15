# Foundation Stabilization Backlog

Stage 8.5 closeout accepted this backlog as non-blocking future work. M7/M8 are
important before complex Stage 9 implementation, but they are not required
before Stage 9 preparation. Do not resolve M7-M12 inside the Stage 8.5 closeout
task.

This backlog documents maintainability risks and future work without converting
orchestration or adding Stage 9 features now.

## M7 Dashboard Orchestration Cleanup

- Current risk: `dashboard_service.py` still contains a long sequential chain
  that builds base rows, D13, D14, D10, D11, D17, D18, D15, D19, D16, and Stage
  8 rows in one function.
- Affected files/functions: `src/app_backend/services/dashboard_service.py`,
  especially `build_dashboard_evidence_table` and the private
  `_..._evidence_rows` builders.
- Why it matters: future Stage 9 surfaces could accidentally call summary,
  evidence, and manifest paths separately and rebuild the same chain.
- Proposed future task: split orchestration into a small pipeline builder that
  returns named row groups while preserving the public dashboard service entry
  points.
- Not-now boundary: do not rewrite production model logic or change D10-D19 /
  Stage 8 financial meanings during Stage 8.5.
- Validation needed: exact evidence-table JSON equality against baseline,
  benchmark reuse flags, audit output equality where practical, and full
  dashboard contract tests.

## M8 Registry-driven Model Row Builder

- Current risk: several model row builders are still hard-wired in
  `dashboard_service.py`: financial stress, pullback checklist,
  growth/inflation macro pack, valuation/equity structure, macro regime review,
  scenario stress, historical validation, and portfolio exposure overlay.
- Affected files/functions: `dashboard_service.py`,
  `src/modeling/model_registry.py`, and individual modules under
  `src/data_quality/`.
- Why it matters: ModelRegistry already defines public keys and policies, but
  row construction is still hand ordered in the service layer.
- Proposed future task: introduce `build_registered_model_rows` for modules
  whose dependencies are explicit and stable, beginning with pure row-to-row
  builders.
- Not-now boundary: do not convert all orchestration during Stage 8.5.
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
