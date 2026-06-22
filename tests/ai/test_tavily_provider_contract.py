from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest
from pydantic import ValidationError

from app_backend.schemas.search_external import SearchRequest
from app_backend.services.tavily_provider_contract import (
    TavilyProviderPayload,
    build_tavily_provider_payload,
)
from app_backend.services.tavily_transport_contract import (
    TavilyTransport,
    TavilyTransportError,
    TavilyTransportRequest,
    TavilyTransportResponse,
    TavilyTransportResult,
    build_transport_request_from_provider_payload,
)


def test_provider_payload_maps_search_request_exactly():
    request = SearchRequest(
        query="Federal Reserve policy statement",
        max_results=7,
        domain_filter=["federalreserve.gov", "reuters.com"],
    )

    payload = build_tavily_provider_payload(request)

    assert payload.model_dump() == {
        "query": "Federal Reserve policy statement",
        "max_results": 7,
        "include_domains": ["federalreserve.gov", "reuters.com"],
    }


def test_empty_domain_filter_stays_empty():
    payload = build_tavily_provider_payload(
        SearchRequest(query="US inflation outlook")
    )

    assert payload.include_domains == []


def test_transport_request_is_derived_only_from_provider_payload():
    payload = TavilyProviderPayload(
        query="Treasury curve",
        max_results=3,
        include_domains=["treasury.gov"],
    )

    request = build_transport_request_from_provider_payload(payload)

    assert request.model_dump() == payload.model_dump()


@pytest.mark.parametrize(
    "model",
    [
        TavilyProviderPayload,
        TavilyTransportRequest,
        TavilyTransportResponse,
        TavilyTransportResult,
    ],
)
def test_contract_models_forbid_extra_sensitive_fields(model):
    values = {
        TavilyProviderPayload: {
            "query": "CPI release",
            "max_results": 5,
            "include_domains": [],
        },
        TavilyTransportRequest: {
            "query": "CPI release",
            "max_results": 5,
            "include_domains": [],
        },
        TavilyTransportResponse: {"results": []},
        TavilyTransportResult: {
            "url": "https://bls.gov/cpi",
            "title": "CPI",
            "snippet": "Release summary",
        },
    }[model]

    with pytest.raises(ValidationError):
        model(**values, api_key="forbidden")


def test_contract_field_names_exclude_network_and_sensitive_surfaces():
    models = (
        TavilyProviderPayload,
        TavilyTransportRequest,
        TavilyTransportResponse,
        TavilyTransportResult,
    )
    forbidden = {
        "api_key",
        "authorization",
        "endpoint",
        "base_url",
        "headers",
        "cookies",
        "raw_payload",
        "holdings",
        "account",
        "position",
        "transaction",
        "local_path",
        "persist",
        "log",
    }

    for model in models:
        assert not forbidden.intersection(model.model_fields)


def test_fake_transport_satisfies_protocol():
    class FakeTransport:
        def send(
            self,
            request: TavilyTransportRequest,
        ) -> TavilyTransportResponse:
            return TavilyTransportResponse()

    assert isinstance(FakeTransport(), TavilyTransport)


@pytest.mark.parametrize(
    "kind",
    [
        "timeout",
        "http_error",
        "malformed",
        "missing_key",
        "provider_refusal",
    ],
)
def test_transport_error_preserves_only_kind_and_sanitized_detail(kind: str):
    error = TavilyTransportError(kind=kind, detail=" safe   detail ")

    assert error.kind == kind
    assert error.detail == "safe detail"


def test_transport_error_redacts_sensitive_detail():
    error = TavilyTransportError(
        kind="http_error",
        detail="Authorization Bearer tvly-secret",
    )

    assert error.detail == "redacted"
    assert "tvly-secret" not in str(error)


def test_import_has_no_file_or_network_side_effects(monkeypatch):
    imported = []

    def blocked_open(*args, **kwargs):
        raise AssertionError("contract import must not open files")

    def blocked_socket(*args, **kwargs):
        raise AssertionError("contract import must not open sockets")

    monkeypatch.setattr("builtins.open", blocked_open)
    monkeypatch.setattr("socket.socket", blocked_socket)
    for module_name in (
        "app_backend.services.tavily_provider_contract",
        "app_backend.services.tavily_transport_contract",
    ):
        sys.modules.pop(module_name, None)
        imported.append(importlib.import_module(module_name).__name__)

    assert imported == [
        "app_backend.services.tavily_provider_contract",
        "app_backend.services.tavily_transport_contract",
    ]


def test_contract_sources_do_not_import_network_or_environment_access():
    root = Path(__file__).resolve().parents[2]
    source = "\n".join(
        (root / relative).read_text(encoding="utf-8")
        for relative in (
            "src/app_backend/services/tavily_provider_contract.py",
            "src/app_backend/services/tavily_transport_contract.py",
        )
    )

    for forbidden in (
        "import httpx",
        "import requests",
        "import aiohttp",
        "os.environ",
        "os.getenv",
    ):
        assert forbidden not in source
