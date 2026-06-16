# Short-Term Development Plan

## Current Phase

Stage DF - Data Foundation & Historical Evidence Integration.

## Priority Route

### P0

1. DF-0 Roadmap Arbitration and Legacy Document Cleanup: completed.
2. DF-1 D19 v1 Historical Evidence-row Integration: completed.

### P1

1. DF-2 D15/D16 Compliance Audit: completed.
2. DF-3 D17/D18 Data Gap and Source-gate Review: next engineering task.

### P2

1. DF-4 D13 Reliability / Divergence Metadata.
2. D16 scenario stress refinement, only after audit.

### Frozen

- External AI productization.
- Chat UI.
- Tavily/search.
- Tauri.
- Account editing.
- Full-account DeepSeek context.

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
19. DF-3 D17/D18 Data Gap and Source-gate Review: next engineering task.
20. DF-4 D13 Reliability / Divergence Metadata: optional/backlog.
21. Stage 9 AI Chat / Memo / Report: not implemented.

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
as docs-only method and boundary material. The current next phase is a return
to the D15/D19 core modeling roadmap. D19 v0 Historical Validation Event
Registry + Replay Skeleton is now completed as a static local-only registry and
replay-row scaffold. DF-0 roadmap arbitration and legacy cleanup is completed.
DF-1 D19 v1 historical evidence-row integration is completed. DF-2 D15/D16
compliance audit is completed without production code changes. The next
engineering task is DF-3 D17/D18 data gap and source-gate review.

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
