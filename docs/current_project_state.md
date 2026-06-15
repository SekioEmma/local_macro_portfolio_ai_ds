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

Stage 8.5 Foundation Stabilization Sprint is the current freeze and stability
phase on branch `app-mvp`. Stage 8 Portfolio Exposure Overlay v0 is complete.
Stage 9 AI Chat / Memo / Report is not implemented.

The project is frozen against new features until Stage 8.5 passes. Stage 8.5
does not add financial model behavior, does not call DeepSeek or Tavily, does
not run live provider fetches, and does not read holdings line items. It records
the latest validation baseline and produces a maintainability backlog instead
of a major refactor.

## Current Baseline

- Branch before work: `app-mvp`.
- Commit before work: `f47575a Add portfolio exposure overlay`.
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
- Stage 8.5 is a freeze/stabilization sprint. It does not implement Stage 9,
  DeepSeek, Tavily, Tauri, AI Chat, or new financial models.
- Proxy, search-derived, research-needed, stale, and insufficient-history rows are not official facts.
- Missing data must not be filled by AI.
- The backend must not bind `0.0.0.0`.
- CORS must not use `*`.

## Current Next Step

The current next step remains Stage 8.5 completion, not Stage 9 implementation.

Stage 8 Portfolio Exposure Overlay v0 is complete as a downstream-only,
privacy-preserving explanatory layer. It maps sanitized compact portfolio
context to macro risk channels and existing D10-D19 evidence/model outputs. It
does not read or expose holdings line items and does not provide allocation
advice, action directives, return estimates, or probability outputs. Stage 9 is
not implemented.
