# Macro Display Semantics And Labels

This pass fixes display semantics and readability without changing provider fetch logic or internal enum values.

## Inflation YoY Semantics

Dashboard rows whose metric key ends in `_yoy` must display an actual year-over-year rate.

Allowed display cases:

- decimal rate, such as `0.0335`, is normalized to `+3.35%`
- percent-point value, such as `3.35`, is displayed as `+3.35%`

Blocked display cases:

- index levels such as Core CPI `335.42` or Core PCE `129.63`
- payloads that explicitly describe the compact value as an index level

When only an index level is available, the row is blocked:

- `status=insufficient_history`
- `value=null`
- `value_text=insufficient history`
- `source_badge=missing`
- `ai_context_allowed=false`
- `missing_reason=Only index level is available; YoY requires historical comparison.`

No YoY value is fabricated from a single compact index observation.

## PPI Boundary

`ppiaco_yoy` remains distinct from PPI final demand.
`ppi_final_demand` remains `research_needed` until an official series id is verified.

## Frontend Labels

Frontend display labels live in `app_frontend/src/utils/displayLabels.ts`.
They translate module, status, source badge, freshness, and AI-context display text only.

The raw internal values remain unchanged:

- `metric_key`
- `status`
- `source_badge`
- `freshness_status`
- `ai_context_allowed`

Evidence Table still shows raw `metric_key` and module key for auditing.

## Readability

Dashboard cards clamp long hints to two lines.
Module Drawer keeps the full interpretation boundary readable.
Evidence Table uses horizontal scroll, compact rows, sticky headers, and Chinese labels for user-facing status/source/freshness fields.
