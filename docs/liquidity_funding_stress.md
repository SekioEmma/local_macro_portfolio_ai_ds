# Liquidity/Funding Stress Reference Layer

`liquidity_funding_stress` is a local, read-only, auditable reference evidence
module for money-market plumbing, short-term funding, and official/reference
financial stress context. It is not a trading signal, crash probability,
recession probability, or replacement for the project-built D10 financial stress
composite.

## Rows

The first D14 row set is:

- `sofr`
- `effr`
- `iorb`
- `on_rrp`
- `commercial_paper_rate`
- `ofr_fsi`
- `stl_fsi`
- `nfci`
- `anfci`
- `sofr_effr_spread`
- `effr_iorb_spread`
- `cp_effr_spread`
- `cp_sofr_spread`
- `policy_plumbing_status`
- `short_term_funding_pressure_status`
- `official_stress_reference_status`
- `liquidity_funding_stress_status`
- `liquidity_funding_interpretation_boundary`

Rows with stable configured mappings read only from local `market_history`.
Rows without a verified mapping remain visible as `research_needed` with
`missing_reason=source_mapping_required`.

## Source Badges

- `official`: FRED policy plumbing series such as SOFR, EFFR, IORB, and ON RRP.
- `official_fallback`: FRED-relayed reference series such as CP, STLFSI, NFCI,
  and ANFCI.
- `derived`: local spreads, status rows, and interpretation boundary.
- `research_needed`: source mapping still requires verification, currently OFR
  FSI.

## Series Mappings

Current configured FRED mappings are:

- `sofr`: `SOFR`
- `effr`: `EFFR`
- `iorb`: `IORB`
- `on_rrp`: `RRPONTSYD`
- `commercial_paper_rate`: `DCPF3M`
- `stl_fsi`: `STLFSI4`
- `nfci`: `NFCI`
- `anfci`: `ANFCI`

`ofr_fsi` is intentionally `research_needed` until a stable source/API mapping
is added.

## Derived Spreads

Spreads are local derived rows:

- `sofr_effr_spread = SOFR - EFFR`
- `effr_iorb_spread = EFFR - IORB`
- `cp_effr_spread = commercial_paper_rate - EFFR`
- `cp_sofr_spread = commercial_paper_rate - SOFR`

Units are percentage points (`pp`). If input dates differ, the row records
explicit as-of alignment metadata and `forward_fill_used=false`.

## Status Rules

The status rows are conservative:

- Normal policy plumbing, CP spread, and reference indices produce `ok`.
- One mildly elevated area produces `watch`.
- Elevated CP spread plus at least one elevated reference index can produce
  `pressure`.
- Severe CP spread plus multiple elevated reference indices plus abnormal policy
  plumbing can produce `stress`.
- Missing CP and missing reference indices produce `insufficient_evidence`.
- ON RRP alone cannot trigger `pressure` or `stress`.
- Official/reference stress indices alone can at most support reference context;
  they do not confirm systemic crisis.

## Boundaries

Liquidity/funding stress rows are reference evidence, not trading signals.
Official stress indices are external reference layers and do not replace the
project financial stress composite. Commercial paper spread can support
funding-pressure confirmation but cannot alone prove systemic crisis.
SOFR/EFFR/IORB/ON RRP describe policy plumbing and money-market backdrop, not
market direction. ON RRP usage alone is not a risk trigger. Different
frequencies must not be mixed without explicit as-of alignment. No crash
probability or recession probability is produced. No buy/sell/hedge instruction
is produced.

## Why D14 Does Not Replace D10

D10 is the project's transparent composite. D14 external/reference indices are
comparison evidence for funding and official financial-conditions backdrop.
They do not become a shadow PCA/HMM/FSI model and do not override D10.

## Why D14 Does Not Yet Change D11

D14 creates the reference data layer only. D11 still keeps liquidity/funding as
a critical missing input in this task. D14b can later decide how to integrate
eligible D14 rows into the pullback/systemic checklist.

## D14b Plan

D14b can consume the audited D14 rows as auxiliary confirmation evidence for
ordinary pullback, credit warning, and systemic risk review separation. That
integration should preserve the same boundaries: no trading instructions, no
probability claims, no D10 replacement, and no single liquidity/funding metric
as sufficient systemic-crisis proof.
