# Short-Term Development Plan

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
13. Stage 9 preparation: current next phase.
14. Stage 9.0 AI Readiness Design: immediate next task.
15. Stage 9 AI Chat / Memo / Report: not implemented.

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

The current next phase is Stage 9 preparation. Stage 9.0 AI Readiness Design is
the immediate next task. Stage 9 preparation is not real AI integration and
must begin with AI Readiness / Memo Context Design.

Stage 9 should be split into:

1. Stage 9.0 AI Readiness Design.
2. Stage 9.1 Memo Template / Context Contract.
3. Stage 9.2 Mock Chat / Mock Memo.
4. Stage 9.3 DeepSeek adapter behind explicit user-controlled switch.
5. Stage 9.4 Tavily explicit-search beta.

Stage 9 AI Chat / Memo / Report is not implemented.

## Not Now

- DeepSeek.
- Tavily.
- Tauri.
- Account editing.
- Auto trading.
- Portfolio optimization.
- Hard PE, forward PE, or earnings provider integration.
- News sentiment engine.
- Black-box machine learning.
- Live provider fetch/write.
- Jumping directly to real DeepSeek Chat.
- Jumping directly to Tavily.
- Agent frameworks, MCP, persistent multi-turn chat, or automatic report saving
  in the first Stage 9 task.
- Treating Stage 9 preparation as real AI integration.

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
