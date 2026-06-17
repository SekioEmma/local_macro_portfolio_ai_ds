from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any

from app_backend.schemas.responses import DashboardMetric
from app_backend.services.dashboard_evidence_policy import (
    AI_BLOCKED_FRESHNESS_STATUSES,
    ai_context_allowed,
)
from app_backend.services.dashboard_metric_builder import (
    dependency_unusable,
    find_metric,
    first_metric_quality_metadata,
    format_value,
    metric_freshness,
    metric_generated_at,
    metric_observation_date,
    metric_quality_metadata,
    metric_source,
    metric_source_badge,
    metric_source_series,
    to_float,
)
from app_backend.services.dashboard_report_loader import ReportState
from app_backend.services.dashboard_summary_assembly import (
    first_updated_at,
    string_or_none,
)
from data_providers import market_history_store
from data_quality import historical_derived_metrics, official_macro_pack


EQUITY_HISTORICAL_DERIVED_METRIC_KEYS = {
    "sp500_30d_return",
    "sp500_60d_return",
    "nasdaq100_30d_return",
    "nasdaq100_60d_return",
    "nasdaq_vs_sp500_30d",
}
OIL_HISTORICAL_DERIVED_METRIC_KEYS = {
    "wti_30d_change",
    "brent_30d_change",
}
PPI_FINAL_DEMAND_HISTORICAL_DERIVED_METRIC_KEYS = {
    "ppi_final_demand_yoy",
}
PROXY_BREADTH_HISTORICAL_DERIVED_METRIC_KEYS = {
    "spy_proxy_30d_return",
    "spy_proxy_60d_return",
    "rsp_proxy_30d_return",
    "rsp_proxy_60d_return",
    "qqq_proxy_30d_return",
    "qqq_proxy_60d_return",
    "spy_vs_rsp_30d",
    "spy_vs_rsp_60d",
    "qqq_vs_spy_30d",
    "qqq_vs_spy_60d",
    "hyg_vs_lqd_30d",
    "hyg_vs_lqd_60d",
}
MARKET_STRESS_HISTORICAL_DERIVED_METRIC_KEYS = {
    "sp500_drawdown_3m",
    "sp500_drawdown_6m",
    "nasdaq100_drawdown_3m",
    "nasdaq100_drawdown_6m",
    "dgs10_dgs2_curve_slope",
    "dgs30_dgs10_curve_slope",
    "tlt_proxy_30d_return",
    "gld_proxy_30d_return",
    "shy_proxy_30d_return",
    "tlt_vs_shy_30d",
}
LABOR_HISTORICAL_DERIVED_METRIC_KEYS = {
    "unemployment_rate_3m_avg",
    "unemployment_rate_12m_low_gap",
    "initial_claims_4w_avg",
    "continuing_claims_4w_avg",
    "sahm_rule_proxy_status",
    "labor_deterioration_status",
}
EQUITY_HISTORICAL_DERIVED_HINT_SUFFIX = (
    " Derived from local market history; underlying source includes yfinance "
    "unofficial_fallback/proxy observations in the market history store; not an "
    "official market breadth or valuation measure."
)
OIL_HISTORICAL_DERIVED_HINT_SUFFIX = (
    " Derived from official FRED/EIA daily oil history in local market history; "
    "this remains a derived energy-pressure input, not a real-time oil quote, "
    "inflation forecast, or commodity trading signal."
)


def apply_historical_derived_metrics(
    metrics: list[DashboardMetric],
    *,
    module_key: str,
    metric_keys: set[str],
    hint_suffix: str,
    fallback_source: str,
    fallback_observations: dict[str, dict[str, Any]] | None = None,
    required_dependency_source_badges: set[str] | None = None,
    replace_existing: bool = False,
    db_path: Path | str | None = None,
    default_market_history_db_path: Path | str | None = None,
) -> list[DashboardMetric]:
    target_db_path = db_path if db_path is not None else default_market_history_db_path
    candidates = {
        item.metric_key: item
        for item in historical_derived_metrics.build_historical_dashboard_candidates(
            db_path=target_db_path,
            fallback_observations=fallback_observations,
        ).get(module_key, [])
        if item.metric_key in metric_keys
    }
    return [
        historical_derived_metric(
            metric,
            candidates.get(metric.metric_key),
            metric_keys=metric_keys,
            hint_suffix=hint_suffix,
            fallback_source=fallback_source,
            required_dependency_source_badges=required_dependency_source_badges,
            replace_existing=replace_existing,
        )
        for metric in metrics
    ]


def apply_ppi_final_demand_history(
    metrics: list[DashboardMetric],
    *,
    db_path: Path | str | None = None,
    default_market_history_db_path: Path | str | None = None,
) -> list[DashboardMetric]:
    target_db_path = db_path if db_path is not None else default_market_history_db_path
    latest = latest_ppifis_observation(target_db_path)
    if latest is None:
        return metrics
    return [
        ppi_final_demand_history_metric(metric, latest)
        if metric.metric_key == "ppi_final_demand"
        else metric
        for metric in metrics
    ]


def apply_labor_history_fallback(
    metrics: list[DashboardMetric],
    *,
    db_path: Path | str | None = None,
    default_market_history_db_path: Path | str | None = None,
) -> list[DashboardMetric]:
    target_db_path = db_path if db_path is not None else default_market_history_db_path
    latest_by_key = {
        metric.metric_key: latest_official_labor_observation(metric.metric_key, target_db_path)
        for metric in metrics
        if is_labor_official_metric(metric.metric_key)
    }
    return [
        labor_history_metric(metric, latest_by_key.get(metric.metric_key))
        if labor_history_fallback_needed(metric, latest_by_key.get(metric.metric_key))
        else metric
        for metric in metrics
    ]


def is_labor_official_metric(metric_key: str) -> bool:
    official_macro = official_macro_pack.get_official_macro_metric(metric_key)
    return bool(
        official_macro
        and official_macro.module == "labor_macro"
        and official_macro.source_series
    )


def labor_history_fallback_needed(
    metric: DashboardMetric,
    observation: dict[str, Any] | None,
) -> bool:
    if observation is None:
        return False
    if metric.status != "ok" or metric.value is None:
        return True
    if metric.freshness_status in AI_BLOCKED_FRESHNESS_STATUSES:
        return True
    if not metric.observation_date:
        return True
    if not metric.generated_at:
        return True
    if metric.source_badge != "official":
        return True
    return False


def latest_official_labor_observation(
    metric_key: str,
    db_path: Path | str | None,
) -> dict[str, Any] | None:
    official_macro = official_macro_pack.get_official_macro_metric(metric_key)
    if official_macro is None or official_macro.module != "labor_macro":
        return None
    rows = market_history_store.list_market_observations(
        metric_key=metric_key,
        limit=100,
        db_path=db_path,
    )
    for row in rows:
        if row.get("status") != "ok":
            continue
        if row.get("source_badge") != "official":
            continue
        if row.get("provider") != "FRED":
            continue
        if row.get("source_series") != official_macro.source_series:
            continue
        if row.get("value_numeric") is None:
            continue
        return row
    return None


def labor_history_metric(
    original: DashboardMetric,
    observation: dict[str, Any] | None,
) -> DashboardMetric:
    if observation is None:
        return original
    official_macro = official_macro_pack.get_official_macro_metric(original.metric_key)
    if official_macro is None:
        return original
    value = float(observation["value_numeric"])
    observation_date = string_or_none(observation.get("observation_date"))
    generated_at = string_or_none(observation.get("generated_at"))
    fetched_at = string_or_none(observation.get("fetched_at"))
    freshness_status = labor_history_freshness_status(
        official_macro,
        observation_date=observation_date,
        stored_freshness=string_or_none(observation.get("freshness_status")),
    )
    status = "stale" if freshness_status == "stale" else "ok"
    interpretation_hint = official_macro.interpretation_hint
    ai_allowed = bool(observation.get("ai_context_allowed")) and ai_context_allowed(
        status=status,
        source="FRED",
        source_badge="official",
        observation_date=observation_date,
        generated_at=generated_at or fetched_at,
        freshness_status=freshness_status,
        interpretation_hint=interpretation_hint,
    )
    return DashboardMetric(
        metric_key=original.metric_key,
        display_name=original.display_name,
        value=value,
        value_text=format_value(value, "number" if original.unit != "percent" else "percent", status),
        unit=original.unit,
        status=status,
        source="FRED",
        source_badge="official",
        source_series=official_macro.source_series,
        observation_date=observation_date,
        generated_at=generated_at or fetched_at,
        freshness_status=freshness_status,
        missing_reason=None,
        interpretation_hint=interpretation_hint,
        ai_context_allowed=ai_allowed,
    )


def labor_history_freshness_status(
    official_macro: official_macro_pack.OfficialMacroMetric,
    *,
    observation_date: str | None,
    stored_freshness: str | None,
) -> str:
    parsed_date = parse_iso_date(observation_date)
    if parsed_date is None:
        return stored_freshness or "unknown"
    max_stale_days = 21 if official_macro.expected_frequency == "weekly" else 75
    if (date.today() - parsed_date).days > max_stale_days:
        return "stale"
    if stored_freshness and stored_freshness not in AI_BLOCKED_FRESHNESS_STATUSES:
        return stored_freshness
    return "historical"


def parse_iso_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(value[:10])
    except ValueError:
        return None


def latest_ppifis_observation(db_path: Path | str | None) -> dict[str, Any] | None:
    rows = market_history_store.list_market_observations(
        metric_key="ppi_final_demand",
        limit=100,
        db_path=db_path,
    )
    for row in rows:
        if row.get("status") != "ok":
            continue
        if row.get("source_badge") != "official":
            continue
        if row.get("provider") != "FRED":
            continue
        if row.get("source_series") != "PPIFIS":
            continue
        if row.get("value_numeric") is None:
            continue
        return row
    return None


def ppi_final_demand_history_metric(
    original: DashboardMetric,
    observation: dict[str, Any],
) -> DashboardMetric:
    official_macro = official_macro_pack.get_official_macro_metric("ppi_final_demand")
    interpretation_hint = (
        official_macro.interpretation_hint
        if official_macro
        else (
            "PPI Final Demand is the official headline final demand PPI index relayed "
            "by FRED PPIFIS; it is distinct from PPIACO and not consensus surprise data."
        )
    )
    value = float(observation["value_numeric"])
    generated_at = string_or_none(observation.get("generated_at"))
    freshness_status = str(observation.get("freshness_status") or "historical")
    ai_allowed = bool(observation.get("ai_context_allowed")) and ai_context_allowed(
        status="ok",
        source="FRED",
        source_badge="official",
        observation_date=string_or_none(observation.get("observation_date")),
        generated_at=generated_at,
        freshness_status=freshness_status,
        interpretation_hint=interpretation_hint,
    )
    return DashboardMetric(
        metric_key=original.metric_key,
        display_name=original.display_name,
        value=value,
        value_text=format_value(value, "number", "ok"),
        unit=original.unit,
        status="ok",
        source="FRED",
        source_badge="official",
        source_series="PPIFIS",
        observation_date=string_or_none(observation.get("observation_date")),
        generated_at=generated_at,
        freshness_status=freshness_status,
        missing_reason=None,
        interpretation_hint=interpretation_hint,
        ai_context_allowed=ai_allowed,
    )


def historical_derived_metric(
    original: DashboardMetric,
    candidate: historical_derived_metrics.HistoricalDerivedMetric | None,
    *,
    metric_keys: set[str],
    hint_suffix: str,
    fallback_source: str,
    required_dependency_source_badges: set[str] | None,
    replace_existing: bool,
) -> DashboardMetric:
    if original.metric_key not in metric_keys:
        return original
    if original.status != "insufficient_history" and not replace_existing:
        return original
    if candidate is None:
        return original
    if candidate.status in {"missing", "insufficient_history"}:
        if original.metric_key != "labor_deterioration_status":
            return original
        return DashboardMetric(
            metric_key=original.metric_key,
            display_name=original.display_name,
            value=None,
            value_text=candidate.value_text,
            unit=original.unit,
            status=candidate.status,
            source=fallback_source,
            source_badge="derived",
            source_series=", ".join(candidate.dependency_source_series or []) or None,
            observation_date=candidate.observation_date,
            generated_at=candidate.generated_at,
            freshness_status=candidate.freshness_status,
            missing_reason=candidate.missing_reason,
            interpretation_hint=candidate.interpretation_hint,
            ai_context_allowed=False,
        )
    if candidate.status not in {"ok", "watch", "pressure"} or candidate.value is None:
        return original
    if required_dependency_source_badges is not None:
        source_badges = set(candidate.dependency_source_badges or [])
        if not source_badges or not source_badges.issubset(required_dependency_source_badges):
            return original
    value = dashboard_historical_derived_value(candidate)
    hint = dashboard_historical_derived_hint(candidate, hint_suffix=hint_suffix)
    ai_allowed = bool(candidate.ai_context_allowed) and ai_context_allowed(
        status=candidate.status,
        source=fallback_source,
        source_badge="derived",
        observation_date=candidate.observation_date,
        generated_at=candidate.generated_at,
        freshness_status=candidate.freshness_status,
        interpretation_hint=hint,
    )
    return DashboardMetric(
        metric_key=original.metric_key,
        display_name=original.display_name,
        value=value,
        value_text=format_historical_derived_value(value, candidate.unit),
        unit=original.unit,
        status="ok",
        source=fallback_source,
        source_badge="derived",
        source_series=", ".join(candidate.dependency_source_series or []) or None,
        observation_date=candidate.observation_date,
        generated_at=candidate.generated_at,
        freshness_status=candidate.freshness_status,
        missing_reason=None,
        interpretation_hint=hint,
        ai_context_allowed=ai_allowed,
    )


def compact_dgs_fallback_observations(
    reports: tuple[ReportState, ...],
    *,
    metric_aliases: dict[str, tuple[str, ...]],
    derived_metric_keys: set[str],
    source_badge_aliases: dict[str, str],
) -> dict[str, dict[str, Any]]:
    observations: dict[str, dict[str, Any]] = {}
    for metric_key in ("dgs2", "dgs10", "dgs30"):
        found = find_metric(metric_key, reports, metric_aliases=metric_aliases)
        if found is None:
            continue
        value, payload, report = found
        quality_metadata = metric_quality_metadata(report, metric_key) or first_metric_quality_metadata(reports, metric_key)
        official_macro = official_macro_pack.get_official_macro_metric(metric_key)
        numeric_value = to_float(value)
        source_badge = metric_source_badge(
            payload,
            report,
            "rate_pressure",
            metric_key,
            quality_metadata,
            derived_metric_keys=derived_metric_keys,
            source_badge_aliases=source_badge_aliases,
        )
        source_series = metric_source_series(payload, quality_metadata, official_macro=official_macro)
        if source_series is None and source_badge == "official" and metric_key in {"dgs2", "dgs10", "dgs30"}:
            source_series = metric_key.upper()
        observations[metric_key] = {
            "value": numeric_value if isinstance(numeric_value, float) else None,
            "source": metric_source(payload, report, quality_metadata),
            "source_badge": source_badge,
            "source_series": source_series,
            "observation_date": metric_observation_date(payload, quality_metadata),
            "generated_at": metric_generated_at(payload, report),
            "freshness_status": metric_freshness(
                payload,
                report,
                metric_key=metric_key,
                quality_metadata=quality_metadata,
            ),
            "ai_context_allowed": not dependency_unusable(found),
        }
    return observations


def dashboard_historical_derived_value(
    candidate: historical_derived_metrics.HistoricalDerivedMetric,
) -> float | str | bool:
    if isinstance(candidate.value, (str, bool)):
        return candidate.value
    value = float(candidate.value)
    if candidate.unit in {"percent", "pp"}:
        return value * 100.0
    return value


def format_historical_derived_value(value: float | str | bool, unit: str | None) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, str):
        return value
    if unit == "percent":
        return f"{value:+.2f}%"
    if unit == "pp":
        return f"{value:+.2f}pp"
    if unit == "raw_pp":
        return f"{value:+.2f}pp"
    if unit == "raw_percent":
        return f"{value:.2f}%"
    if unit == "claims":
        return f"{value:,.0f}"
    return f"{value:.4g}"


def dashboard_historical_derived_hint(
    candidate: historical_derived_metrics.HistoricalDerivedMetric,
    *,
    hint_suffix: str,
) -> str:
    base = (candidate.interpretation_hint or "").strip()
    return (base + hint_suffix).strip()


def equity_historical_derived_metrics_available(
    metrics: list[DashboardMetric],
) -> bool:
    return all(
        any(item.metric_key == metric_key and item.status == "ok" for item in metrics)
        for metric_key in EQUITY_HISTORICAL_DERIVED_METRIC_KEYS
    )
