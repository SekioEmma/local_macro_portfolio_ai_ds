# S2 Scenario Stress Matrix Explanation Contract / Golden Integration

## Scope

S2 locks Scenario Stress Matrix (legacy: D16) explanation metadata contracts,
forbidden output language, D13/D17/D18/D19 context boundaries, and integration
with golden output, AI Context Manifest, and AI memo validation.

S2 is L3 boundary-adjacent contract hardening implemented as tests + docs only.
It does not change production code, financial model semantics, support/severity/
uncertainty calculation, frontend, endpoints, or external AI.

## What S2 Tests

`tests/test_s2_scenario_stress_contract.py` — 38 tests across 11 categories:

### 4.1 Public Output Contract (6 tests)

- Exact metric_key set matches `D16_PUBLIC_OUTPUT_KEYS`
- `MODULE_KEY` = `scenario_stress`, `MODEL_KEY` = `scenario_stress_v0`
- Source badge is `derived` for all rows
- Scenario count is 7 with exact scenario name set
- Model registry registration matches public output keys

### 4.2 Scenario Explanation Metadata Shape (3 tests)

- All S1 metadata fields present with correct types on every scenario
- Summary top-level shape includes all expected keys
- Refinement boundary text contains S1 disclaimers

### 4.3 Forbidden Output Language (4 tests)

- No forbidden terms in serialized rows or summary
- Boundary text contains required disclaimers
- No forbidden metric keys in output

### 4.4 D13 Reliability/OAS Coverage Context (4 tests)

- D13 reliability does not change severity or support
- D13 reliability adds uncertainty drivers and context
- OAS below-gate surfaces coverage context, source gate constraints, and
  current-level-only missing constraints
- D13 percentile rows do not enter supporting evidence

### 4.5 D17/D18 Missing/Gap Context (3 tests)

- Valuation/earnings/breadth gaps visible in scenario metadata
- Growth macro gaps visible when relevant
- Proxy-limited status raises uncertainty

### 4.6 D19 Historical Reference Context (3 tests)

- D19 replay is reference-only with correct reference_note
- Limited replay shows limited note
- D19 does not change severity or support

### 4.7 Portfolio Overlay Boundary (3 tests)

- Portfolio overlay does not change severity or support
- Portfolio overlay alone does not create support
- No portfolio action language in output

### 4.8 Golden Contract Integration (3 tests)

- Golden evidence table contains exact D16 public keys
- Golden D16 boundary text verified
- Golden scenarios carry all S1 metadata fields

### 4.9 AI Context Manifest Integration (3 tests)

- D16 enters manifest as model_output, not fact
- Manifest row carries S1 scenario metadata
- No forbidden terms in manifest D16 output

### 4.10 AI Memo Contract Integration (3 tests)

- Memo with D16 context passes validation
- Memo with forbidden D16 content is blocked
- Privacy flags remain closed

### 4.11 D15/D16 Compliance Audit Reinforcement (3 tests)

- D16 audit section present and clean
- Production file contains no forbidden surfaces
- Model registry boundary and forbidden policy verified

## What Does Not Change

- No scenario probabilities, forecasts, expected returns, or trading outputs
- No changes to support/severity/uncertainty calculation
- No production code modifications
- No frontend, endpoint, or external AI changes
- No D13 gate relaxation or BAA10Y substitution
- No new providers, live fetches, or live writes
- No reopening of P-M4-D Manifest cache implementation

## Decision

S2 is completed as tests + docs only. All 38 new contract tests pass. Full
test suite (1420 tests) passes with zero regressions.

Next recommended task: S3 AI memo boundary template update, only after S2.
