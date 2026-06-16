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
    existing_event_summary: dict[str, Any] | None,
) -> HistoricalValidationReplayRow:
    status = _validation_status(existing_event_summary)
    available_outputs = _available_outputs(existing_event_summary)
    missing_inputs = _missing_or_limited_inputs(event, existing_event_summary)
    notes = _validation_notes(event, status, existing_event_summary)
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
    )


def _summary_events_by_id(existing_summary: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
    if not existing_summary:
        return {}
    events = existing_summary.get("events")
    if not isinstance(events, list):
        return {}
    return {
        str(event["event_id"]): event
        for event in events
        if isinstance(event, dict) and event.get("event_id")
    }


def _validation_status(
    existing_event_summary: dict[str, Any] | None,
) -> HistoricalValidationReplayStatus:
    if not existing_event_summary:
        return "reference_only"
    coverage_status = str(existing_event_summary.get("coverage_status", ""))
    if coverage_status == "available":
        return "available"
    if coverage_status == "limited_replay":
        return "limited"
    return "insufficient"


def _available_outputs(existing_event_summary: dict[str, Any] | None) -> tuple[str, ...]:
    if not existing_event_summary:
        return ()
    dominant_groups = existing_event_summary.get("dominant_primary_pressure_groups", ())
    if not isinstance(dominant_groups, (list, tuple)):
        return ()
    return tuple(str(group) for group in dominant_groups)


def _missing_or_limited_inputs(
    event: HistoricalValidationEvent,
    existing_event_summary: dict[str, Any] | None,
) -> tuple[str, ...]:
    if existing_event_summary is None:
        return tuple(event.data_availability_constraints)
    missing_inputs = existing_event_summary.get("missing_inputs", ())
    if isinstance(missing_inputs, (list, tuple)) and missing_inputs:
        return tuple(str(item) for item in missing_inputs)
    if _validation_status(existing_event_summary) in {"limited", "insufficient"}:
        return tuple(event.data_availability_constraints)
    return ()


def _validation_notes(
    event: HistoricalValidationEvent,
    status: HistoricalValidationReplayStatus,
    existing_event_summary: dict[str, Any] | None,
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
    if existing_event_summary and existing_event_summary.get("boundary_violations"):
        notes.append("Existing summary reports boundary items that require review.")
    return tuple(notes)
