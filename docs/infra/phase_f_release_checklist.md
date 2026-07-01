# Phase F Release Checklist

## Status

- Current phase state: `remediation_and_optimization`.
- User acceptance: `not user_accepted`.
- Production readiness: `not production_ready`.
- MacroBrief output label: `研究辅助输出` / `非自动投资决策` / `需要用户审阅`.

This checklist is the release gate for Phase F MacroBrief Agent remediation. It does not approve automatic trading, order placement, background agents, scheduled search, broker sync, raw holdings export, or any frozen capability.

## Automated Gates

Run these before requesting human acceptance:

```bash
python -m ruff check src tests scripts
python -m pytest tests/ai tests/api tests/contracts -q
python scripts/run_phase_f_controlled_agent_smoke.py --report-path docs/infra/phase_f_controlled_run_fixture_latest.json
cd app_frontend && npm.cmd run typecheck
cd app_frontend && npm.cmd test
cd app_frontend && npm.cmd run build
```

The controlled smoke must return:

```text
check_status=passed
final_status=ok
warning_codes=[]
include_holdings=false
external_search_confirmed=false
validation_record.run_id=<session id>
validation_record.current_date=<NY/server date>
validation_record.acceptance_questions=[...]
validation_record.cutoffs.market_data_cutoff=<date or null>
validation_record.tool_call_sequence=[...]
validation_record.evidence_counts.official=<count>
validation_record.evidence_counts.public=<count>
validation_record.evidence_counts.institutional=<count>
validation_record.evidence_counts.local_data_foundation=<count>
validation_record.unavailable_modules=[...]
validation_record.asynchronous_inputs=<bool>
validation_record.budget_usage.steps=<count>
validation_record.elapsed_seconds=<seconds>
```

CI must also run `python scripts/run_phase_f_controlled_agent_smoke.py` so the fixture-mode critical path is covered without external API calls, holdings context, `.env`, raw data, or `outputs`.

## Dependency And Coverage Strategy

- Python dependency authority remains `requirements.txt` plus `requirements-dev.txt`; CI caches pip from those files.
- Frontend dependency authority remains `app_frontend/package-lock.json`; CI uses `npm ci`.
- No new dependency is required for the Phase F controlled smoke or release checklist.
- Critical path coverage is split across `tests/ai`, `tests/api`, and `tests/contracts`; the release gate treats these as Phase F coverage, not only unit coverage.

## Manual Acceptance Checklist

- ADR-0001 through ADR-0006 are `accepted`.
- `POST /api/agent/run` and `POST /api/agent/run/stream` preserve default `include_holdings=false`.
- Holdings consent token is one-time, session-bound, expires, and never returns holdings content.
- Server-side holdings injection is fail-closed when the snapshot provider is unwired.
- Trace records only holdings metadata and sanitized runtime events.
- SSE events are monotonic, sanitized, cancellable, and emit brief sections only after validation.
- Claim-evidence ledger rejects unbound facts, fabricated evidence ids, and incompatible source projection.
- Temporal alignment exposes asynchronous inputs instead of silently merging dates.
- RAG runtime refuses incompatible embedding generations and invalidates stale cached generations.
- Institutional MEMO material remains institutional view, not official evidence.
- MacroBrief rendered output contains research auxiliary / non-automatic-decision / user-review status language.
- ROADMAP, Governance, frontend behavior, API behavior, and this checklist agree on `not user_accepted` until a human explicitly accepts the release.

## Controlled Live Run

Fixture mode is the CI gate. A live provider run is optional and manual only:

```bash
python scripts/run_phase_f_controlled_agent_smoke.py --mode live --report-path docs/infra/phase_f_controlled_run_live_latest.json
```

Run live mode only after the user approves use of configured external APIs for this release check. Live mode uses the real DeepSeek provider with the same controlled `treasury_curve` + `finalize_macro_brief` tool registry; it does not enable Tavily, RAG, holdings, background jobs, or raw data reads. If the live provider lacks credentials or fails a guard, the result remains a failed release check, not an exception to the gate.
