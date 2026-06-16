# Historical Percentile Risk Metrics

`historical_risk_percentile` is a local-only derived evidence module. It reads
normalized observations from the ignored local `market_history` database and
does not fetch live data.

## Metric Batch

- `high_yield_spread_percentile`, `high_yield_spread_zscore`, `high_yield_spread_robust_zscore`
- `investment_grade_spread_percentile`, `investment_grade_spread_zscore`, `investment_grade_spread_robust_zscore`
- `vix_percentile`, `vix_zscore`, `vix_robust_zscore`
- `dgs30_percentile`, `dgs30_zscore`, `dgs30_robust_zscore`
- `dfii10_percentile`, `dfii10_zscore`, `dfii10_robust_zscore`
- `sp500_drawdown_3m_percentile`, `sp500_drawdown_3m_robust_zscore`
- `nasdaq100_drawdown_3m_percentile`, `nasdaq100_drawdown_3m_robust_zscore`
- `initial_claims_4w_avg_percentile`, `initial_claims_4w_avg_robust_zscore`
- `continuing_claims_4w_avg_percentile`, `continuing_claims_4w_avg_robust_zscore`

## Windows And Gates

The MVP window rule is:

- preferred: `5Y rolling`
- fallback: `3Y rolling limited_history`
- below 3Y: `all_available_limited` with `status=insufficient_history`

Rows also require the configured minimum observation count. Daily or market-like
series require at least 60 observations. Weekly labor-derived series require at
least 26 observations.

`all_available` is not treated as the default formal window. It is only exposed
as `all_available_limited` when history is too short to compute a trusted row.

## Bands

For `higher_is_more_stress` metrics:

- `normal`: percentile below 60
- `elevated`: 60 to below 80
- `high`: 80 to 90
- `extreme`: above 90

For `lower_is_more_stress` metrics:

- `normal`: percentile 40 or above
- `elevated`: 20 to below 40
- `high`: 10 to below 20
- `extreme`: below 10

Drawdown rows use `lower_is_more_stress`; more negative drawdown is interpreted
as greater damage or severity.

## Robust Z-Score

Robust z-score is calculated as:

```text
robust_z = 0.6745 * (current - median) / MAD
```

If MAD is zero or history is insufficient, the robust z-score row is blocked
with `status=not_available` or `status=insufficient_history`. Robust z-score is
a normalization statistic, not probability.

## AI Context And Eligibility

D13 rows can enter AI factual context only when source metadata, date metadata,
freshness, status, lookback window, observation count, band, and interpretation
boundary are all present. Eligible rows prefer band fields over pseudo-precise
decimal interpretation.

`trigger_eligibility` is descriptive only:

- `hard_trigger_allowed`: official or official fallback source with sufficient history
- `auxiliary_only`: unofficial fallback or derived source
- `proxy_auxiliary_only`: proxy source
- `not_eligible`: missing, stale, insufficient, or otherwise blocked

D13 does not change D10 financial stress score or D11 pullback classification.
A later D13c step may use these bands as auxiliary evidence.

## Reliability And Divergence Metadata

D13 rows also carry DF-4 reliability / divergence metadata:

- `reliability_band`: `high` / `medium` / `low` / `insufficient`, derived from
  history quality, latest input source badge, method availability, and
  divergence. It is data and method quality, not probability.
- `divergence_band`: `none` / `mild` / `material` / `not_available`. It flags
  disagreement among percentile, z-score, and robust z-score, not market
  direction. Material divergence should be explained, not traded.
- `method_agreement`: categorical summary across available methods.
- `normalization_methods_available`: which methods produced a band.
- `percentile_zscore_alignment`, `percentile_robust_zscore_alignment`,
  `zscore_robust_zscore_alignment`: pairwise alignment labels.
- `reliability_drivers`: sorted list of reason tags.
- `source_quality_note` and `history_window_note`: human-readable summaries.

`reliability_band=high` is descriptive only. It does not promote a row to a
new hard trigger, change `trigger_eligibility`, or relax `ai_context_allowed`.

See `docs/d13_reliability_divergence_metadata.md` for the full DF-4 design.

## Credit OAS Coverage Metadata

DF-4c adds credit OAS coverage and provider-rebuild metadata to D13 rows:

- `history_coverage_status`
- `provider_rebuild_status`
- `normalization_availability`
- `coverage_diagnostics`
- `credit_reference_role`
- `substitution_policy`
- `long_history_reference_status`

For `high_yield_spread` and `investment_grade_spread`, the current audited
provider rebuild status is `provider_rebuild_limited`. When the local sample is
1094 days, D13 remains fail-closed with
`history_coverage_status=below_exact_gate`; the exact 3Y fallback gate remains
1095 days.

`normalization_availability.current_level_available=True` means the latest
level can be present in local history. It does not mean percentile, z-score, or
robust-z normalization is available. Below-gate rows remain excluded from AI
factual context.

`BAA10Y` is a long-history credit proxy/reference only. It is not substituted
for HY/IG OAS and does not satisfy their percentile requirements.

## Boundary

Historical percentile is relative to available local history, not a forecast.
Z-score and robust z-score are normalization statistics, not crash probability.
Short or limited history can make percentile unstable. Different frequencies
must not be mixed. Percentile bands do not produce buy/sell instructions. Proxy
inputs are auxiliary and cannot be hard triggers. Reliability and divergence
metadata are explanatory model-quality context; they do not authorize
probability, forecast, allocation, or trading interpretation.
