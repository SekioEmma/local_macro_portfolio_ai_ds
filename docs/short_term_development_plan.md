# Short-Term Development Plan

`docs/short_term_development_plan.md` is the source of truth for the immediate
route and the next engineering task. For a one-page orientation, see
`docs/INDEX.md`. For task-level rules, see `docs/task_governance_policy.md`.

## Current Phase

Stage S - Scenario Stress / Explanation Refinement. S1 Scenario Stress Matrix
Refinement v1 (legacy: D16) is completed. HF-1 Test Runtime Hotfix is
completed after S1. HF-2 Project Namespace Index / Governance Light Cleanup
(including D-line naming cleanup) is completed as a docs-only governance
hotfix.

## Priority Route

### P0

1. S1 Scenario Stress Matrix Refinement v1 (legacy: D16): completed.
2. HF-1 Test Runtime Hotfix / DB-backed Fixture Batching: completed.
3. HF-2 Project Namespace Index / Governance Light Cleanup (including D-line
   naming cleanup): completed.
4. P-M1 dashboard_model_pipeline row conversion accumulator (Historical Risk
   Normalization through Scenario Stress Matrix): completed.
5. P-M2 dashboard_service helper split (M7/M8-B follow-up): completed.
6. P-M3 Historical Risk Normalization metadata helper split: completed.
7. P-M4-A M11 cross-request shared context cache design review: completed.
8. P-M4-B M11 cache key / file signature helpers: completed.
9. P-M4-C In-process Summary / Evidence Cache: completed.
10. P-M4-D AI Context Manifest cache review: completed as review-only.
    Implementation deferred; P-M4-C evidence cache already eliminates
    Manifest bottleneck.
11. S2 Scenario Stress Matrix explanation tests / golden contract integration:
    next.

### P1

1. S2 Scenario Stress Matrix (legacy: D16) explanation tests / golden contract
   integration if needed.
2. S3 AI memo boundary template update only after S2.

### Completed

- DF-0 Roadmap Arbitration and Legacy Document Cleanup.
- DF-1 D19 v1 Historical Evidence-row Integration.
- DF-2 D15/D16 Compliance Audit.
- DF-3 D17/D18 Data Gap and Source-gate Review.
- DF-4 D13 Reliability / Divergence Metadata.
- DF-4a Credit OAS history availability audit.
- DF-4c Credit OAS coverage/provider-rebuild metadata.
- S0 Post-DF Roadmap Reconciliation and S1 Entry Plan.
- S1 D16 Scenario Stress Refinement v1.
- HF-1 Test Runtime Hotfix / DB-backed Fixture Batching.
- HF-2 Project Namespace Index / Governance Light Cleanup.
- P-M1 dashboard_model_pipeline row conversion accumulator.
- P-M2 dashboard_service Evidence Row / AI Gate Helper Split.
- P-M3 Historical Risk Normalization Metadata Helper Split.
- P-M4-A M11 Cross-request Shared Context Cache Design Review.
- P-M4-B M11 Cache Key / File Signature Helpers.
- P-M4-C In-process Summary / Evidence Cache.
- P-M4-D AI Context Manifest Cache Review (review-only; implementation deferred).

### Deferred

- DF-4d BAA10Y D19 proxy/reference documentation, only if explicitly
  requested later.

### Frozen

- External AI productization.
- Chat UI.
- Tavily/search.
- Tauri.
- Account editing.
- Full-account DeepSeek context.
- Live provider fetch/write.
- Prediction/probability/trading outputs.

## Mainline Route

1. Stage 0 documentation governance: completed.
2. Stage 0.5 optional credit history backfill: only with explicit user authorization.
3. Stage 1 D15 Macro Regime Review v0: completed.
4. Stage 2 Golden Output Contract: completed.
5. Stage 2.5 D19 Historical Validation v0: completed.
6. Stage 3 EvidenceIndex / MetricLookup / Model Registry: completed.
7. Stage 4 D16 Scenario Stress Test v0: completed.
8. Stage 5 D17 Growth / Inflation Macro Pack: completed.
9. Stage 6 D18 Valuation / Equity Structure v0: completed.
10. Stage 7 D19 expanded historical validation: completed.
11. Stage 8 Portfolio Exposure Overlay: completed.
12. Stage 8.5 Foundation Stabilization Sprint: completed.
13. Stage 9 preparation through Stage 9.3-B-2d: completed; external AI line frozen.
14. Stage R1 Course Paper Research Recovery Note: completed as docs-only research recovery.
15. D19 v0 Historical Validation Event Registry + Replay Skeleton: completed.
16. DF-0 Roadmap Arbitration and Legacy Document Cleanup: completed.
17. DF-1 D19 v1 Historical Evidence-row Integration: completed.
18. DF-2 D15/D16 Compliance Audit: completed.
19. DF-3 D17/D18 Data Gap and Source-gate Review: completed.
20. DF-4 D13 Reliability / Divergence Metadata: completed.
21. DF-4a Credit OAS history availability audit: completed.
22. DF-4c Credit OAS coverage/provider-rebuild metadata: completed.
23. Stage 9 AI Chat / Memo / Report: not implemented.

## Current Task Boundary

Stage 7 D19 expanded historical validation v1 is completed as a read-only
historical replay, event-window consistency, and boundary-validation layer.

D19 expanded does not output forecasts, event odds, allocation directives,
action instructions, return estimates, probability calibration, prediction
backtests, or strategy-evaluation results. Missing/stale/research-needed,
proxy-only, valuation, earnings, and true-breadth gaps remain visible.

Stage 8 Portfolio Exposure Overlay v0 is completed as a downstream-only,
privacy-preserving explanatory overlay using sanitized portfolio context only.
It maps compact portfolio context to macro risk channels and existing D10-D19
evidence/model outputs. It does not read or expose holdings line items and does
not provide allocation advice, action directives, return estimates, or
probability outputs.

Stage 8.5 Foundation Stabilization Sprint is completed. It refreshed validation
baselines, checked pipeline reuse, audited Stage 8 AI context behavior, locked
privacy and forbidden-output boundaries, and recorded maintainability backlog
items. It did not add financial model behavior, did not read holdings line
items, and did not call DeepSeek or Tavily.

Stage 9.3-B-2d completed the internal one-shot manual invocation review and
froze the external AI line. Stage R1 completed course-paper research recovery
as docs-only method and boundary material. The current phase is Stage S -
Scenario Stress / Explanation Refinement. D19 v0 Historical Validation Event
Registry + Replay Skeleton is now completed as a static local-only registry and
replay-row scaffold. DF-0 roadmap arbitration and legacy cleanup is completed.
DF-1 D19 v1 historical evidence-row integration is completed. DF-2 D15/D16
compliance audit is completed without production code changes. DF-3 D17/D18
data gap and source-gate review is completed without production code changes.
DF-4 D13 reliability / divergence metadata is completed with scoped D13
production-code changes that add explanatory metadata fields only.
DF-4a Credit OAS history availability audit and DF-4c Credit OAS
coverage/provider-rebuild metadata are completed. DF-4c does not add providers,
relax the exact 3Y gate, substitute `BAA10Y` for HY/IG OAS, change D10/D11/D15/
D19 trigger logic, add prediction/probability/trading outputs, endpoints,
frontend UI, external AI, Tavily/search, persistence, live fetches, or live
writes.

Stage S0 reconciled the post-DF roadmap. S1 D16 Scenario Stress Refinement v1
is completed as explanation refinement, not a prediction model,
scenario-probability model, return-estimate model, price-path model, or
portfolio-action model.

The next recommended task is S2 D16 scenario explanation tests / golden
contract integration if needed, or S3 AI memo boundary template update only
after S1/S2.

HF-1 Test Runtime Hotfix is completed after S1. HF-1 optimized DB-backed D13
test fixtures and benchmark result reuse only; it did not change model
semantics, providers, endpoints, frontend UI, external AI, Tavily/search, live
fetches, or live writes.

HF-2 Project Namespace Index / Governance Light Cleanup is completed as a
docs-only governance hotfix. HF-2 added `docs/INDEX.md` as a one-page
orientation map and `docs/task_governance_policy.md` as the task-level rule
source. It did not change production code, tests, financial model semantics,
D13 context shape, D16 behavior, AI context eligibility, providers,
endpoints, frontend UI, external AI, Tavily/search, live fetches, or live
writes.

P-M1 dashboard_model_pipeline row conversion accumulator is completed, covering
the model chain from Historical Risk Normalization (legacy: D13) through
Scenario Stress Matrix (legacy: D16).

P-M2 dashboard_service Evidence Row / AI Gate Helper Split is completed as a
behavior-preserving extraction. It moved evidence row construction and AI gate
policy helpers into `dashboard_evidence_policy.py` while keeping private
compatibility aliases in `dashboard_service.py`. It did not change model
semantics, public keys, schemas, AI context semantics, providers, endpoints,
frontend UI, external AI, Tavily/search, live fetches, or live writes.

P-M3 Historical Risk Normalization Metadata Helper Split is completed as a
behavior-preserving extraction. It moved reliability/divergence metadata and
credit OAS coverage/provider-rebuild metadata helpers into
`historical_percentile_metadata.py`, while preserving compatibility aliases in
`historical_percentile_metrics.py`. It did not change D13 formulas, 5Y/3Y
gates, exact 1095-day fallback behavior, output fields, AI context eligibility,
trigger eligibility, BAA10Y proxy/reference policy, providers, endpoints,
frontend UI, external AI, Tavily/search, live fetches, or live writes.

P-M4-A M11 Cross-request Shared Context Cache Design Review is completed as a
docs-first design audit. It defines future cache key, scope, invalidation,
`write_last_good`, privacy, AI Context Manifest, and risk-register boundaries.
It did not implement runtime cache, change dashboard API behavior, change model
semantics, change AI Context Manifest semantics, add providers, endpoints,
frontend UI, external AI, Tavily/search, live fetches, or live writes.

P-M4-B M11 Cache Key / File Signature Helpers is completed as a production
helper foundation. It added deterministic path/file-signature and digest helpers
plus cache bypass reason policy only. It did not implement runtime cache, wire
routes, change dashboard service behavior, change `write_last_good`, read report
contents into keys, open SQLite contents, or add providers, endpoints, frontend
UI, external AI, Tavily/search, live fetches, or live writes.

P-M4-C In-process Summary / Evidence Cache is completed as a narrow runtime
performance change. It adds a process-local single-slot cache for default-path
summary and unfiltered evidence table responses when `write_last_good=False`.
Filtered calls may filter the cached unfiltered table, but filtered responses
are not cached directly. `write_last_good=True` and custom paths bypass the
shared cache. P-M4-C does not cache AI Context Manifest, persist cache to disk,
change dashboard API schema, change model semantics, change AI context
eligibility, change `write_last_good`, add providers, endpoints, frontend UI,
external AI, Tavily/search, live fetches, or live writes.

P-M4-D AI Context Manifest Cache Review is completed as a review-only decision
audit. The review found that P-M4-C evidence cache already eliminates the
Manifest bottleneck (warm Manifest ~26 ms; Manifest-specific work ~2 ms).
Implementation is deferred. The next recommended task is S2 Scenario Stress
Matrix explanation tests / golden contract integration.

Legacy Stage 9 productization remains frozen and is not the current short-term
route. Historical Stage 9 notes should not be used to authorize Chat UI,
Tavily/search, full-account DeepSeek context, persistence, Tauri, or new API
endpoints.

Historical Stage 9 work was split into:

1. Stage 9.0 AI Readiness Design.
2. Stage 9.1 Memo Template / Context Contract.
3. Stage 9.2 Mock Chat / Mock Memo.
4. Stage 9.3 DeepSeek adapter behind explicit user-controlled switch.
5. Stage 9.4 Tavily explicit-search beta.

Stage 9 AI Chat / Memo / Report productization is not implemented.

Stage R research recovery is docs-only. Stage R1 may inform D13 percentile
methodology, D15 historical archetype language, D19 event-note integration, and
AI memo boundary wording. It does not add production clustering, K-means/GMM
classifier logic, cluster probability, cluster-to-action mapping, cluster
dashboard modules, live fetches, external calls, or trading signals.

D19 v0 uses Stage R1 only as historical event-note source material. It adds
static event registry and replay skeleton coverage only, not a Dashboard product
surface, endpoint, external AI integration, live fetch, live ingest, production
classifier, probability output, return estimate, or trading advice.

## Not Now

- Reopening DeepSeek productization.
- Reopening Tavily/search productization.
- Tauri.
- Account editing.
- Full-account DeepSeek context.
- Holdings line items, account values, position weights, or transaction history
  in external AI context.
- Auto trading.
- Portfolio optimization.
- Hard PE, forward PE, or earnings provider integration.
- News sentiment engine.
- Black-box machine learning.
- K-means or GMM production classifier.
- Cluster probability or cluster-to-action mapping.
- Cluster dashboard module.
- Live provider fetch/write.
- Jumping directly to real DeepSeek Chat.
- Jumping directly to Tavily.
- Agent frameworks, MCP, persistent multi-turn chat, or automatic report saving
  in the first Stage 9 task.
- Treating Stage 9 preparation as real AI integration.
- Treating Stage R research notes as implemented production models.

## Persistent Boundaries

- Public outputs may describe evidence, support bands, conflicts, missing inputs,
  and current-review boundaries.
- Public outputs must not provide allocation directives, action instructions,
  event odds, market-direction probabilities, or return estimates.
- Missing data must remain missing.
- Proxy, search-derived, research-needed, stale, and insufficient-history rows
  must keep their limits visible.
- Backend facts, source badges, freshness gates, and AI-context eligibility remain
  the source of truth.
- M7-M12 remain future maintainability backlog, not blockers for Stage 9
  preparation.
