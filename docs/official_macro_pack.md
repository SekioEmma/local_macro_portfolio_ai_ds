# Official Macro Pack Foundation

The official macro pack is a local metadata foundation for a small set of audited macro indicators used by Dashboard evidence rows and the data coverage audit. It does not call live providers, does not write provider responses, and does not change yfinance history ingestion.

## Metrics

The initial configured metrics are:

- `dgs2`: FRED `DGS2`, daily 2-year Treasury constant maturity yield
- `dgs30`: FRED `DGS30`, daily 30-year Treasury constant maturity yield
- `dfii10`: FRED `DFII10`, daily 10-year TIPS real yield
- `t10yie`: FRED `T10YIE`, daily 10-year breakeven inflation
- `core_cpi_yoy`: FRED `CPILFESL` compact Core CPI YoY observation
- `core_pce_yoy`: FRED `PCEPILFE` compact Core PCE YoY observation
- `ppiaco_yoy`: FRED `PPIACO` all commodities PPI YoY observation, not final demand PPI
- `ppi_final_demand`: FRED `PPIFIS`, monthly headline PPI Final Demand index, official FRED relay of BLS PPI data
- `ppi_final_demand_yoy`: derived from `PPIFIS` index history only when at least 13 monthly observations are available
- `unemployment_rate`: FRED `UNRATE`, monthly unemployment rate
- `initial_jobless_claims`: FRED `ICSA`, weekly initial claims
- `nonfarm_payrolls`: FRED `PAYEMS`, monthly nonfarm payroll employment level
- `continuing_claims`: FRED `CCSA`, weekly continuing claims

`PPIFIS` was selected after source research against the FRED series page for "Producer Price Index by Commodity: Final Demand". `PPIACO` remains a separate all-commodities PPI series and must not be used to fill PPI Final Demand.

`scripts/ingest_official_ppifis_history.py` can ingest FRED `PPIFIS` observations
into local `market_history` when run with `--live --write`. Its default
`--dry-run` path does not fetch or write. Stored rows use `source=FRED`,
`source_badge=official`, `source_series=PPIFIS`, `metric_kind=raw`, and
`freshness_status=historical`.

`scripts/ingest_official_labor_history.py` can ingest official FRED labor
history for `UNRATE`, `ICSA`, `PAYEMS`, and `CCSA` into local `market_history`
when run with `--live --write`. Its default `--dry-run` path does not fetch or
write. Default limits are 24 monthly observations for `UNRATE`/`PAYEMS` and 52
weekly observations for `ICSA`/`CCSA`. Stored rows are normalized observations
only and use `source=FRED`, `source_badge=official`, `provider=FRED`,
`metric_kind=raw`, and `freshness_status=historical`.

## Dashboard Scope

Dashboard and Evidence Table rows are enabled for:

- `rate_pressure`: `dgs2`, `dgs30`
- `real_yield_pressure`: `dfii10`, `t10yie`
- `inflation_energy_pressure`: `core_cpi_yoy`, `core_pce_yoy`, `ppiaco_yoy`, `ppi_final_demand`, `ppi_final_demand_yoy`

Labor metrics are surfaced as `labor_macro` Evidence Table rows for audit coverage. They include `UNRATE`, `ICSA`, `PAYEMS`, and `CCSA` official rows plus local derived labor context when history is sufficient. They are not added to the Dashboard homepage cards.

## Provenance Semantics

Rows with compact values use:

- `source=FRED`
- `source_badge=official`
- compact `observation_date` or `generated_at`
- compact `freshness_status`
- an `interpretation_hint` describing frequency and source boundaries

Missing rows stay blocked from AI factual context. They include a configured source label, `source_badge=missing`, a `missing_reason`, and an interpretation hint.

Labor rows remain source-bound:

- official labor rows require FRED source metadata and source series
- unemployment and claims derived rows use `source_badge=derived`
- Sahm proxy status is a recession-warning proxy, not an official recession fact
- labor deterioration status is macro context only; it is not a recession prediction, crisis confirmation, or trading signal

`ppi_final_demand` can enter AI factual context only when the row has a value, `source`/`source_badge`, `source_series=PPIFIS`, `observation_date`, `generated_at`, non-stale freshness, and an interpretation hint. `ppi_final_demand_yoy` is blocked as `insufficient_history` unless it is explicitly provided as a YoY compact metric or derived from enough official `PPIFIS` index history.

PPI Final Demand hints must state:

- PPIFIS is headline final demand PPI relayed by FRED from official BLS PPI data
- PPIFIS is distinct from PPIACO
- PPI is monthly/low-frequency data, not a real-time inflation signal
- without consensus data, the row cannot support "above expectations" or "below expectations" claims

## Boundaries

The official macro pack:

- does not call FRED, BLS, BEA, Treasury, yfinance, DeepSeek, Tavily, or search
- does not save raw provider responses
- does not save API keys, raw holdings, raw snapshots, or raw outputs
- does not mark proxy or search-derived rows as official
- does not provide trading advice

## Audit

`scripts/audit_data_pipeline_coverage.py` reports an `official_macro_pack` block with configured, available, and missing counts plus real-yield, core-inflation, labor, and PPI final-demand availability/status fields. It also reports a `valuation_research` block so valuation gaps stay explicit while PPI Final Demand is handled separately.
