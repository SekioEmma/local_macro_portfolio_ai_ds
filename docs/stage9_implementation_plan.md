# Stage 9 Implementation Plan

## Stage 9.0 AI Readiness Design

Status: current task.

- Create docs and contracts only.
- Define AI Context Manifest consumption rules.
- Define memo/report context rules.
- Define staged implementation gates.
- Do not implement real AI integration.
- Do not change Python or TypeScript production behavior.

## Stage 9.1 Memo Template / Context Contract

Status: completed.

- Build deterministic memo templates only.
- Render locally.
- Consume AI Context Manifest only.
- Preserve included/excluded context boundaries.
- Add validator checks before display.
- No external model call.
- No persistent chat.
- No Tavily.
- No holdings exposure.
- No frontend chat UI.
- No persistent chat.
- No automatic report saving.
- Next step after Stage 9.1 is Stage 9.2 Mock Chat / Mock Memo, not Stage 9.3
  DeepSeek.

## Stage 9.2 Mock Chat / Mock Memo

Status: completed.

- Add mock/local preview endpoints only.
- Use a deterministic renderer.
- Show manifest-derived context preview.
- Run validator before output is accepted.
- Expose local preview API endpoints for context, mock chat, mock memo, and
  mock report review.
- No DeepSeek.
- No Tavily.
- No network.
- No raw prompt persistence.
- No holdings exposure.
- No automatic report saving.
- No frontend chat UI.

## Stage 9.2 Closeout / Security Review

Status: completed 2026-06-15 (commit on app-mvp after M7/M8-A extraction).

- Endpoint surface audit: required preview routes present; `/api/chat`,
  `/api/search`, DeepSeek/Tavily, save/favorite/report-export endpoints absent.
- Context source audit: preview services consume only AI Context Manifest +
  Stage 9.1 deterministic renderer; do not import dashboard_model_pipeline
  directly, do not open private files, do not read SQLite/holdings/.env.
- M7/M8-A regression check: row counts, public output keys, Stage 8 overlay
  gates, and AI Context Manifest counts all unchanged after the pipeline
  extraction.
- Request handling audit: chat preview does not echo `request.question`,
  handles empty/whitespace/very-long question safely, rejects unsupported
  style/context_mode (422), and is byte-deterministic across repeated calls.
- Context-mode audit: facts_only / model_outputs_only / full_sanitized
  boundaries hold; excluded rows remain constraints only; Stage 8 overlay
  stays downstream-only with compact_summary_only policy.
- Privacy scan: no holdings line items, account values, raw provider
  payloads, raw prompts, API keys, .env, data/private, or local private
  paths appear in any preview response body.
- Forbidden output scan: no buy/sell/add/reduce/clear position, rebalance,
  target allocation/weight, expected/predicted/future return, market
  direction/crash/recession probability, guaranteed/will rise/will fall
  terms in any preview body.
- Validator gates: flag-level blocks for external_model_called=true,
  search_called=true, saved_by_default=true, missing not_sent_to_external_model,
  missing human_review_required, missing interpretation_boundary, and missing
  boundary notice are all locked by regression tests.
- Documented in `docs/stage9_2_security_review.md`; locked by
  `tests/test_stage9_2_security_closeout.py` (34 new tests).
- Stage 9.3 DeepSeek is NOT approved by this closeout and requires a
  separate explicit user approval task before work may begin.

## Stage 9.3 DeepSeek Adapter Behind Explicit User-Controlled Switch

### Stage 9.3-A Adapter Skeleton

Status: completed 2026-06-15 (commit on `app-mvp` after Stage 9.2 closeout).

- Disabled-by-default adapter skeleton, no real network call, no API key
  read, no `.env` read.
- Files added: `src/app_backend/schemas/ai_external.py`,
  `src/app_backend/services/ai_external_adapter.py`,
  `src/app_backend/services/deepseek_adapter.py`.
- Defaults: `enabled=False`, `mode="disabled"`, `allow_network=False`,
  `requires_user_switch=True`, `requires_context_preview=True`,
  `requires_validator=True`, `save_raw_prompt=False`, `save_raw_response=False`.
- `FakeDeepSeekAdapter` returns deterministic local text only; flags
  `external_model_called=False`, `fake_response=True`,
  `not_saved_by_default=True`, `human_review_required=True`.
- `guard_config` / `guard_request` / `guard_response` fail-closed on
  network mode, allow_network, save_raw_prompt, save_raw_response,
  forbidden field names (holdings / account / position / transaction /
  api_key / raw_prompt / file_path / env_value / search_results),
  forbidden tokens, and missing boundary/validator markers.
- Stage 9.2 preview endpoints do not import the adapter; no new HTTP
  routes added; no httpx/requests/aiohttp imports anywhere in the
  adapter source.
- 80 fail-closed unit tests in
  `tests/test_deepseek_adapter_skeleton.py` and
  `tests/test_ai_external_adapter_guards.py`.
- Documented in `docs/stage9_deepseek_adapter_design.md`.
- Stage 9.3-A completion does NOT authorize Stage 9.3-B; explicit
  approval still required.

### Stage 9.3-A Closeout / Adapter Guard Hardening

Status: completed 2026-06-15.

- ExternalAI Pydantic schemas reject extra fields to prevent silent acceptance
  of raw prompt, holdings, API key, raw response, account value, or other
  undeclared caller-provided fields.
- `guard_response` now blocks `validator_result.passed=False`.
- `guard_response` now scans response content for Stage 9.2-mirrored forbidden
  generated-output terms, including action, allocation, return-estimation,
  probability, and guarantee phrasing.
- `guard_response` now scans response content for privacy forbidden tokens,
  including API key markers, private path markers, holdings/account/position
  language, raw provider payload language, and external LLM config markers.
- `FakeDeepSeekAdapter` remains deterministic and passes the strengthened
  response guard.
- Default disabled adapter behavior remains fail-closed.
- Stage 9.3-B real DeepSeek integration remains not implemented and not
  approved.

### Stage 9.3-B Readiness Review / External AI Integration Seam Audit

Status: completed 2026-06-15 (commit on `app-mvp`).

- Documentation state drift fixed in `docs/current_project_state.md`
  (next step now states Stage 9.3-B readiness review, not Stage 9.3-A
  closeout).
- Added `src/app_backend/services/ai_external_request_builder.py` with
  `build_external_ai_request_from_manifest(...)` as the ONLY safe path
  from AI Context Manifest to `ExternalAIRequest`. The builder rejects
  any `question` / `prompt` parameter at the signature level, defaults to
  `mode="fake"`, and rejects `mode="network"` at the entry point. It
  runs `guard_request` internally so callers cannot get an unchecked
  request.
- Hardened `guard_request` to recursively scan `raw_request` nested
  keys and nested string values so that attempts like
  `{"meta": {"holdings_line_items": ...}}` or
  `{"meta": {"note": "API_KEY=sk_live_..."}}` are caught.
- Stage 9.2 preview endpoints still do NOT import the builder or the
  adapter; no new HTTP routes; no httpx/requests/aiohttp imports
  anywhere in the adapter / builder source.
- Documented the required Stage 9.3-B integration seam order in
  `docs/stage9_deepseek_adapter_design.md`:
  manifest preview → builder → `guard_request` → (future external call)
  → `guard_response` → Stage 9.2 generated-output validator → human
  review → no raw persistence by default.
- Locked by new `tests/test_ai_external_request_builder.py` and
  additional nested-input tests in
  `tests/test_ai_external_adapter_guards.py`.
- Benchmark row count 219/119/63 unchanged. Validator boundaries
  allowed=9 blocked=8 regression=17 unchanged.
- Stage 9.3-B readiness audit completion does NOT authorize Stage
  9.3-B real DeepSeek implementation.

### Stage 9.3-B-0 Runtime Approval Gate / External AI Policy Contract

Status: completed 2026-06-15 (commit on `app-mvp`).

- New `ExternalAIRuntimePolicy` Pydantic schema in
  `src/app_backend/schemas/ai_external.py` (`extra="forbid"`), with a
  `default_external_ai_runtime_policy()` factory that returns a fully
  fail-closed default.
- New `src/app_backend/services/ai_external_runtime_policy.py` exposing
  `guard_external_ai_runtime_policy` and
  `assert_external_ai_runtime_policy_allowed`.
- Pass condition: every approval gate True AND every dangerous permission
  False; otherwise fail-closed with a deterministic findings list.
- Approval gates: `external_ai_enabled`, `provider_network_enabled`,
  `user_controlled_switch_enabled`, `single_request_user_approved`,
  `context_preview_confirmed`, `request_built_from_manifest`,
  `request_guard_passed`, `response_guard_required`,
  `stage9_validator_required`, `human_review_required`.
- Dangerous permissions: `save_raw_prompt`, `save_raw_response`,
  `persist_chat_by_default`, `allow_search`, `allow_tavily`,
  `allow_background_call`, `allow_app_start_call`, `allow_page_load_call`,
  `allow_holdings_line_items`, `allow_account_values`,
  `allow_position_weights`, `allow_transaction_history`.
- Stage 9.2 preview endpoints, `ai_preview_service`, `ai_memo_renderer`,
  and `ai_context_service` do NOT import the runtime policy module, the
  request builder, or the DeepSeek adapter.
- No new HTTP routes; no network client imported; no env / yaml / file read
  in the runtime policy module.
- 106 tests in `tests/test_ai_external_runtime_policy.py` lock the
  contract: default fail-closed; happy-path pass; per-gate / per-permission
  parametrized failures; extra-fields rejection; source-surface scan;
  Stage 9.2 isolation; forbidden-routes absence.
- Documented in `docs/stage9_deepseek_adapter_design.md` (Stage 9.3-B-0
  section and the updated 10-step seam order).
- Stage 9.3-B-0 completion does NOT authorize Stage 9.3-B real DeepSeek;
  explicit approval still required.

### Stage 9.3-B Real DeepSeek Adapter

Status: not implemented; requires explicit approval before work begins.
Stage 9.3-A skeleton, Stage 9.3-A closeout hardening, Stage 9.3-B
readiness audit, and Stage 9.3-B-0 runtime approval gate (all 2026-06-15)
do NOT authorize Stage 9.3-B.

- Start only after Stage 9.2 closeout, Stage 9.3-A skeleton, and explicit
  user approval.
- Keep adapter disabled by default.
- Must not start automatically on app launch or page load.
- Require an explicit UI or settings switch.
- Must show AI Context Manifest preview before any external send.
- Must run the Stage 9.2 validator after every response.
- Must not save raw prompts or raw responses by default.
- Must reuse `ExternalAIRequest` / `ExternalAIResponse` / `guard_*`
  contracts from Stage 9.3-A unchanged; may only extend in backwards-
  compatible ways.
- Show context preview before send.
- Show cost and model metadata.
- Send only approved AI Context Manifest material.
- Run validator after response.
- Do not save ordinary chat by default.
- Do not persist raw prompts.
- Do not include holdings line items.
- Do not include account values, position weights, or transaction history.

## Stage 9.4 Tavily Explicit-Search Beta

- Keep disabled by default.
- Send only the user's search query.
- Do not send account context.
- Do not send portfolio context.
- Do not send holdings or transaction data.
- Require cited results.
- Treat search failure as missing context.
- Do not invent facts after search failure.
- Do not keep a long-term search cache by default.

## Stage 9.5 Tauri / Desktop Shell

- Start only after backend, frontend, and AI surfaces stabilize.
- Do not add hidden background calls.
- Do not add automatic provider refresh.
- Do not add account editing unless a later phase explicitly permits it.
- Preserve local-first, privacy-first, fail-closed behavior.

## Dependency Gates

- M7/M8 are not blockers for Stage 9 preparation.
- M7/M8 should be considered before complex Stage 9 implementation.
- M12 AI Context Manifest Contract Hardening should remain active during all
  Stage 9 work.
- Stage R Course Paper Research Recovery remains optional docs/research work and
  must not enter production model logic.

## Global Stage 9 Boundaries

- Stage 9 is an application surface over AI Context Manifest.
- Stage 9 is not a new financial model.
- Stage 9 is not a new data source.
- Stage 9 must not change D10-D19 or Stage 8 model semantics.
- Stage 9 must not broaden AI context eligibility.
- Stage 9 must not bypass existing AI context gates.
- Stage 9 must not output action directives, allocation advice, return
  estimates, event odds, or position-level recommendations.
