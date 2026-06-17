# Local Macro Portfolio AI DS - Project Index

One-page orientation. Read this first when returning to the project after a
break. Detailed history stays in `docs/current_project_state.md`. The immediate
route is in `docs/short_term_development_plan.md`.

## Current Truth

- Current branch: `app-mvp`
- Current phase: Stage S - Scenario Stress / Explanation Refinement (S1 complete)
- Last completed task: P-M3 Historical Risk Normalization metadata helper split
  (behavior-preserving; no model semantics changed)
- Last completed governance task: HF-2 Project Namespace Index / Governance
  Light Cleanup
- Current immediate route: performance hardening
- Next engineering task: P-M4 M11 cross-request shared context cache design,
  or pause for manual review before cache work
- Frozen lines: external AI productization, Chat UI, Tavily/search, Tauri,
  full-account DeepSeek context, live provider fetch/write,
  prediction/probability/trading outputs

## What This Project Is

A local-first macro risk research workbench:

- macro risk evidence system
- explainable financial and math model layer
- personal portfolio risk explanation layer
- AI research context foundation
- Chinese professional research report system

## What This Project Is Not

- no auto-trading
- no short-term prediction engine
- no AI stock picker
- no news sentiment trading
- no portfolio optimizer
- no brokerage sync
- no real-time market terminal

## Namespace Map

The project uses several parallel namespaces. Each namespace has its own
discipline. Always check `short_term_development_plan.md` for the active item.

### D-line: Financial / Macro Model Modules

New docs prefer plain-English module names; D IDs are legacy aliases. See
[Legacy ID Translation](#legacy-id-translation) below.

- D7-D9: data foundation, drawdowns, curves, cross-asset, labor mini-pack
- D12: AI Context Manifest / context preview (privacy and eligibility gate)
- Financial Stress Composite (legacy: D10): `financial_stress_composite`
  (pressure temperature, not probability)
- Pullback vs Systemic Risk Review (legacy: D11):
  `pullback_systemic_risk_checklist` (current evidence review)
- Historical Risk Normalization (legacy: D13): `historical_risk_percentile`
  (percentile / z-score / robust z-score, 5Y/3Y windows, DF-4
  reliability/divergence metadata, DF-4c OAS coverage)
- Liquidity & Funding Stress (legacy: D14): `liquidity_funding_stress`
- Macro Regime Review (legacy: D15): current evidence review, not classifier
- Scenario Stress Matrix (legacy: D16): S1 refinement; not a probability or
  forecast model
- Growth & Inflation Context (legacy: D17): Growth / Inflation Macro Pack
  (not a recession call)
- Valuation & Equity Structure Context (legacy: D18): not a timing model;
  proxy/research only
- Historical Validation Replay (legacy: D19): event-window replay, not backtest

### M-line: Maintainability / Performance Work

- M1: dashboard pipeline benchmark (completed)
- M2: batch market history reads (completed)
- M3: shared dashboard pipeline context (completed)
- M4a: dashboard service helper split (completed)
- M5: audit pipeline modularized (completed)
- M6: frontend display registries organized (completed)
- M7/M8-A: dashboard model pipeline extraction (completed; remaining work in
  `docs/foundation_stabilization_backlog.md`)
- P-M1 completed: dashboard_model_pipeline row conversion accumulator
  (Historical Risk Normalization through Scenario Stress Matrix)
- P-M2 completed: dashboard_service helper split (M7/M8-B follow-up)
- P-M3 completed: Historical Risk Normalization (legacy: D13) metadata helper
  split (reliability/divergence and OAS coverage helpers extracted)
- P-M4 planned: M11 cross-request shared context design

### DF-line: Data Foundation / Historical Evidence (concluded)

- DF-0: roadmap arbitration and legacy doc cleanup (completed)
- DF-1: D19 v1 historical evidence-row integration (completed)
- DF-2: D15/D16 compliance audit (completed)
- DF-3: D17/D18 data gap and source-gate review (completed)
- DF-4: D13 reliability / divergence metadata (completed)
- DF-4a: Credit OAS history availability audit (completed)
- DF-4c: Credit OAS coverage / provider-rebuild metadata (completed)
- DF-4d: BAA10Y D19 proxy/reference documentation (deferred unless explicitly
  requested)

Stage DF is concluded. No default DF-5.

### S-line: Scenario Stress / Explanation Refinement

- S0: Post-DF roadmap reconciliation (completed)
- S1: D16 Scenario Stress Refinement v1 (completed)
- HF-1: Test Runtime Hotfix / DB-backed Fixture Batching (completed)
- HF-2: Project Namespace Index / Governance Light Cleanup (current; docs-only)
- S2: D16 scenario explanation tests / golden contract integration (deferred
  until after performance work unless explicitly requested)
- S3: AI memo boundary template update (deferred; only after S2)

### R-line: Research Recovery

- R1: Course Paper Research Recovery Note (completed as docs-only research
  recovery). K-means, GMM, cluster probability, and cluster-to-action mapping
  remain outside production.

### Stage 8 / 8.5

- Portfolio Exposure Overlay (legacy: Stage 8): v0 completed; downstream-only,
  privacy-preserving
- Stage 8.5: Foundation Stabilization Sprint (completed)

### Stage 9 / External AI (frozen)

- Stage 9.0–9.3-B: preparation, adapter design, security closeout (completed
  where documented)
- Stage 9.3-B-2d: internal one-shot manual invocation review (completed)
- External AI productization: frozen
- No Chat endpoint, no frontend chat, no Tavily/search, no persistence, no
  automatic external calls

## Source of Truth Policy

| Document | What it owns |
|---|---|
| `docs/INDEX.md` | navigation map and current orientation (this file) |
| `docs/short_term_development_plan.md` | immediate route and next task |
| `docs/current_project_state.md` | detailed project state and completed baseline |
| `docs/modeling_roadmap.md` | modeling-history narrative and module boundaries |
| `docs/foundation_stabilization_backlog.md` | M-line backlog (M7-M12) |
| stage-specific closeout docs | per-stage evidence and contract |

When these disagree, `docs/short_term_development_plan.md` is the immediate
route source of truth. `docs/current_project_state.md` and
`docs/modeling_roadmap.md` carry the longer narrative and module boundaries but
should not be read as "what to do next".

## Task Level Policy

See `docs/task_governance_policy.md` for L1 / L2 / L3 / L4 task-level rules and
validation requirements. The short version:

- L1 micro-fixes do not require full governance doc updates.
- L2 docs/audit/metadata-only tasks update governance docs and a closeout doc.
- L3 boundary-touching production changes run the full validation set.
- L4 product surface / external AI / privacy changes require explicit user
  approval before implementation.

## Current Backlog (ordered)

1. ~~P-M1 dashboard_model_pipeline row conversion accumulator~~ (completed)
2. ~~P-M2 dashboard_service helper split~~ (completed)
3. ~~P-M3 Historical Risk Normalization (legacy: D13) metadata helper split~~
   (completed)
4. P-M4 M11 cross-request shared context cache design, or pause for manual
   review before cache work
5. S2 Scenario Stress Matrix (legacy: D16) explanation tests / golden contract
   integration (only after explicit decision)
6. S3 AI memo boundary template update (only after S2)
7. DF-4d BAA10Y Historical Validation Replay (legacy: D19) proxy/reference
   documentation (only if explicitly requested)

Not on this list: external AI productization, Chat UI, Tavily/search, Tauri,
full-account DeepSeek context, account editing, live provider fetch/write,
prediction/probability/trading outputs. These remain frozen.

## Naming Policy

Future task names and commit messages prefer human-readable names over deep
stage codes. Stage IDs may remain in docs for historical mapping, but a commit
message like `Speed up DB-backed test fixtures` is preferred over `Add HF-1
test runtime hotfix`. See `docs/task_governance_policy.md`.

## Legacy ID Translation

The project historically used D10-D19 IDs for model modules. New docs should
prefer plain-English names and keep D IDs only as legacy aliases.

| Plain-English name | Legacy ID | Role |
|---|---|---|
| Financial Stress Composite | D10 | combines core financial stress evidence across rates, credit, equity, liquidity, and volatility |
| Pullback vs Systemic Risk Review | D11 | distinguishes ordinary equity pullback from broader systemic-risk evidence |
| Historical Risk Normalization | D13 | historical percentile, z-score, robust z-score, reliability/divergence metadata, and credit OAS coverage metadata |
| Liquidity & Funding Stress | D14 | liquidity plumbing, short-term funding pressure, official stress references, and funding confirmation |
| Macro Regime Review | D15 | current-evidence macro pressure review, not classifier/probability/forecast/trading model |
| Scenario Stress Matrix | D16 | hypothetical scenario matrix and current evidence transmission review, not forecast/event-odds/return/action model |
| Growth & Inflation Context | D17 | conservative growth, inflation, policy-constraint, and stagflation-watch context |
| Valuation & Equity Structure Context | D18 | valuation, earnings, true-breadth gaps, equity structure, breadth/concentration proxy context |
| Historical Validation Replay | D19 | historical event-window replay, coverage review, boundary validation, and reference-only historical context |
| Portfolio Exposure Overlay | Stage 8 | downstream-only sanitized portfolio exposure explanation layer, not allocation advice or optimizer |

**Pipeline order (human-readable):**

```
Historical Risk Normalization (legacy: D13)
→ Liquidity & Funding Stress (legacy: D14)
→ Financial Stress Composite (legacy: D10)
→ Pullback vs Systemic Risk Review (legacy: D11)
→ Growth & Inflation Context (legacy: D17)
→ Valuation & Equity Structure Context (legacy: D18)
→ Macro Regime Review (legacy: D15)
→ Historical Validation Replay (legacy: D19)
→ Scenario Stress Matrix (legacy: D16)
→ Portfolio Exposure Overlay (legacy: Stage 8)
```

Production identifiers (`module_key`, `model_key`, `metric_key`, registry keys,
and public output keys) are unchanged.
