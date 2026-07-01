"""Validate MacroBrief claims against the current run evidence ledger."""
from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any

from app_backend.schemas.macro_brief import ConfirmedFact, MacroBrief
from app_backend.services.run_evidence_ledger import EvidenceRecord, RunEvidenceLedger


def validate_macro_brief_claim_evidence(
    brief: MacroBrief,
    ledger: RunEvidenceLedger,
) -> list[str]:
    records = ledger.by_id()
    findings: list[str] = []

    for fact in brief.confirmed_facts:
        if not fact.evidence_ids:
            findings.append(f"confirmed_facts[{fact.id}].missing_evidence_ids")
            continue
        missing = [evidence_id for evidence_id in fact.evidence_ids if evidence_id not in records]
        if missing:
            findings.append(f"confirmed_facts[{fact.id}].unknown_evidence_ids:{','.join(missing)}")
            continue
        fact_records = [records[evidence_id] for evidence_id in fact.evidence_ids]
        findings.extend(_validate_fact_records(fact, fact_records))

    for index, judgment in enumerate(brief.judgments):
        if not judgment.evidence_ids:
            continue
        missing = [evidence_id for evidence_id in judgment.evidence_ids if evidence_id not in records]
        if missing:
            findings.append(f"judgments[{index}].unknown_evidence_ids:{','.join(missing)}")

    return findings


def _validate_fact_records(
    fact: ConfirmedFact,
    records: list[EvidenceRecord],
) -> list[str]:
    findings: list[str] = []
    if fact.claim_status == "observed":
        if not any(record.temporal_status == "observed" for record in records):
            findings.append(f"confirmed_facts[{fact.id}].observed_without_observed_evidence")
        if any(record.evidence_tier == "institutional_view" for record in records):
            findings.append(f"confirmed_facts[{fact.id}].observed_uses_institutional_view")
        findings.extend(_validate_observed_atomic_observation(fact, records))
    if fact.claim_status == "reported":
        if any(
            record.evidence_tier == "institutional_view"
            and record.source_kind != "institutional_research"
            for record in records
        ):
            findings.append(f"confirmed_facts[{fact.id}].institutional_view_source_kind_mismatch")
        findings.extend(_validate_reported_atomic_observation(fact, records))
    if fact.claim_status == "unavailable":
        if fact.value is not None or fact.unit is not None or fact.as_of is not None:
            findings.append(f"confirmed_facts[{fact.id}].unavailable_has_structured_value")
    return findings


def _validate_observed_atomic_observation(
    fact: ConfirmedFact,
    records: list[EvidenceRecord],
) -> list[str]:
    if fact.value is None:
        return [f"confirmed_facts[{fact.id}].observed_missing_value"]
    observed_records = [record for record in records if record.temporal_status == "observed"]
    observations = [
        (record, observation)
        for record in observed_records
        for observation in record.atomic_observations
    ]
    if not observations:
        return [f"confirmed_facts[{fact.id}].observed_without_atomic_observation"]
    if any(
        _atomic_observation_matches(
            fact_value=fact.value,
            fact_unit=fact.unit,
            fact_as_of=fact.as_of,
            record=record,
            observation_value=observation.value,
            observation_unit=observation.unit,
            observation_as_of=observation.as_of,
        )
        for record, observation in observations
    ):
        return []
    return [f"confirmed_facts[{fact.id}].atomic_observation_mismatch"]


def _validate_reported_atomic_observation(
    fact: ConfirmedFact,
    records: list[EvidenceRecord],
) -> list[str]:
    if fact.value is None:
        if fact.unit is not None or fact.as_of is not None:
            return [f"confirmed_facts[{fact.id}].reported_value_missing_with_unit_or_as_of"]
        return []
    observations = [
        (record, observation)
        for record in records
        for observation in record.atomic_observations
    ]
    if not observations:
        return [f"confirmed_facts[{fact.id}].reported_without_atomic_observation"]
    if any(
        _reported_atomic_observation_matches(
            fact_value=fact.value,
            fact_unit=fact.unit,
            fact_as_of=fact.as_of,
            record=record,
            observation_value=observation.value,
            observation_unit=observation.unit,
            observation_as_of=observation.as_of,
        )
        for record, observation in observations
    ):
        return []
    return [f"confirmed_facts[{fact.id}].reported_atomic_observation_mismatch"]


def _atomic_observation_matches(
    *,
    fact_value: Any,
    fact_unit: str | None,
    fact_as_of: str | None,
    record: EvidenceRecord,
    observation_value: Any,
    observation_unit: str | None,
    observation_as_of: str | None,
) -> bool:
    return (
        _values_equal(fact_value, observation_value)
        and _optional_text_equal(fact_unit, observation_unit)
        and _optional_text_equal(fact_as_of, observation_as_of or record.observation_date)
    )


def _reported_atomic_observation_matches(
    *,
    fact_value: Any,
    fact_unit: str | None,
    fact_as_of: str | None,
    record: EvidenceRecord,
    observation_value: Any,
    observation_unit: str | None,
    observation_as_of: str | None,
) -> bool:
    if not _values_equal(fact_value, observation_value):
        return False
    if fact_unit is not None and not _optional_text_equal(fact_unit, observation_unit):
        return False
    if fact_as_of is not None and not _optional_text_equal(
        fact_as_of,
        observation_as_of or record.observation_date,
    ):
        return False
    return True


def _values_equal(left: Any, right: Any) -> bool:
    left_decimal = _decimal_or_none(left)
    right_decimal = _decimal_or_none(right)
    if left_decimal is not None and right_decimal is not None:
        return left_decimal == right_decimal
    return str(left).strip() == str(right).strip()


def _decimal_or_none(value: Any) -> Decimal | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int | float | str):
        text = str(value).strip()
        if not text:
            return None
        try:
            return Decimal(text)
        except InvalidOperation:
            return None
    return None


def _optional_text_equal(left: str | None, right: str | None) -> bool:
    return _normalize_optional_text(left) == _normalize_optional_text(right)


def _normalize_optional_text(value: str | None) -> str | None:
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None


__all__ = ["validate_macro_brief_claim_evidence"]
