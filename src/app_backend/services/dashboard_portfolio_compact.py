from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Any

from app_backend.schemas.responses import DashboardMetric
from app_backend.services.dashboard_evidence_policy import ai_context_allowed
from app_backend.services.dashboard_metric_catalog import (
    PORTFOLIO_COMPACT_INTERPRETATION_HINT,
)
from app_backend.services.dashboard_metric_builder import (
    format_value,
    missing_metric,
    to_float,
)
from app_backend.services.dashboard_report_loader import ReportState
from app_backend.services.dashboard_summary_assembly import string_or_none


PORTFOLIO_TARGET_ASSET_CLASSES = ("sp500", "nasdaq100", "short_bond", "gold")
PORTFOLIO_DEFAULT_TARGET_WEIGHTS = {
    "sp500": 0.50,
    "nasdaq100": 0.20,
    "short_bond": 0.20,
    "gold": 0.10,
}


@dataclass(frozen=True)
class PortfolioDeviationCompact:
    generated_at: str | None
    holdings_updated_at: str | None
    target_weights: dict[str, float]
    current_weights: dict[str, float]
    deviation_pp: dict[str, float]
    max_deviation_asset: str | None
    max_deviation_pp: float | None
    equity_total_current_weight: float | None
    equity_total_target_weight: float | None
    equity_total_deviation_pp: float | None
    cash_reserve_status: str
    stale_status: str
    notes: list[str]


def portfolio_compact_metric(
    *,
    module_key: str,
    reports: tuple[ReportState, ...],
    metric_key: str,
    display_name: str,
    unit: str | None,
    format_kind: str,
) -> DashboardMetric | None:
    if module_key != "portfolio_deviation":
        return None
    report = next((item for item in reports if item.name == "portfolio_snapshot"), None)
    if report is None:
        return None
    compact = portfolio_deviation_compact(report)
    if compact is None:
        return None
    value_map: dict[str, Any] = {
        "max_deviation_asset": compact.max_deviation_asset,
        "max_deviation_pp": compact.max_deviation_pp,
        "equity_total_deviation_pp": compact.equity_total_deviation_pp,
        "cash_reserve_status": compact.cash_reserve_status,
        "holdings_updated_at": compact.holdings_updated_at,
    }
    if metric_key not in value_map:
        return None

    value = value_map[metric_key]
    if value is None:
        return missing_metric(
            metric_key=metric_key,
            display_name=display_name,
            unit=unit,
            status="missing",
            generated_at=compact.generated_at,
            interpretation_hint=PORTFOLIO_COMPACT_INTERPRETATION_HINT,
            dgs30_breakout_missing_reason="",
        )

    status = portfolio_compact_metric_status(compact, metric_key)
    source = "local_portfolio_compact"
    source_badge = "local"
    observation_date = compact.holdings_updated_at
    freshness_status = compact.stale_status
    return DashboardMetric(
        metric_key=metric_key,
        display_name=display_name,
        value=value,
        value_text=format_value(value, format_kind, status),
        unit=unit,
        status=status,
        source=source,
        source_badge=source_badge,
        observation_date=observation_date,
        generated_at=compact.generated_at,
        freshness_status=freshness_status,
        missing_reason=None,
        interpretation_hint=PORTFOLIO_COMPACT_INTERPRETATION_HINT,
        ai_context_allowed=ai_context_allowed(
            status=status,
            source=source,
            source_badge=source_badge,
            observation_date=observation_date,
            generated_at=compact.generated_at,
            freshness_status=freshness_status,
            interpretation_hint=PORTFOLIO_COMPACT_INTERPRETATION_HINT,
        ),
    )


def portfolio_deviation_compact(report: ReportState) -> PortfolioDeviationCompact | None:
    if not isinstance(report.data, dict):
        return None
    data = report.data
    embedded = data.get("portfolio_deviation_compact")
    compact_payload = embedded if isinstance(embedded, dict) else data

    target_weights = portfolio_weight_map(
        compact_payload.get("target_weights")
        or compact_payload.get("target_allocation")
        or PORTFOLIO_DEFAULT_TARGET_WEIGHTS,
        default=PORTFOLIO_DEFAULT_TARGET_WEIGHTS,
    )
    current_weights = portfolio_weight_map(
        compact_payload.get("current_weights") or compact_payload.get("weights_ex_cash")
    )
    deviation_pp = portfolio_deviation_pp_map(compact_payload, current_weights, target_weights)
    if not current_weights and not deviation_pp:
        return None

    max_asset = max_deviation_asset(deviation_pp)
    max_pp = round(deviation_pp[max_asset], 4) if max_asset is not None else None
    equity_current = sum_weights(current_weights, ("sp500", "nasdaq100"))
    equity_target = sum_weights(target_weights, ("sp500", "nasdaq100"))
    equity_deviation_pp = (
        round((equity_current - equity_target) * 100.0, 4)
        if equity_current is not None and equity_target is not None
        else None
    )
    holdings_updated_at = portfolio_holdings_updated_at(data)
    generated_at = string_or_none(
        compact_payload.get("generated_at")
        or data.get("generated_at")
        or data.get("updated_at")
    )
    stale_status = portfolio_stale_status(
        holdings_updated_at=holdings_updated_at,
        generated_at=generated_at,
        existing_status=string_or_none(
            compact_payload.get("stale_status")
            or data.get("holdings_freshness_status")
        ),
    )
    cash_reserve_status = portfolio_cash_reserve_status(data)

    return PortfolioDeviationCompact(
        generated_at=generated_at,
        holdings_updated_at=holdings_updated_at,
        target_weights={key: round(value * 100.0, 4) for key, value in target_weights.items()},
        current_weights={key: round(value * 100.0, 4) for key, value in current_weights.items()},
        deviation_pp={key: round(value, 4) for key, value in deviation_pp.items()},
        max_deviation_asset=max_asset,
        max_deviation_pp=max_pp,
        equity_total_current_weight=round(equity_current * 100.0, 4)
        if equity_current is not None
        else None,
        equity_total_target_weight=round(equity_target * 100.0, 4)
        if equity_target is not None
        else None,
        equity_total_deviation_pp=equity_deviation_pp,
        cash_reserve_status=cash_reserve_status,
        stale_status=stale_status,
        notes=[
            "cash reserve excluded from target mix",
            "portfolio deviation is not attributed to market factors",
            "reference review only",
        ],
    )


def portfolio_weight_map(
    value: Any,
    default: dict[str, float] | None = None,
) -> dict[str, float]:
    payload = value if isinstance(value, dict) else {}
    result: dict[str, float] = {}
    for key in PORTFOLIO_TARGET_ASSET_CLASSES:
        number = to_float(payload.get(key))
        if number is None and default is not None:
            number = default[key]
        if number is None:
            continue
        result[key] = weight_fraction(number)
    return result


def portfolio_deviation_pp_map(
    payload: dict[str, Any],
    current_weights: dict[str, float],
    target_weights: dict[str, float],
) -> dict[str, float]:
    explicit = payload.get("deviation_pp")
    if isinstance(explicit, dict):
        return {
            key: number
            for key in PORTFOLIO_TARGET_ASSET_CLASSES
            if (number := to_float(explicit.get(key))) is not None
        }
    fractional = payload.get("deviation")
    if isinstance(fractional, dict):
        return {
            key: round(weight_fraction(number) * 100.0, 4)
            for key in PORTFOLIO_TARGET_ASSET_CLASSES
            if (number := to_float(fractional.get(key))) is not None
        }
    return {
        key: round((current_weights[key] - target_weights[key]) * 100.0, 4)
        for key in PORTFOLIO_TARGET_ASSET_CLASSES
        if key in current_weights and key in target_weights
    }


def weight_fraction(value: float) -> float:
    return value / 100.0 if abs(value) > 1.0 else value


def max_deviation_asset(deviation_pp: dict[str, float]) -> str | None:
    if not deviation_pp:
        return None
    return max(deviation_pp, key=lambda key: abs(deviation_pp[key]))


def sum_weights(weights: dict[str, float], keys: tuple[str, ...]) -> float | None:
    if not all(key in weights for key in keys):
        return None
    return sum(weights[key] for key in keys)


def portfolio_holdings_updated_at(data: dict[str, Any]) -> str | None:
    value = data.get("holdings_updated_at")
    if isinstance(value, dict):
        value = value.get("value") or value.get("date") or value.get("updated_at")
    return string_or_none(value)


def portfolio_cash_reserve_status(data: dict[str, Any]) -> str:
    if "cash_reserve_status" in data:
        value = data["cash_reserve_status"]
        if isinstance(value, dict):
            value = value.get("value") or value.get("status")
        text = string_or_none(value)
        if text in {
            "cash_excluded_from_target_allocation",
            "cash_missing",
            "cash_present",
            "unknown",
        }:
            return text
    if any(key in data for key in ("cash", "cash_reserve_value")):
        return "cash_excluded_from_target_allocation"
    return "cash_missing"


def portfolio_stale_status(
    *,
    holdings_updated_at: str | None,
    generated_at: str | None,
    existing_status: str | None,
) -> str:
    holdings_date = parse_date(holdings_updated_at)
    generated_date = parse_date(generated_at)
    if holdings_date is not None and generated_date is not None:
        age_days = max((generated_date - holdings_date).days, 0)
        if age_days <= 14:
            return "fresh"
        if age_days <= 30:
            return "watch"
        return "stale"
    status = (existing_status or "").lower()
    if status in {"fresh", "ok"}:
        return "fresh"
    if status in {"watch", "aging"}:
        return "watch"
    if status in {"stale", "very_stale"}:
        return "stale"
    return "unknown"


def parse_date(value: Any) -> date | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value).strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).date()
    except ValueError:
        pass
    try:
        return date.fromisoformat(text[:10])
    except ValueError:
        return None


def portfolio_compact_metric_status(
    compact: PortfolioDeviationCompact,
    metric_key: str,
) -> str:
    if compact.stale_status == "stale":
        return "stale"
    if compact.stale_status == "unknown":
        return "unknown"
    if metric_key == "holdings_updated_at":
        return "ok" if compact.stale_status in {"fresh", "watch"} else compact.stale_status
    if metric_key == "cash_reserve_status":
        return "ok" if compact.cash_reserve_status != "unknown" else "unknown"
    return portfolio_deviation_status(compact.max_deviation_pp)


def portfolio_compact_module_status(compact: PortfolioDeviationCompact) -> str:
    if compact.stale_status in {"stale", "unknown"}:
        return compact.stale_status
    return portfolio_deviation_status(compact.max_deviation_pp)


def portfolio_deviation_status(value: float | None) -> str:
    if value is None:
        return "unknown"
    abs_value = abs(value)
    if abs_value < 3.0:
        return "ok"
    if abs_value <= 5.0:
        return "watch"
    return "pressure"
