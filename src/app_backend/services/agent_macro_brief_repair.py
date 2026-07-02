"""Deterministic repairs for common MacroBrief finalize errors."""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app_backend.services.run_evidence_ledger import (
    AtomicObservation,
    EvidenceRecord,
    RunEvidenceLedger,
)


class MacroBriefRepairResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    payload: dict[str, Any]
    actions: list[str] = Field(default_factory=list)


def repair_macro_brief_payload(
    payload: Mapping[str, Any],
    ledger: RunEvidenceLedger,
) -> MacroBriefRepairResult:
    records = ledger.by_id()
    data = dict(payload)
    actions: list[str] = []
    repaired_facts: list[dict[str, Any]] = []
    kept_fact_ids: set[str] = set()

    for raw_fact in _as_list(data.get("confirmed_facts")):
        if not isinstance(raw_fact, Mapping):
            actions.append("drop_non_object_fact")
            continue
        fact = dict(raw_fact)
        fact_id = str(fact.get("id") or f"fact_{len(repaired_facts) + 1}")
        fact["id"] = fact_id
        evidence_ids = _string_list(fact.get("evidence_ids"))
        valid_records = [records[evidence_id] for evidence_id in evidence_ids if evidence_id in records]
        if not evidence_ids or not valid_records:
            actions.append(f"drop_fact_without_known_evidence:{fact_id}")
            continue
        fact["evidence_ids"] = [record.evidence_id for record in valid_records]

        claim_status = fact.get("claim_status")
        if claim_status == "unavailable":
            actions.append(f"drop_unavailable_fact:{fact_id}")
            continue
        if claim_status == "observed":
            observation_pair = _first_observed_atomic(valid_records)
            if observation_pair is None:
                fact["claim_status"] = "reported"
                fact["value"] = None
                fact["unit"] = None
                fact["as_of"] = None
                actions.append(f"observed_to_reported_without_atomic:{fact_id}")
            else:
                record, observation = observation_pair
                fact["value"] = observation.value
                fact["unit"] = observation.unit
                fact["as_of"] = observation.as_of or record.observation_date
                actions.append(f"observed_filled_from_atomic:{fact_id}")
        elif claim_status == "reported":
            if fact.get("value") is None:
                if fact.get("unit") is not None or fact.get("as_of") is not None:
                    actions.append(f"reported_cleared_unit_as_of_without_value:{fact_id}")
                fact["unit"] = None
                fact["as_of"] = None
            elif not _reported_value_matches(fact, valid_records):
                fact["value"] = None
                fact["unit"] = None
                fact["as_of"] = None
                actions.append(f"reported_cleared_mismatched_value:{fact_id}")
        else:
            fact["claim_status"] = "reported"
            fact["value"] = None
            fact["unit"] = None
            fact["as_of"] = None
            actions.append(f"unknown_status_to_reported:{fact_id}")

        repaired_facts.append(fact)
        kept_fact_ids.add(fact_id)

    data["confirmed_facts"] = repaired_facts
    data["judgments"] = _repair_judgments(data.get("judgments"), kept_fact_ids, actions)
    return MacroBriefRepairResult(payload=data, actions=actions)


def _repair_judgments(
    value: Any,
    kept_fact_ids: set[str],
    actions: list[str],
) -> list[dict[str, Any]]:
    repaired: list[dict[str, Any]] = []
    for index, raw_judgment in enumerate(_as_list(value)):
        if not isinstance(raw_judgment, Mapping):
            actions.append(f"drop_non_object_judgment:{index}")
            continue
        judgment = dict(raw_judgment)
        supports = [fact_id for fact_id in _string_list(judgment.get("evidence_supports")) if fact_id in kept_fact_ids]
        if not supports:
            actions.append(f"drop_judgment_without_supported_fact:{index}")
            continue
        judgment["evidence_supports"] = supports
        repaired.append(judgment)
    return repaired


def _first_observed_atomic(
    records: list[EvidenceRecord],
) -> tuple[EvidenceRecord, AtomicObservation] | None:
    for record in records:
        if record.temporal_status != "observed":
            continue
        if record.evidence_tier == "institutional_view":
            continue
        for observation in record.atomic_observations:
            return record, observation
    return None


def _reported_value_matches(fact: Mapping[str, Any], records: list[EvidenceRecord]) -> bool:
    for record in records:
        for observation in record.atomic_observations:
            if str(fact.get("value")).strip() != str(observation.value).strip():
                continue
            unit = fact.get("unit")
            if unit is not None and str(unit).strip() != str(observation.unit or "").strip():
                continue
            as_of = fact.get("as_of")
            observation_as_of = observation.as_of or record.observation_date
            if as_of is not None and str(as_of).strip() != str(observation_as_of or "").strip():
                continue
            return True
    return False


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str) and item]


__all__ = ["MacroBriefRepairResult", "repair_macro_brief_payload"]
