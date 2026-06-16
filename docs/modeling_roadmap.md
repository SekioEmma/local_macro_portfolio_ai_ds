# Modeling Roadmap

## Scope

This document is the modeling-history narrative and module-boundary record.
It does not authorize live fetches, provider writes, account actions, or
portfolio instructions.

This document is not the source of truth for the immediate next task. The
immediate route lives in `docs/short_term_development_plan.md`. For a
one-page orientation, see `docs/INDEX.md`. For task-level rules, see
`docs/task_governance_policy.md`.

## D15 Macro Regime Review v0

D15 is implemented as Macro Regime Review, not as a classifier, probability
model, forecast model, or trading model.

Approved public D15 labels:

- `low_stress_liquidity_support`
- `rates_pressure`
- `inflation_energy_pressure`
- `credit_stress`
- `liquidity_funding_pressure`
- `growth_slowdown_watch`
- `stagflation_pressure`
- `mixed_or_transition`
- `insufficient_evidence`

Public D15 output policy:

- No public `macro_regime_score`.
- No public internal support or group scores.
- Use `support_band`, `evidence_quality_band`, and `conflict_band`.
- Keep `primary_pressure_ranking`, supporting evidence, conflicting evidence,
  missing inputs, and blocked inputs visible.
- Treat valuation, earnings, and true-breadth gaps as constraints, not support.

Hard gates:

- VIX alone cannot trigger credit or systemic stress.
- Equity drawdown alone cannot trigger stress.
- D14 alone cannot trigger liquidity or systemic regime.
- Percentile-only evidence cannot determine regime.
- Proxy-only evidence cannot determine pressure or high label.
- Blocked, insufficient-history, stale, missing, or research-needed rows cannot support a label.
- Oil or breakeven alone cannot trigger inflation/energy pressure.
- DGS30 alone cannot trigger high rates pressure.

## Stage 7 D19 Expanded Historical Validation v1

D19 expanded historical validation v1 is implemented as read-only historical
replay of the deterministic evidence pipeline over predefined event windows.

It is event-window consistency, local-history coverage review, and boundary
validation. It is not probability calibration, a prediction backtest, future
market forecasting, or a strategy-evaluation model.

Current D19 public outputs remain compact model-output rows: status, event
counts, available/limited/insufficient-history counts, over/under-escalation
flags, boundary/proxy/missing-data violation counts, privacy flags,
model/formula versions, validation boundary, and compact coverage summaries.

## D19 v0 Historical Validation Event Registry + Replay Skeleton

Status: completed.

The Stage R1 candidate event windows are now captured in a static, auditable
D19 v0 event registry. The registry records controlled event types, expected
pressure groups, ordinary-pullback markers, data-availability constraints,
external-reference notes, historical archetypes, and interpretation
boundaries.

The replay skeleton converts those registry entries into structured event rows
with `available`, `limited`, `insufficient`, or `reference_only` validation
status. It is local-only and does not read DB files, outputs, private data,
external model config, or live providers.

D19 v0 event windows are historical interpretation references, not
ground-truth labels. The skeleton does not add probability outputs, return
estimates, trading advice, production clustering, cluster probability,
cluster-to-action mapping, endpoints, frontend UI, external AI, or live
fetch/ingest behavior.

DF-1 D19 v1 historical evidence-row integration is completed.

## Stage DF - Data Foundation & Historical Evidence Integration

Status: concluded.

Stage DF was the modeling/data route after D19 v0 and DF-0 roadmap
arbitration. It is concluded after DF-4c.

Stage order:

1. DF-0 Roadmap arbitration and legacy cleanup: completed.
2. DF-1 D19 v1 historical evidence-row integration: completed.
3. DF-2 D15/D16 compliance audit: completed.
4. DF-3 D17/D18 data gap and source-gate review: completed.
5. DF-4 D13 reliability/divergence metadata: completed.
6. DF-4a Credit OAS history availability audit: completed.
7. DF-4c Credit OAS coverage/provider-rebuild metadata: completed.

DF-1 integrates existing historical validation summary information into D19
replay rows through compact component metadata. D19 remains historical pressure
recognition and boundary validation, not prediction, backtest, probability
calibration, return estimation, or trading strategy review.

DF-2 reviewed the existing D15 and D16 implementations for compliance with
current boundaries rather than inventing a parallel model. The audit passed
without production code changes.

DF-3 reviewed the existing D17 Growth/Inflation Macro Pack and D18
Valuation/Equity Structure for data coverage, source gates, proxy /
research_needed / insufficient_history handling, and AI Context Manifest
entry rules. The audit confirmed all D17/D18 hard gates remain enforced,
missing valuation/earnings/true-breadth gaps remain visible, proxy-only
inputs cannot strong-trigger labels, and research_needed/missing rows stay
excluded from AI factual context. DF-3 passed without production code
changes.

DF-4 added explanatory reliability and method-divergence metadata to D13
`historical_risk_percentile` rows. New fields include `reliability_band`,
`reliability_drivers`, `divergence_band`, `divergence_notes`,
`method_agreement`, `normalization_methods_available`, three pairwise
alignment labels, `source_quality_note`, and `history_window_note`. The
metadata is descriptive model-quality context. It does not change percentile
/ z-score / robust z-score values, 5Y/3Y lookback rules, band thresholds,
trigger eligibility, or AI context allowance. See
`docs/d13_reliability_divergence_metadata.md` for the full DF-4 design.

DF-4a audited current credit OAS history availability. HY/IG OAS local and
current provider history are approximately three years and were still below the
exact 3Y fallback gate at 1094 coverage days. `BAA10Y` remains a separate
long-history credit proxy/reference, not a substitute for HY/IG OAS.

DF-4c integrated that conclusion into D13 metadata. New fields include
`history_coverage_status`, `provider_rebuild_status`,
`normalization_availability`, `coverage_diagnostics`, `credit_reference_role`,
`substitution_policy`, and `long_history_reference_status`. DF-4c does not
change D13 formulas, 5Y/3Y gates, band thresholds, trigger eligibility, AI
context allowance, providers, D10/D11/D15/D19 trigger logic, endpoints,
frontend UI, external AI, search, persistence, live fetches, or live writes.

Optional DF-4d BAA10Y D19 proxy/reference documentation is deferred unless
explicitly requested later. It is not the default next task.

## Stage S - Scenario Stress / Explanation Refinement

Status: S1 completed. HF-1 Test Runtime Hotfix completed after S1.

Stage S is the next modeling phase after Stage DF. Its purpose is to refine
Scenario Stress Matrix (legacy: D16) explanation quality using existing evidence
and metadata, without changing trigger semantics or introducing prediction
behavior.

Stage S0 Post-DF Roadmap Reconciliation is completed. S1 Scenario Stress Matrix
Refinement v1 (legacy: D16) is completed. HF-1 Test Runtime Hotfix / DB-backed
Fixture Batching is completed.

S1 improves scenario explanation text, uncertainty drivers, missing/proxy/
research_needed constraints, and component contribution metadata. It does not
change Scenario Stress Matrix (legacy: D16) public output keys, support
triggers, or severity rules. It does not add scenario probabilities, forecasts,
expected returns, price paths, portfolio actions, buy/sell/hedge/rebalance
language, providers, endpoints, frontend UI, external AI, Tavily/search, live
fetches, live writes, BAA10Y substitution for HY/IG OAS, or Historical Risk
Normalization (legacy: D13) gate relaxation.

HF-1 optimized DB-backed Historical Risk Normalization (legacy: D13) test
fixtures and benchmark result reuse only. It did not change model semantics,
formulas/gates, Scenario Stress Matrix (legacy: D16) behavior, AI context
rules, providers, endpoints, frontend UI, external AI, Tavily/search, live
fetches, or live writes.

Next recommended task after HF-1: P-M1 dashboard_model_pipeline row conversion
accumulator, covering the model chain from Historical Risk Normalization
(legacy: D13) through Scenario Stress Matrix (legacy: D16).

External AI remains frozen. Stage S does not reopen DeepSeek Chat,
Tavily/search, frontend AI UI, persistence, full-account external context, or
automatic external calls.

## Stage 8 Portfolio Exposure Overlay v0

Status: completed.

Stage 8 Portfolio Exposure Overlay v0 is implemented as a downstream-only,
privacy-preserving explanatory layer. It uses sanitized compact portfolio
context and existing D10-D19 dashboard evidence/model outputs to map macro risk
channels such as equity beta, rates duration, credit spread,
liquidity/funding, inflation/energy, growth slowdown, valuation/earnings
breadth, equity concentration, cash buffer, and historical-validation context.

It does not read or expose holdings line items. It does not provide allocation
advice, action directives, return estimates, probability outputs, position-level
diagnosis, target mixes, or optimization results. Missing sanitized portfolio
context remains visible and is not interpreted as low or high exposure.

Stage 9 AI Chat / Memo / Report is not implemented and is not the current next
engineering task.

## Stage 8.5 Foundation Stabilization Sprint

Status: completed.

Stage 8.5 was the freeze/stability phase after Stage 8 and before any Stage 9
AI surface work. It verified the Stage 0-D19 foundation, refreshed validation
baselines, profiled shared pipeline context reuse, audited Stage 8 AI context
eligibility, confirmed privacy and forbidden-output boundaries, and recorded a
maintainability backlog.

Stage 8.5 did not add financial model behavior. It did not call DeepSeek or
Tavily, did not read holdings line items, did not add a dashboard feature, and
did not implement AI Chat / Memo / Report.

## Stage 9 AI Chat / Memo / Report

Status: frozen / later work only; not implemented.

Stage 9 is an application surface over the evidence/model context, not a new
financial model. It consumes D10-D19 and Stage 8 model outputs through AI
Context Manifest rather than raw dashboard payloads, holdings payloads, or
provider payloads.

Stage 9 must not broaden model eligibility or bypass existing AI context gates.
It must not change D10-D19 or Stage 8 model semantics. Stage 9 productization is
not current. Any user-facing AI feature requires separate explicit approval
before any real DeepSeek adapter, Tavily search, persistent chat, agent flow,
Tauri shell, or automatic report saving work.

## Stage 3 Modeling Infrastructure v0

Stage 3 is implemented as shared modeling infrastructure:

- `EvidenceIndex` for read-only evidence row lookup and support gating.
- `MetricLookup` for compact model-critical metric semantics.
- `ModelRegistry` for model modules, public output keys, boundaries, and
  audit/AI/frontend contract policies.
- `ModelOutput` as an optional payload helper for future modules.

Stage 3 does not add new financial model behavior. D15 remains Macro Regime
Review, not a classifier or probability model. D19 remains historical replay,
not probability modeling or strategy evaluation.

## D16 Scenario Stress Test v0

D16 is implemented as a deterministic scenario matrix / current evidence
transmission review, not a forecast.

It uses current evidence rows and model outputs to summarize predefined scenario
support, affected evidence groups, transmission channels, missing inputs,
severity band, and uncertainty band.

It does not output scenario odds, asset-direction certainty, return estimates,
allocation directives, action instructions, or portfolio optimization results.

Stage 5 D17 follows D16 and is completed.

## D17 Growth / Inflation Macro Pack v0

D17 is implemented as a conservative growth/inflation current-evidence context
layer for growth, inflation, policy-constraint, and stagflation-watch
interpretation.

It is not a forecast, recession call, event-odds model, allocation directive,
or return estimate. Missing and research-needed inputs remain visible and do not
support labels.

Stage 6 D18 follows D17 and is now completed.

## D18 Valuation / Equity Structure v0

D18 is implemented as a conservative valuation/equity-structure research and
proxy context layer. It keeps valuation, earnings, and true breadth gaps
explicit while allowing existing sanitized proxy rows to provide limited
equity-structure and breadth/concentration context.

D18 is not a forecast, timing model, event-odds model, allocation directive, or
return estimate. Valuation context cannot determine macro regime or systemic
review by itself, and proxy breadth/concentration does not replace true breadth.

Stage 7 D19 expanded historical validation follows D18 and is now completed.
Stage 8 Portfolio Exposure Overlay follows D19 and is now completed.

## Later Modeling Areas

Later work may cover AI memo/report surfaces, but Stage 9 productization is not
current. Stage 8 Portfolio Exposure Overlay and Stage 8.5 Foundation
Stabilization Sprint are completed. Later areas must preserve the same source,
freshness, privacy, and evidence-boundary rules.

## Stage R Research Recovery Notes

Status: Stage R1 completed.

Stage R is a documentation-only research recovery track. It can translate
course-paper research into method notes, interpretation boundaries, historical
archetypes, and D19 event-note material. It does not authorize production
models, Dashboard modules, endpoints, frontend UI, AI productization, external
calls, live fetches, or data ingests.

Stage R1 recovers the course-paper research on historical percentiles and
clustering for U.S. macro-financial pressure recognition:

- D13 can reuse percentile methodology, pressure-up normalization language,
  lookback-window discipline, proxy caveats, and `insufficient_history`
  boundary language.
- D15 can reuse historical archetype vocabulary as design context, not as a
  K-means or GMM production classifier.
- D19 can reuse candidate event windows, cluster-period descriptions, and
  external stress index comparison notes as historical validation context.
- Stage 9 memo/report language can reuse boundary sentences that distinguish
  historical pressure interpretation from forecasts, probabilities, and
  actions.

K-means, GMM, cluster probability, cluster-to-action mapping,
cluster-to-portfolio mapping, and full-sample percentile as live D13 are
explicitly outside production logic. External stress indices remain independent
reference layers and do not replace D10, D11, D15, or D19.

The next core modeling step should return to D15/D19, using Stage R1 only as
methodology and boundary-language support.
