from __future__ import annotations

from datetime import date
from typing import Any

from data_providers import market_history_store


FALLBACK_WINDOW_DAYS = 365 * 3
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
BROAD_BAND_LEVELS: dict[str | None, int] = {
    "low_extreme": -1,
    "normal": 0,
    "elevated": 1,
    "high": 2,
    "extreme": 3,
}


def build_reliability_metadata(
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


def build_credit_oas_coverage_metadata(
    spec: Any,
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
