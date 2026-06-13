from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, timezone
from statistics import mean, pstdev
from typing import Any

from data_quality import market_history_store


INTERPRETATION_BOUNDARY = (
    "Historical percentile is relative to available local history, not a forecast. "
    "Z-score is a normalization statistic, not crash probability. Short history "
    "can make percentile unstable. Different frequencies must not be mixed. "
    "Percentile does not produce buy/sell instructions."
)

LOOKBACK_WINDOW = "all_available"
ROBUST_ZSCORE_STATUS = "research_needed"


@dataclass(frozen=True)
class PercentileMetricSpec:
    metric_key: str
    source_metric_key: str
    display_name: str
    kind: str
    percentile_direction: str
    minimum_observation_count: int
    unit: str | None = None


PERCENTILE_METRIC_SPECS: tuple[PercentileMetricSpec, ...] = (
    PercentileMetricSpec("high_yield_spread_percentile", "high_yield_spread", "High-yield spread percentile", "percentile", "higher_is_more_stress", 60, "percentile"),
    PercentileMetricSpec("high_yield_spread_zscore", "high_yield_spread", "High-yield spread z-score", "zscore", "higher_is_more_stress", 60, "zscore"),
    PercentileMetricSpec("investment_grade_spread_percentile", "investment_grade_spread", "Investment-grade spread percentile", "percentile", "higher_is_more_stress", 60, "percentile"),
    PercentileMetricSpec("investment_grade_spread_zscore", "investment_grade_spread", "Investment-grade spread z-score", "zscore", "higher_is_more_stress", 60, "zscore"),
    PercentileMetricSpec("vix_percentile", "vix", "VIX percentile", "percentile", "higher_is_more_stress", 60, "percentile"),
    PercentileMetricSpec("vix_zscore", "vix", "VIX z-score", "zscore", "higher_is_more_stress", 60, "zscore"),
    PercentileMetricSpec("dgs30_percentile", "dgs30", "30Y Treasury yield percentile", "percentile", "higher_is_more_stress", 60, "percentile"),
    PercentileMetricSpec("dgs30_zscore", "dgs30", "30Y Treasury yield z-score", "zscore", "higher_is_more_stress", 60, "zscore"),
    PercentileMetricSpec("dfii10_percentile", "dfii10", "10Y real yield percentile", "percentile", "higher_is_more_stress", 60, "percentile"),
    PercentileMetricSpec("dfii10_zscore", "dfii10", "10Y real yield z-score", "zscore", "higher_is_more_stress", 60, "zscore"),
    PercentileMetricSpec("sp500_drawdown_3m_percentile", "sp500_drawdown_3m", "S&P 500 3M drawdown stress percentile", "percentile", "lower_is_more_stress", 60, "percentile"),
    PercentileMetricSpec("nasdaq100_drawdown_3m_percentile", "nasdaq100_drawdown_3m", "Nasdaq 100 3M drawdown stress percentile", "percentile", "lower_is_more_stress", 60, "percentile"),
    PercentileMetricSpec("initial_claims_4w_avg_percentile", "initial_claims_4w_avg", "Initial claims 4W average percentile", "percentile", "higher_is_more_stress", 26, "percentile"),
    PercentileMetricSpec("continuing_claims_4w_avg_percentile", "continuing_claims_4w_avg", "Continuing claims 4W average percentile", "percentile", "higher_is_more_stress", 26, "percentile"),
)


def build_historical_percentile_rows(
    *,
    db_path: str | None = None,
) -> list[dict[str, Any]]:
    return [build_metric_payload(spec, db_path=db_path) for spec in PERCENTILE_METRIC_SPECS]


def build_metric_payload(
    spec: PercentileMetricSpec,
    *,
    db_path: str | None = None,
) -> dict[str, Any]:
    generated_at = datetime.now(timezone.utc).isoformat()
    latest_any = _latest_numeric_observation(spec.source_metric_key, db_path=db_path)
    if latest_any is not None and (
        latest_any.get("status") == "stale" or latest_any.get("freshness_status") == "stale"
    ):
        return _blocked_payload(
            spec,
            "stale",
            "latest_input_stale",
            0,
            generated_at,
            latest=latest_any,
        )
    observations = _usable_observations(spec.source_metric_key, db_path=db_path)
    if not observations:
        return _blocked_payload(spec, "missing", "latest_input_missing", 0, generated_at)
    latest = observations[-1]
    count = len(observations)
    if count < spec.minimum_observation_count:
        return _blocked_payload(
            spec,
            "insufficient_history",
            "insufficient_history_for_percentile",
            count,
            generated_at,
            latest=latest,
        )
    values = [item["value"] for item in observations]
    current = latest["value"]
    percentile = _empirical_percentile(current, values)
    zscore = _zscore(current, values)
    if spec.kind == "percentile":
        value = round(percentile, 2)
        value_text = f"{value:.2f} percentile"
        status = _status_for_percentile(percentile, spec.percentile_direction)
    else:
        if zscore is None:
            return _blocked_payload(
                spec,
                "insufficient_history",
                "insufficient_history_for_percentile",
                count,
                generated_at,
                latest=latest,
            )
        value = round(zscore, 4)
        value_text = f"{value:+.2f} z"
        status = _status_for_percentile(percentile, spec.percentile_direction)
    return {
        "metric_key": spec.metric_key,
        "display_name": spec.display_name,
        "value": value,
        "value_text": value_text,
        "unit": spec.unit,
        "status": status,
        "source": "local_market_history",
        "source_badge": "derived",
        "source_series": latest.get("source_series"),
        "observation_date": latest.get("observation_date"),
        "generated_at": generated_at,
        "freshness_status": latest.get("freshness_status") or "historical",
        "missing_reason": None,
        "interpretation_hint": (
            f"Derived from local market history using {LOOKBACK_WINDOW} "
            f"observations for {spec.source_metric_key}; percentile_direction="
            f"{spec.percentile_direction}; robust_zscore_status={ROBUST_ZSCORE_STATUS}."
        ),
        "ai_context_allowed": True,
        "input_evidence": [_input_snapshot(latest)],
        "lookback_window": LOOKBACK_WINDOW,
        "observation_count": count,
        "percentile_direction": spec.percentile_direction,
        "component_contributions": {
            "lookback_window": LOOKBACK_WINDOW,
            "observation_count": count,
            "minimum_observation_count": spec.minimum_observation_count,
            "percentile_direction": spec.percentile_direction,
            "robust_zscore_status": ROBUST_ZSCORE_STATUS,
            "history_mean": round(mean(values), 6),
            "history_std": round(pstdev(values), 6),
        },
        "missing_inputs": [],
        "interpretation_boundary": INTERPRETATION_BOUNDARY,
    }


def _blocked_payload(
    spec: PercentileMetricSpec,
    status: str,
    missing_reason: str,
    observation_count: int,
    generated_at: str,
    *,
    latest: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "metric_key": spec.metric_key,
        "display_name": spec.display_name,
        "value": None,
        "value_text": _missing_value_text(status),
        "unit": spec.unit,
        "status": status,
        "source": "local_market_history",
        "source_badge": "derived" if latest is not None else "missing",
        "source_series": latest.get("source_series") if latest else None,
        "observation_date": latest.get("observation_date") if latest else None,
        "generated_at": generated_at,
        "freshness_status": latest.get("freshness_status") if latest else "missing",
        "missing_reason": missing_reason,
        "interpretation_hint": (
            f"Historical percentile requires at least {spec.minimum_observation_count} "
            f"same-frequency local market history observations for {spec.source_metric_key}."
        ),
        "ai_context_allowed": False,
        "input_evidence": [_input_snapshot(latest)] if latest else [],
        "lookback_window": LOOKBACK_WINDOW,
        "observation_count": observation_count,
        "percentile_direction": spec.percentile_direction,
        "component_contributions": {
            "lookback_window": LOOKBACK_WINDOW,
            "observation_count": observation_count,
            "minimum_observation_count": spec.minimum_observation_count,
            "percentile_direction": spec.percentile_direction,
            "robust_zscore_status": ROBUST_ZSCORE_STATUS,
        },
        "missing_inputs": [spec.source_metric_key],
        "interpretation_boundary": INTERPRETATION_BOUNDARY,
    }


def _usable_observations(metric_key: str, *, db_path: str | None) -> list[dict[str, Any]]:
    rows = market_history_store.list_market_observations(
        metric_key=metric_key,
        limit=market_history_store.MAX_LIMIT,
        db_path=db_path,
    )
    observations: list[dict[str, Any]] = []
    for row in reversed(rows):
        value = _to_float(row.get("value_numeric"))
        if value is None:
            continue
        if row.get("status") in market_history_store.BLOCKED_STATUSES:
            continue
        if row.get("source_badge") in market_history_store.BLOCKED_SOURCE_BADGES:
            continue
        observations.append({**row, "value": value})
    return observations


def _latest_numeric_observation(metric_key: str, *, db_path: str | None) -> dict[str, Any] | None:
    rows = market_history_store.list_market_observations(
        metric_key=metric_key,
        limit=market_history_store.MAX_LIMIT,
        db_path=db_path,
    )
    for row in rows:
        value = _to_float(row.get("value_numeric"))
        if value is None:
            continue
        return {**row, "value": value}
    return None


def _empirical_percentile(current: float, values: list[float]) -> float:
    less = sum(1 for value in values if value < current)
    equal = sum(1 for value in values if value == current)
    return ((less + 0.5 * equal) / len(values)) * 100.0


def _zscore(current: float, values: list[float]) -> float | None:
    std = pstdev(values)
    if math.isclose(std, 0.0):
        return None
    return (current - mean(values)) / std


def _status_for_percentile(percentile: float, direction: str) -> str:
    if direction == "lower_is_more_stress":
        if percentile <= 5.0:
            return "stress"
        if percentile <= 15.0:
            return "pressure"
        if percentile <= 30.0:
            return "watch"
        return "ok"
    if percentile >= 95.0:
        return "stress"
    if percentile >= 85.0:
        return "pressure"
    if percentile >= 70.0:
        return "watch"
    return "ok"


def _input_snapshot(row: dict[str, Any] | None) -> dict[str, Any]:
    if row is None:
        return {}
    return {
        "metric_key": row.get("metric_key"),
        "value": row.get("value"),
        "value_text": row.get("value_text"),
        "status": row.get("status"),
        "source": row.get("source"),
        "source_badge": row.get("source_badge"),
        "source_series": row.get("source_series"),
        "observation_date": row.get("observation_date"),
        "generated_at": row.get("generated_at"),
        "freshness_status": row.get("freshness_status"),
    }


def _missing_value_text(status: str) -> str:
    if status == "insufficient_history":
        return "insufficient history"
    if status == "stale":
        return "stale"
    return "missing"


def _to_float(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return float(str(value).strip())
    except (TypeError, ValueError):
        return None
