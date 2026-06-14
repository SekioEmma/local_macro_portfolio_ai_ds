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
11. Stage 8 Portfolio Exposure Overlay.
12. Stage 9 AI Chat / Memo / Report.

## Current Task Boundary

Stage 7 D19 expanded historical validation v1 is completed as a read-only
historical replay, event-window consistency, and boundary-validation layer.

D19 expanded does not output forecasts, event odds, allocation directives,
action instructions, return estimates, probability calibration, prediction
backtests, or strategy-evaluation results. Missing/stale/research-needed,
proxy-only, valuation, earnings, and true-breadth gaps remain visible.

The next step is Stage 8 Portfolio Exposure Overlay. Stage 8 is not implemented
in the Stage 7 task.

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
