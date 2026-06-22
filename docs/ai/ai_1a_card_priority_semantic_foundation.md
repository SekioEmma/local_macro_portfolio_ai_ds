# AI-1a - Card / Priority / Semantic Foundation (Backend Primitives)

## Scope

AI-1a is the first half of AI-1 (Context-Manifest Driven Local Research
Preview). It introduces three backend primitives required for higher-quality
local AI preview output, without touching the existing memo renderer
templates, schemas, API surface, or frontend pages. CODEX (or a follow-up
task) will wire these primitives into the preview service and update the
contract tests as AI-1b.

## What is implemented

### 1. `src/app_backend/services/ai_context_priority.py`

A deterministic 1-4 priority ranking layer for AI Context Manifest rows.
Mirrors the user-specified financial reasoning order:

- **P1 core macro state** -
  `macro_regime_review`, `financial_stress_composite`,
  `pullback_systemic_risk_checklist`, `credit_stress`,
  `liquidity_funding_stress`, `rate_pressure`, `real_yield_pressure`.
  Intra-priority order: regime -> stress composite -> credit -> funding ->
  rates -> real yield -> pullback.
- **P2 inflation / growth / equity** -
  `inflation_energy_pressure`, `growth_inflation_macro_pack`, `equity_trend`,
  `market_stress_derived`, `historical_risk_percentile`.
- **P3 proxy / explanation / portfolio** -
  `breadth_concentration_proxy`, `valuation_equity_structure`,
  `scenario_stress`, `historical_validation`, `portfolio_exposure_overlay`,
  `portfolio_deviation`, `data_quality_diagnostics`.
- **P4 excluded constraint** -
  any row passed in with `excluded=True` regardless of module.

Public API:

- `assign_context_priority(row, *, excluded=False) -> int`
- `priority_label(priority, *, language='en'|'zh') -> str`
- `sort_rows_by_priority(rows, *, excluded=False) -> list`
- `group_rows_by_priority(rows, *, excluded=False) -> dict[int, list]`

Unknown modules fall back to P3 (conservative: visible but not promoted to
core macro state).

### 2. `src/app_backend/services/ai_evidence_cards.py`

Renders three structured card types from manifest rows. Cards are bounded
explanatory units; they never expose holdings line items, raw provider
payloads, raw prompt text, credentials, or any other privacy-marked content.

Card types:

- `EvidenceCard` (factual row, P1-P3 by module)
- `ModelOutputCard` (D10-D19 / Stage 8, with support / severity / uncertainty
  / evidence_quality / conflict bands pulled from
  `component_contributions`)
- `ExcludedConstraintCard` (excluded / missing / stale row, P4)

Each card carries both English keys and Chinese display strings
(`module_display_zh`, `status_display_zh`, `source_badge_display_zh`,
`freshness_display_zh`, `trigger_eligibility_display_zh`,
`priority_label_zh`) plus a fixed `boundary_notice_zh`. Cards expose an
`as_text_block()` method that produces a deterministic prompt-ready block.

Public API:

- `render_evidence_card(row) -> EvidenceCard`
- `render_model_output_card(row) -> ModelOutputCard`
- `render_excluded_constraint_card(row) -> ExcludedConstraintCard`
- `render_manifest_cards(manifest) -> dict[str, list]` (all three buckets,
  sorted by priority)
- `cards_as_text_blocks(cards) -> str` (join for prompt context)

Boundary notices are baked into every card:

- Evidence card: not a prediction, not event-odds, not return-estimation,
  not a position directive.
- Model output card: financial stress score is pressure temperature (not
  probability), macro regime review is current evidence review (not future
  direction), scenario stress is hypothetical transmission matrix (not
  forecast).
- Excluded constraint card: explicitly states the row cannot be promoted to
  fact, cannot be used as trigger evidence.

### 3. `src/app_backend/services/ai_semantic_validator.py`

A financial semantic rules engine. Goes beyond the existing term-blacklist
validators in `ai_memo_renderer.py` and `ai_preview_service.py`. Those check
whether forbidden words or privacy tokens appear in output. The semantic
validator checks whether financial reasoning logic is properly bounded.

Rule catalog (`SEMANTIC_RULES`):

1. `systemic_risk_requires_credit_funding_transmission` -
   if output references systemic risk, must also reference credit
   (HY/IG OAS, credit spread), funding/liquidity (SOFR, RRP, CP), and
   transmission/channel evidence.
2. `credit_warning_cannot_rely_only_on_vix_or_etf_proxy` -
   credit warning anchored on VIX or HYG/LQD alone fails; HY OAS / IG OAS /
   official credit spread required.
3. `valuation_pressure_must_acknowledge_missing_or_proxy` -
   valuation pressure claim must mention `missing`, `research_needed`,
   `proxy`, `not_available`, `limited_evidence`, or `insufficient` for the
   relevant inputs.
4. `scenario_requires_not_a_forecast_notice` -
   any reference to scenario stress / scenario matrix / scenario
   transmission must include a "not a forecast / not event-odds / not
   action directive / not return-estimation" notice (English or Chinese).
5. `historical_validation_requires_not_a_backtest_notice` -
   any reference to historical validation must include
   "event-window replay / not a backtest / not prediction accuracy /
   reference-only" notice (English or Chinese).
6. `portfolio_requires_local_sanitized_no_allocation` -
   any portfolio reference must include sanitized / compact_summary_only /
   local-only / not action directive language (English or Chinese).
7. `financial_stress_score_must_clarify_pressure_temperature` -
   any reference to a financial stress score must clarify the score is
   pressure temperature, not probability or forecast.

All rules are bilingual: anchors and required-context phrases each include
English and Chinese variants. The validator does not call external models,
does not modify the input payload, and does not produce any allocation /
probability / forecast output.

Public API:

- `validate_financial_semantics(payload, *, extra_text=None, rules=None)
  -> SemanticValidatorResult`
- `explain_findings(result, *, language='zh'|'en') -> list[str]`

`SemanticValidatorResult` exposes `.passed` and `.findings`, each finding
carrying `rule`, `description_zh`, `matched_anchor`, and `missing_groups`.

## What is NOT implemented (handoff to CODEX as AI-1b)

The primitives above are standalone and tested. They are not yet wired into
the preview service or surfaced on the frontend. The following should be
done as a separate task to avoid mixing primitive introduction with
contract-test rewrites in one commit:

1. **Schema extensions** (additive, non-breaking):

   - Add optional `evidence_cards`, `model_output_cards`,
     `excluded_constraint_cards` lists to `AIPreviewChatResponse` and to
     `AIMemoPreview` (or add a separate `AIPreviewCardsResponse`).
   - Add optional `semantic_validator_result` field alongside the existing
     `validator_result` so semantic findings are surfaced without breaking
     the existing term-blacklist validator contract.
   - Add optional `priority_buckets` field to expose the ranked context
     outline.

2. **Service wiring** in `ai_preview_service.py` and `ai_memo_renderer.py`:

   - Replace ad-hoc `_summarize_rows()` / `_summarize_models()` with
     priority-sorted rendering using `sort_rows_by_priority()`.
   - Populate the new card lists from `render_manifest_cards()`.
   - Call `validate_financial_semantics()` alongside the existing validator
     and merge findings into a combined result. Semantic findings should
     not auto-block existing memos that already pass the term validator;
     during AI-1b, semantic findings should be reported but not yet
     fail-closed. Promote to fail-closed in AI-1c once Chinese templates
     are clean.

3. **Chinese-ify memo section content** (`_section_content` in
   `ai_memo_renderer.py`):

   - Rewrite the English summary strings ("Evidence rows", "Excluded
     context constraints", "D10 financial stress", etc.) into the Chinese
     7-段 financial-research structure (当前结论 / 支撑证据 / 反向证据 /
     数据约束 / 宏观解释 / 组合通道 / 边界声明).
   - Update `tests/ai/test_ai_memo_renderer.py` and
     `tests/ai/test_ai_memo_contract.py` (~38 assertions on English
     phrases) to match new Chinese output. Keep validator and forbidden-
     term assertions intact.
   - Preserve the `MODEL_MODULE_LABELS` / Scenario Stress Matrix label
     contract that S2/S3 tests depend on.

4. **Frontend integration** (`app_frontend`):

   - Extend `types.ts` to declare the new optional card / semantic-result
     fields.
   - Add a new `Evidence Cards` panel on `AIContextPreviewPage.tsx` that
     renders each `as_text_block()`-equivalent in Chinese, grouped by
     priority band.
   - Add a `Semantic Validator` panel showing `findings[].rule`,
     `matched_anchor`, `missing_groups`, `description_zh`.

5. **Prompt Preview page** (AI-3 preparatory):

   - New frontend page that renders `build_external_ai_request_from_manifest`
     output as system prompt + task prompt + ranked context cards +
     semantic validator pre-check. Still no external call; dry-run only.

## Tests

New: 54 unit tests covering the three modules.

- `tests/ai/test_ai_context_priority.py` - 25 tests (P1-P4 module mapping,
  intra-P1 reading order, fallback behavior, sort/group helpers, bilingual
  labels).
- `tests/ai/test_ai_evidence_cards.py` - 11 tests (card identity,
  Chinese glosses, band extraction, missing-input counting, excluded
  reason mapping, manifest-level sort).
- `tests/ai/test_ai_semantic_validator.py` - 18 tests (each rule has a
  fail case + pass case, bilingual anchor / required-context handling,
  explain_findings output, rule catalog completeness).

Existing AI test suite: 857 tests pass (no regression).
Full pytest suite: not yet rerun in this commit; CODEX should rerun
`python -m pytest -q` before AI-1b.

## Boundary compliance

This task adds three new local-only service modules and unit tests. It:

- does not add or change any HTTP route;
- does not add or change frontend code;
- does not commit generated data;
- does not change any AI Context Manifest field semantics;
- does not promote any proxy / research_needed / not_available row to
  official fact status;
- does not alias PPIACO to final-demand PPI;
- does not alias BAA10Y to HY/IG OAS;
- does not call external models, Tavily, or any search service;
- does not consume holdings line items, account values, position weights,
  raw provider payloads, raw prompt text, credentials, or local file
  paths;
- does not produce any allocation, probability, return, forecast, or
  trading output.

External AI line, Chat UI, Tavily/search, Tauri, full-account DeepSeek
context, and prediction/probability/trading outputs remain frozen.

## Next

Hand off to CODEX as AI-1b. Recommended sequencing:

1. AI-1b - schema extension + service wiring + Chinese template rewrite +
   contract test updates.
2. AI-1c - frontend Evidence Cards panel + Semantic Validator panel +
   Prompt Preview page.
3. AI-2 - Template-based Research Assistant (6 answer modes consuming the
   wired primitives).
4. AI-3 - External AI dry run (no send).
5. AI-4 - Explicit-approval external model (gated by existing
   `ai_external_runtime_policy` chain).
