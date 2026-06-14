# Modeling Roadmap

## Scope

This document is roadmap control only. It does not authorize live fetches,
provider writes, account actions, or portfolio instructions.

## D15 Macro Regime Review v0

D15 is implemented as Macro Regime Review, not as a classifier, probability
model, forecast model, or trading model.

Approved public D15 labels:

- `low_stress_liquidity_support`
- `rates_pressure`
- `inflation_energy_pressure`
- `credit_stress`
- `liquidity_funding_pressure`
- `growth_slowdown_watch`
- `stagflation_pressure`
- `mixed_or_transition`
- `insufficient_evidence`

Public D15 output policy:

- No public `macro_regime_score`.
- No public internal support or group scores.
- Use `support_band`, `evidence_quality_band`, and `conflict_band`.
- Keep `primary_pressure_ranking`, supporting evidence, conflicting evidence,
  missing inputs, and blocked inputs visible.
- Treat valuation, earnings, and true-breadth gaps as constraints, not support.

Hard gates:

- VIX alone cannot trigger credit or systemic stress.
- Equity drawdown alone cannot trigger stress.
- D14 alone cannot trigger liquidity or systemic regime.
- Percentile-only evidence cannot determine regime.
- Proxy-only evidence cannot determine pressure or high label.
- Blocked, insufficient-history, stale, missing, or research-needed rows cannot support a label.
- Oil or breakeven alone cannot trigger inflation/energy pressure.
- DGS30 alone cannot trigger high rates pressure.

## Stage 2.5 D19 Historical Validation v0

D19 v0 is implemented as historical replay of the deterministic evidence
pipeline over predefined event windows.

It is historical pressure recognition, event-window consistency, and boundary
validation. It is not ROC/AUC optimization, probability modeling, future-market
forecasting, or a trading performance review.

Current D19 public outputs are compact model-output rows: status, event counts,
available/insufficient-history counts, over/under-escalation flags, boundary
violation count, privacy flags, model/formula versions, and validation boundary.

## Stage 3 Modeling Infrastructure v0

Stage 3 is implemented as shared modeling infrastructure:

- `EvidenceIndex` for read-only evidence row lookup and support gating.
- `MetricLookup` for compact model-critical metric semantics.
- `ModelRegistry` for model modules, public output keys, boundaries, and
  audit/AI/frontend contract policies.
- `ModelOutput` as an optional payload helper for future modules.

Stage 3 does not add new financial model behavior. D15 remains Macro Regime
Review, not a classifier or probability model. D19 remains historical replay,
not probability modeling or trading backtest.

## D16 Scenario Stress Test v0

D16 is implemented as a deterministic scenario matrix / current evidence
transmission review, not a forecast.

It uses current evidence rows and model outputs to summarize predefined scenario
support, affected evidence groups, transmission channels, missing inputs,
severity band, and uncertainty band.

It does not output scenario odds, asset-direction certainty, return estimates,
allocation directives, action instructions, or portfolio optimization results.

Stage 5 D17 follows D16 and is completed.

## D17 Growth / Inflation Macro Pack v0

D17 is implemented as a conservative growth/inflation current-evidence context
layer for growth, inflation, policy-constraint, and stagflation-watch
interpretation.

It is not a forecast, recession call, event-odds model, allocation directive,
or return estimate. Missing and research-needed inputs remain visible and do not
support labels.

Stage 6 D18 follows D17 and is now completed.

## D18 Valuation / Equity Structure v0

D18 is implemented as a conservative valuation/equity-structure research and
proxy context layer. It keeps valuation, earnings, and true breadth gaps
explicit while allowing existing sanitized proxy rows to provide limited
equity-structure and breadth/concentration context.

D18 is not a forecast, timing model, event-odds model, allocation directive, or
return estimate. Valuation context cannot determine macro regime or systemic
review by itself, and proxy breadth/concentration does not replace true breadth.

The next engineering step is Stage 7 D19 expanded historical validation. D19
expanded historical validation is not implemented in D18.

## Later Modeling Areas

Later work may cover expanded historical validation, portfolio exposure
overlays, and AI memo/report surfaces. Those areas must preserve the same
source, freshness, privacy, and evidence-boundary rules.
