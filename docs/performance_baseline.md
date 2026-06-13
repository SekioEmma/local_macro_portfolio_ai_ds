# Performance Baseline — Dashboard Pipeline

> **M1 window** (June 2026). Read-only audit only; no financial logic changed.
> Run `python scripts/benchmark_dashboard_pipeline.py` to regenerate timings.

---

## How to run

```bash
python scripts/benchmark_dashboard_pipeline.py
# optional overrides
python scripts/benchmark_dashboard_pipeline.py \
  --reports-dir outputs/reports \
  --market-history-db data/market_history/market_history.sqlite3
```

Output is JSON on stdout. No DB writes, no network calls.

---

## Current measured timings

These are wall-clock times on a local development machine with a populated
`market_history.sqlite3`. Times vary with DB size and hardware; treat these
as order-of-magnitude baselines, not SLAs.

Observed timings with 33,803 observations / 45 metrics in local `market_history.sqlite3` (June 2026 baseline):

| Path | Observed ms | Notes |
|---|---|---|
| `build_dashboard_summary` | 736 ms | reads JSON reports + labor fallback DB queries |
| `build_dashboard_evidence_table` | 1479 ms | includes `build_dashboard_summary` internally |
| `build_ai_context_manifest` | 1449 ms | calls `build_dashboard_evidence_table` internally |
| `build_historical_percentile_rows` (D13) | **557 ms** | 23 individual DB queries — primary hotspot |
| `build_liquidity_funding_rows` (D14) | 34 ms | 9 individual DB queries |
| `build_financial_stress_rows` (D10) | < 1 ms | pure in-memory after row assembly |
| `build_pullback_checklist_rows` (D11) | < 1 ms | pure in-memory after row assembly |
| `build_coverage_audit` (audit) | 3929 ms | calls summary + evidence_table independently |
| evidence_row_count | 118 rows | — |
| included_facts_count | 95 | — |
| included_model_outputs_count | 15 | — |

D10 and D11 timings above are partial isolations (D13+D14 dicts as input;
`base_rows` from dashboard_service internals are excluded). Actual in-request
D10/D11 compute is dominated by the row-assembly cost, not the in-memory
composite calculation.

---

## Confirmed hotspots

These are facts derived directly from reading the source code. Not guesses.

### 1. Redundant full-pipeline rebuilds across call sites

`build_dashboard_evidence_table` calls `build_dashboard_summary` internally.
`ai_context_service.build_ai_context_manifest` calls `build_dashboard_evidence_table`.
`audit_data_pipeline_coverage.build_coverage_audit` calls both
`build_dashboard_summary` and `build_dashboard_evidence_table` independently.

A single page load that touches `/summary`, `/evidence-table`, and
`/ai/context-preview` can trigger **3+ full pipeline rebuilds**. Running the
audit script on the same process adds a fourth.

**Source**: `src/app_backend/services/dashboard_service.py:510`,
`src/app_backend/services/ai_context_service.py:43`,
`scripts/audit_data_pipeline_coverage.py:180–188`.

### 2. D13 N+1 DB query pattern

`build_historical_percentile_rows` iterates over 23 `PERCENTILE_METRIC_SPECS`
and issues one `list_market_observations(metric_key=spec.source_metric_key)`
call per spec. Each call opens a new `sqlite3.connect()` connection, executes
a single-metric SELECT, and closes the connection. This is **23 separate
connection open/query/close cycles** per request.

**Source**: `src/data_quality/historical_percentile_metrics.py:104–108`,
`src/data_quality/market_history_store.py:173–203`.

### 3. D14 N+1 DB query pattern

`build_liquidity_funding_rows` issues one `_raw_row` call per `RAW_METRIC_KEY`
(9 keys). Each `_raw_row` calls `list_market_observations` with its own
`sqlite3.connect()` open/close cycle. **9 separate connection cycles** per request.

**Source**: `src/data_quality/liquidity_funding_stress.py:96–118`.

### 4. No connection pooling

`market_history_store.list_market_observations` opens `sqlite3.connect(path)`
on every call. There is no shared connection, connection pool, or thread-local
connection reuse. For D13+D14 combined this means **31 connection open/close
cycles per full evidence table build**.

**Source**: `src/data_quality/market_history_store.py:183`.

### 5. No request-scoped cache

No `@lru_cache`, `@cache`, or in-process memoization exists on any builder or
query function. Every HTTP request rebuilds all rows from scratch. The only
caching layer is the optional filesystem `last_good_cache` for individual
evidence rows (not for the full pipeline result).

**Source**: confirmed by grep — no `lru_cache` or `functools.cache` in
`src/data_quality/` or `src/app_backend/services/`.

### 6. Post-build evidence filter

Evidence table filters (`module`, `status`, `source_badge`, `ai_context_allowed`)
are applied **after** the full evidence pipeline completes. A filtered request
for a single module still runs D13 (22 queries), D14 (9 queries), D10, and D11.

**Source**: `src/app_backend/services/dashboard_service.py:544–554`.

---

## Suspected hotspots

These are risks inferred from code structure, not confirmed by profiling.

- **Frontend double-request**: if the frontend calls `/summary` and `/evidence-table`
  independently on the same page load, two full pipeline builds run in parallel.
  No shared cache means no deduplication. *(Not confirmed — depends on frontend
  request sequence.)*

- **`get_market_history_summary` N+1**: the function calls `get_latest_observation`
  per distinct metric key (one DB query per metric) after a batch COUNT query.
  If called frequently this could add up, but it is not called inside the hot
  evidence table path. *(Suspected minor cost on summary stats endpoint.)*

- **4-column UNIQUE index vs 2-column covering index**: the implicit UNIQUE index
  on `(metric_key, observation_date, source_badge, source_series)` lets SQLite
  use a range scan on `metric_key`. The `ORDER BY observation_date DESC` is the
  second column in the index, so SQLite may avoid a sort for within-metric ordering.
  However, the implicit index carries four columns; a dedicated
  `(metric_key, observation_date DESC)` covering index could be faster and
  reduce I/O. *(Suspected improvement; not confirmed by EXPLAIN QUERY PLAN.)*

- **D10/D11 `base_rows` I/O cost**: D10 and D11 are pure in-memory after row
  assembly. But the `base_rows` they receive include labor fallback DB reads
  (several queries via `_apply_labor_history_fallback`). The cost of these reads
  is embedded inside `build_dashboard_evidence_table` and not separately
  instrumented. *(Suspected contributor to total evidence table time.)*

---

## What must not change during optimization

Any M2/M3 optimization work **must not**:

- Change `source_badge`, `freshness_status`, `ai_context_allowed`, `missing`,
  or `insufficient_history` gate logic.
- Change D11 `pullback_systemic_risk_checklist` condition thresholds or
  classification rules.
- Change D12 AI context manifest privacy/destination policy.
- Change D10 `financial_stress_composite` scoring weights or interpretation hints.
- Change D13 percentile/z-score/robust-z computation or `PERCENTILE_METRIC_SPECS`.
- Change D14 liquidity/funding stress reference rows or their boundary text.
- Alter what rows are `ai_context_allowed`.
- Introduce network calls, DeepSeek, Tavily, Tauri, or ML/PCA/HMM models.
- Output buy/sell/hedge instructions, crash probability, or recession probability.
- Commit SQLite DB files, cache files, outputs, or holdings.

---

## Recommended M2

**Batch DB reads for D13 and D14.**

Replace the per-metric `list_market_observations(metric_key=...)` loop with a
single `SELECT * FROM market_observations WHERE metric_key IN (?, ...) ...`
query, then partition results by `metric_key` in Python. This reduces D13 from
22 queries + 22 connection cycles to 1 query + 1 connection, and D14 from 9 to 1.

Estimated impact: reduces evidence table build time by ~50–70% on a populated DB.

Implementation notes:
- Add `list_market_observations_batch(metric_keys, limit_per_key, db_path)` to
  `market_history_store.py`.
- Add schema-level unit test confirming no financial row values change.
- Add index migration test: `CREATE INDEX IF NOT EXISTS idx_market_observations_metric_key_date ON market_observations (metric_key, observation_date DESC)` inside `_run_migrations` under a new schema version.
- Do not change any public function signatures already used by ingest scripts.

---

## Recommended M3

**Request-scoped result sharing for summary → evidence → manifest call chain.**

The three call sites (`/summary`, `/evidence-table`, `/ai/context-preview`)
each rebuild the full pipeline independently. A lightweight
`_DashboardPipelineResult` dataclass (or `functools.lru_cache` with a per-request
key) could let the evidence table reuse the already-built summary, and the
manifest reuse the already-built evidence rows.

Estimated impact: eliminates 2 of the ~3 full rebuilds on a typical page load.

Implementation notes:
- Scope cache to a single HTTP request (e.g., pass a mutable context dict into
  the service functions, or use `starlette.requests.Request.state`).
- Do not use a process-level cache — report JSON files are mutable and a stale
  process-level cache would serve outdated data.
- Do not add caching to the audit script path — audit intentionally rebuilds.
- Confirm all existing tests still pass and no financial logic changes.

---

## Index migration note

If M2 batch query work is implemented, also add this migration in
`market_history_store._run_migrations` under `CURRENT_SCHEMA_VERSION = 2`:

```sql
CREATE INDEX IF NOT EXISTS idx_market_observations_metric_date
    ON market_observations (metric_key, observation_date DESC);
```

This index does not change any stored values or query semantics; it only
changes query planning. A migration test should confirm the index exists
after `initialize_market_history_db()`.
