"""Build writer-facing evidence packs from planned tool evidence."""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from app_backend.services.agent_tool_plan_runner import PlannedToolOutcome
from app_backend.services.run_evidence_ledger import (
    AtomicObservation,
    EvidenceRecord,
    RunEvidenceLedger,
)


CandidateClaimStatus = Literal["observed", "reported"]


class EvidenceCard(BaseModel):
    model_config = ConfigDict(extra="forbid")

    evidence_id: str
    tool_name: str
    title: str
    evidence_tier: str
    source_kind: str
    canonical_url: str | None = None
    rag_doc_id: str | None = None
    as_of: str | None = None
    temporal_status: str
    value_summary: dict[str, Any] = Field(default_factory=dict)
    atomic_observations: list[AtomicObservation] = Field(default_factory=list)
    public_visible: bool = False


class CandidateFact(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    statement: str
    evidence_ids: list[str]
    claim_status: CandidateClaimStatus
    value: str | float | int | None = None
    unit: str | None = None
    as_of: str | None = None
    source_id: str = "auto"

    def to_macro_brief_fact(self) -> dict[str, Any]:
        return self.model_dump(mode="json")


class EvidencePack(BaseModel):
    model_config = ConfigDict(extra="forbid")

    cards: list[EvidenceCard] = Field(default_factory=list)
    candidate_facts: list[CandidateFact] = Field(default_factory=list)
    unavailable_topics: list[str] = Field(default_factory=list)
    tool_outcomes: list[dict[str, Any]] = Field(default_factory=list)


def build_evidence_pack(
    *,
    ledger: RunEvidenceLedger | None,
    outcomes: list[PlannedToolOutcome],
) -> EvidencePack:
    records = list(ledger.records) if ledger is not None else []
    cards = [_card_from_record(record) for record in records]
    candidate_facts = _candidate_facts_from_records(records)
    unavailable_topics = [
        outcome.topic
        for outcome in outcomes
        if _outcome_unavailable(outcome) and outcome.topic not in {"finalize"}
    ]
    return EvidencePack(
        cards=cards,
        candidate_facts=candidate_facts,
        unavailable_topics=list(dict.fromkeys(unavailable_topics)),
        tool_outcomes=[_summarize_outcome(outcome) for outcome in outcomes],
    )


def _card_from_record(record: EvidenceRecord) -> EvidenceCard:
    return EvidenceCard(
        evidence_id=record.evidence_id,
        tool_name=record.tool_name,
        title=record.title,
        evidence_tier=record.evidence_tier,
        source_kind=record.source_kind,
        canonical_url=record.canonical_url,
        rag_doc_id=record.rag_doc_id,
        as_of=record.observation_date or record.release_date,
        temporal_status=record.temporal_status,
        value_summary=dict(record.value_summary),
        atomic_observations=list(record.atomic_observations),
        public_visible=record.public_visible,
    )


def _candidate_facts_from_records(records: list[EvidenceRecord]) -> list[CandidateFact]:
    facts: list[CandidateFact] = []
    for record in records:
        if (
            record.temporal_status == "observed"
            and record.evidence_tier != "institutional_view"
            and record.atomic_observations
        ):
            for observation in record.atomic_observations:
                facts.append(_observed_candidate(record, observation, len(facts) + 1))
            continue
        facts.append(_reported_candidate(record, len(facts) + 1))
    return facts


def _observed_candidate(
    record: EvidenceRecord,
    observation: AtomicObservation,
    index: int,
) -> CandidateFact:
    as_of = observation.as_of or record.observation_date
    unit = observation.unit
    statement_parts = [record.title, f"value {observation.value}"]
    if unit:
        statement_parts.append(unit)
    if as_of:
        statement_parts.append(f"as of {as_of}")
    return CandidateFact(
        id=f"cf{index}",
        statement="; ".join(statement_parts),
        evidence_ids=[record.evidence_id],
        claim_status="observed",
        value=observation.value,
        unit=unit,
        as_of=as_of,
    )


def _reported_candidate(record: EvidenceRecord, index: int) -> CandidateFact:
    return CandidateFact(
        id=f"cf{index}",
        statement=_reported_statement(record),
        evidence_ids=[record.evidence_id],
        claim_status="reported",
        value=None,
        unit=None,
        as_of=None,
    )


def _reported_statement(record: EvidenceRecord) -> str:
    detail = record.value_summary.get("status") or record.temporal_status
    if detail:
        return f"{record.title}; reported context: {detail}"
    return record.title


def _summarize_outcome(outcome: PlannedToolOutcome) -> dict[str, Any]:
    return {
        "topic": outcome.topic,
        "tool_name": outcome.tool_name,
        "status": outcome.status,
        "required": outcome.required,
        "error_code": outcome.error_code,
        "evidence_ids": list(outcome.evidence_ids),
    }


def _outcome_unavailable(outcome: PlannedToolOutcome) -> bool:
    if outcome.status != "ok":
        return True
    content = outcome.content
    if not isinstance(content, dict):
        return False
    if content.get("status") == "unavailable":
        return True
    if outcome.tool_name == "rag_retrieve" and content.get("chunk_count") == 0:
        return True
    if outcome.tool_name == "search_tavily" and content.get("result_count") == 0:
        return True
    if outcome.tool_name == "calendar_lookup" and content.get("events") == []:
        return True
    if outcome.tool_name == "quote_etf" and _all_quotes_unavailable(content.get("quotes")):
        return True
    return False


def _all_quotes_unavailable(quotes: object) -> bool:
    if not isinstance(quotes, list) or not quotes:
        return False
    quote_dicts = [quote for quote in quotes if isinstance(quote, dict)]
    if not quote_dicts:
        return False
    return all(quote.get("value") is None for quote in quote_dicts)


__all__ = [
    "CandidateFact",
    "EvidenceCard",
    "EvidencePack",
    "build_evidence_pack",
]
