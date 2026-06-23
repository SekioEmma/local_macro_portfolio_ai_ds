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
- Add `/api/chat`, `/api/ai/deepseek`, `/api/ai/external`, or `/api/ai/tavily` (the bare `/api/ai/deepseek` stays forbidden; the sanctioned model endpoint is `/api/ai/research-deepseek`)
- Add `/api/search/tavily` before the separately approved TASK-B7
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
- `/api/search/tavily` remains forbidden until the separately approved TASK-B7.

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
