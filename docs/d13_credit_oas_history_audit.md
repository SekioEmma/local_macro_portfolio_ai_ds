# D13 Credit OAS History Availability Audit

## Scope

This DF-4a audit checks how much high-yield and investment-grade credit OAS
history is available for D13 historical percentile use and D19 historical
validation reference use.

Target series:

| metric_key | FRED series |
|---|---|
| `high_yield_spread` | `BAMLH0A0HYM2` |
| `investment_grade_spread` | `BAMLC0A0CM` |
| optional comparison | `BAA10Y` |

The audit is read-only. It does not write SQLite, CSV, raw provider payloads,
API keys, endpoints, frontend UI, production D13 logic, or production D19
logic.

## Local market_history coverage

Source inspected: `data/market_history/market_history.sqlite3`

Compatible table detected: `market_observations`

| metric_key | series_id | local_start | local_end | local_count | distinct_dates | coverage_days | coverage_years | frequency_guess | gaps | duplicates | nulls | status |
|---|---|---:|---:|---:|---:|---:|---:|---|---:|---:|---:|---|
| `high_yield_spread` | `BAMLH0A0HYM2` | 2023-06-13 | 2026-06-11 | 788 | 787 | 1094 | 2.995 | daily market/business day | 0 gaps > 10 days | 1 duplicate date, max 2 rows | 0 | insufficient under exact 3Y gate |
| `investment_grade_spread` | `BAMLC0A0CM` | 2023-06-13 | 2026-06-11 | 786 | 786 | 1094 | 2.995 | daily market/business day | 0 gaps > 10 days | 0 | 0 | insufficient under exact 3Y gate |

Notes:

- Local HY/IG OAS coverage is approximately three years, but the exact span is
  1094 days. The current D13 fallback rule uses `365 * 3 = 1095` days, so both
  rows are one day below the exact 3Y rolling fallback gate as of this audit.
- Local coverage is not long history. It does not cover 2000, 2008, 2011,
  2015-16, 2018Q4, 2020, 2022, or the March-May 2023 bank-stress window.
- No abnormal null counts were found for the two target metrics.

## Current FRED provider availability

Probe method: FRED observations API from the current process environment
(`FRED_API_KEY` if already present). The script does not read `.env`. If no
process key is present, it falls back to the public FRED CSV endpoint.

Probe date: 2026-06-16

| series_id | provider_start_now | provider_end_now | provider_count_now | latest_date | latest_value | frequency_detected | query_method | provider note |
|---|---:|---:|---:|---:|---:|---|---|---|
| `BAMLH0A0HYM2` | 2023-06-16 | 2026-06-12 | 785 | 2026-06-12 | 2.71 | daily market/business day | `fred_api` | current availability appears limited to approximately 3 years |
| `BAMLC0A0CM` | 2023-06-16 | 2026-06-12 | 784 | 2026-06-12 | 0.74 | daily market/business day | `fred_api` | current availability appears limited to approximately 3 years |
| `BAA10Y` | 1986-01-02 | 2026-06-12 | 10112 | 2026-06-12 | 1.53 | daily market/business day | `fred_api` | current provider still returns long history |

Current FRED provider availability for the two primary HY/IG OAS series appears
limited to approximately 3 years. Do not treat the current provider as a
reproducible full-history source for these two OAS series.

`BAA10Y` remains a long-history comparison series, but it is a separate
credit-spread proxy/reference and should not be substituted silently for HY/IG
OAS.

## D13 eligibility

| metric_key | can_compute_3y_rolling | can_compute_5y_rolling | can_compute_10y_reference | can_compute_long_history_reference | recommended D13 status |
|---|---:|---:|---:|---:|---|
| `high_yield_spread` | false | false | false | false | `insufficient_history` under exact current gate |
| `investment_grade_spread` | false | false | false | false | `insufficient_history` under exact current gate |

Recommended metadata flags for DF-4 design:

- `local_reference_available`
- `provider_rebuild_limited`
- `below_exact_3y_gate`
- `long_history_reference_unavailable`

DF-4c implements these as D13 row metadata:

- `history_coverage_status=below_exact_gate` while HY/IG OAS coverage remains
  one day below the exact 3Y fallback gate.
- `provider_rebuild_status=provider_rebuild_limited` for both primary OAS
  series.
- `normalization_availability.current_level_available=True` while percentile,
  z-score, robust-z, and long-history reference availability remain false.
- `substitution_policy=no_substitution` and
  `long_history_reference_status=unavailable_for_primary_series` for both
  primary OAS series.

Recommended D13 decision:

- Keep production D13 on the existing fail-closed 5Y preferred / 3Y fallback
  policy.
- Do not claim long-history HY/IG OAS context.
- Treat HY/IG OAS as near-3Y / provider-limited evidence until the exact 3Y
  gate is satisfied in the local DB or a reproducible provider long-history
  source is restored.
- If DF-4 metadata is extended, expose the provider limitation explicitly
  rather than relaxing the percentile gate.

## D19 historical validation impact

| event window | credit coverage from local HY/IG OAS? |
|---|---:|
| 2000 dot-com / credit stress | false |
| 2008 global financial crisis | false |
| 2011 eurozone / US downgrade stress | false |
| 2015-16 oil / HY energy credit stress | false |
| 2018Q4 tightening scare | false |
| 2020 COVID liquidity shock | false |
| 2022 inflation / rates bear market | false |
| 2023 regional-bank stress window | false |

The current local HY/IG OAS history does not upgrade these D19 historical
validation windows with credit coverage. It starts after the listed 2023 event
window and cannot support older windows.

Recommended D19 decision:

- Use current local HY/IG OAS only as local historical reference for periods it
  actually covers.
- Do not use the local ignored DB as a production trigger source.
- Keep missing historical credit coverage visible for older event windows.
- `BAA10Y` can be documented as a separate optional reference/proxy, but it
  should not be merged into HY/IG OAS coverage.

## License and reproducibility boundary

- Current FRED can rebuild only approximately three years for
  `BAMLH0A0HYM2` and `BAMLC0A0CM` in this environment.
- Current FRED can still rebuild long history for `BAA10Y`, but that is not the
  same as HY/IG OAS.
- If a local ignored DB ever contains longer HY/IG OAS history, it should remain
  local-only historical reference unless the provider/reuse boundary is
  explicitly cleared.
- Do not commit or redistribute raw SQLite, raw CSV, raw provider payloads, or
  full historical series.
- It is acceptable to commit this coverage summary.

## Recommended project decision

This audit matches Case 2 for the two primary HY/IG OAS series: local history
and current FRED availability are both approximately three years, not long
history. Under the exact current D13 gate they are still just below 3Y as of
2026-06-16.

Project decision:

- `high_yield_spread` and `investment_grade_spread` should remain
  `insufficient_history` until the exact D13 3Y gate is met.
- Do not claim 5Y, 10Y, or long-history HY/IG OAS context.
- Do not use HY/IG OAS local history to upgrade old D19 event windows.
- Add or preserve metadata that says current provider rebuild is limited and
  local reference is available only for the covered local window.
- Raw data must not be committed or redistributed.
