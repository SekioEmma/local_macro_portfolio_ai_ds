# P-M4-B Cache Key / File Signature Helpers

## Scope

Adds deterministic file-signature and cache-key helpers only.

P-M4-B is a production helper foundation for future M11 work. It does not
implement a runtime cache and is not wired into FastAPI routes or dashboard
service execution.

## What Was Added

- `FileSignature`
- `DashboardCacheKey`
- report file signature helpers
- market history DB signature helper
- deterministic digest helper
- cache bypass reason helper

## What Was Not Added

- no runtime cache
- no global cache object
- no route integration
- no dashboard API behavior change
- no summary/evidence/manifest caching
- no `write_last_good` change
- no provider/endpoint/frontend/external AI/live fetch/write

## Privacy Boundary

Cache key helpers use stat metadata only:

- resolved path
- existence
- file size
- mtime

They do not read JSON report contents, do not open SQLite contents, do not
parse provider payloads, and do not include holdings line items, account values,
prompt text, raw AI payloads, or provider secrets in cache key payloads.

## Relationship to P-M4-A

P-M4-B implements only the P-M4-A phase-B foundation: cache key and file
signature helpers. It keeps route behavior unchanged and leaves actual
cross-request summary/evidence/manifest caching for a later reviewed phase.

## Validation

- `PYTHONIOENCODING=utf-8 python -m pytest -q tests/test_dashboard_cache_key.py tests/test_m11_cache_design_boundaries.py`
- route/context/security contract tests
- `python scripts/dev_check_validator_boundaries.py`
- `git diff --check`
- full pytest
- dashboard benchmark, audit, and historical validation scripts

## Status

P-M4-B M11 cache key / file signature helpers: completed.

Next recommended task: manual review before P-M4-C in-process summary/evidence
cache implementation.
