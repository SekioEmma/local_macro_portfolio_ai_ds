# App Frontend Dev

This Phase 1 web shell is read-only. It calls the local FastAPI backend and does not run market pipelines, provider refreshes, DeepSeek, Tavily, account writes, or SQLite.

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

## Read-only Boundaries

- No account editing.
- No holdings CSV reads in the frontend.
- No raw output display.
- No provider live check.
- No refresh POST endpoint.
- No DeepSeek or Tavily calls.
- No chat history storage.
- No complete project root display.

## CORS

The backend allows only local Vite origins:

- `http://127.0.0.1:5173`
- `http://localhost:5173`

Wildcard CORS is not allowed.

## Git Hygiene

Do not commit:

- `app_frontend/node_modules/`
- `app_frontend/dist/`
- `outputs/`
- `.env`
- private holdings or `data/private/`
