# Frontend Registry Architecture

## M6 Scope

M6 only organizes frontend display registries. It does not change API response
schemas, backend dashboard logic, evidence row content, AI manifest policy,
source/freshness gates, or D10/D11/D13/D14 financial semantics.

The frontend registry files are display helpers:

- `app_frontend/src/utils/moduleRegistry.ts` owns module labels, module display
  metadata, and module interpretation-boundary copy.
- `app_frontend/src/utils/metricRegistry.ts` owns metric display labels.
- `app_frontend/src/utils/statusRegistry.ts` owns status, freshness, and missing
  reason labels.
- `app_frontend/src/utils/sourceBadgeRegistry.ts` owns source-badge labels.
- `app_frontend/src/utils/displayLabels.ts` keeps the existing public helper API
  and delegates to the registries.

## Boundary

The registries are not a financial logic layer. They do not drive backend
classification, scoring, source selection, freshness checks, AI eligibility, or
missing-data gates. The backend evidence rows, audit output, and docs remain
the source of truth.

D10/D11/D13/D14 boundaries are displayed by the frontend registry, but their
meaning remains governed by the backend evidence rows and project docs:

- D10 financial stress is pressure temperature, not crash probability.
- D11 pullback checklist is review context, not a forecast or trading command.
- D13 percentile and z-score are historical rarity/normalization, not
  prediction.
- D14 liquidity/funding rows are reference evidence and cannot stand alone as a
  systemic trigger.

Proxy breadth remains a proxy, not true constituent breadth. Portfolio
deviation cannot be attributed to macro factors by itself.

## Future Work

M6b could add a frontend test runner or component snapshots for the drawer and
evidence table. D15 regime classification remains deferred and should not be
introduced through display registries.
