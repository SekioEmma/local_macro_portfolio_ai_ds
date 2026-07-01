"""Run-scoped evidence ledger contracts for Phase F MacroBrief validation."""
from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


SourceKind = Literal[
    "official_primary",
    "public_reporting",
    "institutional_research",
    "licensed_manual_data",
    "local_data_foundation",
    "unavailable",
]
EvidenceTier = Literal[
    "official_evidence",
    "public_reporting",
    "institutional_view",
    "licensed_manual_data",
    "local_data_foundation",
    "unavailable",
]
TemporalStatus = Literal["observed", "reported", "as_released", "unavailable"]


class AtomicObservation(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    value: str | float | int = Field()
    unit: str | None = Field(default=None, max_length=80)
    as_of: str | None = Field(default=None, max_length=40)
    series_id: str | None = Field(default=None, max_length=128)


class EvidenceRecord(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    evidence_id: str = Field(min_length=1, max_length=128)
    run_id: str = Field(min_length=1, max_length=128)
    tool_name: str = Field(min_length=1, max_length=128)
    source_kind: SourceKind
    evidence_tier: EvidenceTier
    title: str = Field(min_length=1, max_length=500)
    canonical_url: str | None = Field(default=None, max_length=1000)
    rag_doc_id: str | None = Field(default=None, max_length=256)
    series_id: str | None = Field(default=None, max_length=128)
    observation_date: str | None = Field(default=None, max_length=40)
    release_date: str | None = Field(default=None, max_length=40)
    accessed_at: str = Field(default_factory=lambda: datetime.now(UTC).isoformat(), max_length=40)
    temporal_status: TemporalStatus = "observed"
    value_summary: dict[str, Any] = Field(default_factory=dict)
    atomic_observations: tuple[AtomicObservation, ...] = ()
    content_sha256: str | None = Field(default=None, min_length=64, max_length=64)
    public_visible: bool = False


class RunEvidenceLedger(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    run_id: str = Field(min_length=1, max_length=128)
    records: tuple[EvidenceRecord, ...] = ()

    def by_id(self) -> dict[str, EvidenceRecord]:
        return {record.evidence_id: record for record in self.records}

    def add(self, record: EvidenceRecord) -> "RunEvidenceLedger":
        if record.run_id != self.run_id:
            raise ValueError("evidence record run_id does not match ledger")
        if record.evidence_id in self.by_id():
            raise ValueError(f"duplicate evidence_id: {record.evidence_id}")
        return self.model_copy(update={"records": (*self.records, record)})


def sha256_json_summary(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


__all__ = [
    "AtomicObservation",
    "EvidenceRecord",
    "EvidenceTier",
    "RunEvidenceLedger",
    "SourceKind",
    "TemporalStatus",
    "sha256_json_summary",
]
