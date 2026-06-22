# DF-2 D15/D16 Compliance Audit

## Scope

DF-2 audits the existing D15 Macro Regime Review and D16 Scenario Stress Test
against the current project boundaries. It does not add a new model, rewrite
D15, rewrite D16, add endpoints, add frontend UI, reopen external AI, add
Tavily/search, add persistence, run live fetches, or add prediction,
probability, return, allocation, or trading outputs.

## D15 Audit

### Current Outputs

D15 public outputs are limited to:

- `macro_regime_label`
- `support_band`
- `evidence_quality_band`
- `conflict_band`
- `primary_pressure_ranking`
- `supporting_evidence`
- `conflicting_evidence`
- `missing_inputs`
- `blocked_inputs`
- `interpretation_boundary`
- `model_version`
- `formula_version`
- `as_of_date`

### Compliant Boundaries

- D15 is implemented as current evidence review, not a classifier.
- D15 does not expose a public numeric `macro_regime_score`.
- D15 public keys do not expose internal support or group scores.
- D15 uses support/evidence-quality/conflict bands and ranked evidence.
- Missing and blocked inputs remain visible.
- Valuation, earnings, and true-breadth gaps remain visible constraints.
- Missing, stale, research-needed, insufficient-history, and ineligible rows do
  not support labels.
- VIX alone cannot trigger `credit_stress`.
- Equity drawdown alone cannot trigger a stress regime.
- Percentile-only and proxy-only evidence remain auxiliary.
- Portfolio overlay rows do not decide macro regime.

### Risks Found

No production-code compliance failure was found.

### Required Fixes, If Any

None. DF-2 adds tests and documentation only.

### No-go Items

D15 must not add public numeric regime scores, probabilities, forecasts,
event-odds language, trading instructions, allocation directives, or return
estimates.

## D16 Audit

### Current Outputs

D16 public outputs are limited to:

- `scenario_stress_status`
- `scenario_stress_scenario_count`
- `scenario_stress_scenarios`
- `scenario_stress_primary_scenario`
- `scenario_stress_affected_groups`
- `scenario_stress_transmission_channels`
- `scenario_stress_severity_band`
- `scenario_stress_uncertainty_band`
- `scenario_stress_supporting_evidence`
- `scenario_stress_missing_inputs`
- `scenario_stress_interpretation_boundary`
- `scenario_stress_model_version`
- `scenario_stress_formula_version`
- `scenario_stress_as_of_date`

### Compliant Boundaries

- D16 is a hypothetical scenario matrix and current evidence transmission
  review, not a forecast.
- D16 does not estimate scenario probability.
- D16 does not estimate market direction.
- D16 does not estimate expected or future returns.
- D16 does not produce target prices, stop losses, price paths, or portfolio
  actions.
- D16 preserves uncertainty bands and missing evidence.
- D16 reports affected evidence groups and transmission channels.
- Proxy-only evidence cannot produce strong support or high severity.

### Risks Found

No production-code compliance failure was found.

### Required Fixes, If Any

None. DF-2 adds tests and documentation only.

### No-go Items

D16 must not add scenario probabilities, return estimates, asset-direction
calls, trading strategy outputs, allocation directives, or portfolio actions.

## AI Context / D19 Interaction

### Compliant

- D15 and D16 enter AI Context Manifest only as `model_output` rows, not as
  factual rows.
- D15 and D16 boundary text is preserved in AI context.
- D19 replay rows do not convert D15 or D16 into backtest, probability,
  forecast, or performance metrics.
- AI memo contracts continue to block investment-advice expansion and
  forbidden output terms.

### Documentation-only Risk

Legacy APP roadmap language remains in `docs/ROADMAP_CURRENT.md`, but DF-0
marks it as legacy and superseded. It is not a current execution source.

### Test Coverage Gap

Before DF-2, several D15/D16 boundaries were covered by separate D15, D16,
golden, and AI context tests, but there was no single DF-2 compliance audit
test file. DF-2 adds `tests/test_d15_d16_compliance_audit.py` to make the
boundary package explicit.

### Scoped Code Fix Needed

None.

### Future Backlog

DF-3 should audit D17/D18 data gaps and source gates. Future D16 refinements
should happen only after compliance audit work and must preserve the
scenario-matrix boundary.

## Final Decision

DF-2 audit passed without production code changes.

## Next Step

DF-3 D17/D18 data gap and source-gate review.
