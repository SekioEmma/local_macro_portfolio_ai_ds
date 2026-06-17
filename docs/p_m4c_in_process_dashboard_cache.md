# P-M4-C In-process Summary / Evidence Cache

## Scope

P-M4-C implements an in-process cache for the dashboard summary and unfiltered
evidence table only. The cache is local to the backend process and is used only
for default-path requests with `write_last_good=False`.

## What Was Implemented

- shared single-slot cache object
- default-path cache key using P-M4-B file signatures
- summary reuse from a populated evidence cache
- unfiltered evidence table reuse
- filtered calls filter cached unfiltered rows
- defensive copies on cache set/get
- `write_last_good=True` bypass
- custom `reports_dir` / `market_history_db_path` bypass

## What Was Not Implemented

- no AI Context Manifest cache
- no disk cache
- no background refresh
- no external AI
- no endpoint or frontend change
- no live fetch/write
- no provider calls
- no public cache diagnostics

## Invalidation

The cache key changes when any of these stat signatures change:

- required report file size or mtime
- optional report file size or mtime
- market history DB file size or mtime
- schema marker
- resolved default reports directory
- resolved default market history DB path

## Boundaries

- no model semantics changed
- no AI context eligibility changed
- no public output keys changed
- no module/model/metric/registry keys changed
- no private payload in cache key
- no report contents read into cache key
- no SQLite contents opened for cache key
- no `write_last_good` side-effect suppression

## Validation

- `PYTHONIOENCODING=utf-8 python -m pytest -q tests/test_dashboard_context_cache.py tests/test_dashboard_cache_key.py tests/test_m11_cache_design_boundaries.py tests/test_m3_dashboard_pipeline_context.py tests/test_dashboard_model_pipeline.py`
- route/context/security contract tests
- full pytest
- dashboard benchmark
- audit and historical validation scripts
- validator boundary script
- `git diff --check`

## Status

P-M4-C In-process Summary / Evidence Cache: completed.

Next recommended task: P-M4-D optional AI Context Manifest cache review, or
defer cache work and return to S2 only after an explicit decision.
