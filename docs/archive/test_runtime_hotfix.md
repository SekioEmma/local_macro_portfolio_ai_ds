# HF-1 Test Runtime Hotfix

## Scope

HF-1 is a test fixture/runtime optimization only.

It does not change financial model semantics, D13 formulas or gates, D16
behavior, AI context eligibility, validator boundaries, providers, endpoints,
frontend UI, external AI, Tavily/search, live fetches, or live writes.

## Problem

A small DB-backed D13 test cluster and benchmark test cluster dominated full
pytest runtime.

The waste was fixture/runtime overhead rather than test count:

- D13 tests repeatedly inserted hundreds or thousands of SQLite rows through
  one-row `upsert_market_observation` calls.
- Benchmark tests repeatedly executed the full benchmark pipeline for output
  shape, privacy, timing, and call-path assertions that can safely share one
  read-only result.

## Changes

- Added `tests/helpers/market_history_fixtures.py` with test-only market
  history seed helpers.
- Replaced repeated D13 one-row SQLite fixture setup with one-connection,
  `executemany`, single-commit inserts against per-test temporary DB files.
- Reused a module-scope benchmark result for read-only assertions over the same
  minimal reports directory and missing DB case.
- Kept write-safety, raw-holdings, populated-DB, missing-DB, and empty-DB
  benchmark checks explicit and independent where side effects matter.

## Production Impact

Production code did not change.

The batch insert helper lives under `tests/helpers/` and uses temporary DB
paths supplied by each test. It does not read or write the real market history
DB and does not alter `market_history_store` behavior.

## Results

Before HF-1:

- D13 targeted tests: 231.86 seconds.
- Benchmark targeted tests: 170.85 seconds.
- Full pytest latest available pre-HF-1 run: 1339 passed in 547.20 seconds.

After HF-1 targeted runs:

- D13 targeted tests: 4.64 seconds.
- Benchmark targeted tests: 55.68 seconds.
- Full pytest: 247.06 seconds.

## Boundaries

- No model semantics changed.
- No D13 percentile, z-score, robust-z, 5Y gate, or 3Y gate changed.
- No D16 scenario severity or uncertainty semantics changed.
- No AI context rule changed.
- No provider, endpoint, frontend UI, external AI, Tavily/search, live fetch,
  or live write was added.
- No test assertion was skipped or weakened.

## Next Recommended Task

P-M1 dashboard_model_pipeline `_to_dicts` accumulator optimization.
