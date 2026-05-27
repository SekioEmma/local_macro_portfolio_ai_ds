# Financial Data Package

This document defines abstract, non-private fields used to enrich local analyst memo context. It must not contain account snapshots, API keys, generated answers, or time-sensitive output values.

## Financial Conditions Fields

Each item should be structured with:

- key
- name
- value
- unit
- observation_date
- source
- source_tier
- freshness
- status
- error
- interpretation_hint
- risk_relevance

## Configured FRED Fields

The following fields are configured through `configs/data_sources.yaml` and fetched through the local FRED provider:

| Key | FRED series | Unit | Purpose |
| --- | --- | --- | --- |
| high_yield_spread | BAMLH0A0HYM2 | percent | Credit-stress context for distinguishing normal pullbacks from credit pressure. |
| vix | VIXCLS | index | Volatility-stress context, not a standalone trading signal. |
| real_yield_10y | DFII10 | percent | Discount-rate and gold opportunity-cost context. |
| breakeven_inflation_10y | T10YIE | percent | Market-implied inflation-expectation context. |
| yield_curve_10y2y | T10Y2Y | percentage_points | Yield-curve and recession-pressure context, not a standalone recession call. |

## DeepSeek Rates, Inflation, and Oil Package

The `market_data_package` is designed for DeepSeek Pro analyst memo context. Each item uses the same audited field shape as financial conditions: `key`, `name`, `value`, `unit`, `observation_date`, `source`, `source_tier`, `freshness`, `status`, `error`, `interpretation_hint`, and `risk_relevance`.

| Key | FRED series / derivation | Unit | Boundary |
| --- | --- | --- | --- |
| nominal_yield_2y | DGS2 | percent | Daily FRED constant maturity yield. |
| nominal_yield_10y | DGS10 | percent | Daily FRED constant maturity yield, not intraday high. |
| nominal_yield_30y | DGS30 | percent | Daily FRED constant maturity yield, not intraday high. |
| dgs10_30d_high | max DGS10 over 30 calendar days | percent | Recent daily high, not intraday high. |
| dgs10_60d_high | max DGS10 over 60 calendar days | percent | Recent daily high, not intraday high. |
| dgs30_30d_high | max DGS30 over 30 calendar days | percent | Recent daily high, not intraday high. |
| dgs30_60d_high | max DGS30 over 60 calendar days | percent | Recent daily high, not intraday high. |
| dgs10_distance_to_5pct | latest DGS10 - 5.0 | percentage_points | Positive means above 5%; negative means below 5%. |
| dgs30_distance_to_5pct | latest DGS30 - 5.0 | percentage_points | Positive means above 5%; negative means below 5%. |
| dgs10_above_5pct | latest DGS10 >= 5.0 | boolean | Daily observation threshold only. |
| dgs30_above_5pct | latest DGS30 >= 5.0 | boolean | Daily observation threshold only. |
| dgs10_above_5pct_days_5d | count of latest 5 available DGS10 observations >= 5.0 | count | Daily observations only; not intraday confirmation. |
| dgs30_above_5pct_days_5d | count of latest 5 available DGS30 observations >= 5.0 | count | Daily observations only; not intraday confirmation. |
| dgs10_5d_avg | average of latest 5 available DGS10 observations | percent | Daily average; not intraday high. |
| dgs30_5d_avg | average of latest 5 available DGS30 observations | percent | Daily average; not intraday high. |
| dgs10_5pct_breakout_confirmed | derived threshold confirmation | boolean | True only under the project threshold rule; false means do not write confirmed breakout. |
| dgs30_5pct_breakout_confirmed | derived threshold confirmation | boolean | True only under the project threshold rule; false means do not write confirmed breakout. |
| headline_cpi | CPIAUCSL | index | Monthly index; no consensus surprise data. |
| core_cpi | CPILFESL | index | Monthly index; no consensus surprise data. |
| headline_pce | PCEPI | index | Monthly index; no consensus surprise data. |
| core_pce | PCEPILFE | index | Monthly index; no consensus surprise data. |
| ppi_all_commodities | PPIACO | index | All commodities PPI, not final demand PPI. |
| ppi_final_demand | research_needed | index | Do not guess the series id. |
| headline_cpi_mom_pct / headline_cpi_yoy_pct | derived from CPIAUCSL | percent | Allows MoM/YoY inflation discussion; not consensus surprise. |
| core_cpi_mom_pct / core_cpi_yoy_pct | derived from CPILFESL | percent | Allows MoM/YoY inflation discussion; not consensus surprise. |
| headline_pce_mom_pct / headline_pce_yoy_pct | derived from PCEPI | percent | Allows MoM/YoY inflation discussion; not consensus surprise. |
| core_pce_mom_pct / core_pce_yoy_pct | derived from PCEPILFE | percent | Allows MoM/YoY inflation discussion; not consensus surprise. |
| ppi_all_commodities_mom_pct / ppi_all_commodities_yoy_pct | derived from PPIACO | percent | All commodities PPI change only; not final demand PPI and not consensus surprise. |
| wti_oil | DCOILWTICO | USD per barrel | Daily WTI oil price. |
| brent_oil | DCOILBRENTEU | USD per barrel | Daily Brent oil price. |
| wti_oil_30d_change | derived from DCOILWTICO | percent | Uses nearest available daily observation around 30 days ago. |
| brent_oil_30d_change | derived from DCOILBRENTEU | percent | Uses nearest available daily observation around 30 days ago. |

## DeepSeek Market Analysis Framework

DeepSeek Pro should analyze market state in this order:

1. Credit and financial stress: check credit spread and VIX before calling a pullback a crisis.
2. Nominal and real rates: separate nominal yield pressure, real yield pressure, and yield-curve structure.
3. Inflation and oil: use CPI/PCE/PPI/oil and breakeven inflation without claiming consensus surprise.
4. Valuation and earnings boundary: if valuation or earnings data are missing, do not invent PE or forward PE.
5. Market structure boundary: if breadth and concentration data are missing, do not confirm AI or mega-cap concentration deterioration.
6. Portfolio observation: use relative target deviation, risk exposure, DCA evaluation, threshold review, year-end review, and rebalancing evaluation; do not issue trade instructions.

## Explicitly Unavailable Fields

The following fields are included as structured limitations when no stable configured source is available:

| Key | Status | Boundary |
| --- | --- | --- |
| valuation_proxy | not_available | Do not infer PE, forward PE, CAPE, earnings yield, or valuation percentiles. |
| fedwatch_probability | not_available | Do not infer FedWatch or market-implied rate-probability values. |
| forward_pe | not_available | Do not infer forward PE. |
| cape | research_needed | Do not infer CAPE until a stable source is configured. |
| earnings_revision | not_available | Do not infer earnings revisions. |
| market_breadth | research_needed | Do not infer breadth deterioration. |
| equal_weight_vs_cap_weight | research_needed | Do not infer equal-weight versus cap-weight divergence. |
| mega_cap_concentration | research_needed | Do not infer mega-cap concentration deterioration. |
| intraday_treasury_high | not_available | FRED DGS series are daily observations, not intraday highs. |
| consensus_cpi | not_available | Do not claim CPI was above or below consensus. |
| consensus_ppi | not_available | Do not claim PPI was above or below consensus. |

## Interpretation Boundaries

- Credit spread helps distinguish normal pullback from credit stress, but is not a standalone crisis signal.
- VIX indicates volatility stress, not long-term return forecast.
- Real yield affects growth equity and gold through discount-rate and opportunity-cost channels.
- Missing valuation data must not be inferred by the model.
- Missing FedWatch probability must not be inferred by the model.
- Evidence tables should include exact `metric_key` values for market metrics used in the memo.
- FRED DGS fields are daily constant maturity yields; they cannot be used as real intraday highs.
- If oil data is stale, describe it as data available as of its observation date and do not call it current real-time oil pressure.
- Missing consensus CPI/PPI, valuation, FedWatch, market breadth, mega-cap concentration, and intraday Treasury data must be stated as boundaries rather than inferred.
