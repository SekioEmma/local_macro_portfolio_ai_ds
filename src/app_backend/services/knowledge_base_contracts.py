from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import StrEnum
import hashlib
import ipaddress
import re
from urllib.parse import SplitResult, urlsplit, urlunsplit


class KnowledgeDocumentType(StrEnum):
    POLICY_DOC = "policy_doc"
    RESEARCH_REPORT = "research_report"
    HISTORICAL_DATA = "historical_data"
    ONE_SHOT_NEWS = "one_shot_news"


class KnowledgeBaseAdmissionError(ValueError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass(frozen=True)
class KnowledgeDocumentInput:
    url: str
    title: str
    doc_type: str
    fetched_at: str
    raw_text: str


@dataclass(frozen=True)
class AdmittedKnowledgeDocument:
    canonical_url: str
    title: str
    source_domain: str
    doc_type: KnowledgeDocumentType
    fetched_at: str
    raw_text: str
    content_sha256: str


_MAX_TITLE_CHARS = 500
_MAX_RAW_TEXT_BYTES = 1024 * 1024
_REJECTED_DOC_TYPES = {
    "discard",
    "unknown",
    "research_needed",
    "search-derived",
}
_SENSITIVE_MARKERS = (
    "TAVILY_API_KEY",
    "DEEPSEEK_API_KEY",
    "FRED_API_KEY",
    "BLS_API_KEY",
    ".env",
    "data/holdings/",
    "data/private/",
    "data/private_notes/",
    "current_holdings.csv",
)
_OPENAI_SECRET_RE = re.compile(r"\bsk-[A-Za-z0-9_-]{10,}\b")
_WINDOWS_USER_DIR_RE = re.compile(r"\b[A-Za-z]:[\\/]+Users[\\/]+[^\\/\s]+")
_UNIX_HOME_RE = re.compile(r"(?<!\w)/(?:home|Users)/[^/\s]+")


def canonicalize_document_url(url: str) -> tuple[str, str]:
    parsed = _parse_url(url)
    hostname = _validated_hostname(parsed)
    path = parsed.path or ""
    if _path_has_traversal(path):
        raise KnowledgeBaseAdmissionError("invalid_url")
    canonical = urlunsplit(("https", hostname, path, "", ""))
    return canonical, hostname


def admit_document(document: KnowledgeDocumentInput) -> AdmittedKnowledgeDocument:
    canonical_url, source_domain = canonicalize_document_url(document.url)
    title = _validated_title(document.title)
    doc_type = _validated_doc_type(document.doc_type)
    fetched_at = _validated_fetched_at(document.fetched_at)
    raw_text_bytes = _validated_raw_text_bytes(document.raw_text)
    return AdmittedKnowledgeDocument(
        canonical_url=canonical_url,
        title=title,
        source_domain=source_domain,
        doc_type=doc_type,
        fetched_at=fetched_at,
        raw_text=document.raw_text,
        content_sha256=hashlib.sha256(raw_text_bytes).hexdigest(),
    )


def _parse_url(url: str) -> SplitResult:
    try:
        parsed = urlsplit(url)
        _ = parsed.port
    except ValueError as exc:
        raise KnowledgeBaseAdmissionError("invalid_url") from exc
    if parsed.scheme.lower() != "https":
        raise KnowledgeBaseAdmissionError("invalid_url")
    if parsed.username is not None or parsed.password is not None:
        raise KnowledgeBaseAdmissionError("invalid_url")
    if parsed.port is not None:
        raise KnowledgeBaseAdmissionError("invalid_url")
    if parsed.query or parsed.fragment:
        raise KnowledgeBaseAdmissionError("invalid_url")
    return parsed


def _validated_hostname(parsed: SplitResult) -> str:
    hostname = (parsed.hostname or "").strip().lower().rstrip(".")
    if not hostname:
        raise KnowledgeBaseAdmissionError("invalid_url")
    if hostname == "localhost" or hostname.endswith(".localhost"):
        raise KnowledgeBaseAdmissionError("invalid_url")
    try:
        ipaddress.ip_address(hostname)
    except ValueError:
        return hostname
    raise KnowledgeBaseAdmissionError("invalid_url")


def _path_has_traversal(path: str) -> bool:
    return any(part == ".." for part in path.split("/"))


def _validated_title(title: str) -> str:
    normalized = title.strip()
    if not normalized or len(normalized) > _MAX_TITLE_CHARS:
        raise KnowledgeBaseAdmissionError("invalid_title")
    return normalized


def _validated_doc_type(doc_type: str) -> KnowledgeDocumentType:
    if doc_type in _REJECTED_DOC_TYPES:
        raise KnowledgeBaseAdmissionError("unsupported_doc_type")
    try:
        return KnowledgeDocumentType(doc_type)
    except ValueError as exc:
        raise KnowledgeBaseAdmissionError("unsupported_doc_type") from exc


def _validated_fetched_at(value: str) -> str:
    normalized = value.strip()
    if normalized.endswith("Z"):
        normalized = normalized[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise KnowledgeBaseAdmissionError("invalid_fetched_at") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise KnowledgeBaseAdmissionError("invalid_fetched_at")
    return parsed.astimezone(timezone.utc).isoformat()


def _validated_raw_text_bytes(raw_text: str) -> bytes:
    if not raw_text.strip() or "\x00" in raw_text:
        raise KnowledgeBaseAdmissionError("invalid_raw_text")
    raw_text_bytes = raw_text.encode("utf-8")
    if len(raw_text_bytes) > _MAX_RAW_TEXT_BYTES:
        raise KnowledgeBaseAdmissionError("raw_text_too_large")
    if _contains_sensitive_content(raw_text):
        raise KnowledgeBaseAdmissionError("sensitive_content_rejected")
    return raw_text_bytes


def _contains_sensitive_content(raw_text: str) -> bool:
    return (
        any(marker in raw_text for marker in _SENSITIVE_MARKERS)
        or _OPENAI_SECRET_RE.search(raw_text) is not None
        or _WINDOWS_USER_DIR_RE.search(raw_text) is not None
        or _UNIX_HOME_RE.search(raw_text) is not None
    )


__all__ = [
    "AdmittedKnowledgeDocument",
    "KnowledgeBaseAdmissionError",
    "KnowledgeDocumentInput",
    "KnowledgeDocumentType",
    "admit_document",
    "canonicalize_document_url",
]
