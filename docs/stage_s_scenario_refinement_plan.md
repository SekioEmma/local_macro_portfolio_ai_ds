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

## S1 D16 Scenario Stress Refinement v1

Goal:

Use existing D13 reliability/divergence/OAS coverage metadata, D17/D18
missing/source-gate notes, and D19 historical replay metadata to improve
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
