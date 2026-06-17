# P-M4-A M11 Cross-request Shared Context Cache Design Review

## Scope

Design-only review for future M11 cache. No runtime cache implemented.

This document defines boundaries and acceptance criteria for a possible future
cross-request shared dashboard context cache. It does not change runtime code,
FastAPI routes, dashboard API behavior, model semantics, AI Context Manifest
eligibility, provider behavior, frontend UI, or refresh behavior.

## Current State

- `DashboardPipelineContext` is per-call only.
- `DashboardPipelineContext` currently stores `summary` and `evidence_table`.
- FastAPI routes do not share a context across HTTP requests.
- `/api/dashboard/summary` calls `build_dashboard_summary` directly.
- `/api/dashboard/evidence-table` calls `build_dashboard_evidence_table`
  directly.
- `/api/context/manifest` calls `build_ai_context_manifest` directly.
- AI preview routes call `build_ai_context_manifest` through
  `ai_preview_service` for context preview, chat preview, memo preview, and
  report preview.
- Existing context reuse is explicit and intra-call only: callers must pass a
  `DashboardPipelineContext`.
- `build_ai_context_manifest` can reuse a passed context, but no cross-request
  cache currently exists.
- P-M1, P-M2, and P-M3 are completed. P-M1 reduced repeated row conversion
  inside one pipeline build; P-M2/P-M3 moved helper policy code without runtime
  behavior changes.

## Motivation

When the frontend or local tooling calls `/api/dashboard/summary`,
`/api/dashboard/evidence-table`, `/api/context/manifest`, and AI preview routes
close together, the dashboard pipeline can be rebuilt multiple times across
HTTP requests.

P-M1 reduced redundant row-to-dict conversion inside one pipeline build, but it
does not share pipeline results across requests. The remaining design problem is
how to reuse current summary/evidence/manifest work safely without changing
stale semantics, `last_good` writes, privacy boundaries, filters, refresh state,
or AI Context Manifest inclusion/exclusion.

## Non-goals

- no external AI
- no endpoint expansion
- no live fetch/write
- no persistence of prompts
- no portfolio/account private expansion
- no model semantic changes
- no dashboard API schema changes
- no source/freshness/trigger gate changes
- no `write_last_good` behavior changes

## Candidate Cache Object

Future design object, not implemented in P-M4-A:

`SharedDashboardContextCache`

Candidate fields:

- `summary`
- `unfiltered_evidence_table`
- `ai_context_manifest`, optional, or derived from `unfiltered_evidence_table`
- `generated_at`
- `reports_dir`
- `market_history_db_path`
- `source_file_signatures`
- `cache_key`
- `stale_reason`
- `last_refresh_reason`

The object should store immutable or defensively copied response data. Callers
must not be able to mutate cached response objects and affect later responses.

## Cache Key Design

The future cache key must include:

- resolved `reports_dir` path
- resolved `market_history_db_path` path
- report file mtimes and sizes for required report files
- optional metadata report file signatures
- market history DB mtime and size, if present
- code/schema version marker
- app process version marker, if available

The cache key must not include:

- user prompts
- raw external AI payloads
- holdings line items
- private account values
- provider secrets

## Cache Scope

Recommended initial implementation:

- in-process only
- local backend process only
- no disk persistence
- no cross-user / account concept
- no background refresh
- no automatic live provider fetch
- no external AI involvement
- no writes to SQLite, `data/private`, `outputs`, or `cache`

## Cacheable Calls

Future candidates:

- `build_dashboard_summary` with default `reports_dir` and default market
  history path.
- `build_dashboard_evidence_table` for the unfiltered table with
  `write_last_good=False`.
- `build_ai_context_manifest` derived from cached evidence rows, only when those
  rows are current for the cache key.

Non-cacheable or separate-path calls:

- Filtered evidence table calls should filter a cached unfiltered table instead
  of becoming separate expensive rebuild keys.
- `write_last_good=True` behavior must not be hidden behind cache.
- Custom `reports_dir` or `market_history_db_path` should use a separate key or
  bypass cache.
- Provider health checks and refresh-run creation should remain outside this
  cache.

## Invalidation / Staleness

Invalidation triggers:

- report file mtime or size change
- optional metadata report file mtime or size change
- market history DB mtime or size change
- code/schema version change
- explicit refresh-run completion, if such a signal exists later
- conservative cache TTL, if used

Stale markers:

- `cache_hit`
- `cache_miss`
- `cache_invalidated_by_report_change`
- `cache_invalidated_by_market_history_change`
- `cache_bypassed_for_custom_path`
- `cache_bypassed_for_write_last_good`

## Side-effect Boundaries

Future implementation must preserve:

- `build_dashboard_evidence_table(write_last_good=True)` semantics.
- `last_good` write behavior must not be repeated silently from cache.
- `last_good` write behavior must not be suppressed when the caller explicitly
  asks for the write path.
- cache reads or writes must not write to `data/private`, `outputs`, `cache`, or
  SQLite.
- no live fetch/write
- no provider call

## Privacy Boundaries

Future implementation must preserve:

- no holdings line items
- no account values
- no position weights beyond already-sanitized compact context
- no prompt persistence
- no raw external AI payloads
- no expanded DeepSeek context
- no provider secrets or raw provider payloads
- no private report contents in cache diagnostics

The cache may hold only the same sanitized response objects already returned by
local dashboard/context services.

## AI Context Manifest Consistency

- Manifest may be built from cached evidence rows only if evidence rows are
  current for the cache key.
- Manifest output must preserve exclusion logic.
- Cache must not mark missing, research_needed, stale, insufficient-history, or
  not-available rows as included.
- Cache must not change `included_facts`, `excluded_facts`,
  `included_model_outputs`, or `excluded_model_outputs` semantics.
- Cache must preserve source badge, freshness, blocked reason, and
  `ai_context_allowed` fields exactly as produced by the current evidence
  pipeline.

## Failure Modes

- stale cache after file update
- DB mtime resolution edge cases
- accidental `write_last_good` suppression
- filtered table accidentally cached as unfiltered
- privacy boundary regression
- mutation of cached response objects by callers
- thread-safety under concurrent FastAPI requests
- test fragility from `generated_at`
- cache key path confusion for custom `reports_dir`
- cache hiding degraded audit state
- manifest inclusion/exclusion drift after source/freshness changes

## Proposed Implementation Phases

### P-M4-B

- Add cache key and file signature helpers.
- Keep route behavior unchanged, or add only an explicit service-level function.
- Add tests for file signatures, custom path keying, and forbidden private
  payload inputs.

Status: completed. P-M4-B added deterministic cache key and file signature
helpers only. No runtime cache, route integration, summary/evidence/manifest
caching, or `write_last_good` behavior change was implemented.

### P-M4-C

- Cache summary and unfiltered evidence table in process.
- Filtered evidence table responses filter cached unfiltered rows.
- Add tests for invalidation, custom path bypass or separate keys, no side
  effects, and defensive copies.

Status: completed. P-M4-C added an in-process single-slot cache for default-path
summary and unfiltered evidence table responses when `write_last_good=False`.
Filtered responses are derived from cached unfiltered rows and are not cached
directly. AI Context Manifest cache remains unimplemented.

### P-M4-D

- Optional manifest reuse from cached evidence table.
- Preserve AI Context Manifest inclusion/exclusion counts and model-output
  boundaries.
- No external AI.

## Acceptance Criteria for Future Implementation

- identical row count and module list for cached vs uncached evidence table
- identical included/excluded AI context counts
- no public key changes
- no `last_good` semantic changes
- cache invalidates on report file change
- cache invalidates on market history DB file change
- cache bypasses custom paths or uses separate keys
- filtered evidence calls do not poison the unfiltered table
- cached response mutation by one caller cannot affect later callers
- full validator passes
- route/security tests pass
- benchmark confirms fewer repeated rebuilds without changing output contracts
