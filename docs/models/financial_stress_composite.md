# Financial Stress Composite

`financial_stress_composite` is a local-only derived evidence module. It consumes
existing dashboard evidence rows and does not fetch live data.

## Outputs

- `financial_stress_score`
- `financial_stress_status`
- `financial_stress_dominant_pressure_source`
- `financial_stress_component_contributions`
- `financial_stress_missing_inputs`
- `financial_stress_interpretation_boundary`
- `financial_stress_percentile_context`
- `financial_stress_funding_liquidity_context`

Every row is `source_badge=derived` and preserves structured input evidence,
component contributions, missing inputs, and the interpretation boundary.

## Scoring

The score is a 0-100 pressure temperature using four groups:

- credit conditions: 40
- rates and real yield: 20
- equity damage and cross-asset proxies: 25
- labor deterioration: 15

D14 funding/liquidity rows are recorded as confirmation context under
`funding_liquidity`. They do not replace the four score groups and cannot alone
produce `stress`.

Status thresholds are:

- `ok`: 0-24
- `watch`: 25-44
- `pressure`: 45-69
- `stress`: 70-100

Core credit spread inputs are required for a total score. If high-yield or
investment-grade spread evidence is missing, stale, research-only, or otherwise
blocked from AI factual context, the composite returns `insufficient_evidence`.

## D13 Auxiliary Percentile Context

D13 `historical_risk_percentile` rows are read only after they already exist in
the dashboard evidence table. They are not fetched, recalculated, or used to
replace the core D10 scoring inputs.

The composite records D13 context under `percentile_context` and exposes
`financial_stress_percentile_context`. This context can explain local historical
rarity for VIX, rates, real yields, equity drawdown, claims, and credit spreads.
Missing or insufficient D13 rows remain in missing percentile context and do not
become hard auxiliary evidence.

VIX percentile, equity drawdown percentile, and claims percentile cannot by
themselves trigger stress. Credit percentile context is auxiliary unless core raw
credit evidence is available.

## D14 Funding/Liquidity Confirmation Context

D10 reads existing `liquidity_funding_stress` rows after they already exist in
the dashboard evidence table. It does not fetch, read raw provider payloads, or
read holdings.

The composite records D14 context under `funding_liquidity` and exposes
`financial_stress_funding_liquidity_context`. Eligible D14 rows can confirm
whether short-term funding, policy plumbing, and official/reference stress
indices are aligned with credit deterioration.

D14 pressure or stress can support funding confirmation when raw credit evidence
is also deteriorating. D14 alone, ON RRP alone, CP spread alone, or official
stress reference indices alone cannot replace the D10 score or produce systemic
stress conclusions.

## Boundaries

The score is not crash probability, recession probability, or trading advice.
VIX alone cannot trigger stress. Equity drawdown alone cannot trigger stress.
Proxy-only evidence is capped below stress. Labor deterioration can confirm macro
pressure, but it cannot by itself confirm systemic crisis. Percentile bands
describe local historical rarity, not forecast probability. Liquidity/funding
evidence is confirmation context only, not a trading signal or probability.
