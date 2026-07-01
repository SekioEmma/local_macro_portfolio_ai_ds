# ADR-0004: Claim Evidence Ledger and Temporal Alignment

Status: accepted

Approved date: 2026-06-30

Approved by: user

## Context

MacroBrief output must be auditable from each claim to current-run tool evidence, source class, and observation/release/access dates.

## Decision

Phase F introduces a run-scoped evidence ledger and temporal envelope:

- `confirmed_facts[*].evidence_ids` is required.
- `confirmed_facts[*].claim_status` is `observed`, `reported`, or `unavailable`.
- Observed facts must bind `value`, `unit`, and `as_of` to a current-run
  ledger `atomic_observations` entry.
- `judgments[*].evidence_ids` and `judgments[*].temporal_scope` distinguish analysis support from fact ids.
- MacroBrief may include report and data cutoff fields.

## Allowed Scope

- Official primary data can support observed facts when the evidence temporal status is observed.
- Public reporting and institutional research can support reported facts.
- Missing values must use unavailable status without carrying a numeric value.
- RAG, MEMO, and news evidence can support reported or interpretive claims;
  they do not become observed facts unless an atomic observation is present.

## Prohibited Scope

- Cite a fact without current-run evidence.
- Attach a valid evidence id to a different observed value, unit, or date.
- Treat institutional views as observed facts.
- Merge market, policy, macro, and news dates without displaying or validating cutoff differences.

## Migration

Current implementation adds schema, prompt, ledger, validator, temporal envelope foundations, server-side source projection, and automatic tool-result ledger registration when an agent run provides a `RunEvidenceLedger`. `AgentRunService` enables the run ledger by default; focused runtime tests may disable it when exercising legacy fixture behavior.

## Validation

- `tests/ai/test_macro_brief_schema.py`
- `tests/ai/test_macro_brief_prompt.py`
- `tests/ai/test_run_evidence_ledger.py`
- `tests/ai/test_agent_evidence_ledger_registration.py`
- `tests/ai/test_claim_evidence_validator.py`
- `tests/ai/test_agent_runtime_mocked.py`
- `tests/ai/test_temporal_alignment_service.py`
