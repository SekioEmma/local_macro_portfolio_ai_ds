# Local Macro Portfolio AI DS

Local-first macro risk research workbench. CS learning vehicle > macro research > investment tool.

## Quick Start

```bash
# Backend (FastAPI + Uvicorn)
cd src && python -m uvicorn app_backend.main:app --reload --host 127.0.0.1 --port 8000

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
- **AI**: Local deterministic preview only. External LLM calls disabled by default via 22-flag runtime policy guard.

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
- Read `os.environ` / `os.getenv`
- Import `httpx` / `requests` / `aiohttp`
- Make real network calls
- Add endpoints: `/api/chat`, `/api/search`, `/api/ai/deepseek`, `/api/ai/external`, `/api/ai/tavily`
- Send raw questions/prompts/holdings/account/position/transaction data or local paths
- Change D10-D19 or Stage 8 financial semantics
- Broaden AI Context Manifest eligibility
- Weaken `guard_response` blocking when `external_model_called=True`

## Key Design Invariants

- `ExternalAIRuntimePolicy` has 10 required-true gates + 12 required-false dangerous permissions. Default: fail-closed.
- `ExternalAIAdapterConfig` defaults: `enabled=False`, `mode="disabled"`, `allow_network=False`
- All AI preview endpoints are local/deterministic only — no LLM calls
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
- Frontend: `app_frontend/src/App.tsx`, `app_frontend/src/api/client.ts`, `app_frontend/src/components/`
- Docs entry point: `docs/INDEX.md`, `docs/short_term_development_plan.md`
