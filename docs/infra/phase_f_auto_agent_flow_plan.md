# Phase F Auto Agent Flow Plan

Status: implemented and smoke-verified on 2026-07-02.

Goal: replace open-ended ReAct behavior with a planned evidence pipeline plus
a constrained writer so the agent can choose tools autonomously, execute them
deterministically, and return a natural answer without inventing unsupported
claims.

| Slice | Purpose | Implementation | Gate | Current evidence |
| --- | --- | --- | --- | --- |
| F-AUTO-1 planning | Identify required tools before any model call. | `build_agent_tool_plan` maps topic markers to bounded tool steps. Search remains disabled unless confirmed. | Planner tests must prove local-first behavior and no raw question leakage in trace event. | `tests/ai/test_agent_information_plan.py` |
| F-AUTO-2 execution | Run planned tools once under budget control. | `run_agent_tool_plan` executes registry tools, dedupes calls, and records failures as outcomes. | Tool errors must degrade without aborting; evidence ledger may be absent in test/service mode. | `tests/ai/test_agent_tool_plan_runner.py` |
| F-AUTO-3 evidence pack | Convert tool outcomes into writer-safe evidence. | `build_evidence_pack` creates evidence cards, candidate facts, unavailable topics, and compact outcome summaries. | Candidate observed facts must validate against ledger atomic observations. | `tests/ai/test_agent_evidence_pack.py` |
| F-AUTO-4 writer prompt | Prevent model-side tool chasing and unsupported claims. | `build_evidence_writer_prompt` supports strict MacroBrief and `natural_answer` modes. | Prompt must forbid new tool calls and require evidence IDs/boundary language. | `tests/ai/test_agent_evidence_writer.py` |
| F-AUTO-5 repair | Deterministically repair strict MacroBrief payloads. | `repair_macro_brief_payload` aligns observed values with ledger records and drops unsupported facts. | Repaired payload must pass schema and claim-evidence validation. | `tests/ai/test_agent_macro_brief_repair.py` |
| F-AUTO-6 natural answer API | Expose a natural answer path without reopening ReAct. | `AgentRunRequest.output_mode="natural_answer"` runs plan -> tools -> evidence pack -> writer once. | Default strict path remains unchanged; natural text holdings leaks are blocked. | `tests/api/test_agent_run_route.py` |
| F-AUTO-7 smoke | Prove the whole planned natural pipeline runs end to end. | `scripts/run_phase_f_auto_agent_smoke.py` supports fixture and live provider modes. | Fixture and live reports must show one provider writing call, local tool execution, no holdings, no external search. | `docs/infra/phase_f_auto_run_fixture_latest.json`; `docs/infra/phase_f_auto_run_live_latest.json` |

## Gate Policy

Strict gates remain required for schema, evidence, privacy, and deterministic
fixture behavior. Live natural-answer wording is allowed to vary, but the live
report must preserve the raw check result instead of rewriting failures into a
pass. If a live provider omits required boundary language or returns an empty
answer, the report should remain `check_status="failed"` and the failure should
be handled in a follow-up slice.

## Verified Boundaries

- `include_holdings=false` for both F-AUTO smoke reports.
- `confirm_external_search=false`; no Tavily/search path is used in F-AUTO smoke.
- The writer receives no tool schema and makes exactly one provider call in the
  smoke reports.
- Natural answer text is scanned for holdings disclosure before returning.
- The response carries `natural_answer` and `rendered_markdown` for frontend
  compatibility while leaving `brief` and `partial_brief` empty.

## Latest Smoke Summary

Fixture report:

- Path: `docs/infra/phase_f_auto_run_fixture_latest.json`
- Status: `passed`
- Executed tools: `dashboard_query`, four `quote_etf` calls, `treasury_curve`
- Provider calls: `1`

Live report:

- Path: `docs/infra/phase_f_auto_run_live_latest.json`
- Status: `passed`
- Executed tools: `dashboard_query`, four `quote_etf` calls, `treasury_curve`
- Provider calls: `1`
- External search: disabled
