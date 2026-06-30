# ADR-0001: Document Authority Hierarchy

Status: accepted

Approved date: 2026-06-30

Approved by: user

## Context

Phase F adds runtime, API, trace, RAG, evidence, and detailed holdings rules. These rules must not be split across competing task plans.

## Decision

Current authority order is:

1. `docs/GOVERNANCE.md`
2. `docs/ADR/ADR-*.md`
3. `docs/ROADMAP.md`
4. `docs/era2_phase_*.md`
5. `docs/era2_codex_brief.md` and repo-local agent instructions
6. `docs/archive/*`

Task plans may describe implementation details, but they cannot create new data egress exceptions or weaken governance/ADR rules.

## Allowed Scope

- Update `ROADMAP.md` when current phase status changes.
- Update this ADR set when an approved boundary changes.
- Keep implementation taskbooks narrower than governance rules.

## Prohibited Scope

- Treat archived docs as current authority.
- Use a phase plan to override privacy, trace, RAG, provider, or API boundaries.
- Create a new external model, holdings, RAG, trace, or SSE exception without an ADR.

## Validation

- Documentation changes must keep `GOVERNANCE.md`, ADRs, and `ROADMAP.md` consistent.
- Code changes touching L4 boundaries must include targeted tests plus the relevant privacy/security tests.
