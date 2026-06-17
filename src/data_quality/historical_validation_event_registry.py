from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date
from typing import Literal


HistoricalValidationEventType = Literal[
    "ordinary_pullback",
    "rates_pressure_event",
    "inflation_rates_event",
    "credit_stress_event",
    "liquidity_funding_event",
    "systemic_stress_event",
    "growth_slowdown_event",
    "mixed_transition_event",
    "valuation_structure_research_window",
]

HistoricalValidationPressureGroup = Literal[
    "credit",
    "liquidity_funding",
    "rates_real_yield",
    "inflation_energy",
    "labor_growth",
    "equity_structure",
    "valuation_earnings_breadth",
    "external_reference",
]

ALLOWED_EVENT_TYPES: frozenset[str] = frozenset(HistoricalValidationEventType.__args__)
ALLOWED_PRESSURE_GROUPS: frozenset[str] = frozenset(
    HistoricalValidationPressureGroup.__args__
)

COMMON_INTERPRETATION_BOUNDARY: tuple[str, ...] = (
    "D19 event windows are historical reference windows, not training labels.",
    "D19 validates pressure-recognition context and boundary behavior only.",
    "Missing inputs remain missing, and proxy inputs remain constrained.",
    "External stress indices are comparison references, not direct triggers.",
)


@dataclass(frozen=True)
class HistoricalValidationEvent:
    event_id: str
    event_name: str
    start_date: str
    end_date: str
    pre_window_start: str
    pre_window_end: str
    event_type: HistoricalValidationEventType
    expected_archetype: str
    expected_pressure_groups: tuple[HistoricalValidationPressureGroup, ...]
    ordinary_pullback_flag: bool
    external_index_reference: tuple[str, ...]
    data_availability_constraints: tuple[str, ...]
    interpretation_boundary: tuple[str, ...]
    source_note: str

    def as_dict(self) -> dict[str, object]:
        return asdict(self)


def build_historical_validation_event_registry() -> list[HistoricalValidationEvent]:
    """Return the static D19 v0 historical reference-window registry."""

    return [
        HistoricalValidationEvent(
            event_id="dot_com_equity_valuation_unwind_2000",
            event_name="2000 dot-com equity valuation unwind",
            start_date="2000-03-01",
            end_date="2002-10-31",
            pre_window_start="1999-10-01",
            pre_window_end="2000-02-29",
            event_type="valuation_structure_research_window",
            expected_archetype="equity valuation unwind with breadth and earnings constraints",
            expected_pressure_groups=(
                "equity_structure",
                "valuation_earnings_breadth",
                "external_reference",
            ),
            ordinary_pullback_flag=False,
            external_index_reference=("NFCI", "STLFSI", "KCFSI"),
            data_availability_constraints=(
                "coarse_research_window",
                "older valuation and true-breadth inputs may be unavailable locally",
            ),
            interpretation_boundary=COMMON_INTERPRETATION_BOUNDARY
            + (
                "Valuation and concentration context cannot determine systemic stress by itself.",
            ),
            source_note=(
                "Recovered from Stage R1 event-note material as a broad historical "
                "reference window, not a scoring label."
            ),
        ),
        HistoricalValidationEvent(
            event_id="gfc_credit_funding_systemic_stress_2008",
            event_name="2008 GFC credit-funding systemic stress",
            start_date="2007-08-01",
            end_date="2009-03-31",
            pre_window_start="2007-04-01",
            pre_window_end="2007-07-31",
            event_type="systemic_stress_event",
            expected_archetype="broad credit, funding, volatility, and equity pressure",
            expected_pressure_groups=(
                "credit",
                "liquidity_funding",
                "equity_structure",
                "external_reference",
            ),
            ordinary_pullback_flag=False,
            external_index_reference=("NFCI", "STLFSI", "OFR FSI", "KCFSI"),
            data_availability_constraints=(
                "coarse_research_window",
                "local market-history coverage may be sparse before newer providers",
            ),
            interpretation_boundary=COMMON_INTERPRETATION_BOUNDARY
            + (
                "Systemic-stress context requires multiple pressure groups and cannot be inferred from one proxy.",
            ),
            source_note=(
                "Historical systemic-stress reference window from Stage R1 notes; "
                "used for explanation checks only."
            ),
        ),
        HistoricalValidationEvent(
            event_id="debt_ceiling_eurozone_stress_2011",
            event_name="2011 debt ceiling and eurozone stress",
            start_date="2011-07-01",
            end_date="2011-10-31",
            pre_window_start="2011-04-01",
            pre_window_end="2011-06-30",
            event_type="mixed_transition_event",
            expected_archetype="policy and external-reference stress with mixed transmission",
            expected_pressure_groups=(
                "credit",
                "liquidity_funding",
                "equity_structure",
                "external_reference",
            ),
            ordinary_pullback_flag=False,
            external_index_reference=("NFCI", "STLFSI", "OFR FSI", "KCFSI"),
            data_availability_constraints=(
                "coarse_research_window",
                "policy-risk context is descriptive and may not have a direct local metric",
            ),
            interpretation_boundary=COMMON_INTERPRETATION_BOUNDARY
            + (
                "External-reference agreement can support notes but cannot override project evidence rows.",
            ),
            source_note="Recovered Stage R1 candidate window for D19 event-note use.",
        ),
        HistoricalValidationEvent(
            event_id="oil_hy_energy_credit_stress_2015_2016",
            event_name="2015-2016 oil and high-yield energy credit stress",
            start_date="2015-08-01",
            end_date="2016-02-29",
            pre_window_start="2015-05-01",
            pre_window_end="2015-07-31",
            event_type="credit_stress_event",
            expected_archetype="energy-linked credit stress with mixed macro transmission",
            expected_pressure_groups=(
                "credit",
                "inflation_energy",
                "equity_structure",
                "external_reference",
            ),
            ordinary_pullback_flag=False,
            external_index_reference=("NFCI", "STLFSI", "KCFSI"),
            data_availability_constraints=(
                "sector-specific credit pressure may not be separately available",
                "energy and credit history may be incomplete locally",
            ),
            interpretation_boundary=COMMON_INTERPRETATION_BOUNDARY
            + (
                "Sector-specific credit pressure should not be generalized without broader evidence.",
            ),
            source_note="Recovered Stage R1 candidate window aligned with existing D19 oil/HY coverage.",
        ),
        HistoricalValidationEvent(
            event_id="q4_rates_liquidity_equity_stress_2018",
            event_name="2018 Q4 rates-liquidity-equity stress",
            start_date="2018-10-01",
            end_date="2018-12-31",
            pre_window_start="2018-07-01",
            pre_window_end="2018-09-30",
            event_type="ordinary_pullback",
            expected_archetype="ordinary pullback with rates pressure and equity damage",
            expected_pressure_groups=(
                "rates_real_yield",
                "credit",
                "equity_structure",
                "liquidity_funding",
            ),
            ordinary_pullback_flag=True,
            external_index_reference=("NFCI", "STLFSI", "KCFSI"),
            data_availability_constraints=(
                "true-breadth and valuation history may be unavailable locally",
            ),
            interpretation_boundary=COMMON_INTERPRETATION_BOUNDARY
            + (
                "An ordinary pullback should not be escalated to systemic stress without confirming groups.",
            ),
            source_note="Recovered Stage R1 candidate window and aligned with existing D19 2018 Q4 replay.",
        ),
        HistoricalValidationEvent(
            event_id="covid_liquidity_shock_2020",
            event_name="2020 COVID liquidity shock",
            start_date="2020-02-15",
            end_date="2020-04-30",
            pre_window_start="2020-01-01",
            pre_window_end="2020-02-14",
            event_type="liquidity_funding_event",
            expected_archetype="broad liquidity, credit, volatility, and labor-growth shock",
            expected_pressure_groups=(
                "credit",
                "liquidity_funding",
                "labor_growth",
                "equity_structure",
                "external_reference",
            ),
            ordinary_pullback_flag=False,
            external_index_reference=("NFCI", "STLFSI", "OFR FSI", "KCFSI"),
            data_availability_constraints=(
                "labor and funding inputs are required for full interpretation",
            ),
            interpretation_boundary=COMMON_INTERPRETATION_BOUNDARY
            + (
                "Historical shock recognition cannot be reused as a template for future event calls.",
            ),
            source_note="Recovered Stage R1 candidate window aligned with existing D19 COVID replay.",
        ),
        HistoricalValidationEvent(
            event_id="inflation_rates_pressure_2022",
            event_name="2022 inflation and rates pressure",
            start_date="2022-01-03",
            end_date="2022-10-31",
            pre_window_start="2021-10-01",
            pre_window_end="2021-12-31",
            event_type="inflation_rates_event",
            expected_archetype="inflation and real-yield pressure with mixed transmission",
            expected_pressure_groups=(
                "inflation_energy",
                "rates_real_yield",
                "credit",
                "equity_structure",
            ),
            ordinary_pullback_flag=False,
            external_index_reference=("NFCI", "STLFSI", "KCFSI"),
            data_availability_constraints=(
                "earnings and true-breadth history may be unavailable locally",
            ),
            interpretation_boundary=COMMON_INTERPRETATION_BOUNDARY
            + (
                "Rates and inflation evidence should be interpreted as pressure context only.",
            ),
            source_note="Recovered Stage R1 candidate window aligned with existing D19 2022 replay.",
        ),
        HistoricalValidationEvent(
            event_id="svb_regional_banking_liquidity_credit_stress_2023",
            event_name="2023 SVB regional banking liquidity-credit stress",
            start_date="2023-03-08",
            end_date="2023-03-31",
            pre_window_start="2023-02-01",
            pre_window_end="2023-03-07",
            event_type="liquidity_funding_event",
            expected_archetype="regional banking liquidity-credit stress with rates context",
            expected_pressure_groups=(
                "liquidity_funding",
                "credit",
                "rates_real_yield",
                "external_reference",
            ),
            ordinary_pullback_flag=False,
            external_index_reference=("NFCI", "STLFSI", "OFR FSI", "KCFSI"),
            data_availability_constraints=(
                "bank-specific stress inputs may be unavailable locally",
                "event context should remain separate from generic market timing",
            ),
            interpretation_boundary=COMMON_INTERPRETATION_BOUNDARY
            + (
                "Regional banking stress should remain event context unless broader evidence confirms transmission.",
            ),
            source_note="Recovered Stage R1 candidate window aligned with existing D19 SVB replay.",
        ),
        HistoricalValidationEvent(
            event_id="ai_concentration_valuation_structure_research_window_2024_2025",
            event_name="2024-2025 AI concentration valuation-structure research window",
            start_date="2024-01-01",
            end_date="2025-12-31",
            pre_window_start="2023-10-01",
            pre_window_end="2023-12-31",
            event_type="valuation_structure_research_window",
            expected_archetype="valuation, earnings, breadth, and concentration research constraint",
            expected_pressure_groups=(
                "rates_real_yield",
                "equity_structure",
                "valuation_earnings_breadth",
                "external_reference",
            ),
            ordinary_pullback_flag=False,
            external_index_reference=("NFCI", "STLFSI", "KCFSI"),
            data_availability_constraints=(
                "coarse_research_window",
                "full 2025 local history may not be complete",
                "valuation, earnings, and true-breadth inputs may require future safe integration",
            ),
            interpretation_boundary=COMMON_INTERPRETATION_BOUNDARY
            + (
                "Concentration proxies and valuation gaps cannot determine macro regime or systemic stress.",
            ),
            source_note="Recovered Stage R1 research window for D19 event-note use.",
        ),
    ]


def get_historical_validation_event_registry() -> list[dict[str, object]]:
    return [event.as_dict() for event in build_historical_validation_event_registry()]


def validate_historical_validation_event_registry(
    events: list[HistoricalValidationEvent] | None = None,
) -> None:
    event_list = events or build_historical_validation_event_registry()
    event_ids = [event.event_id for event in event_list]
    if len(event_ids) != len(set(event_ids)):
        raise ValueError("D19 event registry contains duplicate event_id values")
    for event in event_list:
        if event.event_type not in ALLOWED_EVENT_TYPES:
            raise ValueError(f"unsupported D19 event_type: {event.event_type}")
        unsupported_groups = set(event.expected_pressure_groups) - ALLOWED_PRESSURE_GROUPS
        if unsupported_groups:
            raise ValueError(
                f"unsupported D19 pressure groups for {event.event_id}: "
                f"{sorted(unsupported_groups)}"
            )
        if not event.event_name:
            raise ValueError(f"missing event_name for {event.event_id}")
        if not event.interpretation_boundary:
            raise ValueError(f"missing interpretation_boundary for {event.event_id}")
        if not event.data_availability_constraints:
            raise ValueError(f"missing data_availability_constraints for {event.event_id}")
        start = date.fromisoformat(event.start_date)
        end = date.fromisoformat(event.end_date)
        pre_start = date.fromisoformat(event.pre_window_start)
        pre_end = date.fromisoformat(event.pre_window_end)
        if start > end:
            raise ValueError(f"invalid event window for {event.event_id}")
        if pre_start > pre_end or pre_end >= start:
            raise ValueError(f"invalid pre-window for {event.event_id}")
