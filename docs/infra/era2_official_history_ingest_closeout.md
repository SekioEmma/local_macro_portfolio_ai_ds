# Era 2 C2 Official History Ingest Closeout

## Scope

C2 adds an explicit, manual, guarded ingest layer for approved official historical data. It supports only two route keys:

- `fred_rates`
- `bls_cpi`

The CLI defaults to planned dry-run behavior. `--live` is required before any provider fetch can occur, and `--live --write` is required before any market-history write can occur.

## Boundaries

C2 does not accept URL, SearchResult, Tavily result, search result, webpage HTML, or arbitrary webpage text as market-history input. It does not directly scrape webpages.

FRED rate observations always keep `source_badge=official_fallback`. BLS CPI observations always keep `source_badge=official`. Every observation must pass `official_history_ingest_guard` before the writer is called.

C2 route writes are all-or-nothing. Every required source series for a route must produce at least one qualified raw observation before admission validation and before any writer call. Empty results and partial route results are `blocked`; `--live --write` is permission to write only after route completeness and admission both pass.

The writer summary is also treated as an untrusted boundary. A missing, malformed, non-integer, negative, or count-mismatched summary is `write_failed`; it is never reported as `written`.

C2 does not create an API route, frontend control, background task, scheduler, cache, startup call, or page-load call. Raw provider payloads are never written to market history, and raw URLs, snippets, API keys, account data, holdings, positions, transactions, prompts, and raw outputs are rejected before write.

C2 is a manual guarded ingest path, not automatic data refresh or background ingest.

## Phase Handoff

C3 is still the knowledge-base phase. C4 is still the economic-calendar phase. C2 does not start RAG, agent runtime work, frontend work, search persistence, or arbitrary provider ingestion.
