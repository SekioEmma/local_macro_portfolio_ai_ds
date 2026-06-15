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

### Stage 9.3-B Real DeepSeek Adapter

Status: not implemented; requires explicit approval before work begins.
Stage 9.3-A skeleton (2026-06-15) does NOT authorize Stage 9.3-B.

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
