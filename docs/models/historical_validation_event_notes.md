# Historical Validation Event Notes

## Purpose

This document recovers event-note material from the course-paper clustering
research for future D19 historical validation work. It is not a backtest result,
not a production classifier, and not a trading or prediction layer.

D19 validates historical pressure recognition and boundary behavior. It does
not validate return prediction, crash prediction, recession probability, or
portfolio strategy performance.

## Event Note Schema

Future event notes can use this schema:

- `event_id`
- `event_name`
- `window`
- `expected_pressure_groups`
- `expected_archetype`
- `external_index_reference`
- `ordinary_pullback_flag`
- `data_availability_constraints`
- `interpretation_boundary`

The schema is descriptive. It should not include trade direction, expected
return, prediction accuracy, cluster probability, or portfolio action.

## D19 v0 Implementation Status

D19 v0 Historical Validation Event Registry + Replay Skeleton is completed.
The candidate windows below are now represented in
`src/data_quality/historical_validation_event_registry.py` with
controlled event types, expected pressure groups, ordinary-pullback markers,
external-reference notes, data-availability constraints, and interpretation
boundaries.

`src/data_quality/historical_validation_replay.py` converts those
registry entries into structured replay rows. The default status is
`reference_only` unless a caller supplies an existing local historical
validation summary. `reference_only` and `limited` are coverage states, not
risk labels.

The implementation does not read DB files, outputs, holdings, private data,
external AI config, or live providers. It does not add endpoints, frontend UI,
production clustering, probabilities, return estimates, or trading advice.

## Candidate Windows

### 2000 Dot-com / Equity Valuation Unwind

Expected pressure groups: equity drawdown, volatility, valuation/structure
research gaps.

Expected archetype: volatility/equity drawdown pressure.

Boundary: not a reusable crash-probability template.

### 2008 GFC / Credit-funding Systemic Stress

Expected pressure groups: credit spread, funding/liquidity, volatility, equity
drawdown.

Expected archetype: credit-volatility joint pressure.

Boundary: historical systemic-stress reference only; not a trading backtest.

### 2011 Debt Ceiling / Eurozone Stress

Expected pressure groups: volatility, credit pressure, equity drawdown,
policy-risk context.

Expected archetype: mixed or transition stress.

Boundary: external-index comparison can help interpret conflict, not override
project labels.

### 2015-2016 Oil / HY Energy Stress

Expected pressure groups: high-yield credit, energy pressure, equity
volatility.

Expected archetype: credit-volatility joint pressure.

Boundary: sector-specific credit pressure should not be generalized without
broader evidence.

### 2018 Q4 Rates / Liquidity / Equity Stress

Expected pressure groups: rates pressure, liquidity/funding context, volatility,
equity drawdown.

Expected archetype: rates pressure with volatility/equity damage.

Boundary: DGS30 or VIX alone cannot trigger systemic interpretation.

### 2020 COVID Liquidity Shock

Expected pressure groups: volatility, equity drawdown, credit spread,
funding/liquidity stress.

Expected archetype: broad credit-volatility-funding pressure.

Boundary: historical shock recognition, not future shock prediction.

### 2022 Inflation / Rates Pressure

Expected pressure groups: inflation, real yield, long-term rates, equity
drawdown, credit pressure.

Expected archetype: rates/inflation pressure with mixed transmission.

Boundary: rates and inflation evidence do not imply a recession probability or
allocation action.

### 2023 SVB / Regional Banking Liquidity-credit Stress

Expected pressure groups: funding/liquidity, credit, volatility, policy-rate
pressure.

Expected archetype: liquidity-credit stress.

Boundary: regional banking stress should be documented as event context, not as
a generic market-timing signal.

### 2024-2025 AI Concentration / Valuation-structure Research Window

Expected pressure groups: concentration, valuation/earnings research gaps,
rates context, equity-structure proxy context.

Expected archetype: low-to-mixed pressure with valuation/concentration research
constraints.

Boundary: proxy concentration or valuation gaps cannot determine systemic
stress or macro regime.

## How Paper Clustering Can Help

Cluster periods can serve as historical archetype notes. They can help explain
which pressure groups tended to co-occur in the course-paper sample and can
inform candidate D19 event descriptions.

They cannot serve as prediction backtests, live classifiers, trading signals,
or cluster-to-portfolio mappings.

## External Index Reference

External indices such as NFCI, STLFSI, OFR FSI, or KCFSI can be recorded as
independent reference layers when available. Agreement can support historical
interpretation. Disagreement should become a conflict note.

External indices do not replace project model outputs and do not trigger
production labels directly.

## D19 Boundary

D19 validates historical pressure recognition, data coverage, and boundary
behavior. It is not return prediction, event-odds modeling, probability
calibration, investment advice, or a strategy backtest.
