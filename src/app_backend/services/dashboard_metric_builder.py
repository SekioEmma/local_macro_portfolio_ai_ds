from __future__ import annotations

from collections.abc import Callable
from typing import Any

from app_backend.schemas.responses import DashboardMetric
from app_backend.services.dashboard_evidence_policy import (
    AI_BLOCKED_METRIC_STATUSES,
    ai_context_allowed,
    missing_value_text,
)
from app_backend.services.dashboard_report_loader import ReportState
from app_backend.services.dashboard_summary_assembly import (
    contains_signal,
    first_updated_at,
    string_or_none,
)
from data_quality import official_macro_pack


ALLOWED_METRIC_STATUSES = {
    "ok",
    "watch",
    "pressure",
    "stress",
    "missing",
    "stale",
    "unknown",
    "research_needed",
    "insufficient_history",
    "not_available",
    "insufficient_evidence",
    "limited_evidence",
}
ALLOWED_SOURCE_BADGES = {
    "official",
    "official_fallback",
    "official_reference",
    "scraped_official_reference",
    "commercial_api_fallback",
    "unofficial_fallback",
    "proxy",
    "search-derived",
    "missing",
    "research_needed",
    "local",
    "derived",
}
SOURCE_BADGE_ALIASES = {
    "official_api": "official",
    "official_or_public_data_api": "official",
    "public_data_api": "official",
    "third_party_api": "proxy",
    "manual": "local",
    "cached_report": "derived",
}
INFLATION_YOY_METRIC_KEYS = {
    "core_cpi_yoy",
    "core_pce_yoy",
    "ppiaco_yoy",
    "ppi_final_demand_yoy",
}
INDEX_LEVEL_YOY_MISSING_REASON = (
    "Only index level is available; YoY requires historical comparison."
)


DerivedMetricBuilder = Callable[[str, tuple[ReportState, ...]], DashboardMetric | None]
PortfolioCompactMetricBuilder = Callable[..., DashboardMetric | None]
FindMetricBuilder = Callable[
    [str, tuple[ReportState, ...]],
    tuple[Any, dict[str, Any], ReportState] | None,
]


def build_metric(
    module_key: str,
    reports: tuple[ReportState, ...],
    spec: tuple[str, str, str | None, str, str],
    *,
    derived_metric: DerivedMetricBuilder,
    portfolio_compact_metric: PortfolioCompactMetricBuilder,
    find_metric_callback: FindMetricBuilder | None = None,
    derived_metric_keys: set[str],
    metric_aliases: dict[str, tuple[str, ...]],
    source_badge_aliases: dict[str, str],
    portfolio_compact_interpretation_hint: str,
    dgs30_breakout_missing_reason: str,
) -> DashboardMetric:
    metric_key, display_name, unit, format_kind, missing_status = spec
    derived = derived_metric(metric_key, reports)
    if derived is not None:
        return derived
    compact = portfolio_compact_metric(
        module_key=module_key,
        reports=reports,
        metric_key=metric_key,
        display_name=display_name,
        unit=unit,
        format_kind=format_kind,
    )
    if compact is not None:
        return compact

    found = (
        find_metric_callback(metric_key, reports)
        if find_metric_callback is not None
        else find_metric(metric_key, reports, metric_aliases=metric_aliases)
    )
    official_macro = official_macro_pack.get_official_macro_metric(metric_key)
    hint = interpretation_hint(
        metric_key,
        portfolio_compact_interpretation_hint=portfolio_compact_interpretation_hint,
    )
    if found is None:
        return missing_metric(
            metric_key=metric_key,
            display_name=display_name,
            unit=unit,
            status=official_macro.status_when_missing if official_macro else missing_status,
            generated_at=first_updated_at([report for report in reports if report.data is not None]),
            interpretation_hint=hint,
            source=official_macro.source if official_macro else None,
            source_badge=(
                official_macro.source_badge
                if official_macro and official_macro.source_badge == "research_needed"
                else None
            ),
            missing_reason=official_macro.missing_reason if official_macro else None,
            dgs30_breakout_missing_reason=dgs30_breakout_missing_reason,
        )

    value, payload, report = found
    hint = metric_interpretation_hint(
        metric_key,
        payload,
        portfolio_compact_interpretation_hint=portfolio_compact_interpretation_hint,
    )
    quality_metadata = metric_quality_metadata(report, metric_key) or first_metric_quality_metadata(reports, metric_key)
    status = metric_status(payload)
    if (
        official_macro
        and official_macro.source_series
        and status == "research_needed"
        and official_macro.status_when_missing != "research_needed"
    ):
        status = official_macro.status_when_missing
    freshness_status = metric_freshness(
        payload,
        report,
        metric_key=metric_key,
        quality_metadata=quality_metadata,
    )
    if freshness_status == "stale" and status == "ok":
        status = "stale"

    source = metric_source(payload, report, quality_metadata)
    source_series = metric_source_series(payload, quality_metadata, official_macro)
    source_badge = metric_source_badge(
        payload,
        report,
        module_key,
        metric_key,
        quality_metadata,
        derived_metric_keys=derived_metric_keys,
        source_badge_aliases=source_badge_aliases,
    )
    if (
        official_macro
        and official_macro.source_series
        and status in AI_BLOCKED_METRIC_STATUSES
        and status != "research_needed"
    ):
        source_badge = "missing"
    if official_macro and source is None and source_badge == "missing":
        source = official_macro.source
        source_badge = official_macro.source_badge
    if official_macro and source_badge == "missing":
        source_badge = official_macro.source_badge
    if official_macro and source is None:
        source = official_macro.source
    if (
        official_macro
        and official_macro.source_series
        and value is None
        and status in AI_BLOCKED_METRIC_STATUSES
        and status != "research_needed"
    ):
        source_badge = "missing"
    observation_date = metric_observation_date(payload, quality_metadata)
    generated_at = metric_generated_at(payload, report)
    missing_reason = string_or_none(payload.get("missing_reason")) if isinstance(payload, dict) else None
    yoy_result = normalize_inflation_yoy_value(metric_key, value, payload)
    if yoy_result == "index_level":
        return DashboardMetric(
            metric_key=metric_key,
            display_name=display_name,
            value=None,
            value_text=missing_value_text("insufficient_history"),
            unit=unit,
            status="insufficient_history",
            source=source,
            source_badge="missing",
            source_series=source_series,
            observation_date=None,
            generated_at=generated_at,
            freshness_status="insufficient_history",
            missing_reason=INDEX_LEVEL_YOY_MISSING_REASON,
            interpretation_hint=hint,
            ai_context_allowed=False,
        )
    if isinstance(yoy_result, float):
        value = yoy_result
    if official_macro and status in AI_BLOCKED_METRIC_STATUSES and missing_reason is None:
        missing_reason = official_macro.missing_reason

    return DashboardMetric(
        metric_key=metric_key,
        display_name=display_name,
        value=value,
        value_text=format_value(value, format_kind, status),
        unit=unit,
        status=status,
        source=source,
        source_badge=source_badge,
        source_series=source_series,
        observation_date=observation_date,
        generated_at=generated_at,
        freshness_status=freshness_status,
        missing_reason=missing_reason,
        interpretation_hint=hint,
        ai_context_allowed=ai_context_allowed(
            status=status,
            source=source,
            source_badge=source_badge,
            observation_date=observation_date,
            generated_at=generated_at,
            freshness_status=freshness_status,
            interpretation_hint=hint,
        )
        and not (
            metric_key in {"ppi_final_demand", "ppi_final_demand_yoy"}
            and not observation_date
        ),
    )


def missing_metric(
    *,
    metric_key: str,
    display_name: str,
    unit: str | None,
    status: str,
    generated_at: str | None,
    interpretation_hint: str | None = None,
    source: str | None = None,
    source_badge: str | None = None,
    missing_reason: str | None = None,
    dgs30_breakout_missing_reason: str,
) -> DashboardMetric:
    normalized_status = metric_status_value(status)
    normalized_source_badge = (
        source_badge
        if source_badge in ALLOWED_SOURCE_BADGES
        else "research_needed" if normalized_status == "research_needed" else "missing"
    )
    return DashboardMetric(
        metric_key=metric_key,
        display_name=display_name,
        value=None,
        value_text=missing_value_text(normalized_status),
        unit=unit,
        status=normalized_status,
        source=source,
        source_badge=normalized_source_badge,
        source_series=None,
        observation_date=None,
        generated_at=generated_at,
        freshness_status="unknown",
        missing_reason=missing_reason
        or (
            dgs30_breakout_missing_reason
            if metric_key == "dgs30_breakout_confirmed"
            else missing_value_text(normalized_status)
        ),
        interpretation_hint=interpretation_hint,
        ai_context_allowed=False,
    )


def find_metric(
    metric_key: str,
    reports: tuple[ReportState, ...],
    *,
    include_aliases: bool = True,
    metric_aliases: dict[str, tuple[str, ...]] | None = None,
) -> tuple[Any, dict[str, Any], ReportState] | None:
    metric_aliases = metric_aliases or {}
    metric_keys = (
        (metric_key, *metric_aliases.get(metric_key, ()), *official_macro_pack.aliases_for(metric_key))
        if include_aliases
        else (metric_key,)
    )
    for report in reports:
        if report.data is None:
            continue
        for key in metric_keys:
            found = find_metric_payload(report.data, key)
            if found is None:
                continue
            if key != metric_key and _alias_payload_unusable(found):
                continue
            value, payload = found
            return value, payload, report
    return None


def _alias_payload_unusable(found: tuple[Any, dict[str, Any]]) -> bool:
    value, payload = found
    if not isinstance(payload, dict):
        return value is None
    if "value" not in payload and "value_text" not in payload:
        return True
    return value is None


def find_metric_payload(value: Any, metric_key: str) -> tuple[Any, dict[str, Any]] | None:
    if isinstance(value, dict):
        for key, child in value.items():
            if str(key).lower() == metric_key.lower():
                if isinstance(child, dict):
                    child_value = _extract_metric_value(child)
                    return child_value, child
                return child, {"value": child}
        for child in value.values():
            found = find_metric_payload(child, metric_key)
            if found is not None:
                return found
    elif isinstance(value, list):
        for child in value:
            found = find_metric_payload(child, metric_key)
            if found is not None:
                return found
    return None


def _extract_metric_value(payload: dict[str, Any]) -> Any:
    if "value" in payload:
        return payload.get("value")
    for key in ("value", "value_text", "status", "label", "date", "updated_at"):
        if key in payload and payload.get(key) is not None:
            return payload.get(key)
    return None


def metric_status(payload: dict[str, Any]) -> str:
    return metric_status_value(payload.get("status") or "ok")


def metric_status_value(value: Any) -> str:
    status = str(value or "unknown").lower()
    return status if status in ALLOWED_METRIC_STATUSES else "unknown"


def metric_freshness(
    payload: dict[str, Any],
    report: ReportState,
    metric_key: str | None = None,
    quality_metadata: dict[str, Any] | None = None,
) -> str:
    freshness = payload.get("freshness_status")
    if freshness is None and isinstance(payload.get("freshness"), dict):
        freshness = payload["freshness"].get("freshness_status")
    if freshness is None and isinstance(payload.get("freshness"), str):
        freshness = payload.get("freshness")
    if freshness is None and quality_metadata:
        freshness = quality_metadata.get("freshness_status") or quality_metadata.get("freshness")
    if freshness is None and metric_key:
        quality = metric_quality_metadata(report, metric_key)
        freshness = quality.get("freshness_status") or quality.get("freshness")
    if freshness is None and metric_key == "holdings_updated_at" and isinstance(report.data, dict):
        freshness = report.data.get("holdings_freshness_status")
    if freshness is None and contains_signal(payload, ("stale_cache",)):
        freshness = "stale"
    if freshness is None and report.data is not None and contains_signal(report.data, ("stale_cache",)):
        freshness = "stale"
    return str(freshness or "unknown").lower()


def metric_source(
    payload: dict[str, Any],
    report: ReportState,
    quality_metadata: dict[str, Any] | None = None,
) -> str | None:
    source = payload.get("source")
    if source is None and isinstance(payload.get("metadata"), dict):
        source = payload["metadata"].get("source")
    if source is None and quality_metadata:
        source = quality_metadata.get("source") or quality_metadata.get("provider")
    if source is None and isinstance(report.data, dict):
        source = report.data.get("source")
    if source is None and report.name == "portfolio_snapshot":
        source = "local"
    return string_or_none(source)


def metric_source_series(
    payload: dict[str, Any],
    quality_metadata: dict[str, Any] | None = None,
    official_macro: official_macro_pack.OfficialMacroMetric | None = None,
) -> str | None:
    source_series = payload.get("source_series")
    if source_series is None and isinstance(payload.get("metadata"), dict):
        source_series = payload["metadata"].get("source_series")
    if source_series is None and quality_metadata:
        source_series = quality_metadata.get("source_series")
    if source_series is None and official_macro:
        source_series = official_macro.source_series
    text = string_or_none(source_series)
    if text and ":" in text:
        return text.split(":")[-1]
    return text


def metric_source_badge(
    payload: dict[str, Any],
    report: ReportState,
    module_key: str,
    metric_key: str | None = None,
    quality_metadata: dict[str, Any] | None = None,
    *,
    derived_metric_keys: set[str],
    source_badge_aliases: dict[str, str] | None = None,
) -> str:
    if module_key == "portfolio_deviation":
        return "local"
    if metric_key in derived_metric_keys and (
        payload.get("source_series") is not None
        or payload.get("derived_from") is not None
        or metric_key in {"dgs10_5d_avg", "dgs30_distance_to_5pct", "nasdaq_vs_sp500_30d"}
    ):
        return "derived"
    badge = payload.get("source_badge") or payload.get("source_tier")
    if badge is None and isinstance(payload.get("freshness"), dict):
        badge = payload["freshness"].get("source_tier")
    if badge is None and quality_metadata:
        badge = quality_metadata.get("source_badge") or quality_metadata.get("source_tier")
    if badge is None and isinstance(report.data, dict):
        badge = report.data.get("source_badge") or report.data.get("source_tier")
    badge_text = str(badge or "missing").lower()
    badge_text = (source_badge_aliases or SOURCE_BADGE_ALIASES).get(badge_text, badge_text)
    if badge_text in {
        "official",
        "official_fallback",
        "official_reference",
        "scraped_official_reference",
        "commercial_api_fallback",
        "unofficial_fallback",
        "proxy",
        "search-derived",
    }:
        return badge_text
    return badge_text if badge_text in ALLOWED_SOURCE_BADGES else "missing"


def metric_observation_date(
    payload: dict[str, Any],
    quality_metadata: dict[str, Any] | None = None,
) -> str | None:
    return string_or_none(
        payload.get("observation_date")
        or payload.get("date")
        or payload.get("updated_at")
        or (quality_metadata or {}).get("observation_date")
    )


def metric_generated_at(payload: dict[str, Any], report: ReportState) -> str | None:
    if payload.get("generated_at") is not None:
        return string_or_none(payload.get("generated_at"))
    if isinstance(report.data, dict):
        return string_or_none(report.data.get("generated_at") or report.data.get("updated_at"))
    return None


def metric_quality_metadata(report: ReportState, metric_key: str) -> dict[str, Any]:
    if not isinstance(report.data, dict):
        return {}
    data_quality = report.data.get("data_quality")
    if isinstance(data_quality, dict):
        market_quality = data_quality.get("market_data_quality")
        if isinstance(market_quality, dict) and isinstance(market_quality.get(metric_key), dict):
            return market_quality[metric_key]
    if report.name == "portfolio_snapshot" and metric_key == "holdings_updated_at":
        return {
            "source": "local",
            "source_badge": "local",
            "observation_date": report.data.get("holdings_updated_at"),
            "freshness_status": report.data.get("holdings_freshness_status"),
        }
    return {}


def first_metric_quality_metadata(
    reports: tuple[ReportState | None, ...],
    metric_key: str,
) -> dict[str, Any]:
    for report in reports:
        if report is None:
            continue
        metadata = metric_quality_metadata(report, metric_key)
        if metadata:
            return metadata
    return {}


def format_value(value: Any, format_kind: str, status: str) -> str:
    if status in {"missing", "research_needed", "insufficient_history", "not_available"}:
        return missing_value_text(status)
    if status == "stale" and value is None:
        return "stale"
    if value is None:
        return "missing"
    if format_kind == "bool":
        if isinstance(value, bool):
            return "true" if value else "false"
        return "unknown"
    if format_kind == "percent":
        number = to_float(value)
        return f"{number:.2f}%" if isinstance(number, float) else str(value)
    if format_kind == "signed_percent":
        number = to_float(value)
        return f"{number:+.2f}%" if isinstance(number, float) else str(value)
    if format_kind == "pp":
        number = to_float(value)
        return f"{number:+.2f}pp" if isinstance(number, float) else str(value)
    if format_kind == "number":
        number = to_float(value)
        if isinstance(number, float):
            return f"{number:,.0f}" if number.is_integer() else f"{number:,.1f}"
        return str(value)
    return str(value)


def normalize_inflation_yoy_value(
    metric_key: str,
    value: Any,
    payload: dict[str, Any],
) -> float | str | None:
    if metric_key not in INFLATION_YOY_METRIC_KEYS:
        return None
    number = to_float(value)
    if number is None:
        return None
    if payload_declares_index_level(payload) or abs(number) > 50.0:
        return "index_level"
    if -1.0 < number < 1.0 and number != 0.0:
        return round(number * 100.0, 6)
    return number


def payload_declares_index_level(payload: dict[str, Any]) -> bool:
    for key in ("value_type", "metric_kind", "calculation", "unit"):
        text = str(payload.get(key) or "").lower()
        if "index" in text and "yoy" not in text and "year" not in text:
            return True
    metadata = payload.get("metadata")
    if isinstance(metadata, dict):
        return payload_declares_index_level(metadata)
    return False


def to_float(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value.strip().replace("%", ""))
        except ValueError:
            return None
    return None


def interpretation_hint(
    metric_key: str,
    *,
    portfolio_compact_interpretation_hint: str,
) -> str | None:
    official_macro = official_macro_pack.get_official_macro_metric(metric_key)
    if official_macro is not None:
        return official_macro.interpretation_hint
    if metric_key in {"dgs10", "dgs10_5d_avg", "dgs30_distance_to_5pct"}:
        return "FRED Treasury yield series are daily, not intraday."
    if metric_key == "dgs30_breakout_confirmed":
        return "Breakout confirmation requires explicit compact evidence; do not infer it."
    if metric_key == "ppiaco_yoy":
        return "PPIACO is not final demand PPI."
    if metric_key in {
        "max_deviation_asset",
        "max_deviation_pp",
        "equity_total_deviation_pp",
        "cash_reserve_status",
    }:
        return portfolio_compact_interpretation_hint
    return None


def metric_interpretation_hint(
    metric_key: str,
    payload: dict[str, Any],
    *,
    portfolio_compact_interpretation_hint: str,
) -> str | None:
    hint = string_or_none(payload.get("interpretation_hint"))
    if metric_key == "ppiaco_yoy" and hint:
        if "final demand" not in hint.lower():
            return f"{hint} PPIACO is not final demand PPI."
        return hint
    if metric_key in {"ppi_final_demand", "ppi_final_demand_yoy"} and hint:
        text = hint.lower()
        if "ppiaco" not in text or "consensus" not in text:
            return (
                f"{hint} PPI Final Demand is distinct from PPIACO and must not be "
                "described as above or below consensus without consensus data."
            )
        return hint
    return hint or interpretation_hint(
        metric_key,
        portfolio_compact_interpretation_hint=portfolio_compact_interpretation_hint,
    )


def dependency_unusable(found: tuple[Any, dict[str, Any], ReportState]) -> bool:
    value, payload, report = found
    status = metric_status(payload)
    freshness = metric_freshness(payload, report)
    if status in AI_BLOCKED_METRIC_STATUSES:
        return True
    if freshness in {"missing", "insufficient_history", "stale"}:
        return True
    return value is None
