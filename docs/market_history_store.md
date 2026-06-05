# Market Historical Store

The market historical store is a local SQLite database for long-term market metric observations.
It is independent from the app state database and from the per-key last-good cache.

## Purpose

The Dashboard still has many `insufficient_history` rows.
This store provides the foundation for accumulating dated market observations so later phases can build historical derived metrics.

This phase only adds infrastructure, idempotent writes, ingest, audit fields, and tests.
It does not change Dashboard current values and does not calculate 30D or 60D returns.

## Storage

Default database path:

```text
data/market_history/market_history.sqlite3
```

The database is ignored by Git:

- `data/market_history/*.sqlite3`
- `data/market_history/*.sqlite3-*`

Only `data/market_history/.gitkeep` is tracked.

This database is separate from `data/app_state/app_state.sqlite3`.
Market history must not store app settings, favorites, account edits, portfolio holdings, or chat state.

## Schema

`schema_migrations`:

- `version INTEGER PRIMARY KEY`
- `applied_at TEXT NOT NULL`

`market_observations`:

- `id INTEGER PRIMARY KEY AUTOINCREMENT`
- `metric_key TEXT NOT NULL`
- `observation_date TEXT NOT NULL`
- `value_numeric REAL`
- `value_text TEXT`
- `value_type TEXT NOT NULL`
- `unit TEXT`
- `status TEXT NOT NULL`
- `source TEXT`
- `source_badge TEXT NOT NULL`
- `provider TEXT`
- `source_series TEXT NOT NULL DEFAULT ''`
- `generated_at TEXT`
- `fetched_at TEXT NOT NULL`
- `freshness_status TEXT`
- `ai_context_allowed INTEGER NOT NULL DEFAULT 0`
- `metric_kind TEXT NOT NULL DEFAULT 'raw'`
- `lineage_json TEXT NOT NULL DEFAULT '{}'`
- `raw_hash TEXT`
- `created_at TEXT NOT NULL`
- `updated_at TEXT NOT NULL`

Unique key:

```text
metric_key, observation_date, source_badge, source_series
```

Repeated writes to the same unique key update the existing row instead of inserting a duplicate.

## Store Service

The store service lives in:

```text
src/data_quality/market_history_store.py
```

It provides:

- `get_default_market_history_db_path`
- `connect_market_history_db`
- `initialize_market_history_db`
- `get_market_history_schema_version`
- `upsert_market_observation`
- `list_market_observations`
- `get_latest_observation`
- `count_observations_by_metric`
- `get_market_history_summary`

Importing the module does not create the database.
Initialization is explicit.

## Ingest Rules

The ingest script lives in:

```text
scripts/ingest_market_history_from_dashboard.py
```

Default mode is dry-run:

```powershell
python scripts/ingest_market_history_from_dashboard.py --dry-run
```

Write mode is explicit:

```powershell
python scripts/ingest_market_history_from_dashboard.py --write
```

The script reads Dashboard evidence rows and writes only compact market metadata.
It does not read raw holdings, call providers, call DeepSeek, call Tavily, or access the network.

Eligible rows must have:

- non-null value
- `observation_date`
- source badge not `missing`, `research_needed`, or `search-derived`
- status not `missing`, `research_needed`, `not_available`, `insufficient_history`, or `stale`

Excluded rows include:

- `portfolio_deviation`
- `holdings_updated_at`
- raw holdings-like payloads
- raw provider response
- raw prompt
- raw output text
- API-key-like content

Derived rows may be stored only when lineage metadata is available.
Proxy rows may be stored as `metric_kind=proxy`, but they are not promoted into AI factual context by the Dashboard gate.

## Relationship To Last-good Cache

Last-good cache keeps one recent usable value per metric in JSON files.
Market history stores dated observations in SQLite for long-term accumulation.

Neither one is the current live value.
This phase does not use market history to replace Dashboard values or compute current derived metrics.

## Privacy Boundary

The market history store saves only compact metadata and safe values.
It must not save:

- raw provider responses
- raw prompts
- raw holdings
- API keys
- full output reports
- complete project roots

## Future Work

Potential follow-up phases:

- historical derived metrics from market history
- yfinance batch history provider
- official macro pack
