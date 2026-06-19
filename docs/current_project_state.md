# Current Project State

For quick orientation, see `docs/INDEX.md`. The detailed historical state
remains in this document. For the immediate route and the next engineering
task, see `docs/short_term_development_plan.md`. For task-level rules, see
`docs/task_governance_policy.md`.

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

AI-1 Local Controlled Research Preview is completed. The project is entering
AI-1.5 Local Preview Evaluation & Governance Closeout to add local golden
fixtures, structure and adversarial coverage, a reproducible quality audit,
and an evidence-backed AI-2 readiness checklist. This phase remains local-only
and does not authorize an external model, search, persistence, account detail,
prediction, probability, return, allocation, or trading output.

Stage 8.5 Foundation Stabilization Sprint is completed. Stage 8 Portfolio
Exposure Overlay v0 is complete. Stage 9.1 Memo Template / Context Contract is
completed. Stage 9.2 Mock Chat / Mock Memo is completed as local preview API
surfaces only. Stage 9.3-A DeepSeek adapter skeleton is complete as a
disabled-by-default, fake-client-only internal adapter contract.

Current branch: `ai-1-local-research-preview`. `main` remains the stable
baseline and should not be touched for this work.

Current phase: AI-1 Local Controlled Research Preview is complete; AI-1.5
Local Preview Evaluation & Governance Closeout is active. Scenario Stress
Matrix Refinement v1 (legacy: D16) and the subsequent historical foundation,
runtime, governance, data, and frontend-audit work remain completed baselines.
DF-0 Roadmap Arbitration and Legacy Document Cleanup is complete. DF-1 D19 v1
Historical Evidence-row Integration is complete. DF-2 D15/D16 Compliance Audit
is complete. DF-3 D17/D18 Data Gap and Source-gate Review is complete. DF-4
D13 Reliability / Divergence Metadata is complete with scoped D13 production
code edits that add explanatory metadata fields only. DF-4a Credit OAS history
availability audit is complete. DF-4c Credit OAS coverage / provider-rebuild
metadata integration is complete. Stage DF is concluded. Stage S0 Post-DF
Roadmap Reconciliation is complete. S1 D16 Scenario Stress Refinement v1 is
complete. HF-1 Test Runtime Hotfix / DB-backed Fixture Batching is complete.
Optional DF-4d BAA10Y reference documentation is deferred unless explicitly
requested later.
Data Foundation Gap Fill v1 is completed after the Phase F/G dashboard service
refactor as an offline source-registry, audit, tests, and governance-doc task
before frontend work.
Data Foundation G1 Controlled Local Refresh and Coverage Audit is completed
using only existing source-gated ingest scripts. Local market-history coverage
was refreshed without committing generated data or changing production code.

Stage 9.3-B-2d internal one-shot manual invocation review is complete.
External AI line is frozen. Stage 9 Chat / Memo / Report productization remains
not implemented and not current. Stage R1 Course Paper Research Recovery Note is
complete as docs-only research recovery. D19 v0 Historical Validation Event
Registry + Replay Skeleton is complete as a static, local-only event registry
and replay-row scaffold. Stage
9.3-A skeleton, Stage 9.3-A closeout / adapter guard hardening, Stage 9.3-B
readiness seam audit, Stage 9.3-B-0 runtime approval gate, Stage 9.3-B-1
minimal real adapter design + config contract, Stage 9.3-B-2a mocked
transport adapter, Stage 9.3-B-2b real transport code, and Stage 9.3-B-2c
external response guard + validator integration, and Stage 9.3-B security
closeout are all complete. None of these add HTTP routes, frontend chat,
prompt/response persistence, Tavily/search, or automatic external calls.

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
- Data Foundation G1 post-refresh market history: 45243 observations / 45
  metrics.
- Data Foundation G1 post-refresh included facts: 125.
- Data Foundation G1 post-refresh included model outputs: 63.
- Data Foundation G1 post-refresh dashboard `insufficient_history` rows: 0.
- Data Foundation G1 post-refresh D13 history sufficiency: true.
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
- Stage 9.3-B-1 minimal real DeepSeek adapter design + config contract
  (new `DeepSeekProviderMessage` / `DeepSeekProviderPayload` schemas
  with `extra="forbid"`; restricted message roles to
  system/context/summary; `build_deepseek_provider_payload` in
  `src/app_backend/services/deepseek_provider_contract.py` runs
  `guard_request` first and fails closed on any finding; payload schema
  excludes API key, env var name, base URL, endpoint, model name, raw
  question / prompt, holdings / account / position / transaction data,
  raw provider payloads, search results, and local paths; locked by
  `tests/test_deepseek_provider_contract.py`). Stage 9.3-B-2 real
  network adapter remains not implemented and not approved.
- Stage 9.3-B-2a mocked DeepSeek transport adapter
  (`DeepSeekTransportRequest` / `DeepSeekTransportResponse` schemas;
  `DeepSeekTransport` protocol, categorical `DeepSeekTransportError`, and
  deterministic `MockDeepSeekTransport`; `DeepSeekNetworkAdapter` with
  injected transport only). The default remains disabled. The success path
  requires explicit fake config, passing runtime policy, sanitized provider
  payload, mocked transport, `ExternalAIResponse`, and `guard_response`.
  Transport errors, malformed responses, forbidden output terms, and privacy
  tokens all fail closed. No real HTTP, API key, env read, `.env`,
  `external_llm.yaml`, or endpoint was added in 2a; real key/config/network
  transport was deferred to Stage 9.3-B-2b.
- Stage 9.3-B-2b real DeepSeek transport code
  (`deepseek_real_transport.py` with `DeepSeekRealTransport` and
  `load_deepseek_api_key_from_env`). The key read is limited to
  `DEEPSEEK_API_KEY` in the process environment and fails closed when
  missing or blank. The real provider URL and model name stay inside the
  transport implementation and are not added to schemas. Timeout-like,
  non-2xx / connection, malformed response, missing content, and provider
  refusal paths all raise categorical sanitized `DeepSeekTransportError`
  values. Tests use mocked opener callables only; no live provider call is
  made. No endpoint, frontend UI, Chat productization, Tavily/search, raw
  prompt/response persistence, or automatic call was added. 2b did not
  authorize surfacing real external responses; that guard/validator semantic
  work was deferred to Stage 9.3-B-2c.
- Stage 9.3-B-2c external response guard + validator integration
  (`guard_response` default behavior preserved; new
  `guard_external_model_response`; new `validate_external_ai_response_content`;
  explicit `DeepSeekNetworkAdapter.generate_external_response` path).
  External responses are allowed only by the explicit guard when
  `external_model_called=True`, `fake_response=False`, `mode="network"`,
  privacy flags remain manifest-only/no-search/no-persistence/no-raw-payload/
  no-raw-prompt/no-holdings, `not_saved_by_default=True`,
  `human_review_required=True`, `validator_result.passed=True`, and content
  contains no forbidden output terms or privacy tokens. No endpoint, frontend
  UI, Chat productization, Tavily/search, persistence, or automatic external
  call was added.
- Stage 9.3-B security closeout / external AI boundary audit
  (`tests/test_stage9_3b_security_closeout.py` and
  `docs/stage9_3b_security_closeout.md`). The audit verifies route surface,
  Stage 9.2 endpoint isolation, secret/env handling, real transport isolation,
  manifest-only request and payload chain, runtime policy gates, explicit
  external response guard semantics, mocked adapter external path failure
  modes, no persistence, and no financial-advice expansion. No production code
  change, endpoint, frontend UI, persistence, Tavily/search, live call, or
  automatic external call was added.
- Stage 9.3-B-2d internal one-shot manual invocation review
  (`scripts/dev_deepseek_one_shot_review.py`,
  `tests/test_stage9_3b_manual_one_shot_review.py`, and
  `docs/stage9_3b_one_shot_review.md`). The script is local-only,
  command-line-only, manual-only, and dry-run/fail-closed by default. A live
  call requires `--live-call`, `--i-understand-this-calls-deepseek`,
  `--confirm-context-preview`, process-env `DEEPSEEK_API_KEY`, a passing
  request guard, a passing runtime policy, provider payload/transport
  contract construction, the external response validator, and
  `guard_external_model_response`. No endpoint, frontend UI, persistence,
  Tavily/search, live test, or automatic external call was added.
- Stage R1 Course Paper Research Recovery Note
  (`docs/research/financial_market_pressure_clustering_note.md`,
  `docs/historical_percentile_method_note.md`,
  `docs/metric_interpretation_boundaries.md`, and
  `docs/historical_validation_event_notes.md`). The course-paper research is
  recovered as methodology, boundary language, historical archetypes, and D19
  event-note material only. It does not add production clustering, K-means/GMM
  classifier logic, cluster probability, cluster dashboard modules, trading
  signals, AI productization, endpoints, or external calls.
- D19 v0 Historical Validation Event Registry + Replay Skeleton
  (`src/data_quality/historical_validation_event_registry.py`,
  `src/data_quality/historical_validation_replay.py`, and
  `docs/d19_historical_validation_v0.md`). The Stage R1 event windows are now
  represented as a static, auditable registry with controlled event types,
  pressure groups, ordinary-pullback markers, data-availability constraints,
  external-reference notes, and interpretation boundaries. The replay skeleton
  converts registry events into `reference_only`, `limited`, `insufficient`, or
  `available` rows without reading DB files, outputs, private data, external AI
  config, or live providers. The CLI has optional read-only event-registry
  display flags. No frontend, endpoint, external AI call, live ingest,
  production clustering, probability output, return estimate, or trading advice
  was added.
- DF-1 D19 v1 Historical Evidence-row Integration
  (`src/data_quality/historical_validation_replay.py` and
  `src/data_quality/historical_validation.py`). The static D19 registry/replay
  skeleton now consumes existing D19 historical validation summary data when
  available. D19 public rows carry compact `d19_v1_replay_rows` and
  `d19_v1_replay_summary` metadata in component contributions while preserving
  `reference_only` fallback behavior when no summary is supplied. Missing,
  stale, research-needed, proxy-only, valuation, earnings, and true-breadth
  gaps remain visible. No endpoint, frontend UI, external AI, Tavily/search,
  persistence, live fetch/ingest, probability output, prediction output,
  trading advice, or allocation directive was added.
- DF-2 D15/D16 Compliance Audit
  (`docs/d15_d16_compliance_audit.md` and
  `tests/test_d15_d16_compliance_audit.py`). The audit confirms D15 remains a
  current-evidence review with band/evidence outputs, not a classifier,
  probability model, forecast, or trading model. It confirms D16 remains a
  hypothetical scenario matrix/current evidence transmission review, not a
  forecast, scenario-probability model, portfolio-action model, or return
  estimator. D15/D16 enter AI Context Manifest only as model outputs, not facts.
  DF-2 passed without production code changes.
- DF-3 D17/D18 Data Gap and Source-gate Review
  (`docs/d17_d18_data_gap_review.md` and
  `tests/test_d17_d18_data_gap_review.py`). The audit confirms D17 remains a
  growth/inflation context layer (not a recession call, business-cycle
  forecast, or return estimate) with oil-alone, CPI-alone, single-labor, and
  low-frequency inflation hard gates enforced. It confirms D18 remains a
  valuation/equity-structure research and proxy context layer (not a timing
  model, target-price model, or trading model) with source-gated
  valuation/earnings facts, always-visible valuation/earnings/true-breadth
  gaps, single-proxy-cannot-create-pressure, and proxy-breadth-not-true-breadth
  hard gates enforced. D17/D18 enter AI Context Manifest only when per-row
  `ai_context_allowed` is True. DF-3 passed without production code changes.
- DF-4 D13 Reliability / Divergence Metadata
  (`docs/d13_reliability_divergence_metadata.md`,
  `tests/test_d13_reliability_divergence_metadata.py`, and
  `src/data_quality/historical_percentile_metrics.py`). DF-4 adds new
  explanatory metadata fields to every D13 row and to component_contributions:
  `reliability_band`, `reliability_drivers`, `divergence_band`,
  `divergence_notes`, `method_agreement`, `normalization_methods_available`,
  three pairwise alignment labels, `source_quality_note`, and
  `history_window_note`. New fields propagate through `sanitized_d13_context`
  for downstream D10/D11/D15/D16/AI Context consumers. DF-4 did not change
  percentile / z-score / robust z-score values, 5Y/3Y lookback rules, band
  thresholds, `trigger_eligibility`, or `ai_context_allowed` semantics. The
  new metadata cannot promote a row to a hard trigger and cannot relax AI
  context eligibility. No new provider, endpoint, frontend UI, external AI,
  Tavily/search, persistence, live fetch/write, prediction output,
  probability output, allocation directive, or trading advice was added.
- DF-4a / DF-4c Credit OAS coverage work
  (`docs/d13_credit_oas_history_audit.md`,
  `docs/d13_credit_oas_coverage_metadata.md`,
  `tests/test_d13_credit_oas_coverage_metadata.py`, and
  `src/data_quality/historical_percentile_metrics.py`). DF-4a confirmed the
  current HY/IG OAS local and provider history is about three years and still
  below the exact 3Y fallback gate at 1094 coverage days. DF-4c adds row-level
  and component-level metadata for `history_coverage_status`,
  `provider_rebuild_status`, `normalization_availability`,
  `coverage_diagnostics`, `credit_reference_role`, `substitution_policy`, and
  `long_history_reference_status`. HY/IG below-gate rows remain
  `ai_context_allowed=False` and `trigger_eligibility=not_eligible`.
  `BAA10Y` is documented as a long-history proxy/reference only, not a
  substitute for HY/IG OAS.
- S1 D16 Scenario Stress Refinement v1
  (`src/data_quality/scenario_stress.py`,
  `tests/test_s1_d16_scenario_refinement.py`, and
  `docs/s1_d16_scenario_refinement.md`). S1 adds explanation-only scenario
  component metadata for uncertainty drivers, missing constraints, proxy
  constraints, source-gate constraints, D13 reliability/divergence/OAS coverage
  context, D17/D18 gap context, and D19 reference context. D16 public output
  keys remain unchanged. S1 does not add providers, endpoints, frontend UI,
  external AI, Tavily/search, persistence, live fetches, live writes, scenario
  probabilities, forecasts, return estimates, target prices, portfolio
  actions, D13 gate relaxation, BAA10Y substitution, or new hard triggers.
- HF-1 Test Runtime Hotfix / DB-backed Fixture Batching
  (`tests/helpers/market_history_fixtures.py`,
  `tests/test_historical_percentile_metrics.py`,
  `tests/test_d13_reliability_divergence_metadata.py`,
  `tests/test_d13_credit_oas_coverage_metadata.py`,
  `tests/test_benchmark_dashboard_pipeline.py`, and
  `docs/test_runtime_hotfix.md`). HF-1 adds test-only SQLite fixture batching
  and module-scope benchmark result reuse for read-only assertions. Production
  code is unchanged. HF-1 does not change D13 formulas/gates, D16 behavior,
  model semantics, AI context rules, providers, endpoints, frontend UI,
  external AI, Tavily/search, live fetches, or live writes.

## Hard Boundaries

- No allocation directive, action instruction, or return estimate language in public outputs.
- No event-odds, crash-odds, recession-odds, or market-direction probability output.
- No AI Chat.
- No DeepSeek endpoint.
- No Tavily/search productization.
- No frontend AI UI.
- No prompt/response/chat/report persistence productization.
- No automatic external calls.
- No full-account external context.
- No holdings line items, account values, position weights, or transaction
  history may be exposed to external AI context.
- No prediction, probability, or trading model.
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

AI-1 Local Controlled Research Preview is completed with local research and
prompt preview APIs, six answer modes, three detail levels, seven-section
Chinese output, full-context catalogue and selected-prompt separation,
semantic validation, and a read-only frontend workbench.

Next recommended task: AI-1.5 Local Preview Evaluation & Governance Closeout.
It must remain local-only and should finish golden fixtures, structure and
adversarial tests, a quality audit baseline, and the AI-2 readiness checklist
before any request to start AI-2 is considered.

Stage 9.3-B-2d internal one-shot manual invocation review completed.
External AI line frozen. No AI Chat/product endpoint/frontend UI/persistence/
Tavily/search was added. Stage R1 Course Paper Research Recovery Note
completed as docs-only research recovery. D19 v0 Historical Validation Event
Registry + Replay Skeleton is completed. Current phase is Stage S - Scenario
Stress / Explanation Refinement. S1 D16 Scenario Stress Refinement v1 is
completed. HF-1 Test Runtime Hotfix is completed after S1. DF-0 roadmap
arbitration and
legacy document cleanup is completed. DF-1 D19 v1 historical evidence-row
integration is completed. DF-2 D15/D16 compliance audit is completed. DF-3
D17/D18 data gap and source-gate review is completed without production code
changes. DF-4 D13 reliability / divergence metadata is completed with scoped
D13 production code edits that add explanatory metadata fields only. DF-4a
Credit OAS history audit and DF-4c Credit OAS coverage/provider-rebuild
metadata are complete. Stage DF is concluded. Stage S0 Post-DF Roadmap
Reconciliation is complete. S1 D16 Scenario Stress Refinement v1 is complete.
HF-1 Test Runtime Hotfix / DB-backed Fixture Batching is complete. Optional
DF-4d BAA10Y D19 proxy/reference documentation is deferred unless explicitly
requested later. HF-2 Project Namespace Index / Governance Light Cleanup (including D-line
naming cleanup: plain-English names added, legacy D IDs preserved as aliases,
production identifiers unchanged) is a docs-only governance hotfix completed
after HF-1.

Stage 8 Portfolio Exposure Overlay v0 is complete as a downstream-only,
privacy-preserving explanatory layer. It maps sanitized compact portfolio
context to macro risk channels and existing D10-D19 evidence/model outputs. It
does not read or expose holdings line items and does not provide allocation
advice, action directives, return estimates, or probability outputs. Stage 8.5
Foundation Stabilization Sprint is complete. Stage 9.0 AI Readiness Design,
Stage 9.1 Memo Template / Context Contract, Stage 9.2 Mock Chat / Mock Memo
local preview endpoints, Stage 9.3-A adapter skeleton hardening, Stage
9.3-B readiness review / external AI integration seam audit, Stage
9.3-B-0 runtime approval gate / external AI policy contract, Stage
9.3-B-1 minimal real adapter design + config contract, Stage 9.3-B-2a
mocked transport adapter, Stage 9.3-B-2b real transport code, Stage 9.3-B-2c
external response guard + validator integration, and Stage 9.3-B security
closeout, and Stage 9.3-B-2d internal one-shot manual invocation review are
complete. Stage R1 Course Paper Research Recovery Note is complete as docs-only
research recovery. D19 v0 Historical Validation Event Registry + Replay
Skeleton is complete as static local-only registry/replay scaffolding. DF-1 D19
v1 historical evidence-row integration is complete. DF-2 D15/D16 compliance
audit is complete without production code changes. DF-3 D17/D18 data gap and
source-gate review is complete without production code changes. DF-4 D13
reliability / divergence metadata is complete with scoped D13 production code
edits that add explanatory metadata fields only. DF-4a Credit OAS history audit
is complete. DF-4c Credit OAS coverage / provider-rebuild metadata integration
is complete. Stage DF is concluded. Stage S0 is complete, and S1 D16 Scenario
Stress Refinement v1 is complete. HF-1 Test Runtime Hotfix is complete.
Optional DF-4d BAA10Y D19 proxy/reference documentation is deferred unless
explicitly requested later. P-M1 dashboard_model_pipeline row conversion
accumulator optimization is complete as a behavior-preserving refactor; each
row group is now converted to dicts once and reused through a shared
accumulator. No model semantics, public output keys, module keys, endpoints,
or external AI changed. P-M2 dashboard_service Evidence Row / AI Gate Helper
Split is complete as a behavior-preserving helper extraction; evidence row
construction and AI context gate policy now live in
`dashboard_evidence_policy.py`, with private compatibility aliases preserved
in `dashboard_service.py`. No model semantics, public keys, schemas, AI context
semantics, endpoints, frontend UI, providers, or external AI changed. P-M3
Historical Risk Normalization Metadata Helper Split is complete as a
behavior-preserving extraction; reliability/divergence metadata and credit OAS
coverage/provider-rebuild helpers now live in
`historical_percentile_metadata.py`, with private compatibility aliases
preserved in `historical_percentile_metrics.py`. No D13 formula, 5Y/3Y gate,
exact 1095-day fallback behavior, output field, AI context eligibility,
trigger eligibility, BAA10Y proxy/reference policy, provider, endpoint,
frontend UI, external AI, Tavily/search, live fetch, or live write changed.
P-M4-A M11 Cross-request Shared Context Cache Design Review is complete as a
docs-first design audit. It documents the current per-call-only
`DashboardPipelineContext`, future cache key and invalidation boundaries,
`write_last_good` side-effect limits, privacy limits, AI Context Manifest
consistency requirements, and M11 cache risk register. It did not implement
runtime cache, change dashboard API behavior, alter model semantics, change AI
Context Manifest semantics, add providers, endpoints, frontend UI, external AI,
Tavily/search, live fetch, or live write. P-M4-B M11 Cache Key / File Signature
Helpers is complete as a production helper foundation. It added deterministic
path/file-signature and digest helpers plus cache bypass reason policy only. It
did not implement runtime cache, wire routes, change dashboard service behavior,
alter `write_last_good`, read report contents into keys, open SQLite contents,
change AI Context Manifest semantics, add providers, endpoints, frontend UI,
external AI, Tavily/search, live fetch, or live write. P-M4-C In-process
Summary / Evidence Cache is complete as a narrow runtime performance change. It
adds a process-local single-slot cache for default-path summary and unfiltered
evidence table responses when `write_last_good=False`; filtered calls may
filter cached unfiltered rows, while filtered responses are not cached directly.
It bypasses custom paths and explicit `write_last_good=True` calls, returns
defensive copies, and does not cache AI Context Manifest, persist cache to disk,
change dashboard API schema, alter model semantics, change AI context
eligibility, or add providers, endpoints, frontend UI, external AI,
Tavily/search, live fetch, or live write. P-M4-D AI Context Manifest Cache
Review is complete as a review-only decision audit. The review found that
P-M4-C evidence cache already reduces warm Manifest calls from ~3350 ms to
~26 ms; Manifest-specific row classification takes ~2 ms. A dedicated Manifest
cache is deferred because the ~24 ms saving does not justify the
stale/privacy/AI context eligibility risk. S2 Scenario Stress Matrix
Explanation Contract / Golden Integration is complete as tests + docs only
(38 new contract tests across 11 categories covering public output keys,
metadata shape, forbidden language, D13/D17/D18/D19 context boundaries,
golden integration, AI Context Manifest integration, AI memo contract
integration, and D15/D16 compliance audit reinforcement). S2 does not change
production code, financial model semantics, support/severity/uncertainty
calculation, frontend, endpoints, or external AI. S3 AI Memo Boundary Template
Update is complete as local deterministic memo template hardening. It updates
Scenario Stress Matrix labels, scenario review rendering, risk review scenario
notes, macro report model-output treatment, and validator-safe non-forecast /
non-action wording. S3 does not change financial model semantics, Scenario
Stress Matrix support/severity/uncertainty logic, public keys, module/model/
metric/registry keys, AI Context Manifest semantics, AI memo schema, providers,
endpoints, frontend UI, external AI, Tavily/search, live fetch, or live write.
Dashboard Service Refactor Phase E - Module Builder Extraction is complete as a
behavior-preserving extraction of `DashboardModule` construction helpers into
`src/app_backend/services/dashboard_module_builder.py`. `dashboard_service.py`
keeps compatibility wrappers for the legacy underscore helper surface. The new
module receives key metric builders, portfolio compact builders, core metric
keys, blocked statuses, and historical-derived key sets by
callback/configuration, and does not import `dashboard_service.py`. No
dashboard public API, module key, public output key, key metric semantic,
financial model semantic, cache semantic, `write_last_good` behavior, AI
context eligibility, provider, endpoint, frontend UI, external AI,
Tavily/search, live fetch/write, prediction/probability output, return
estimate, allocation output, or trading advice changed.
Phase F1 Dashboard Metric Characterization Tests is complete as tests and docs
only. It locks current `_build_metric`, `_key_metrics_for_module`, official
macro missing behavior, PPI Final Demand / PPIACO boundaries, source/freshness/
date metadata, derived-first and portfolio-compact-first order, dependency
unusable behavior, AI context gate outcomes, and the legacy callable surface
before metric builder extraction. It does not move `_build_metric`, move
`_key_metrics_for_module`, add `dashboard_metric_builder.py`, change production
metric semantics, change dashboard public APIs, alter cache or
`write_last_good`, add providers, endpoints, frontend UI, external AI, live
fetches, live writes, prediction, probability, return, allocation, or trading
outputs.
Phase F2 Dashboard Metric Builder Extraction is complete as a
behavior-preserving extraction of metric object construction and metric
metadata helpers into `src/app_backend/services/dashboard_metric_builder.py`.
`dashboard_service.py` keeps compatibility aliases or thin wrappers for the
legacy underscore helper surface, with local configuration and callbacks
injected into the new builder module. The new module does not import
`dashboard_service.py`. No dashboard public API, module key, metric key,
`DashboardMetric` schema, source_badge/freshness/AI-context semantic, PPI
Final Demand / PPIACO boundary, cache semantic, `write_last_good` behavior,
provider, endpoint, frontend UI, external AI, Tavily/search, live fetch/write,
prediction/probability output, return estimate, allocation output, or trading
advice changed.
Phase F/G Dashboard Service Refactor Completion is complete as the remaining
dashboard service extraction. Historical-derived helpers now live in
`dashboard_historical_derived.py`, sanitized portfolio compact helpers in
`dashboard_portfolio_compact.py`, derived status metric helpers in
`dashboard_derived_metrics.py`, static metric catalog data in
`dashboard_metric_catalog.py`, and key-metric routing in
`dashboard_key_metrics.py`. `dashboard_service.py` remains the public
orchestration facade and compatibility surface, with local configuration and
callbacks injected into extracted modules. No dashboard public API, module key,
metric key, `DashboardMetric` schema, source_badge/freshness/AI-context
semantic, PPI Final Demand / PPIACO boundary, historical-derived gate,
portfolio compact privacy boundary, cache semantic, `write_last_good` behavior,
provider, endpoint, frontend UI, external AI, Tavily/search, live fetch/write,
prediction/probability output, return estimate, allocation output, or trading
advice changed.
Data Foundation Gap Fill v1 is complete as an offline source-gated cleanup
before frontend work. It updates the PPI Final Demand source tier, adds the
read-only `audit_data_foundation_gaps.py` CLI, locks D14 source mappings,
keeps `ofr_fsi`, valuation, FedWatch, and BAA reference-only boundaries gated,
and records the validation plan in `docs/data_foundation_gap_fill_v1.md`.
Data Foundation G1 Controlled Local Refresh and Coverage Audit is complete. It
used existing ingest scripts only, refreshed the ignored local
`market_history.sqlite3`, increased coverage from 33,803 to 45,243
observations, resolved six `insufficient_history` rows, and preserved PPI,
D14, OFR FSI, valuation/FedWatch, BAA, and proxy source gates. No generated
data, production code, API schema, model semantic, frontend, or AI-context
change was committed. See `docs/data_foundation_local_refresh_g1.md`.
UI-0 Frontend Information Architecture Audit is complete.
AI-1 Local Controlled Research Preview is complete.
Next recommended task: AI-1.5 Local Preview Evaluation & Governance Closeout.
UI-1 remains in backlog. A G2 official-source refresh-command task is optional
and requires separate explicit approval.
Real AI Chat / Memo / Report integrations remain not implemented.
