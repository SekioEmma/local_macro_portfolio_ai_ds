# Data Foundation G1 - Controlled Local Refresh and Coverage Audit

## Scope

Controlled local data refresh and coverage audit after G0 (source registry
cleanup, `06e4a4c`). Uses only existing repository ingest scripts. Covers
already-configured official / official_fallback / public-source FRED and
yfinance series. No new provider code, no new endpoints, no model-semantic
changes, no committed generated data.

User authorization: run existing local refresh scripts to fill official/public
source gaps. All other frozen boundaries remain in effect.

The pre-refresh baseline and command results below were captured during the
interrupted G1 execution on June 17, 2026. The post-refresh database state,
coverage audit, benchmark, and source gates were rechecked on June 18, 2026
before closeout.

## Pre-refresh Baseline

Commands run:

```
python scripts/audit_data_foundation_gaps.py
python scripts/audit_data_pipeline_coverage.py
python scripts/run_historical_validation.py --format text
python scripts/benchmark_dashboard_pipeline.py
```

| Metric | Before |
|---|---|
| audit_data_foundation_gaps status | PASS (12 findings, 0 errors) |
| pipeline overall_status | degraded |
| degraded reason | portfolio_deviation: module_status=pressure |
| evidence rows | 219 |
| included facts | 119 |
| included model outputs | 63 |
| ok rows | 168 |
| watch rows | 8 |
| pressure rows | 5 |
| research_needed rows | 15 |
| insufficient_history rows | 6 |
| missing rows | 0 |
| stale rows | 0 |
| ai_context_allowed true | 182 |
| ai_context_allowed false | 37 |
| rows_with_value | 211 |
| rows_missing_value | 8 |
| market_history observations | 33,803 |
| market_history metrics | 45 |
| ppi_final_demand status | ok (180 observations) |
| wti observations | 352 |
| brent observations | 357 |
| core_risk official observations | 6,270 |
| core_risk unofficial_fallback | 3,014 |
| core_risk derived | 6,206 |
| D13 history_sufficient_for_d13 | false |
| historical validation events | 11 total, 2 available, 3 limited, 6 insufficient |
| historical validation boundary violations | 0 |
| benchmark evidence rows | 219 |

Note: `overall_status=degraded` is due to `portfolio_deviation:
module_status=pressure`, which reflects existing portfolio state, not a data
failure. This is expected behavior and does not indicate a data gap.

## Refresh Commands Discovered

Discovery classification:

- Provider health refresh: `run_provider_health_check.py`; live/network smoke,
  writes a compact report only with `--save`.
- Market history refresh/backfill: the six ingest scripts used below, plus
  `ingest_market_history_from_dashboard.py` for local dashboard-derived history.
- Daily report generation: `run_daily_report.py`; writes generated reports and
  may invoke snapshot generators when existing snapshots are stale.
- Dashboard/report regeneration: `run_market_data_check.py`,
  `run_market_temperature_check.py`, `run_portfolio_check.py`, and
  `run_llm_context_pack.py`; not needed for this coverage-only refresh.
- Audit-only scripts: the four baseline/post-refresh audit, validation, and
  benchmark commands below plus `dev_check_validator_boundaries.py`.
- Test-only commands: the targeted and full `pytest` commands in Validation.

| Command | Purpose | Live/network? | Writes local data? | Used? | Notes |
|---|---|---|---|---|---|
| `scripts/ingest_official_ppifis_history.py` | PPI Final Demand (PPIFIS) via FRED | FRED API | SQLite | yes | `--live --write` |
| `scripts/ingest_liquidity_funding_history.py` | D14: SOFR/EFFR/IORB/RRPONTSYD/DCPF3M/STLFSI4/NFCI/ANFCI via FRED | FRED API | SQLite | yes | `--live --write`; ofr_fsi stays research_needed |
| `scripts/ingest_core_risk_history.py` | DGS30/DFII10/HY/IG/VIX/ICSA/CCSA (FRED) + SP500/NASDAQ100 (yfinance) + derived | FRED + yfinance | SQLite | yes | `--live --write` |
| `scripts/ingest_official_labor_history.py` | UNRATE/ICSA/PAYEMS/CCSA via FRED | FRED API | SQLite | yes | `--live --write --monthly-limit 60 --weekly-limit 156` |
| `scripts/ingest_official_energy_history.py` | WTI/Brent (DCOILWTICO/DCOILBRENTEU) via FRED | FRED API | SQLite | yes | `--live --write` |
| `scripts/ingest_yfinance_history.py` | 11 symbols (proxy/unofficial_fallback breadth/equity basket) via yfinance | yfinance | SQLite | yes | `--live --write --period 6y` |
| `scripts/ingest_market_history_from_dashboard.py` | Dashboard-derived history | local | SQLite | no | Not needed; covered by above |
| `scripts/run_provider_health_check.py` | Provider health snapshot | provider smoke calls | outputs only with `--save` | no | Not required for market-history coverage |
| `scripts/run_daily_report.py` | Regenerate snapshots and daily report | possible if snapshots stale | outputs/reports | no | Generated reports are outside commit scope |
| `scripts/audit_data_foundation_gaps.py` | Audit source registry | read-only | none | yes | baseline + post |
| `scripts/audit_data_pipeline_coverage.py` | Full pipeline coverage audit | read-only | none | yes | baseline + post |
| `scripts/benchmark_dashboard_pipeline.py` | Performance benchmark | read-only | none | yes | baseline + post |
| `scripts/run_historical_validation.py` | Historical event replay | read-only | none | yes | baseline + post |
| `scripts/dev_check_validator_boundaries.py` | Forbidden-language boundary check | read-only | none | yes | post |

DGS2, DGS10, T10Y2Y, T10YIE are in the refresh target universe but have no
dedicated ingest script surface. See Remaining Gaps.

## Refresh Commands Run

| Command | Result | Files written | Notes |
|---|---|---|---|
| `python scripts/ingest_official_ppifis_history.py --live --write` | 180 updated | market_history.sqlite3 | All 180 existing observations refreshed; 0 inserted (data current) |
| `python scripts/ingest_liquidity_funding_history.py --live --write` | 20 inserted, 11,952 updated, 8 derived | market_history.sqlite3 | All 8 series ok; ofr_fsi stays research_needed |
| `python scripts/ingest_core_risk_history.py --live --write` | 25 inserted, 18,613 updated, 6,212 derived | market_history.sqlite3 | All 9 providers ok; SP500/NASDAQ100 yfinance ok |
| `python scripts/ingest_official_labor_history.py --live --write --monthly-limit 60 --weekly-limit 156` | 72 inserted, 359 updated | market_history.sqlite3 | 4 series ok; extended limits for fuller coverage |
| `python scripts/ingest_official_energy_history.py --live --write` | 10 inserted, 701 updated | market_history.sqlite3 | WTI/Brent ok |
| `python scripts/ingest_yfinance_history.py --live --write --period 6y` | 11,313 inserted, 5,275 updated | market_history.sqlite3 | 11 symbols ok; proxy + unofficial_fallback badges only |

Total new data: 11,440 market_history observations added (33,803 → 45,243).

FRED credentials were resolved from the existing environment. No credential
value was read into this document, printed, passed on the command line, or
committed.

## Post-refresh Coverage

| Metric | Before | After | Change |
|---|---|---|---|
| evidence rows | 219 | 219 | unchanged |
| included facts | 119 | **125** | +6 |
| included model outputs | 63 | 63 | unchanged |
| ok rows | 168 | **175** | +7 |
| watch rows | 8 | 7 | -1 |
| pressure rows | 5 | 5 | unchanged |
| research_needed rows | 15 | 15 | unchanged |
| **insufficient_history rows** | **6** | **0** | **fully resolved** |
| missing rows | 0 | 0 | unchanged |
| stale rows | 0 | 0 | unchanged |
| ai_context_allowed true | 182 | **188** | +6 |
| ai_context_allowed false | 37 | **31** | -6 |
| rows_with_value | 211 | **217** | +6 |
| rows_missing_value | 8 | **2** | -6 |
| market_history observations | 33,803 | **45,243** | +11,440 |
| market_history metrics | 45 | 45 | unchanged |
| ppi_final_demand status | ok | ok | unchanged |
| ppifis observations | 180 | 180 | current |
| wti observations | 352 | **357** | +5 |
| brent observations | 357 | **362** | +5 |
| core_risk official | 6,270 | **6,274** | +4 |
| core_risk unofficial_fallback | 3,014 | **3,020** | +6 |
| core_risk derived | 6,206 | **6,212** | +6 |
| **D13 history_sufficient_for_d13** | **false** | **true** | **resolved** |
| historical validation available events | 2 | 2 | unchanged |
| historical validation limited events | 3 | 3 | unchanged |
| historical validation insufficient events | 6 | 6 | unchanged; current cross-series local coverage does not satisfy those event windows |
| historical validation boundary violations | 0 | 0 | unchanged |
| benchmark included facts | 119 | **125** | +6 |

Key outcome: `D13 history_sufficient_for_d13` flipped from `false` to `true`.
The 6 previously `insufficient_history` rows are now resolved, making 6
additional facts eligible for AI context.

Pipeline overall_status remains `degraded` because `portfolio_deviation:
module_status=pressure`. This is pre-existing portfolio state, not a data
gap.

## Source-Gate Results

| Source | Status | Notes |
|---|---|---|
| PPI Final Demand / PPIFIS | ok | 180 observations, official badge, PPIFIS series only; YoY gate intact |
| PPIACO / ppi_all_commodities | configured official mapping | FRED `PPIACO` remains distinct from PPIFIS; no dedicated history ingest was run |
| D14 SOFR | ok, official | refreshed |
| D14 EFFR | ok, official | refreshed |
| D14 IORB | ok, official | refreshed |
| D14 ON RRP (RRPONTSYD) | ok, official | refreshed |
| D14 commercial_paper_rate (DCPF3M) | ok, official_fallback | refreshed |
| D14 STL FSI (STLFSI4) | ok, official_fallback | refreshed |
| D14 NFCI | ok, official_fallback | refreshed |
| D14 ANFCI | ok, official_fallback | refreshed |
| OFR FSI | research_needed | source_mapping_required; not promoted; stays excluded |
| valuation_proxy | not_available | intentionally blocked; not promoted |
| fedwatch_probability | not_available | intentionally blocked; not promoted |
| BAA10Y / BAA10YM | reference-only | not aliased to HY/IG OAS; not promoted |
| proxy/SPY/RSP/QQQ breadth | proxy badge | proxy badge preserved; not promoted to official fact |
| SP500 / NASDAQ100 yfinance | unofficial_fallback | badge preserved; not promoted |
| PPIACO | official mapping, not refreshed | no dedicated history ingest surface; never substituted for final-demand PPI |
| HYG/LQD | proxy mappings | refreshed only as yfinance ETF proxies; never promoted to HY/IG OAS facts |

Source-gate audit: PASS (12 findings, 0 errors) — identical before and after
refresh. No source_badge was upgraded from proxy/unofficial to official.

## Files Not Committed

The following files were written by ingest scripts but are gitignored and
were not committed:

```
data/market_history/market_history.sqlite3   (updated, not tracked)
```

The final ignored-file audit also observed existing generated artifacts under:

```
outputs/reports/*.json
outputs/reports/*.md
outputs/analyst_memos/*.json
outputs/analyst_memos/*.md
```

These output files remain ignored and uncommitted. Only
`outputs/reports/.gitkeep` and `outputs/analyst_memos/.gitkeep` are tracked.

The SQLite file is ignored by `.gitignore`. Final Git checks confirm that it is
not tracked or staged; only the intended documentation changes are commit
candidates.

## Remaining Gaps

| Gap | Reason | Disposition |
|---|---|---|
| DGS2, DGS10, T10Y2Y, T10YIE | No dedicated market-history ingest script in repository; compact report values may still exist | History refresh surface missing; requires G2 task with explicit approval before implementation |
| Core CPI / CPILFESL | Configured source, but no dedicated history ingest script | History refresh surface missing |
| Core PCE / PCEPILFE | Configured source, but no dedicated history ingest script | History refresh surface missing |
| OFR FSI | No stable public FRED series mapping; research_needed is correct | Stays research_needed; excluded from AI context |
| valuation_proxy | Intentionally not_available; no official provider | Stays not_available |
| fedwatch_probability | Intentionally not_available | Stays not_available |
| BAA10Y | Reference-only; cannot substitute HY/IG OAS | Stays reference-only |
| Historical validation 2011–2021 events | 0 available days; FRED history too short for 5Y lookback | Insufficient history is expected for these event windows; not a data gap to fill |
| True breadth / concentration | No official ingest layer in scope | Outside G1 scope |
| Forward PE / earnings revisions | No official provider | Outside G1 scope |

## D-line naming cleanup compliance

All gap descriptions use plain-English module names per HF-2 policy:
- Historical Risk Normalization (legacy: D13)
- Liquidity & Funding Stress (legacy: D14)
- Scenario Stress Matrix (legacy: D16) — not modified by G1

## Validation

- Targeted source-gate and dashboard tests: 73 passed, 1 existing
  Starlette/TestClient deprecation warning.
- API / AI Context Manifest / golden contract regression tests: 36 passed, 1
  existing Starlette/TestClient deprecation warning.
- Full `python -m pytest -q`: 1488 passed, 1 existing
  Starlette/TestClient deprecation warning.
- `python scripts/audit_data_foundation_gaps.py`: PASS, 12 findings, 0 errors.
- `python scripts/audit_data_pipeline_coverage.py`: exit 0,
  `overall_status=degraded`, 0 hard failures; the only degraded reason is
  `portfolio_deviation: module_status=pressure`.
- `python scripts/run_historical_validation.py --format text`: available; 11
  events, 2 available, 3 limited, 6 insufficient, 0 boundary violations.
- `python scripts/dev_check_validator_boundaries.py`: passed; allowed=9,
  blocked=8, regression=17.
- `python scripts/benchmark_dashboard_pipeline.py`: 45,243 observations / 45
  metrics, 219 evidence rows, 125 included facts, 63 included model outputs,
  explicit shared-context reuse, 2 estimated rebuilds avoided.
- `git diff --check`: passed; only Git line-ending conversion warnings were
  emitted.

## Next

Data coverage is materially improved (6 insufficient_history resolved, 6
new AI-eligible facts, D13 now `history_sufficient_for_d13=true`). The
remaining degraded status is exclusively `portfolio_deviation:
module_status=pressure`, which is portfolio state, not a data gap.

Recommended next steps (in order):
1. If data coverage is acceptable: proceed to **UI-0 / UI-1 frontend
   data-display route**.
2. If DGS2/DGS10/T10Y2Y/T10YIE coverage is needed before UI work: create
   **G2 official-source refresh command implementation**, but only with
   explicit approval.
3. G2 would also cover core CPI (CPILFESL) and core PCE (PCEPILFE) ingest
   if BEA or FRED mappings are configured.

Data Foundation G1 is a controlled local data refresh and coverage audit task.
It may run existing local provider/report refresh commands with user approval,
but it does not add new live provider code, commit generated data, change
backend API schema, change financial model semantics, change
metric/module/public output keys, change AI Context Manifest semantics, promote
missing/research_needed/not_available/proxy/search-derived data to official
facts, treat PPIACO as final demand PPI, use BAA10Y as an HY/IG OAS substitute,
open external AI, open Tavily/search, add frontend UI, add Tauri, add account
editing, expose holdings line items, or add
prediction/probability/return/trading/allocation outputs.
