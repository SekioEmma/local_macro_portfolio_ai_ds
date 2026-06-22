# Portfolio Deviation Compact

This document defines the local-only compact portfolio deviation fields used by
Dashboard and Evidence Table.

The compact view is derived from aggregate asset-class fields in
`portfolio_snapshot.json`. It must not return holdings line items, fund codes,
security identifiers, account amounts, or raw portfolio snapshots.

## Target Allocation

The supported target asset classes are fixed for the MVP:

- `sp500`: 50%
- `nasdaq100`: 20%
- `short_bond`: 20%
- `gold`: 10%

Cash is not part of the target allocation. It is reported only as reserve status.

## Current Weight

`current_weights` are calculated using the non-cash target asset classes as the
denominator:

- `sp500`
- `nasdaq100`
- `short_bond`
- `gold`

Cash values do not change the target-weight denominator.

## Deviation

`deviation_pp` is the current weight minus target weight, expressed in percentage
points.

`max_deviation_asset` is the non-cash target asset class with the largest
absolute `deviation_pp`.

`max_deviation_pp` is the signed deviation for `max_deviation_asset`.

## Equity Total

`equity_total_current_weight` is:

```text
sp500 current weight + nasdaq100 current weight
```

`equity_total_target_weight` is 70%.

`equity_total_deviation_pp` is:

```text
equity_total_current_weight - 70%
```

## Freshness

Freshness is based on `holdings_updated_at` compared with the snapshot
generation date when both dates are available:

- `fresh`: 0-14 days
- `watch`: 15-30 days
- `stale`: more than 30 days
- `unknown`: missing or unparsable date

Stale or unknown portfolio holdings must not make the module display OK.

## Dashboard Fields

Dashboard `portfolio_deviation` key metrics expose only compact fields:

- `max_deviation_asset`
- `max_deviation_pp`
- `equity_total_deviation_pp`
- `cash_reserve_status`
- `holdings_updated_at`

Evidence Table and Module Detail Drawer render the same compact rows.

## AI Factual Context Boundary

Portfolio compact rows may enter the future AI factual context layer only when
they have a value, local provenance, usable freshness, and date metadata.

Allowed compact context:

- aggregate asset-class deviation
- aggregate equity-total deviation
- cash reserve exclusion status
- holdings update date

Forbidden context:

- holdings line items
- fund codes or security identifiers
- complete amounts or account totals
- raw `portfolio_snapshot` payloads
- trade instructions

The interpretation hint must state that cash reserve is excluded from target
allocation, portfolio deviation is not attributed to market factors, and no
trading instruction is provided.
