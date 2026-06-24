from __future__ import annotations

from enum import StrEnum
from urllib.parse import SplitResult, urlsplit

from app_backend.schemas.search_external import SearchResult


class ResultCategory(StrEnum):
    ONE_SHOT_NEWS = "one_shot_news"
    POLICY_DOC = "policy_doc"
    RESEARCH_REPORT = "research_report"
    HISTORICAL_DATA = "historical_data"
    DISCARD = "discard"


_HISTORICAL_DATA_DOMAINS = (
    "fred.stlouisfed.org",
    "bls.gov",
    "bea.gov",
    "treasury.gov",
)

_POLICY_DOC_DOMAINS = (
    "federalreserve.gov",
    "imf.org",
    "worldbank.org",
)

_POLICY_KEYWORDS = (
    "speech",
    "minutes",
    "statement",
    "fomc",
    "monetary policy",
    "press release",
)

_RESEARCH_REPORT_DOMAINS = (
    "nber.org",
    "bis.org",
    "brookings.edu",
    "piie.com",
    "bruegel.org",
    "cepr.org",
    "imf.org",
    "worldbank.org",
    "federalreserve.gov",
)

_ONE_SHOT_NEWS_DOMAINS = (
    "reuters.com",
    "bloomberg.com",
    "ft.com",
    "oilprice.com",
)


def classify(result: SearchResult) -> ResultCategory:
    parsed_url = _safe_url_parts(result.url)
    if parsed_url is None:
        return ResultCategory.DISCARD

    parsed, hostname = parsed_url
    merged_text = _classification_text(result.title, result.snippet, parsed.path)

    if _matches_any_domain(hostname, _HISTORICAL_DATA_DOMAINS):
        return ResultCategory.HISTORICAL_DATA
    if _matches_any_domain(hostname, _POLICY_DOC_DOMAINS) and _has_policy_keyword(
        merged_text
    ):
        return ResultCategory.POLICY_DOC
    if _is_pdf_path(parsed.path) and _matches_any_domain(
        hostname, _RESEARCH_REPORT_DOMAINS
    ):
        return ResultCategory.RESEARCH_REPORT
    if _matches_any_domain(hostname, _ONE_SHOT_NEWS_DOMAINS):
        return ResultCategory.ONE_SHOT_NEWS
    return ResultCategory.DISCARD


def _safe_url_parts(url: str) -> tuple[SplitResult, str] | None:
    try:
        parsed = urlsplit(url)
        _ = parsed.port
    except ValueError:
        return None

    if parsed.scheme.lower() not in {"http", "https"}:
        return None
    if parsed.hostname is None:
        return None
    if parsed.username is not None or parsed.password is not None:
        return None
    if parsed.query or parsed.fragment:
        return None

    hostname = _normalize_hostname(parsed.hostname)
    if not hostname:
        return None
    return parsed, hostname


def _normalize_hostname(hostname: str) -> str:
    normalized = hostname.strip().lower().rstrip(".")
    if normalized.startswith("www."):
        normalized = normalized[4:]
    return normalized


def _domain_matches(hostname: str, allowed_domain: str) -> bool:
    return hostname == allowed_domain or hostname.endswith("." + allowed_domain)


def _matches_any_domain(hostname: str, allowed_domains: tuple[str, ...]) -> bool:
    return any(_domain_matches(hostname, domain) for domain in allowed_domains)


def _classification_text(title: str, snippet: str, path: str) -> str:
    return f"{title}\n{snippet}\n{path}".lower()


def _has_policy_keyword(text: str) -> bool:
    return any(keyword in text for keyword in _POLICY_KEYWORDS)


def _is_pdf_path(path: str) -> bool:
    return path.lower().endswith(".pdf")


__all__ = ["ResultCategory", "classify"]
