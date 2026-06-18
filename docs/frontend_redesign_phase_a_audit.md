# Frontend Redesign Phase A Audit

Date: 2026-06-18

## Scope and branch

- Working branch: `frontend-redesign`
- Preflight HEAD: `a95521631dca1d65b2e06477473b0c959c22677d`
- Upstream: `origin/frontend-redesign`
- Worktree at preflight: clean
- `main` is not used or modified.
- The branch is currently 2 commits ahead of and 3 commits behind
  `origin/app-mvp`. This redesign continues on the explicitly requested branch;
  no automatic merge or rebase is performed.

## Design inputs reviewed

- `Local_Macro_Portfolio_AI_DS_前端金融侧设计方案.pdf` (23 pages)
- Dashboard, Evidence Audit, AI Context Preview, and Portfolio/Diagnostics
  reference images supplied with the task
- Existing paper-style dashboard implementation from commit `265a113`
- Repository governance, current-state, modeling-roadmap, frontend-audit, and
  pre-redesign baseline documents

The target visual system is warm paper / charcoal / low-saturation status
colors. A generic dark-dashboard recommendation produced by the UI design
search was rejected because it conflicts with the supplied design source of
truth.

## Current frontend baseline

- React 18 + TypeScript + Vite
- Hand-written CSS and local React state
- No router dependency; top-level views are selected in `App.tsx`
- Existing active views:
  - Dashboard
  - Evidence Table
  - frozen AI placeholder
  - read-only account placeholder
  - Diagnostics
- Existing shared components:
  - `DashboardHomepage`
  - `ModuleDetailDrawer`
  - `EvidenceRowsTable`
  - `MetricBadge`
- Existing semantic registries cover module labels, metric labels, statuses,
  source badges, freshness, CSS classes, and interpretation boundaries.

## Read-only API mapping

| Surface | Existing API | Frontend treatment |
|---|---|---|
| Dashboard | `GET /api/dashboard/summary` | Header, temperature, executive brief, risk channels, compact evidence, freshness |
| Evidence Audit | `GET /api/dashboard/evidence-table` | Local search/filter, audit table, row drawer, copy helpers |
| Module Drawer | Summary modules + evidence rows grouped by module | Overview / metrics / sources / boundaries tabs |
| Scenario Stress | Evidence rows where `module=scenario_stress` | Structured scenario cards and transmission review |
| Historical Validation | Evidence rows where `module=historical_validation` | Coverage summary, event replay, boundary review |
| AI Context Preview | `GET /api/context/manifest` | Included/excluded facts and model outputs, policies, read-only preview |
| Portfolio Overlay | Dashboard `portfolio_deviation` + evidence rows where `module=portfolio_exposure_overlay` | Sanitized local-only exposure explanation |
| Diagnostics | `GET /api/status`, `GET /api/provider-health`, Dashboard freshness/missing summaries | Provider, freshness, missing, privacy, validator-boundary audit |

The existing `fetchAIContextManifest()` points to `/api/ai/context-preview`
while its TypeScript return type models the base manifest. The preview schema
extends the manifest, so this is not currently unsafe, but the redesign will
use the exact read-only `/api/context/manifest` contract for the manifest
review page.

## Field availability and fallback policy

The existing contracts expose enough data for the requested pages:

- `DashboardMetric` and `DashboardEvidenceRow` include source, source series,
  observation/generated dates, unit, freshness, missing/blocked reasons,
  interpretation hints/boundaries, AI eligibility, input evidence, component
  contributions, missing inputs, lookback/history metadata, percentile and
  z-score metadata, AI tier, and trigger eligibility.
- Scenario, Historical Validation, Macro Regime, Financial Stress, and
  Portfolio Exposure model outputs are already represented as evidence rows.
- AI Context Manifest already exposes included/excluded facts and model
  outputs plus portfolio, privacy, search, destination, persistence, and risk
  policies.

When a field is absent, the UI will show `not available`, `missing`,
`research_needed`, or an explicit disabled surface. It will not synthesize
production values, time series, probabilities, or placeholder charts.

## Information architecture decisions

1. Dashboard becomes a brief, not a complete field listing.
2. The Financial Stress score is rendered only when a real numeric
   `financial_stress_score` row exists; otherwise the temperature component
   shows a band or `not available`.
3. Eight dashboard risk-channel tiles use only existing module summaries and
   metrics.
4. Module details use one tabbed drawer shared by dashboard modules and
   evidence-driven model modules.
5. Evidence Audit performs additional freshness, trigger, and text filtering
   locally over the existing complete read-only response; no new endpoint is
   needed.
6. Scenario and Historical pages unpack existing row values and
   `component_contributions` defensively. Unknown shapes remain readable as
   labeled key/value content rather than fabricated diagrams.
7. AI Context is a manifest preview only. No prompt submission, external model,
   search, or persistence control is added.
8. Portfolio is sanitized and aggregate-only. No holdings line items or account
   editing controls are rendered.
9. Diagnostics removes the misleading refresh action and presents current
   read-only pipeline state only.

## Safety and frozen-line confirmation

- No backend code or public API schema change is planned.
- No provider refresh/write call is added.
- No external AI, DeepSeek, Tavily, search, or chat request is added.
- No account write or holdings line-item surface is added.
- No prediction, probability, expected return, target price, optimization, or
  trading-action language is added.
- No generated files under `outputs` or private holdings data are read for this
  audit.

## Implementation phases

1. Shared paper shell, navigation, design tokens, badges, notices, icons.
2. Dashboard and tabbed Module Detail Drawer.
3. Evidence Audit and Evidence Row Drawer.
4. AI Context Preview.
5. Scenario Stress and Historical Validation.
6. Portfolio Overlay and Diagnostics.
7. Responsive/accessibility cleanup and validation.

