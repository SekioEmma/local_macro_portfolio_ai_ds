# Era 2 C4a Offline Economic Calendar Closeout

## Scope

C4a adds an offline economic-calendar foundation: fixed event contracts, a local SQLite schema, a synthetic fixture-only seed file, and an explicit local service for upserting and querying event metadata.

The tracked `data/economic_calendar_seed.json` file is synthetic fixture-only data for tests. It is not real, current, or future economic schedule data. Production service code does not automatically load it.

## Boundaries

C4a does not fetch BLS, BEA, Federal Reserve, Tavily, FRED, Alpha Vantage, yfinance, webpages, HTML, XML, SearchResult objects, or provider payloads.

C4a adds no API route, CLI, frontend, scheduler, background task, startup seed, page-load seed, or automatic refresh. Only explicit `EconomicCalendarService.upsert_events(...)` may write to the local calendar DB.

C4a stores event metadata only. It does not add actual, forecast, previous, surprise, value, score, probability, trading-signal, raw-provider-payload, account, holdings, position, transaction, embedding, chunk, or RAG fields.

`data/economic_calendar.sqlite` and SQLite sidecars are gitignored and remain prohibited for manual reading, printing, copying, or committing outside the narrow service runtime boundary.

## C4d — Read path boundary hardening

All three public methods (`upsert_events`, `next_releases`, `events_by_name`) now call the same `_validate_calendar_root()` guard before any `Path.exists()`, `sqlite3.connect()`, schema initialization, directory creation, or SQL query.

The guard walks the full ancestor chain from the DB file path to the filesystem root. Any symlink on the DB file itself, its immediate parent, or any higher ancestor causes an immediate `EconomicCalendarAdmissionError("invalid_calendar_root")`. An `OSError` during `is_symlink()` also fails closed with the same code.

Query methods (`next_releases`, `events_by_name`) do not silently return empty lists when the path is dangerous — they raise before reaching `Path.exists()`.

C4a remains offline-only. C4d does not change the catalog, source admission rules, ET window logic, fixture-only seed status, public metadata-only record shape, or any network boundary.

## Phase Handoff

C4b is the earliest phase where official schedule acquisition can be discussed. Phase D remains the future embedding, vector store, and RAG phase.
