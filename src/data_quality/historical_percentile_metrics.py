from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from statistics import mean, median, pstdev
from typing import Any

from data_quality import market_history_store


INTERPRETATION_BOUNDARY = (
    "Historical percentile is relative to available local history, not a forecast. "
    "Z-score and robust z-score are normalization statistics, not event odds. "
    "Short or limited history can make percentile unstable. Different frequencies "
    "must not be mixed. Percentile bands are reference review only. "
    "Proxy inputs are auxiliary and cannot be hard triggers."
)
PREFERRED_WINDOW_DAYS = 365 * 5
FALLBACK_WINDOW_DAYS = 365 * 3
ALL_AVAILABLE_LIMITED = "all_available_limited"
LOOKBACK_5Y = "5Y rolling"
LOOKBACK_3Y = "3Y rolling limited_history"
SUFFICIENT_HISTORY_STATUS = "sufficient"
LIMITED_HISTORY_STATUS = "limited_history"
INSUFFICIENT_HISTORY_STATUS = "insufficient_history"
BAD_FRESHNESS = {"unknown", "missing", "stale"}
BAD_STATUSES = {
    "missing",
    "research_needed",
    "not_available",
    "insufficient_history",
    "stale",
}
OFFICIAL_BADGES = {"official", "official_fallback"}
PRIMARY_CREDIT_OAS_METRICS = {"high_yield_spread", "investment_grade_spread"}
LONG_HISTORY_CREDIT_PROXY_REFERENCES = {"BAA10Y", "baa10y"}
CREDIT_OAS_PROVIDER_REBUILD_STATUS = {
    "high_yield_spread": "provider_rebuild_limited",
    "investment_grade_spread": "provider_rebuild_limited",
    "BAA10Y": "reproducible_long_history",
    "baa10y": "reproducible_long_history",
}
AUXILIARY_CONTEXT_FIELDS = (
    "metric_key",
    "display_name",
    "value_text",
    "status",
    "source_badge",
    "lookback_window",
    "lookback_start",
    "lookback_end",
    "observation_count",
    "minimum_observation_count",
    "history_quality_status",
    "percentile",
    "percentile_band",
    "zscore",
    "zscore_band",
    "robust_zscore",
    "robust_zscore_band",
    "percentile_direction",
    "frequency_class",
    "ai_context_tier",
    "trigger_eligibility",
    "interpretation_boundary",
    "missing_reason",
    "blocked_reason",
    "reliability_band",
    "reliability_drivers",
    "divergence_band",
    "divergence_notes",
    "method_agreement",
    "normalization_methods_available",
    "percentile_zscore_alignment",
    "percentile_robust_zscore_alignment",
    "zscore_robust_zscore_alignment",
    "source_quality_note",
    "history_window_note",
    "history_coverage_status",
    "provider_rebuild_status",
    "normalization_availability",
    "coverage_diagnostics",
    "credit_reference_role",
    "substitution_policy",
    "long_history_reference_status",
)

BROAD_BAND_LEVELS: dict[str | None, int] = {
    "low_extreme": -1,
    "normal": 0,
    "elevated": 1,
    "high": 2,
    "extreme": 3,
}


@dataclass(frozen=True)
class PercentileMetricSpec:
    metric_key: str
    source_metric_key: str
    display_name: str
    kind: str
    percentile_direction: str
    minimum_observation_count: int
    unit: str | None = None
    frequency_class: str = "daily_or_weekly_market"
    transform_class: str = "level"


PERCENTILE_METRIC_SPECS: tuple[PercentileMetricSpec, ...] = (
    PercentileMetricSpec("high_yield_spread_percentile", "high_yield_spread", "High-yield spread percentile", "percentile", "higher_is_more_stress", 60, "percentile"),
    PercentileMetricSpec("high_yield_spread_zscore", "high_yield_spread", "High-yield spread z-score", "zscore", "higher_is_more_stress", 60, "zscore"),
    PercentileMetricSpec("high_yield_spread_robust_zscore", "high_yield_spread", "High-yield spread robust z-score", "robust_zscore", "higher_is_more_stress", 60, "robust_zscore"),
    PercentileMetricSpec("investment_grade_spread_percentile", "investment_grade_spread", "Investment-grade spread percentile", "percentile", "higher_is_more_stress", 60, "percentile"),
    PercentileMetricSpec("investment_grade_spread_zscore", "investment_grade_spread", "Investment-grade spread z-score", "zscore", "higher_is_more_stress", 60, "zscore"),
    PercentileMetricSpec("investment_grade_spread_robust_zscore", "investment_grade_spread", "Investment-grade spread robust z-score", "robust_zscore", "higher_is_more_stress", 60, "robust_zscore"),
    PercentileMetricSpec("vix_percentile", "vix", "VIX percentile", "percentile", "higher_is_more_stress", 60, "percentile"),
    PercentileMetricSpec("vix_zscore", "vix", "VIX z-score", "zscore", "higher_is_more_stress", 60, "zscore"),
    PercentileMetricSpec("vix_robust_zscore", "vix", "VIX robust z-score", "robust_zscore", "higher_is_more_stress", 60, "robust_zscore"),
    PercentileMetricSpec("dgs30_percentile", "dgs30", "30Y Treasury yield percentile", "percentile", "higher_is_more_stress", 60, "percentile"),
    PercentileMetricSpec("dgs30_zscore", "dgs30", "30Y Treasury yield z-score", "zscore", "higher_is_more_stress", 60, "zscore"),
    PercentileMetricSpec("dgs30_robust_zscore", "dgs30", "30Y Treasury yield robust z-score", "robust_zscore", "higher_is_more_stress", 60, "robust_zscore"),
    PercentileMetricSpec("dfii10_percentile", "dfii10", "10Y real yield percentile", "percentile", "higher_is_more_stress", 60, "percentile"),
    PercentileMetricSpec("dfii10_zscore", "dfii10", "10Y real yield z-score", "zscore", "higher_is_more_stress", 60, "zscore"),
    PercentileMetricSpec("dfii10_robust_zscore", "dfii10", "10Y real yield robust z-score", "robust_zscore", "higher_is_more_stress", 60, "robust_zscore"),
    PercentileMetricSpec("sp500_drawdown_3m_percentile", "sp500_drawdown_3m", "S&P 500 3M drawdown stress percentile", "percentile", "lower_is_more_stress", 60, "percentile", transform_class="damage"),
    PercentileMetricSpec("sp500_drawdown_3m_robust_zscore", "sp500_drawdown_3m", "S&P 500 3M drawdown robust z-score", "robust_zscore", "lower_is_more_stress", 60, "robust_zscore", transform_class="damage"),
    PercentileMetricSpec("nasdaq100_drawdown_3m_percentile", "nasdaq100_drawdown_3m", "Nasdaq 100 3M drawdown stress percentile", "percentile", "lower_is_more_stress", 60, "percentile", transform_class="damage"),
    PercentileMetricSpec("nasdaq100_drawdown_3m_robust_zscore", "nasdaq100_drawdown_3m", "Nasdaq 100 3M drawdown robust z-score", "robust_zscore", "lower_is_more_stress", 60, "robust_zscore", transform_class="damage"),
    PercentileMetricSpec("initial_claims_4w_avg_percentile", "initial_claims_4w_avg", "Initial claims 4W average percentile", "percentile", "higher_is_more_stress", 26, "percentile", frequency_class="weekly_labor"),
    PercentileMetricSpec("initial_claims_4w_avg_robust_zscore", "initial_claims_4w_avg", "Initial claims 4W average robust z-score", "robust_zscore", "higher_is_more_stress", 26, "robust_zscore", frequency_class="weekly_labor"),
    PercentileMetricSpec("continuing_claims_4w_avg_percentile", "continuing_claims_4w_avg", "Continuing claims 4W average percentile", "percentile", "higher_is_more_stress", 26, "percentile", frequency_class="weekly_labor"),
    PercentileMetricSpec("continuing_claims_4w_avg_robust_zscore", "continuing_claims_4w_avg", "Continuing claims 4W average robust z-score", "robust_zscore", "higher_is_more_stress", 26, "robust_zscore", frequency_class="weekly_labor"),
)


def build_historical_percentile_rows(
    *,
    db_path: str | None = None,
) -> list[dict[str, Any]]:
    unique_source_keys = list(dict.fromkeys(spec.source_metric_key for spec in PERCENTILE_METRIC_SPECS))
    prefetched = market_history_store.list_market_observations_batch(
        unique_source_keys,
        limit_per_key=market_history_store.MAX_LIMIT,
        db_path=db_path,
    )
    return [build_metric_payload(spec, db_path=db_path, prefetched=prefetched) for spec in PERCENTILE_METRIC_SPECS]


class EvidenceIndex:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self._rows = {str(row.get("metric_key")): row for row in rows}

    def by_metric_key(self, metric_key: str) -> dict[str, Any] | None:
        return self._rows.get(metric_key)

    def d13_context(self, metric_key: str) -> dict[str, Any] | None:
        row = self.by_metric_key(metric_key)
        if row is None:
            return None
        if row.get("module") != "historical_risk_percentile":
            return None
        return sanitized_d13_context(row)

    def available_d13_context(self, keys: tuple[str, ...] | list[str]) -> list[dict[str, Any]]:
        return [
            context
            for key in keys
            for context in [self.d13_context(key)]
            if context is not None and _hard_auxiliary_context(context)
        ]

    def missing_d13_context(self, keys: tuple[str, ...] | list[str]) -> list[dict[str, Any]]:
        missing: list[dict[str, Any]] = []
        for key in keys:
            context = self.d13_context(key)
            if context is None:
                missing.append(
                    {
                        "metric_key": key,
                        "status": "missing",
                        "source_badge": "missing",
                        "missing_reason": "d13_context_row_missing",
                    }
                )
            elif not _hard_auxiliary_context(context):
                missing.append(context)
        return missing


def build_evidence_index(rows: list[dict[str, Any]]) -> EvidenceIndex:
    return EvidenceIndex(rows)


def sanitized_d13_context(row: dict[str, Any]) -> dict[str, Any]:
    return {field: row.get(field) for field in AUXILIARY_CONTEXT_FIELDS if field in row}


def _hard_auxiliary_context(context: dict[str, Any]) -> bool:
    if context.get("status") in BAD_STATUSES:
        return False
    if context.get("source_badge") in {"missing", "research_needed", "search-derived"}:
        return False
    if context.get("history_quality_status") == INSUFFICIENT_HISTORY_STATUS:
        return False
    if context.get("trigger_eligibility") == "not_eligible":
        return False
    if not (context.get("percentile_band") or context.get("zscore_band") or context.get("robust_zscore_band")):
        return False
    return True


def build_metric_payload(
    spec: PercentileMetricSpec,
    *,
    db_path: str | None = None,
    prefetched: dict[str, list[dict[str, Any]]] | None = None,
) -> dict[str, Any]:
    generated_at = datetime.now(timezone.utc).isoformat()
    latest_any = _latest_numeric_observation(spec.source_metric_key, db_path=db_path, prefetched=prefetched)
    if latest_any is not None and (
        latest_any.get("status") in BAD_STATUSES
        or latest_any.get("freshness_status") == "stale"
    ):
        return _blocked_payload(
            spec,
            "stale" if latest_any.get("freshness_status") == "stale" else "insufficient_history",
            "latest_input_unusable",
            0,
            generated_at,
            latest=latest_any,
        )
    observations = _usable_observations(spec.source_metric_key, db_path=db_path, prefetched=prefetched)
    if not observations:
        return _blocked_payload(spec, "missing", "latest_input_missing", 0, generated_at)
    latest = observations[-1]
    window = _select_lookback_window(observations)
    if window["status"] == INSUFFICIENT_HISTORY_STATUS:
        return _blocked_payload(
            spec,
            "insufficient_history",
            "insufficient_history_for_percentile",
            window["observation_count"],
            generated_at,
            latest=latest,
            lookback=window,
        )
    values = [item["value"] for item in window["observations"]]
    if len(values) < spec.minimum_observation_count:
        return _blocked_payload(
            spec,
            "insufficient_history",
            "insufficient_history_for_percentile",
            len(values),
            generated_at,
            latest=latest,
            lookback=window,
        )
    current = latest["value"]
    percentile = _empirical_percentile(current, values)
    zscore = _zscore(current, values)
    robust_zscore = _robust_zscore(current, values)
    percentile_band = _percentile_band(percentile, spec.percentile_direction)
    zscore_band = _zscore_band(zscore, spec.percentile_direction)
    robust_zscore_band = _zscore_band(robust_zscore, spec.percentile_direction)
    if spec.kind == "percentile":
        value = round(percentile, 2)
        value_text = f"{value:.2f} percentile ({percentile_band})"
        band = percentile_band
    elif spec.kind == "zscore":
        if zscore is None:
            return _blocked_payload(
                spec,
                "not_available",
                "zscore_not_available_zero_std",
                len(values),
                generated_at,
                latest=latest,
                lookback=window,
            )
        value = round(zscore, 4)
        value_text = f"{value:+.2f} z ({zscore_band})"
        band = zscore_band
    else:
        if robust_zscore is None:
            return _blocked_payload(
                spec,
                "not_available",
                "robust_zscore_not_available_zero_mad",
                len(values),
                generated_at,
                latest=latest,
                lookback=window,
            )
        value = round(robust_zscore, 4)
        value_text = f"{value:+.2f} robust z ({robust_zscore_band})"
        band = robust_zscore_band
    trigger_eligibility = _trigger_eligibility(latest.get("source_badge"), window["status"])
    ai_context_tier = _ai_context_tier(trigger_eligibility)
    reliability = _reliability_metadata(
        status=_status_for_band(band),
        history_quality_status=window["status"],
        latest_source_badge=latest.get("source_badge"),
        trigger_eligibility=trigger_eligibility,
        percentile_band=percentile_band,
        zscore_band=zscore_band,
        robust_zscore_band=robust_zscore_band,
        lookback_window=window["lookback_window"],
        observation_count=len(values),
        minimum_observation_count=spec.minimum_observation_count,
        blocked=False,
    )
    coverage = _credit_oas_coverage_metadata(
        spec,
        status=_status_for_band(band),
        history_quality_status=window["status"],
        observation_count=len(values),
        latest=latest,
        lookback=window,
        percentile_band=percentile_band,
        zscore_band=zscore_band,
        robust_zscore_band=robust_zscore_band,
    )
    payload = {
        "metric_key": spec.metric_key,
        "display_name": spec.display_name,
        "value": value,
        "value_text": value_text,
        "unit": spec.unit,
        "status": _status_for_band(band),
        "source": "local_market_history",
        "source_badge": "derived",
        "source_series": latest.get("source_series"),
        "observation_date": latest.get("observation_date"),
        "generated_at": generated_at,
        "freshness_status": latest.get("freshness_status") or "historical",
        "missing_reason": None,
        "interpretation_hint": _interpretation_hint(spec, window, trigger_eligibility),
        "ai_context_allowed": False,
        "input_evidence": [_input_snapshot(latest)],
        "lookback_window": window["lookback_window"],
        "lookback_start": window["lookback_start"],
        "lookback_end": window["lookback_end"],
        "observation_count": len(values),
        "minimum_observation_count": spec.minimum_observation_count,
        "history_quality_status": window["status"],
        "percentile": round(percentile, 4),
        "percentile_band": percentile_band,
        "zscore": round(zscore, 6) if zscore is not None else None,
        "zscore_band": zscore_band,
        "robust_zscore": round(robust_zscore, 6) if robust_zscore is not None else None,
        "robust_zscore_band": robust_zscore_band,
        "percentile_direction": spec.percentile_direction,
        "frequency_class": spec.frequency_class,
        "transform_class": spec.transform_class,
        "ai_context_tier": ai_context_tier,
        "trigger_eligibility": trigger_eligibility,
        **reliability,
        **coverage,
        "component_contributions": {
            "lookback_window": window["lookback_window"],
            "lookback_start": window["lookback_start"],
            "lookback_end": window["lookback_end"],
            "observation_count": len(values),
            "minimum_observation_count": spec.minimum_observation_count,
            "history_quality_status": window["status"],
            "percentile_direction": spec.percentile_direction,
            "percentile": round(percentile, 4),
            "percentile_band": percentile_band,
            "zscore": round(zscore, 6) if zscore is not None else None,
            "zscore_band": zscore_band,
            "robust_zscore": round(robust_zscore, 6) if robust_zscore is not None else None,
            "robust_zscore_band": robust_zscore_band,
            "history_mean": round(mean(values), 6),
            "history_std": round(pstdev(values), 6),
            "history_median": round(median(values), 6),
            "history_mad": round(_mad(values), 6),
            "frequency_class": spec.frequency_class,
            "transform_class": spec.transform_class,
            "trigger_eligibility": trigger_eligibility,
            "ai_context_tier": ai_context_tier,
            **reliability,
            **coverage,
        },
        "missing_inputs": [],
        "interpretation_boundary": INTERPRETATION_BOUNDARY,
    }
    payload["ai_context_allowed"] = _ai_context_allowed(payload)
    if not payload["ai_context_allowed"] and trigger_eligibility != "not_eligible":
        payload["trigger_eligibility"] = "not_eligible"
        payload["ai_context_tier"] = "excluded"
        payload["component_contributions"]["trigger_eligibility"] = "not_eligible"
        payload["component_contributions"]["ai_context_tier"] = "excluded"
    return payload


def _blocked_payload(
    spec: PercentileMetricSpec,
    status: str,
    missing_reason: str,
    observation_count: int,
    generated_at: str,
    *,
    latest: dict[str, Any] | None = None,
    lookback: dict[str, Any] | None = None,
) -> dict[str, Any]:
    lookback_window = (lookback or {}).get("lookback_window") or "5Y rolling"
    history_quality_status = (lookback or {}).get("status") or status
    trigger_eligibility = "not_eligible"
    latest_source_badge = latest.get("source_badge") if latest else None
    reliability = _reliability_metadata(
        status=status,
        history_quality_status=history_quality_status,
        latest_source_badge=latest_source_badge,
        trigger_eligibility=trigger_eligibility,
        percentile_band=None,
        zscore_band=None,
        robust_zscore_band=None,
        lookback_window=lookback_window,
        observation_count=observation_count,
        minimum_observation_count=spec.minimum_observation_count,
        blocked=True,
        missing_reason=missing_reason,
    )
    coverage = _credit_oas_coverage_metadata(
        spec,
        status=status,
        history_quality_status=history_quality_status,
        observation_count=observation_count,
        latest=latest,
        lookback=lookback,
        percentile_band=None,
        zscore_band=None,
        robust_zscore_band=None,
    )
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
            f"same-frequency local market history observations for {spec.source_metric_key}; "
            f"history_quality_status={history_quality_status}."
        ),
        "ai_context_allowed": False,
        "input_evidence": [_input_snapshot(latest)] if latest else [],
        "lookback_window": lookback_window,
        "lookback_start": (lookback or {}).get("lookback_start"),
        "lookback_end": (lookback or {}).get("lookback_end"),
        "observation_count": observation_count,
        "minimum_observation_count": spec.minimum_observation_count,
        "history_quality_status": history_quality_status,
        "percentile": None,
        "percentile_band": None,
        "zscore": None,
        "zscore_band": None,
        "robust_zscore": None,
        "robust_zscore_band": None,
        "percentile_direction": spec.percentile_direction,
        "frequency_class": spec.frequency_class,
        "transform_class": spec.transform_class,
        "ai_context_tier": "excluded",
        "trigger_eligibility": trigger_eligibility,
        **reliability,
        **coverage,
        "component_contributions": {
            "lookback_window": lookback_window,
            "lookback_start": (lookback or {}).get("lookback_start"),
            "lookback_end": (lookback or {}).get("lookback_end"),
            "observation_count": observation_count,
            "minimum_observation_count": spec.minimum_observation_count,
            "history_quality_status": history_quality_status,
            "percentile_direction": spec.percentile_direction,
            "frequency_class": spec.frequency_class,
            "transform_class": spec.transform_class,
            "trigger_eligibility": trigger_eligibility,
            "ai_context_tier": "excluded",
            **reliability,
            **coverage,
        },
        "missing_inputs": [spec.source_metric_key],
        "interpretation_boundary": INTERPRETATION_BOUNDARY,
    }


def _usable_observations(
    metric_key: str,
    *,
    db_path: str | None,
    prefetched: dict[str, list[dict[str, Any]]] | None = None,
) -> list[dict[str, Any]]:
    if prefetched is not None:
        rows = prefetched.get(metric_key, [])
    else:
        rows = market_history_store.list_market_observations(
            metric_key=metric_key,
            limit=market_history_store.MAX_LIMIT,
            db_path=db_path,
        )
    observations: list[dict[str, Any]] = []
    for row in reversed(rows):
        value = _to_float(row.get("value_numeric"))
        parsed_date = _parse_date(row.get("observation_date"))
        if value is None or parsed_date is None:
            continue
        if row.get("status") in market_history_store.BLOCKED_STATUSES:
            continue
        if row.get("source_badge") in market_history_store.BLOCKED_SOURCE_BADGES:
            continue
        observations.append({**row, "value": value, "date": parsed_date})
    return observations


def _latest_numeric_observation(
    metric_key: str,
    *,
    db_path: str | None,
    prefetched: dict[str, list[dict[str, Any]]] | None = None,
) -> dict[str, Any] | None:
    if prefetched is not None:
        rows = prefetched.get(metric_key, [])
    else:
        rows = market_history_store.list_market_observations(
            metric_key=metric_key,
            limit=market_history_store.MAX_LIMIT,
            db_path=db_path,
        )
    for row in rows:
        value = _to_float(row.get("value_numeric"))
        parsed_date = _parse_date(row.get("observation_date"))
        if value is None or parsed_date is None:
            continue
        return {**row, "value": value, "date": parsed_date}
    return None


def _select_lookback_window(observations: list[dict[str, Any]]) -> dict[str, Any]:
    latest = observations[-1]
    latest_date = latest["date"]
    preferred_start = latest_date - timedelta(days=PREFERRED_WINDOW_DAYS)
    fallback_start = latest_date - timedelta(days=FALLBACK_WINDOW_DAYS)
    preferred = [item for item in observations if item["date"] >= preferred_start]
    fallback = [item for item in observations if item["date"] >= fallback_start]
    if observations[0]["date"] <= preferred_start and preferred:
        return _window_result(preferred, LOOKBACK_5Y, SUFFICIENT_HISTORY_STATUS)
    if observations[0]["date"] <= fallback_start and fallback:
        return _window_result(fallback, LOOKBACK_3Y, LIMITED_HISTORY_STATUS)
    return _window_result(observations, ALL_AVAILABLE_LIMITED, INSUFFICIENT_HISTORY_STATUS)


def _window_result(
    observations: list[dict[str, Any]],
    lookback_window: str,
    status: str,
) -> dict[str, Any]:
    return {
        "observations": observations,
        "lookback_window": lookback_window,
        "lookback_start": observations[0]["observation_date"] if observations else None,
        "lookback_end": observations[-1]["observation_date"] if observations else None,
        "observation_count": len(observations),
        "status": status,
    }


def _empirical_percentile(current: float, values: list[float]) -> float:
    less = sum(1 for value in values if value < current)
    equal = sum(1 for value in values if value == current)
    return ((less + 0.5 * equal) / len(values)) * 100.0


def _zscore(current: float, values: list[float]) -> float | None:
    std = pstdev(values)
    if math.isclose(std, 0.0):
        return None
    return (current - mean(values)) / std


def _robust_zscore(current: float, values: list[float]) -> float | None:
    mad = _mad(values)
    if math.isclose(mad, 0.0):
        return None
    return 0.6745 * (current - median(values)) / mad


def _mad(values: list[float]) -> float:
    center = median(values)
    return median([abs(value - center) for value in values])


def _percentile_band(percentile: float, direction: str) -> str:
    if direction == "lower_is_more_stress":
        if percentile < 10.0:
            return "extreme"
        if percentile < 20.0:
            return "high"
        if percentile < 40.0:
            return "elevated"
        return "normal"
    if percentile > 90.0:
        return "extreme"
    if percentile >= 80.0:
        return "high"
    if percentile >= 60.0:
        return "elevated"
    return "normal"


def _zscore_band(zscore: float | None, direction: str) -> str | None:
    if zscore is None:
        return None
    stress_value = -zscore if direction == "lower_is_more_stress" else zscore
    if stress_value > 3.0:
        return "extreme"
    if stress_value > 2.0:
        return "high"
    if stress_value > 1.0:
        return "elevated"
    if stress_value < -2.0:
        return "low_extreme"
    return "normal"


def _status_for_band(band: str | None) -> str:
    if band == "extreme":
        return "stress"
    if band == "high":
        return "pressure"
    if band == "elevated":
        return "watch"
    return "ok"


def _trigger_eligibility(source_badge: str | None, history_quality_status: str) -> str:
    if history_quality_status not in {SUFFICIENT_HISTORY_STATUS, LIMITED_HISTORY_STATUS}:
        return "not_eligible"
    if source_badge in OFFICIAL_BADGES:
        return "hard_trigger_allowed"
    if source_badge == "unofficial_fallback":
        return "auxiliary_only"
    if source_badge == "proxy":
        return "proxy_auxiliary_only"
    if source_badge == "derived":
        return "auxiliary_only"
    return "not_eligible"


def _ai_context_tier(trigger_eligibility: str) -> str:
    if trigger_eligibility == "hard_trigger_allowed":
        return "factual_band"
    if trigger_eligibility in {"auxiliary_only", "proxy_auxiliary_only", "context_only"}:
        return "auxiliary_context"
    return "excluded"


def _ai_context_allowed(payload: dict[str, Any]) -> bool:
    if not payload.get("source") or not payload.get("source_badge"):
        return False
    if not (payload.get("observation_date") or payload.get("generated_at")):
        return False
    if payload.get("freshness_status") in BAD_FRESHNESS:
        return False
    if payload.get("status") in BAD_STATUSES:
        return False
    if not payload.get("lookback_window"):
        return False
    if int(payload.get("observation_count") or 0) < int(payload.get("minimum_observation_count") or 0):
        return False
    if not (payload.get("percentile_band") or payload.get("zscore_band") or payload.get("robust_zscore_band")):
        return False
    if not payload.get("interpretation_boundary"):
        return False
    return True


def _interpretation_hint(
    spec: PercentileMetricSpec,
    window: dict[str, Any],
    trigger_eligibility: str,
) -> str:
    direction_note = (
        "lower values represent higher damage/severity"
        if spec.percentile_direction == "lower_is_more_stress"
        else "higher values represent higher stress"
    )
    return (
        f"Derived from local market history using {window['lookback_window']} "
        f"for {spec.source_metric_key}; percentile_direction={spec.percentile_direction} "
        f"({direction_note}); history_quality_status={window['status']}; "
        f"trigger_eligibility={trigger_eligibility}. "
        "Bands are descriptive normalization labels, not probabilities or allocation directives."
    )


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
    if status == "not_available":
        return "not available"
    if status == "stale":
        return "stale"
    return "missing"


def _parse_date(value: Any) -> date | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        return date.fromisoformat(value[:10])
    except ValueError:
        return None


def _to_float(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return float(str(value).strip())
    except (TypeError, ValueError):
        return None


def _band_level(band: str | None) -> int | None:
    if band is None:
        return None
    return BROAD_BAND_LEVELS.get(band)


def _alignment_label(level_a: int | None, level_b: int | None) -> str:
    if level_a is None or level_b is None:
        return "not_available"
    diff = abs(level_a - level_b)
    if diff == 0:
        return "aligned"
    if diff == 1:
        return "mildly_divergent"
    return "materially_divergent"


def _normalization_methods_available(
    percentile_band: str | None,
    zscore_band: str | None,
    robust_zscore_band: str | None,
) -> dict[str, bool]:
    return {
        "percentile": percentile_band is not None,
        "zscore": zscore_band is not None,
        "robust_zscore": robust_zscore_band is not None,
    }


def _divergence_band(
    percentile_band: str | None,
    zscore_band: str | None,
    robust_zscore_band: str | None,
) -> str:
    levels = [
        level
        for level in (
            _band_level(percentile_band),
            _band_level(zscore_band),
            _band_level(robust_zscore_band),
        )
        if level is not None
    ]
    if len(levels) < 2:
        return "not_available"
    diff = max(levels) - min(levels)
    if diff == 0:
        return "none"
    if diff == 1:
        return "mild"
    return "material"


def _method_agreement(
    percentile_band: str | None,
    zscore_band: str | None,
    robust_zscore_band: str | None,
) -> str:
    levels = [
        level
        for level in (
            _band_level(percentile_band),
            _band_level(zscore_band),
            _band_level(robust_zscore_band),
        )
        if level is not None
    ]
    if len(levels) < 2:
        return "insufficient_methods"
    diff = max(levels) - min(levels)
    if diff == 0:
        return "all_available_aligned"
    if diff == 1:
        return "mostly_aligned"
    if diff == 2:
        return "mixed"
    return "divergent"


def _source_driver(source_badge: str | None) -> str | None:
    if source_badge == "official":
        return "official_source"
    if source_badge == "official_fallback":
        return "official_fallback_source"
    if source_badge == "unofficial_fallback":
        return "unofficial_fallback_source"
    if source_badge == "derived":
        return "derived_source"
    if source_badge == "proxy":
        return "proxy_source_auxiliary_only"
    if source_badge in {"missing", "research_needed", "search-derived"}:
        return "missing_input_blocked"
    return None


def _history_driver(history_quality_status: str | None) -> str | None:
    if history_quality_status == SUFFICIENT_HISTORY_STATUS:
        return "sufficient_5y_history"
    if history_quality_status == LIMITED_HISTORY_STATUS:
        return "limited_3y_history"
    if history_quality_status == INSUFFICIENT_HISTORY_STATUS:
        return "insufficient_history"
    return None


def _method_availability_drivers(
    percentile_band: str | None,
    zscore_band: str | None,
    robust_zscore_band: str | None,
    *,
    blocked: bool,
) -> list[str]:
    drivers: list[str] = []
    if percentile_band is not None:
        drivers.append("percentile_available")
    elif blocked:
        drivers.append("percentile_band_unavailable")
    else:
        drivers.append("percentile_unavailable")
    if zscore_band is not None:
        drivers.append("zscore_available")
    elif blocked:
        drivers.append("zscore_band_unavailable")
    else:
        drivers.append("zscore_unavailable_zero_std")
    if robust_zscore_band is not None:
        drivers.append("robust_zscore_available")
    elif blocked:
        drivers.append("robust_zscore_band_unavailable")
    else:
        drivers.append("robust_zscore_unavailable_zero_mad")
    return drivers


def _reliability_drivers(
    *,
    status: str,
    history_quality_status: str | None,
    latest_source_badge: str | None,
    trigger_eligibility: str,
    percentile_band: str | None,
    zscore_band: str | None,
    robust_zscore_band: str | None,
    divergence_band: str,
    blocked: bool,
    missing_reason: str | None,
) -> list[str]:
    drivers: set[str] = set()
    history_driver = _history_driver(history_quality_status)
    if history_driver is not None:
        drivers.add(history_driver)
    source_driver = _source_driver(latest_source_badge)
    if source_driver is not None:
        drivers.add(source_driver)
    drivers.update(
        _method_availability_drivers(
            percentile_band,
            zscore_band,
            robust_zscore_band,
            blocked=blocked,
        )
    )
    if divergence_band == "none":
        drivers.add("method_agreement")
    elif divergence_band in {"mild", "material"}:
        drivers.add("method_divergence")
    if status == "stale":
        drivers.add("stale_input_blocked")
    elif status == "missing":
        drivers.add("missing_input_blocked")
    elif status == "insufficient_history":
        drivers.add("insufficient_history_blocked")
    elif status == "not_available":
        drivers.add("normalization_method_unavailable_blocked")
    if missing_reason == "zscore_not_available_zero_std":
        drivers.add("zscore_unavailable_zero_std")
    elif missing_reason == "robust_zscore_not_available_zero_mad":
        drivers.add("robust_zscore_unavailable_zero_mad")
    if trigger_eligibility == "not_eligible" and not blocked:
        drivers.add("trigger_not_eligible")
    return sorted(drivers)


def _reliability_band(
    *,
    status: str,
    history_quality_status: str | None,
    latest_source_badge: str | None,
    methods: dict[str, bool],
    divergence_band: str,
) -> str:
    if status in BAD_STATUSES:
        return "insufficient"
    if history_quality_status not in {SUFFICIENT_HISTORY_STATUS, LIMITED_HISTORY_STATUS}:
        return "insufficient"
    if not any(methods.values()):
        return "insufficient"
    if latest_source_badge == "proxy":
        return "low"
    if divergence_band == "material":
        return "low"
    methods_unavailable = sum(1 for available in methods.values() if not available)
    if methods_unavailable >= 2:
        return "low"
    if history_quality_status == LIMITED_HISTORY_STATUS and divergence_band == "mild":
        return "low"
    if history_quality_status == LIMITED_HISTORY_STATUS:
        return "medium"
    if latest_source_badge == "unofficial_fallback":
        return "medium"
    if methods_unavailable >= 1:
        return "medium"
    if divergence_band == "mild":
        return "medium"
    return "high"


def _divergence_notes(
    *,
    divergence_band: str,
    method_agreement: str,
    percentile_band: str | None,
    zscore_band: str | None,
    robust_zscore_band: str | None,
) -> str:
    if divergence_band == "not_available":
        return (
            "fewer than two normalization methods available; divergence cannot be assessed"
        )
    if divergence_band == "none":
        return "percentile, z-score, and robust z-score bands align on the same broad level"
    parts = [
        f"percentile_band={percentile_band or 'unavailable'}",
        f"zscore_band={zscore_band or 'unavailable'}",
        f"robust_zscore_band={robust_zscore_band or 'unavailable'}",
    ]
    if divergence_band == "mild":
        return (
            "normalization methods differ by one broad level; explanation only, "
            "not a trading signal (" + ", ".join(parts) + ", agreement=" + method_agreement + ")"
        )
    return (
        "normalization methods disagree across major levels; downgrade explanation "
        "rather than escalate (" + ", ".join(parts) + ", agreement=" + method_agreement + ")"
    )


def _source_quality_note(
    source_badge: str | None,
    trigger_eligibility: str,
) -> str:
    return (
        f"latest input source_badge={source_badge or 'missing'}; "
        f"trigger_eligibility={trigger_eligibility}"
    )


def _history_window_note(
    lookback_window: str,
    history_quality_status: str | None,
    observation_count: int,
    minimum_observation_count: int,
) -> str:
    return (
        f"lookback_window={lookback_window}; "
        f"history_quality_status={history_quality_status}; "
        f"observation_count={observation_count}/{minimum_observation_count}"
    )


def _credit_oas_coverage_metadata(
    spec: PercentileMetricSpec,
    *,
    status: str,
    history_quality_status: str | None,
    observation_count: int,
    latest: dict[str, Any] | None,
    lookback: dict[str, Any] | None,
    percentile_band: str | None,
    zscore_band: str | None,
    robust_zscore_band: str | None,
) -> dict[str, Any]:
    diagnostics = _coverage_diagnostics(
        lookback=lookback,
        observation_count=observation_count,
    )
    current_level_available = _current_level_available(latest)
    return {
        "history_coverage_status": _history_coverage_status(
            source_metric_key=spec.source_metric_key,
            status=status,
            history_quality_status=history_quality_status,
            coverage_days=diagnostics["coverage_days"],
            days_short=diagnostics["days_short"],
        ),
        "provider_rebuild_status": _provider_rebuild_status(spec.source_metric_key),
        "normalization_availability": _normalization_availability(
            percentile_band=percentile_band,
            zscore_band=zscore_band,
            robust_zscore_band=robust_zscore_band,
            current_level_available=current_level_available,
            source_metric_key=spec.source_metric_key,
        ),
        "coverage_diagnostics": diagnostics,
        "credit_reference_role": _credit_reference_role(spec.source_metric_key),
        "substitution_policy": _substitution_policy(spec.source_metric_key),
        "long_history_reference_status": _long_history_reference_status(
            spec.source_metric_key
        ),
    }


def _history_coverage_status(
    *,
    source_metric_key: str,
    status: str,
    history_quality_status: str | None,
    coverage_days: int | None,
    days_short: int | None,
) -> str:
    if history_quality_status == SUFFICIENT_HISTORY_STATUS:
        return "sufficient_history"
    if history_quality_status == LIMITED_HISTORY_STATUS:
        return "limited_history"
    if (
        source_metric_key in PRIMARY_CREDIT_OAS_METRICS
        and coverage_days is not None
        and coverage_days < FALLBACK_WINDOW_DAYS
        and days_short is not None
        and 0 < days_short <= 7
    ):
        return "below_exact_gate"
    if status in BAD_STATUSES or history_quality_status == INSUFFICIENT_HISTORY_STATUS:
        return "insufficient_history"
    return "not_applicable"


def _provider_rebuild_status(source_metric_key: str) -> str:
    return CREDIT_OAS_PROVIDER_REBUILD_STATUS.get(source_metric_key, "not_applicable")


def _normalization_availability(
    *,
    percentile_band: str | None,
    zscore_band: str | None,
    robust_zscore_band: str | None,
    current_level_available: bool,
    source_metric_key: str,
) -> dict[str, bool]:
    return {
        "percentile_available": percentile_band is not None,
        "zscore_available": zscore_band is not None,
        "robust_zscore_available": robust_zscore_band is not None,
        "current_level_available": current_level_available,
        "long_history_reference_available": (
            source_metric_key in LONG_HISTORY_CREDIT_PROXY_REFERENCES
        ),
    }


def _coverage_diagnostics(
    *,
    lookback: dict[str, Any] | None,
    observation_count: int,
) -> dict[str, Any]:
    observations = (lookback or {}).get("observations") or []
    dates = sorted(
        {
            parsed
            for observation in observations
            for parsed in [_parse_date(observation.get("observation_date"))]
            if parsed is not None
        }
    )
    local_start = dates[0] if dates else _parse_date((lookback or {}).get("lookback_start"))
    local_end = dates[-1] if dates else _parse_date((lookback or {}).get("lookback_end"))
    coverage_days = (local_end - local_start).days if local_start and local_end else None
    days_short = (
        max(FALLBACK_WINDOW_DAYS - coverage_days, 0)
        if coverage_days is not None
        else None
    )
    return {
        "local_start": local_start.isoformat() if local_start else None,
        "local_end": local_end.isoformat() if local_end else None,
        "observation_count": observation_count,
        "distinct_dates": len(dates) if dates else None,
        "coverage_days": coverage_days,
        "required_days": FALLBACK_WINDOW_DAYS,
        "days_short": days_short,
        "provider_start_now": None,
        "provider_end_now": None,
    }


def _credit_reference_role(source_metric_key: str) -> str:
    if source_metric_key in PRIMARY_CREDIT_OAS_METRICS:
        return "primary_oas_series"
    if source_metric_key in LONG_HISTORY_CREDIT_PROXY_REFERENCES:
        return "long_history_credit_proxy_reference"
    return "non_credit_percentile_metric"


def _substitution_policy(source_metric_key: str) -> str:
    if source_metric_key in PRIMARY_CREDIT_OAS_METRICS:
        return "no_substitution"
    if source_metric_key in LONG_HISTORY_CREDIT_PROXY_REFERENCES:
        return "proxy_reference_not_oas_substitute"
    return "not_applicable"


def _long_history_reference_status(source_metric_key: str) -> str:
    if source_metric_key in PRIMARY_CREDIT_OAS_METRICS:
        return "unavailable_for_primary_series"
    if source_metric_key in LONG_HISTORY_CREDIT_PROXY_REFERENCES:
        return "available_proxy_reference"
    return "not_applicable"


def _current_level_available(latest: dict[str, Any] | None) -> bool:
    if latest is None:
        return False
    if latest.get("status") in market_history_store.BLOCKED_STATUSES:
        return False
    if latest.get("source_badge") in market_history_store.BLOCKED_SOURCE_BADGES:
        return False
    if latest.get("freshness_status") in BAD_FRESHNESS:
        return False
    if latest.get("value") is None and _to_float(latest.get("value_numeric")) is None:
        return False
    return True


def _reliability_metadata(
    *,
    status: str,
    history_quality_status: str | None,
    latest_source_badge: str | None,
    trigger_eligibility: str,
    percentile_band: str | None,
    zscore_band: str | None,
    robust_zscore_band: str | None,
    lookback_window: str,
    observation_count: int,
    minimum_observation_count: int,
    blocked: bool,
    missing_reason: str | None = None,
) -> dict[str, Any]:
    methods = _normalization_methods_available(
        percentile_band, zscore_band, robust_zscore_band
    )
    divergence_band = _divergence_band(
        percentile_band, zscore_band, robust_zscore_band
    )
    method_agreement = _method_agreement(
        percentile_band, zscore_band, robust_zscore_band
    )
    reliability_band = _reliability_band(
        status=status,
        history_quality_status=history_quality_status,
        latest_source_badge=latest_source_badge,
        methods=methods,
        divergence_band=divergence_band,
    )
    drivers = _reliability_drivers(
        status=status,
        history_quality_status=history_quality_status,
        latest_source_badge=latest_source_badge,
        trigger_eligibility=trigger_eligibility,
        percentile_band=percentile_band,
        zscore_band=zscore_band,
        robust_zscore_band=robust_zscore_band,
        divergence_band=divergence_band,
        blocked=blocked,
        missing_reason=missing_reason,
    )
    return {
        "reliability_band": reliability_band,
        "reliability_drivers": drivers,
        "divergence_band": divergence_band,
        "divergence_notes": _divergence_notes(
            divergence_band=divergence_band,
            method_agreement=method_agreement,
            percentile_band=percentile_band,
            zscore_band=zscore_band,
            robust_zscore_band=robust_zscore_band,
        ),
        "method_agreement": method_agreement,
        "normalization_methods_available": methods,
        "percentile_zscore_alignment": _alignment_label(
            _band_level(percentile_band), _band_level(zscore_band)
        ),
        "percentile_robust_zscore_alignment": _alignment_label(
            _band_level(percentile_band), _band_level(robust_zscore_band)
        ),
        "zscore_robust_zscore_alignment": _alignment_label(
            _band_level(zscore_band), _band_level(robust_zscore_band)
        ),
        "source_quality_note": _source_quality_note(
            latest_source_badge, trigger_eligibility
        ),
        "history_window_note": _history_window_note(
            lookback_window,
            history_quality_status,
            observation_count,
            minimum_observation_count,
        ),
    }
