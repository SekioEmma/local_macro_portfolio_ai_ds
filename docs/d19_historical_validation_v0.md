# D19 Historical Validation v0

## Scope

D19 v0 adds a static historical validation event registry and replay skeleton.
It validates historical pressure recognition and interpretation boundaries.
It is not prediction, not a return backtest, and not trading strategy
evaluation.

The v0 registry is local, static, and auditable. It does not read private data,
does not read external model configuration, does not query SQLite, does not
call live providers, and does not add endpoints or frontend UI.

## Event Registry

The registry lives in
`src/app_backend/services/historical_validation_event_registry.py`.

Each event includes:

- `event_id`
- `event_name`
- `start_date`
- `end_date`
- `pre_window_start`
- `pre_window_end`
- `event_type`
- `expected_archetype`
- `expected_pressure_groups`
- `ordinary_pullback_flag`
- `external_index_reference`
- `data_availability_constraints`
- `interpretation_boundary`
- `source_note`

Event types are controlled literals:

- `ordinary_pullback`
- `rates_pressure_event`
- `inflation_rates_event`
- `credit_stress_event`
- `liquidity_funding_event`
- `systemic_stress_event`
- `growth_slowdown_event`
- `mixed_transition_event`
- `valuation_structure_research_window`

Pressure groups are controlled literals:

- `credit`
- `liquidity_funding`
- `rates_real_yield`
- `inflation_energy`
- `labor_growth`
- `equity_structure`
- `valuation_earnings_breadth`
- `external_reference`

## Initial Event Windows

The initial static registry contains these Stage R1 reference windows:

- `dot_com_equity_valuation_unwind_2000`
- `gfc_credit_funding_systemic_stress_2008`
- `debt_ceiling_eurozone_stress_2011`
- `oil_hy_energy_credit_stress_2015_2016`
- `q4_rates_liquidity_equity_stress_2018`
- `covid_liquidity_shock_2020`
- `inflation_rates_pressure_2022`
- `svb_regional_banking_liquidity_credit_stress_2023`
- `ai_concentration_valuation_structure_research_window_2024_2025`

The windows are conservative historical reference windows. They are not
ground-truth labels for probabilities or live model targets.

## Replay Skeleton

The replay skeleton lives in
`src/app_backend/services/historical_validation_replay.py`.

It converts registry events into structured replay rows with:

- event identity and type
- event and pre-event windows
- expected pressure groups and archetype
- ordinary-pullback marker
- available model-output hints when a caller provides an existing summary
- missing or limited input notes
- external-reference notes
- interpretation boundaries
- validation status

Allowed statuses:

- `available`
- `limited`
- `insufficient`
- `reference_only`

When no existing summary is passed, v0 returns `reference_only`. That status is
a coverage state, not a low-risk label.

## What D19 Can Validate

- Historical pressure-recognition timing.
- Ordinary pullback versus stress escalation boundary.
- Missing, proxy, stale, or limited-history handling.
- External stress index conflict notes.
- D10/D11/D13/D14 interpretation stability.

## What D19 Cannot Validate

- Crash probability.
- Recession probability.
- Market direction.
- Expected return.
- Trading performance.
- Portfolio allocation.

## Relation to Course Paper Recovery

The Stage R1 course-paper recovery informs historical archetype descriptions,
event notes, and interpretation boundaries only.

K-means and GMM research remain outside production logic. D19 v0 does not add a
production classifier, cluster probability, or cluster-to-action mapping.

External stress indices remain reference layers. They do not replace D10, D11,
D15, D19, or project evidence gates.

## CLI Integration

`scripts/run_historical_validation.py` keeps its default summary behavior.

Optional read-only flags were added:

- `--include-event-registry`
- `--show-events`

`python scripts/run_historical_validation.py --format text` remains compatible
with the existing D19 historical validation script behavior.

## Next Step

DF-0 roadmap arbitration begins Stage DF and keeps external AI frozen. The next
engineering task after DF-0 is D19 v1 historical evidence-row integration.

D19 v1 may connect the static registry to actual historical evidence rows when
safe. D15 may use the D19 event registry as historical interpretation
reference, not as training labels.
