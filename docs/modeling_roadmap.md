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

The next engineering step is Stage 3 EvidenceIndex / MetricLookup / Model
Registry, not D16.

## D16 Scenario Stress Test v0

D16 is later. It should be a scenario matrix, not a forecast.

It should not output probabilities, asset-direction certainty, return estimates,
or allocation directives.

## Later Modeling Areas

Later work may cover growth/inflation macro packs, valuation/equity structure,
expanded historical validation, portfolio exposure overlays, and AI memo/report
surfaces. Those areas must preserve the same source, freshness, privacy, and
evidence-boundary rules.
