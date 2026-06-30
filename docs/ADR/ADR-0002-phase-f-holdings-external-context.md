# ADR-0002: Phase F Holdings External Context

Status: accepted

Approved date: 2026-06-30

Approved by: user

## Context

Phase F may send detailed holdings context to the external MacroBrief LLM only for an explicitly requested agent run. The default system remains local-only and fail-closed.

## Decision

Detailed holdings context is allowed only through:

- `POST /api/agent/holdings-consent`
- `POST /api/agent/run`
- `POST /api/agent/run/stream`

The consent endpoint issues a process-local one-time token. It does not return holdings content. `AgentRunRequest.include_holdings=true` must include a valid `holdings_consent_token`. The token expires after 10 minutes and is consumed when a run starts with a server-side holdings snapshot.

## Allowed Scope

- Server-side injection into the MacroBrief system prompt after consent.
- Synthetic or injected snapshot providers in tests.
- Trace metadata containing only `holdings_included=true` and `holdings_snapshot_sha256`.

## Prohibited Scope

- Reading, printing, committing, or manually inspecting `data/holdings/`.
- Sending holdings through `research-deepseek`, `preview-*`, `context-preview`, normal RAG, normal search, background jobs, schedulers, or automatic refresh.
- Returning detailed holdings in API/SSE/debug response bodies.
- Sending account numbers, broker login identifiers, credentials, raw provider payloads, order history, transaction history, local paths, database paths, or environment variables.

## Migration

Current implementation is a guarded foundation: consent and injection contracts exist for sync and SSE agent runs, but the default snapshot provider is intentionally unwired.

## Validation

- `tests/ai/test_holdings_consent_service.py`
- `tests/ai/test_holdings_external_context_service.py`
- `tests/api/test_agent_run_route.py`
- `tests/api/test_agent_stream_route.py`
- `tests/ai/test_agent_trace_service.py`
