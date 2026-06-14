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
- Confirmed HEAD: `9674895 Organize frontend display registries`.
- `main` is the old stable baseline and must not be modified for current app-mvp work.

Validation baseline from the confirmed current state:

- `python -m pytest -q`: 363 passed, 1 warning.
- `npm run typecheck`: passed.
- `npm run build`: passed.
- Benchmark evidence rows: 118.
- Included facts: 95.
- Included model outputs: 15.
- Market history: 33803 observations / 45 metrics.

## Completed Mainline

- D7-D9 data foundation, PPIFIS, drawdown/curve/cross-asset, labor mini-pack, official labor history, labor compact fallback.
- D10 `financial_stress_composite`.
- D11 `pullback_systemic_risk_checklist`.
- D12 AI context manifest / context preview.
- D13 historical percentile / z-score / robust-z.
- D13a-D13c core risk history backfill, percentile bands, D10/D11 integration.
- D14 `liquidity_funding_stress`.
- D14b D14 liquidity/funding confirmation integrated into D10/D11.
- M1 dashboard pipeline benchmark.
- M2 batch market history reads.
- M3 shared dashboard pipeline context.
- M4a dashboard service helper split.
- M5 audit pipeline modularized.
- M6 frontend display registries organized.

## Hard Boundaries

- No buy, sell, add, reduce, clear, hedge, target allocation, or expected return language.
- No crash probability or recession probability.
- `financial_stress_score` is pressure temperature, not crash probability.
- A macro regime label is current evidence review, not future market direction.
- Proxy, search-derived, research-needed, and insufficient-history rows are not official facts.
- Missing data must not be filled by AI.
- The backend must not bind `0.0.0.0`.
- CORS must not use `*`.

## Current Next Step

The current next step is Stage 0 documentation governance only.

This is not D15 code. Do not implement a macro regime classifier, new backend logic,
new frontend behavior, new provider integration, or new model outputs during Stage 0.

