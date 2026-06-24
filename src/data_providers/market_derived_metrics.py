from __future__ import annotations

from datetime import date, timedelta

from . import fred_provider
from .market_data_packaging import (
    _derived_package_error,
    _package_item,
    _parse_date,
    _source_error_derived_item,
)
from .market_data_service import _to_float_or_none


def _build_treasury_derived_metrics(treasury_yields: dict[str, dict], timestamp: str) -> dict[str, dict]:
    result = {}
    for prefix, source_key in (
        ("dgs10", "nominal_yield_10y"),
        ("dgs30", "nominal_yield_30y"),
    ):
        source_item = treasury_yields.get(source_key, {})
        series_id = str(source_item.get("series_id") or "").strip()
        history = _fred_history(series_id, limit=140) if series_id else []
        for window_days in (30, 60):
            result[f"{prefix}_{window_days}d_high"] = _recent_high_item(
                key=f"{prefix}_{window_days}d_high",
                source_item=source_item,
                history=history,
                window_days=window_days,
                timestamp=timestamp,
            )
        result[f"{prefix}_distance_to_5pct"] = _distance_to_5pct_item(
            key=f"{prefix}_distance_to_5pct",
            source_item=source_item,
            timestamp=timestamp,
        )
        result[f"{prefix}_above_5pct"] = _above_5pct_item(
            key=f"{prefix}_above_5pct",
            source_item=source_item,
            timestamp=timestamp,
        )
        for window_observation_count in (5, 10):
            result[f"{prefix}_above_5pct_days_{window_observation_count}d"] = (
                _above_5pct_days_item(
                    key=f"{prefix}_above_5pct_days_{window_observation_count}d",
                    source_item=source_item,
                    history=history,
                    window_observation_count=window_observation_count,
                    timestamp=timestamp,
                )
            )
            result[f"{prefix}_{window_observation_count}d_avg"] = _threshold_average_item(
                key=f"{prefix}_{window_observation_count}d_avg",
                source_item=source_item,
                history=history,
                window_observation_count=window_observation_count,
                timestamp=timestamp,
            )
        result[f"{prefix}_5pct_breakout_confirmed"] = _breakout_confirmed_item(
            key=f"{prefix}_5pct_breakout_confirmed",
            source_item=source_item,
            history=history,
            timestamp=timestamp,
        )
    return result


def _build_inflation_derived_metrics(inflation_indicators: dict[str, dict], timestamp: str) -> dict[str, dict]:
    result = {}
    for prefix, source_key in (
        ("headline_cpi", "headline_cpi"),
        ("core_cpi", "core_cpi"),
        ("headline_pce", "headline_pce"),
        ("core_pce", "core_pce"),
        ("ppi_all_commodities", "ppi_all_commodities"),
        ("ppi_final_demand", "ppi_final_demand"),
    ):
        source_item = inflation_indicators.get(source_key, {})
        series_id = str(source_item.get("series_id") or "").strip()
        history = _fred_history(series_id, limit=30) if series_id else []
        result[f"{prefix}_mom_pct"] = _inflation_change_item(
            key=f"{prefix}_mom_pct",
            source_item=source_item,
            history=history,
            months_back=1,
            calculation="(latest_index / prior_month_index - 1) * 100",
            timestamp=timestamp,
        )
        result[f"{prefix}_yoy_pct"] = _inflation_change_item(
            key=f"{prefix}_yoy_pct",
            source_item=source_item,
            history=history,
            months_back=12,
            calculation="(latest_index / same_month_prior_year_index - 1) * 100",
            timestamp=timestamp,
        )
    return result


def _latest_available_observations(history: list[dict], count: int) -> list[dict]:
    observations = [
        item
        for item in history
        if isinstance(item.get("date"), date) and _to_float_or_none(item.get("value")) is not None
    ]
    observations.sort(key=lambda item: item["date"], reverse=True)
    return observations[:count]


def _above_5pct_days_item(
    *,
    key: str,
    source_item: dict,
    history: list[dict],
    window_observation_count: int,
    timestamp: str,
) -> dict:
    calculation = (
        f"count of latest {window_observation_count} available FRED daily observations "
        "with value >= 5.0"
    )
    if source_item.get("status") != "ok":
        return _source_error_derived_item(
            key,
            source_item,
            "Cannot calculate threshold count because source data is unavailable.",
            timestamp,
            unit="observations",
            window_observation_count=0,
            calculation=calculation,
        )

    window = _latest_available_observations(history, window_observation_count)
    if len(window) < window_observation_count:
        return _derived_package_error(
            key,
            source_item,
            f"Only {len(window)} valid daily observations available; {window_observation_count} required.",
            timestamp,
            unit="observations",
            window_observation_count=len(window),
            calculation=calculation,
            interpretation_hint="Insufficient history to count recent daily observations at or above 5%.",
        )

    above_count = sum(1 for item in window if item["value"] >= 5.0)
    return _package_item(
        key=key,
        name=f"{source_item.get('name') or source_item.get('series_id')} Above 5% Count",
        value=above_count,
        unit="observations",
        observation_date=window[0]["date"].isoformat(),
        source=source_item.get("source"),
        source_tier=source_item.get("source_tier"),
        freshness=source_item.get("freshness"),
        status="ok",
        error=None,
        interpretation_hint=(
            "Counts latest available FRED daily observations at or above 5%; "
            "not calendar days and not intraday highs."
        ),
        risk_relevance="Distinguishes a single daily threshold print from repeated observations near 5%.",
        timestamp=timestamp,
        series_id=source_item.get("series_id"),
        source_series=source_item.get("source"),
        derived_from=source_item.get("source"),
        calculation=calculation,
        window_observation_count=window_observation_count,
        intraday_high_available=False,
    )


def _threshold_average_item(
    *,
    key: str,
    source_item: dict,
    history: list[dict],
    window_observation_count: int,
    timestamp: str,
) -> dict:
    calculation = f"average of latest {window_observation_count} available FRED daily observations"
    if source_item.get("status") != "ok":
        return _source_error_derived_item(
            key,
            source_item,
            "Cannot calculate threshold average because source data is unavailable.",
            timestamp,
            unit=source_item.get("unit") or "percent",
            window_observation_count=0,
            calculation=calculation,
        )

    window = _latest_available_observations(history, window_observation_count)
    if len(window) < window_observation_count:
        return _derived_package_error(
            key,
            source_item,
            f"Only {len(window)} valid daily observations available; {window_observation_count} required.",
            timestamp,
            unit=source_item.get("unit") or "percent",
            window_observation_count=len(window),
            calculation=calculation,
            interpretation_hint="Insufficient history to calculate the recent available-observation average.",
        )

    avg_value = sum(float(item["value"]) for item in window) / window_observation_count
    return _package_item(
        key=key,
        name=f"{source_item.get('name') or source_item.get('series_id')} {window_observation_count} Observation Avg",
        value=round(avg_value, 4),
        unit=source_item.get("unit") or "percent",
        observation_date=window[0]["date"].isoformat(),
        source=source_item.get("source"),
        source_tier=source_item.get("source_tier"),
        freshness=source_item.get("freshness"),
        status="ok",
        error=None,
        interpretation_hint=(
            f"Average of latest {window_observation_count} available FRED daily observations; "
            "not a calendar-day or intraday measure."
        ),
        risk_relevance="Helps judge whether the 5% threshold is repeated in recent daily observations.",
        timestamp=timestamp,
        series_id=source_item.get("series_id"),
        source_series=source_item.get("source"),
        derived_from=source_item.get("source"),
        calculation=calculation,
        window_observation_count=window_observation_count,
        intraday_high_available=False,
    )


def _breakout_confirmed_item(
    *,
    key: str,
    source_item: dict,
    history: list[dict],
    timestamp: str,
) -> dict:
    calculation = "above_5pct_days_5d >= 3 and 5d_avg >= 5.0"
    if source_item.get("status") != "ok":
        return _source_error_derived_item(
            key,
            source_item,
            "Cannot calculate breakout confirmation because source data is unavailable.",
            timestamp,
            unit="boolean",
            window_observation_count=0,
            calculation=calculation,
        )

    window = _latest_available_observations(history, 5)
    if len(window) < 5:
        return _derived_package_error(
            key,
            source_item,
            f"Only {len(window)} valid daily observations available; 5 required.",
            timestamp,
            unit="boolean",
            window_observation_count=len(window),
            calculation=calculation,
            interpretation_hint="Insufficient history to confirm the 5% threshold under the project rule.",
        )

    above_count = sum(1 for item in window if item["value"] >= 5.0)
    avg_value = sum(float(item["value"]) for item in window) / 5
    confirmed = above_count >= 3 and avg_value >= 5.0
    return _package_item(
        key=key,
        name=f"{source_item.get('name') or source_item.get('series_id')} 5% Breakout Confirmed",
        value=confirmed,
        unit="boolean",
        observation_date=window[0]["date"].isoformat(),
        source=source_item.get("source"),
        source_tier=source_item.get("source_tier"),
        freshness=source_item.get("freshness"),
        status="ok",
        error=None,
        interpretation_hint=(
            "True only when at least 3 of the latest 5 available FRED daily observations are "
            "at or above 5% and the 5-observation average is at or above 5%."
        ),
        risk_relevance="Defines when the memo may describe the 5% threshold as confirmed under project rules.",
        timestamp=timestamp,
        series_id=source_item.get("series_id"),
        source_series=source_item.get("source"),
        derived_from=source_item.get("source"),
        calculation=calculation,
        window_observation_count=5,
        above_5pct_days_5d=above_count,
        five_observation_average=round(avg_value, 4),
        intraday_high_available=False,
    )


def _inflation_change_item(
    *,
    key: str,
    source_item: dict,
    history: list[dict],
    months_back: int,
    calculation: str,
    timestamp: str,
) -> dict:
    if source_item.get("status") != "ok":
        return _source_error_derived_item(
            key,
            source_item,
            "Cannot calculate inflation change because source index data is unavailable.",
            timestamp,
            unit="percent",
            calculation=calculation,
        )

    latest_value = _to_float_or_none(source_item.get("value"))
    latest_date = _parse_date(source_item.get("observation_date"))
    if latest_value is None or latest_date is None:
        return _derived_package_error(
            key,
            source_item,
            "Latest inflation index observation unavailable for percent-change calculation.",
            timestamp,
            unit="percent",
            calculation=calculation,
            status="error",
            freshness="unknown",
            interpretation_hint="Cannot calculate inflation change because the latest index value/date is unavailable.",
        )

    comparison = _monthly_comparison_observation(history, latest_date, months_back)
    comparison_value = _to_float_or_none(comparison.get("value")) if isinstance(comparison, dict) else None
    if comparison_value is None or comparison_value == 0:
        comparison_label = "prior month" if months_back == 1 else "same month prior year"
        return _derived_package_error(
            key,
            source_item,
            f"No valid {comparison_label} inflation index observation found.",
            timestamp,
            unit="percent",
            calculation=calculation,
            status="insufficient_history",
            freshness="insufficient_history",
            interpretation_hint="Derived from index levels; not a consensus-surprise measure.",
        )

    change_pct = (latest_value / comparison_value - 1.0) * 100
    return _package_item(
        key=key,
        name=f"{source_item.get('name') or source_item.get('series_id')} {'MoM' if months_back == 1 else 'YoY'}",
        value=round(change_pct, 4),
        unit="percent",
        observation_date=source_item.get("observation_date"),
        source=source_item.get("source"),
        source_tier=source_item.get("source_tier"),
        freshness=source_item.get("freshness"),
        status="ok",
        error=None,
        interpretation_hint="Derived from index levels; not a consensus-surprise measure.",
        risk_relevance="Provides trend context without treating index levels as consensus surprises.",
        timestamp=timestamp,
        series_id=source_item.get("series_id"),
        source_series=source_item.get("source"),
        derived_from=source_item.get("source"),
        calculation=calculation,
        comparison_observation_date=(
            comparison["date"].isoformat() if isinstance(comparison.get("date"), date) else None
        ),
        comparison_value=comparison_value,
    )


def _monthly_comparison_observation(
    history: list[dict],
    latest_date: date,
    months_back: int,
) -> dict | None:
    target = _add_months(latest_date, -months_back)
    for item in history:
        observed_at = item.get("date")
        if not isinstance(observed_at, date):
            continue
        if observed_at.year == target.year and observed_at.month == target.month:
            return item
    return None


def _add_months(value: date, months: int) -> date:
    month_index = value.year * 12 + value.month - 1 + months
    year = month_index // 12
    month = month_index % 12 + 1
    return date(year, month, 1)


def _recent_high_item(
    *,
    key: str,
    source_item: dict,
    history: list[dict],
    window_days: int,
    timestamp: str,
) -> dict:
    latest_date = _parse_date(source_item.get("observation_date"))
    if source_item.get("status") != "ok":
        return _source_error_derived_item(
            key,
            source_item,
            "Cannot calculate recent high because source data is unavailable.",
            timestamp,
            window_days=window_days,
            calculation=f"max daily FRED observation over the latest {window_days} calendar days",
        )
    if latest_date is None:
        return _derived_package_error(
            key,
            source_item,
            "Latest source observation unavailable for recent high calculation.",
            timestamp,
            window_days=window_days,
            calculation=f"max daily FRED observation over the latest {window_days} calendar days",
            status="error",
            freshness="unknown",
            interpretation_hint="Cannot calculate recent high because the latest source observation date is unavailable.",
        )

    start_date = latest_date - timedelta(days=window_days)
    window = [
        item
        for item in history
        if isinstance(item.get("date"), date) and start_date <= item["date"] <= latest_date
    ]
    if not window:
        return _derived_package_error(
            key,
            source_item,
            f"No valid observations in {window_days} day window.",
            timestamp,
            window_days=window_days,
            calculation=f"max daily FRED observation over the latest {window_days} calendar days",
        )

    high = max(window, key=lambda item: item["value"])
    high_date = high["date"].isoformat()
    return _package_item(
        key=key,
        name=f"{source_item.get('name') or source_item.get('series_id')} {window_days}D High",
        value=float(high["value"]),
        unit=source_item.get("unit"),
        observation_date=high_date,
        source=source_item.get("source"),
        source_tier=source_item.get("source_tier"),
        freshness=source_item.get("freshness"),
        status="ok",
        error=None,
        interpretation_hint="FRED daily constant maturity yield; not intraday high.",
        risk_relevance="Recent daily high helps frame whether long rates are pressing toward key thresholds.",
        timestamp=timestamp,
        series_id=source_item.get("series_id"),
        source_series=source_item.get("source"),
        derived_from=source_item.get("source"),
        window_days=window_days,
        high_date=high_date,
        intraday_high_available=False,
        calculation=f"max daily FRED observation over the latest {window_days} calendar days",
    )


def _distance_to_5pct_item(*, key: str, source_item: dict, timestamp: str) -> dict:
    value = _to_float_or_none(source_item.get("value"))
    if source_item.get("status") != "ok":
        return _source_error_derived_item(
            key,
            source_item,
            "Cannot calculate distance to 5% because source data is unavailable.",
            timestamp,
            calculation="latest_value - 5.0 percentage points",
        )
    if value is None:
        return _derived_package_error(
            key,
            source_item,
            "Latest source observation unavailable for 5 percent distance calculation.",
            timestamp,
            calculation="latest_value - 5.0 percentage points",
            status="error",
            freshness="unknown",
            interpretation_hint="Cannot calculate distance to 5% because the latest source value is unavailable.",
        )
    return _package_item(
        key=key,
        name=f"{source_item.get('name') or source_item.get('series_id')} Distance to 5%",
        value=round(value - 5.0, 4),
        unit="percentage_points",
        observation_date=source_item.get("observation_date"),
        source=source_item.get("source"),
        source_tier=source_item.get("source_tier"),
        freshness=source_item.get("freshness"),
        status="ok",
        error=None,
        interpretation_hint="Positive value means the latest daily FRED observation is above 5%; negative means below 5%.",
        risk_relevance="Frames long-rate pressure near the 5% threshold without using intraday highs.",
        timestamp=timestamp,
        series_id=source_item.get("series_id"),
        source_series=source_item.get("source"),
        derived_from=source_item.get("source"),
        intraday_high_available=False,
        calculation="latest_value - 5.0 percentage points",
    )


def _above_5pct_item(*, key: str, source_item: dict, timestamp: str) -> dict:
    value = _to_float_or_none(source_item.get("value"))
    if source_item.get("status") != "ok":
        return _source_error_derived_item(
            key,
            source_item,
            "Cannot calculate above-5% flag because source data is unavailable.",
            timestamp,
            calculation="latest_value >= 5.0",
        )
    if value is None:
        return _derived_package_error(
            key,
            source_item,
            "Latest source observation unavailable for above 5 percent calculation.",
            timestamp,
            calculation="latest_value >= 5.0",
            status="error",
            freshness="unknown",
            interpretation_hint="Cannot calculate above-5% flag because the latest source value is unavailable.",
        )
    return _package_item(
        key=key,
        name=f"{source_item.get('name') or source_item.get('series_id')} Above 5%",
        value=bool(value >= 5.0),
        unit="boolean",
        observation_date=source_item.get("observation_date"),
        source=source_item.get("source"),
        source_tier=source_item.get("source_tier"),
        freshness=source_item.get("freshness"),
        status="ok",
        error=None,
        interpretation_hint="True only if the latest daily FRED observation is at or above 5%.",
        risk_relevance="Flags rate-pressure threshold using daily observations only.",
        timestamp=timestamp,
        series_id=source_item.get("series_id"),
        source_series=source_item.get("source"),
        derived_from=source_item.get("source"),
        intraday_high_available=False,
        calculation="latest_value >= 5.0",
    )


def _oil_30d_change_item(*, key: str, source_item: dict, timestamp: str) -> dict:
    latest_value = _to_float_or_none(source_item.get("value"))
    latest_date = _parse_date(source_item.get("observation_date"))
    series_id = str(source_item.get("series_id") or "").strip()
    if source_item.get("status") != "ok":
        return _source_error_derived_item(
            key,
            source_item,
            "Cannot calculate 30 day oil change because source data is unavailable.",
            timestamp,
            window_days=30,
            calculation="(latest_value - value_30d_ago_or_nearest_available) / old_value * 100",
        )
    if latest_value is None or latest_date is None or not series_id:
        return _derived_package_error(
            key,
            source_item,
            "Latest oil observation unavailable for 30 day change calculation.",
            timestamp,
            window_days=30,
            calculation="(latest_value - value_30d_ago_or_nearest_available) / old_value * 100",
            status="error",
            freshness="unknown",
            interpretation_hint="Cannot calculate 30 day oil change because the latest source observation is unavailable.",
        )

    old = _nearest_observation(
        _fred_history(series_id, limit=90),
        latest_date - timedelta(days=30),
        exclude_date=latest_date,
    )
    old_value = _to_float_or_none(old.get("value")) if isinstance(old, dict) else None
    if old_value is None or old_value == 0:
        return _derived_package_error(
            key,
            source_item,
            "No valid historical oil observation near 30 days ago.",
            timestamp,
            window_days=30,
            calculation="(latest_value - value_30d_ago_or_nearest_available) / old_value * 100",
        )

    change_abs = latest_value - old_value
    change_pct = change_abs / old_value * 100
    return _package_item(
        key=key,
        name=f"{source_item.get('name') or series_id} 30D Change",
        value=round(change_pct, 4),
        unit="percent",
        observation_date=source_item.get("observation_date"),
        source=source_item.get("source"),
        source_tier=source_item.get("source_tier"),
        freshness=source_item.get("freshness"),
        status="ok",
        error=None,
        interpretation_hint="30 day change uses nearest available daily FRED observation, not intraday price.",
        risk_relevance="Oil momentum can indicate energy pressure but does not alone determine inflation.",
        timestamp=timestamp,
        series_id=series_id,
        source_series=source_item.get("source"),
        derived_from=source_item.get("source"),
        window_days=30,
        calculation="(latest_value - value_30d_ago_or_nearest_available) / old_value * 100",
        change_abs=round(change_abs, 4),
        change_pct=round(change_pct, 4),
        old_value=old_value,
        old_observation_date=old["date"].isoformat() if isinstance(old.get("date"), date) else None,
    )


def _fred_history(series_id: str, limit: int) -> list[dict]:
    result = fred_provider.get_fred_series(series_id, limit=limit)
    if result.get("status") != "ok":
        return []
    observations = []
    for item in result.get("data", []):
        observed_at = _parse_date(item.get("date"))
        value = _to_float_or_none(item.get("value"))
        if observed_at is not None and value is not None:
            observations.append({"date": observed_at, "value": value})
    return observations


def _nearest_observation(
    observations: list[dict],
    target_date: date,
    *,
    exclude_date: date,
) -> dict | None:
    candidates = [
        item
        for item in observations
        if isinstance(item.get("date"), date) and item["date"] != exclude_date
    ]
    if not candidates:
        return None
    return min(candidates, key=lambda item: abs((item["date"] - target_date).days))
