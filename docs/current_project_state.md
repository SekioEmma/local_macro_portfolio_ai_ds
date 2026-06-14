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

## Current Baseline

- Branch: `app-mvp`.
- D15 baseline before Stage 2: `b1ccde6 Add macro regime review`.
- `main` is the old stable baseline and must not be modified for current app-mvp work.

Validation baseline after Stage 2 golden contracts:

- `python -m pytest -q`: 372 passed, 1 warning.
- `npm run typecheck`: passed.
- `npm run build`: passed.
- Benchmark evidence rows: 131.
- Included facts: 95.
- Included model outputs: 28.
- Market history: 33803 observations / 45 metrics.

Stage 2.5 D19 local audit baseline:

- D19 event windows configured: 5.
- Current local historical validation coverage: 0 available / 5 insufficient history.
- D19 boundary violations: 0.

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
- Proxy, search-derived, research-needed, stale, and insufficient-history rows are not official facts.
- Missing data must not be filled by AI.
- The backend must not bind `0.0.0.0`.
- CORS must not use `*`.

## Current Next Step

The current next step is Stage 8 Portfolio Exposure Overlay.

Stage 7 D19 expanded historical validation is complete as a read-only
historical replay, event-window consistency, and boundary-validation layer. It
is not probability calibration, a prediction backtest, or a strategy-evaluation
model. Stage 8 is not implemented yet.
