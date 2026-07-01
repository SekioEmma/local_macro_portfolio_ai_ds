"""Temporal envelope helpers for Phase F MacroBrief evidence."""
from __future__ import annotations

from datetime import date

from pydantic import BaseModel, ConfigDict, Field

from app_backend.services.run_evidence_ledger import RunEvidenceLedger


class TemporalEnvelope(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    report_generated_at: str
    market_data_cutoff: str | None = None
    policy_data_cutoff: str | None = None
    macro_data_cutoff: str | None = None
    public_news_cutoff: str | None = None
    max_market_data_age_trading_days: int | None = Field(default=None, ge=0)
    asynchronous_inputs: bool = False
    temporal_alignment_note: str | None = None


def build_temporal_envelope(
    ledger: RunEvidenceLedger,
    *,
    report_generated_at: str,
) -> TemporalEnvelope:
    market_dates: list[str] = []
    policy_dates: list[str] = []
    macro_dates: list[str] = []
    public_news_dates: list[str] = []

    for record in ledger.records:
        if record.tool_name in {"quote_etf", "treasury_curve", "quote_dxy", "commodity_quote"}:
            _append_if_present(market_dates, record.observation_date)
        elif record.source_kind == "official_primary":
            _append_if_present(policy_dates, record.release_date)
            _append_if_present(macro_dates, record.observation_date)
        elif record.source_kind == "public_reporting":
            _append_if_present(public_news_dates, record.observation_date or record.accessed_at)

    max_market_data_age = _max_trading_day_span(market_dates)
    asynchronous_inputs = (
        max_market_data_age is not None and max_market_data_age > 2
    )
    return TemporalEnvelope(
        report_generated_at=report_generated_at,
        market_data_cutoff=_max_or_none(market_dates),
        policy_data_cutoff=_max_or_none(policy_dates),
        macro_data_cutoff=_max_or_none(macro_dates),
        public_news_cutoff=_max_or_none(public_news_dates),
        max_market_data_age_trading_days=max_market_data_age,
        asynchronous_inputs=asynchronous_inputs,
        temporal_alignment_note=(
            "本次输入存在时间错配；市场数据年龄为工作日跨度近似值，以下判断不构成同一时点市场快照。"
            if asynchronous_inputs
            else None
        ),
    )


def _append_if_present(items: list[str], value: str | None) -> None:
    if value:
        items.append(value)


def _max_or_none(items: list[str]) -> str | None:
    return max(items) if items else None


def _max_trading_day_span(items: list[str]) -> int | None:
    parsed = sorted(_parse_iso_date(item) for item in items)
    parsed = [item for item in parsed if item is not None]
    if len(parsed) < 2:
        return 0 if parsed else None
    return _weekday_span(parsed[0], parsed[-1])


def _parse_iso_date(value: str) -> date | None:
    try:
        return date.fromisoformat(value[:10])
    except ValueError:
        return None


def _weekday_span(start: date, end: date) -> int:
    if end <= start:
        return 0
    days = 0
    cursor = start
    while cursor < end:
        cursor = date.fromordinal(cursor.toordinal() + 1)
        if cursor.weekday() < 5:
            days += 1
    return days


__all__ = ["TemporalEnvelope", "build_temporal_envelope"]
