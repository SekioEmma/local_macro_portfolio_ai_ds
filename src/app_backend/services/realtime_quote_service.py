from __future__ import annotations

import json
from collections.abc import Callable
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from pydantic import BaseModel, ConfigDict

from app_backend.schemas.realtime_quote import (
    CurvePoint,
    FxSnapshot,
    MarketState,
    QuoteSnapshot,
    YieldCurveSnapshot,
)


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


AlphaHistoryReader = Callable[[str, str], dict[str, Any]]
FredSeriesReader = Callable[[str, int], dict[str, Any]]
HistoryLookup = Callable[[str], dict[str, Any] | None]
CalendarLoader = Callable[[], NyseTradingCalendar]
NowProvider = Callable[[], datetime]

_SUPPORTED_ETFS = ("SPY", "QQQ", "SHY", "GLD")
_SUPPORTED_SYMBOLS = frozenset((*_SUPPORTED_ETFS, "VIX"))
_HISTORY_METRIC_KEYS = {
    "SPY": "proxy_spy_close",
    "QQQ": "proxy_qqq_close",
    "SHY": "proxy_shy_close",
    "GLD": "proxy_gld_close",
    "VIX": "vix",
}
_TREASURY_SERIES = (
    ("2Y", "DGS2"),
    ("10Y", "DGS10"),
    ("20Y", "DGS20"),
    ("30Y", "DGS30"),
)
_TIPS_SERIES = (
    ("5Y", "DFII5"),
    ("10Y", "DFII10"),
    ("30Y", "DFII30"),
)


class RealtimeQuoteService:
    def __init__(
        self,
        *,
        alpha_history_reader: AlphaHistoryReader,
        fred_series_reader: FredSeriesReader,
        history_lookup: HistoryLookup,
        calendar_loader: CalendarLoader | None = None,
        now_provider: NowProvider | None = None,
    ) -> None:
        self._alpha_history_reader = alpha_history_reader
        self._fred_series_reader = fred_series_reader
        self._history_lookup = history_lookup
        self._calendar_loader = calendar_loader or load_nyse_trading_calendar
        self._now_provider = now_provider or _utc_now

    def quote_etf(self, symbols: list[str]) -> list[QuoteSnapshot]:
        normalized = _normalize_symbols(symbols)
        calendar = self._calendar_loader()
        now = self._now_provider()
        state = market_state_at(now, calendar)
        expected_date = _latest_completed_session_date(now, calendar)
        return [
            self._quote_symbol(
                symbol,
                now=now,
                state=state,
                expected_date=expected_date,
            )
            for symbol in normalized
        ]

    def treasury_curve(
        self,
        date: str | None = None,
    ) -> YieldCurveSnapshot:
        return self._yield_curve(
            curve_kind="nominal_treasury",
            series=_TREASURY_SERIES,
            requested_date=date,
        )

    def tips_curve(
        self,
        date: str | None = None,
    ) -> YieldCurveSnapshot:
        return self._yield_curve(
            curve_kind="tips_real_yield",
            series=_TIPS_SERIES,
            requested_date=date,
        )

    def fx_rate(self, pair: str = "USDCNH") -> FxSnapshot:
        requested_pair = str(pair).strip().upper()
        calendar = self._calendar_loader()
        state = market_state_at(self._now_provider(), calendar)
        reason = (
            "native_usdcnh_not_configured"
            if requested_pair == "USDCNH"
            else "unsupported_pair"
        )
        return FxSnapshot(
            requested_pair=requested_pair,
            status="unavailable",
            stale=False,
            reason_code=reason,
            market_state=state.market_state,
            calendar_covered=state.calendar_covered,
        )

    def _yield_curve(
        self,
        *,
        curve_kind: str,
        series: tuple[tuple[str, str], ...],
        requested_date: str | None,
    ) -> YieldCurveSnapshot:
        calendar = self._calendar_loader()
        now = self._now_provider()
        state = market_state_at(now, calendar)
        selection_date = _curve_selection_date(
            requested_date,
            now=now,
            calendar=calendar,
        )
        if selection_date is None:
            return YieldCurveSnapshot(
                curve_kind=curve_kind,
                requested_date=requested_date,
                status="unavailable",
                complete=False,
                market_state=state.market_state,
                calendar_covered=state.calendar_covered,
            )

        limit = 5000 if requested_date is not None else 10
        points = [
            self._curve_point(
                tenor=tenor,
                series_id=series_id,
                selection_date=selection_date,
                limit=limit,
            )
            for tenor, series_id in series
        ]
        available = [point for point in points if point.value is not None]
        complete = len(available) == len(points)
        if complete and not any(point.stale for point in points):
            status = "ok"
        elif available:
            status = "partial"
        else:
            status = "unavailable"
        dates = {point.observation_date for point in available}
        selected_date = dates.pop() if len(dates) == 1 else None
        return YieldCurveSnapshot(
            curve_kind=curve_kind,
            requested_date=requested_date,
            selected_observation_date=selected_date,
            points=points,
            status=status,
            complete=complete,
            market_state=state.market_state,
            calendar_covered=state.calendar_covered,
        )

    def _curve_point(
        self,
        *,
        tenor: str,
        series_id: str,
        selection_date: date,
        limit: int,
    ) -> CurvePoint:
        try:
            payload = self._fred_series_reader(series_id, limit)
            observation = _latest_fred_observation(payload, selection_date)
        except Exception:
            payload = None
            observation = None
        if observation is not None:
            observed_date, value = observation
            return CurvePoint(
                tenor=tenor,
                value=value,
                observation_date=observed_date.isoformat(),
                source_series=series_id,
                status="ok",
                stale=False,
            )

        fallback = self._safe_curve_fallback(
            series_id,
            selection_date=selection_date,
        )
        if fallback is not None:
            observed_date, value = fallback
            return CurvePoint(
                tenor=tenor,
                value=value,
                observation_date=observed_date.isoformat(),
                source_series=series_id,
                status="stale",
                stale=True,
            )
        reason = (
            "provider_unavailable"
            if not isinstance(payload, dict) or payload.get("status") != "ok"
            else "malformed_provider_data"
        )
        return CurvePoint(
            tenor=tenor,
            source_series=series_id,
            status="unavailable",
            stale=False,
            reason_code=reason,
        )

    def _safe_curve_fallback(
        self,
        series_id: str,
        *,
        selection_date: date,
    ) -> tuple[date, float] | None:
        metric_key = series_id.lower()
        try:
            row = self._history_lookup(metric_key)
        except Exception:
            return None
        fallback = _safe_history_observation(
            row,
            expected_metric_key=metric_key,
        )
        if fallback is None or fallback[0] > selection_date:
            return None
        return fallback

    def _quote_symbol(
        self,
        symbol: str,
        *,
        now: datetime,
        state: MarketStateResult,
        expected_date: date | None,
    ) -> QuoteSnapshot:
        local_date = now.astimezone(_NEW_YORK).date()
        try:
            if symbol == "VIX":
                payload = self._fred_series_reader("VIXCLS", 10)
                observation = _latest_fred_observation(payload, local_date)
                source = "FRED"
                source_series = "VIXCLS"
                quote_kind = "index_close"
                instrument_kind = "volatility_index"
                unit = "index"
            else:
                payload = self._alpha_history_reader(symbol, "compact")
                observation = _latest_alpha_observation(payload, local_date)
                source = "Alpha Vantage"
                source_series = symbol
                quote_kind = "daily_close"
                instrument_kind = "etf"
                unit = "USD"
        except Exception:
            return self._fallback_snapshot(
                symbol,
                state=state,
                quote_kind="index_close" if symbol == "VIX" else "daily_close",
                instrument_kind=(
                    "volatility_index" if symbol == "VIX" else "etf"
                ),
                unit="index" if symbol == "VIX" else "USD",
                reason_code="provider_unavailable",
            )

        if observation is None:
            reason = (
                "provider_unavailable"
                if isinstance(payload, dict) and payload.get("status") != "ok"
                else "malformed_provider_data"
            )
            return self._fallback_snapshot(
                symbol,
                state=state,
                quote_kind=quote_kind,
                instrument_kind=instrument_kind,
                unit=unit,
                reason_code=reason,
            )

        observed_date, value = observation
        stale = (
            not state.calendar_covered
            or expected_date is None
            or observed_date < expected_date
        )
        return QuoteSnapshot(
            symbol=symbol,
            instrument_kind=instrument_kind,
            value=value,
            unit_or_currency=unit,
            observation_date=observed_date.isoformat(),
            fetched_at=_safe_timestamp(payload.get("timestamp")),
            source=source,
            source_series=source_series,
            quote_kind=quote_kind,
            status="stale" if stale else "ok",
            stale=stale,
            reason_code="calendar_not_covered"
            if not state.calendar_covered
            else None,
            market_state=state.market_state,
            calendar_covered=state.calendar_covered,
        )

    def _fallback_snapshot(
        self,
        symbol: str,
        *,
        state: MarketStateResult,
        quote_kind: str,
        instrument_kind: str,
        unit: str,
        reason_code: str,
    ) -> QuoteSnapshot:
        try:
            fallback_row = self._history_lookup(_HISTORY_METRIC_KEYS[symbol])
        except Exception:
            fallback_row = {}
        fallback = _safe_history_observation(
            fallback_row,
            expected_metric_key=_HISTORY_METRIC_KEYS[symbol],
        )
        if fallback is not None:
            observed_date, value = fallback
            return QuoteSnapshot(
                symbol=symbol,
                instrument_kind=instrument_kind,
                value=value,
                unit_or_currency=unit,
                observation_date=observed_date.isoformat(),
                source="local_market_history",
                source_series=_HISTORY_METRIC_KEYS[symbol],
                quote_kind=quote_kind,
                status="stale",
                stale=True,
                market_state=state.market_state,
                calendar_covered=state.calendar_covered,
            )
        safe_reason = (
            "no_safe_history_fallback"
            if fallback_row is not None
            else reason_code
        )
        return QuoteSnapshot(
            symbol=symbol,
            instrument_kind=instrument_kind,
            unit_or_currency=unit,
            quote_kind=quote_kind,
            status="unavailable",
            stale=False,
            reason_code=safe_reason,
            market_state=state.market_state,
            calendar_covered=state.calendar_covered,
        )


def build_default_realtime_quote_service() -> RealtimeQuoteService:
    from data_providers import (
        alpha_vantage_history_provider,
        fred_provider,
        market_history_store,
    )

    return RealtimeQuoteService(
        alpha_history_reader=alpha_vantage_history_provider.get_daily_time_series,
        fred_series_reader=fred_provider.get_fred_series,
        history_lookup=market_history_store.get_latest_observation,
    )


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


def _normalize_symbols(symbols: list[str]) -> list[str]:
    if not symbols:
        raise ValueError("at least one supported symbol is required")
    normalized: list[str] = []
    for raw_symbol in symbols:
        symbol = str(raw_symbol).strip().upper()
        if symbol not in _SUPPORTED_SYMBOLS:
            raise ValueError("unsupported symbol")
        if symbol not in normalized:
            normalized.append(symbol)
    return normalized


def _latest_alpha_observation(
    payload: Any,
    max_date: date,
) -> tuple[date, float] | None:
    if not isinstance(payload, dict) or payload.get("status") != "ok":
        return None
    observations = payload.get("observations")
    if not isinstance(observations, list):
        return None
    candidates = []
    for item in observations:
        if not isinstance(item, dict):
            continue
        observed_date = _date_or_none(item.get("date"))
        value = _float_or_none(item.get("close"))
        if observed_date is not None and observed_date <= max_date and value is not None:
            candidates.append((observed_date, value))
    return max(candidates, default=None)


def _latest_fred_observation(
    payload: Any,
    max_date: date,
) -> tuple[date, float] | None:
    if not isinstance(payload, dict) or payload.get("status") != "ok":
        return None
    observations = payload.get("data")
    if not isinstance(observations, list):
        return None
    candidates = []
    for item in observations:
        if not isinstance(item, dict):
            continue
        observed_date = _date_or_none(item.get("date"))
        value = _float_or_none(item.get("value"))
        if observed_date is not None and observed_date <= max_date and value is not None:
            candidates.append((observed_date, value))
    return max(candidates, default=None)


def _safe_history_observation(
    row: Any,
    *,
    expected_metric_key: str,
) -> tuple[date, float] | None:
    if not isinstance(row, dict):
        return None
    if row.get("metric_key") != expected_metric_key or row.get("status") != "ok":
        return None
    observed_date = _date_or_none(row.get("observation_date"))
    value = _float_or_none(row.get("value"))
    if observed_date is None or value is None:
        return None
    return observed_date, value


def _latest_completed_session_date(
    now: datetime,
    calendar: NyseTradingCalendar,
) -> date | None:
    local_now = now.astimezone(_NEW_YORK)
    local_date = local_now.date()
    if not calendar.coverage_start <= local_date <= calendar.coverage_end:
        return None
    close = (
        calendar.sessions.early_close
        if local_date in calendar.early_close_dates
        else calendar.sessions.regular_close
    )
    is_session = (
        local_date.weekday() < 5 and local_date not in calendar.closed_dates
    )
    if is_session and local_now.time().replace(tzinfo=None) >= close:
        return local_date
    return _previous_session_date(local_date, calendar)


def _previous_session_date(
    start: date,
    calendar: NyseTradingCalendar,
) -> date | None:
    candidate = start - timedelta(days=1)
    while candidate >= calendar.coverage_start:
        if candidate.weekday() < 5 and candidate not in calendar.closed_dates:
            return candidate
        candidate -= timedelta(days=1)
    return None


def _curve_selection_date(
    requested_date: str | None,
    *,
    now: datetime,
    calendar: NyseTradingCalendar,
) -> date | None:
    today = now.astimezone(_NEW_YORK).date()
    if requested_date is None:
        if not calendar.coverage_start <= today <= calendar.coverage_end:
            return None
        return today
    parsed = _date_or_none(requested_date)
    if parsed is None:
        return None
    if parsed > today:
        return None
    if not calendar.coverage_start <= parsed <= calendar.coverage_end:
        return None
    return parsed


def _date_or_none(value: Any) -> date | None:
    if not isinstance(value, str):
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def _float_or_none(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed == parsed and abs(parsed) != float("inf") else None


def _safe_timestamp(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    try:
        datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return value


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


__all__ = [
    "MarketStateResult",
    "NyseSessions",
    "NyseTradingCalendar",
    "RealtimeQuoteService",
    "build_default_realtime_quote_service",
    "load_nyse_trading_calendar",
    "market_state_at",
]
