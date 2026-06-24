# Local Macro Portfolio AI DS

Local-first macro risk research workbench. CS learning vehicle > macro research > investment tool.

## Quick Start

```bash
# Backend (FastAPI + Uvicorn)
cd src && python -m uvicorn app_backend.main:app --reload --host 127.0.0.1 --port 8765

# Frontend (React 18 + Vite 5 + TypeScript 5.5)
cd app_frontend && npm run dev

# Tests (1511 tests, ~250s full suite)
cd src && python -m pytest ../tests/ -x -q

# Type check frontend
cd app_frontend && npx tsc --noEmit
```

PYTHONPATH must include `src/` for all Python commands.

## Project Structure

```
src/
  app_backend/
    main.py              # FastAPI app, 13 API routes
    services/
      dashboard_service.py          # 820-line façade, main orchestrator
      dashboard_model_pipeline.py   # D10-D19 model pipeline sequence
      dashboard_context_cache.py    # In-process shared context cache
      dashboard_*.py                # 17 dashboard service modules
      ai_context_service.py         # AI Context Manifest builder
      ai_preview_service.py         # Local deterministic preview (no LLM)
      ai_memo_renderer.py           # Deterministic memo templates (712 lines)
      ai_external_adapter.py        # Stage 9 adapter skeleton (disabled)
      ai_external_runtime_policy.py # 22-flag guard (fail-closed)
      ai_research_*.py              # Local research preview services
      deepseek_*.py                 # DeepSeek adapter chain (dormant)
    schemas/
      responses.py        # Dashboard response models
      ai_external.py      # AI runtime policy schemas
  data_providers/         # FRED, yfinance, BLS, etc. (read-only)
  data_quality/           # D10-D19 model modules + historical validation
  modeling/               # Evidence index, metric registry
  market/                 # Market temperature
  portfolio/              # Portfolio engine
  llm/                    # DeepSeek client (offline)
app_frontend/
  src/
    App.tsx               # Router
    api/client.ts         # API client
    components/           # 15 React components, paper-style research UI
    types.ts              # Shared TypeScript types
tests/                    # 7 test directories matching src/ structure
docs/                     # 70+ design docs, specs, audits
scripts/                  # Ingest, audit, benchmark scripts
```

## Architecture

- **Backend**: FastAPI + Uvicorn, Pydantic v2 schemas, SQLite market_history store
- **Frontend**: React 18 + Vite 5 + TypeScript 5.5, paper-style research UI
- **Data flow**: JSON reports → dashboard_service → model pipeline (D10-D19) → evidence table → API → frontend
- **AI**: Preview endpoints are local/deterministic. One approved external LLM path exists — the AI-2 single-turn DeepSeek research endpoint (`/api/ai/research-deepseek`) — gated by the 22-flag runtime policy guard, which fails closed when external AI is not enabled (no provider key). All other external/network/search paths remain disabled by default.

## Era Roadmap

- Era 0: Data foundation (done)
- Era 1: Frontend beautification (done, tagged `era1-frontend-redesign-complete`)
- Era 2: AI/agent/MCP (current)
- Era 3: China data (future)

## Security Constraints (MUST FOLLOW)

**Do NOT read, modify, commit, print, copy, move, or reference:**
- `.env`, `configs/external_llm.yaml`, `*.sqlite`, `*.sqlite3`
- `data/holdings/`, `data/private/`, `outputs/`, `cache/`
- Raw provider payloads, raw prompts, API keys, local logs, `dist/`, `node_modules/`

**Do NOT:**
- Read `os.environ` / `os.getenv`, **except** the approved key loads isolated to `deepseek_real_transport.load_deepseek_api_key_from_env()` and `tavily_real_transport.load_tavily_api_key_from_env()`. Do not scatter new env reads elsewhere.
- Import `httpx` / `requests` / `aiohttp` outside an explicitly approved transport boundary
- Make real network calls, **except** the approved AI-2 single-turn DeepSeek call through `deepseek_real_transport.py` and the approved B4 transport boundary in `tavily_real_transport.py`; both remain synchronous and must never run in the background, at app start, or on page load
- Add `/api/chat`, `/api/ai/deepseek`, `/api/ai/external`, or `/api/ai/tavily` (the bare `/api/ai/deepseek` stays forbidden; the sanctioned model endpoint is `/api/ai/research-deepseek`; `/api/chat` and `/api/ai/tavily` stay forbidden)
- Add a `/api/search/tavily` or `/api/quote/*` route that bypasses its guarded service (TASK-B7 approves these routes only through `TavilySearchExecutionService` / `RealtimeQuoteService` / `CommodityQuoteService`; never call the Tavily transport directly from a route)
- Send raw questions/prompts/holdings/account/position/transaction data or local paths
- Change D10-D19 or Stage 8 financial semantics
- Broaden AI Context Manifest eligibility
- Weaken `guard_response` blocking when `external_model_called=True`
- Re-hardcode the AI-2 runtime policy gates to constants (they must reflect real state and stay able to fail closed)

### Era 2 search exception

- The only approved search HTTP boundary is `src/app_backend/services/tavily_real_transport.py`.
- TASK-B4 approves that transport implementation only; it does not approve an API route, UI control, automatic invocation, or any bypass around the existing guards.
- Real Tavily requests must be explicitly triggered by the user and pass `SearchRuntimePolicy`, query sanitizer, domain allowlist, budget, and response guard checks.
- Automatic, background, app-start, and page-load search calls remain forbidden.
- Tavily may receive only a sanitizer-approved query. Raw prompts, full account context, holdings, positions, transactions, local paths, and raw provider payloads remain forbidden.
- `tavily_real_transport.load_tavily_api_key_from_env()` may read only `TAVILY_API_KEY` from the process environment. It must not read `.env`, dotenv, config files, or any other secret source.
- `/api/search/tavily` is approved by TASK-B7 as **POST only**, routed exclusively through `TavilySearchExecutionService.execute`, and requires `confirm_external_search=true`. It must pass the query sanitizer, runtime policy, domain allowlist, per-process daily budget, and response guard. It defaults fail-closed, never calls the Tavily transport directly, never saves the raw query or raw response, and is never invoked automatically, in the background, at app start, or on page load.

### Era 2 read-only quote exception

- `src/app_backend/services/realtime_quote_service.py` may call only the existing audited `alpha_vantage_history_provider.get_daily_time_series`, `fred_provider.get_fred_series`, and read-only `market_history_store.get_latest_observation` callables when one of its public query methods is explicitly invoked.
- The B5 service itself must not import network clients, read environment variables, `.env`, secrets, or provider config, write databases, persist provider responses, call Tavily, or run automatically.
- Provider payloads and free-text provider errors must not enter B5 public schemas or responses.
- B5 itself does not wire API routes; the `/api/quote/*` routes are added by the separately approved TASK-B7 (see below) and remain read-only.

### Era 2 B7 API routes

- TASK-B7 exposes local FastAPI routes only. There is no frontend, no automatic refresh, no background task, no app-start call, and no page-load call. Every call is an explicit user HTTP request.
- `POST /api/search/tavily` goes only through `TavilySearchExecutionService`, requires `confirm_external_search=true`, and is fail-closed (sanitizer + runtime policy + allowlist + budget + response guard). It never calls the transport directly and never persists raw query/response.
- The following GET routes are read-only and write no SQLite/cache/outputs: `/api/quote/etf`, `/api/quote/treasury_curve`, `/api/quote/fx`, `/api/quote/commodity`. They emit no trade, forecast, probability, or advice fields.
- `/api/quote/commodity` runs through the B6 `CommodityQuoteService` over a request-scoped search callable that still passes config, sanitizer, allowlist, budget, runtime policy, adapter, transport, and response guard; it is limited to the three fixed domains (reuters.com / bloomberg.com / oilprice.com).
- USDCNH on `/api/quote/fx` still returns `unavailable` (`native_usdcnh_not_configured`); `DEXCHUS` / USD/CNY proxies remain forbidden.
- Importing `main` reads no config, env, database, or network; dependency factories never call providers at app start.

### Era 2 C2 official-history ingest exception

- TASK-C2 allows only `OfficialHistoryIngestService` and `scripts/ingest_approved_official_history.py` to call existing FRED/BLS history provider paths, and only after a user manually executes the CLI with `--live`.
- C2 adds no network import, transport, API route, frontend, background task, startup call, scheduler, or page-load call.
- The default mode is planned dry-run. Fetching requires `--live`; market-history writes require `--live --write`.
- Every write candidate must pass `official_history_ingest_guard` before the writer is called.
- C2 accepts no URL, SearchResult, Tavily result, search result, or webpage body as market-history input.
- The catalog is fixed to approved FRED rate series and BLS CPI series only. FRED remains `official_fallback`; BLS remains `official`.
- C2 must not persist raw provider payloads, URLs, API keys, account data, holdings, positions, transactions, prompts, or raw outputs.
- All other live-network, search, AI, quote, privacy, and persistence prohibitions remain in force.

### Era 2 C3 guarded local knowledge-base store exception

- `data/knowledge_base.sqlite` and `data/knowledge_base/raw/` remain forbidden for manual reading, printing, copying, or committing.
- Only `src/app_backend/services/knowledge_base_service.py` may access those paths at runtime, and only through explicit public methods. Import, construction, lookup, list, and mark-stale operations must not create DB/raw files.
- C3 adds no network, provider, API route, frontend, scheduler, background task, automatic ingest, Tavily/SearchResult/provider-payload ingestion, embedding, vector store, RAG, or private-notes access.
- Raw text must stay local: it must not enter API responses, model context, logs, error text, public service result objects, or the `documents` table.
- C3 tests must use temporary DB/raw roots. Existing privacy, network, AI, and RAG prohibitions remain in force.

### Era 2 C4a offline economic-calendar exception

- `data/economic_calendar.sqlite` remains forbidden for manual reading, printing, copying, or committing.
- Only `src/app_backend/services/economic_calendar_service.py` may access that path at runtime, and only through explicit public methods.
- C4a does not unlock Federal Reserve network requests, webpage scraping, Tavily, provider payloads, API routes, frontend, scheduler, automatic refresh, startup seed, page-load seed, or background tasks.
- `data/economic_calendar_seed.json` is tracked synthetic fixture-only data for tests. Production service code must not automatically load it or present it as a real economic schedule.
- C4a does not add actual, forecast, previous, surprise, value, score, probability, trading signal, RAG, embedding, vector store, or Agent work.
- Existing privacy, network, AI, persistence, and D10-D19 / Stage 8 prohibitions remain in force.

### Era 2 C4b official calendar acquisition exception

- `src/data_providers/official_calendar_real_transport.py` is the only new file that may import `httpx`. It fetches exactly two fixed official URLs: BLS ICS (`https://www.bls.gov/schedule/news_release/bls.ics`) and BEA JSON (`https://apps.bea.gov/API/signup/release_dates.json`).
- Live fetch is only allowed when a user manually runs `scripts/ingest_official_economic_calendar.py --live`. Default mode is planned (no network, no write).
- DB writes require `--live --write`. Any source failure blocks the entire batch.
- No API key, no env read, no config, no redirect, no retry, no credentials, no cookie.
- Raw response body stays in-process only — never persisted to SQLite, log, CLI output, error message, or public result.
- BLS and BEA are the only allowed sources. Fed / FOMC is not fetched. FOMC statement exact-time acquisition is deferred because the schema requires precise `HH:MM` and inferring "usually 14:00" is not permitted.
- C4b adds no API route, frontend, scheduler, background task, automatic refresh, RAG, embedding, vector store, or Agent.
- All other privacy, network, AI, persistence, D10-D19 / Stage 8, and AI Context Manifest prohibitions remain in force.

## Key Design Invariants

- `ExternalAIRuntimePolicy` has 10 required-true gates + 12 required-false dangerous permissions. Default: fail-closed.
- AI-2 single-turn runtime policy gates are **derived from real state, never hardcoded**: operational gates (`external_ai_enabled` / `provider_network_enabled` / `user_controlled_switch_enabled`) follow the user-controlled switch (provider key presence); provenance gates follow manifest budget readiness. Missing key → guard fails closed → structured blocked response (no raw 500). See `ai_deepseek_research_service._build_runtime_policy`.
- `ExternalAIAdapterConfig` defaults stay `enabled=False`, `mode="disabled"`, `allow_network=False`. The AI-2 path opts in explicitly via `deepseek_adapter.network_config()`.
- AI **preview** endpoints (`/api/ai/preview-*`, `/api/ai/context-preview`, `/api/ai/research-preview`, `/api/ai/prompt-preview`) are local/deterministic only — no LLM calls. The only model-calling endpoint is `/api/ai/research-deepseek` (AI-2 single-turn).
- Dashboard pipeline order is fixed: D13→D14→D10→D11→D17→D18→D15→D19→D16→Stage8
- Evidence table cache uses file-stat-based cache keys (mtime+size)

## Testing

```bash
# Full suite
cd src && python -m pytest ../tests/ -x -q

# Specific module
cd src && python -m pytest ../tests/dashboard/ -x -q
cd src && python -m pytest ../tests/contracts/ -x -q  # 65 contract tests

# Single file
cd src && python -m pytest ../tests/dashboard/test_dashboard_context_cache.py -x -q
```

## Important Files for Common Tasks

- Performance: `dashboard_service.py`, `dashboard_context_cache.py`, `historical_validation.py`, `historical_derived_metrics.py`
- AI development: `ai_preview_service.py`, `ai_context_service.py`, `ai_external_runtime_policy.py`, `ai_research_*.py`
- AI-2 external path: `ai_deepseek_research_service.py`, `deepseek_adapter.py`, `deepseek_real_transport.py` (real `urllib` transport; key-gated, manifest-only)
- Frontend: `app_frontend/src/App.tsx`, `app_frontend/src/api/client.ts`, `app_frontend/src/components/`
- Docs entry point: `docs/INDEX.md`, `docs/ROADMAP.md`, `docs/GOVERNANCE.md`, `docs/era2_plan.md`, `docs/era2_codex_brief.md`
