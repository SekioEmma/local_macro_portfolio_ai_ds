from __future__ import annotations

import inspect
import socket
from pathlib import Path

import httpx
import pytest

from data_providers.official_calendar_real_transport import (
    FetchedOfficialCalendarPayload,
    OfficialCalendarRealTransport,
    OfficialCalendarSource,
    OfficialCalendarTransportError,
    get_fixed_url,
)


ROOT = Path(__file__).parents[2]
TRANSPORT_SOURCE = ROOT / "src" / "data_providers" / "official_calendar_real_transport.py"


def _fake_response(body: str, status_code: int = 200, content_type: str = "text/calendar"):
    chunks = [body.encode("utf-8")]

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            status_code=status_code,
            headers={"content-type": content_type},
            stream=httpx.ByteStream(b"".join(chunks)),
        )

    return httpx.MockTransport(handler)


def _transport_with_mock(mock_transport: httpx.MockTransport) -> OfficialCalendarRealTransport:
    transport = OfficialCalendarRealTransport()
    original_fetch = transport.fetch

    def patched_fetch(source):
        original_client = httpx.Client
        try:
            httpx.Client = lambda **kwargs: httpx.Client.__new__(httpx.Client) or original_client(
                **{**kwargs, "transport": mock_transport}
            )
            httpx.Client = lambda **kwargs: original_client(**{**kwargs, "transport": mock_transport})
            return original_fetch(source)
        finally:
            httpx.Client = original_client

    transport.fetch = patched_fetch
    return transport


def test_only_bls_and_bea_sources_accepted():
    transport = OfficialCalendarRealTransport()
    with pytest.raises(OfficialCalendarTransportError) as exc_info:
        transport.fetch("fred")
    assert exc_info.value.code == "unsupported_source"


def test_unsupported_source_fomc():
    transport = OfficialCalendarRealTransport()
    with pytest.raises(OfficialCalendarTransportError) as exc_info:
        transport.fetch("fomc")
    assert exc_info.value.code == "unsupported_source"


def test_bls_source_key():
    assert OfficialCalendarSource.BLS == "bls"


def test_bea_source_key():
    assert OfficialCalendarSource.BEA == "bea"


def test_fixed_url_bls():
    assert get_fixed_url(OfficialCalendarSource.BLS) == "https://www.bls.gov/schedule/news_release/bls.ics"


def test_fixed_url_bea():
    assert get_fixed_url(OfficialCalendarSource.BEA) == "https://apps.bea.gov/API/signup/release_dates.json"


def test_fetch_does_not_accept_url_parameter():
    sig = inspect.signature(OfficialCalendarRealTransport.fetch)
    params = list(sig.parameters.keys())
    assert params == ["self", "source"]


def test_import_creates_no_network(monkeypatch):
    calls = []
    monkeypatch.setattr(socket, "create_connection", lambda *a, **kw: calls.append(1) or (_ for _ in ()).throw(AssertionError))
    import importlib
    import sys
    mod_key = "data_providers.official_calendar_real_transport"
    saved = sys.modules.pop(mod_key)
    try:
        importlib.import_module(mod_key)
        assert calls == []
    finally:
        sys.modules[mod_key] = saved


def test_construction_creates_no_network(monkeypatch):
    calls = []
    monkeypatch.setattr(socket, "create_connection", lambda *a, **kw: calls.append(1) or (_ for _ in ()).throw(AssertionError))
    OfficialCalendarRealTransport()
    assert calls == []


def test_bls_success_with_mock_transport():
    ics_body = "BEGIN:VCALENDAR\nEND:VCALENDAR"
    mock = _fake_response(ics_body, content_type="text/calendar")
    transport = _transport_with_mock(mock)
    result = transport.fetch(OfficialCalendarSource.BLS)
    assert isinstance(result, FetchedOfficialCalendarPayload)
    assert result.source == OfficialCalendarSource.BLS
    assert result.body == ics_body
    assert result.content_type == "text/calendar"


def test_bea_success_with_mock_transport():
    json_body = '{"test": true}'
    mock = _fake_response(json_body, content_type="application/json")
    transport = _transport_with_mock(mock)
    result = transport.fetch(OfficialCalendarSource.BEA)
    assert isinstance(result, FetchedOfficialCalendarPayload)
    assert result.source == OfficialCalendarSource.BEA
    assert result.content_type == "application/json"


def test_http_500_raises_fetch_failed():
    mock = _fake_response("error", status_code=500, content_type="text/calendar")
    transport = _transport_with_mock(mock)
    with pytest.raises(OfficialCalendarTransportError) as exc_info:
        transport.fetch(OfficialCalendarSource.BLS)
    assert exc_info.value.code == "fetch_failed"


def test_http_301_redirect_raises_fetch_failed():
    mock = _fake_response("redirect", status_code=301, content_type="text/calendar")
    transport = _transport_with_mock(mock)
    with pytest.raises(OfficialCalendarTransportError) as exc_info:
        transport.fetch(OfficialCalendarSource.BLS)
    assert exc_info.value.code == "fetch_failed"


def test_http_302_redirect_raises_fetch_failed():
    mock = _fake_response("redirect", status_code=302, content_type="text/calendar")
    transport = _transport_with_mock(mock)
    with pytest.raises(OfficialCalendarTransportError) as exc_info:
        transport.fetch(OfficialCalendarSource.BLS)
    assert exc_info.value.code == "fetch_failed"


def test_wrong_content_type_raises_invalid_response():
    mock = _fake_response("<html>", status_code=200, content_type="text/html")
    transport = _transport_with_mock(mock)
    with pytest.raises(OfficialCalendarTransportError) as exc_info:
        transport.fetch(OfficialCalendarSource.BLS)
    assert exc_info.value.code == "invalid_response"


def test_bea_wrong_content_type_raises_invalid_response():
    mock = _fake_response("{}", status_code=200, content_type="text/plain")
    transport = _transport_with_mock(mock)
    with pytest.raises(OfficialCalendarTransportError) as exc_info:
        transport.fetch(OfficialCalendarSource.BEA)
    assert exc_info.value.code == "invalid_response"


def test_body_over_1mib_raises_response_too_large():
    big_body = "x" * (1_048_576 + 100)
    mock = _fake_response(big_body, content_type="text/calendar")
    transport = _transport_with_mock(mock)
    with pytest.raises(OfficialCalendarTransportError) as exc_info:
        transport.fetch(OfficialCalendarSource.BLS)
    assert exc_info.value.code == "response_too_large"


def test_connection_error_raises_fetch_failed(monkeypatch):
    def raise_connection(*a, **kw):
        raise httpx.ConnectError("connection refused")

    transport = OfficialCalendarRealTransport()
    monkeypatch.setattr(httpx.Client, "__init__", lambda self, **kw: None)
    monkeypatch.setattr(httpx.Client, "__enter__", lambda self: self)
    monkeypatch.setattr(httpx.Client, "__exit__", lambda self, *a: None)
    monkeypatch.setattr(httpx.Client, "stream", raise_connection)
    with pytest.raises(OfficialCalendarTransportError) as exc_info:
        transport.fetch(OfficialCalendarSource.BLS)
    assert exc_info.value.code == "fetch_failed"


def test_timeout_raises_fetch_failed(monkeypatch):
    def raise_timeout(*a, **kw):
        raise httpx.ReadTimeout("timeout")

    transport = OfficialCalendarRealTransport()
    monkeypatch.setattr(httpx.Client, "__init__", lambda self, **kw: None)
    monkeypatch.setattr(httpx.Client, "__enter__", lambda self: self)
    monkeypatch.setattr(httpx.Client, "__exit__", lambda self, *a: None)
    monkeypatch.setattr(httpx.Client, "stream", raise_timeout)
    with pytest.raises(OfficialCalendarTransportError) as exc_info:
        transport.fetch(OfficialCalendarSource.BLS)
    assert exc_info.value.code == "fetch_failed"


def test_no_retry_on_failure(monkeypatch):
    call_count = {"n": 0}

    def counting_stream(self, *a, **kw):
        call_count["n"] += 1
        raise httpx.ConnectError("refused")

    transport = OfficialCalendarRealTransport()
    monkeypatch.setattr(httpx.Client, "__init__", lambda self, **kw: None)
    monkeypatch.setattr(httpx.Client, "__enter__", lambda self: self)
    monkeypatch.setattr(httpx.Client, "__exit__", lambda self, *a: None)
    monkeypatch.setattr(httpx.Client, "stream", counting_stream)
    with pytest.raises(OfficialCalendarTransportError):
        transport.fetch(OfficialCalendarSource.BLS)
    assert call_count["n"] == 1


def test_no_raw_endpoint_in_error():
    try:
        transport = OfficialCalendarRealTransport()
        transport.fetch("unknown_source")
    except OfficialCalendarTransportError as exc:
        assert "bls.gov" not in str(exc)
        assert "bea.gov" not in str(exc)
        assert "https://" not in str(exc)


def test_no_raw_body_in_error():
    mock = _fake_response("secret body", status_code=500, content_type="text/calendar")
    transport = _transport_with_mock(mock)
    with pytest.raises(OfficialCalendarTransportError) as exc_info:
        transport.fetch(OfficialCalendarSource.BLS)
    assert "secret body" not in str(exc_info.value)


def test_transport_source_only_imports_httpx():
    source = TRANSPORT_SOURCE.read_text(encoding="utf-8")
    assert "import httpx" in source
    assert "import requests" not in source
    assert "import aiohttp" not in source
    assert "os.environ" not in source
    assert "os.getenv" not in source
    assert "dotenv" not in source
    assert "config" not in source.lower().split("import")[-1] if "import" in source else True


def test_follow_redirects_disabled():
    source = TRANSPORT_SOURCE.read_text(encoding="utf-8")
    assert "follow_redirects=False" in source


def test_payload_dataclass_fields():
    from dataclasses import fields as dc_fields
    names = {f.name for f in dc_fields(FetchedOfficialCalendarPayload)}
    assert names == {"source", "body", "content_type"}
    forbidden = {"url", "headers", "raw", "endpoint", "status_code"}
    assert not names & forbidden


def test_transport_has_no_env_config_or_api_key_read():
    source = TRANSPORT_SOURCE.read_text(encoding="utf-8")
    for token in ["os.environ", "os.getenv", "API_KEY", "dotenv", "load_dotenv", ".env", "config_loader"]:
        assert token not in source
