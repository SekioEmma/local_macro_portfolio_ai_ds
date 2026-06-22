# UI-0 Frontend Information Architecture Audit

## Scope

Read-only frontend information architecture audit after Data Foundation G1.
The audit inspected the existing frontend shell, pages, components, API client,
response types, registries, placeholders, and build readiness. It did not
change frontend code, backend code, API schemas, model semantics, AI Context
Manifest semantics, providers, or generated data.

## Baseline

- Audit date: 2026-06-18.
- Branch: `app-mvp`.
- HEAD before audit: `09d436d Add unified local app launcher`.
- Required baseline `097377f Audit controlled local data refresh coverage` is
  an ancestor of HEAD.
- `HEAD...origin/app-mvp`: `0 0` at preflight.
- Working tree: clean at preflight.
- Data Foundation G1: 45,243 market-history observations, 125 included facts,
  63 included model outputs, zero dashboard `insufficient_history` rows, and
  Historical Risk Normalization history sufficiency true.
- Current route: frontend data display using existing backend APIs and source
  gates.
- G2 remains optional and requires explicit approval.
- Frozen: external AI productization, Chat UI activation, Tavily/search,
  Tauri, account editing, live provider refresh/write, prediction,
  probability, return, trading, allocation, and holdings-line-item surfaces.

Preflight found the repository-tracked placeholders
`outputs/analyst_memos/.gitkeep` and `outputs/reports/.gitkeep`. The user
explicitly approved continuing with those two placeholders as exceptions. No
generated file under `outputs`, `cache`, or private data was read, changed, or
committed.

## Frontend Structure

- Frontend root: `app_frontend`.
- Stack: React 18, Vite 5, and TypeScript 5.
- Package and lockfile: `package.json` and `package-lock.json`.
- Existing dependencies were present in `node_modules`; no installation was
  required.
- Scripts: `dev`, `build`, `preview`, and `typecheck`.
- Entry and shell: `src/main.tsx`, `src/App.tsx`, and `src/App.css`.
- API client: `src/api/client.ts`.
- Response types: `src/types.ts`.
- Components: `EvidenceRowsTable`, `MetricBadge`, and
  `ModuleDetailDrawer`.
- Registries: module, metric, source-badge, status, style-class, and registry
  contract helpers under `src/utils`.
- Navigation uses local `activeView` state. There is no router dependency,
  URL route mapping, deep link, or browser-history integration.
- There are no separate `pages`, `routes`, or `hooks` directories.
- There is no frontend test script. Registry compatibility is checked by
  backend-side contract tests.

## Existing Pages and Capabilities

| Area | Exists | Uses real API | Main files | Main gaps | Risk |
|---|---:|---:|---|---|---|
| Dashboard summary | yes | yes | `App.tsx`, `client.ts`, `types.ts` | Does not display dashboard `next_actions`; key metric rows omit raw source, source series, observation/generated dates, unit, metric key, and explicit AI eligibility on the card | medium |
| Evidence Table | yes | yes | `App.tsx`, `EvidenceRowsTable.tsx` | No metric-key search, row expansion, copy JSON, copy fact summary, source/source-series columns, unit column, or component-contribution inspection | medium |
| Module detail | yes | yes | `ModuleDetailDrawer.tsx`, `EvidenceRowsTable.tsx` | Generic evidence table does not expose nested model metadata or full provenance | low |
| Scenario Stress Matrix | partial | yes, through generic evidence API | metric/module registries and module drawer | No dedicated matrix view; nested scenarios and S1/S2 metadata in `component_contributions` are not rendered | high |
| Historical Validation Replay | partial | yes, through generic evidence API | metric/module registries and module drawer | No dedicated replay view; event-window, coverage, consistency, proxy, missing-data, and replay-version detail is not organized for review | high |
| AI Context Preview | no active page | no active call | dormant type and `fetchAIContextManifest()` | Client function exists but is unused; included/excluded facts and model outputs, exclusion reasons, policies, and forbidden-output boundaries are not displayed | high |
| Provider Health | yes | yes | Dashboard status and Diagnostics view | Per-check `error_summary`, endpoint summary, `next_action`, observation date, and value-presence detail are hidden | medium |
| Missing/Freshness | yes | yes | Dashboard view | Missing rows are summarized generically; freshness is file-oriented and does not offer a focused stale/missing review | medium |
| Account placeholder | yes | no | `App.tsx` | Clearly says current phase is read-only, but “will be added later” can imply an approved route when account editing is frozen | medium |
| AI Chat placeholder | yes | no | `App.tsx`, `ModuleDetailDrawer.tsx` | Disabled/no-send behavior is clear, but “will be added later” should become an explicit frozen/not-approved label in a future UI task | medium |
| Settings/diagnostics | yes | yes, read-only UI | `App.tsx`, `client.ts` | Settings are displayed as raw key/value records; no editing control is active | low |

Loading, top-level error, and empty-table states exist. The shell eagerly
loads status, provider health, dashboard, two evidence-table variants,
storage, settings, refresh-run history, and favorites on initial mount,
regardless of the active view.

## Backend API Contract Usage

| Endpoint | Frontend function | Active UI use | Contract assessment |
|---|---|---:|---|
| `GET /api/status` | `fetchStatus` | yes | Type matches current backend response; diagnostics reveal only configured/missing key booleans, not key values |
| `GET /api/provider-health` | `fetchProviderHealth` | yes | Type matches; UI hides several diagnostic fields |
| `GET /api/dashboard/summary` | `fetchDashboardSummary` | yes | Type matches current schema; significant response fields are not fully presented |
| `GET /api/dashboard/evidence-table` | `fetchDashboardEvidenceTable` | yes | Filters match backend query parameters; row type matches `blocked_reason` and current optional metadata |
| `GET /api/ai/context-preview` | `fetchAIContextManifest` | no | Type matches inherited manifest fields, but no page calls it |
| `GET /api/context/manifest` | none | no | Not consumed |
| `POST /api/ai/preview-chat` | none | no | Not consumed |
| `POST /api/ai/preview-memo` | none | no | Not consumed |
| `POST /api/ai/preview-report` | none | no | Not consumed |
| `GET /api/app/storage` | `fetchStorageStatus` | yes | Read-only diagnostics |
| `GET /api/app/settings` | `fetchSettings` | yes | Read-only diagnostics |
| `GET /api/app/refresh-runs` | `fetchRefreshRuns` | yes | Reads local app-state records; does not run providers |
| `GET /api/app/favorites` | `fetchFavorites` | yes | Reads local placeholder/app-state records |

No frontend call exists for `/api/chat`, `/api/search`, `/api/ai/external`,
`/api/ai/deepseek`, Tavily, or a live provider refresh/write endpoint.

The API client defines unused mutation helpers:

- `updateSettings()` -> `PUT /api/app/settings`
- `createRefreshRun()` -> `POST /api/app/refresh-runs` with a
  `ui_placeholder` record
- `createFavorite()` -> `POST /api/app/favorites` with mock text

They are not imported or called by the UI. They are not active blockers, but
they are frozen-surface risks and must remain unconnected unless a separately
approved task opens those product surfaces.

## Dashboard Homepage Display Audit

The homepage displays:

- `overall_status`
- `overall_risk_level`
- provider-health overall status
- missing-data summaries
- file freshness
- all six fixed dashboard modules
- module status, source badge, updated time, summary, and up to five key
  metrics

The six required modules are supported:

- `credit_stress`
- `rate_pressure`
- `real_yield_pressure`
- `inflation_energy_pressure`
- `equity_trend`
- `portfolio_deviation`

Main gaps:

- Dashboard-level `next_actions` is not rendered.
- Cards do not show `metric_key`, `unit`, raw `source`, `source_series`,
  `observation_date`, `generated_at`, or a normal explicit
  `ai_context_allowed` indicator.
- Module detail adds observation date and AI eligibility but still omits raw
  source, source series, generated time, unit, input evidence, missing inputs,
  and component contributions.
- `value_text` formatting is inconsistent: the reusable detail table replaces
  unexplained `--`, while the homepage and full Evidence Table use raw
  `value_text`. Missing reasons are usually nearby, but UI-1 should use the
  same explicit formatter everywhere.
- Portfolio deviation remains compact and does not display holdings line
  items or action language.
- Registry boundaries correctly state that DGS is daily, PPIACO is not final
  demand PPI, cash reserve is not target allocation, and module status is not
  a trading signal.

## Evidence Table Audit

Currently displayed:

- module and raw module key
- `metric_key`
- `display_name`
- `value_text`
- status
- `source_badge`
- `freshness_status`
- `observation_date`
- `generated_at`
- `ai_context_allowed` plus `blocked_reason`
- `missing_reason`
- `interpretation_hint`

Currently supported filters:

- module
- status
- source badge
- AI-context eligibility

Missing:

- raw `source`
- `source_series`
- `unit`
- visible structured blocked-reason detail
- `input_evidence`
- `missing_inputs`
- `interpretation_boundary`
- `component_contributions`
- metric-key search
- row detail expansion
- copy row JSON
- copy fact summary

These are UI-2 readability and auditability priorities. They do not require a
new backend endpoint.

## Scenario Stress Matrix Audit

Scenario Stress rows and labels exist in the registry, and generic evidence
rows can reach the Evidence Table and module drawer. There is no dedicated
Scenario Stress Matrix page or visualization.

The UI does not unpack the scenario list or display:

- affected groups and transmission channels as structured relationships
- severity and uncertainty bands per scenario
- supporting evidence and missing inputs per scenario
- uncertainty drivers, missing constraints, proxy constraints, source-gate
  constraints, D13 reliability/divergence/OAS context, D17/D18 gaps, D19
  reference context, or the refinement boundary

The generic module boundary is present and correctly says Scenario Stress is
not a forecast, event-odds model, asset-direction call, allocation directive,
or return estimate. A dedicated UI-3 view must preserve and make that boundary
prominent.

## Historical Validation Replay Audit

Historical Validation labels and generic evidence rows exist, but there is no
dedicated replay page. The current UI does not organize event counts,
event-window summaries, coverage, module consistency, proxy constraints,
missing-data summaries, boundary violations, or replay version into a
reviewable replay display.

The generic module boundary correctly states that Historical Validation is not
a forecast, event-odds model, strategy evaluation, allocation directive, or
return estimate. UI-4 should additionally state explicitly that it is not a
backtest, prediction-accuracy claim, ROC/AUC analysis, or trading-performance
report.

## AI Context Preview Audit

No active AI Context Preview page exists. `AIContextManifestResponse` and
`fetchAIContextManifest()` are already defined, but the shell never calls the
function and no navigation item renders the response.

UI-5 should display:

- included and excluded facts
- included and excluded model outputs
- exclusion reasons
- source badges, freshness, and AI-context eligibility
- portfolio, privacy, search, model-destination, and persistence policies
- risk and forbidden-output boundaries

The page must remain preview-only: no real DeepSeek, Tavily, Chat endpoint,
prompt/response persistence, full-account context, or holdings-line-item
exposure.

## Provider, Missing, and Freshness Audit

- Provider status is visible on the homepage and in Diagnostics.
- Provider failures are not fabricated as normal, but per-check error details
  and endpoint `next_action` are not shown.
- Missing data and file freshness are visible on the homepage.
- Stale and blocked labels exist in status/freshness registries.
- The Diagnostics “重新读取” button only repeats GET requests. It is not a
  provider refresh or write action.
- No export button exists.
- No active live refresh/write control exists.

## Placeholder / Misleading UI Risks

| Location | Text/code | Risk | Recommended treatment |
|---|---|---|---|
| `App.tsx` Chat placeholder | “will be added in a later phase” | Implies future approval although Chat UI is frozen | In UI-1, label as frozen/not approved and keep disabled |
| `App.tsx` Account placeholder | “editing will be added in a later phase” | Implies future approval although account editing is frozen | In UI-1, label as read-only placeholder; remove roadmap promise |
| `ModuleDetailDrawer.tsx` disabled button | “后续阶段打开 AI Chat” | Visually advertises a frozen surface | Hide or relabel as “AI Chat 未批准/未启用” |
| `client.ts` unused create functions | Mock favorite and `ui_placeholder` refresh-run payloads | Could create misleading stored records if wired accidentally | Keep unimported; consider removing in a separately approved cleanup |
| homepage/full Evidence Table | raw `value_text` | Can show inconsistent placeholders instead of normalized status text | Use the existing formatter consistently in UI-1 |

No fake sparkline, trend chart, forecast path, probability, allocation pie
chart, AI insight, news/search result, or holdings-detail visualization was
found.

## UX and Information-Hierarchy Notes

For this data-heavy local risk dashboard, clarity and auditability should take
priority over decorative visualization:

- Status must use text plus color, not color alone.
- Dense model metadata should use progressive disclosure through row expansion
  or a detail drawer.
- Scenario and historical views should provide text summaries alongside any
  visualization.
- Tables should preserve readable labels while keeping raw module and metric
  keys available for audit.
- Frozen or disabled actions must be semantically disabled and explicitly
  labeled.
- Loading, error, empty, stale, missing, and blocked states must remain
  distinct.

## Frozen Surface Check

No active frontend integration was found for:

- Chat endpoint or Chat product flow
- DeepSeek live call
- Tavily/search
- Tauri
- account editing
- live provider refresh/write
- prediction, event odds, probability, expected return, trading action, or
  allocation directive
- holdings line items

The account and Chat navigation items are placeholders only. Unused local
app-state mutation helpers exist in the API client, but they are not connected
to UI controls.

## Recommended UI Route

1. UI-1 Dashboard homepage data-display polish using existing APIs only.
2. UI-2 Evidence Table readability and structured row detail.
3. UI-3 Scenario Stress Matrix visualization.
4. UI-4 Historical Validation Replay display.
5. UI-5 AI Context Preview display.

All work should reuse the existing summary, evidence-table, and context-preview
contracts before considering any new backend surface.

## First Implementation Task Recommendation

UI-1 Dashboard homepage data-display polish using existing APIs only.

UI-1 should render dashboard `next_actions`, normalize missing/stale value
display, expose complete key-metric provenance through progressive disclosure,
show provider error/next-action detail, and relabel frozen Chat/account
placeholders. It must not add routes, backend endpoints, account editing,
provider writes, external AI, or new financial semantics.

## Validation

- `git status --short --untracked-files=all`: clean at preflight.
- `git branch --show-current`: `app-mvp`.
- `git rev-list --left-right --count HEAD...origin/app-mvp`: `0 0` at
  preflight.
- `git merge-base --is-ancestor 097377f HEAD`: passed.
- Frontend source and API-contract audit: completed read-only.
- `npm.cmd run typecheck`: passed.
- `npm.cmd run build`: passed; Vite transformed 41 modules and produced the
  ignored local `dist` output.
- `python scripts/dev_check_validator_boundaries.py`: passed; allowed=9,
  blocked=8, regression=17.
- Targeted dashboard/API/AI Context Manifest/golden-contract regression:
  26 passed with one existing Starlette/TestClient deprecation warning.
- `git diff --check`: passed; Git emitted only line-ending conversion
  warnings.
- Final tracked changes are limited to the five allowed documentation files.

UI-0 is a read-only frontend information architecture audit. It does not
change frontend code, backend code, API schema, financial model semantics, AI
Context Manifest semantics, providers, endpoints, external AI, Tavily/search,
Tauri, account editing, live fetch/write, generated data, prediction outputs,
probability outputs, return estimates, allocation outputs, trading advice, or
holdings line item exposure.
