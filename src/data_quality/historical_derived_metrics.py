from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from data_quality import market_history_store


DEFAULT_FRESHNESS_STATUS = "historical"
DERIVED_SOURCE_BADGE = "derived"
PROXY_BREADTH_MODULE = "breadth_concentration_proxy"
MARKET_STRESS_DERIVED_MODULE = "market_stress_derived"
PROXY_BREADTH_HINT_SUFFIX = (
    " Derived from local market history; underlying source includes yfinance ETF "
    "proxy observations. This is not official market breadth, not valuation data, "
    "and not a crash confirmation signal."
)
EQUITY_DRAWDOWN_HINT_SUFFIX = (
    " Drawdown is derived from local market history as a market outcome, not a "
    "cause, model score, or trading signal."
)
CURVE_SLOPE_HINT_SUFFIX = (
    " Curve slope is derived from local Treasury yield history as macro context; "
    "it is not a trading signal."
)
CROSS_ASSET_PROXY_HINT_SUFFIX = (
    " Derived from local market history; TLT/GLD/SHY are yfinance ETF proxy "
    "observations, not official asset-class data or trading advice."
)


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
    dependency_source_badges: list[str] | None = None
    dependency_source_series: list[str] | None = None
    dependency_sources: list[str] | None = None
    dependency_observation_dates: list[str] | None = None
    dependency_generated_ats: list[str] | None = None
    dependency_freshness_statuses: list[str] | None = None


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
    "ppi_final_demand_yoy": {
        "module": "inflation_energy_pressure",
        "kind": "observation_yoy",
        "metric_key": "ppi_final_demand",
        "window_observations": 13,
        "unit": "percent",
        "interpretation_hint_suffix": (
            " PPIFIS is the FRED official relay for headline PPI Final Demand; "
            "it is distinct from PPIACO, monthly/low-frequency, and not consensus surprise data."
        ),
    },
    "spy_proxy_30d_return": {
        "module": PROXY_BREADTH_MODULE,
        "kind": "period_return",
        "metric_key": "spy_proxy",
        "window_days": 30,
        "unit": "percent",
        "interpretation_hint_suffix": PROXY_BREADTH_HINT_SUFFIX,
    },
    "spy_proxy_60d_return": {
        "module": PROXY_BREADTH_MODULE,
        "kind": "period_return",
        "metric_key": "spy_proxy",
        "window_days": 60,
        "unit": "percent",
        "interpretation_hint_suffix": PROXY_BREADTH_HINT_SUFFIX,
    },
    "rsp_proxy_30d_return": {
        "module": PROXY_BREADTH_MODULE,
        "kind": "period_return",
        "metric_key": "rsp_proxy",
        "window_days": 30,
        "unit": "percent",
        "interpretation_hint_suffix": PROXY_BREADTH_HINT_SUFFIX,
    },
    "rsp_proxy_60d_return": {
        "module": PROXY_BREADTH_MODULE,
        "kind": "period_return",
        "metric_key": "rsp_proxy",
        "window_days": 60,
        "unit": "percent",
        "interpretation_hint_suffix": PROXY_BREADTH_HINT_SUFFIX,
    },
    "qqq_proxy_30d_return": {
        "module": PROXY_BREADTH_MODULE,
        "kind": "period_return",
        "metric_key": "qqq_proxy",
        "window_days": 30,
        "unit": "percent",
        "interpretation_hint_suffix": PROXY_BREADTH_HINT_SUFFIX,
    },
    "qqq_proxy_60d_return": {
        "module": PROXY_BREADTH_MODULE,
        "kind": "period_return",
        "metric_key": "qqq_proxy",
        "window_days": 60,
        "unit": "percent",
        "interpretation_hint_suffix": PROXY_BREADTH_HINT_SUFFIX,
    },
    "spy_vs_rsp_30d": {
        "module": PROXY_BREADTH_MODULE,
        "kind": "relative_return",
        "numerator_metric_key": "spy_proxy",
        "denominator_metric_key": "rsp_proxy",
        "window_days": 30,
        "unit": "pp",
        "interpretation_hint_suffix": PROXY_BREADTH_HINT_SUFFIX,
    },
    "spy_vs_rsp_60d": {
        "module": PROXY_BREADTH_MODULE,
        "kind": "relative_return",
        "numerator_metric_key": "spy_proxy",
        "denominator_metric_key": "rsp_proxy",
        "window_days": 60,
        "unit": "pp",
        "interpretation_hint_suffix": PROXY_BREADTH_HINT_SUFFIX,
    },
    "qqq_vs_spy_30d": {
        "module": PROXY_BREADTH_MODULE,
        "kind": "relative_return",
        "numerator_metric_key": "qqq_proxy",
        "denominator_metric_key": "spy_proxy",
        "window_days": 30,
        "unit": "pp",
        "interpretation_hint_suffix": PROXY_BREADTH_HINT_SUFFIX,
    },
    "qqq_vs_spy_60d": {
        "module": PROXY_BREADTH_MODULE,
        "kind": "relative_return",
        "numerator_metric_key": "qqq_proxy",
        "denominator_metric_key": "spy_proxy",
        "window_days": 60,
        "unit": "pp",
        "interpretation_hint_suffix": PROXY_BREADTH_HINT_SUFFIX,
    },
    "hyg_vs_lqd_30d": {
        "module": PROXY_BREADTH_MODULE,
        "kind": "relative_return",
        "numerator_metric_key": "hyg_proxy",
        "denominator_metric_key": "lqd_proxy",
        "window_days": 30,
        "unit": "pp",
        "interpretation_hint_suffix": PROXY_BREADTH_HINT_SUFFIX,
    },
    "hyg_vs_lqd_60d": {
        "module": PROXY_BREADTH_MODULE,
        "kind": "relative_return",
        "numerator_metric_key": "hyg_proxy",
        "denominator_metric_key": "lqd_proxy",
        "window_days": 60,
        "unit": "pp",
        "interpretation_hint_suffix": PROXY_BREADTH_HINT_SUFFIX,
    },
    "sp500_drawdown_3m": {
        "module": MARKET_STRESS_DERIVED_MODULE,
        "kind": "drawdown",
        "metric_key": "sp500",
        "window_days": 90,
        "unit": "percent",
        "interpretation_hint_suffix": EQUITY_DRAWDOWN_HINT_SUFFIX,
    },
    "sp500_drawdown_6m": {
        "module": MARKET_STRESS_DERIVED_MODULE,
        "kind": "drawdown",
        "metric_key": "sp500",
        "window_days": 180,
        "unit": "percent",
        "interpretation_hint_suffix": EQUITY_DRAWDOWN_HINT_SUFFIX,
    },
    "nasdaq100_drawdown_3m": {
        "module": MARKET_STRESS_DERIVED_MODULE,
        "kind": "drawdown",
        "metric_key": "nasdaq100",
        "window_days": 90,
        "unit": "percent",
        "interpretation_hint_suffix": EQUITY_DRAWDOWN_HINT_SUFFIX,
    },
    "nasdaq100_drawdown_6m": {
        "module": MARKET_STRESS_DERIVED_MODULE,
        "kind": "drawdown",
        "metric_key": "nasdaq100",
        "window_days": 180,
        "unit": "percent",
        "interpretation_hint_suffix": EQUITY_DRAWDOWN_HINT_SUFFIX,
    },
    "dgs10_dgs2_curve_slope": {
        "module": MARKET_STRESS_DERIVED_MODULE,
        "kind": "latest_spread",
        "numerator_metric_key": "dgs10",
        "denominator_metric_key": "dgs2",
        "unit": "raw_pp",
        "interpretation_hint_suffix": CURVE_SLOPE_HINT_SUFFIX,
    },
    "dgs30_dgs10_curve_slope": {
        "module": MARKET_STRESS_DERIVED_MODULE,
        "kind": "latest_spread",
        "numerator_metric_key": "dgs30",
        "denominator_metric_key": "dgs10",
        "unit": "raw_pp",
        "interpretation_hint_suffix": CURVE_SLOPE_HINT_SUFFIX,
    },
    "tlt_proxy_30d_return": {
        "module": MARKET_STRESS_DERIVED_MODULE,
        "kind": "period_return",
        "metric_key": "tlt_proxy",
        "window_days": 30,
        "unit": "percent",
        "interpretation_hint_suffix": CROSS_ASSET_PROXY_HINT_SUFFIX,
    },
    "gld_proxy_30d_return": {
        "module": MARKET_STRESS_DERIVED_MODULE,
        "kind": "period_return",
        "metric_key": "gld_proxy",
        "window_days": 30,
        "unit": "percent",
        "interpretation_hint_suffix": CROSS_ASSET_PROXY_HINT_SUFFIX,
    },
    "shy_proxy_30d_return": {
        "module": MARKET_STRESS_DERIVED_MODULE,
        "kind": "period_return",
        "metric_key": "shy_proxy",
        "window_days": 30,
        "unit": "percent",
        "interpretation_hint_suffix": CROSS_ASSET_PROXY_HINT_SUFFIX,
    },
    "tlt_vs_shy_30d": {
        "module": MARKET_STRESS_DERIVED_MODULE,
        "kind": "relative_return",
        "numerator_metric_key": "tlt_proxy",
        "denominator_metric_key": "shy_proxy",
        "window_days": 30,
        "unit": "pp",
        "interpretation_hint_suffix": (
            f"{CROSS_ASSET_PROXY_HINT_SUFFIX} This is a relative return proxy, "
            "not an official bond-risk indicator."
        ),
    },
}


def calculate_period_return(
    metric_key: str,
    window_days: int,
    *,
    db_path: Path | str | None = None,
    output_metric_key: str | None = None,
    unit: str | None = "percent",
    interpretation_hint_suffix: str | None = None,
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
    dependency_observations = [start, latest]
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
            f"{interpretation_hint_suffix or ''}"
        ),
        dependency_observations=dependency_observations,
    )


def calculate_rolling_average(
    metric_key: str,
    window_observations: int,
    *,
    db_path: Path | str | None = None,
    output_metric_key: str | None = None,
    unit: str | None = "percent",
) -> HistoricalDerivedMetric:
    if metric_key == "ppi_final_demand" and not interpretation_hint_suffix:
        interpretation_hint_suffix = (
            " PPIFIS is the FRED official relay for headline PPI Final Demand; "
            "it is distinct from PPIACO, monthly/low-frequency, and not consensus surprise data."
        )
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
        dependency_observations=window,
    )


def calculate_relative_return(
    numerator_metric_key: str,
    denominator_metric_key: str,
    window_days: int,
    *,
    db_path: Path | str | None = None,
    output_metric_key: str | None = None,
    unit: str | None = "pp",
    interpretation_hint_suffix: str | None = None,
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
            f"{interpretation_hint_suffix or ''}"
        ),
        dependency_source_badges=sorted(
            set((numerator.dependency_source_badges or []) + (denominator.dependency_source_badges or []))
        ),
        dependency_source_series=sorted(
            set((numerator.dependency_source_series or []) + (denominator.dependency_source_series or []))
        ),
        dependency_sources=sorted(
            set((numerator.dependency_sources or []) + (denominator.dependency_sources or []))
        ),
        ai_context_allowed=numerator.ai_context_allowed and denominator.ai_context_allowed,
    )


def calculate_drawdown(
    metric_key: str,
    window_days: int,
    *,
    db_path: Path | str | None = None,
    output_metric_key: str | None = None,
    unit: str | None = "percent",
    interpretation_hint_suffix: str | None = None,
) -> HistoricalDerivedMetric:
    if interpretation_hint_suffix is None:
        interpretation_hint_suffix = EQUITY_DRAWDOWN_HINT_SUFFIX
    observations = _numeric_observations(metric_key, db_path=db_path)
    required = 2
    if len(observations) < required:
        return _insufficient_metric(
            metric_key=output_metric_key or f"{metric_key}_drawdown_{window_days}d",
            dependency_keys=[metric_key],
            window=f"{window_days}D",
            calculation="drawdown",
            points_used=len(observations),
            points_required=required,
            missing_reason="history_points_insufficient",
        )
    latest = observations[-1]
    target_date = latest["date"] - timedelta(days=window_days)
    start = _latest_on_or_before(observations, target_date)
    if start is None or start["date"] >= latest["date"]:
        return _insufficient_metric(
            metric_key=output_metric_key or f"{metric_key}_drawdown_{window_days}d",
            dependency_keys=[metric_key],
            window=f"{window_days}D",
            calculation="drawdown",
            points_used=len(observations),
            points_required=required,
            missing_reason="window_start_observation_missing",
        )
    window = [item for item in observations if item["date"] >= start["date"]]
    peak = max(item["value"] for item in window)
    if peak == 0:
        return _insufficient_metric(
            metric_key=output_metric_key or f"{metric_key}_drawdown_{window_days}d",
            dependency_keys=[metric_key],
            window=f"{window_days}D",
            calculation="drawdown",
            points_used=len(observations),
            points_required=required,
            missing_reason="window_peak_value_zero",
        )
    value = latest["value"] / peak - 1.0
    peak_observation = max(window, key=lambda item: item["value"])
    return _ok_metric(
        metric_key=output_metric_key or f"{metric_key}_drawdown_{window_days}d",
        value=value,
        unit=unit,
        dependency_keys=[metric_key],
        window=f"{window_days}D",
        calculation="latest_value / lookback_peak_value - 1",
        points_used=len(window),
        points_required=required,
        observation_date=latest["observation_date"],
        generated_at=latest.get("generated_at"),
        interpretation_hint=(
            f"Derived from market history: latest {metric_key} divided by the "
            f"highest {metric_key} observation in the {window_days}D lookback, minus 1."
            f"{interpretation_hint_suffix or ''}"
        ),
        dependency_observations=[peak_observation, latest],
    )


def calculate_latest_spread(
    numerator_metric_key: str,
    denominator_metric_key: str,
    *,
    db_path: Path | str | None = None,
    fallback_observations: dict[str, dict[str, Any]] | None = None,
    output_metric_key: str | None = None,
    unit: str | None = "raw_pp",
    interpretation_hint_suffix: str | None = None,
) -> HistoricalDerivedMetric:
    if interpretation_hint_suffix is None:
        interpretation_hint_suffix = CURVE_SLOPE_HINT_SUFFIX
    fallback_observations = fallback_observations or {}
    numerator = _latest_usable_spread_observation(numerator_metric_key, db_path=db_path) or _fallback_observation(
        numerator_metric_key,
        fallback_observations,
    )
    denominator = _latest_usable_spread_observation(denominator_metric_key, db_path=db_path) or _fallback_observation(
        denominator_metric_key,
        fallback_observations,
    )
    metric_key = output_metric_key or f"{numerator_metric_key}_{denominator_metric_key}_spread"
    missing = []
    if numerator is None:
        missing.append(f"{numerator_metric_key}:latest_observation_missing")
    if denominator is None:
        missing.append(f"{denominator_metric_key}:latest_observation_missing")
    if missing:
        return _insufficient_metric(
            metric_key=metric_key,
            dependency_keys=[numerator_metric_key, denominator_metric_key],
            window="latest",
            calculation="latest_spread",
            points_used=sum(1 for item in (numerator, denominator) if item is not None),
            points_required=2,
            missing_reason="; ".join(missing),
        )
    assert numerator is not None and denominator is not None
    value = numerator["value"] - denominator["value"]
    dependency_observations = [numerator, denominator]
    source_text = "market history"
    if any(item.get("observation_source") == "compact_dashboard" for item in dependency_observations):
        source_text = "market history with compact/dashboard official DGS fallback"
    return _ok_metric(
        metric_key=metric_key,
        value=value,
        unit=unit,
        dependency_keys=[numerator_metric_key, denominator_metric_key],
        window="latest",
        calculation=f"latest {numerator_metric_key} - latest {denominator_metric_key}",
        points_used=2,
        points_required=2,
        observation_date=max(
            item for item in [numerator["observation_date"], denominator["observation_date"]] if item
        ),
        generated_at=max(
            item for item in [numerator.get("generated_at"), denominator.get("generated_at")] if item
        ),
        interpretation_hint=(
            f"Derived from {source_text}: latest {numerator_metric_key} minus "
            f"latest {denominator_metric_key}."
            f"{interpretation_hint_suffix or ''}"
        ),
        dependency_observations=dependency_observations,
    )


def calculate_observation_yoy(
    metric_key: str,
    window_observations: int,
    *,
    db_path: Path | str | None = None,
    output_metric_key: str | None = None,
    unit: str | None = "percent",
    interpretation_hint_suffix: str | None = None,
) -> HistoricalDerivedMetric:
    if metric_key == "ppi_final_demand" and not interpretation_hint_suffix:
        interpretation_hint_suffix = (
            " PPIFIS is the FRED official relay for headline PPI Final Demand; "
            "it is distinct from PPIACO, monthly/low-frequency, and not consensus surprise data."
        )
    observations = _numeric_observations(metric_key, db_path=db_path)
    if len(observations) < window_observations:
        return _insufficient_metric(
            metric_key=output_metric_key or f"{metric_key}_yoy",
            dependency_keys=[metric_key],
            window=f"{window_observations} monthly observations",
            calculation="observation_yoy",
            points_used=len(observations),
            points_required=window_observations,
            missing_reason="history_points_insufficient",
        )
    latest = observations[-1]
    prior = observations[-window_observations]
    if prior["value"] == 0:
        return _insufficient_metric(
            metric_key=output_metric_key or f"{metric_key}_yoy",
            dependency_keys=[metric_key],
            window=f"{window_observations} monthly observations",
            calculation="observation_yoy",
            points_used=len(observations),
            points_required=window_observations,
            missing_reason="prior_year_value_zero",
        )
    value = latest["value"] / prior["value"] - 1.0
    return _ok_metric(
        metric_key=output_metric_key or f"{metric_key}_yoy",
        value=value,
        unit=unit,
        dependency_keys=[metric_key],
        window="12M",
        calculation="(latest_index / same_month_prior_year_index) - 1",
        points_used=len(observations),
        points_required=window_observations,
        observation_date=latest["observation_date"],
        generated_at=latest.get("generated_at"),
        interpretation_hint=(
            f"Derived from market history: latest {metric_key} index divided by "
            f"the observation 12 monthly observations earlier, minus 1."
            f"{interpretation_hint_suffix or ''}"
        ),
        dependency_observations=[prior, latest],
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
        dependency_observations=[latest],
    )


def build_historical_dashboard_candidates(
    *,
    db_path: Path | str | None = None,
    fallback_observations: dict[str, dict[str, Any]] | None = None,
) -> dict[str, list[HistoricalDerivedMetric]]:
    candidates: dict[str, list[HistoricalDerivedMetric]] = {}
    for output_key, spec in DERIVED_METRIC_SPECS.items():
        module = spec["module"]
        item = _calculate_spec(
            output_key,
            spec,
            db_path=db_path,
            fallback_observations=fallback_observations,
        )
        candidates.setdefault(module, []).append(item)
    return candidates


def flatten_historical_dashboard_candidates(
    *,
    db_path: Path | str | None = None,
    fallback_observations: dict[str, dict[str, Any]] | None = None,
) -> list[HistoricalDerivedMetric]:
    return [
        item
        for items in build_historical_dashboard_candidates(
            db_path=db_path,
            fallback_observations=fallback_observations,
        ).values()
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
        "dependency_source_badges": metric.dependency_source_badges,
        "dependency_source_series": metric.dependency_source_series,
        "dependency_sources": metric.dependency_sources,
        "dependency_observation_dates": metric.dependency_observation_dates,
        "dependency_generated_ats": metric.dependency_generated_ats,
        "dependency_freshness_statuses": metric.dependency_freshness_statuses,
    }


def _calculate_spec(
    output_key: str,
    spec: dict[str, Any],
    *,
    db_path: Path | str | None,
    fallback_observations: dict[str, dict[str, Any]] | None,
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
            interpretation_hint_suffix=spec.get("interpretation_hint_suffix"),
        )
    if kind == "relative_return":
        return calculate_relative_return(
            spec["numerator_metric_key"],
            spec["denominator_metric_key"],
            spec["window_days"],
            db_path=db_path,
            output_metric_key=output_key,
            unit=spec.get("unit"),
            interpretation_hint_suffix=spec.get("interpretation_hint_suffix"),
        )
    if kind == "drawdown":
        return calculate_drawdown(
            spec["metric_key"],
            spec["window_days"],
            db_path=db_path,
            output_metric_key=output_key,
            unit=spec.get("unit"),
            interpretation_hint_suffix=spec.get("interpretation_hint_suffix"),
        )
    if kind == "latest_spread":
        return calculate_latest_spread(
            spec["numerator_metric_key"],
            spec["denominator_metric_key"],
            db_path=db_path,
            fallback_observations=fallback_observations,
            output_metric_key=output_key,
            unit=spec.get("unit"),
            interpretation_hint_suffix=spec.get("interpretation_hint_suffix"),
        )
    if kind == "observation_yoy":
        return calculate_observation_yoy(
            spec["metric_key"],
            spec["window_observations"],
            db_path=db_path,
            output_metric_key=output_key,
            unit=spec.get("unit"),
            interpretation_hint_suffix=spec.get("interpretation_hint_suffix"),
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
                "source": observation.get("source"),
                "source_badge": observation.get("source_badge"),
                "source_series": observation.get("source_series"),
                "freshness_status": observation.get("freshness_status"),
                "ai_context_allowed": observation.get("ai_context_allowed"),
            }
        )
    return sorted(results, key=lambda item: item["date"])


def _latest_on_or_before(
    observations: list[dict[str, Any]],
    target_date: date,
) -> dict[str, Any] | None:
    candidates = [item for item in observations if item["date"] <= target_date]
    return candidates[-1] if candidates else None


def _latest_numeric_observation(
    metric_key: str,
    *,
    db_path: Path | str | None = None,
) -> dict[str, Any] | None:
    observations = _numeric_observations(metric_key, db_path=db_path)
    return observations[-1] if observations else None


def _latest_usable_spread_observation(
    metric_key: str,
    *,
    db_path: Path | str | None = None,
) -> dict[str, Any] | None:
    latest = _latest_numeric_observation(metric_key, db_path=db_path)
    if latest is None:
        return None
    if not _dependency_metadata_complete([latest]):
        return None
    return latest


def _fallback_observation(
    metric_key: str,
    fallback_observations: dict[str, dict[str, Any]],
) -> dict[str, Any] | None:
    raw = fallback_observations.get(metric_key)
    if not isinstance(raw, dict):
        return None
    value = raw.get("value")
    parsed_date = _parse_date(raw.get("observation_date"))
    if value is None or parsed_date is None:
        return None
    try:
        numeric_value = float(value)
    except (TypeError, ValueError):
        return None
    required_metadata = (
        "source",
        "source_badge",
        "source_series",
        "observation_date",
        "generated_at",
        "freshness_status",
    )
    if any(raw.get(field) in (None, "") for field in required_metadata):
        return None
    if raw.get("source_badge") != "official":
        return None
    if str(raw.get("freshness_status")).lower() in {"unknown", "missing"}:
        return None
    return {
        "value": numeric_value,
        "date": parsed_date,
        "observation_date": raw.get("observation_date"),
        "generated_at": raw.get("generated_at"),
        "source": raw.get("source"),
        "source_badge": raw.get("source_badge"),
        "source_series": raw.get("source_series"),
        "freshness_status": raw.get("freshness_status"),
        "ai_context_allowed": raw.get("ai_context_allowed"),
        "observation_source": "compact_dashboard",
    }


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
    dependency_observations: list[dict[str, Any]] | None = None,
    dependency_source_badges: list[str] | None = None,
    dependency_source_series: list[str] | None = None,
    dependency_sources: list[str] | None = None,
    ai_context_allowed: bool | None = None,
) -> HistoricalDerivedMetric:
    dependency_metadata = _dependency_metadata(dependency_observations or [])
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
        ai_context_allowed=(
            bool(ai_context_allowed)
            if ai_context_allowed is not None
            else _dependency_metadata_complete(dependency_observations or [])
        ),
        dependency_keys=dependency_keys,
        window=window,
        calculation=calculation,
        history_points_used=points_used,
        history_points_required=points_required,
        dependency_source_badges=dependency_source_badges
        if dependency_source_badges is not None
        else dependency_metadata["source_badges"],
        dependency_source_series=dependency_source_series
        if dependency_source_series is not None
        else dependency_metadata["source_series"],
        dependency_sources=dependency_sources
        if dependency_sources is not None
        else dependency_metadata["sources"],
        dependency_observation_dates=dependency_metadata["observation_dates"],
        dependency_generated_ats=dependency_metadata["generated_ats"],
        dependency_freshness_statuses=dependency_metadata["freshness_statuses"],
    )


def _dependency_metadata(observations: list[dict[str, Any]]) -> dict[str, list[str]]:
    return {
        "source_badges": _ordered_unique_metadata(observations, "source_badge"),
        "source_series": _ordered_unique_metadata(observations, "source_series"),
        "sources": _ordered_unique_metadata(observations, "source"),
        "observation_dates": _ordered_unique_metadata(observations, "observation_date"),
        "generated_ats": _ordered_unique_metadata(observations, "generated_at"),
        "freshness_statuses": _ordered_unique_metadata(observations, "freshness_status"),
    }


def _ordered_unique_metadata(observations: list[dict[str, Any]], key: str) -> list[str]:
    values: list[str] = []
    seen: set[str] = set()
    for item in observations:
        value = item.get(key)
        if value is None:
            continue
        text = str(value)
        if text in seen:
            continue
        seen.add(text)
        values.append(text)
    return values


def _dependency_metadata_complete(observations: list[dict[str, Any]]) -> bool:
    if not observations:
        return False
    for item in observations:
        if item.get("source_badge") is None:
            return False
        if item.get("source") is None:
            return False
        if item.get("source_series") is None:
            return False
        if item.get("observation_date") is None:
            return False
        if item.get("generated_at") is None:
            return False
        if item.get("freshness_status") is None:
            return False
    return True


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
        dependency_source_badges=[],
        dependency_source_series=[],
        dependency_sources=[],
        dependency_observation_dates=[],
        dependency_generated_ats=[],
        dependency_freshness_statuses=[],
    )


def _format_value(value: float, unit: str | None) -> str:
    if unit == "percent":
        return f"{value * 100:.2f}%"
    if unit == "pp":
        return f"{value:.2f}pp"
    if unit == "raw_pp":
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
