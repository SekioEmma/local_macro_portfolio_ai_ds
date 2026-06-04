# SQLite App State

Phase 2 adds a local SQLite app state database for small application metadata. It is not a holdings source of truth and does not store raw model prompts, raw provider responses, raw output files, API keys, or private holdings.

## Path

Default database path:

```text
data/app_state/app_state.sqlite3
```

The database file and SQLite sidecar files are ignored by Git. `data/app_state/.gitkeep` is committed only to keep the directory shape.

## Schema Version

Current schema version: `1`

Migrations are idempotent and can be run repeatedly. The app creates `schema_migrations` and inserts the current version when initialized.

## Tables

`schema_migrations`

- `version INTEGER PRIMARY KEY`
- `applied_at TEXT NOT NULL`

`app_settings`

- `key TEXT PRIMARY KEY`
- `value_json TEXT NOT NULL`
- `updated_at TEXT NOT NULL`

Default settings:

- `ui_language`
- `default_context_mode`
- `search_enabled_by_default`
- `save_chat_by_default`
- `show_cost_detail`

`refresh_runs`

- `id INTEGER PRIMARY KEY AUTOINCREMENT`
- `kind TEXT NOT NULL`
- `status TEXT NOT NULL`
- `started_at TEXT NOT NULL`
- `finished_at TEXT`
- `summary_json TEXT NOT NULL DEFAULT '{}'`
- `error_summary TEXT`
- `created_at TEXT NOT NULL`

`favorite_answers`

- `id INTEGER PRIMARY KEY AUTOINCREMENT`
- `title TEXT`
- `question TEXT NOT NULL`
- `answer TEXT NOT NULL`
- `model TEXT`
- `context_snapshot_json TEXT NOT NULL DEFAULT '{}'
- `created_at TEXT NOT NULL`

Favorites are a placeholder foundation for future chat favorites. They currently store only sanitized fake metadata from the UI or tests.

## API

- `GET /api/app/storage`
- `GET /api/app/settings`
- `PUT /api/app/settings`
- `GET /api/app/refresh-runs`
- `POST /api/app/refresh-runs`
- `GET /api/app/favorites`
- `POST /api/app/favorites`

These APIs operate only on the local app state database. They do not refresh market data, call providers, call DeepSeek, call Tavily, or read holdings.

## Privacy Boundary

The app state repository rejects secret-like input containing `sk-...` or `API_KEY`-style strings. This keeps API keys out of SQLite, logs, responses, and test fixtures.

Do not store:

- API keys
- real holdings rows or full amounts
- raw prompt text
- raw provider responses
- raw output files
- private files from `data/private/`

## Development Reset

To reset the local development app state database:

```powershell
Remove-Item data/app_state/app_state.sqlite3 -ErrorAction SilentlyContinue
python scripts/run_app_backend.py
```

The backend recreates the database and default settings when the app state API is used.
