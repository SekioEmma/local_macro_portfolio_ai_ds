# yfinance Batch History Provider

The yfinance batch history provider is an optional local ingestion path for historical price observations.
It is designed to fill the market historical store with compact index fallback and ETF proxy prices.

## Purpose

Historical derived metrics need a deeper local observation window than the Dashboard currently has.
This provider normalizes yfinance daily history into `market_observations` rows so later phases can calculate returns and relative trends from the local SQLite store.

This provider does not change Dashboard current values.
It does not create official facts.

## Source Boundary

yfinance data is never treated as official in this project.

Allowed `source_badge` values are:

- `unofficial_fallback` for index symbols such as `^GSPC`, `^IXIC`, and `^NDX`
- `proxy` for ETF proxy symbols such as `SPY`, `QQQ`, and `RSP`

ETF proxy observations stay out of the official layer.
They default to `ai_context_allowed=false`.

## Initial Symbols

Configuration lives in:

```text
configs/yfinance_history.yaml
```

Initial unofficial fallback index symbols:

- `sp500`: `^GSPC`
- `nasdaq`: `^IXIC`
- `nasdaq100`: `^NDX`

Initial ETF proxy symbols:

- `spy_proxy`: `SPY`
- `qqq_proxy`: `QQQ`
- `rsp_proxy`: `RSP`
- `hyg_proxy`: `HYG`
- `lqd_proxy`: `LQD`
- `gld_proxy`: `GLD`
- `shy_proxy`: `SHY`
- `tlt_proxy`: `TLT`

This phase intentionally excludes Mag7 baskets and oil futures.

## Config Fields

Each enabled symbol entry includes:

- `metric_key`
- `symbol`
- `display_name`
- `source_badge`
- `metric_kind`
- `unit`
- `enabled`
- `interpretation_hint`

Only `source_badge=unofficial_fallback` and `source_badge=proxy` are accepted.

## Provider

The provider lives in:

```text
src/data_providers/yfinance_history_provider.py
```

It provides:

- `load_yfinance_history_config`
- `fetch_yfinance_batch_history`
- `normalize_yfinance_history`
- `build_market_observations_from_yfinance`

`fetch_yfinance_batch_history` accepts an injectable downloader.
Tests use fake downloaders only.
The default downloader imports yfinance inside the function and is used only when the caller explicitly allows live mode.

Normalization stores only the chosen close value:

- prefer `Adjusted Close`
- fall back to `Close`
- skip missing or non-finite prices
- normalize dates to `YYYY-MM-DD`
- strip timezone detail from observation dates

The provider does not save raw DataFrames, raw yfinance responses, volume, open, high, low, API keys, holdings, prompts, or output text.

## Ingestion

The ingestion script lives in:

```text
scripts/ingest_yfinance_history.py
```

Default dry-run without network:

```powershell
python scripts/ingest_yfinance_history.py --dry-run
```

Dry-run with an explicit config:

```powershell
python scripts/ingest_yfinance_history.py --dry-run --config configs/yfinance_history.yaml
```

Manual live write command for a user-run later step:

```powershell
python scripts/ingest_yfinance_history.py --live --write --period 1y --interval 1d
```

`--live` and `--write` are separate controls:

- without `--live`, the script does not call yfinance
- without `--write`, the script does not write SQLite observations
- default behavior is dry-run and offline

The compact summary includes configured symbols, enabled symbols, fetched symbols, normalized observations, inserted count, updated count, skipped count, skipped reasons, source badge distribution, dry-run state, and live state.

## Market History Writes

Written observations use:

- `metric_key` from config, not the symbol
- `provider=yfinance`
- `source=Yahoo Finance via yfinance`
- `source_series=<symbol>`
- `source_badge=unofficial_fallback` or `proxy`
- `metric_kind=index` or `proxy`
- `ai_context_allowed=false`

They are written through `market_history_store.upsert_market_observation`, so the existing unique key controls idempotent insert/update behavior.

## Historical Derived Metrics

Once a user manually ingests enough history, `historical_derived_metrics` can calculate candidate period returns and relative returns from the local store.
Dashboard integration is currently limited to selected `equity_trend` derived metrics.
Those rows use `source_badge=derived`, not `official`, and their interpretation text preserves the yfinance unofficial/proxy boundary.

## Current Non-goals

This phase does not:

- call yfinance during Codex validation
- access the network
- add an official provider
- call DeepSeek or Tavily
- replace non-equity Dashboard current values
- promote proxies into official evidence
- save raw provider responses
- save raw holdings
- output trading advice

## Future Work

- User-run live yfinance ingest
- Historical derived metrics dashboard integration
- Official macro pack
- SPY vs RSP and QQQ vs SPY proxy watchlist
