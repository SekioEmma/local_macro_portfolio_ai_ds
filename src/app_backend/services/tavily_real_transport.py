from __future__ import annotations

import os
from typing import Any
from urllib.parse import urlsplit, urlunsplit

import httpx

from app_backend.services.tavily_transport_contract import (
    TavilyTransportError,
    TavilyTransportRequest,
    TavilyTransportResponse,
    TavilyTransportResult,
)


DEFAULT_TAVILY_SEARCH_ENDPOINT = "https://api.tavily.com/search"
_TAVILY_API_KEY_ENV = "TAVILY_API_KEY"
_DEFAULT_TIMEOUT_SECONDS = 30.0


def load_tavily_api_key_from_env() -> str:
    value = os.environ.get(_TAVILY_API_KEY_ENV, "").strip()
    if not value:
        raise TavilyTransportError(kind="missing_key")
    return value


class TavilyRealTransport:
    def __init__(
        self,
        *,
        api_key: str | None = None,
        endpoint: str = DEFAULT_TAVILY_SEARCH_ENDPOINT,
        timeout_seconds: float = _DEFAULT_TIMEOUT_SECONDS,
        client: httpx.Client | None = None,
    ) -> None:
        self._api_key = api_key.strip() if api_key is not None else None
        self._endpoint = endpoint
        self._timeout_seconds = timeout_seconds
        self._client = client

    def __repr__(self) -> str:
        return (
            "TavilyRealTransport("
            f"endpoint={self._endpoint!r}, "
            f"timeout_seconds={self._timeout_seconds!r})"
        )

    def send(
        self,
        request: TavilyTransportRequest,
    ) -> TavilyTransportResponse:
        _validate_endpoint(self._endpoint)
        _validate_request(request)
        api_key = self._load_api_key()
        body = {
            "query": request.query,
            "max_results": request.max_results,
            "include_domains": list(request.include_domains),
            "search_depth": "basic",
            "include_answer": False,
            "include_raw_content": False,
            "include_images": False,
            "include_usage": False,
        }

        try:
            if self._client is not None:
                response = self._client.post(
                    self._endpoint,
                    headers=_headers(api_key),
                    json=body,
                    timeout=self._timeout_seconds,
                    follow_redirects=False,
                )
            else:
                with httpx.Client(
                    timeout=self._timeout_seconds,
                    follow_redirects=False,
                ) as client:
                    response = client.post(
                        self._endpoint,
                        headers=_headers(api_key),
                        json=body,
                    )
        except httpx.TimeoutException as exc:
            raise TavilyTransportError(kind="timeout") from exc
        except httpx.RequestError as exc:
            raise TavilyTransportError(kind="http_error") from exc

        if response.status_code in {401, 403}:
            raise TavilyTransportError(kind="provider_refusal")
        if not 200 <= response.status_code < 300:
            raise TavilyTransportError(kind="http_error")

        return _parse_response(
            response,
            include_domains=request.include_domains,
        )

    def _load_api_key(self) -> str:
        if self._api_key is None:
            return load_tavily_api_key_from_env()
        if not self._api_key:
            raise TavilyTransportError(kind="missing_key")
        return self._api_key


def _headers(api_key: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }


def _validate_endpoint(endpoint: str) -> None:
    try:
        parsed = urlsplit(endpoint)
        port = parsed.port
    except (TypeError, ValueError) as exc:
        raise TavilyTransportError(kind="malformed") from exc
    if (
        parsed.scheme != "https"
        or parsed.hostname != "api.tavily.com"
        or parsed.path != "/search"
        or port is not None
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
        or endpoint != DEFAULT_TAVILY_SEARCH_ENDPOINT
    ):
        raise TavilyTransportError(kind="malformed")


def _validate_request(request: TavilyTransportRequest) -> None:
    if not 1 <= request.max_results <= 20:
        raise TavilyTransportError(kind="malformed")
    if not request.include_domains:
        raise TavilyTransportError(kind="malformed")
    if any(not domain.strip() for domain in request.include_domains):
        raise TavilyTransportError(kind="malformed")


def _parse_response(
    response: httpx.Response,
    *,
    include_domains: list[str],
) -> TavilyTransportResponse:
    try:
        payload = response.json()
    except ValueError as exc:
        raise TavilyTransportError(kind="malformed") from exc
    if not isinstance(payload, dict):
        raise TavilyTransportError(kind="malformed")
    if payload.get("refusal"):
        raise TavilyTransportError(kind="provider_refusal")
    results = payload.get("results")
    if not isinstance(results, list):
        raise TavilyTransportError(kind="malformed")

    mapped: list[TavilyTransportResult] = []
    for item in results:
        result = _map_result(item, include_domains=include_domains)
        if result is not None:
            mapped.append(result)
    return TavilyTransportResponse(results=mapped)


def _map_result(
    item: Any,
    *,
    include_domains: list[str],
) -> TavilyTransportResult | None:
    if not isinstance(item, dict):
        return None
    url = item.get("url")
    title = item.get("title")
    content = item.get("content")
    if not all(isinstance(value, str) for value in (url, title, content)):
        return None
    safe_url = _safe_result_url(url, include_domains=include_domains)
    if safe_url is None:
        return None
    return TavilyTransportResult(
        url=safe_url,
        title=title,
        snippet=content,
    )


def _safe_result_url(
    url: str,
    *,
    include_domains: list[str],
) -> str | None:
    try:
        parsed = urlsplit(url)
        port = parsed.port
    except ValueError:
        return None
    if (
        parsed.scheme not in {"http", "https"}
        or parsed.hostname is None
        or parsed.username is not None
        or parsed.password is not None
    ):
        return None
    hostname = parsed.hostname.lower().rstrip(".")
    allowed = [
        domain.strip().lower().lstrip(".").rstrip(".")
        for domain in include_domains
        if domain.strip()
    ]
    if not any(_domain_matches(hostname, domain) for domain in allowed):
        return None
    netloc = hostname if port is None else f"{hostname}:{port}"
    return urlunsplit(
        (
            parsed.scheme,
            netloc,
            parsed.path,
            "",
            "",
        )
    )


def _domain_matches(hostname: str, allowed: str) -> bool:
    return hostname == allowed or hostname.endswith("." + allowed)


__all__ = [
    "DEFAULT_TAVILY_SEARCH_ENDPOINT",
    "TavilyRealTransport",
    "load_tavily_api_key_from_env",
]
