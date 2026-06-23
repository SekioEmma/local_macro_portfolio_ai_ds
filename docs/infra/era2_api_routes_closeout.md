# Era 2 B7 API Routes Closeout

## Scope

TASK-B7 exposes the existing guarded services as **local FastAPI routes only**.
There is no frontend, no automatic refresh, no background task, no app-start
call, and no page-load call. Every route call is an explicit user HTTP request.

Importing `app_backend.main` reads no config, environment, database, or
network. The realtime quote service is built per request; the Tavily search
execution service is a process-local singleton whose construction touches
nothing. Dependency factories never call providers at app start, and API
tests inject fakes through `app.dependency_overrides`.

## Routes

### POST /api/search/tavily

- Request: `TavilySearchApiRequest` (`query`, `max_results`, `domain_filter`,
  `confirm_external_search`). The client cannot supply runtime policy, budget,
  provider keys, transport endpoint, allowlist/blocklist, or any dangerous
  permission.
- Routed exclusively through `TavilySearchExecutionService.execute`.
- **Fail-closed by default.** A request without `confirm_external_search=true`
  returns `results=[]`, `search_available=false`, `guard_passed=false` and
  reads no config and creates no transport.
- Still subject to: query sanitizer, per-request runtime policy (derived from
  real state, never hardcoded), domain allowlist, process-local daily budget,
  and the response guard.
- Never calls the Tavily transport directly from the route; never persists the
  raw query or raw response; never echoes the query, blocking flags, provider
  error, key, or config in the response.
- POST only. `GET` returns 405.

### GET /api/quote/etf

- `symbols` is a required, repeatable query parameter
  (`?symbols=SPY&symbols=QQQ&symbols=VIX`).
- Calls `RealtimeQuoteService.quote_etf`.
- An unsupported symbol returns a fixed `422` (`detail="unsupported_symbol"`)
  with no internal exception text. Provider failure degrades to the B5
  service's `unavailable` / `stale` snapshot. The route writes no data.

### GET /api/quote/treasury_curve

- `date` optional (`YYYY-MM-DD`); `curve_kind` is `nominal_treasury`
  (default) or `tips_real_yield`.
- `nominal_treasury` calls `treasury_curve`; `tips_real_yield` calls
  `tips_curve`. An unknown `curve_kind` returns a fixed `422`. Future or
  malformed dates degrade to an `unavailable` snapshot; no future data is
  used.

### GET /api/quote/fx

- `pair` defaults to `USDCNH`.
- Calls `fx_rate`. USDCNH still returns `unavailable` /
  `native_usdcnh_not_configured`. `DEXCHUS`, USD/CNY, and any proxy/inversion
  remain forbidden.

### GET /api/quote/commodity

- `benchmark` defaults to `brent`, with `brent` / `wti` supported.
- The endpoint is itself the explicit user request, so the request-scoped
  search callable fixes `confirm_external_search=true`. The call still passes
  config, sanitizer, allowlist, per-process daily budget, runtime policy,
  adapter, transport, and response guard via `TavilySearchExecutionService`.
- The commodity search is limited to the three fixed B6 domains: `reuters.com`,
  `bloomberg.com`, `oilprice.com`.
- When search is disabled, blocked, or budget is exhausted, the route returns
  `unavailable` and never raises. The route never calls `TavilyRealTransport`
  directly and does not bypass the budget.

## Error handling

- Quote-service exceptions map to a fixed `HTTP 503`
  (`detail="quote_service_unavailable"`) with no raw exception text or secret.
- Search failures never raise a raw `500`; the route returns a safe
  fail-closed `SearchResponse`.

## Budget

- The daily search budget is **process-local memory only**, partitioned by UTC
  date, reset on UTC rollover, and **reset on every process restart**. It is
  never written to SQLite, files, cache, or logs.

## Forbidden / unchanged

- `/api/chat` and `/api/ai/tavily` remain forbidden.
- No RAG, no Agent, no persisted search, no raw search-result storage.
- No frontend control, no automatic refresh, no background/app-start/page-load
  call.
- Financial model semantics (D10–D19, Stage 8) are unchanged.
- The only Tavily HTTP boundary remains `tavily_real_transport.py`.
- The project is still not an automated trading system.
