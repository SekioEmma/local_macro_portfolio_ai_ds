from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


MarketState = Literal["pre_market", "regular", "after_hours", "closed"]
QuoteStatus = Literal["ok", "stale", "unavailable"]
CurveStatus = Literal["ok", "partial", "unavailable"]
ReasonCode = Literal[
    "provider_unavailable",
    "malformed_provider_data",
    "no_safe_history_fallback",
    "calendar_not_covered",
    "missing_maturity",
    "invalid_date",
    "future_date",
    "unsupported_pair",
    "native_usdcnh_not_configured",
]


class QuoteSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    symbol: str
    instrument_kind: str
    value: float | None = None
    unit_or_currency: str | None = None
    observation_date: str | None = None
    fetched_at: str | None = None
    source: str | None = None
    source_series: str | None = None
    quote_kind: str
    status: QuoteStatus
    stale: bool
    reason_code: ReasonCode | None = None
    market_state: MarketState
    calendar_covered: bool


class CurvePoint(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    tenor: str
    value: float | None = None
    observation_date: str | None = None
    source_series: str
    status: QuoteStatus
    stale: bool
    reason_code: ReasonCode | None = None


class YieldCurveSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    curve_kind: Literal["nominal_treasury", "tips_real_yield"]
    requested_date: str | None = None
    selected_observation_date: str | None = None
    points: list[CurvePoint] = Field(default_factory=list)
    status: CurveStatus
    complete: bool
    market_state: MarketState
    calendar_covered: bool


class FxSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    requested_pair: str
    observed_pair: str | None = None
    value: float | None = None
    observation_date: str | None = None
    source: str | None = None
    source_series: str | None = None
    status: QuoteStatus
    stale: bool
    reason_code: ReasonCode | None = None
    market_state: MarketState
    calendar_covered: bool


__all__ = [
    "CurvePoint",
    "CurveStatus",
    "FxSnapshot",
    "MarketState",
    "QuoteSnapshot",
    "QuoteStatus",
    "ReasonCode",
    "YieldCurveSnapshot",
]
