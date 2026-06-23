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
    assert not hasattr(module, "RealtimeQuoteService")
    assert not hasattr(module, "quote_etf")

    source = (
        _REPO_ROOT / "src/app_backend/services/realtime_quote_service.py"
    ).read_text(encoding="utf-8")
    assert "os.environ" not in source
    assert "os.getenv" not in source
