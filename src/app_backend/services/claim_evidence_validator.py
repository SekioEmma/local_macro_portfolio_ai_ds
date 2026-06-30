"""Validate MacroBrief claims against the current run evidence ledger."""
from __future__ import annotations

from app_backend.schemas.macro_brief import MacroBrief
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
        findings.extend(_validate_fact_records(fact.id, fact.claim_status, fact_records))

    for index, judgment in enumerate(brief.judgments):
        if not judgment.evidence_ids:
            continue
        missing = [evidence_id for evidence_id in judgment.evidence_ids if evidence_id not in records]
        if missing:
            findings.append(f"judgments[{index}].unknown_evidence_ids:{','.join(missing)}")

    return findings


def _validate_fact_records(
    fact_id: str,
    claim_status: str,
    records: list[EvidenceRecord],
) -> list[str]:
    findings: list[str] = []
    if claim_status == "observed":
        if not any(record.temporal_status == "observed" for record in records):
            findings.append(f"confirmed_facts[{fact_id}].observed_without_observed_evidence")
        if any(record.evidence_tier == "institutional_view" for record in records):
            findings.append(f"confirmed_facts[{fact_id}].observed_uses_institutional_view")
    if claim_status == "reported":
        if any(
            record.evidence_tier == "institutional_view"
            and record.source_kind != "institutional_research"
            for record in records
        ):
            findings.append(f"confirmed_facts[{fact_id}].institutional_view_source_kind_mismatch")
    return findings


__all__ = ["validate_macro_brief_claim_evidence"]
