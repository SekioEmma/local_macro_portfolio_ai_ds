# P-M1 Pipeline Row Conversion Accumulator

## Scope

Behavior-preserving dashboard model pipeline optimization. No model semantics,
public output keys, module keys, endpoints, or external AI changes.

## Problem

`build_dashboard_model_rows` repeatedly converted accumulated
`DashboardEvidenceRow` groups to dicts for each downstream model. The same
`base_rows` were converted 8 times (once per downstream model call), and each
intermediate model group was re-converted for every subsequent model in the
chain. With 10 model groups and ~120 base rows, this produced thousands of
redundant `model_dump()` calls.

## Change

Each row group is now converted to dicts exactly once via `_model_to_dict`,
then appended to a shared `model_input_dicts` accumulator list. Downstream
models receive the pre-converted dict list directly instead of re-converting
the same `DashboardEvidenceRow` objects on every call.

Key implementation details:

- `base_dict_rows = _to_dicts(base_rows)` — converted once at pipeline start
- Each model group's rows are converted immediately after creation and
  extended into `model_input_dicts`
- `pre_validation_input_dicts` snapshot taken before Historical Validation
  Replay for Scenario Stress Matrix and Portfolio Exposure Overlay input
  construction

## Input Order Preservation

### Scenario Stress Matrix (legacy: D16)

Input order: base + Historical Risk Normalization + Liquidity & Funding Stress
+ Financial Stress Composite + Pullback vs Systemic Risk Review + Growth &
Inflation Context + Valuation & Equity Structure Context + Macro Regime Review
+ Historical Validation Replay.

Constructed as `pre_validation_input_dicts + historical_validation_dict_rows`.

### Portfolio Exposure Overlay (legacy: Stage 8)

Input order: base + Historical Risk Normalization + Liquidity & Funding Stress
+ Financial Stress Composite + Pullback vs Systemic Risk Review + Growth &
Inflation Context + Valuation & Equity Structure Context + Macro Regime Review
+ Scenario Stress Matrix + Historical Validation Replay.

Constructed as `pre_validation_input_dicts + scenario_stress_dict_rows +
historical_validation_dict_rows`.

### Final row assembly order (unchanged)

Financial Stress Composite + Pullback vs Systemic Risk Review + Growth &
Inflation Context + Valuation & Equity Structure Context + Macro Regime Review
+ Scenario Stress Matrix + Historical Validation Replay + Portfolio Exposure
Overlay + Historical Risk Normalization + Liquidity & Funding Stress.

## What Does Not Change

- no model semantics
- no public output keys
- no module/model/metric key rename
- no endpoint/frontend/external AI
- no live fetch/write
- no Stage 9 reopening
- no D13 formula/gate change
- no Scenario Stress Matrix behavior change
- no Portfolio Exposure Overlay privacy boundary change

## Validation

- 18 pipeline tests pass (14 existing + 4 new P-M1 tests)
- 93 contract tests pass (golden output, AI context manifest, AI memo, Stage 9.2)
- 1343 full test suite pass
- Benchmark: 219 evidence rows, 119 included facts, 63 included model outputs
- Validator boundaries: allowed=9 blocked=8 regression=17
- Historical validation: 0 boundary violations
- `git diff --check` clean
