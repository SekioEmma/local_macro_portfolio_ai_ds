# Frontend Baseline (Pre-Redesign Snapshot)

Captured 2026-06-18, on branch `app-mvp` at HEAD `09d436d`. This document
is the "before" snapshot taken right before the Era 1 frontend
beautification work begins. It is descriptive only — not a recommendation
and not a contract. The contract is enforced by
`tests/contracts/test_frontend_registry_contracts.py` (registry semantics)
and `tests/contracts/test_api_response_shape.py` (API field set).

## Stack

| Component | Version |
|---|---|
| React | 18.3.1 |
| Vite | 5.4 |
| TypeScript | 5.5 |
| UI library | none (hand-written CSS only) |
| State management | local `useState` per top-level view |
| Routing | none (sidebar `activeView` switch in `App.tsx`) |
| Tests | none on the frontend side (contracts run from Python) |

Dev scripts: `npm run dev` (host 127.0.0.1, port 5173), `npm run build`
(`tsc -b && vite build`), `npm run typecheck`.

## File inventory

| Path | Lines | Role |
|---|---:|---|
| `app_frontend/src/App.tsx` | 932 | All top-level views in one file: Dashboard, Evidence Table, AI Chat placeholder, Account placeholder, Diagnostics |
| `app_frontend/src/App.css` | 933 | Single global stylesheet; 52 `--*` design tokens declared in `:root` |
| `app_frontend/src/main.tsx` | 10 | React 18 root |
| `app_frontend/src/types.ts` | (mirrors backend pydantic shapes) | TS counterpart of `src/app_backend/schemas/responses.py` |
| `app_frontend/src/api/client.ts` | 131 | `fetch` wrappers for 12 backend endpoints |
| `app_frontend/src/components/EvidenceRowsTable.tsx` | 108 | Shared evidence row renderer |
| `app_frontend/src/components/MetricBadge.tsx` | 14 | Status badge |
| `app_frontend/src/components/ModuleDetailDrawer.tsx` | 280 | Side drawer when a module card is clicked |
| `app_frontend/src/utils/moduleRegistry.ts` | 107 | `moduleLabels`, `interpretationBoundaries`, `getModuleBoundary` |
| `app_frontend/src/utils/metricRegistry.ts` | 229 | `metricLabels` (CN + EN, accumulated via `Object.assign`) |
| `app_frontend/src/utils/displayLabels.ts` | 54 | `getModuleLabel`, `getStatusLabel`, `getMetricLabel`, ... |
| `app_frontend/src/utils/statusRegistry.ts` | 41 | `statusLabels`, `freshnessLabels`, `missingReasonLabels` |
| `app_frontend/src/utils/sourceBadgeRegistry.ts` | 12 | `sourceBadgeLabels` |
| `app_frontend/src/utils/styleClasses.ts` | 55 | `aiContextClass`, `freshnessClass`, `sourceBadgeClass` |
| `app_frontend/src/utils/registryContractChecks.ts` | 73 | Runtime registry sanity checks |
| `app_frontend/src/vite-env.d.ts` | (trivial) | Vite types |

Total: ~3,200 LOC across 16 source files. No tests.

## Top-level navigation

`App.tsx` defines five views via a sidebar switch:

| Key | Label | Status |
|---|---|---|
| `dashboard` | 今日市场 | Full implementation: module cards + drawer |
| `evidence` | 全量证据表 | Full implementation: filter bar + evidence table |
| `chat` | AI 对话 | Placeholder ("DeepSeek chat will be added in a later phase") |
| `account` | 账户概览 | Placeholder ("Account editing will be added in a later phase") |
| `diagnostics` | 系统诊断 | Provider health, storage, settings, refresh runs, favorites |

## Backend API surface consumed

All endpoints are local-only (`http://127.0.0.1:8765` by default). The
frontend never reads `.env`, never imports `httpx` / `requests`, and never
calls third-party services. See `src/app_backend/main.py` for the source
of truth.

| Endpoint | Method | Consumer | Schema |
|---|---|---|---|
| `/api/status` | GET | Diagnostics | `StatusResponse` |
| `/api/provider-health` | GET | Diagnostics | `ProviderHealthResponse` |
| `/api/dashboard/summary` | GET | Dashboard | `DashboardSummaryResponse` |
| `/api/dashboard/evidence-table` | GET | Evidence table, dashboard drawer | `DashboardEvidenceTableResponse` |
| `/api/ai/context-preview` | GET | (not yet wired) | `AIContextPreviewResponse` |
| `/api/context/manifest` | GET | (not yet wired) | `AIContextManifestResponse` |
| `/api/app/storage` | GET | Diagnostics | `StorageStatusResponse` |
| `/api/app/settings` | GET / PUT | Diagnostics | `AppSettingsResponse` |
| `/api/app/refresh-runs` | GET / POST | Diagnostics | `list[RefreshRun]` |
| `/api/app/favorites` | GET / POST | Diagnostics | `list[FavoriteAnswer]` |

Not wired in the current UI: `/api/ai/preview-chat`,
`/api/ai/preview-memo`, `/api/ai/preview-report` — they exist on the
backend but the chat view is a placeholder.

## Design tokens (the existing hand-built system)

`App.css` `:root` declares 52 CSS custom properties grouped by:

- **Text & background**: `--text-primary`, `--text-muted`, `--text-soft`,
  `--page-bg`, `--panel-bg`, `--panel-subtle-bg`, `--panel-border`, ...
- **Sidebar**: `--sidebar-bg`, `--sidebar-hover-bg`, `--sidebar-text`,
  `--sidebar-muted`
- **Status colors** (each as text + background pair): `ok`, `watch`,
  `pressure`, `stress`, `missing`, `research-needed`,
  `insufficient-history`, `stale`, `muted`, `unknown`
- **Source badge colors**: `official`, `derived`, `local`, `proxy`, `muted`
- **Freshness colors**: `fresh`, `normal-lag`, `stale`, `muted`
- **Shape tokens**: `--radius-card`, `--radius-chip`, `--space-card`,
  `--shadow-panel`, `--shadow-drawer`

There are 130 `var(--*)` references and 160 `.class` rules. The redesign
should preserve the **status / source / freshness color taxonomy** as the
semantic anchor — the underlying values can change, but every
`status_*` / `source_*` / `freshness_*` key produced by the backend must
still resolve to a distinct, accessible visual state.

## Frontend / backend registry alignment

Backend `ModelRegistry` defines 10 `model_output` module keys. The
frontend `moduleLabels` and `interpretationBoundaries` maps must cover
all of them; backend `public_output_keys(module_key)` must each appear in
`metricLabels`. These invariants are enforced by
`tests/contracts/test_frontend_registry_contracts.py`.

Module keys (as of this snapshot):

```
financial_stress_composite
growth_inflation_macro_pack
historical_risk_percentile
historical_validation
liquidity_funding_stress
macro_regime_review
portfolio_exposure_overlay
pullback_systemic_risk_checklist
scenario_stress
valuation_equity_structure
```

## Locked privacy / safety boundaries (must survive the redesign)

These are project-wide red lines, not just frontend conventions:

- The frontend must never reference raw provider payloads or raw holdings
  rows. Enforced by
  `test_frontend_files_do_not_contain_raw_provider_or_holdings_payload_logic`.
- The frontend must not introduce new endpoints `/api/chat`,
  `/api/search`, `/api/ai/deepseek`, `/api/ai/external`, or
  `/api/ai/tavily`. Stage 9 external AI productization stays frozen.
- The chat view stays a placeholder. No `fetch` to a chat endpoint, no
  prompt input box wired to a real backend.
- The account view stays read-only. No holdings editing UI.
- Module / metric / status keys are produced by the backend; the frontend
  is a renderer, never a source of truth for these strings.

## What the redesign is free to change

- Component file structure under `app_frontend/src/components/`.
- Single-file `App.tsx` can split into route-level components.
- Import paths inside the frontend (the contract tests no longer pin
  specific paths or JSX literals).
- CSS strategy: vanilla CSS → Tailwind / shadcn / design-token JSON, all
  acceptable.
- Label text wording in both languages, as long as every required key has
  an entry.
- `App.css` can be deleted / replaced with a different token system
  provided the semantic status taxonomy survives.

## Reference: contract tests that gate this work

| Test file | What it pins |
|---|---|
| `tests/contracts/test_frontend_registry_contracts.py` | Registry coverage + drawer reads boundaries from registry + privacy guard |
| `tests/contracts/test_api_response_shape.py` | Exact field set of every response model the frontend consumes |
| `tests/contracts/test_golden_output_contract.py` | Existing end-to-end manifest / row contract |
| `tests/contracts/test_stage8_registry_consistency.py` | Existing Stage 8 portfolio overlay registry consistency |

Run before opening a redesign PR:

```
python -m pytest tests/contracts -q
cd app_frontend && npm run typecheck && npm run build
```
