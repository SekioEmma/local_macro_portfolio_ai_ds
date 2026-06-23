from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, model_validator


CommodityBenchmark = Literal["brent", "wti"]
CommodityQuoteStatus = Literal["observed", "unavailable"]
CommodityReasonCode = Literal[
    "search_unavailable",
    "blocked_search",
    "no_safe_price_match",
    "ambiguous_price_match",
    "unsupported_benchmark",
]


class CommodityQuoteSnapshot(BaseModel):
    """Read-only commodity benchmark price snapshot.

    The snapshot never carries snippets, raw payloads, raw errors, headers,
    API keys, holdings, account, position, transaction data, or local paths.
    It also never carries trade, forecast, probability, or advice fields.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    benchmark: str
    value_usd_per_barrel: float | None = None
    unit: Literal["USD/bbl"] | None = None
    status: CommodityQuoteStatus
    reason_code: CommodityReasonCode | None = None
    source_url: str | None = None
    source_domain: str | None = None
    source_title: str | None = None

    @model_validator(mode="after")
    def _validate_status_consistency(self) -> "CommodityQuoteSnapshot":
        if self.status == "observed":
            if (
                self.value_usd_per_barrel is None
                or self.unit is None
                or self.source_url is None
                or self.source_domain is None
            ):
                raise ValueError(
                    "observed snapshot requires value, unit, source_url, "
                    "and source_domain"
                )
            if self.reason_code is not None:
                raise ValueError("observed snapshot must not carry a reason_code")
        else:
            if self.reason_code is None:
                raise ValueError("unavailable snapshot requires a reason_code")
            if self.value_usd_per_barrel is not None or self.unit is not None:
                raise ValueError(
                    "unavailable snapshot must not carry value or unit"
                )
        return self


__all__ = [
    "CommodityBenchmark",
    "CommodityQuoteSnapshot",
    "CommodityQuoteStatus",
    "CommodityReasonCode",
]
