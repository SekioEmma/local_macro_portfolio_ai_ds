# Modeling Roadmap

## Scope

This document is roadmap only. It is not an implementation plan for the current
Stage 0 task and must not introduce code changes.

## D15 Macro Regime Review v0

D15 labels under consideration:

- `low_stress_liquidity_support`
- `rates_pressure`
- `inflation_energy_pressure`
- `credit_stress`
- `liquidity_funding_pressure`
- `growth_slowdown_watch`
- `stagflation_pressure`
- `mixed_or_transition`
- `insufficient_evidence`

D15 score meaning:

- Evidence support strength only.
- Not probability.
- Not forecast confidence.
- Not future market direction.
- Not a trade signal.

Hard gates:

- VIX alone cannot trigger credit or systemic stress.
- Equity drawdown alone cannot trigger stress.
- D14 alone cannot trigger liquidity or systemic regime.
- Percentile-only evidence cannot determine regime.
- Proxy-only evidence cannot determine pressure or high label.
- Blocked, insufficient-history, stale, missing, or research-needed rows cannot support a label.
- Valuation, earnings, and true breadth gaps must remain explicit.

## D16 Scenario Stress Test v0

D16 scenario stress should be a coherent scenario matrix, not a forecast.

It should not output:

- Probability.
- Trade action.
- Asset direction certainty.
- Expected return.
- Target allocation.

## Later Modeling Areas

Later work may cover growth/inflation macro packs, valuation/equity structure,
historical validation, portfolio exposure overlays, and AI memo/report surfaces.
Those areas must preserve the same source, freshness, privacy, and no-trading
boundaries.

