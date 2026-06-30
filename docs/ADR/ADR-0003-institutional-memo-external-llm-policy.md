# ADR-0003: Institutional Memo External LLM Policy

Status: accepted

Approved date: 2026-06-30

Approved by: user

## Context

Institutional memos can be useful as interpretation inputs, but they are not official primary evidence and must not be mixed with observed market or official macro data.

## Decision

Institutional memo content may be used only as an `institutional_view` evidence tier. It must be labeled separately from official primary data, public reporting, licensed manual data, and local data foundation rows.

## Allowed Scope

- Use institutional memo excerpts as reported interpretation.
- Link institutional memo evidence through run-scoped `evidence_ids`.
- Include memo metadata in a ledger record when the source is allowed for the current run.

## Prohibited Scope

- Treat institutional views as observed facts.
- Convert institutional memo conclusions into official evidence.
- Add institutional memo content to ordinary RAG without the RAG governance path.
- Expose raw private memo text through API, SSE, trace, or debug response bodies.

## Validation

- `tests/ai/test_claim_evidence_validator.py` verifies observed facts cannot rely on institutional views as direct observations.
- Future memo ingestion must add source-specific tests before enabling runtime use.
