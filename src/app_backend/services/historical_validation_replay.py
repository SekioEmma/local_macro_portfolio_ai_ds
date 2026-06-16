from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Literal

from app_backend.services.historical_validation_event_registry import (
    HistoricalValidationEvent,
    build_historical_validation_event_registry,
)


HistoricalValidationReplayStatus = Literal[
    "available",
    "limited",
    "insufficient",
    "reference_only",
]

ALLOWED_VALIDATION_STATUSES: frozenset[str] = frozenset(
    HistoricalValidationReplayStatus.__args__
)

STATUS_BOUNDARY_NOTE = (
    "reference_only and limited statuses are evidence-coverage states, not low-risk labels"
)

D19_V1_EVENT_ID_ALIASES: dict[str, tuple[str, ...]] = {
    "debt_ceiling_eurozone_stress_2011": ("2011_euro_debt_us_downgrade_stress",),
    "oil_hy_energy_credit_stress_2015_2016": (
        "2015_2016_oil_hy_energy_stress",
        "2016_global_growth_oil_credit_stress",
    ),
    "q4_rates_liquidity_equity_stress_2018": (
        "2018_q4_tightening_scare",
        "2018_volmageddon_liquidity_shock",
    ),
    "covid_liquidity_shock_2020": ("2020_covid_shock",),
    "inflation_rates_pressure_2022": (
        "2021_reopening_inflation_pressure",
        "2022_inflation_rates_bear_market",
    ),
    "svb_regional_banking_liquidity_credit_stress_2023": (
        "2023_svb_bank_stress",
    ),
    "ai_concentration_valuation_structure_research_window_2024_2025": (
        "2024_rates_concentration_watch",
        "2025_ai_concentration_rates_watch",
    ),
}


@dataclass(frozen=True)
class HistoricalValidationReplayRow:
    event_id: str
    event_name: str
    event_type: str
    window: dict[str, str]
    pre_window: dict[str, str]
    expected_pressure_groups: tuple[str, ...]
    expected_archetype: str
    ordinary_pullback_flag: bool
    available_model_outputs: tuple[str, ...]
    missing_or_limited_inputs: tuple[str, ...]
    external_reference_notes: tuple[str, ...]
    interpretation_boundary: tuple[str, ...]
    validation_status: HistoricalValidationReplayStatus
    validation_notes: tuple[str, ...]
    source_summary_event_ids: tuple[str, ...]
    coverage_statuses: tuple[str, ...]
    window_statuses: tuple[str, ...]
    available_day_count: int
    insufficient_history_day_count: int
    dominant_labels: tuple[str, ...]
    blocked_inputs: tuple[str, ...]
    boundary_violation_flags: tuple[str, ...]
    boundary_violation_count: int
    proxy_constraints: dict[str, object]
    missing_data_summary: dict[str, int]
    compact_validation_metadata: dict[str, object]

    def as_dict(self) -> dict[str, object]:
        return asdict(self)


def build_historical_validation_replay_rows(
    events: list[HistoricalValidationEvent] | None = None,
    existing_summary: dict[str, Any] | None = None,
) -> list[HistoricalValidationReplayRow]:
    """Build read-only D19 v0 replay rows from static event references."""

    event_list = events or build_historical_validation_event_registry()
    summary_by_event_id = _summary_events_by_id(existing_summary)
    return [
        _build_replay_row(event, summary_by_event_id.get(event.event_id))
        for event in event_list
    ]


def get_historical_validation_replay_rows(
    events: list[HistoricalValidationEvent] | None = None,
    existing_summary: dict[str, Any] | None = None,
) -> list[dict[str, object]]:
    return [
        row.as_dict()
        for row in build_historical_validation_replay_rows(
            events=events,
            existing_summary=existing_summary,
        )
    ]


def _build_replay_row(
    event: HistoricalValidationEvent,
    existing_event_summaries: list[dict[str, Any]] | None,
) -> HistoricalValidationReplayRow:
    summaries = existing_event_summaries or []
    status = _validation_status(summaries)
    available_outputs = _available_outputs(summaries)
    missing_inputs = _missing_or_limited_inputs(event, summaries)
    notes = _validation_notes(event, status, summaries)
    boundary_flags = _tuple_union(summaries, "boundary_violation_flags")
    proxy_constraints = _proxy_constraints(summaries)
    missing_data_summary = _missing_data_summary(summaries)
    return HistoricalValidationReplayRow(
        event_id=event.event_id,
        event_name=event.event_name,
        event_type=event.event_type,
        window={"start": event.start_date, "end": event.end_date},
        pre_window={"start": event.pre_window_start, "end": event.pre_window_end},
        expected_pressure_groups=tuple(event.expected_pressure_groups),
        expected_archetype=event.expected_archetype,
        ordinary_pullback_flag=event.ordinary_pullback_flag,
        available_model_outputs=available_outputs,
        missing_or_limited_inputs=missing_inputs,
        external_reference_notes=tuple(event.external_index_reference),
        interpretation_boundary=event.interpretation_boundary,
        validation_status=status,
        validation_notes=notes,
        source_summary_event_ids=tuple(
            str(summary["event_id"])
            for summary in summaries
            if summary.get("event_id")
        ),
        coverage_statuses=tuple(
            str(summary.get("coverage_status"))
            for summary in summaries
            if summary.get("coverage_status")
        ),
        window_statuses=tuple(
            str(summary.get("window_status"))
            for summary in summaries
            if summary.get("window_status")
        ),
        available_day_count=sum(_int_value(summary, "available_day_count") for summary in summaries),
        insufficient_history_day_count=sum(
            _int_value(summary, "insufficient_history_day_count")
            for summary in summaries
        ),
        dominant_labels=_tuple_union(summaries, "dominant_labels"),
        blocked_inputs=_tuple_union(summaries, "blocked_inputs"),
        boundary_violation_flags=boundary_flags,
        boundary_violation_count=len(boundary_flags),
        proxy_constraints=proxy_constraints,
        missing_data_summary=missing_data_summary,
        compact_validation_metadata={
            "has_summary": bool(summaries),
            "source_summary_event_count": len(summaries),
            "coverage_statuses": tuple(
                str(summary.get("coverage_status"))
                for summary in summaries
                if summary.get("coverage_status")
            ),
            "available_day_count": sum(
                _int_value(summary, "available_day_count") for summary in summaries
            ),
            "missing_input_count": len(missing_inputs),
            "boundary_violation_count": len(boundary_flags),
            "proxy_metric_keys": tuple(proxy_constraints.get("proxy_metric_keys", ())),
        },
    )


def _summary_events_by_id(existing_summary: dict[str, Any] | None) -> dict[str, list[dict[str, Any]]]:
    if not existing_summary:
        return {}
    events = existing_summary.get("events")
    if not isinstance(events, list):
        return {}
    by_source_event_id = {
        str(event["event_id"]): event
        for event in events
        if isinstance(event, dict) and event.get("event_id")
    }
    result = {
        event_id: [event]
        for event_id, event in by_source_event_id.items()
    }
    for registry_event_id, source_event_ids in D19_V1_EVENT_ID_ALIASES.items():
        matches = [
            by_source_event_id[source_event_id]
            for source_event_id in source_event_ids
            if source_event_id in by_source_event_id
        ]
        if matches and registry_event_id not in result:
            result[registry_event_id] = matches
    return result


def _validation_status(
    existing_event_summaries: list[dict[str, Any]],
) -> HistoricalValidationReplayStatus:
    if not existing_event_summaries:
        return "reference_only"
    coverage_statuses = {
        str(summary.get("coverage_status", ""))
        for summary in existing_event_summaries
    }
    if coverage_statuses == {"available"}:
        return "available"
    if coverage_statuses & {"available", "limited_replay"}:
        return "limited"
    return "insufficient"


def _available_outputs(existing_event_summaries: list[dict[str, Any]]) -> tuple[str, ...]:
    return _tuple_union(existing_event_summaries, "dominant_primary_pressure_groups")


def _missing_or_limited_inputs(
    event: HistoricalValidationEvent,
    existing_event_summaries: list[dict[str, Any]],
) -> tuple[str, ...]:
    if not existing_event_summaries:
        return tuple(event.data_availability_constraints)
    missing_inputs = _tuple_union(existing_event_summaries, "missing_inputs")
    if missing_inputs:
        return missing_inputs
    if _validation_status(existing_event_summaries) in {"limited", "insufficient"}:
        return tuple(event.data_availability_constraints)
    return ()


def _validation_notes(
    event: HistoricalValidationEvent,
    status: HistoricalValidationReplayStatus,
    existing_event_summaries: list[dict[str, Any]],
) -> tuple[str, ...]:
    notes = [
        "D19 v0 row is a historical interpretation scaffold.",
        STATUS_BOUNDARY_NOTE,
    ]
    if status == "reference_only":
        notes.append("No local historical replay summary was connected for this event id.")
    elif status == "available":
        notes.append("Existing summary reports local evidence coverage for this event id.")
    elif status == "limited":
        notes.append("Existing summary reports partial local evidence coverage for this event id.")
    else:
        notes.append("Existing summary reports insufficient local evidence coverage for this event id.")
    if event.ordinary_pullback_flag:
        notes.append("Ordinary pullback windows require confirmation before stress escalation.")
    if _tuple_union(existing_event_summaries, "boundary_violation_flags"):
        notes.append("Existing summary reports boundary items that require review.")
    return tuple(notes)


def _tuple_union(summaries: list[dict[str, Any]], key: str) -> tuple[str, ...]:
    values: list[str] = []
    seen: set[str] = set()
    for summary in summaries:
        items = summary.get(key, ())
        if not isinstance(items, (list, tuple)):
            continue
        for item in items:
            value = str(item)
            if value and value not in seen:
                seen.add(value)
                values.append(value)
    return tuple(values)


def _missing_data_summary(summaries: list[dict[str, Any]]) -> dict[str, int]:
    result: dict[str, int] = {}
    for summary in summaries:
        items = summary.get("missing_data_summary", {})
        if not isinstance(items, dict):
            continue
        for key, value in items.items():
            result[str(key)] = result.get(str(key), 0) + int(value or 0)
    return dict(sorted(result.items()))


def _proxy_constraints(summaries: list[dict[str, Any]]) -> dict[str, object]:
    proxy_keys: list[str] = []
    for summary in summaries:
        constraints = summary.get("proxy_constraints", {})
        if not isinstance(constraints, dict):
            continue
        for key in constraints.get("proxy_metric_keys", ()):
            value = str(key)
            if value and value not in proxy_keys:
                proxy_keys.append(value)
    return {
        "proxy_metric_keys": tuple(proxy_keys),
        "proxy_only_evidence_remains_auxiliary": True,
        "proxy_cannot_satisfy_required_groups": True,
    }


def _int_value(summary: dict[str, Any], key: str) -> int:
    value = summary.get(key, 0)
    return value if isinstance(value, int) else 0
