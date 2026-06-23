from __future__ import annotations

import json
import socket
from pathlib import Path

import httpx
import pytest

from app_backend.services.tavily_real_transport import (
    DEFAULT_TAVILY_SEARCH_ENDPOINT,
    MAX_TAVILY_RESPONSE_BYTES,
    TavilyRealTransport,
    load_tavily_api_key_from_env,
)
from app_backend.services.tavily_transport_contract import (
    TavilyTransport,
    TavilyTransportError,
    TavilyTransportRequest,
)


_REPO_ROOT = Path(__file__).resolve().parents[2]
_TEST_KEY = "tvly-test-only-secret"


def _request(**overrides) -> TavilyTransportRequest:
    values = {
        "query": "Federal Reserve rate outlook",
        "max_results": 3,
        "include_domains": ["reuters.com"],
        **overrides,
    }
    return TavilyTransportRequest(**values)


def _response_payload():
    return {
        "answer": "ignored provider answer",
        "images": ["https://example.test/image.png"],
        "usage": {"credits": 1},
        "request_id": "provider-debug-id",
        "results": [
            {
                "url": "https://www.reuters.com/markets/rates?token=hidden#top",
                "title": "Rates update",
                "content": "Policy-sensitive yields were mixed.",
                "raw_content": "<html>ignored</html>",
                "score": 0.99,
            }
        ],
    }


def _transport(handler, **kwargs) -> tuple[TavilyRealTransport, httpx.Client]:
    client = httpx.Client(transport=httpx.MockTransport(handler))
    return (
        TavilyRealTransport(api_key=_TEST_KEY, client=client, **kwargs),
        client,
    )


def test_construction_has_no_env_file_or_network_side_effects(monkeypatch):
    def blocked_env():
        raise AssertionError("construction must not read the environment")

    def blocked_open(*args, **kwargs):
        raise AssertionError("construction must not read files")

    def blocked_socket(*args, **kwargs):
        raise AssertionError("construction must not open sockets")

    monkeypatch.setattr(
        "app_backend.services.tavily_real_transport.load_tavily_api_key_from_env",
        blocked_env,
    )
    monkeypatch.setattr("builtins.open", blocked_open)
    monkeypatch.setattr(socket, "socket", blocked_socket)

    transport = TavilyRealTransport()

    assert "api.tavily.com/search" in repr(transport)


@pytest.mark.parametrize("value", [None, "", "   "])
def test_missing_or_blank_api_key_fails_closed(monkeypatch, value):
    if value is None:
        monkeypatch.delenv("TAVILY_API_KEY", raising=False)
    else:
        monkeypatch.setenv("TAVILY_API_KEY", value)

    with pytest.raises(TavilyTransportError) as exc:
        load_tavily_api_key_from_env()

    assert exc.value.kind == "missing_key"
    assert exc.value.detail == ""


def test_injected_key_happy_path_and_outbound_contract():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["request"] = request
        return httpx.Response(200, json=_response_payload())

    transport, client = _transport(handler)
    try:
        response = transport.send(_request())
    finally:
        client.close()

    outbound = captured["request"]
    body = json.loads(outbound.content)
    assert outbound.method == "POST"
    assert str(outbound.url) == DEFAULT_TAVILY_SEARCH_ENDPOINT
    assert outbound.headers["authorization"] == f"Bearer {_TEST_KEY}"
    assert outbound.headers["content-type"] == "application/json"
    assert body == {
        "query": "Federal Reserve rate outlook",
        "max_results": 3,
        "include_domains": ["reuters.com"],
        "search_depth": "basic",
        "include_answer": False,
        "include_raw_content": False,
        "include_images": False,
        "include_usage": False,
    }
    assert "api_key" not in body
    assert response.model_dump() == {
        "results": [
            {
                "url": "https://www.reuters.com/markets/rates",
                "title": "Rates update",
                "snippet": "Policy-sensitive yields were mixed.",
            }
        ]
    }


def test_timeout_and_redirect_policy_are_explicit():
    calls = []

    class SpyClient:
        def post(self, url, **kwargs):
            calls.append((url, kwargs))
            return httpx.Response(
                200,
                json={"results": []},
                request=httpx.Request("POST", url),
            )

    transport = TavilyRealTransport(api_key=_TEST_KEY, client=SpyClient())

    transport.send(_request())

    _, kwargs = calls[0]
    assert kwargs["timeout"] == 30.0
    assert kwargs["follow_redirects"] is False


def test_provider_extra_fields_do_not_enter_response():
    transport, client = _transport(
        lambda request: httpx.Response(200, json=_response_payload())
    )
    try:
        serialized = transport.send(_request()).model_dump_json()
    finally:
        client.close()

    for forbidden in (
        "answer",
        "images",
        "usage",
        "request_id",
        "raw_content",
        "<html>",
        "score",
    ):
        assert forbidden not in serialized


def test_oversized_response_fails_closed_without_body_leakage():
    oversized = b"x" * (MAX_TAVILY_RESPONSE_BYTES + 1)
    transport, client = _transport(
        lambda request: httpx.Response(200, content=oversized)
    )
    try:
        with pytest.raises(TavilyTransportError) as exc:
            transport.send(_request())
    finally:
        client.close()

    assert exc.value.kind == "malformed"
    assert exc.value.detail == ""
    assert "xxx" not in str(exc.value)


@pytest.mark.parametrize("status", [400, 404, 429, 500, 503])
def test_non_2xx_maps_to_http_error(status):
    transport, client = _transport(
        lambda request: httpx.Response(status, text="provider body hidden")
    )
    try:
        with pytest.raises(TavilyTransportError) as exc:
            transport.send(_request())
    finally:
        client.close()

    assert exc.value.kind == "http_error"
    assert exc.value.detail == ""
    assert "provider body hidden" not in str(exc.value)


@pytest.mark.parametrize("status", [401, 403])
def test_auth_refusal_maps_to_provider_refusal(status):
    transport, client = _transport(
        lambda request: httpx.Response(status, text="secret refusal body")
    )
    try:
        with pytest.raises(TavilyTransportError) as exc:
            transport.send(_request())
    finally:
        client.close()

    assert exc.value.kind == "provider_refusal"
    assert "secret refusal body" not in str(exc.value)


def test_timeout_maps_to_categorical_error():
    def handler(request):
        raise httpx.ReadTimeout("raw timeout detail", request=request)

    transport, client = _transport(handler)
    try:
        with pytest.raises(TavilyTransportError) as exc:
            transport.send(_request())
    finally:
        client.close()

    assert exc.value.kind == "timeout"
    assert "raw timeout detail" not in str(exc.value)


def test_request_error_maps_to_categorical_error():
    def handler(request):
        raise httpx.ConnectError("raw network detail", request=request)

    transport, client = _transport(handler)
    try:
        with pytest.raises(TavilyTransportError) as exc:
            transport.send(_request())
    finally:
        client.close()

    assert exc.value.kind == "http_error"
    assert "raw network detail" not in str(exc.value)


@pytest.mark.parametrize(
    ("response", "expected_kind"),
    [
        (httpx.Response(200, content=b"not-json"), "malformed"),
        (httpx.Response(200, json=["not", "an", "object"]), "malformed"),
        (httpx.Response(200, json={}), "malformed"),
        (httpx.Response(200, json={"results": {}}), "malformed"),
        (httpx.Response(200, json={"refusal": "blocked"}), "provider_refusal"),
    ],
)
def test_malformed_and_refusal_responses_fail_closed(response, expected_kind):
    transport, client = _transport(lambda request: response)
    try:
        with pytest.raises(TavilyTransportError) as exc:
            transport.send(_request())
    finally:
        client.close()

    assert exc.value.kind == expected_kind
    assert exc.value.detail == ""


def test_result_url_allowlist_keeps_exact_and_child_domains_only():
    payload = {
        "results": [
            {
                "url": "https://reuters.com/a",
                "title": "Exact",
                "content": "Exact domain",
            },
            {
                "url": "https://markets.reuters.com/b",
                "title": "Child",
                "content": "Child domain",
            },
            {
                "url": "https://evilreuters.com/c",
                "title": "Evil suffix",
                "content": "Must be dropped",
            },
            {
                "url": "https://example.com/d",
                "title": "Other",
                "content": "Must be dropped",
            },
        ]
    }
    transport, client = _transport(
        lambda request: httpx.Response(200, json=payload)
    )
    try:
        response = transport.send(_request())
    finally:
        client.close()

    assert [result.title for result in response.results] == ["Exact", "Child"]


def test_result_urls_strip_query_fragment_and_drop_userinfo():
    payload = {
        "results": [
            {
                "url": "http://reuters.com/a?q=raw-query#fragment",
                "title": "Safe",
                "content": "Safe content",
            },
            {
                "url": "https://user:password@reuters.com/b",
                "title": "Userinfo",
                "content": "Must be dropped",
            },
        ]
    }
    transport, client = _transport(
        lambda request: httpx.Response(200, json=payload)
    )
    try:
        response = transport.send(_request())
    finally:
        client.close()

    assert response.model_dump() == {
        "results": [
            {
                "url": "http://reuters.com/a",
                "title": "Safe",
                "snippet": "Safe content",
            }
        ]
    }


@pytest.mark.parametrize(
    "endpoint",
    [
        "http://api.tavily.com/search",
        "https://api.tavily.com/other",
        "https://user@api.tavily.com/search",
        "https://api.tavily.com/search?redirect=https://evil.test",
        "https://api.tavily.com/search#fragment",
        "https://evil.test/search",
        "https://api.tavily.com:443/search",
    ],
)
def test_noncanonical_endpoint_fails_before_http(endpoint):
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(200, json={"results": []})

    transport, client = _transport(handler, endpoint=endpoint)
    try:
        with pytest.raises(TavilyTransportError) as exc:
            transport.send(_request())
    finally:
        client.close()

    assert exc.value.kind == "malformed"
    assert calls == []


@pytest.mark.parametrize(
    "transport_request",
    [
        _request(max_results=0),
        _request(max_results=21),
        _request(include_domains=[]),
        _request(include_domains=["   "]),
    ],
)
def test_malformed_request_fails_before_http(transport_request):
    calls = []

    def handler(outbound):
        calls.append(outbound)
        return httpx.Response(200, json={"results": []})

    transport, client = _transport(handler)
    try:
        with pytest.raises(TavilyTransportError) as exc:
            transport.send(transport_request)
    finally:
        client.close()

    assert exc.value.kind == "malformed"
    assert calls == []


def test_secret_query_and_provider_body_do_not_leak_from_error_or_repr():
    raw_query = "unique sanitizer-approved query"
    provider_body = "raw provider body must remain hidden"
    transport, client = _transport(
        lambda request: httpx.Response(500, text=provider_body)
    )
    try:
        with pytest.raises(TavilyTransportError) as exc:
            transport.send(_request(query=raw_query))
    finally:
        client.close()

    serialized = f"{exc.value!r} {exc.value} {repr(transport)}"
    assert _TEST_KEY not in serialized
    assert raw_query not in serialized
    assert provider_body not in serialized


def test_real_transport_satisfies_protocol():
    assert isinstance(TavilyRealTransport(api_key=_TEST_KEY), TavilyTransport)


def test_import_has_no_env_file_or_network_side_effects(monkeypatch):
    import importlib
    import os
    import sys

    class BlockedEnvironment(dict):
        def get(self, *args, **kwargs):
            raise AssertionError("import must not read the environment")

    def blocked_open(*args, **kwargs):
        raise AssertionError("import must not read files")

    def blocked_socket(*args, **kwargs):
        raise AssertionError("import must not open sockets")

    monkeypatch.setattr(os, "environ", BlockedEnvironment())
    monkeypatch.setattr("builtins.open", blocked_open)
    monkeypatch.setattr(socket, "socket", blocked_socket)
    sys.modules.pop("app_backend.services.tavily_real_transport", None)

    module = importlib.import_module(
        "app_backend.services.tavily_real_transport"
    )

    assert module.DEFAULT_TAVILY_SEARCH_ENDPOINT == DEFAULT_TAVILY_SEARCH_ENDPOINT


def test_main_has_no_tavily_search_route():
    source = (_REPO_ROOT / "src/app_backend/main.py").read_text(encoding="utf-8")

    assert "/api/search/tavily" not in source
    assert "/api/chat" not in source
    assert "/api/ai/tavily" not in source


def test_httpx_import_is_isolated_to_real_transport():
    backend_root = _REPO_ROOT / "src/app_backend"
    importers = []
    for path in backend_root.rglob("*.py"):
        source = path.read_text(encoding="utf-8")
        if "import httpx" in source or "from httpx" in source:
            importers.append(path.relative_to(_REPO_ROOT).as_posix())

    assert importers == [
        "src/app_backend/services/tavily_real_transport.py"
    ]


def test_real_transport_source_preserves_security_boundary():
    source = (
        _REPO_ROOT / "src/app_backend/services/tavily_real_transport.py"
    ).read_text(encoding="utf-8")

    for forbidden in (
        "dotenv",
        "load_dotenv",
        '".env"',
        "'.env'",
        "open(",
        "write_text(",
        "write_bytes(",
        "FastAPI",
        "app_backend.main",
        "data.holdings",
        "data.private",
        "outputs",
        "cache",
    ):
        assert forbidden not in source
