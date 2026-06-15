# Current Project State

## Identity

Local Macro Portfolio AI DS is a local-first macro risk research workbench.

It is designed as:

- A macro risk evidence system.
- An explainable financial and math model layer.
- A personal portfolio risk explanation layer.
- An AI research context foundation.
- A Chinese professional research report system.

It is not:

- An auto-trading system.
- A short-term prediction engine.
- An AI stock picker.
- A news sentiment trading system.
- A portfolio optimizer.
- A brokerage sync tool.
- A real-time market terminal.

## Current Phase

Stage 8.5 Foundation Stabilization Sprint is completed. Stage 8 Portfolio
Exposure Overlay v0 is complete. Stage 9.1 Memo Template / Context Contract is
completed. Stage 9.2 Mock Chat / Mock Memo is completed as local preview API
surfaces only. Stage 9.3-A DeepSeek adapter skeleton is complete as a
disabled-by-default, fake-client-only internal adapter contract.

The current next step is Stage 9.3-B implementation decision / explicit
approval review, not automatic real DeepSeek integration. Stage 9.3-A skeleton,
Stage 9.3-A closeout / adapter guard hardening, Stage 9.3-B readiness seam
audit, and Stage 9.3-B-0 runtime approval gate are all complete. None of these
call external models, read API keys or `.env`, or add HTTP routes. None of
them authorize Stage 9.3-B. Real DeepSeek integration remains not implemented
and requires a separate explicit approval task.

## Current Baseline

- Branch before work: `app-mvp`.
- Current frozen foundation baseline: `cc5c1aa Stabilize Stage 8 foundation`.
- Commit before Stage 8.5 stabilization work: `f47575a Add portfolio exposure overlay`.
- Upstream before work: `origin/app-mvp`, aligned with local branch.
- `main` is the old stable baseline and must not be modified for current
  `app-mvp` work.

Validation baseline captured during Stage 8.5 preflight:

- `python scripts/benchmark_dashboard_pipeline.py`: passed.
- Benchmark evidence rows: 219.
- Included facts: 119.
- Included model outputs: 63.
- Market history: 33803 observations / 45 metrics.
- Legacy total latency: 7247.83 ms.
- Shared pipeline context total latency: 3385.64 ms.
- Dashboard summary latency: 744.55 ms legacy / 759.01 ms shared.
- Evidence table latency: 3140.64 ms legacy / 2624.77 ms shared.
- AI context manifest latency: 3362.64 ms legacy / 1.86 ms shared.
- Audit latency inside benchmark: 7979.45 ms.
- PipelineContext available: true.
- Summary reused by evidence: true.
- Evidence reused by manifest: true.
- Estimated rebuilds avoided: 2.
- D13 query strategy: batch.
- D14 query strategy: batch.
- `python scripts/audit_data_pipeline_coverage.py`: passed, `overall_status=degraded`.
- Audit degraded reason: `portfolio_deviation: module_status=pressure`.
- Stage 8 audit status: `portfolio_exposure_overlay_available=true`,
  `overlay_status=available`, 18 configured public outputs, no missing public
  output keys.
- Stage 8 privacy flags: reads holdings line items false, returns holdings
  line items false, returns position weights false, returns account values
  false, sanitized compact context only true.
- Stage 8 hard gates: downstream-only true, cannot trigger macro regime true,
  cannot trigger systemic stress true, cannot change scenario severity true.
- `python scripts/run_historical_validation.py --format text`: passed.
- Historical validation summary: 11 events total, 2 available, 3 limited,
  6 insufficient, 0 boundary violations.
- `PYTHONIOENCODING=utf-8 python -m pytest -q`: 459 passed, 1 warning.
- Targeted Stage 8.5 and related contract tests: passed after stabilization
  edits; see final run log for exact command list.
- `cd app_frontend && npm run typecheck`: passed.
- `cd app_frontend && npm run build`: passed.
- `python scripts/dev_check_validator_boundaries.py`: passed,
  `allowed=9 blocked=8 regression=17`.
- `git diff --check`: passed.
- Preflight `git status --short --untracked-files=all`: clean.

This Stage 8.5 baseline supersedes the older Stage 2 values previously listed
in this file, including `372 passed`, 131 evidence rows, 95 included facts, and
28 included model outputs.

## Completed Mainline

- D7-D9 data foundation, PPIFIS, drawdown/curve/cross-asset, labor mini-pack, official labor history, labor compact fallback.
- D10 `financial_stress_composite`.
- D11 `pullback_systemic_risk_checklist`.
- D12 AI context manifest / context preview.
- D13 historical percentile / z-score / robust-z.
- D13a-D13c core risk history backfill, percentile bands, D10/D11 integration.
- D14 `liquidity_funding_stress`.
- D14b D14 liquidity/funding confirmation integrated into D10/D11.
- D15 Macro Regime Review v0.
- M1 dashboard pipeline benchmark.
- M2 batch market history reads.
- M3 shared dashboard pipeline context.
- M4a dashboard service helper split.
- M5 audit pipeline modularized.
- M6 frontend display registries organized.
- Stage 2 Golden Output Contract and forbidden-language tests.
- Stage 2.5 D19 Historical Validation v0.
- Stage 3 EvidenceIndex / MetricLookup / Model Registry v0.
- Stage 4 D16 Scenario Stress Test v0.
- Stage 5 D17 Growth / Inflation Macro Pack v0.
- Stage 6 D18 Valuation / Equity Structure v0.
- Stage 7 D19 Expanded Historical Validation v1.
- Stage 8 Portfolio Exposure Overlay v0.
- Stage 9.0 AI Readiness Design.
- Stage 9.1 Memo Template / Context Contract.
- Stage 9.2 Mock Chat / Mock Memo local preview endpoints.
- M7/M8-A dashboard model pipeline extraction (behavior-preserving; row count
  unchanged at 219/119/63; 586 tests pass).
- Stage 9.2 closeout / security review (locked by
  `tests/test_stage9_2_security_closeout.py`; documented in
  `docs/stage9_2_security_review.md`). Stage 9.3 DeepSeek remains
  not implemented and requires explicit approval before work begins; it must
  be disabled by default and behind a user-controlled switch.
- Stage 9.3-A DeepSeek adapter skeleton (disabled-by-default, fake-client-only,
  no network, no API key read, no `.env` read; documented in
  `docs/stage9_deepseek_adapter_design.md`; locked by
  `tests/test_deepseek_adapter_skeleton.py` and
  `tests/test_ai_external_adapter_guards.py`). Stage 9.3-B real DeepSeek
  adapter remains not implemented; Stage 9.3-A does NOT authorize Stage 9.3-B.
- Stage 9.3-A closeout / adapter guard hardening (ExternalAI schemas reject
  extra fields; response guard blocks failed validator results, forbidden
  generated-output terms, and privacy tokens in response content). Stage 9.3-B
  real DeepSeek adapter remains not implemented and not approved.
- Stage 9.3-B readiness review / external AI integration seam audit
  (recursive `raw_request` guard for nested forbidden keys and nested
  forbidden tokens; new `ai_external_request_builder.build_external_ai_request_from_manifest`
  as the only safe manifest→ExternalAIRequest entry point;
  documented seam order in `docs/stage9_deepseek_adapter_design.md`;
  locked by `tests/test_ai_external_request_builder.py` and additional
  nested-input tests in `tests/test_ai_external_adapter_guards.py`).
  Stage 9.3-B real DeepSeek adapter remains not implemented and not approved.
- Stage 9.3-B-0 runtime approval gate / external AI policy contract
  (new `ExternalAIRuntimePolicy` schema with `extra="forbid"`,
  `default_external_ai_runtime_policy()` factory, and
  `guard_external_ai_runtime_policy` / `assert_external_ai_runtime_policy_allowed`
  in `src/app_backend/services/ai_external_runtime_policy.py`; default
  fails closed; pass condition requires every approval gate True AND
  every dangerous permission False; locked by
  `tests/test_ai_external_runtime_policy.py`). No new HTTP routes; no
  network client imported; no env / yaml / file read. Stage 9.3-B real
  DeepSeek adapter remains not implemented and not approved.

## Hard Boundaries

- No allocation directive, action instruction, or return estimate language in public outputs.
- No event-odds, crash-odds, recession-odds, or market-direction probability output.
- `financial_stress_score` is pressure temperature, not probability.
- D15 macro regime review is current evidence review, not a classifier or forecast model.
- D15 exposes bands and ranked evidence, not a public numeric regime score.
- D19 is historical replay / event-window consistency validation, not probability
  modeling or trading performance review.
- Stage 3 is infrastructure and contract consolidation, not new financial model behavior.
- D16 is a hypothetical scenario matrix / current evidence transmission review,
  not a forecast, probability model, allocation directive, or return estimate.
- D17 is a conservative growth/inflation evidence context layer, not a forecast
  or recession call.
- D18 is a conservative valuation/equity-structure research and proxy context
  layer, not a forecast or timing model.
- Stage 8 is a privacy-preserving explanatory overlay using sanitized
  portfolio context only. It does not read or expose holdings line items and
  does not provide allocation advice, action directives, return estimates, or
  probability outputs.
- Stage 8.5 Foundation Stabilization Sprint is complete. It did not implement
  Stage 9, DeepSeek, Tavily, Tauri, AI Chat, or new financial models.
- Stage 9.1 Memo Template / Context Contract is deterministic local rendering
  only. It does not call DeepSeek or Tavily, does not add persistent chat or
  frontend chat UI, and does not expose holdings line items.
- Stage 9.2 Mock Chat / Mock Memo is deterministic local preview API work only.
  It adds context, mock chat, mock memo, and mock report preview endpoints over
  AI Context Manifest and the Stage 9.1 renderer. It does not call DeepSeek or
  Tavily, does not add persistent chat, does not automatically save reports, does
  not add frontend chat UI, and does not expose holdings line items.
- Proxy, search-derived, research-needed, stale, and insufficient-history rows are not official facts.
- Missing data must not be filled by AI.
- The backend must not bind `0.0.0.0`.
- CORS must not use `*`.

## Current Next Step

The current next step is Stage 9.3-B readiness review / external AI integration
seam audit, not Stage 9.3-B real DeepSeek integration. Stage 9.3-A skeleton and
its closeout / adapter guard hardening are both complete.

Stage 9.3-A DeepSeek adapter skeleton is complete as a disabled-by-default,
fake-client-only internal adapter contract. It does not call external models,
does not read API keys or `.env`, does not add HTTP routes, and does not
authorize Stage 9.3-B. Real DeepSeek integration remains not implemented and
requires a separate explicit approval task.

Stage 8 Portfolio Exposure Overlay v0 is complete as a downstream-only,
privacy-preserving explanatory layer. It maps sanitized compact portfolio
context to macro risk channels and existing D10-D19 evidence/model outputs. It
does not read or expose holdings line items and does not provide allocation
advice, action directives, return estimates, or probability outputs. Stage 8.5
Foundation Stabilization Sprint is complete. Stage 9.0 AI Readiness Design,
Stage 9.1 Memo Template / Context Contract, Stage 9.2 Mock Chat / Mock Memo
local preview endpoints, Stage 9.3-A adapter skeleton hardening, Stage
9.3-B readiness review / external AI integration seam audit, and Stage
9.3-B-0 runtime approval gate / external AI policy contract are complete.
Real AI Chat / Memo / Report integrations remain not implemented.
