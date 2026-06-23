from __future__ import annotations

from typing import Any

from app_backend.schemas.responses import DashboardMetric
from app_backend.services.dashboard_evidence_policy import (
    ai_context_allowed,
    missing_value_text,
)
from app_backend.services.dashboard_metric_catalog import (
    DGS30_BREAKOUT_MISSING_REASON,
    METRIC_ALIASES,
)
from app_backend.services.dashboard_metric_builder import (
    dependency_unusable,
    find_metric,
    format_value,
    metric_freshness,
    metric_generated_at,
    metric_observation_date,
    metric_source,
    metric_source_series,
    metric_status_value,
    to_float,
)
from app_backend.services.dashboard_report_loader import ReportState
from app_backend.services.dashboard_summary_assembly import first_updated_at


def derived_metric(
    metric_key: str,
    reports: tuple[ReportState, ...],
    *,
    metric_aliases: dict[str, tuple[str, ...]] = METRIC_ALIASES,
    dgs30_breakout_missing_reason: str = DGS30_BREAKOUT_MISSING_REASON,
) -> DashboardMetric | None:
    if metric_key == "credit_stress_status":
        if find_metric(
            "credit_stress_status",
            reports,
            include_aliases=False,
            metric_aliases=metric_aliases,
        ) is not None:
            return None
        return credit_stress_status_metric(reports, metric_aliases=metric_aliases)
    if metric_key == "real_yield_pressure_status":
        if find_metric(
            "real_yield_pressure_status",
            reports,
            include_aliases=False,
            metric_aliases=metric_aliases,
        ) is not None:
            return None
        return real_yield_pressure_status_metric(reports, metric_aliases=metric_aliases)
    if metric_key == "dgs30_distance_to_5pct":
        found = find_metric("dgs30", reports, metric_aliases=metric_aliases)
        if found is None or dependency_unusable(found):
            return blocked_dependency_metric(
                metric_key="dgs30_distance_to_5pct",
                display_name="30Y distance to 5%",
                unit="pp",
                status="missing",
                missing_reason="DGS30 is missing; distance to 5% cannot be calculated.",
                generated_at=first_updated_at([report for report in reports if report.data is not None]),
                interpretation_hint="Distance requires daily DGS30 compact evidence.",
            )
        dgs30_value = to_float(found[0])
        if not isinstance(dgs30_value, float):
            return blocked_dependency_metric(
                metric_key="dgs30_distance_to_5pct",
                display_name="30Y distance to 5%",
                unit="pp",
                status="missing",
                missing_reason="DGS30 is missing; distance to 5% cannot be calculated.",
                generated_at=first_updated_at([report for report in reports if report.data is not None]),
                interpretation_hint="Distance requires numeric daily DGS30 compact evidence.",
            )
        value = round(dgs30_value - 5.0, 4)
        return derived_metric_response(
            metric_key,
            "30Y distance to 5%",
            value,
            "pp",
            "pp",
            found,
            "Distance is derived from daily DGS30; it is not intraday.",
        )
    if metric_key == "dgs30_breakout_confirmed":
        found = find_metric("dgs30_breakout_confirmed", reports, metric_aliases=metric_aliases)
        if found is None:
            return blocked_dependency_metric(
                metric_key="dgs30_breakout_confirmed",
                display_name="30Y breakout confirmed",
                unit=None,
                status="research_needed",
                missing_reason=dgs30_breakout_missing_reason,
                generated_at=first_updated_at([report for report in reports if report.data is not None]),
                interpretation_hint="Breakout confirmation requires explicit compact evidence; do not infer it.",
            )
        dgs30 = find_metric("dgs30", reports, metric_aliases=metric_aliases)
        if dgs30 is None or dependency_unusable(dgs30):
            return blocked_dependency_metric(
                metric_key="dgs30_breakout_confirmed",
                display_name="30Y breakout confirmed",
                unit=None,
                status="missing",
                missing_reason="DGS30 is missing; breakout confirmation cannot be evaluated.",
                generated_at=first_updated_at([report for report in reports if report.data is not None]),
                interpretation_hint="Breakout confirmation requires DGS30 and explicit compact history evidence.",
            )
        _, payload, report = found
        if dependency_unusable(found):
            return None
        if not has_breakout_history_evidence(payload):
            return blocked_dependency_metric(
                metric_key="dgs30_breakout_confirmed",
                display_name="30Y breakout confirmed",
                unit=None,
                status="insufficient_history",
                missing_reason="DGS30 breakout confirmation requires compact history window evidence.",
                generated_at=metric_generated_at(payload, report),
                interpretation_hint="Breakout confirmation requires explicit compact evidence; do not infer it.",
            )
    if metric_key == "nasdaq_vs_sp500_30d":
        nasdaq = find_metric("nasdaq100_30d_return", reports, metric_aliases=metric_aliases)
        sp500 = find_metric("sp500_30d_return", reports, metric_aliases=metric_aliases)
        if nasdaq is None or sp500 is None or dependency_unusable(nasdaq) or dependency_unusable(sp500):
            return blocked_dependency_metric(
                metric_key="nasdaq_vs_sp500_30d",
                display_name="Nasdaq vs S&P 500 30D",
                unit="pp",
                status="insufficient_history",
                missing_reason="S&P 500 and Nasdaq 100 30D returns are both required.",
                generated_at=first_updated_at([report for report in reports if report.data is not None]),
                interpretation_hint="Derived spread requires both compact 30D return metrics.",
            )
        nasdaq_value = to_float(nasdaq[0])
        sp500_value = to_float(sp500[0])
        if not isinstance(nasdaq_value, float) or not isinstance(sp500_value, float):
            return blocked_dependency_metric(
                metric_key="nasdaq_vs_sp500_30d",
                display_name="Nasdaq vs S&P 500 30D",
                unit="pp",
                status="insufficient_history",
                missing_reason="S&P 500 and Nasdaq 100 30D returns must both be numeric.",
                generated_at=first_updated_at([report for report in reports if report.data is not None]),
                interpretation_hint="Derived spread requires numeric compact 30D return metrics.",
            )
        value = round(nasdaq_value - sp500_value, 4)
        return derived_metric_response(
            metric_key,
            "Nasdaq vs S&P 500 30D",
            value,
            "pp",
            "pp",
            nasdaq,
            "Derived spread between compact 30D return metrics.",
        )
    return None


def credit_stress_status_metric(
    reports: tuple[ReportState, ...],
    *,
    metric_aliases: dict[str, tuple[str, ...]] = METRIC_ALIASES,
) -> DashboardMetric:
    high_yield = usable_numeric_metric("high_yield_spread", reports, metric_aliases=metric_aliases)
    investment_grade = usable_numeric_metric("investment_grade_spread", reports, metric_aliases=metric_aliases)
    vix = usable_numeric_metric("vix", reports, metric_aliases=metric_aliases)
    generated_at = latest_metric_timestamp(
        [item for item in (high_yield, investment_grade, vix) if item is not None]
    ) or first_updated_at([report for report in reports if report.data is not None])
    observation_date = latest_metric_observation_date(
        [item for item in (high_yield, investment_grade, vix) if item is not None]
    )
    hint = (
        "Derived from available credit spread evidence plus VIX. VIX alone is not "
        "sufficient to infer systemic credit stress or crisis."
    )

    if high_yield is None and investment_grade is None:
        return blocked_dependency_metric(
            metric_key="credit_stress_status",
            display_name="Credit stress status",
            unit=None,
            status="unknown" if vix is not None else "missing",
            missing_reason=(
                "Credit spread evidence is missing; VIX alone is not sufficient "
                "to classify credit stress."
            ),
            generated_at=generated_at,
            interpretation_hint=hint,
        )

    high_yield_value = high_yield[0] if high_yield else None
    investment_grade_value = investment_grade[0] if investment_grade else None
    vix_value = vix[0] if vix else None
    status, value, missing_reason = credit_status_from_values(
        high_yield=high_yield_value,
        investment_grade=investment_grade_value,
        vix=vix_value,
    )
    return DashboardMetric(
        metric_key="credit_stress_status",
        display_name="Credit stress status",
        value=value,
        value_text=format_value(value, "text", status),
        unit=None,
        status=status,
        source="dashboard_compact",
        source_badge="derived",
        observation_date=observation_date,
        generated_at=generated_at,
        freshness_status="fresh" if observation_date or generated_at else "unknown",
        missing_reason=missing_reason,
        interpretation_hint=hint,
        ai_context_allowed=ai_context_allowed(
            status=status,
            source="dashboard_compact",
            source_badge="derived",
            observation_date=observation_date,
            generated_at=generated_at,
            freshness_status="fresh" if observation_date or generated_at else "unknown",
            interpretation_hint=hint,
        ),
    )


def credit_status_from_values(
    *,
    high_yield: float | None,
    investment_grade: float | None,
    vix: float | None,
) -> tuple[str, str, str | None]:
    credit_values = [value for value in (high_yield, investment_grade) if value is not None]
    if not credit_values:
        return "unknown", "spread_data_missing", "Credit spread evidence is missing."

    high_yield_stress = high_yield is not None and high_yield >= 8.0
    investment_grade_stress = investment_grade is not None and investment_grade >= 3.0
    high_yield_pressure = high_yield is not None and high_yield >= 5.0
    investment_grade_pressure = investment_grade is not None and investment_grade >= 2.0
    high_yield_watch = high_yield is not None and high_yield >= 3.5
    investment_grade_watch = investment_grade is not None and investment_grade >= 1.5
    vix_pressure = vix is not None and vix >= 30.0
    vix_watch = vix is not None and vix >= 25.0

    if high_yield_stress or investment_grade_stress:
        return "stress", "credit_spreads_stressed", None
    if high_yield_pressure or investment_grade_pressure or (
        vix_pressure and (high_yield_watch or investment_grade_watch)
    ):
        return "pressure", "credit_pressure", None
    if high_yield_watch or investment_grade_watch or vix_watch:
        return "watch", "credit_watch", None
    if investment_grade is None:
        return (
            "watch",
            "partial_coverage",
            "Investment-grade spread is missing; credit stress coverage is partial.",
        )
    return "ok", "credit_calm", None


def real_yield_pressure_status_metric(
    reports: tuple[ReportState, ...],
    *,
    metric_aliases: dict[str, tuple[str, ...]] = METRIC_ALIASES,
) -> DashboardMetric:
    real_yield = usable_numeric_metric("dfii10", reports, metric_aliases=metric_aliases)
    breakeven = usable_numeric_metric("t10yie", reports, metric_aliases=metric_aliases)
    generated_at = latest_metric_timestamp(
        [item for item in (real_yield, breakeven) if item is not None]
    ) or first_updated_at([report for report in reports if report.data is not None])
    observation_date = latest_metric_observation_date(
        [item for item in (real_yield, breakeven) if item is not None]
    )
    hint = (
        "Derived from 10Y real yield (DFII10) and 10Y breakeven inflation (T10YIE). "
        "Real yield pressure is a valuation and opportunity-cost mechanism, not a sole "
        "driver of equities, gold, or portfolio action."
    )
    if real_yield is None or breakeven is None:
        missing = []
        if real_yield is None:
            missing.append("DFII10")
        if breakeven is None:
            missing.append("T10YIE")
        return blocked_dependency_metric(
            metric_key="real_yield_pressure_status",
            display_name="Real yield pressure status",
            unit=None,
            status="missing",
            missing_reason=(
                "Real yield pressure status requires both "
                f"{' and '.join(missing)} compact evidence."
            ),
            generated_at=generated_at,
            interpretation_hint=hint,
        )

    status, value = real_yield_status_from_values(
        real_yield=real_yield[0],
        breakeven=breakeven[0],
    )
    freshness_status = "fresh" if observation_date or generated_at else "unknown"
    return DashboardMetric(
        metric_key="real_yield_pressure_status",
        display_name="Real yield pressure status",
        value=value,
        value_text=format_value(value, "text", status),
        unit=None,
        status=status,
        source="dashboard_compact",
        source_badge="derived",
        observation_date=observation_date,
        generated_at=generated_at,
        freshness_status=freshness_status,
        missing_reason=None,
        interpretation_hint=hint,
        ai_context_allowed=ai_context_allowed(
            status=status,
            source="dashboard_compact",
            source_badge="derived",
            observation_date=observation_date,
            generated_at=generated_at,
            freshness_status=freshness_status,
            interpretation_hint=hint,
        ),
    )


def real_yield_status_from_values(
    *,
    real_yield: float,
    breakeven: float,
) -> tuple[str, str]:
    if real_yield >= 2.0:
        return "pressure", "real_yield_pressure"
    if real_yield >= 1.5 or breakeven >= 2.5:
        return "watch", "real_yield_watch"
    return "ok", "real_yield_calm"


def derived_metric_response(
    metric_key: str,
    display_name: str,
    value: float,
    unit: str,
    format_kind: str,
    source_metric: tuple[Any, dict[str, Any], ReportState],
    interpretation_hint: str,
) -> DashboardMetric:
    _, payload, report = source_metric
    generated_at = metric_generated_at(payload, report)
    observation_date = metric_observation_date(payload)
    freshness_status = metric_freshness(payload, report)
    source = metric_source(payload, report)
    return DashboardMetric(
        metric_key=metric_key,
        display_name=display_name,
        value=value,
        value_text=format_value(value, format_kind, "ok"),
        unit=unit,
        status="ok",
        source=source,
        source_badge="derived",
        source_series=metric_source_series(payload, None, None),
        observation_date=observation_date,
        generated_at=generated_at,
        freshness_status=freshness_status,
        missing_reason=None,
        interpretation_hint=interpretation_hint,
        ai_context_allowed=ai_context_allowed(
            status="ok",
            source=source,
            source_badge="derived",
            observation_date=observation_date,
            generated_at=generated_at,
            freshness_status=freshness_status,
            interpretation_hint=interpretation_hint,
        ),
    )


def blocked_dependency_metric(
    *,
    metric_key: str,
    display_name: str,
    unit: str | None,
    status: str,
    missing_reason: str,
    generated_at: str | None,
    interpretation_hint: str | None,
) -> DashboardMetric:
    normalized_status = metric_status_value(status)
    return DashboardMetric(
        metric_key=metric_key,
        display_name=display_name,
        value=None,
        value_text=missing_value_text(normalized_status),
        unit=unit,
        status=normalized_status,
        source=None,
        source_badge="research_needed" if normalized_status == "research_needed" else "missing",
        source_series=None,
        observation_date=None,
        generated_at=generated_at,
        freshness_status="missing"
        if normalized_status == "missing"
        else "unknown" if normalized_status == "unknown"
        else "insufficient_history",
        missing_reason=missing_reason,
        interpretation_hint=interpretation_hint,
        ai_context_allowed=False,
    )


def usable_numeric_metric(
    metric_key: str,
    reports: tuple[ReportState, ...],
    *,
    metric_aliases: dict[str, tuple[str, ...]] = METRIC_ALIASES,
) -> tuple[float, dict[str, Any], ReportState] | None:
    found = find_metric(metric_key, reports, metric_aliases=metric_aliases)
    if found is None or dependency_unusable(found):
        return None
    value = to_float(found[0])
    if not isinstance(value, float):
        return None
    return value, found[1], found[2]


def latest_metric_timestamp(
    found_items: list[tuple[float, dict[str, Any], ReportState]],
) -> str | None:
    candidates = [
        metric_generated_at(payload, report)
        for _, payload, report in found_items
    ]
    return max([item for item in candidates if item], default=None)


def latest_metric_observation_date(
    found_items: list[tuple[float, dict[str, Any], ReportState]],
) -> str | None:
    candidates = [
        metric_observation_date(payload)
        for _, payload, _ in found_items
    ]
    return max([item for item in candidates if item], default=None)


def has_breakout_history_evidence(payload: dict[str, Any]) -> bool:
    return any(
        key in payload
        for key in (
            "window_observation_count",
            "above_5pct_days_5d",
            "five_observation_average",
            "calculation",
        )
    )
