# Core Risk History Backfill

`scripts/ingest_core_risk_history.py` is the D13 history orchestration script. It
plans and, only when explicitly allowed, backfills the first core risk history
batch into the ignored local `data/market_history/*.sqlite3` store.

## Safety Defaults

Default dry-run:

```bash
python scripts/ingest_core_risk_history.py --dry-run
```

Dry-run does not fetch providers and does not write SQLite. It reports planned
official series, planned yfinance/proxy series, derived materialization targets,
missing source mappings, and the flags required for live/write.

Live write:

```bash
python scripts/ingest_core_risk_history.py --live --write
```

Only `--live --write` writes normalized observations to the local ignored
market-history database. Raw provider payloads are not persisted.

## Raw History Mappings

Official or official-like FRED mappings are loaded from `configs/data_sources.yaml`:

- `dgs30`: FRED `DGS30`, `source_badge=official`
- `dfii10`: FRED `DFII10`, `source_badge=official`
- `high_yield_spread`: FRED `BAMLH0A0HYM2`, `source_badge=official_fallback`
- `investment_grade_spread`: FRED `BAMLC0A0CM`, `source_badge=official_fallback`
- `vix`: FRED `VIXCLS`, `source_badge=official_fallback`
- `initial_jobless_claims`: FRED `ICSA`, `source_badge=official`
- `continuing_claims`: FRED `CCSA`, `source_badge=official`

Yfinance mappings are loaded from `configs/yfinance_history.yaml` and remain
`unofficial_fallback` or `proxy`; they are never promoted to official.

## Derived Materialization

The script can materialize these derived rows from local raw history:

- `sp500_drawdown_3m`: rolling 90-day drawdown from `sp500`
- `nasdaq100_drawdown_3m`: rolling 90-day drawdown from `nasdaq100`
- `initial_claims_4w_avg`: latest four observations of `initial_jobless_claims`
- `continuing_claims_4w_avg`: latest four observations of `continuing_claims`

Derived rows use `source_badge=derived`, keep dependency metadata in lineage, and
do not forward-fill weekly data into daily rows.

## Audit

`scripts/audit_data_pipeline_coverage.py` reports `core_risk_history` with raw
and derived counts, missing mappings, source-badge distribution, missing history
metrics, and whether D13 has enough history to compute all configured rows.
