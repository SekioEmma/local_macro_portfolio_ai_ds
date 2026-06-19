# Data Foundation G2/G3 Source Supplementation

## Status

Completed on `app-mvp` without merging, cherry-picking, or modifying
`ai-1-local-research-preview`.

This round adds source adapters and source-policy gates. It does not turn the
project into a real-time terminal and does not add forecasts, event
probabilities, trading signals, target allocations, or portfolio actions.

## Added

### Central source policy

`src/data_providers/source_registry.py` defines the provider contracts and
source classes used by this round:

| Provider | Source badge | Trigger eligibility | Role |
|---|---|---|---|
| FRED | `official_fallback` | `eligible` | official-series mirror/fallback |
| BLS | `official` | `eligible` | first-party CPI |
| BEA | `official` | `eligible` | first-party NIPA PCE/GDP |
| Alpha Vantage | `commercial_api_fallback` | `support_only` | ETF/market proxy |
| EIA | `dataset_official` | `eligible` | controlled official datasets |
| OFR | `official_reference` | `reference_only` | external stress reference |
| GDELT Cloud | `research_context` | `research_context_only` | aggregate research context |

Every new observation or research bucket carries provider, source identity,
source badge, source series/dataset identifier, retrieval method, freshness
policy, AI-context policy, trigger eligibility, interpretation boundary,
ingest time, and a deterministic payload/file hash where applicable.

Raw provider payload persistence defaults to false.

### FRED rates and inflation expectations

`scripts/ingest_official_rates_history.py` supports `DGS2`, `DGS10`, `DGS30`,
`T10Y2Y`, `T10YIE`, and `DFII10`, mapped to their lowercase metric keys.
The rows use the existing market-history SQLite store.

### BLS CPI v1

`scripts/ingest_official_bls_cpi_history.py` uses the public BLS v1 endpoint
without a registration key. It uses safe ten-year chunks and supports:

- `CUSR0000SA0`: headline CPI index and `headline_cpi_yoy`
- `CUSR0000SA0L1E`: core CPI index and `core_cpi_yoy`

The response series identifier is always checked. If the API supplies a series
title, expected title tokens are checked. The production mapping is restricted
to the two confirmed identifiers instead of accepting arbitrary series.

### BEA NIPA

- `scripts/discover_bea_nipa_tables.py` discovers official NIPA metadata.
- `scripts/ingest_official_bea_nipa_history.py` ingests confirmed mappings.

Confirmed mappings:

- NIPA `T20804`, line `1`: `headline_pce_yoy`
- NIPA `T20804`, line `25`: `core_pce_yoy`
- NIPA `T10101`, line `1`: `real_gdp_qoq_saaar`

Table, line, frequency, and line-description metadata are validated.

### Alpha Vantage market proxies

`scripts/ingest_alpha_vantage_market_proxy_history.py` supports SPY, QQQ, RSP,
TLT, GLD, HYG, LQD, and SHY.

These observations are support-only commercial fallbacks. ETF proxies cannot
replace true breadth, official macro observations, HY OAS, or IG OAS.

### EIA controlled datasets

`scripts/ingest_eia_controlled_dataset.py` accepts a local CSV file or a
controlled download from an `eia.gov` host. First-scope datasets are WTI spot,
Brent spot, and retail gasoline.

The adapter preserves dataset location, last-modified/release metadata, file
hash, retrieval method, and ingest time. It does not create oil forecasts or
trading signals.

### OFR Financial Stress Index

- `scripts/discover_ofr_fsi_download_url.py` discovers the official download.
- `scripts/ingest_ofr_fsi_download.py` parses the official CSV.

Confirmed endpoint:

`https://www.financialresearch.gov/financial-stress-index/data/fsi.csv`

Total FSI, five category contributions, and three regional contributions are
reference-only observations. OFR FSI does not replace internal D10 or D11.

### GDELT aggregate research context

GDELT uses a dedicated research-context SQLite store, not the financial
market-history fact table.

Added:

- event and story aggregate bucket schemas
- configured query presets
- 30-day explicit-window guard
- bearer-token loading from `GDELT_CLOUD_API_KEY`
- deterministic raw response hash
- strict no-article-body persistence

GDELT is excluded from `included_facts` and core model triggers. It may only be
used later as an explicitly separated `included_research_context` layer.

## Run Commands

All network scripts require explicit `--live`; database writes require
explicit `--write`.

```bash
python scripts/audit_source_registry.py
python scripts/ingest_official_rates_history.py --live --dry-run
python scripts/ingest_official_bls_cpi_history.py --live --dry-run
python scripts/discover_bea_nipa_tables.py --live
python scripts/ingest_official_bea_nipa_history.py --live --dry-run
python scripts/ingest_alpha_vantage_market_proxy_history.py --live --dry-run --symbols SPY
python scripts/ingest_eia_controlled_dataset.py --dataset wti_spot --file PATH.csv --dry-run
python scripts/discover_ofr_fsi_download_url.py --live
python scripts/ingest_ofr_fsi_download.py --dry-run
python scripts/audit_research_context_boundaries.py
python scripts/ingest_gdelt_event_summary.py --preset global_conflict_pressure --live --dry-run
python scripts/ingest_gdelt_story_summary.py --preset middle_east_energy_risk --live --dry-run
```

Add `--write` and optionally `--db-path` only after reviewing a dry-run.

## Environment Variables

| Variable | Required for |
|---|---|
| `FRED_API_KEY` | FRED rates/breakeven history |
| `BEA_API_KEY` | BEA NIPA discovery and history |
| `ALPHA_VANTAGE_API_KEY` | Alpha Vantage proxy history |
| `GDELT_CLOUD_API_KEY` | GDELT Cloud event/story summaries |

BLS v1, local/official EIA files, and OFR FSI do not require API keys.

`GDELT_CLOUD_API_KEY` was not configured during closeout, so GDELT live
ingestion was validated through mocked aggregate responses and an explicit
`not_available` runtime result.

## Intentionally Untracked Outputs

- `data/market_history/*.sqlite3`
- `data/research_context/*.sqlite3`
- `data/eia/*`
- discovery/report output under `outputs/reports/`
- raw downloaded datasets and provider payload dumps
- `.env` and all credentials

## Deliberately Not Added

- Cboe paid historical volatility integration
- SEC EDGAR advanced fundamentals
- true historical breadth/constituent coverage
- FactSet/LSEG/Bloomberg/S&P Capital IQ forward P/E and earnings revisions
- FedWatch integration
- arbitrary news search or full article storage
- GDELT-driven stress, regime, probability, allocation, or trading outputs
- Alpha Vantage economic endpoints as primary macro sources

## Validation

Preflight full suite before changes:

- `1563 passed`
- 2 pre-existing failures:
  - frontend launcher dependency check because the isolated worktree has no
    `app_frontend/node_modules`
  - existing golden audit assertion for D15 included model output count

Final validation:

- targeted provider/dashboard/schema/storage/boundary suite:
  `71 passed, 1 warning`
- full suite: `1610 passed, 2 failed, 1 warning`
- failure set is unchanged from preflight:
  - missing frontend `node_modules` in the isolated worktree
  - pre-existing D15 golden-audit included-output assertion
- `python scripts/audit_source_registry.py`: `status=ok`
- `python scripts/audit_research_context_boundaries.py`: `status=ok`
- `git diff --check`: passed

Live read-only dry-runs successfully validated BLS CPI, BEA NIPA, Alpha
Vantage SPY, and OFR FSI. EIA was validated with controlled fixtures because
no source file was supplied. GDELT remained `not_available` because its API key
was not configured.
