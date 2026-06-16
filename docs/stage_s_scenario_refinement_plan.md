# Stage S Scenario Stress / Explanation Refinement Plan

## Scope

Stage S refines scenario-stress explanation quality after Stage DF.

It does not add:

- forecasting
- scenario probability
- expected return
- price path
- trading advice
- allocation directives
- endpoints
- frontend UI
- external AI
- Tavily/search
- live data writes

## Why Stage S Now

Stage DF completed:

- D19 replay integration
- D15/D16 compliance audit
- D17/D18 source-gate audit
- D13 reliability/divergence metadata
- D13 credit OAS coverage/provider-rebuild metadata

The safe next modeling step is to let D16 consume existing explanatory metadata
without changing trigger semantics.

## S1 Scenario Stress Matrix Refinement v1 (legacy: D16)

Status: completed.

Goal:

Use existing Historical Risk Normalization (legacy: D13)
reliability/divergence/OAS coverage metadata, Growth & Inflation Context /
Valuation & Equity Structure Context (legacy: D17/D18) missing/source-gate
notes, and Historical Validation Replay (legacy: D19) metadata to improve
scenario severity, uncertainty, and missing-constraint explanations.

Allowed:

- Better scenario explanation text.
- Better uncertainty drivers.
- More explicit missing/proxy/research_needed constraints.
- Component contribution metadata.
- Tests ensuring D16 remains non-predictive.

Not allowed:

- `scenario_probability`
- `forecast_path`
- `expected_return`
- `target_price`
- `portfolio_action`
- buy/sell/hedge/rebalance
- new provider
- frontend UI
- external AI
- live fetch/write
- BAA10Y substitution for HY/IG OAS
- relaxing D13 3Y gate

## S1 Design Principles

- D13 reliability/divergence/OAS coverage may affect explanation and
  uncertainty, not hard triggers.
- D17/D18 missing gaps should increase uncertainty or remain visible, not be
  filled.
- D19 replay may provide historical context notes, not prediction accuracy.
- Portfolio overlay remains downstream-only and cannot change D16 severity.
- BAA10Y can remain a future reference-only documentation topic, not S1 input
  unless explicitly approved.

## S1 Validation Expectations

- Targeted D16 tests.
- D13 metadata integration tests if D16 reads new D13 fields.
- Golden contract tests.
- AI context manifest tests.
- AI memo contract tests.
- Full pytest if production code changes.
- Benchmark/audit/historical validation if D16 production code changes.

## S1 Completion Notes

S1 is completed in `src/data_quality/scenario_stress.py` with focused contract
coverage in `tests/test_s1_d16_scenario_refinement.py` and the implementation
note in `docs/s1_d16_scenario_refinement.md` (Scenario Stress Matrix,
legacy: D16).

The D16 public output keys remain unchanged. New explanation details are kept
inside existing scenario component metadata:

- `scenario_uncertainty_drivers`
- `scenario_missing_constraints`
- `scenario_proxy_constraints`
- `scenario_source_gate_constraints`
- `scenario_d13_reliability_context`
- `scenario_d13_divergence_context`
- `scenario_d13_oas_coverage_context`
- `scenario_d17_d18_gap_context`
- `scenario_d19_reference_context`
- `scenario_refinement_boundary`

S1 does not add providers, endpoints, frontend UI, external AI, search,
persistence, live fetches, live writes, scenario probabilities, forecast paths,
return estimates, price targets, portfolio actions, D13 gate relaxation,
BAA10Y substitution, or new hard triggers.

S1 is completed. Further S-line tasks (S2, S3) are deferred until after
HF-1, HF-2, and P-M1 unless explicitly requested. See
`docs/short_term_development_plan.md` for the current immediate route and
`docs/INDEX.md` for the namespace map.

Next recommended task: P-M1 dashboard_model_pipeline row conversion
accumulator, covering the model chain from Historical Risk Normalization
(legacy: D13) through Scenario Stress Matrix (legacy: D16). S2 Scenario Stress
Matrix explanation tests / golden contract integration or S3 AI memo boundary
template update may follow only after explicit decision.
