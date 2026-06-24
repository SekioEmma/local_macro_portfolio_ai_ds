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

## C4c: Acquisition result boundary hardening

C4c treats both the transport output and the writer result as untrusted boundaries.

### Transport payload guard (`_validate_transport_payload`)

Before the parser is called, each payload object is validated:

- `source`, `content_type`, and `body` attributes must be readable.
- `source` must normalise to the expected source key (`enum.value` or plain string).
- `content_type` must exactly match after stripping MIME parameters and lowercasing:
  - BLS: `text/calendar`
  - BEA: `application/json`
- `body` must be `str`, must be NUL-free, must be UTF-8 encodable, must not exceed 1 MiB.
- Any failure → `status="blocked"`, `error_codes=["invalid_response"]`.
- Remaining sources in the batch are not fetched. The writer is not called.
- Raw payload object, URL, headers, and exception text never enter the public summary.

### Parser exception guard

- `OfficialCalendarParseError` → its stable `.code` is recorded as-is.
- Any other `Exception` → converted to `"invalid_response"`. Exception text never enters the summary.
- `BaseException` is not caught.

### Writer result guard (`_validate_mutation_result`)

All of the following must hold for `status="ok"` to be returned:

1. Result must be an instance of `EconomicCalendarMutationResult`.
2. `result.status` must equal `"ok"`.
3. `event_count`, `created_count`, `updated_count` must each be a non-bool, non-negative `int`.
4. `result.event_count == len(all_events)`.
5. `result.created_count + result.updated_count == result.event_count`.

Any failure → `status="blocked"`, `error_codes=["write_failed"]`. Writer object repr, SQLite exception text, and raw event data never enter the public summary.

### What C4c does NOT change

- BLS and BEA remain the only sources.
- FOMC exact-time acquisition remains deferred.
- Transport, parsers, CLI, calendar schema, calendar service, and C4a/C4d semantics are unchanged.
- No new API route, frontend, scheduler, background task, RAG, embedding, vector store, or Agent.

## What remains not started

- Phase D: RAG, embedding, vector store
- No API route, frontend, scheduler, automatic refresh, background task, or Agent
