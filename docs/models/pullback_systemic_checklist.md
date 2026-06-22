# Pullback Systemic Risk Checklist

`pullback_systemic_risk_checklist` is a local-only derived evidence module. It
uses existing dashboard evidence rows, including the D10 financial stress
composite, and does not fetch live data.

## Outputs

- `pullback_classification`
- `pullback_checklist_items`
- `pullback_missing_critical_inputs`
- `pullback_supporting_evidence`
- `pullback_interpretation_boundary`
- `pullback_percentile_context`
- `pullback_liquidity_funding_context`

All rows use `source=local_dashboard_evidence` and `source_badge=derived`.

## Classification Values

- `ordinary_pullback`
- `valuation_drawdown`
- `macro_pressure`
- `credit_warning`
- `systemic_risk_review`
- `insufficient_evidence`

Core credit spread evidence is required before the checklist can make a useful
classification. Equity drawdown alone, VIX alone, and proxy-only evidence cannot
produce `systemic_risk_review`.

## Checklist Items

- `equity_damage`
- `credit_spread_confirmation`
- `volatility_confirmation`
- `rates_real_yield_pressure`
- `labor_deterioration`
- `inflation_fed_constraint`
- `cross_asset_proxy_confirmation`
- `liquidity_funding_confirmation`
- `valuation_gap`
- `earnings_gap`
- `true_breadth_gap`

Each item preserves supporting evidence snapshots where available. Items can also
carry D13 `percentile_evidence` and a `rarity_note`; these are auxiliary context
only and do not replace the raw checklist conditions.

The liquidity/funding item carries D14 `liquidity_funding_evidence` and a
`funding_confirmation_note`. If D14 is usable, `liquidity` is removed from
`pullback_missing_critical_inputs` with boundaries preserved. If D14 is
insufficient, `liquidity` remains missing.

## D13 Auxiliary Percentile Context

The checklist reads existing D13 evidence rows to describe local rarity for
equity drawdown, VIX, rates, real yields, labor claims, and credit spreads.
Percentile evidence cannot by itself trigger `systemic_risk_review`.

Credit percentile can support `credit_warning` only as auxiliary context when
core credit inputs are usable. VIX and drawdown percentile are never sufficient
on their own. Proxy-only evidence remains auxiliary and cannot stand in for true
breadth or official funding stress.

## D14 Funding/Liquidity Confirmation

D11 reads existing D14 evidence rows only after they are present in the evidence
table. D14 does not fetch data inside D11 and does not expose raw provider
payloads or holdings.

`systemic_risk_review` requires all of the following:

- core credit deterioration
- liquidity/funding pressure or stress confirmation from D14
- at least one transmission confirmation: labor deterioration, broad equity
  damage with credit confirmation, or official reference pressure plus CP spread
  pressure

D14-only, CP-only, official-reference-only, ON RRP-only, VIX-only, drawdown-only,
or percentile-only evidence cannot trigger `systemic_risk_review`.

## Boundary

This checklist is not crash probability. It does not predict market bottom or
top. It does not produce buy/sell/hedge instructions. Equity drawdown alone is
not systemic risk. VIX alone is not systemic risk. Percentile evidence is
auxiliary and cannot alone trigger `systemic_risk_review`. Proxy breadth is not
true market breadth. Liquidity/funding confirmation can upgrade risk review only
when credit and transmission evidence also confirm. Missing earnings, valuation,
and true breadth continue to limit crisis confirmation.
