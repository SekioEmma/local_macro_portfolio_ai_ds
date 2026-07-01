# Phase F DoD Audit

Status date: 2026-07-01

This audit maps the Phase F remediation Definition of Done to current repository evidence. It does not mark Phase F as `user_accepted`; human acceptance remains the final release gate.

## Summary

| Item | Evidence | Status |
|---|---|---|
| 文档权威层级已生效 | `docs/ADR/ADR-0001-document-authority-hierarchy.md`; `docs/GOVERNANCE.md`; `docs/INDEX.md`; `docs/ROADMAP.md`; `docs/era2_phase_f_plan.md` | implemented |
| 所有 ADR 已 accepted | `docs/ADR/ADR-0001-document-authority-hierarchy.md` through `docs/ADR/ADR-0006-rag-index-generation-and-embedding-compatibility.md` all contain `Status: accepted` | implemented |
| 详细 holdings consent / injection contract 已实现，production snapshot provider 未接线时 activation fail-closed，输出防泄露 guard 已 fail-closed | `GET /api/agent/capabilities` reports `holdings_snapshot_backend_not_wired`; consent endpoint does not issue tokens while unwired; typed `HoldingsSnapshot` rejects legacy `cost_basis`; `HoldingsOutputGuard` blocks account/quantity/cost/market value/P&L disclosure before API/SSE sections; `tests/ai/test_holdings_consent_service.py`; `tests/ai/test_holdings_snapshot.py`; `tests/ai/test_holdings_external_context_service.py`; `tests/ai/test_holdings_output_guard.py`; `tests/ai/test_agent_runtime_mocked.py`; `tests/api/test_agent_run_route.py`; `tests/api/test_agent_stream_route.py`; `app_frontend/src/api/client.test.ts`; `app_frontend/src/components/AIChatPage.test.tsx` | guarded foundation |
| Institution MEMO rights gate 已实现 | `docs/ADR/ADR-0003-institutional-memo-external-llm-policy.md`; `tests/ai/test_curated_rag_ingest.py`; `tests/ai/test_rag_evidence_governance.py` | implemented |
| Claim-Evidence Ledger 已实现 | `src/app_backend/services/run_evidence_ledger.py` stores atomic observations; `src/app_backend/services/claim_evidence_validator.py` binds observed fact `value` / `unit` / `as_of` to current-run ledger observations; `tests/ai/test_run_evidence_ledger.py`; `tests/ai/test_claim_evidence_validator.py`; `tests/ai/test_agent_evidence_ledger_registration.py`; `tests/ai/test_agent_runtime_mocked.py` | implemented |
| Temporal Alignment Gate 已实现 | `src/app_backend/services/temporal_alignment_service.py` prefers public news published dates and labels market age as working-day approximation; RAG `release_date` / `observation_period` / `vintage` propagate through chunk store, retrieval, and ledger; backend Markdown and SSE expose a server-owned temporal envelope; `tests/ai/test_temporal_alignment_service.py`; `tests/ai/test_rag_retrieval_service.py`; `tests/llm/test_chunk_text_store.py`; `tests/ai/test_macro_brief_renderer.py`; `tests/api/test_agent_stream_route.py`; `app_frontend/src/components/AIChatPage.test.tsx` | implemented |
| SSE 已实现 | `src/app_backend/services/agent_stream_service.py` emits sanitized lifecycle, heartbeat, cancellation, and brief-section events; client disconnects request cancellation through `AgentRunRegistry`; `tests/api/test_agent_stream_route.py` covers lifecycle, explicit cancel, disconnect cancel, heartbeat, queue overflow, holdings non-leakage, and unhandled exception sanitization; `app_frontend/src/components/AIChatPage.tsx`; `app_frontend/src/components/AIChatPage.test.tsx` | implemented |
| Trace 长期保存已实现 | `src/app_backend/services/agent_trace_service.py`; `src/app_backend/main.py`; `tests/ai/test_agent_trace_service.py`; `tests/api/test_agent_trace_route.py`; `docs/ADR/ADR-0005-phase-f-sse-and-trace-retention.md` | implemented |
| RAG generation contract 已实现 | `src/app_backend/services/rag_index_generation.py` records and validates generation, embedding model, embedding dimension, and chunking version compatibility; `src/app_backend/services/local_rag_runtime_factory.py` fail-closes nonempty runtime builds with missing or incompatible generation metadata; `src/app_backend/services/curated_rag_ingest.py`; `src/llm/vector_store.py` rejects configured embedding dimension mismatches; `scripts/validate_local_rag.py`; `tests/ai/test_validate_local_rag_script.py`; `tests/ai/test_curated_rag_ingest.py`; `tests/ai/test_local_rag_runtime_factory.py`; `tests/llm/test_vector_store.py`; `docs/ADR/ADR-0006-rag-index-generation-and-embedding-compatibility.md` | implemented |
| 所有关键测试通过 | Latest local gate: `python -m pytest -q tests/ai tests/api tests/contracts tests/llm` = `2884 passed, 14 skipped`; `python -m ruff check src tests scripts` passed; frontend typecheck/test/build = `21 passed` and build passed | verified locally |
| 真实受控 Agent run 验收通过 | `docs/infra/phase_f_controlled_run_live_latest.json` has `mode=live`, `check_status=passed`, `final_status=ok`, `warning_codes=[]`; fixture report also recorded | verified locally |
| ROADMAP、Governance、Phase Plan、API、前端行为一致 | `docs/ROADMAP.md`; `docs/GOVERNANCE.md`; `docs/era2_phase_f_plan.md`; `docs/infra/phase_f_release_checklist.md`; `tests/contracts/test_phase_f_quality_contract.py` | implemented |
| MacroBrief 产品边界标签固定呈现 | `src/app_backend/services/macro_brief_renderer.py`; `tests/ai/test_macro_brief_renderer.py`; `tests/api/test_agent_run_route.py`; `app_frontend/src/components/AIChatPage.tsx`; `app_frontend/src/components/AIChatPage.test.tsx` | implemented |

## F-RAG Compatibility Refresh

- RAG generation metadata now includes chunking version, embedding model, and
  embedding dimension compatibility evidence.
- Nonempty local RAG runtime builds fail closed when index generation metadata
  is missing, corrupt, or incompatible with the runtime embedding contract.
- Vector search rejects configured embedding dimension mismatches before
  upsert or query.
- Local RAG validation reports `index_compatibility_error` when compatibility
  checks fail.

## Release State

- Current phase state: `remediation_and_optimization`.
- User acceptance: `not user_accepted`.
- Production readiness: `not production_ready`.
- Required MacroBrief product label is rendered deterministically in backend Markdown and frontend UI: `研究辅助输出` / `非自动投资决策` / `需要用户审阅`.

## Controlled Run Evidence

- Fixture report: `docs/infra/phase_f_controlled_run_fixture_latest.json`
- Live report: `docs/infra/phase_f_controlled_run_live_latest.json`

Both reports record:

- run id
- current date
- market/policy/macro/public-news cutoffs
- tool call sequence
- evidence count
- official/public/institutional/local evidence counts
- unavailable modules
- `asynchronous_inputs`
- final status
- budget usage
- elapsed seconds
- the four Phase F acceptance questions

## Remaining Gate

The implementation-side DoD evidence is present. The status must remain `not user_accepted` until the user explicitly accepts the Phase F release after reviewing the release checklist and controlled run reports.
