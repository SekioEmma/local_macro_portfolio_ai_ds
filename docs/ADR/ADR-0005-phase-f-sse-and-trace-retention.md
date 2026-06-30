# ADR-0005: Phase F SSE and Trace Retention

Status: accepted

Approved date: 2026-06-30

Approved by: user

## Context

Agent runs need observable lifecycle events and replayable traces, while preserving privacy and avoiding raw provider or holdings leakage.

## Decision

Phase F trace records may persist sanitized lifecycle events, tool summaries, final status, warning codes, `holdings_included`, and `holdings_snapshot_sha256`. They must not persist raw prompts, raw provider responses, raw search queries, detailed holdings, API keys, local paths, or raw provider payloads.

Future SSE must mirror the same sanitized event contract and must not introduce a broader data surface than trace.

## Allowed Scope

- Local debug trace route for sanitized events.
- Lifecycle/status events needed for user-visible progress.
- Hash-only holdings trace metadata.

## Prohibited Scope

- Raw prompt/response persistence.
- Detailed holdings in SSE, trace, API, frontend console, or frontend state.
- Bulk deleting historical traces before a retention policy supersedes this ADR.

## Migration

Current implementation has sanitized trace, debug replay, date-partitioned trace paths, `index.jsonl`, per-session summary files, append-only event hash chains, graceful `trace_overflow` summary preservation, a backend `POST /api/agent/run/stream` SSE endpoint, runtime event callback bridging, and a process-local cancel registry seam. Frontend progress/cancel UI and deep cancellation propagation into in-flight provider/tool calls remain pending.

## Validation

- `tests/ai/test_agent_trace_service.py`
- `tests/api/test_agent_trace_route.py`
- `tests/api/test_agent_stream_route.py`
- Trace tests verify `schema_version`, `event_sequence`, `previous_event_hash`, `event_hash`, overflow summary behavior, and absence of raw question / holdings details.
- Future frontend SSE implementation must include privacy and lifecycle tests before acceptance.
