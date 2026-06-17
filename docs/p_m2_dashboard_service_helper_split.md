# P-M2 dashboard_service Evidence Row / AI Gate Helper Split

## Scope

P-M2 is a behavior-preserving helper extraction from `dashboard_service.py`.

The extraction is limited to evidence row construction and the one-row AI
context gate / blocked-reason policy. It does not change dashboard orchestration,
model execution order, public keys, schemas, endpoints, frontend UI, external
AI, Tavily/search, live fetches, or live writes.

## What Moved

The following helpers moved to
`src/app_backend/services/dashboard_evidence_policy.py`:

- evidence row construction
- evidence value text
- AI context allowed policy
- AI context blocked reason policy
- PPI observation-date block
- derived dependency hint gate
- AI blocked status / freshness / source-badge constants

## What Did Not Change

- Financial model semantics.
- Public output keys.
- Module, model, metric, or registry keys.
- Dashboard API schemas.
- Dashboard model pipeline order.
- P-M1 row conversion accumulator behavior.
- AI context eligibility semantics.
- Blocked reason precedence.
- PPI observation-date blocking behavior.
- Source, freshness, and trigger gates.
- Providers, endpoints, frontend UI, external AI, Tavily/search, persistence,
  live fetches, or live writes.

## Compatibility

`dashboard_service.py` keeps private aliases for the moved helpers:

- `_evidence_row`
- `_evidence_value_text`
- `_evidence_ai_context_allowed`
- `_ppi_observation_date_blocked_reason`
- `_ai_context_allowed`
- `_ai_context_blocked_reason`
- `_missing_value_text`
- `_derived_dependency_hint_complete`

Existing internal call sites and tests continue to resolve through those
private names.

## Validation

P-M2 adds `tests/test_dashboard_evidence_policy.py` for field-copy,
blocked-reason precedence, PPI date blocking, local freshness exception,
derived dependency hint gating, missing value text, compatibility aliases, and
forbidden-surface checks.

Full validation is recorded in the final task report.

## Next Recommended Task

P-M3 Historical Risk Normalization metadata helper split.
