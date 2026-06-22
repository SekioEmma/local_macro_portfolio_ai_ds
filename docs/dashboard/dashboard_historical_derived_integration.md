# Dashboard Historical Derived Integration

This integration lets the Dashboard use selected historical derived metrics when local market history has enough observations.

## Scope

Only these `equity_trend` metrics are eligible:

- `sp500_30d_return`
- `sp500_60d_return`
- `nasdaq100_30d_return`
- `nasdaq100_60d_return`
- `nasdaq_vs_sp500_30d`

No new metric keys are created.
Rate and oil derived metrics remain outside this Dashboard integration.

## Data Source Boundary

The values are calculated from local `market_observations` through `historical_derived_metrics`.
The current local historical data can include yfinance observations, but those observations remain `unofficial_fallback` or `proxy`.

Dashboard rows produced by this integration use:

- `source=local_market_history`
- `source_badge=derived`
- `freshness_status=historical`
- an `interpretation_hint` that states the local market history and yfinance unofficial/proxy boundary

yfinance-derived values are not official market facts.
They are not official market breadth or valuation measures.

## AI Context Rule

The integrated S&P 500 and Nasdaq index derived returns may enter the AI factual context only when:

- the derived metric status is `ok`
- value, date, freshness, and source metadata are present
- `source_badge=derived`
- the interpretation hint includes dependency and local-history context

ETF proxy observations remain `ai_context_allowed=false` at the observation layer.
Proxy-derived metrics should stay false unless a later phase adds explicit allowed-proxy semantics.

## Insufficient History Rule

If the historical derived candidate is still `insufficient_history`, the Dashboard keeps the original insufficient-history row.
The integration does not fabricate history and does not call yfinance.

Rate and oil examples that can remain insufficient:

- `dgs10_5d_avg`
- `dgs10_10d_avg`
- `dgs30_distance_to_5pct`
- `wti_30d_change`
- `brent_30d_change`

## User-Run Ingest Prerequisite

When the local market history DB lacks yfinance observations, the user can run:

```powershell
python scripts/ingest_yfinance_history.py --live --write --period 1y --interval 1d
```

This command is intentionally manual.
The Dashboard integration itself does not access the network.

## Non-goals

This integration does not:

- call yfinance live
- call DeepSeek or Tavily
- change provider request logic
- add an official provider
- write raw yfinance responses
- write raw holdings
- emit trading advice
