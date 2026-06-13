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
- `valuation_gap`
- `earnings_gap`
- `true_breadth_gap`
- `liquidity_gap`

Each item preserves supporting evidence snapshots where available.

## Boundary

This checklist is not crash probability. It does not predict market bottom or
top. It does not produce buy/sell/hedge instructions. Equity drawdown alone is
not systemic risk. VIX alone is not systemic risk. Proxy breadth is not true
market breadth. Missing earnings, valuation, liquidity, and true breadth limit
crisis confirmation.
