# Era 2 B5 Realtime Quote Closeout

## Scope

TASK-B5 adds a read-only quote service. It does not add API routes, frontend controls, automatic refresh, background work, app-start calls, or page-load calls.

The service itself does not read environment variables, `.env`, provider configuration, or secrets. It imports no HTTP client and writes no SQLite, cache, outputs, or provider response.

## Provider boundary

- ETF daily closes: existing `alpha_vantage_history_provider.get_daily_time_series`
- VIX and yield curves: existing `fred_provider.get_fred_series`
- Optional stale fallback: read-only `market_history_store.get_latest_observation`

All readers are injectable. Tests use fake callables only and make no real Alpha Vantage, FRED, yfinance, Tavily, or SQLite request.

Provider free-text errors and raw payloads do not enter public quote schemas. A local fallback is accepted only for the exact metric key, a valid date, numeric value, and `status=ok`; every fallback output is explicitly stale.

## Semantics

- SPY, QQQ, SHY, and GLD are latest available daily closes, not intraday ticks.
- VIX is a latest available index close, not an intraday tick.
- Treasury and TIPS points disclose their actual observation dates.
- Curves do not fill missing maturities and never select an observation after the requested date.
- Partial curves remain `partial`; unavailable curves remain `unavailable`.
- `market_state` is session metadata only. It is not price validity, direction, advice, probability, or a signal.
- Native USDCNH remains unavailable. Existing `DEXCHUS` is USD/CNY and is not used as a USDCNH proxy, inversion, or estimate.

## Remaining boundaries

- `/api/quote/*` routes remain unimplemented and belong to TASK-B7.
- B6 commodity quote has not started.
- B5 does not change D10–D19, Stage 8, or any financial model semantics.
