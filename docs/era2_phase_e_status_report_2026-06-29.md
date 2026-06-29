# Era 2 Phase E Status Report

Date: 2026-06-29
Branch: `app-mvp`
Scope: Phase E scenario return-band engine readiness and framework progress

## 1. Executive Status

Phase E has moved from pure design into framework implementation, but it is still not allowed to output numerical scenario return-band values.

Current status:

- E1 design is present in `docs/era2_return_band_design.md`.
- E2 framework development has started with small, tested commits.
- HY OAS history is no longer the immediate data-length blocker after the manual audited MacroMicro/ICE series was normalized.
- The engine remains blocked for numerical output because several required factor inputs are not yet wired into a monthly Phase E panel, and `real_yield_10y` still needs a policy decision.

The current implementation is diagnostic/framework-only. It does not run OLS, does not create scenario shock vectors, does not compute ETF or portfolio scenario impacts, and does not emit return-band values.

## 2. Implemented Commits

The local branch is currently ahead of `origin/app-mvp` by five commits:

| Commit | Change | Status |
|---|---|---|
| `f2dd53d` | Add manual HY OAS capture tooling | Complete |
| `c76b3dc` | Add Phase E input diagnostics | Complete |
| `9c1d855` | Add Phase E input audit CLI | Complete |
| `763f6e2` | Add Phase E monthly factor panel | Complete |
| `61887fc` | Add Phase E ETF return series | Complete |

Implemented files:

- `tools/browser/macromicro_oas_recorder.user.js`
- `tools/data/normalize_manual_oas_capture.py`
- `tests/tools/test_normalize_manual_oas_capture.py`
- `src/data_quality/phase_e_return_band_diagnostics.py`
- `tests/data_quality/test_phase_e_return_band_diagnostics.py`
- `scripts/audit_phase_e_inputs.py`
- `tests/scripts/test_audit_phase_e_inputs.py`
- `src/data_quality/phase_e_factor_panel.py`
- `tests/data_quality/test_phase_e_factor_panel.py`
- `src/data_quality/phase_e_etf_returns.py`
- `tests/data_quality/test_phase_e_etf_returns.py`

## 3. Data Status

### 3.1 HY OAS

Manual audited HY OAS data has been normalized into the local ignored manual-capture area:

- Local normalized monthly file: `data/manual_capture/oas/high_yield_spread_manual_audited_monthly.csv`
- Source method: `manual_audited_download`
- Source series: `BAMLH0A0HYM2`
- Source page: MacroMicro series page, upstream ICE BofA data
- Database write: none
- Raw source values committed to public git: no

Latest local Phase E input audit result:

| Field | Value |
|---|---|
| Factor | `credit_spread_hy` |
| Series key | `high_yield_spread` |
| Status | `ok` |
| First month | `1996-12` |
| Last month | `2026-06` |
| Observation count | `345` |
| Month span inclusive | `355` |
| Meets 84M main-window minimum | `true` |
| Meets 60M auxiliary-window minimum | `true` |
| Duplicate months | none |
| Longest consecutive run | `82` months |
| Trailing 120M windows with at least 84 observed | `271` |

Known missing months in the manual monthly series:

```text
1999-08
2006-07
2011-12
2013-04
2013-10
2016-04
2016-05
2019-07
2025-02
2025-08
```

Interpretation: the HY OAS data-length gate is satisfied for Phase E diagnostics. This does not by itself authorize numerical return-band output; it only removes the prior F2 history-length blocker, subject to final project admission of the manual audited source.

### 3.2 Remaining Factor Inputs

The latest input audit still reports overall status `insufficient_inputs`.

Blocking factors:

| Factor | Current audit status | Required next action |
|---|---|---|
| `real_yield_10y` | `blocked` | User/project decision required: design formula `DGS10 - T5YIFR` vs existing `DFII10` convention |
| `growth_momentum_zscore` | `missing` | Locate and map monthly ISM PMI / PMI z-score source |
| `vix_level` | `missing` | Locate and map monthly VIX close or monthly aggregate |
| `ust_slope` | `missing` | Locate and map `DGS10 - DGS2` monthly slope |
| `commodity_trend` | `missing` | Locate and map Brent 3M monthly momentum |

Non-blocking for the current framework slice:

- `credit_spread_hy` is available at sufficient monthly history length.
- ETF 3M return calculation framework exists, but real ETF monthly price/total-return inputs have not yet been connected to the Phase E engine.

## 4. Framework Components

### 4.1 Manual HY OAS Capture And Normalization

Implemented:

- Browser-side Tampermonkey tooltip recorder for manual hover capture.
- Local normalizer for raw capture CSV.
- Daily and monthly normalized output generation.
- Quality report and manifest generation.
- Tests for duplicate handling, conflict detection, monthly latest-observation logic, capture metadata preservation, and history gates.

Boundary:

- No OCR.
- No provider API scraping.
- No network fetch by the normalizer.
- No database write.
- Manual capture outputs remain under ignored local data paths.

### 4.2 Phase E Input Diagnostics

Implemented:

- `MonthlyObservation` data contract.
- Series coverage diagnostics.
- Factor-level diagnostics for the six Phase E factors.
- 84M main-window and 60M auxiliary-window gate checks.
- Duplicate-month and missing-month detection.
- Explicit diagnostic-only boundary.

Current behavior:

- Returns `diagnostic_only`.
- Sets `no_return_band_values = true`.
- Blocks `real_yield_10y` by default until the policy choice is explicit.

### 4.3 Phase E Input Audit CLI

Implemented command:

```bash
python scripts/audit_phase_e_inputs.py
```

Purpose:

- Load the normalized manual audited HY OAS monthly file.
- Produce a JSON readiness audit.
- Report source-file metadata and factor blockers.

Safety properties:

- `network_access = false`
- `reads_database = false`
- `writes_database = false`
- `reads_private_holdings = false`
- `emits_raw_series_values = false`
- `computes_return_band_values = false`

### 4.4 Monthly Factor Panel

Implemented:

- Common-month alignment for confirmed monthly factor observations.
- Missing required factor detection.
- Missing month reporting by factor.
- Duplicate month rejection.
- Minimum common-history gate.

Boundary:

- No imputation.
- No forward-fill.
- No regression.
- No scenario construction.
- No return-band values.

### 4.5 ETF 3M Return Series

Implemented:

- Monthly trailing 3-month ETF return calculation:

```text
return_3m(month_t) = level(month_t) / level(month_t - 3M) - 1
```

- Exact lag-month matching.
- Missing lag-month skip.
- Duplicate-month rejection.
- Non-positive level rejection.
- 84-return history gate.

Boundary:

- No forecasting.
- No annualization.
- No portfolio optimization.
- No scenario impact calculation.

## 5. Verification

Commands run for the current status report:

```bash
git status --short --branch
git log --oneline -8
python scripts/audit_phase_e_inputs.py
```

Most recent targeted regression for the Phase E work:

```bash
python -m pytest -q \
  tests/tools/test_normalize_manual_oas_capture.py \
  tests/data_quality/test_phase_e_return_band_diagnostics.py \
  tests/scripts/test_audit_phase_e_inputs.py \
  tests/data_quality/test_phase_e_factor_panel.py \
  tests/data_quality/test_phase_e_etf_returns.py
```

Result:

```text
26 passed in 2.67s
```

## 6. Current Gate Assessment

Phase E framework development can continue.

Phase E numerical return-band output cannot start yet.

Allowed next work:

- Wire existing local macro/market histories into monthly Phase E input adapters.
- Implement deterministic factor transforms where already approved, such as `DGS10 - DGS2` and Brent 3M momentum.
- Add tests for each adapter using fixtures.
- Continue keeping all public/live outputs fail-closed until the full factor panel passes gates.

Not allowed yet:

- OLS beta estimation on live project data.
- Scenario shock vector generation.
- ETF or portfolio scenario impact output.
- Probability labels, expected-return labels, buy/sell/timing labels, or optimizer output.
- Treating `BAA10Y` as a substitute for HY OAS.

## 7. Decisions Needed

### Decision 1: `real_yield_10y` Definition

The design document defines:

```text
real_yield_10y = DGS10 - T5YIFR
```

The current project context also has precedent for `DFII10`. Before any numerical Phase E result, the project needs a single admitted policy:

- Option A: use `DGS10 - T5YIFR`, matching the E1 design document.
- Option B: use `DFII10`, matching real-yield market convention and some existing project practice.
- Option C: support both, but only one may be the canonical Phase E regression factor.

Current implementation default: block until this is decided.

### Decision 2: Manual HY OAS Admission

The manual audited MacroMicro/ICE data satisfies the length gate, but the project should explicitly admit it as a Phase E source before numerical output.

Suggested admission language:

```text
For Phase E only, the manually audited MacroMicro/ICE BAMLH0A0HYM2 monthly HY OAS series is admitted as a local historical input with source_method=manual_audited_download. It may be used for factor-history diagnostics and Phase E factor panel construction, but raw source files remain local-only and are not committed.
```

### Decision 3: Monthly Aggregation Rules

For each factor, the project still needs fixed monthly aggregation rules:

| Factor | Suggested rule |
|---|---|
| `real_yield_10y` | month-end value after canonical definition is chosen |
| `credit_spread_hy` | latest observation within month from manual audited monthly file |
| `growth_momentum_zscore` | month-level ISM PMI z-score using approved local PMI series |
| `vix_level` | month-end close or monthly average; needs project choice |
| `ust_slope` | month-end `DGS10 - DGS2` |
| `commodity_trend` | Brent 3M trailing return/momentum |

## 8. Recommended Next Slice

Recommended next implementation slice: factor input adapters, still without OLS.

Proposed order:

1. Add monthly adapter for `ust_slope = DGS10 - DGS2`.
2. Add monthly adapter for `commodity_trend` from Brent.
3. Add monthly adapter for `vix_level`.
4. Add monthly adapter for ISM PMI / `growth_momentum_zscore`.
5. Add `real_yield_10y` adapter only after the definition is confirmed.
6. Extend `scripts/audit_phase_e_inputs.py` to include local monthly factor adapter summaries.

Acceptance criteria for the next slice:

- Each adapter is fixture-tested.
- Each adapter reports coverage, missing months, duplicates, and source metadata.
- The audit CLI still reports `computes_return_band_values = false`.
- No private holdings, raw provider payloads, secrets, or network calls are introduced.
- No public API route or frontend feature is exposed.
