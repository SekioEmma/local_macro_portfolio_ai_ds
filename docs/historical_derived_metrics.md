# Historical Derived Metrics

Historical derived metrics are local-only candidate calculations built from the market historical store.
They do not call providers, DeepSeek, Tavily, search, or yfinance.

## Purpose

The Dashboard currently marks many return and change metrics as `insufficient_history`.
This service provides a reusable calculation layer so future phases can decide when enough stored observations exist to support derived metrics.

This phase exposes service functions, tests, docs, and audit reporting only.
It does not replace Dashboard current values.

## Relationship To Market History

The service reads compact observations from:

```text
data/market_history/market_history.sqlite3
```

It uses only the `market_observations` table through `market_history_store`.
It does not read raw reports, raw provider responses, holdings, prompts, or output text.

## Supported Calculations

### Period Return

`calculate_period_return(metric_key, window_days)`:

- finds the latest observation
- finds the nearest observation on or before `window_days` calendar days before latest
- returns `latest / start - 1`
- returns `insufficient_history` when the start observation is unavailable

### Rolling Average

`calculate_rolling_average(metric_key, window_observations)`:

- sorts observations by `observation_date`
- uses the latest `N` numeric observations
- returns the arithmetic average
- returns `insufficient_history` when fewer than `N` points exist

### Relative Return

`calculate_relative_return(numerator_metric_key, denominator_metric_key, window_days)`:

- calculates period return for each dependency
- returns numerator return minus denominator return
- returns `insufficient_history` when either dependency lacks history

### Threshold Distance

`calculate_distance_to_threshold(metric_key, threshold)`:

- reads the latest observation
- returns latest value minus threshold
- returns `insufficient_history` when no latest observation exists

## Supported Candidate Metrics

`rate_pressure`:

- `dgs10_5d_avg`
- `dgs10_10d_avg`
- `dgs30_distance_to_5pct`

`equity_trend`:

- `sp500_30d_return`
- `sp500_60d_return`
- `nasdaq100_30d_return`
- `nasdaq100_60d_return`
- `nasdaq_vs_sp500_30d`

`inflation_energy_pressure`:

- `wti_30d_change`
- `brent_30d_change`

## Status Rules

A derived metric returns `ok` only when its historical dependency window is sufficient.
Otherwise it returns `insufficient_history`.

The service does not fabricate missing observations and does not use the current snapshot as a historical window.

## AI Context Boundary

Derived metrics use `source_badge=derived`.

`insufficient_history` results always use `ai_context_allowed=false`.
`ok` results include dependency keys, calculation name, window, points used, points required, and an interpretation hint.

Dashboard integration remains a later phase.

## Current Non-goals

This phase does not:

- connect yfinance
- access the network
- alter provider request logic
- replace Dashboard current values
- calculate official current signals
- save raw provider responses
- save raw prompts
- save raw holdings
- emit trading advice

## Future Work

- yfinance batch history provider
- historical derived metrics dashboard integration
- official macro pack
