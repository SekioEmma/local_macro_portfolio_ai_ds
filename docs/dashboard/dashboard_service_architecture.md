# Dashboard Service Architecture

M4a is a low-risk extraction pass for `dashboard_service.py`. It keeps the
public service behavior stable while moving two small helper boundaries into
dedicated modules.

## Current service boundary

`src/app_backend/services/dashboard_service.py` remains the public orchestrator
for dashboard summary and evidence table construction.

It still owns:

- report loading and JSON parse error handling;
- dashboard module assembly;
- evidence row assembly and row ordering;
- last-good candidate writes;
- response construction for summary and evidence endpoints.

## Extracted helpers

`src/app_backend/services/dashboard_context.py`

- Owns `DashboardPipelineContext`, the explicit request-scoped state object
  introduced in M3.
- `dashboard_service.DashboardPipelineContext` remains available through a
  re-exported imported name, so existing call sites do not need to change.

`src/app_backend/services/dashboard_filters.py`

- Owns evidence row predicate and post-build filtering.
- Filtering is still applied after all evidence rows are built. This preserves
  the current D10/D11/D13/D14 build order and row semantics.

## Deliberately unchanged

M4a does not change:

- D10 financial stress weights, conditions, output rows, or interpretation text;
- D11 pullback checklist conditions, classification rules, or output rows;
- D13 percentile, z-score, robust-z, history quality, or eligibility logic;
- D14 liquidity/funding stress rules, source rows, or boundary text;
- source badge, freshness, missing-data, or AI-context eligibility gates;
- D12 AI context manifest privacy, destination, or persistence policy;
- last-good write policy;
- row order for unfiltered evidence tables.

## Deferred extraction candidates

The report loader and evidence assembly shell remain inside
`dashboard_service.py` in M4a. They touch many internal helpers and are better
split in M4b only after a broader golden-output test surface is in place.
