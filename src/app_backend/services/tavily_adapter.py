from __future__ import annotations

import re
from urllib.parse import urlparse

from app_backend.schemas.search_external import (
    SearchRequest,
    SearchResponse,
    SearchResult,
    SearchRuntimePolicy,
)
from app_backend.services.query_sanitizer import sanitize_query
from app_backend.services.search_config_loader import SearchAdapterConfig
from app_backend.services.search_runtime_policy import (
    BlockedAdapterError,
    assert_search_runtime_policy_allowed,
)
from app_backend.services.tavily_provider_contract import (
    build_tavily_provider_payload,
)
from app_backend.services.tavily_transport_contract import (
    TavilyTransport,
    TavilyTransportError,
    TavilyTransportResponse,
    build_transport_request_from_provider_payload,
)


_FORBIDDEN_RESPONSE_PATTERN = re.compile(
    r"(?i)(api[_ -]?key|authorization|bearer|tvly-|"
    r"[a-z]:\\|/users/|/home/|/mnt/data|"
    r"holdings?|account(?:\s+number)?|position\s+weight|"
    r"transaction\s+history)"
)


class TavilyAdapter:
    def __init__(
        self,
        *,
        config: SearchAdapterConfig,
        transport: TavilyTransport | None,
        runtime_policy: SearchRuntimePolicy | None,
    ) -> None:
        self._config = config
        self._transport = transport
        self._runtime_policy = runtime_policy

    def search(self, request: SearchRequest) -> SearchResponse:
        sanitized = sanitize_query(request.query)
        if sanitized.blocked:
            raise BlockedAdapterError(
                [f"query_sanitizer_{finding}" for finding in sanitized.findings]
            )

        if self._runtime_policy is None:
            raise BlockedAdapterError(["missing_runtime_policy"])
        assert_search_runtime_policy_allowed(self._runtime_policy)

        effective_domains = _effective_domains(
            request.domain_filter,
            self._config.domain_allowlist,
            self._config.domain_blocklist,
        )
        if request.max_results < 1:
            raise BlockedAdapterError(["invalid_max_results"])
        effective_request = SearchRequest(
            query=sanitized.text,
            max_results=min(
                request.max_results,
                self._config.max_results_per_call,
            ),
            domain_filter=effective_domains,
        )
        payload = build_tavily_provider_payload(effective_request)
        transport_request = build_transport_request_from_provider_payload(
            payload
        )

        if self._transport is None:
            raise BlockedAdapterError(["missing_transport"])
        try:
            transport_response = self._transport.send(transport_request)
        except TavilyTransportError:
            return SearchResponse(
                results=[],
                search_available=False,
                guard_passed=True,
            )
        except Exception:
            raise BlockedAdapterError(["transport_unknown_error"])

        if not isinstance(transport_response, TavilyTransportResponse):
            raise BlockedAdapterError(["transport_malformed_response"])

        results = _guard_results(
            transport_response,
            effective_domains=effective_domains,
            blocklist=self._config.domain_blocklist,
            original_query=request.query,
        )
        return SearchResponse(
            results=results,
            search_available=True,
            guard_passed=True,
        )


class FakeTavilyAdapter(TavilyAdapter):
    pass


def _effective_domains(
    requested: list[str],
    allowlist: list[str],
    blocklist: list[str],
) -> list[str]:
    allowed = _unique_domains(allowlist)
    blocked = _unique_domains(blocklist)
    if not allowed:
        raise BlockedAdapterError(["empty_domain_allowlist"])

    candidates = _unique_domains(requested) if requested else allowed
    for domain in candidates:
        if _matches_any(domain, blocked):
            raise BlockedAdapterError(["domain_blocklisted"])
        if not _matches_any(domain, allowed):
            raise BlockedAdapterError(["domain_not_allowlisted"])

    effective = [
        domain for domain in candidates if not _matches_any(domain, blocked)
    ]
    if not effective:
        raise BlockedAdapterError(["no_effective_domains"])
    return effective


def _guard_results(
    response: TavilyTransportResponse,
    *,
    effective_domains: list[str],
    blocklist: list[str],
    original_query: str,
) -> list[SearchResult]:
    guarded: list[SearchResult] = []
    for result in response.results:
        hostname = _hostname(result.url)
        if hostname is None:
            continue
        if _matches_any(hostname, _unique_domains(blocklist)):
            continue
        if not _matches_any(hostname, effective_domains):
            continue
        combined_text = f"{result.title}\n{result.snippet}"
        if _FORBIDDEN_RESPONSE_PATTERN.search(combined_text):
            continue
        if original_query.casefold() in combined_text.casefold():
            continue
        guarded.append(
            SearchResult(
                url=result.url,
                title=result.title,
                snippet=result.snippet,
                domain=hostname,
            )
        )
    return guarded


def _unique_domains(domains: list[str]) -> list[str]:
    unique: list[str] = []
    for raw_domain in domains:
        domain = _normalize_domain(raw_domain)
        if domain and domain not in unique:
            unique.append(domain)
    return unique


def _normalize_domain(domain: str) -> str:
    normalized = domain.strip().lower().rstrip(".")
    if normalized.startswith("www."):
        normalized = normalized[4:]
    return normalized


def _domain_matches(domain: str, allowed: str) -> bool:
    return domain == allowed or domain.endswith("." + allowed)


def _matches_any(domain: str, candidates: list[str]) -> bool:
    return any(_domain_matches(domain, candidate) for candidate in candidates)


def _hostname(url: str) -> str | None:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or parsed.hostname is None:
        return None
    return _normalize_domain(parsed.hostname)


__all__ = [
    "FakeTavilyAdapter",
    "TavilyAdapter",
]
