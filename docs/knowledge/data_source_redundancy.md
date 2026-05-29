# Data Source Redundancy Notes

## Stage 8.3 Phase 1 Production Fallbacks

- Market index fallback: S&P 500 and NASDAQ Composite remain FRED-primary. If FRED is unavailable, yfinance may provide an unofficial market quote fallback. This is not an official macro/statistical source and must be marked `source_tier=unofficial_fallback`.
- Treasury yield fallback: DGS2, DGS10, and DGS30 remain FRED-primary. If FRED is unavailable, U.S. Treasury Daily Treasury Par Yield Curve Rates may provide an official fallback for nominal 2-year, 10-year, and 30-year yields. These are Treasury par yield curve rates, not FRED DGS series, and must not be reported as `series_id=DGS*`.

## BLS Research Only

Do not connect BLS to the production market data path in this phase.

- FRED `CPIAUCSL`: candidate BLS CPI-U all items, U.S. city average, seasonally adjusted series ID `CUSR0000SA0`.
- FRED `CPILFESL`: candidate BLS CPI-U all items less food and energy, U.S. city average, seasonally adjusted series ID `CUSR0000SA0L1E`.
- FRED `PAYEMS`: candidate BLS Current Employment Statistics total nonfarm all employees, seasonally adjusted series ID `CES0000000001`.
- Required follow-up: verify seasonal adjustment, units, frequency, revision behavior, and any definition differences from FRED before production use.

References:
- BLS CPI series ID structure: https://www.bls.gov/cpi/factsheets/cpi-series-ids.htm
- BLS Public Data API: https://www.bls.gov/developers/
- BLS API signature examples include `CUSR0000SA0`, `CUSR0000SA0L1E`, and `CES0000000001`: https://www.bls.gov/developers/api_signature_v2.htm

## BEA Research Only

Do not connect BEA to the production market data path in this phase. Do not add `beaapi` as a dependency.

- Future env name: `BEA_API_KEY`.
- FRED `PCEPI` and `PCEPILFE` likely map to BEA NIPA PCE price index tables. BEA notes all PCE prices appear in NIPA Table 2.3.4; third-party metadata also points monthly PCE price index work toward NIPA Table 2.8.4.
- Required follow-up: confirm BEA dataset, `TableName` or `TableID`, `LineNumber`, frequency, unit, seasonal adjustment, and revision behavior before production use.

References:
- BEA API overview: https://apps.bea.gov/api/signup/
- BEA open data/API description: https://www.bea.gov/open-data
- BEA core PCE FAQ: https://www.bea.gov/index.php/help/faq/518

## Treasury Reference

- Treasury Daily Treasury Par Yield Curve Rates page and XML feed: https://home.treasury.gov/resource-center/data-chart-center/interest-rates/TextView?type=daily_treasury_yield_curve
- Treasury methodology note: par yield curve rates are interpolated from Treasury's daily par yield curve and are commonly referred to as CMTs; this fallback still must be labeled as Treasury data, not FRED DGS.
