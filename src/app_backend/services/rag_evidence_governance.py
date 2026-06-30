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
    INSTITUTIONAL_RIGHTS_NOT_AUTHORIZED = "institutional_rights_not_authorized"


_VALID_ALLOWED_USE = frozenset({"external_context_candidate", "local_search_only"})
_OFFICIAL_SOURCE_KINDS = frozenset({"central_bank_policy", "official_release", "official_outlook"})
_INSTITUTIONAL_SOURCE_KIND = "institutional_research"
_VALID_SOURCE_KINDS = _OFFICIAL_SOURCE_KINDS | frozenset({_INSTITUTIONAL_SOURCE_KIND})
_VALID_EVIDENCE_TIERS = frozenset({"official_evidence", "institutional_view"})
_VALID_RIGHTS_STATUS = frozenset({
    "public_official_source",
    "private_local_only",
    "user_authorized_external_context",
})


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
    source_kind: str = "central_bank_policy"
    evidence_tier: str = "official_evidence"
    is_official_source: bool = True
    rights_status: str = "public_official_source"
    external_context_authorized_by_user: bool = False


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
    source_kind: str
    evidence_tier: str
    is_official_source: bool
    rights_status: str
    external_context_authorized_by_user: bool


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
    source_kind = _validated_source_kind(candidate.source_kind)
    evidence_tier = _validated_evidence_tier(candidate.evidence_tier)
    is_official_source = _validated_is_official_source(candidate.is_official_source)
    rights_status = _validated_rights_status(candidate.rights_status)
    external_context_authorized_by_user = _validated_external_context_authorized_by_user(
        candidate.external_context_authorized_by_user
    )
    _validate_source_tier_contract(
        doc_type=doc_type,
        source_kind=source_kind,
        evidence_tier=evidence_tier,
        is_official_source=is_official_source,
    )

    eligibility, exclusion_reason = _apply_admission_policy(
        doc_type=doc_type,
        is_stale=is_stale,
        external_llm_context_allowed=external_llm_context_allowed,
        allowed_use=allowed_use,
        source_kind=source_kind,
        rights_status=rights_status,
        external_context_authorized_by_user=external_context_authorized_by_user,
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
        source_kind=source_kind,
        evidence_tier=evidence_tier,
        is_official_source=is_official_source,
        rights_status=rights_status,
        external_context_authorized_by_user=external_context_authorized_by_user,
    )


def _apply_admission_policy(
    *,
    doc_type: str,
    is_stale: bool,
    external_llm_context_allowed: bool,
    allowed_use: str,
    source_kind: str,
    rights_status: str,
    external_context_authorized_by_user: bool,
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
    if not external_llm_context_allowed or allowed_use != "external_context_candidate":
        return (
            RagEvidenceEligibility.EXCLUDED,
            RagEvidenceExclusionReason.LOCAL_ONLY_USE,
        )
    if source_kind == _INSTITUTIONAL_SOURCE_KIND and (
        rights_status != "user_authorized_external_context"
        or not external_context_authorized_by_user
    ):
        return (
            RagEvidenceEligibility.EXCLUDED,
            RagEvidenceExclusionReason.INSTITUTIONAL_RIGHTS_NOT_AUTHORIZED,
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


def _validated_source_kind(value: object) -> str:
    if type(value) is not str:
        raise RagEvidenceGovernanceError("invalid_source_kind")
    if value not in _VALID_SOURCE_KINDS:
        raise RagEvidenceGovernanceError("invalid_source_kind")
    return value


def _validated_evidence_tier(value: object) -> str:
    if type(value) is not str:
        raise RagEvidenceGovernanceError("invalid_evidence_tier")
    if value not in _VALID_EVIDENCE_TIERS:
        raise RagEvidenceGovernanceError("invalid_evidence_tier")
    return value


def _validated_is_official_source(value: object) -> bool:
    if type(value) is not bool:
        raise RagEvidenceGovernanceError("invalid_is_official_source")
    return value


def _validated_rights_status(value: object) -> str:
    if type(value) is not str:
        raise RagEvidenceGovernanceError("invalid_rights_status")
    if value not in _VALID_RIGHTS_STATUS:
        raise RagEvidenceGovernanceError("invalid_rights_status")
    return value


def _validated_external_context_authorized_by_user(value: object) -> bool:
    if type(value) is not bool:
        raise RagEvidenceGovernanceError("invalid_external_context_authorized_by_user")
    return value


def _validate_source_tier_contract(
    *,
    doc_type: str,
    source_kind: str,
    evidence_tier: str,
    is_official_source: bool,
) -> None:
    if source_kind == _INSTITUTIONAL_SOURCE_KIND:
        if doc_type != KnowledgeDocumentType.RESEARCH_REPORT.value:
            raise RagEvidenceGovernanceError("institutional_research_invalid_document_type")
        if evidence_tier != "institutional_view":
            raise RagEvidenceGovernanceError("institutional_research_not_view_tier")
        if is_official_source:
            raise RagEvidenceGovernanceError("institutional_research_marked_official")
        return
    if evidence_tier != "official_evidence":
        raise RagEvidenceGovernanceError("official_source_not_official_tier")
    if not is_official_source:
        raise RagEvidenceGovernanceError("official_source_not_marked_official")


__all__ = [
    "RagEvidenceAssessment",
    "RagEvidenceCandidate",
    "RagEvidenceEligibility",
    "RagEvidenceExclusionReason",
    "RagEvidenceGovernanceError",
    "assess_rag_evidence_candidate",
]
