"""Project MacroBrief source fields from the run evidence ledger."""
from __future__ import annotations

import hashlib
from collections.abc import Mapping
from typing import Any

from app_backend.services.run_evidence_ledger import EvidenceRecord, RunEvidenceLedger


def project_macro_brief_sources_from_ledger(
    payload: Mapping[str, Any],
    ledger: RunEvidenceLedger,
) -> dict[str, Any]:
    """Return a MacroBrief payload with server-owned source ids/list.

    The LLM may still emit ``source_id`` and ``source_list`` for schema
    compatibility, but when a run ledger is present, the runtime projects
    source fields from ``evidence_ids`` before validation.
    """
    data = dict(payload)
    records = ledger.by_id()
    source_ids_by_evidence = {
        evidence_id: _source_id_for_evidence(evidence_id)
        for evidence_id in _used_evidence_ids(data)
    }
    data["confirmed_facts"] = [
        _project_fact_source_id(fact, source_ids_by_evidence)
        for fact in _as_list(data.get("confirmed_facts"))
    ]
    data["source_list"] = [
        _source_item_for_evidence(
            evidence_id=evidence_id,
            source_id=source_id,
            record=records.get(evidence_id),
        )
        for evidence_id, source_id in source_ids_by_evidence.items()
    ]
    return data


def _project_fact_source_id(
    fact: Any,
    source_ids_by_evidence: dict[str, str],
) -> Any:
    if not isinstance(fact, Mapping):
        return fact
    updated = dict(fact)
    evidence_ids = _string_list(updated.get("evidence_ids"))
    if evidence_ids:
        updated["source_id"] = source_ids_by_evidence[evidence_ids[0]]
    return updated


def _source_item_for_evidence(
    *,
    evidence_id: str,
    source_id: str,
    record: EvidenceRecord | None,
) -> dict[str, Any]:
    if record is None:
        return {
            "id": source_id,
            "accessed_at": "unknown",
            "title": f"Unknown run evidence: {evidence_id}",
        }
    return {
        "id": source_id,
        "url": record.canonical_url,
        "rag_doc_id": record.rag_doc_id,
        "accessed_at": record.accessed_at,
        "title": record.title,
    }


def _used_evidence_ids(payload: Mapping[str, Any]) -> list[str]:
    ordered: list[str] = []
    for fact in _as_list(payload.get("confirmed_facts")):
        if isinstance(fact, Mapping):
            ordered.extend(_string_list(fact.get("evidence_ids")))
    for judgment in _as_list(payload.get("judgments")):
        if isinstance(judgment, Mapping):
            ordered.extend(_string_list(judgment.get("evidence_ids")))
    return list(dict.fromkeys(ordered))


def _source_id_for_evidence(evidence_id: str) -> str:
    candidate = f"src_{evidence_id}"
    if len(candidate) <= 64:
        return candidate
    digest = hashlib.sha256(evidence_id.encode("utf-8")).hexdigest()[:16]
    return f"src_{digest}"


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str) and item]


__all__ = ["project_macro_brief_sources_from_ledger"]
