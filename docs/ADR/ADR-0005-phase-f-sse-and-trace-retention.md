# ADR-0005: Phase F SSE and Trace Retention

Status: accepted

Approved date: 2026-06-30

Approved by: user

## Context

Agent runs need observable lifecycle events and replayable traces, while preserving privacy and avoiding raw provider or holdings leakage.

## Decision

Phase F trace records may persist sanitized lifecycle events, tool summaries, final status, warning codes, `holdings_included`, and `holdings_snapshot_sha256`. They must not persist raw prompts, raw provider responses, raw search queries, detailed holdings, API keys, local paths, or raw provider payloads.

SSE must mirror the same sanitized event contract and must not introduce a broader data surface than trace.

## Allowed Scope

- Local debug trace route for sanitized events.
- Lifecycle/status events needed for user-visible progress.
- Hash-only holdings trace metadata.

## Prohibited Scope

- Raw prompt/response persistence.
- Detailed holdings in SSE, trace, API, frontend console, or frontend state.
- Bulk deleting historical traces before a retention policy supersedes this ADR.

## Migration

Current implementation has sanitized trace, debug replay, date-partitioned trace paths, `index.jsonl`, per-session summary files, append-only event hash chains, graceful `trace_overflow` summary preservation, a backend `POST /api/agent/run/stream` SSE endpoint, runtime event callback bridging, process-local cancel registry, runtime cancellation checks before each new provider/tool/finalize call, and a frontend `fetch + ReadableStream` POST-SSE UI for progress, explicit cancel, and validated `brief_section` rendering. In-flight blocking provider/tool calls are allowed to return or time out before the next cancellation check.

Runtime and stream safeguards now include wall-clock, provider-call, and tool-call timeout budgets, heartbeat events during idle stream periods, disconnect-triggered cancellation through the process-local run registry, plus a bounded SSE queue that emits a sanitized overflow error instead of retaining unbounded pending events.

Provider retry trace events may persist only typed retry metadata such as `error_kind`, attempt count, maximum retries, and backoff seconds; they must not persist raw exception text, prompt content, provider request bodies, or provider response bodies.

## Validation

- `tests/ai/test_agent_trace_service.py`
- `tests/ai/test_agent_runtime_mocked.py`
- `tests/api/test_agent_trace_route.py`
- `tests/api/test_agent_stream_route.py`
- Trace tests verify `schema_version`, `event_sequence`, `previous_event_hash`, `event_hash`, overflow summary behavior, and absence of raw question / holdings details.
- Stream/runtime tests verify explicit cancellation returns `final_status=cancelled`, emits a sanitized cancelled SSE event, prevents subsequent tool dispatch, emits heartbeat events while a run is still active, requests cancellation when the client disconnects, enforces runtime timeouts, records typed provider retry metadata, and reports SSE queue overflow as a sanitized error.
- Frontend tests verify POST-SSE parsing, sanitized SSE error handling, cancel route calls, validated section rendering, and active-session cancellation.
