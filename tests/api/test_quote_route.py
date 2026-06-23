from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app_backend.main import (
    app,
    get_realtime_quote_service,
    get_tavily_search_execution_service,
)
from app_backend.schemas.realtime_quote import (
    FxSnapshot,
    QuoteSnapshot,
    YieldCurveSnapshot,
)
from app_backend.schemas.search_external import (
    SearchResponse,
    SearchResult,
)


@pytest.fixture(autouse=True)
def _clear_overrides():
    yield
    app.dependency_overrides.clear()


def _client() -> TestClient:
    return TestClient(app)


# --------------------------------------------------------------------------
# Fakes
# --------------------------------------------------------------------------
class FakeQuoteService:
    def __init__(
        self,
        *,
        etf=None,
        treasury=None,
        tips=None,
        fx=None,
        etf_error: Exception | None = None,
    ) -> None:
        self._etf = etf
        self._treasury = treasury
        self._tips = tips
        self._fx = fx
        self._etf_error = etf_error
        self.treasury_dates: list[str | None] = []
        self.tips_dates: list[str | None] = []

    def quote_etf(self, symbols):
        if self._etf_error is not None:
            raise self._etf_error
        return self._etf or []

    def treasury_curve(self, date=None):
        self.treasury_dates.append(date)
        return self._treasury

    def tips_curve(self, date=None):
        self.tips_dates.append(date)
        return self._tips

    def fx_rate(self, pair="USDCNH"):
        return self._fx


class RecordingExec:
    def __init__(self, response: SearchResponse) -> None:
        self.requests = []
        self.response = response

    def execute(self, request) -> SearchResponse:
        self.requests.append(request)
        return self.response


def _quote(symbol: str) -> QuoteSnapshot:
    return QuoteSnapshot(
        symbol=symbol,
        instrument_kind="etf",
        value=100.0,
        unit_or_currency="USD",
        observation_date="2026-06-22",
        quote_kind="daily_close",
        status="ok",
        stale=False,
        market_state="closed",
        calendar_covered=True,
    )


def _curve(curve_kind: str, status: str = "ok") -> YieldCurveSnapshot:
    return YieldCurveSnapshot(
        curve_kind=curve_kind,
        status=status,
        complete=status == "ok",
        market_state="closed",
        calendar_covered=True,
    )


def _fx_unavailable() -> FxSnapshot:
    return FxSnapshot(
        requested_pair="USDCNH",
        status="unavailable",
        stale=False,
        reason_code="native_usdcnh_not_configured",
        market_state="closed",
        calendar_covered=True,
    )


def _install_quote(service: FakeQuoteService) -> None:
    app.dependency_overrides[get_realtime_quote_service] = lambda: service


def _install_exec(exec_service: RecordingExec) -> None:
    app.dependency_overrides[get_tavily_search_execution_service] = (
        lambda: exec_service
    )


# --------------------------------------------------------------------------
# ETF
# --------------------------------------------------------------------------
def test_etf_multiple_symbols():
    _install_quote(
        FakeQuoteService(etf=[_quote("SPY"), _quote("QQQ"), _quote("VIX")])
    )

    response = _client().get(
        "/api/quote/etf?symbols=SPY&symbols=QQQ&symbols=VIX"
    )

    assert response.status_code == 200
    assert [item["symbol"] for item in response.json()] == [
        "SPY",
        "QQQ",
        "VIX",
    ]


def test_etf_invalid_symbol_returns_fixed_422():
    _install_quote(
        FakeQuoteService(etf_error=ValueError("unsupported symbol: secret"))
    )

    response = _client().get("/api/quote/etf?symbols=BTC")

    assert response.status_code == 422
    assert response.json()["detail"] == "unsupported_symbol"
    assert "secret" not in response.text


def test_etf_missing_symbols_is_422():
    _install_quote(FakeQuoteService(etf=[]))
    response = _client().get("/api/quote/etf")
    assert response.status_code == 422


# --------------------------------------------------------------------------
# Treasury / TIPS
# --------------------------------------------------------------------------
def test_treasury_nominal_default():
    service = FakeQuoteService(treasury=_curve("nominal_treasury"))
    _install_quote(service)

    response = _client().get("/api/quote/treasury_curve")

    assert response.status_code == 200
    assert response.json()["curve_kind"] == "nominal_treasury"
    assert service.treasury_dates == [None]


def test_treasury_tips_kind():
    service = FakeQuoteService(tips=_curve("tips_real_yield"))
    _install_quote(service)

    response = _client().get(
        "/api/quote/treasury_curve?curve_kind=tips_real_yield"
    )

    assert response.status_code == 200
    assert response.json()["curve_kind"] == "tips_real_yield"
    assert service.tips_dates == [None]


def test_treasury_invalid_curve_kind_is_422():
    _install_quote(FakeQuoteService(treasury=_curve("nominal_treasury")))

    response = _client().get(
        "/api/quote/treasury_curve?curve_kind=junk"
    )

    assert response.status_code == 422
    assert response.json()["detail"] == "unsupported_curve_kind"


def test_treasury_malformed_date_returns_unavailable_snapshot():
    # The service degrades bad dates to an unavailable snapshot, not an error.
    service = FakeQuoteService(
        treasury=_curve("nominal_treasury", status="unavailable")
    )
    _install_quote(service)

    response = _client().get(
        "/api/quote/treasury_curve?date=not-a-date"
    )

    assert response.status_code == 200
    assert response.json()["status"] == "unavailable"


# --------------------------------------------------------------------------
# FX
# --------------------------------------------------------------------------
def test_fx_usdcnh_remains_unavailable():
    _install_quote(FakeQuoteService(fx=_fx_unavailable()))

    response = _client().get("/api/quote/fx")

    body = response.json()
    assert response.status_code == 200
    assert body["status"] == "unavailable"
    assert body["reason_code"] == "native_usdcnh_not_configured"
    assert body["value"] is None


# --------------------------------------------------------------------------
# Commodity
# --------------------------------------------------------------------------
def _brent_search_response() -> SearchResponse:
    return SearchResponse(
        results=[
            SearchResult(
                url="https://www.reuters.com/markets/commodities/brent",
                title="Brent settles higher",
                snippet="Brent crude oil settled at $82.50 per barrel.",
                domain="reuters.com",
            )
        ],
        search_available=True,
        guard_passed=True,
    )


def test_commodity_brent_success():
    exec_service = RecordingExec(_brent_search_response())
    _install_exec(exec_service)

    response = _client().get("/api/quote/commodity?benchmark=brent")

    body = response.json()
    assert response.status_code == 200
    assert body["status"] == "observed"
    assert body["benchmark"] == "brent"
    assert body["value_usd_per_barrel"] == 82.50
    assert body["source_domain"] == "reuters.com"


def test_commodity_wti_unavailable_when_search_unavailable():
    exec_service = RecordingExec(
        SearchResponse(results=[], search_available=False, guard_passed=True)
    )
    _install_exec(exec_service)

    response = _client().get("/api/quote/commodity?benchmark=wti")

    body = response.json()
    assert response.status_code == 200
    assert body["status"] == "unavailable"
    assert body["reason_code"] == "search_unavailable"


def test_commodity_unavailable_when_config_disabled():
    exec_service = RecordingExec(
        SearchResponse(results=[], search_available=False, guard_passed=False)
    )
    _install_exec(exec_service)

    response = _client().get("/api/quote/commodity?benchmark=brent")

    body = response.json()
    assert response.status_code == 200
    assert body["status"] == "unavailable"
    assert body["reason_code"] == "blocked_search"


def test_commodity_does_not_bypass_budget_and_confirms_explicitly():
    exec_service = RecordingExec(_brent_search_response())
    _install_exec(exec_service)

    _client().get("/api/quote/commodity?benchmark=brent")

    assert len(exec_service.requests) == 1
    request = exec_service.requests[0]
    assert request.confirm_external_search is True
    assert request.query == "Brent crude oil price USD per barrel"
    assert request.max_results == 3
    assert request.domain_filter == [
        "reuters.com",
        "bloomberg.com",
        "oilprice.com",
    ]


# --------------------------------------------------------------------------
# Service failure / startup hygiene
# --------------------------------------------------------------------------
def test_quote_service_exception_returns_fixed_503():
    _install_quote(
        FakeQuoteService(etf_error=RuntimeError("raw provider secret"))
    )

    # RuntimeError (not ValueError) maps to 503 with a fixed detail.
    response = _client().get("/api/quote/etf?symbols=SPY")

    assert response.status_code == 503
    assert response.json()["detail"] == "quote_service_unavailable"
    assert "raw provider secret" not in response.text


def test_testclient_startup_makes_no_provider_calls(monkeypatch):
    calls = []

    def forbidden(*args, **kwargs):
        calls.append((args, kwargs))
        raise AssertionError("startup must not call providers")

    monkeypatch.setattr(
        "data_providers.alpha_vantage_history_provider.get_daily_time_series",
        forbidden,
    )
    monkeypatch.setattr(
        "data_providers.fred_provider.get_fred_series",
        forbidden,
    )
    monkeypatch.setattr(
        "data_providers.market_history_store.get_latest_observation",
        forbidden,
    )

    with TestClient(app) as client:
        status = client.get("/api/status")

    assert status.status_code == 200
    assert calls == []
