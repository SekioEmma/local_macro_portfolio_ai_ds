# Era 2 C4a Offline Economic Calendar Closeout

## Scope

C4a adds an offline economic-calendar foundation: fixed event contracts, a local SQLite schema, a synthetic fixture-only seed file, and an explicit local service for upserting and querying event metadata.

The tracked `data/economic_calendar_seed.json` file is synthetic fixture-only data for tests. It is not real, current, or future economic schedule data. Production service code does not automatically load it.

## Boundaries

C4a does not fetch BLS, BEA, Federal Reserve, Tavily, FRED, Alpha Vantage, yfinance, webpages, HTML, XML, SearchResult objects, or provider payloads.

C4a adds no API route, CLI, frontend, scheduler, background task, startup seed, page-load seed, or automatic refresh. Only explicit `EconomicCalendarService.upsert_events(...)` may write to the local calendar DB.

C4a stores event metadata only. It does not add actual, forecast, previous, surprise, value, score, probability, trading-signal, raw-provider-payload, account, holdings, position, transaction, embedding, chunk, or RAG fields.

`data/economic_calendar.sqlite` and SQLite sidecars are gitignored and remain prohibited for manual reading, printing, copying, or committing outside the narrow service runtime boundary.

## Phase Handoff

C4b is the earliest phase where official schedule acquisition can be discussed. Phase D remains the future embedding, vector store, and RAG phase.
