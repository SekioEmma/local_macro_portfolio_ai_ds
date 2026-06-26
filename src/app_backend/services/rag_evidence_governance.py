"""Phase D0 metadata-only RAG evidence governance contracts."""
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
    LOCAL_ONLY_USE = "local_only_use"


_VALID_ALLOWED_USE = frozenset({"external_context_candidate", "local_search_only"})


@dataclass(frozen=True)
class RagEvidenceCandidate:
    """Caller-supplied metadata descriptor accepted by the governance layer."""

    document_id: int
    url: str
    title: str
    source_domain: str
    doc_type: str
    fetched_at: str
    content_sha256: str
    is_stale: bool
    external_llm_context_allowed: bool = True
    allowed_use: str = "external_context_candidate"


@dataclass(frozen=True)
class RagEvidenceAssessment:
    """Caller-safe metadata-only assessment produced by the governance layer."""

    document_id: int
    url: str
    source_domain: str
    doc_type: str
    fetched_at: str
    content_sha256: str
    eligibility: str
    exclusion_reason: str | None
    external_llm_context_allowed: bool
    allowed_use: str


def assess_rag_evidence_candidate(
    candidate: object,
) -> RagEvidenceAssessment:
    """Validate exact candidate metadata and apply the fixed admission policy."""
    if type(candidate) is not RagEvidenceCandidate:
        raise RagEvidenceGovernanceError("invalid_candidate")

    failed = False
    try:
        return _assess_exact_candidate(candidate)
    except RagEvidenceGovernanceError:
        raise
    except Exception:
        failed = True

    if failed:
        raise RagEvidenceGovernanceError("invalid_candidate")


def _assess_exact_candidate(candidate: RagEvidenceCandidate) -> RagEvidenceAssessment:
    document_id = _validated_document_id(candidate.document_id)
    canonical_url, hostname = _validated_url(candidate.url)
    source_domain = _validated_source_domain(candidate.source_domain, hostname)
    _validate_title_shape(candidate.title)
    doc_type = _validated_doc_type(candidate.doc_type)
    fetched_at = _validated_fetched_at(candidate.fetched_at)
    content_sha256 = _validated_content_sha256(candidate.content_sha256)
    is_stale = _validated_is_stale(candidate.is_stale)
    external_llm_context_allowed = _validated_external_llm_context_allowed(
        candidate.external_llm_context_allowed
    )
    allowed_use = _validated_allowed_use(candidate.allowed_use)

    eligibility, exclusion_reason = _apply_admission_policy(
        doc_type, is_stale, external_llm_context_allowed
    )
    return RagEvidenceAssessment(
        document_id=document_id,
        url=canonical_url,
        source_domain=source_domain,
        doc_type=doc_type,
        fetched_at=fetched_at,
        content_sha256=content_sha256,
        eligibility=eligibility.value,
        exclusion_reason=exclusion_reason.value if exclusion_reason else None,
        external_llm_context_allowed=external_llm_context_allowed,
        allowed_use=allowed_use,
    )


def _apply_admission_policy(
    doc_type: str,
    is_stale: bool,
    external_llm_context_allowed: bool,
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
    if not external_llm_context_allowed:
        return (
            RagEvidenceEligibility.EXCLUDED,
            RagEvidenceExclusionReason.LOCAL_ONLY_USE,
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


def _validated_external_llm_context_allowed(value: object) -> bool:
    if type(value) is not bool:
        raise RagEvidenceGovernanceError("invalid_external_llm_context_allowed")
    return value


def _validated_allowed_use(value: object) -> str:
    if type(value) is not str:
        raise RagEvidenceGovernanceError("invalid_allowed_use")
    if value not in _VALID_ALLOWED_USE:
        raise RagEvidenceGovernanceError("invalid_allowed_use")
    return value


__all__ = [
    "RagEvidenceAssessment",
    "RagEvidenceCandidate",
    "RagEvidenceEligibility",
    "RagEvidenceExclusionReason",
    "RagEvidenceGovernanceError",
    "assess_rag_evidence_candidate",
]
