from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from data_quality import market_history_store


DEFAULT_FRESHNESS_STATUS = "historical"
DERIVED_SOURCE_BADGE = "derived"


@dataclass(frozen=True)
class HistoricalDerivedMetric:
    metric_key: str
    value: float | str | bool | None
    value_text: str
    unit: str | None
    status: str
    source: str | None
    source_badge: str
    observation_date: str | None
    generated_at: str | None
    freshness_status: str
    missing_reason: str | None
    interpretation_hint: str | None
    ai_context_allowed: bool
    dependency_keys: list[str]
    window: str | None
    calculation: str
    history_points_used: int
    history_points_required: int


DERIVED_METRIC_SPECS: dict[str, dict[str, Any]] = {
    "dgs10_5d_avg": {
        "module": "rate_pressure",
        "kind": "rolling_average",
        "metric_key": "dgs10",
        "window_observations": 5,
        "unit": "percent",
    },
    "dgs10_10d_avg": {
        "module": "rate_pressure",
        "kind": "rolling_average",
        "metric_key": "dgs10",
        "window_observations": 10,
        "unit": "percent",
    },
    "dgs30_distance_to_5pct": {
        "module": "rate_pressure",
        "kind": "distance_to_threshold",
        "metric_key": "dgs30",
        "threshold": 5.0,
        "unit": "pp",
    },
    "sp500_30d_return": {
        "module": "equity_trend",
        "kind": "period_return",
        "metric_key": "sp500",
        "window_days": 30,
        "unit": "percent",
    },
    "sp500_60d_return": {
        "module": "equity_trend",
        "kind": "period_return",
        "metric_key": "sp500",
        "window_days": 60,
        "unit": "percent",
    },
    "nasdaq100_30d_return": {
        "module": "equity_trend",
        "kind": "period_return",
        "metric_key": "nasdaq100",
        "window_days": 30,
        "unit": "percent",
    },
    "nasdaq100_60d_return": {
        "module": "equity_trend",
        "kind": "period_return",
        "metric_key": "nasdaq100",
        "window_days": 60,
        "unit": "percent",
    },
    "nasdaq_vs_sp500_30d": {
        "module": "equity_trend",
        "kind": "relative_return",
        "numerator_metric_key": "nasdaq100",
        "denominator_metric_key": "sp500",
        "window_days": 30,
        "unit": "pp",
    },
    "wti_30d_change": {
        "module": "inflation_energy_pressure",
        "kind": "period_return",
        "metric_key": "wti",
        "window_days": 30,
        "unit": "percent",
    },
    "brent_30d_change": {
        "module": "inflation_energy_pressure",
        "kind": "period_return",
        "metric_key": "brent",
        "window_days": 30,
        "unit": "percent",
    },
}


def calculate_period_return(
    metric_key: str,
    window_days: int,
    *,
    db_path: Path | str | None = None,
    output_metric_key: str | None = None,
    unit: str | None = "percent",
) -> HistoricalDerivedMetric:
    observations = _numeric_observations(metric_key, db_path=db_path)
    required = 2
    if len(observations) < required:
        return _insufficient_metric(
            metric_key=output_metric_key or f"{metric_key}_{window_days}d_return",
            dependency_keys=[metric_key],
            window=f"{window_days}D",
            calculation="period_return",
            points_used=len(observations),
            points_required=required,
            missing_reason="history_points_insufficient",
        )
    latest = observations[-1]
    target_date = latest["date"] - timedelta(days=window_days)
    start = _latest_on_or_before(observations, target_date)
    if start is None or start["date"] >= latest["date"]:
        return _insufficient_metric(
            metric_key=output_metric_key or f"{metric_key}_{window_days}d_return",
            dependency_keys=[metric_key],
            window=f"{window_days}D",
            calculation="period_return",
            points_used=len(observations),
            points_required=required,
            missing_reason="window_start_observation_missing",
        )
    if start["value"] == 0:
        return _insufficient_metric(
            metric_key=output_metric_key or f"{metric_key}_{window_days}d_return",
            dependency_keys=[metric_key],
            window=f"{window_days}D",
            calculation="period_return",
            points_used=len(observations),
            points_required=required,
            missing_reason="window_start_value_zero",
        )
    value = latest["value"] / start["value"] - 1.0
    return _ok_metric(
        metric_key=output_metric_key or f"{metric_key}_{window_days}d_return",
        value=value,
        unit=unit,
        dependency_keys=[metric_key],
        window=f"{window_days}D",
        calculation="period_return",
        points_used=len(observations),
        points_required=required,
        observation_date=latest["observation_date"],
        generated_at=latest.get("generated_at"),
        interpretation_hint=(
            f"Derived from market history: latest {metric_key} divided by "
            f"the nearest observation on or before {window_days} calendar days earlier, minus 1."
        ),
    )


def calculate_rolling_average(
    metric_key: str,
    window_observations: int,
    *,
    db_path: Path | str | None = None,
    output_metric_key: str | None = None,
    unit: str | None = "percent",
) -> HistoricalDerivedMetric:
    observations = _numeric_observations(metric_key, db_path=db_path)
    if len(observations) < window_observations:
        return _insufficient_metric(
            metric_key=output_metric_key or f"{metric_key}_{window_observations}d_avg",
            dependency_keys=[metric_key],
            window=f"{window_observations} observations",
            calculation="rolling_average",
            points_used=len(observations),
            points_required=window_observations,
            missing_reason="history_points_insufficient",
        )
    window = observations[-window_observations:]
    value = sum(item["value"] for item in window) / window_observations
    latest = window[-1]
    return _ok_metric(
        metric_key=output_metric_key or f"{metric_key}_{window_observations}d_avg",
        value=value,
        unit=unit,
        dependency_keys=[metric_key],
        window=f"{window_observations} observations",
        calculation="rolling_average",
        points_used=window_observations,
        points_required=window_observations,
        observation_date=latest["observation_date"],
        generated_at=latest.get("generated_at"),
        interpretation_hint=(
            f"Derived from market history: arithmetic average of the latest "
            f"{window_observations} {metric_key} observations."
        ),
    )


def calculate_relative_return(
    numerator_metric_key: str,
    denominator_metric_key: str,
    window_days: int,
    *,
    db_path: Path | str | None = None,
    output_metric_key: str | None = None,
    unit: str | None = "pp",
) -> HistoricalDerivedMetric:
    numerator = calculate_period_return(
        numerator_metric_key,
        window_days,
        db_path=db_path,
        output_metric_key=f"{numerator_metric_key}_{window_days}d_return",
    )
    denominator = calculate_period_return(
        denominator_metric_key,
        window_days,
        db_path=db_path,
        output_metric_key=f"{denominator_metric_key}_{window_days}d_return",
    )
    metric_key = output_metric_key or f"{numerator_metric_key}_vs_{denominator_metric_key}_{window_days}d"
    points_used = min(numerator.history_points_used, denominator.history_points_used)
    points_required = max(numerator.history_points_required, denominator.history_points_required)
    if numerator.status != "ok" or denominator.status != "ok":
        missing = []
        if numerator.status != "ok":
            missing.append(f"{numerator_metric_key}:{numerator.missing_reason or numerator.status}")
        if denominator.status != "ok":
            missing.append(f"{denominator_metric_key}:{denominator.missing_reason or denominator.status}")
        return _insufficient_metric(
            metric_key=metric_key,
            dependency_keys=[numerator_metric_key, denominator_metric_key],
            window=f"{window_days}D",
            calculation="relative_return",
            points_used=points_used,
            points_required=points_required,
            missing_reason="; ".join(missing) or "dependency_history_insufficient",
        )
    value = float(numerator.value) - float(denominator.value)
    return _ok_metric(
        metric_key=metric_key,
        value=value,
        unit=unit,
        dependency_keys=[numerator_metric_key, denominator_metric_key],
        window=f"{window_days}D",
        calculation="relative_return",
        points_used=points_used,
        points_required=points_required,
        observation_date=max(
            item for item in [numerator.observation_date, denominator.observation_date] if item
        ),
        generated_at=_utc_now(),
        interpretation_hint=(
            f"Derived from market history: {numerator_metric_key} {window_days}D return "
            f"minus {denominator_metric_key} {window_days}D return."
        ),
    )


def calculate_distance_to_threshold(
    metric_key: str,
    threshold: float,
    *,
    db_path: Path | str | None = None,
    output_metric_key: str | None = None,
    unit: str | None = "pp",
) -> HistoricalDerivedMetric:
    observations = _numeric_observations(metric_key, db_path=db_path)
    if not observations:
        return _insufficient_metric(
            metric_key=output_metric_key or f"{metric_key}_distance_to_threshold",
            dependency_keys=[metric_key],
            window=None,
            calculation="distance_to_threshold",
            points_used=0,
            points_required=1,
            missing_reason="latest_observation_missing",
        )
    latest = observations[-1]
    value = latest["value"] - float(threshold)
    return _ok_metric(
        metric_key=output_metric_key or f"{metric_key}_distance_to_threshold",
        value=value,
        unit=unit,
        dependency_keys=[metric_key],
        window=None,
        calculation="distance_to_threshold",
        points_used=1,
        points_required=1,
        observation_date=latest["observation_date"],
        generated_at=latest.get("generated_at"),
        interpretation_hint=(
            f"Derived from market history: latest {metric_key} minus threshold {threshold}."
        ),
    )


def build_historical_dashboard_candidates(
    *,
    db_path: Path | str | None = None,
) -> dict[str, list[HistoricalDerivedMetric]]:
    candidates: dict[str, list[HistoricalDerivedMetric]] = {}
    for output_key, spec in DERIVED_METRIC_SPECS.items():
        module = spec["module"]
        item = _calculate_spec(output_key, spec, db_path=db_path)
        candidates.setdefault(module, []).append(item)
    return candidates


def flatten_historical_dashboard_candidates(
    *,
    db_path: Path | str | None = None,
) -> list[HistoricalDerivedMetric]:
    return [
        item
        for items in build_historical_dashboard_candidates(db_path=db_path).values()
        for item in items
    ]


def metric_to_dict(metric: HistoricalDerivedMetric) -> dict[str, Any]:
    return {
        "metric_key": metric.metric_key,
        "value": metric.value,
        "value_text": metric.value_text,
        "unit": metric.unit,
        "status": metric.status,
        "source": metric.source,
        "source_badge": metric.source_badge,
        "observation_date": metric.observation_date,
        "generated_at": metric.generated_at,
        "freshness_status": metric.freshness_status,
        "missing_reason": metric.missing_reason,
        "interpretation_hint": metric.interpretation_hint,
        "ai_context_allowed": metric.ai_context_allowed,
        "dependency_keys": metric.dependency_keys,
        "window": metric.window,
        "calculation": metric.calculation,
        "history_points_used": metric.history_points_used,
        "history_points_required": metric.history_points_required,
    }


def _calculate_spec(
    output_key: str,
    spec: dict[str, Any],
    *,
    db_path: Path | str | None,
) -> HistoricalDerivedMetric:
    kind = spec["kind"]
    if kind == "rolling_average":
        return calculate_rolling_average(
            spec["metric_key"],
            spec["window_observations"],
            db_path=db_path,
            output_metric_key=output_key,
            unit=spec.get("unit"),
        )
    if kind == "period_return":
        return calculate_period_return(
            spec["metric_key"],
            spec["window_days"],
            db_path=db_path,
            output_metric_key=output_key,
            unit=spec.get("unit"),
        )
    if kind == "relative_return":
        return calculate_relative_return(
            spec["numerator_metric_key"],
            spec["denominator_metric_key"],
            spec["window_days"],
            db_path=db_path,
            output_metric_key=output_key,
            unit=spec.get("unit"),
        )
    if kind == "distance_to_threshold":
        return calculate_distance_to_threshold(
            spec["metric_key"],
            spec["threshold"],
            db_path=db_path,
            output_metric_key=output_key,
            unit=spec.get("unit"),
        )
    raise ValueError(f"unsupported historical derived metric kind: {kind}")


def _numeric_observations(
    metric_key: str,
    *,
    db_path: Path | str | None = None,
) -> list[dict[str, Any]]:
    observations = market_history_store.list_market_observations(
        metric_key=metric_key,
        limit=500,
        db_path=db_path,
    )
    results: list[dict[str, Any]] = []
    for observation in observations:
        value = observation.get("value_numeric")
        parsed_date = _parse_date(observation.get("observation_date"))
        if value is None or parsed_date is None:
            continue
        results.append(
            {
                "value": float(value),
                "date": parsed_date,
                "observation_date": observation.get("observation_date"),
                "generated_at": observation.get("generated_at"),
            }
        )
    return sorted(results, key=lambda item: item["date"])


def _latest_on_or_before(
    observations: list[dict[str, Any]],
    target_date: date,
) -> dict[str, Any] | None:
    candidates = [item for item in observations if item["date"] <= target_date]
    return candidates[-1] if candidates else None


def _ok_metric(
    *,
    metric_key: str,
    value: float,
    unit: str | None,
    dependency_keys: list[str],
    window: str | None,
    calculation: str,
    points_used: int,
    points_required: int,
    observation_date: str | None,
    generated_at: str | None,
    interpretation_hint: str,
) -> HistoricalDerivedMetric:
    return HistoricalDerivedMetric(
        metric_key=metric_key,
        value=value,
        value_text=_format_value(value, unit),
        unit=unit,
        status="ok",
        source="market_history",
        source_badge=DERIVED_SOURCE_BADGE,
        observation_date=observation_date,
        generated_at=generated_at or _utc_now(),
        freshness_status=DEFAULT_FRESHNESS_STATUS,
        missing_reason=None,
        interpretation_hint=interpretation_hint,
        ai_context_allowed=True,
        dependency_keys=dependency_keys,
        window=window,
        calculation=calculation,
        history_points_used=points_used,
        history_points_required=points_required,
    )


def _insufficient_metric(
    *,
    metric_key: str,
    dependency_keys: list[str],
    window: str | None,
    calculation: str,
    points_used: int,
    points_required: int,
    missing_reason: str,
) -> HistoricalDerivedMetric:
    return HistoricalDerivedMetric(
        metric_key=metric_key,
        value=None,
        value_text="insufficient history",
        unit=None,
        status="insufficient_history",
        source="market_history",
        source_badge=DERIVED_SOURCE_BADGE,
        observation_date=None,
        generated_at=_utc_now(),
        freshness_status="insufficient_history",
        missing_reason=missing_reason,
        interpretation_hint=(
            f"Historical derived metric requires {calculation} from dependencies "
            f"{', '.join(dependency_keys)}; history window is not sufficient."
        ),
        ai_context_allowed=False,
        dependency_keys=dependency_keys,
        window=window,
        calculation=calculation,
        history_points_used=points_used,
        history_points_required=points_required,
    )


def _format_value(value: float, unit: str | None) -> str:
    if unit == "percent":
        return f"{value * 100:.2f}%"
    if unit == "pp":
        return f"{value:.2f}pp"
    return f"{value:.4g}"


def _parse_date(value: Any) -> date | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        return date.fromisoformat(value[:10])
    except ValueError:
        return None


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()
