# Stage 9.2 Security Review (Closeout)

Performed 2026-06-15 against commit `0240f7b` (post M7/M8-A extraction).

## Reviewed endpoints

| Method | Path | Purpose | Source of context |
|--------|------|---------|--------------------|
| GET  | `/api/ai/context-preview` | AI Context Manifest preview with local flags | `ai_context_service.build_ai_context_manifest()` |
| POST | `/api/ai/preview-chat`    | Deterministic chat preview (no external call) | Manifest + Stage 9.1 chat-section renderer |
| POST | `/api/ai/preview-memo`    | Deterministic memo preview | Stage 9.1 `render_ai_memo_preview` |
| POST | `/api/ai/preview-report`  | Deterministic report preview | Stage 9.1 `render_ai_memo_preview` |
| GET  | `/api/context/manifest`   | Underlying manifest | `ai_context_service` |

## Endpoint surface audit

- `/api/chat` — **not present** ✓
- `/api/search` — **not present** ✓
- `/api/ai/chat`, `/api/ai/search`, `/api/ai/deepseek`, `/api/ai/tavily` — **not present** ✓
- Save/favorite/report-export endpoints for AI output — **not present** ✓
  (`/api/app/favorites` exists for user-initiated app-level favorites only; not
  wired to the AI preview endpoints.)
- No endpoint name contains `deepseek`, `tavily`, or `external` ✓

Locked by `tests/test_stage9_2_security_closeout.py::test_required_preview_routes_exist`,
`test_no_forbidden_routes_present`,
`test_no_endpoint_name_implies_real_external_ai`.

## Context source policy

Preview services consume only:

- `ai_context_service.build_ai_context_manifest()` (manifest)
- `ai_memo_renderer.render_ai_memo_preview()` (Stage 9.1 deterministic templates)
- Manifest-derived counts, policy flags, and boundary text

Preview services do **not** import or read:

- `dashboard_model_pipeline.build_dashboard_model_rows` directly
  (must go through the manifest path)
- `data/holdings/current_holdings.csv`, `data/private/`, `.env`
- Any SQLite DB files
- Raw provider payloads / raw prompts
- Storage service for AI persistence

Locked by `test_ai_preview_service_does_not_import_dashboard_model_pipeline`,
`test_ai_memo_renderer_does_not_import_dashboard_model_pipeline`,
`test_ai_preview_service_does_not_open_private_files`, plus the existing
`test_preview_service_does_not_import_external_adapters`.

## M7/M8-A regression check

- `dashboard_model_pipeline.py` exists and exports
  `build_dashboard_model_rows`, `DashboardModelPipelineResult` ✓
- `dashboard_service.py` remains the public dashboard service entry point ✓
- Stage 9.2 preview endpoints route only through `dashboard_service` →
  `ai_context_service` → manifest ✓
- Benchmark row counts (locked by `scripts/benchmark_dashboard_pipeline.py`):
  evidence_row_count=219, included_facts=119, included_model_outputs=63 — same
  as Stage 8.5 baseline ✓
- D10–D19 / Stage 8 public output keys remain in evidence table
  (locked by `tests/test_golden_output_contract.py` and
  `tests/test_dashboard_model_pipeline.py`)
- Stage 8 overlay rows remain `derived` source badge and live only in the
  `portfolio_exposure_overlay` module ✓
- AI Context Manifest counts unchanged ✓

## Request handling policy

`/api/ai/preview-chat` does **not**:

- echo `request.question` text into any section content or `answer_preview`
- log or persist the question (no `logger`, no `print`, no DB write)
- include the raw prompt in any response field
- mutate behavior based on question content — only `style` and `context_mode`
  drive template selection (both are `Literal` types, schema-validated)

Edge cases locked:

- empty `""` question → 200 OK, deterministic output
- whitespace `"   \n\t   "` question → 200 OK, whitespace not echoed
- very long question (5000+ chars) → 200 OK, never appears in response body
- unsupported `style` → 422
- unsupported `context_mode` → 422
- repeated identical request → byte-identical response

Locked by `test_preview_chat_handles_*_question_safely`,
`test_preview_chat_rejects_unsupported_*`,
`test_preview_chat_deterministic_repeated_request`.

## Context mode audit

- `facts_only` mode: model outputs section returns
  `"Not used as support for this context mode."` and does not include model
  output labels ✓
- `model_outputs_only` mode: facts section returns same advisory and does not
  include fact labels ✓
- `full_sanitized` mode: summarizes both ✓
- Excluded facts/model outputs appear only in the
  `missing_or_excluded_constraints` section and never in
  `evidence_summary` / `model_output_summary` ✓
- Stage 8 portfolio overlay summary uses
  `portfolio_context_policy.mode = compact_summary_only`; raw holdings never
  appear ✓

Locked by `test_excluded_facts_appear_only_in_constraints_section`,
`test_stage8_overlay_remains_downstream_only_in_chat`, plus existing
`test_preview_chat_context_modes_limit_support`.

## Privacy scan summary

Response bodies for `/api/ai/context-preview`, `/api/ai/preview-chat`,
`/api/ai/preview-memo`, and `/api/ai/preview-report` are scanned for absence of:

- `current_holdings.csv`, `data/private`, `G:\local_macro_portfolio_ai`,
  `/mnt/data`, `C:\Users\`
- `HOLDINGS_AMOUNT_MUST_NOT_LEAK`, `RAW_FUND`
- `DEEPSEEK_API_KEY`, `TAVILY_API_KEY`
- API-key value patterns (`sk_live_`, `sk_test_`)

Schema-level privacy advertisement field names (`uses_holdings_line_items`,
`uses_raw_provider_payloads`, `uses_raw_prompts`) are intentionally allowed
because they advertise the boundary, not leak data.

Locked by `test_preview_*_body_contains_no_privacy_tokens`.

## Forbidden output scan summary

Memo and report body bodies (across all `memo_type` and `report_type` values)
are scanned for absence of: `buy`, `sell`, `add position`, `reduce position`,
`clear position`, `rebalance`, `target allocation`, `target weight`,
`expected return`, `predicted return`, `future return`, `market direction
probability`, `crash probability`, `recession probability`, `trade signal`,
`guaranteed`, `will rise`, `will fall`.

Locked by `test_preview_memo_body_contains_no_forbidden_*`,
`test_preview_report_body_contains_no_forbidden_*`.

## Validator gate summary

`validate_ai_preview_payload` now has regression locks for:

- `privacy_summary.external_model_called=True` → blocked
- `privacy_summary.search_called=True` → blocked
- `privacy_summary.saved_by_default=True` → blocked
- `not_sent_to_external_model` is not `True` → blocked
- `human_review_required` is not `True` → blocked
- empty `interpretation_boundary` → blocked
- neither sections nor boundary contain the canonical boundary phrasing →
  blocked
- forbidden generated-output terms (26 patterns) → blocked
- privacy-forbidden terms (16 patterns) → blocked

Locked by `test_validator_blocks_*` (8 new tests).

## Route / schema summary

All required preview routes present; no forbidden routes present; no endpoint
name implies external AI invocation. FastAPI `app.routes` iteration is the
authoritative check.

## Documentation updates

- `docs/stage9_2_security_review.md` (this file) — new
- `docs/current_project_state.md` — Stage 9.2 closeout entry added
- `docs/stage9_implementation_plan.md` — Stage 9.2 marked completed,
  Stage 9.3 approval gate noted

## Remaining risks

1. **No CI guard on forbidden-route additions.** A future PR could add a new
   AI endpoint that bypasses these tests if the closeout test file is not run
   in CI. Mitigation: keep `tests/test_stage9_2_security_closeout.py` in the
   default pytest run.
2. **Validator boundary-phrase check is OR-based.** As long as one of
   `interpretation_boundary` or section content contains
   "not an action directive" / "human review is required", the check passes.
   If a future change reuses the validator for a surface that legitimately
   omits the boundary phrase, the check is permissive. Acceptable for current
   scope.
3. **`/api/app/favorites` exists** for user-initiated app-level favorites.
   It is not wired to AI preview endpoints, but a future change could expose
   AI output through it. Stage 9.3 must not auto-save AI output through
   favorites.

## Stage 9.3 approval gate

Stage 9.3 (DeepSeek adapter) remains **not implemented**. Before Stage 9.3 may
begin, the following gates must be satisfied:

1. **Explicit user approval** in a separate task; this closeout does not
   approve Stage 9.3.
2. Stage 9.3 must be **disabled by default** and gated behind a
   user-controlled switch (e.g., env var + per-request opt-in).
3. Stage 9.3 must **not start automatically** on app start or page load.
4. Stage 9.3 must preserve all Stage 9.2 closeout guarantees: AI Context
   Manifest as the only context source, no raw prompt persistence, validator
   gates active, no allocation/return/probability language in generated
   output, no holdings line items in any prompt or response, fail-closed on
   external call failure.
5. Stage 9.3 must add its own contract tests rather than relax existing ones.

This closeout does **not** authorize Stage 9.3 by itself.
