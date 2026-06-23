from __future__ import annotations

import importlib
import json
import socket
import sys
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
from pydantic import ValidationError

from app_backend.schemas.realtime_quote import (
    CurvePoint,
    FxSnapshot,
    QuoteSnapshot,
    YieldCurveSnapshot,
)
from app_backend.services.realtime_quote_service import (
    RealtimeQuoteService,
    build_default_realtime_quote_service,
    load_nyse_trading_calendar,
    market_state_at,
)


_REPO_ROOT = Path(__file__).resolve().parents[2]
_CALENDAR_PATH = _REPO_ROOT / "data/nyse_trading_calendar.json"
_ET = ZoneInfo("America/New_York")


def _at(value: str) -> datetime:
    return datetime.fromisoformat(value).replace(tzinfo=_ET)


@pytest.mark.parametrize(
    ("model", "values"),
    [
        (
            QuoteSnapshot,
            {
                "symbol": "SPY",
                "instrument_kind": "etf",
                "quote_kind": "daily_close",
                "status": "unavailable",
                "stale": False,
                "market_state": "closed",
                "calendar_covered": True,
            },
        ),
        (
            CurvePoint,
            {
                "tenor": "2Y",
                "source_series": "DGS2",
                "status": "unavailable",
                "stale": False,
            },
        ),
        (
            YieldCurveSnapshot,
            {
                "curve_kind": "nominal_treasury",
                "status": "unavailable",
                "complete": False,
                "market_state": "closed",
                "calendar_covered": True,
            },
        ),
        (
            FxSnapshot,
            {
                "requested_pair": "USDCNH",
                "status": "unavailable",
                "stale": False,
                "market_state": "closed",
                "calendar_covered": True,
            },
        ),
    ],
)
def test_quote_schemas_are_frozen_and_forbid_extra(model, values):
    instance = model(**values)
    with pytest.raises(ValidationError):
        model(**values, api_key="forbidden")
    with pytest.raises(ValidationError):
        instance.status = "ok"


def test_quote_schema_fields_exclude_sensitive_surfaces():
    forbidden = {
        "api_key",
        "url",
        "headers",
        "raw_payload",
        "raw_error",
        "holdings",
        "account",
        "position",
        "transaction",
        "local_path",
    }
    for model in (QuoteSnapshot, CurvePoint, YieldCurveSnapshot, FxSnapshot):
        assert not forbidden.intersection(model.model_fields)


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("2025-03-10T03:59:59", "closed"),
        ("2025-03-10T04:00:00", "pre_market"),
        ("2025-03-10T09:29:59", "pre_market"),
        ("2025-03-10T09:30:00", "regular"),
        ("2025-03-10T15:59:59", "regular"),
        ("2025-03-10T16:00:00", "after_hours"),
        ("2025-03-10T19:59:59", "after_hours"),
        ("2025-03-10T20:00:00", "closed"),
    ],
)
def test_normal_session_boundaries(value, expected):
    result = market_state_at(_at(value), load_nyse_trading_calendar())

    assert result.market_state == expected
    assert result.calendar_covered is True


@pytest.mark.parametrize(
    "value",
    [
        "2025-03-08T12:00:00",
        "2025-01-20T12:00:00",
        "2026-04-03T12:00:00",
    ],
)
def test_weekend_and_full_holidays_are_closed(value):
    result = market_state_at(_at(value), load_nyse_trading_calendar())

    assert result.market_state == "closed"
    assert result.calendar_covered is True


def test_early_close_enters_after_hours_at_1300():
    calendar = load_nyse_trading_calendar()

    before = market_state_at(_at("2025-07-03T12:59:59"), calendar)
    after = market_state_at(_at("2025-07-03T13:00:00"), calendar)

    assert before.market_state == "regular"
    assert after.market_state == "after_hours"


def test_normal_day_remains_regular_at_1300():
    result = market_state_at(
        _at("2025-07-02T13:00:00"),
        load_nyse_trading_calendar(),
    )

    assert result.market_state == "regular"


@pytest.mark.parametrize(
    "value",
    [
        datetime(2025, 3, 7, 15, 0, tzinfo=timezone.utc),
        datetime(2025, 3, 10, 14, 0, tzinfo=timezone.utc),
        datetime(2025, 11, 1, 14, 0, tzinfo=timezone.utc),
        datetime(2025, 11, 3, 15, 0, tzinfo=timezone.utc),
    ],
)
def test_dst_aware_datetimes_are_converted_to_new_york(value):
    result = market_state_at(value, load_nyse_trading_calendar())

    assert result.calendar_covered is True


def test_outside_coverage_fails_closed():
    result = market_state_at(
        _at("2027-01-04T10:00:00"),
        load_nyse_trading_calendar(),
    )

    assert result.market_state == "closed"
    assert result.calendar_covered is False


def test_naive_datetime_fails_closed():
    with pytest.raises(ValueError, match="timezone-aware"):
        market_state_at(
            datetime(2025, 6, 2, 10, 0),
            load_nyse_trading_calendar(),
        )


def test_calendar_public_metadata_and_coverage():
    payload = json.loads(_CALENDAR_PATH.read_text(encoding="utf-8"))

    assert payload["timezone"] == "America/New_York"
    assert payload["coverage_start"] == "2025-01-01"
    assert payload["coverage_end"] == "2026-12-31"
    assert "2025-01-09" in payload["closed_dates"]
    assert "2026-11-27" in payload["early_close_dates"]


def test_import_does_not_read_env_files_or_network(monkeypatch):
    def blocked_open(*args, **kwargs):
        raise AssertionError("import must not read files")

    def blocked_socket(*args, **kwargs):
        raise AssertionError("import must not open sockets")

    monkeypatch.setattr("builtins.open", blocked_open)
    monkeypatch.setattr(socket, "socket", blocked_socket)
    sys.modules.pop("app_backend.services.realtime_quote_service", None)

    module = importlib.import_module(
        "app_backend.services.realtime_quote_service"
    )

    assert hasattr(module, "market_state_at")
    assert hasattr(module, "RealtimeQuoteService")
    assert not hasattr(module, "quote_etf")

    source = (
        _REPO_ROOT / "src/app_backend/services/realtime_quote_service.py"
    ).read_text(encoding="utf-8")
    assert "os.environ" not in source
    assert "os.getenv" not in source


def _alpha_payload(symbol: str, observation_date: str, value=100.0):
    return {
        "symbol": symbol,
        "source": "Alpha Vantage",
        "status": "ok",
        "error": None,
        "observations": [
            {
                "date": observation_date,
                "open": value,
                "high": value,
                "low": value,
                "close": value,
                "volume": 1.0,
            }
        ],
        "timestamp": "2025-07-02T21:00:00+00:00",
    }


def _fred_payload(observation_date: str, value=18.0):
    return {
        "series_id": "VIXCLS",
        "status": "ok",
        "error": None,
        "data": [{"date": observation_date, "value": value}],
        "timestamp": "2025-07-02T21:00:00+00:00",
    }


def _service(
    *,
    now: str = "2025-07-02T10:00:00",
    alpha_reader=None,
    fred_reader=None,
    history_lookup=None,
):
    return RealtimeQuoteService(
        alpha_history_reader=alpha_reader
        or (lambda symbol, outputsize: _alpha_payload(symbol, "2025-07-01")),
        fred_series_reader=fred_reader
        or (lambda series_id, limit: _fred_payload("2025-07-01")),
        history_lookup=history_lookup or (lambda metric_key: None),
        calendar_loader=load_nyse_trading_calendar,
        now_provider=lambda: _at(now),
    )


def test_service_construction_does_not_call_any_reader():
    calls = []

    def forbidden(*args, **kwargs):
        calls.append((args, kwargs))
        raise AssertionError("construction must not call dependencies")

    RealtimeQuoteService(
        alpha_history_reader=forbidden,
        fred_series_reader=forbidden,
        history_lookup=forbidden,
        calendar_loader=forbidden,
        now_provider=forbidden,
    )

    assert calls == []


def test_default_factory_only_wires_callables(monkeypatch):
    calls = []

    def forbidden(*args, **kwargs):
        calls.append((args, kwargs))
        raise AssertionError("factory must not execute providers")

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

    service = build_default_realtime_quote_service()

    assert isinstance(service, RealtimeQuoteService)
    assert calls == []


def test_quote_etf_normalizes_deduplicates_and_preserves_order():
    alpha_calls = []
    fred_calls = []

    def alpha_reader(symbol, outputsize):
        alpha_calls.append((symbol, outputsize))
        return _alpha_payload(symbol, "2025-07-01")

    def fred_reader(series_id, limit):
        fred_calls.append((series_id, limit))
        return _fred_payload("2025-07-01")

    snapshots = _service(
        alpha_reader=alpha_reader,
        fred_reader=fred_reader,
    ).quote_etf([" spy ", "QQQ", "spy", "vix"])

    assert [item.symbol for item in snapshots] == ["SPY", "QQQ", "VIX"]
    assert alpha_calls == [("SPY", "compact"), ("QQQ", "compact")]
    assert fred_calls == [("VIXCLS", 10)]


def test_supported_etfs_and_vix_map_daily_close_contracts():
    snapshots = _service().quote_etf(["SPY", "QQQ", "SHY", "GLD", "VIX"])

    assert [item.quote_kind for item in snapshots] == [
        "daily_close",
        "daily_close",
        "daily_close",
        "daily_close",
        "index_close",
    ]
    assert snapshots[0].source == "Alpha Vantage"
    assert snapshots[-1].source == "FRED"
    assert snapshots[-1].source_series == "VIXCLS"
    assert all(item.observation_date == "2025-07-01" for item in snapshots)


@pytest.mark.parametrize(
    ("now", "observation_date", "expected_status"),
    [
        ("2025-07-02T08:00:00", "2025-07-01", "ok"),
        ("2025-07-02T10:00:00", "2025-07-01", "ok"),
        ("2025-07-02T17:00:00", "2025-07-02", "ok"),
        ("2025-07-02T17:00:00", "2025-07-01", "stale"),
        ("2025-07-05T12:00:00", "2025-07-03", "ok"),
        ("2025-07-04T12:00:00", "2025-07-03", "ok"),
        ("2025-07-03T13:30:00", "2025-07-03", "ok"),
    ],
)
def test_quote_freshness_uses_completed_sessions(
    now,
    observation_date,
    expected_status,
):
    service = _service(
        now=now,
        alpha_reader=lambda symbol, outputsize: _alpha_payload(
            symbol,
            observation_date,
        ),
    )

    snapshot = service.quote_etf(["SPY"])[0]

    assert snapshot.status == expected_status
    assert snapshot.stale is (expected_status == "stale")


@pytest.mark.parametrize("symbols", [[], ["BTC"], ["SPY", "BTC"]])
def test_empty_or_unsupported_input_calls_nothing(symbols):
    calls = []

    def forbidden(*args, **kwargs):
        calls.append((args, kwargs))
        raise AssertionError("unsupported input must not call dependencies")

    service = RealtimeQuoteService(
        alpha_history_reader=forbidden,
        fred_series_reader=forbidden,
        history_lookup=forbidden,
        calendar_loader=forbidden,
        now_provider=forbidden,
    )

    with pytest.raises(ValueError):
        service.quote_etf(symbols)

    assert calls == []


@pytest.mark.parametrize(
    "alpha_reader",
    [
        lambda symbol, outputsize: {"status": "ok", "observations": []},
        lambda symbol, outputsize: {"status": "error", "error": "raw secret"},
        lambda symbol, outputsize: (_ for _ in ()).throw(
            RuntimeError("Authorization Bearer secret")
        ),
    ],
)
def test_provider_failure_without_fallback_is_unavailable(alpha_reader):
    snapshot = _service(alpha_reader=alpha_reader).quote_etf(["SPY"])[0]

    assert snapshot.status == "unavailable"
    assert snapshot.value is None
    assert snapshot.stale is False
    serialized = snapshot.model_dump_json()
    assert "raw secret" not in serialized
    assert "Authorization" not in serialized
    assert "Bearer" not in serialized


def test_safe_local_history_fallback_is_always_stale():
    snapshot = _service(
        alpha_reader=lambda symbol, outputsize: {"status": "error"},
        history_lookup=lambda metric_key: {
            "metric_key": metric_key,
            "observation_date": "2025-06-30",
            "value": 99.5,
            "status": "ok",
            "lineage": {"raw": "must not copy"},
        },
    ).quote_etf(["SPY"])[0]

    assert snapshot.status == "stale"
    assert snapshot.stale is True
    assert snapshot.value == 99.5
    assert snapshot.source == "local_market_history"
    assert "lineage" not in snapshot.model_dump_json()


@pytest.mark.parametrize(
    "row",
    [
        {"metric_key": "wrong", "observation_date": "2025-06-30", "value": 1, "status": "ok"},
        {"metric_key": "spy_close", "observation_date": "bad", "value": 1, "status": "ok"},
        {"metric_key": "spy_close", "observation_date": "2025-06-30", "value": 1, "status": "stale"},
        {"metric_key": "spy_close", "observation_date": "2025-06-30", "value": "bad", "status": "ok"},
    ],
)
def test_unsafe_history_fallback_is_rejected(row):
    snapshot = _service(
        alpha_reader=lambda symbol, outputsize: {"status": "error"},
        history_lookup=lambda metric_key: row,
    ).quote_etf(["SPY"])[0]

    assert snapshot.status == "unavailable"
    assert snapshot.reason_code == "no_safe_history_fallback"


def test_calendar_outside_coverage_never_claims_fresh():
    snapshot = _service(
        now="2027-01-04T10:00:00",
        alpha_reader=lambda symbol, outputsize: _alpha_payload(
            symbol,
            "2027-01-03",
        ),
    ).quote_etf(["SPY"])[0]

    assert snapshot.status == "stale"
    assert snapshot.calendar_covered is False
    assert snapshot.reason_code == "calendar_not_covered"
