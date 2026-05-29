# Data Source Redundancy Notes

## Stage 8.3 Phase 1 Production Fallbacks

- Market index fallback: S&P 500 and NASDAQ Composite remain FRED-primary. If FRED is unavailable, yfinance may provide an unofficial market quote fallback. This is not an official macro/statistical source and must be marked `source_tier=unofficial_fallback`.
- Treasury yield fallback: DGS2, DGS10, and DGS30 remain FRED-primary. If FRED is unavailable, U.S. Treasury Daily Treasury Par Yield Curve Rates may provide an official fallback for nominal 2-year, 10-year, and 30-year yields. These are Treasury par yield curve rates, not FRED DGS series, and must not be reported as `series_id=DGS*`.

## BLS Official Fallbacks

BLS is an official fallback for selected monthly macro series when FRED is unavailable. It must not be reported as FRED data.

- FRED `CPIAUCSL`: verified candidate BLS CPI-U all items, U.S. city average, seasonally adjusted series ID `CUSR0000SA0`.
- FRED `CPILFESL`: verified candidate BLS CPI-U all items less food and energy, U.S. city average, seasonally adjusted series ID `CUSR0000SA0L1E`.
- FRED `PAYEMS`: verified candidate BLS Current Employment Statistics total nonfarm all employees, seasonally adjusted series ID `CES0000000001`; value unit is thousands of persons.
- BLS API observations use monthly periods such as `M04`; convert them to `YYYY-MM-01`. Do not use `M13` annual-average values as monthly observations.
- Remaining follow-up before broadening BLS use: monitor revision behavior and confirm any edge-case definition differences from the FRED transformed series.

References:
- BLS CPI series ID structure: https://www.bls.gov/cpi/factsheets/cpi-series-ids.htm
- BLS Public Data API: https://www.bls.gov/developers/
- BLS API signature examples include `CUSR0000SA0`, `CUSR0000SA0L1E`, and `CES0000000001`: https://www.bls.gov/developers/api_signature_v2.htm

## BEA Official Fallbacks

BEA is an official fallback for selected PCE price-index series when FRED is unavailable. Do not add `beaapi` as a dependency.

- Env name: `BEA_API_KEY`; provider must return a non-throwing unavailable/error status when the key is absent.
- FRED `PCEPI`: verified BEA NIPA fallback uses dataset `NIPA`, table `T20804`, line `1`, frequency `M`, line description `Personal consumption expenditures (PCE)`, metric `Fisher Price Index`, unit `Level`.
- FRED `PCEPILFE`: verified BEA NIPA fallback uses dataset `NIPA`, table `T20804`, line `25`, frequency `M`, line description `PCE excluding food and energy`, metric `Fisher Price Index`, unit `Level`.
- BEA `TimePeriod` values such as `2026M04` convert to `YYYY-MM-01`.
- Label BEA output as BEA official fallback, not FRED.
- Remaining follow-up: monitor revision behavior and confirm whether any downstream wording should explicitly mention BEA's Fisher price-index wording versus FRED's series labels.

References:
- BEA API overview: https://apps.bea.gov/api/signup/
- BEA open data/API description: https://www.bea.gov/open-data
- BEA core PCE FAQ: https://www.bea.gov/index.php/help/faq/518

## FedFunds Research Only

- FRED `FEDFUNDS` is a monthly effective federal funds rate series.
- NY Fed Markets Data API provides an official daily Effective Federal Funds Rate (`EFFR`) endpoint with `effectiveDate` and `percentRate`.
- Phase 4 production fallback: if FRED `FEDFUNDS` is unavailable, use NY Fed daily `EFFR` only as a different-frequency official fallback.
- Label NY Fed fallback output as `source_tier=official_fallback`, `frequency=daily`, `primary_source=FRED:FEDFUNDS`, and `fallback_series=NY Fed EFFR daily`.
- Definition note must state: daily effective federal funds rate; not monthly FRED `FEDFUNDS` average.
- Do not use yfinance or any non-official market source as a FedFunds replacement.
- Do not use Treasury yields, SOFR, fed funds futures, market rates, or policy target-range values as substitutes for effective fed funds. A target range may only be modeled later as a distinct metric, not as `FEDFUNDS`.

References:
- New York Fed EFFR overview: https://www.newyorkfed.org/markets/reference-rates/effr
- New York Fed Markets Data APIs: https://markets.newyorkfed.org/static/docs/markets-api.html
- FRED `FEDFUNDS`: https://fred.stlouisfed.org/series/FEDFUNDS

## Treasury Reference

- Treasury Daily Treasury Par Yield Curve Rates page and XML feed: https://home.treasury.gov/resource-center/data-chart-center/interest-rates/TextView?type=daily_treasury_yield_curve
- Treasury methodology note: par yield curve rates are interpolated from Treasury's daily par yield curve and are commonly referred to as CMTs; this fallback still must be labeled as Treasury data, not FRED DGS.
