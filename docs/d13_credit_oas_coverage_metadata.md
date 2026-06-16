# DF-4c D13 Credit OAS Coverage / Provider-Rebuild Metadata

## Scope

DF-4c adds coverage and provider-rebuild diagnostics to existing D13
`historical_risk_percentile` rows. It is metadata integration only.

It does not add providers, run live fetches, write local history, relax the 3Y
gate, substitute `BAA10Y` for HY/IG OAS, change D13 percentile / z-score /
robust-z formulas, change D10/D11/D15/D19 trigger logic, add endpoints, add
frontend UI, add external AI, add search, or add persistence.

## Background

DF-4a confirmed that current local and current FRED availability for the two
primary OAS series is approximately three years:

| metric_key | series_id | local coverage | current provider coverage |
|---|---|---:|---:|
| `high_yield_spread` | `BAMLH0A0HYM2` | 1094 days | about 3 years |
| `investment_grade_spread` | `BAMLC0A0CM` | 1094 days | about 3 years |

The D13 fallback gate is exact: `365 * 3 = 1095` days. A 1094-day sample remains
blocked as `insufficient_history`.

`BAA10Y` has long provider history, but it is a separate credit-spread
proxy/reference. It cannot satisfy HY/IG OAS percentile requirements and cannot
upgrade old D19 event windows as primary HY/IG OAS coverage.

## New Metadata

DF-4c adds these fields to every D13 row and to `component_contributions`:

- `history_coverage_status`
- `provider_rebuild_status`
- `normalization_availability`
- `coverage_diagnostics`
- `credit_reference_role`
- `substitution_policy`
- `long_history_reference_status`

These fields also pass through `sanitized_d13_context`.

## HY/IG OAS Rules

For `high_yield_spread` and `investment_grade_spread`:

- `credit_reference_role=primary_oas_series`
- `substitution_policy=no_substitution`
- `provider_rebuild_status=provider_rebuild_limited`
- `long_history_reference_status=unavailable_for_primary_series`

When the local sample has 1094 coverage days:

- `status=insufficient_history`
- `history_quality_status=insufficient_history`
- `history_coverage_status=below_exact_gate`
- `coverage_diagnostics.required_days=1095`
- `coverage_diagnostics.days_short=1`
- `normalization_availability.current_level_available=True`
- percentile, z-score, and robust-z availability are all `False`
- `ai_context_allowed=False`
- `trigger_eligibility=not_eligible`

When the sample naturally reaches the exact existing 3Y gate, the existing D13
lookback rule sets `history_quality_status=limited_history`; DF-4c then reports
`history_coverage_status=limited_history`. No special 1094-day shortcut exists.

## BAA10Y Rules

`BAA10Y` policy is explicit and separate:

- `credit_reference_role=long_history_credit_proxy_reference`
- `provider_rebuild_status=reproducible_long_history`
- `substitution_policy=proxy_reference_not_oas_substitute`
- `long_history_reference_status=available_proxy_reference`

DF-4c does not add a D13 `BAA10Y` percentile row. The policy exists to prevent
accidental substitution and to support future documentation or reference-only
work.

## AI Context Boundary

Coverage metadata does not relax AI context rules.

Below-gate HY/IG OAS rows remain excluded from factual AI context even when the
latest current level is available. Metadata may explain why normalization is
blocked, but it does not create factual stress evidence, a hard trigger, or a
replacement for missing history.

## D19 Boundary

DF-4c does not upgrade historical validation windows. Current HY/IG OAS local
history starts too late for the older D19 windows, and `BAA10Y` remains only a
separate proxy/reference.

## Final Decision

D13 can now explain the important distinction between "current level exists"
and "historical normalization is unavailable." For current HY/IG OAS, provider
rebuild is limited, long-history primary OAS reference is unavailable, and the
3Y gate remains exact.
