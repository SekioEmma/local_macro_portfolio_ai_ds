"""Typed holdings snapshot contract for explicit Phase F agent context."""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class HoldingPosition(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ticker: str = Field(min_length=1, max_length=32)
    security_name: str | None = Field(default=None, max_length=160)
    asset_class: str | None = Field(default=None, max_length=80)
    currency: str | None = Field(default=None, min_length=3, max_length=12)
    quantity: float | None = None
    average_cost: float | None = None
    total_cost: float | None = None
    latest_price: float | None = None
    market_value: float | None = None
    unrealized_pnl: float | None = None
    realized_pnl: float | None = None
    asset_weight: float | None = None
    target_weight: float | None = None
    deviation: float | None = None


class HoldingsSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid")

    account_name: str | None = Field(default=None, max_length=160)
    positions: list[HoldingPosition] = Field(min_length=1)
    asset_class_breakdown: dict[str, float] = Field(default_factory=dict)
    portfolio_risk_summary: str | None = Field(default=None, max_length=2000)


def normalize_holdings_snapshot(value: Any) -> HoldingsSnapshot:
    return HoldingsSnapshot.model_validate(value)


def holdings_snapshot_payload(value: Any) -> dict[str, Any]:
    return normalize_holdings_snapshot(value).model_dump(mode="json", exclude_none=True)


__all__ = [
    "HoldingPosition",
    "HoldingsSnapshot",
    "holdings_snapshot_payload",
    "normalize_holdings_snapshot",
]
