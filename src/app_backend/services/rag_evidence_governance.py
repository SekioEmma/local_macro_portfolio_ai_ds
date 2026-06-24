"""Phase D0 RAG evidence governance contracts.

Pure, in-memory, metadata-only admission contract for caller-supplied
document descriptors. Validates descriptor shape, normalises a small set of
fields, and applies a fixed admission policy. Does not access document
content, does not perform any matching, ranking, similarity, indexing, or
context assembly. Does not touch storage, the network, configuration,
secrets, or model interfaces.

Inputs are caller-supplied metadata only. Outputs are caller-safe metadata
only: title is required for validation but is never carried into the
assessment.

This module is a governance contract layer. It does not start the future
RAG pipeline, does not change any persistence path, and does not change any
existing AI-context exclusion rule.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import StrEnum

from app_backend.services.knowledge_base_contracts import (
    KnowledgeBaseAdmissionError,
    KnowledgeDocumentType,
    canonicalize_document_url,
)

_ALLOWED_DOC_TYPES = frozenset({
    KnowledgeDocumentType.POLICY_DOC.value,
    KnowledgeDocumentType.RESEARCH_REPORT.value,
    KnowledgeDocumentType.HISTORICAL_DATA.value,
    KnowledgeDocumentType.ONE_SHOT_NEWS.value,
})

_SHA256_HEX_LEN = 64
_HEX_LOWER_DIGITS = frozenset("0123456789abcdef")
_MAX_TITLE_CHARS = 500


class RagEvidenceGovernanceError(ValueError):
    """Raised for malformed candidate metadata. Carries a stable ``code``."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class RagEvidenceEligibility(StrEnum):
    ELIGIBLE = "eligible"
    EXCLUDED = "excluded"


class RagEvidenceExclusionReason(StrEnum):
    STALE_DOCUMENT = "stale_document"
    HISTORICAL_DATA_EXCLUDED = "historical_data_excluded"
    ONE_SHOT_NEWS_EXCLUDED = "one_shot_news_excluded"


@dataclass(frozen=True)
class RagEvidenceCandidate:
    """Caller-supplied document descriptor accepted by the governance layer.

    Document content, persistence handles, model context, holdings, account,
    position, transaction, provider payload, and private-note material are
    not part of this descriptor and must never be supplied here.
    """

    document_id: int
    url: str
    title: str
    source_domain: str
    doc_type: str
    fetched_at: str
    content_sha256: str
    is_stale: bool


@dataclass(frozen=True)
class RagEvidenceAssessment:
    """Caller-safe metadata-only assessment produced by the governance layer.

    Title is intentionally absent. No content, persistence handle, model
    context, score, ranking, or other downstream artefact appears here.
    """

    document_id: int
    url: str
    source_domain: str
    doc_type: str
    fetched_at: str
    content_sha256: str
    eligibility: str
    exclusion_reason: str | None


def assess_rag_evidence_candidate(
    candidate: RagEvidenceCandidate,
) -> RagEvidenceAssessment:
    """Validate the candidate metadata and apply the fixed admission policy.

    The returned assessment is purely a governance signal. It does not by
    itself authorise reading document content, does not authorise model or
    network use, and does not change any persistence or AI-context rule.
    """
    document_id = _validated_document_id(candidate.document_id)
    canonical_url, hostname = _validated_url(candidate.url)
    source_domain = _validated_source_domain(candidate.source_domain, hostname)
    _validate_title_shape(candidate.title)
    doc_type = _validated_doc_type(candidate.doc_type)
    fetched_at = _validated_fetched_at(candidate.fetched_at)
    content_sha256 = _validated_content_sha256(candidate.content_sha256)
    is_stale = _validated_is_stale(candidate.is_stale)

    eligibility, exclusion_reason = _apply_admission_policy(doc_type, is_stale)
    return RagEvidenceAssessment(
        document_id=document_id,
        url=canonical_url,
        source_domain=source_domain,
        doc_type=doc_type,
        fetched_at=fetched_at,
        content_sha256=content_sha256,
        eligibility=eligibility.value,
        exclusion_reason=exclusion_reason.value if exclusion_reason else None,
    )


def _apply_admission_policy(
    doc_type: str,
    is_stale: bool,
) -> tuple[RagEvidenceEligibility, RagEvidenceExclusionReason | None]:
    if is_stale:
        return (
            RagEvidenceEligibility.EXCLUDED,
            RagEvidenceExclusionReason.STALE_DOCUMENT,
        )
    if doc_type == KnowledgeDocumentType.HISTORICAL_DATA.value:
        return (
            RagEvidenceEligibility.EXCLUDED,
            RagEvidenceExclusionReason.HISTORICAL_DATA_EXCLUDED,
        )
    if doc_type == KnowledgeDocumentType.ONE_SHOT_NEWS.value:
        return (
            RagEvidenceEligibility.EXCLUDED,
            RagEvidenceExclusionReason.ONE_SHOT_NEWS_EXCLUDED,
        )
    return RagEvidenceEligibility.ELIGIBLE, None


def _validated_document_id(value: object) -> int:
    if type(value) is not int:
        raise RagEvidenceGovernanceError("invalid_document_id")
    if value <= 0:
        raise RagEvidenceGovernanceError("invalid_document_id")
    return value


def _validated_url(value: object) -> tuple[str, str]:
    if type(value) is not str:
        raise RagEvidenceGovernanceError("invalid_document_url")
    try:
        canonical, hostname = canonicalize_document_url(value)
    except KnowledgeBaseAdmissionError as exc:
        raise RagEvidenceGovernanceError("invalid_document_url") from exc
    return canonical, hostname


def _validated_source_domain(value: object, expected_hostname: str) -> str:
    if type(value) is not str:
        raise RagEvidenceGovernanceError("invalid_source_domain")
    normalized = value.strip().lower().rstrip(".")
    if not normalized or normalized != expected_hostname:
        raise RagEvidenceGovernanceError("invalid_source_domain")
    return normalized


def _validate_title_shape(value: object) -> None:
    if type(value) is not str:
        raise RagEvidenceGovernanceError("invalid_title")
    stripped = value.strip()
    if not stripped or len(stripped) > _MAX_TITLE_CHARS:
        raise RagEvidenceGovernanceError("invalid_title")


def _validated_doc_type(value: object) -> str:
    if type(value) is not str:
        raise RagEvidenceGovernanceError("invalid_document_type")
    if value not in _ALLOWED_DOC_TYPES:
        raise RagEvidenceGovernanceError("invalid_document_type")
    return value


def _validated_fetched_at(value: object) -> str:
    if type(value) is not str:
        raise RagEvidenceGovernanceError("invalid_fetched_at")
    normalized = value.strip()
    if normalized.endswith("Z"):
        normalized = normalized[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise RagEvidenceGovernanceError("invalid_fetched_at") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise RagEvidenceGovernanceError("invalid_fetched_at")
    return parsed.astimezone(timezone.utc).isoformat()


def _validated_content_sha256(value: object) -> str:
    if type(value) is not str:
        raise RagEvidenceGovernanceError("invalid_content_sha256")
    if len(value) != _SHA256_HEX_LEN:
        raise RagEvidenceGovernanceError("invalid_content_sha256")
    for ch in value:
        if ch not in _HEX_LOWER_DIGITS:
            raise RagEvidenceGovernanceError("invalid_content_sha256")
    return value


def _validated_is_stale(value: object) -> bool:
    if type(value) is not bool:
        raise RagEvidenceGovernanceError("invalid_is_stale")
    return value


__all__ = [
    "RagEvidenceAssessment",
    "RagEvidenceCandidate",
    "RagEvidenceEligibility",
    "RagEvidenceExclusionReason",
    "RagEvidenceGovernanceError",
    "assess_rag_evidence_candidate",
]
