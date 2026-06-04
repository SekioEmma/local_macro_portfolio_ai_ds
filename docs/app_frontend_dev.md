# App Frontend Dev

This local web shell calls the FastAPI backend and does not run market pipelines, provider refreshes, DeepSeek, Tavily, or account writes. Phase 2 adds SQLite app state for settings and placeholder metadata only.

## Backend

Start the local API backend from the project root:

```powershell
python scripts/run_app_backend.py
```

The backend binds to `127.0.0.1:8765`.

## Frontend

Install dependencies once:

```powershell
cd app_frontend
npm install
```

Start the Vite dev server:

```powershell
npm run dev
```

Open:

```text
http://127.0.0.1:5173
```

## API Base URL

The frontend reads `VITE_API_BASE_URL` and defaults to:

```text
http://127.0.0.1:8765
```

The frontend calls only:

- `GET /api/status`
- `GET /api/provider-health`
- `GET /api/dashboard/summary`
- `GET /api/app/storage`
- `GET /api/app/settings`
- `PUT /api/app/settings`
- `GET /api/app/refresh-runs`
- `POST /api/app/refresh-runs`
- `GET /api/app/favorites`
- `POST /api/app/favorites`

The app state `PUT`/`POST` endpoints write only local SQLite app metadata. They are not market refresh endpoints and do not run providers.

## Dashboard Key Metrics

The market dashboard reads `modules.*.key_metrics` from `GET /api/dashboard/summary`.
Each module card shows compact metric rows with:

- display name
- value text
- status
- source badge
- freshness status
- missing or research-needed reason when applicable

The UI should not show unexplained `--` for primary metrics. Missing, stale, research-needed, insufficient-history, and not-available states must be visible.

Provider health `not_run_yet` means the local health-check cache has not been generated yet. It does not mean all providers are broken.

Data freshness is shown as a compact file/status/generated-at/stale-cache list, not as raw JSON.

Sparkline placeholders are not shown in this phase. Refresh and export actions remain later-phase work unless a matching backend API exists.

## Read-only Boundaries

- No account editing.
- No holdings CSV reads in the frontend.
- No raw output display.
- No provider live check.
- No refresh POST endpoint.
- No DeepSeek or Tavily calls.
- No chat history storage.
- No complete project root display.
- No raw prompt, raw provider response, raw output, or API key storage.
- No holdings source migration.

## CORS

The backend allows only local Vite origins:

- `http://127.0.0.1:5173`
- `http://localhost:5173`

Wildcard CORS is not allowed.

## SQLite App State

Phase 2 stores local app metadata at:

```text
data/app_state/app_state.sqlite3
```

The frontend diagnostics page can display storage status, update basic settings, and create placeholder refresh/favorite rows. It does not send real chat, holdings, model prompts, or provider responses.

Reset a development database by deleting it and restarting the backend:

```powershell
Remove-Item data/app_state/app_state.sqlite3 -ErrorAction SilentlyContinue
python scripts/run_app_backend.py
```

## Git Hygiene

Do not commit:

- `app_frontend/node_modules/`
- `app_frontend/dist/`
- `data/app_state/*.sqlite3`
- `outputs/`
- `.env`
- private holdings or `data/private/`
