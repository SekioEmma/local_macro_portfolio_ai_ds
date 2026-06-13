# Historical Percentile Risk Metrics

`historical_risk_percentile` is a local-only derived evidence module. It reads
normalized observations from the ignored local `market_history` database and does
not fetch live data.

## First Metric Batch

- `high_yield_spread_percentile`
- `high_yield_spread_zscore`
- `investment_grade_spread_percentile`
- `investment_grade_spread_zscore`
- `vix_percentile`
- `vix_zscore`
- `dgs30_percentile`
- `dgs30_zscore`
- `dfii10_percentile`
- `dfii10_zscore`
- `sp500_drawdown_3m_percentile`
- `nasdaq100_drawdown_3m_percentile`
- `initial_claims_4w_avg_percentile`
- `continuing_claims_4w_avg_percentile`

## Window And Gates

The current implementation uses `all_available` local history with minimum
sample gates:

- daily or high-frequency series: 60 observations
- weekly claims series: 26 observations

If history is insufficient, the row is `insufficient_history`,
`ai_context_allowed=false`, and `missing_reason=insufficient_history_for_percentile`.

## Direction

- `higher_is_more_stress`: high percentiles indicate higher stress.
- `lower_is_more_stress`: low percentiles indicate higher stress.

Drawdown rows use `lower_is_more_stress` because more negative drawdown is worse.

## Boundary

Historical percentile is relative to available local history, not a forecast.
Z-score is a normalization statistic, not crash probability. Short history can
make percentile unstable. Different frequencies must not be mixed. Percentile
does not produce buy/sell instructions.
