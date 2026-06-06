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
- `unemployment_rate`: FRED `UNRATE`, monthly unemployment rate
- `initial_jobless_claims`: FRED `ICSA`, weekly initial claims

`ppi_final_demand` is intentionally `research_needed`. The pack does not guess a series id and does not treat `PPIACO` as final demand PPI.

## Dashboard Scope

Dashboard and Evidence Table rows are enabled for:

- `rate_pressure`: `dgs2`, `dgs30`
- `real_yield_pressure`: `dfii10`, `t10yie`
- `inflation_energy_pressure`: `core_cpi_yoy`, `core_pce_yoy`, `ppi_final_demand`

Labor metrics are surfaced as `labor_macro` Evidence Table rows for audit coverage. They are not added to the Dashboard homepage cards.

## Provenance Semantics

Rows with compact values use:

- `source=FRED`
- `source_badge=official`
- compact `observation_date` or `generated_at`
- compact `freshness_status`
- an `interpretation_hint` describing frequency and source boundaries

Missing rows stay blocked from AI factual context. They include a configured source label, `source_badge=missing`, a `missing_reason`, and an interpretation hint.

`ppi_final_demand` uses `source_badge=research_needed`, has no configured series id, and remains blocked.

## Boundaries

The official macro pack:

- does not call FRED, BLS, BEA, Treasury, yfinance, DeepSeek, Tavily, or search
- does not save raw provider responses
- does not save API keys, raw holdings, raw snapshots, or raw outputs
- does not mark proxy or search-derived rows as official
- does not provide trading advice

## Audit

`scripts/audit_data_pipeline_coverage.py` reports an `official_macro_pack` block with configured, available, and missing counts plus real-yield, core-inflation, labor, and PPI final-demand status fields.
