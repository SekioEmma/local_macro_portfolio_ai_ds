# AI Memo Context Contract

## Role

This contract defines future Stage 9 memo and report output types. All output
types consume AI Context Manifest only. They are deterministic or reviewed
research surfaces unless a later phase explicitly enables an external model
behind a user-controlled switch.

All output types must preserve privacy policies, search policies, persistence
policies, and interpretation boundaries. They must not convert excluded facts or
model outputs into support.

## Shared Forbidden Behavior

Memo and report surfaces must not include:

- Action directives.
- Target allocation.
- Return estimates.
- Event odds.
- Position-level output.
- Holdings line items.
- Raw prompts.
- Raw provider payloads.
- Uncited search facts.
- Automatic saving by default.

## `daily_review_memo`

- Purpose: provide a compact daily research review over eligible manifest
  context.
- Allowed context: `included_facts`, `included_model_outputs`,
  `excluded_facts`, `excluded_model_outputs`, `risk_boundaries`,
  `privacy_policy`, and manifest stats.
- Required sections: `as_of_context`, `evidence_summary`,
  `model_output_summary`, `primary_pressure_channels`,
  `missing_or_excluded_constraints`, `interpretation_boundaries`,
  `human_review_required`.
- Forbidden sections: trade ideas, target allocations, return outlook,
  probability outlook, position-level diagnosis, raw prompt appendix.
- Human review requirement: required before relying on or sharing the memo.
- Persistence policy: not saved automatically.
- Validator requirement: reject forbidden outputs, privacy leakage, missing
  boundaries, and uncited search facts.

## `risk_review_memo`

- Purpose: summarize macro risk context and current pressure channels.
- Allowed context: eligible D10/D11/D14/D15/D16/D17/D18/D19 and Stage 8 compact
  outputs through the manifest.
- Required sections: `current_macro_state`, `financial_stress_context`,
  `pullback_vs_systemic_review`, `liquidity_funding_context`,
  `scenario_stress_notes`, `missing_constraints`, `boundary_notice`,
  `human_review_required`.
- Forbidden sections: crisis probability, recession probability, market
  direction probability, expected return, allocation change.
- Human review requirement: required.
- Persistence policy: not saved automatically.
- Validator requirement: reject probability, action, return, and strategy
  performance language.

## `scenario_review_memo`

- Purpose: explain a selected deterministic scenario using current evidence
  transmission context.
- Allowed context: eligible D16 compact outputs, supporting included facts, and
  relevant excluded constraints.
- Required sections: `selected_scenario`, `affected_evidence_groups`,
  `transmission_channels`, `uncertainty_conditions`, `missing_inputs`,
  `not_a_forecast_notice`, `human_review_required`.
- Forbidden sections: scenario odds, asset-direction certainty, return impact,
  allocation response, hedge instruction.
- Human review requirement: required.
- Persistence policy: not saved automatically.
- Validator requirement: reject forecast, odds, return, action, and
  position-level wording.

## `portfolio_overlay_review`

- Purpose: summarize sanitized portfolio exposure overlay context without
  exposing private holdings.
- Allowed context: eligible Stage 8 compact overlay outputs and related
  manifest risk boundaries.
- Required sections: `sanitized_portfolio_context_policy`,
  `exposure_channel_summary`, `macro_channel_mapping`,
  `private_inputs_excluded`, `not_action_directive_notice`,
  `human_review_required`.
- Forbidden sections: holdings table, account value, position weights, target
  allocation, rebalance plan, position-level recommendation.
- Human review requirement: required.
- Persistence policy: not saved automatically.
- Validator requirement: reject holdings leakage, account values, weights,
  target allocation, and action directives.

## `macro_risk_report`

- Purpose: create a fuller research report over eligible macro evidence, model
  outputs, and explicit constraints.
- Allowed context: all eligible AI Context Manifest sections and appendix-level
  manifest stats.
- Required sections: `executive_summary`, `evidence_table_snapshot_summary`,
  `D10-D19_model_summary`, `Stage8_overlay_summary`,
  `missing_data_and_research_needed`, `boundary_and_privacy_notes`,
  `appendix_manifest_stats`.
- Forbidden sections: trading plan, target portfolio, expected return,
  probability forecast, raw prompt, raw provider appendix.
- Human review requirement: required before export or sharing.
- Persistence policy: not saved automatically; any future save action must be
  explicit and validator-gated.
- Validator requirement: full boundary, privacy, citation, and forbidden-output
  validation.

## `evidence_audit_report`

- Purpose: summarize manifest coverage, exclusions, source/freshness
  constraints, and audit readiness.
- Allowed context: manifest stats, included/excluded facts, included/excluded
  model outputs, source badges, freshness metadata, blocked reasons, and risk
  boundaries.
- Required sections: `manifest_coverage`, `included_context_summary`,
  `excluded_context_summary`, `source_and_freshness_notes`,
  `privacy_policy_summary`, `validator_findings`,
  `human_review_required`.
- Forbidden sections: investment conclusion, action list, model performance
  claims, probability claims, raw private data appendix.
- Human review requirement: required.
- Persistence policy: not saved automatically.
- Validator requirement: reject privacy leakage, unsupported facts, and
  forbidden financial-output language.
