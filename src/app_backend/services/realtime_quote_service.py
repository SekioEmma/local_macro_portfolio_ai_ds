from __future__ import annotations

import json
from datetime import date, datetime, time
from pathlib import Path
from zoneinfo import ZoneInfo

from pydantic import BaseModel, ConfigDict

from app_backend.schemas.realtime_quote import MarketState


_NEW_YORK = ZoneInfo("America/New_York")
_DEFAULT_CALENDAR_PATH = (
    Path(__file__).resolve().parents[3] / "data" / "nyse_trading_calendar.json"
)


class NyseSessions(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    pre_market_start: time
    regular_open: time
    regular_close: time
    after_hours_end: time
    early_close: time


class NyseTradingCalendar(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    version: str
    timezone: str
    coverage_start: date
    coverage_end: date
    sessions: NyseSessions
    closed_dates: frozenset[date]
    early_close_dates: frozenset[date]
    source_note: str


class MarketStateResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    market_state: MarketState
    calendar_covered: bool


def load_nyse_trading_calendar(
    path: Path | str = _DEFAULT_CALENDAR_PATH,
) -> NyseTradingCalendar:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    return NyseTradingCalendar.model_validate(payload)


def market_state_at(
    now: datetime,
    calendar: NyseTradingCalendar,
) -> MarketStateResult:
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("timezone-aware datetime required")
    local_now = now.astimezone(_NEW_YORK)
    local_date = local_now.date()
    if not calendar.coverage_start <= local_date <= calendar.coverage_end:
        return MarketStateResult(
            market_state="closed",
            calendar_covered=False,
        )
    if local_date.weekday() >= 5 or local_date in calendar.closed_dates:
        return MarketStateResult(
            market_state="closed",
            calendar_covered=True,
        )

    current = local_now.time().replace(tzinfo=None)
    sessions = calendar.sessions
    close = (
        sessions.early_close
        if local_date in calendar.early_close_dates
        else sessions.regular_close
    )
    if sessions.pre_market_start <= current < sessions.regular_open:
        state: MarketState = "pre_market"
    elif sessions.regular_open <= current < close:
        state = "regular"
    elif close <= current < sessions.after_hours_end:
        state = "after_hours"
    else:
        state = "closed"
    return MarketStateResult(
        market_state=state,
        calendar_covered=True,
    )


__all__ = [
    "MarketStateResult",
    "NyseSessions",
    "NyseTradingCalendar",
    "load_nyse_trading_calendar",
    "market_state_at",
]
