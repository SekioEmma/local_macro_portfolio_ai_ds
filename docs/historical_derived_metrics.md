# Historical Derived Metrics

Historical derived metrics are local-only candidate calculations built from the market historical store.
They do not call providers, DeepSeek, Tavily, search, or yfinance.
If yfinance observations exist in the market history store, this service reads them only as local stored observations.
Official WTI/Brent history can be ingested separately through FRED/EIA daily series and then read from the same local store.

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

Dashboard integration is currently limited to selected `equity_trend` candidates.
Only OK S&P 500/Nasdaq 30D/60D returns and `nasdaq_vs_sp500_30d` may be surfaced in Dashboard rows.
Oil candidates may be surfaced only when their local history dependencies are official FRED/EIA rows.
Rate candidates remain read-only audit candidates unless an explicit compact rule exists.

## Current Non-goals

The calculation service itself does not:

- connect yfinance
- access the network
- alter provider request logic
- call yfinance live
- calculate official current signals
- save raw provider responses
- save raw prompts
- save raw holdings
- emit trading advice

## Future Work

- user-run live yfinance ingest
- historical derived metrics dashboard integration
- official macro pack

## yfinance History Relationship

The yfinance batch history provider is an ingestion layer, not a calculation layer.
It may add `unofficial_fallback` index history and `proxy` ETF history to `market_observations`.

Historical derived metrics can later calculate candidate returns from those stored observations when the window is sufficient.
The derived result still uses `source_badge=derived`, includes dependency keys and calculation metadata, and does not promote yfinance or proxy data into official evidence.

## Dashboard Integration

Dashboard integration lives in `app_backend.services.dashboard_service`.
It uses historical derived results only when the existing row is still `insufficient_history` and the historical candidate is `ok`.

Integrated rows keep:

- `source_badge=derived`
- `source=local_market_history`
- `freshness_status=historical`
- interpretation text that states the dependency boundary

Equity rows state the local market history and yfinance unofficial/proxy boundary.
WTI/Brent rows state official FRED/EIA daily oil history and remain derived energy-pressure inputs, not real-time oil quotes, inflation forecasts, or commodity trading signals.

## Official Energy History Ingest

Official WTI/Brent history can be previewed or written with:

```text
python scripts/ingest_official_energy_history.py --dry-run
python scripts/ingest_official_energy_history.py --live --write
```

The script uses configured FRED series:

- `wti`: `DCOILWTICO`
- `brent`: `DCOILBRENTEU`

It writes compact `market_observations` rows only and does not store raw provider responses.
