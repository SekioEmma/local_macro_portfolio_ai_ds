# Era 2 C4b Official Calendar Acquisition Closeout

## Scope

C4b adds guarded, manual, official economic schedule acquisition from BLS and BEA only.

### Supported sources

| Source key | URL | Format | Event keys |
|---|---|---|---|
| `bls` | `https://www.bls.gov/schedule/news_release/bls.ics` | ICS (text/calendar) | `consumer_price_index`, `employment_situation` |
| `bea` | `https://apps.bea.gov/API/signup/release_dates.json` | JSON (application/json) | `personal_income_and_outlays`, `gross_domestic_product` |

### What C4b does NOT collect

- `fomc_statement` — the existing schema requires an exact `HH:MM` release time. FOMC statement times cannot be determined from a fixed official URL without inferring "usually 14:00", which violates the no-inference constraint. FOMC acquisition is deferred to a future task that can source exact times.
- No Fed, FRED, IMF, World Bank, Tavily, news, or HTML scraping.

## Architecture

### Real transport

`src/data_providers/official_calendar_real_transport.py` is the only new file that imports `httpx`. It fetches exactly two fixed URLs with:

- `follow_redirects=False` (redirect = fail)
- Fixed 15-second timeout
- 1 MiB streaming body cap
- No retry
- No env, config, API key, dotenv, or credentials
- No request at import, construction, or factory time

Raw response body is kept in-process only. It is never persisted to SQLite, log, CLI output, error message, or public result object.

### Pure parsers

`src/app_backend/services/official_calendar_parsers.py` uses only the standard library. It does not import httpx, sqlite3, pathlib, FastAPI, or any provider/service.

- BLS parser: extracts CPI and Employment Situation from ICS VEVENTs, handles folded lines, UTC / TZID / floating datetimes (all converted to ET).
- BEA parser: extracts Personal Income and Outlays and GDP from the two exact JSON keys, requires offset-aware timestamps, converts to ET.
- Both parsers require all their respective event keys to be present. Missing keys fail closed.

### Acquisition service

`src/app_backend/services/official_calendar_acquisition_service.py` does not import httpx. It accepts an injected transport factory, calendar service, and now provider.

- `live=False` (default): zero transport, parser, or writer calls. Returns `planned`.
- `write=True, live=False`: returns `blocked` with `write_requires_live`.
- `live=True, write=False`: fetches and parses, returns `dry_run` with safe counts.
- `live=True, write=True`: fetches, parses, validates, and writes via a single `upsert_events` call. Any source failure blocks the entire batch.

### CLI

`scripts/ingest_official_economic_calendar.py` is explicit manual invocation only. Default is planned. `--live` enables fetch+parse. `--live --write` enables DB write. No scheduler, no background, no automatic refresh.

## C4a foundation status

C4a offline foundation remains unchanged:

- The tracked `data/economic_calendar_seed.json` is synthetic fixture-only data. Production service code does not automatically load it.
- `data/economic_calendar.sqlite` remains forbidden for manual reading, printing, copying, or committing.
- C4d hardened all three public methods to validate the full symlink ancestor chain before any DB access.

## FOMC statement — why deferred

The existing `economic_calendar_schema.sql` enforces `release_time_et` as `HH:MM` (exact time). FOMC statements have historically been released "typically around 14:00 ET" but the exact time varies. Inferring a default time would violate the schema's precision guarantee. C4b does not fetch Fed pages, does not write FOMC records, and does not create placeholder times.

## What remains not started

- C4c (if defined): further calendar features
- Phase D: RAG, embedding, vector store
- No API route, frontend, scheduler, automatic refresh, background task, or Agent
