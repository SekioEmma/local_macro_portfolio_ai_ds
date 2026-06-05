from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app_backend.schemas.responses import (
    DashboardEvidenceRow,
    DashboardEvidenceTableResponse,
    DashboardMetric,
    DashboardModule,
    DashboardSummaryResponse,
)
from app_backend.services import provider_service


PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_REPORTS_DIR = PROJECT_ROOT / "outputs" / "reports"
MAX_ERROR_SUMMARY_LENGTH = 200
DASHBOARD_MODULE_KEYS = (
    "credit_stress",
    "rate_pressure",
    "real_yield_pressure",
    "inflation_energy_pressure",
    "equity_trend",
    "portfolio_deviation",
)
REPORT_FILES = {
    "market_snapshot": "market_snapshot.json",
    "market_temperature": "market_temperature.json",
    "portfolio_snapshot": "portfolio_snapshot.json",
    "provider_health": "provider_health_check.json",
}
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
}
ALLOWED_SOURCE_BADGES = {
    "official",
    "official_fallback",
    "unofficial_fallback",
    "proxy",
    "search-derived",
    "missing",
    "research_needed",
    "local",
    "derived",
}
AI_BLOCKED_METRIC_STATUSES = {
    "missing",
    "research_needed",
    "not_available",
    "insufficient_history",
    "stale",
}
AI_BLOCKED_FRESHNESS_STATUSES = {
    "unknown",
    "missing",
    "stale",
    "insufficient_history",
}
AI_BLOCKED_SOURCE_BADGES = {
    "missing",
    "research_needed",
    "search-derived",
}
SOURCE_BADGE_ALIASES = {
    "official_api": "official",
    "official_or_public_data_api": "official",
    "public_data_api": "official",
    "third_party_api": "proxy",
    "manual": "local",
    "cached_report": "derived",
}
CORE_METRIC_KEYS = {
    "credit_stress": {"high_yield_spread", "vix", "credit_stress_status"},
    "rate_pressure": {"dgs10", "dgs30", "dgs30_distance_to_5pct"},
    "real_yield_pressure": {"dfii10", "t10yie", "real_yield_pressure_status"},
    "inflation_energy_pressure": {
        "core_cpi_yoy",
        "core_pce_yoy",
        "ppiaco_yoy",
        "wti_30d_change",
        "brent_30d_change",
    },
    "equity_trend": {
        "sp500_30d_return",
        "nasdaq100_30d_return",
        "nasdaq_vs_sp500_30d",
    },
    "portfolio_deviation": {
        "max_deviation_asset",
        "max_deviation_pp",
        "equity_total_deviation_pp",
    },
}
METRIC_SPECS = {
    "credit_stress": [
        ("high_yield_spread", "High-yield spread", "percent", "percent", "missing"),
        (
            "investment_grade_spread",
            "Investment-grade spread",
            "percent",
            "percent",
            "research_needed",
        ),
        ("vix", "VIX", "index", "number", "missing"),
        ("credit_stress_status", "Credit stress status", None, "text", "missing"),
    ],
    "rate_pressure": [
        ("dgs10", "10Y Treasury yield", "percent", "percent", "missing"),
        ("dgs30", "30Y Treasury yield", "percent", "percent", "missing"),
        (
            "dgs30_distance_to_5pct",
            "30Y distance to 5%",
            "pp",
            "pp",
            "missing",
        ),
        ("dgs10_5d_avg", "10Y 5D average", "percent", "percent", "insufficient_history"),
        (
            "dgs30_breakout_confirmed",
            "30Y breakout confirmed",
            None,
            "bool",
            "research_needed",
        ),
    ],
    "real_yield_pressure": [
        ("dfii10", "10Y real yield", "percent", "percent", "missing"),
        ("t10yie", "10Y breakeven inflation", "percent", "percent", "missing"),
        ("real_yield_pressure_status", "Real yield pressure status", None, "text", "missing"),
    ],
    "inflation_energy_pressure": [
        ("core_cpi_yoy", "Core CPI YoY", "percent", "signed_percent", "missing"),
        ("core_pce_yoy", "Core PCE YoY", "percent", "signed_percent", "missing"),
        ("ppiaco_yoy", "PPIACO YoY", "percent", "signed_percent", "missing"),
        ("wti_30d_change", "WTI 30D change", "percent", "signed_percent", "insufficient_history"),
        ("brent_30d_change", "Brent 30D change", "percent", "signed_percent", "insufficient_history"),
    ],
    "equity_trend": [
        ("sp500_30d_return", "S&P 500 30D return", "percent", "signed_percent", "insufficient_history"),
        ("sp500_60d_return", "S&P 500 60D return", "percent", "signed_percent", "insufficient_history"),
        (
            "nasdaq100_30d_return",
            "Nasdaq 100 30D return",
            "percent",
            "signed_percent",
            "insufficient_history",
        ),
        (
            "nasdaq100_60d_return",
            "Nasdaq 100 60D return",
            "percent",
            "signed_percent",
            "insufficient_history",
        ),
        ("nasdaq_vs_sp500_30d", "Nasdaq vs S&P 500 30D", "pp", "pp", "insufficient_history"),
    ],
    "portfolio_deviation": [
        ("max_deviation_asset", "Max deviation asset", None, "text", "missing"),
        ("max_deviation_pp", "Max deviation", "pp", "pp", "missing"),
        ("equity_total_deviation_pp", "Equity total deviation", "pp", "pp", "missing"),
        ("cash_reserve_status", "Cash reserve status", None, "text", "missing"),
        ("holdings_updated_at", "Holdings updated at", None, "text", "missing"),
    ],
}


@dataclass(frozen=True)
class ReportState:
    name: str
    path: Path
    exists: bool
    data: dict[str, Any] | None = None
    error_summary: str | None = None


def build_dashboard_summary(reports_dir: Path | str | None = None) -> DashboardSummaryResponse:
    base_dir = Path(reports_dir) if reports_dir is not None else DEFAULT_REPORTS_DIR
    reports = {
        key: _load_report(key, base_dir / file_name)
        for key, file_name in REPORT_FILES.items()
    }
    provider_health = _provider_health_summary(
        base_dir / REPORT_FILES["provider_health"]
    )
    modules = _build_modules(reports)
    missing_data = _missing_data(reports)
    data_freshness = _data_freshness(reports, provider_health)
    next_actions = _next_actions(modules, provider_health)

    return DashboardSummaryResponse(
        generated_at=_first_generated_at(reports, provider_health),
        overall_status=_overall_status(modules, provider_health),
        overall_risk_level=_overall_risk_level(reports),
        modules=modules,
        provider_health=provider_health,
        missing_data=missing_data,
        data_freshness=data_freshness,
        next_actions=next_actions,
    )


def build_dashboard_evidence_table(
    reports_dir: Path | str | None = None,
    module: str | None = None,
    status: str | None = None,
    source_badge: str | None = None,
    ai_context_allowed: bool | None = None,
) -> DashboardEvidenceTableResponse:
    summary = build_dashboard_summary(reports_dir=reports_dir)
    all_rows = _evidence_rows_from_summary(summary)
    filtered_rows = [
        row
        for row in all_rows
        if _evidence_row_matches(
            row,
            module=module,
            status=status,
            source_badge=source_badge,
            ai_context_allowed=ai_context_allowed,
        )
    ]

    return DashboardEvidenceTableResponse(
        generated_at=summary.generated_at,
        overall_status=summary.overall_status,
        row_count=len(filtered_rows),
        modules=list(summary.modules.keys()),
        rows=filtered_rows,
        filters=_evidence_filters(
            all_rows,
            module=module,
            status=status,
            source_badge=source_badge,
            ai_context_allowed=ai_context_allowed,
        ),
        next_actions=summary.next_actions,
    )


def _load_report(name: str, path: Path) -> ReportState:
    if not path.exists():
        return ReportState(name=name, path=path, exists=False)
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        return ReportState(
            name=name,
            path=path,
            exists=True,
            error_summary=f"{path.name} is invalid or unreadable",
        )
    if not isinstance(payload, dict):
        return ReportState(
            name=name,
            path=path,
            exists=True,
            error_summary=f"{path.name} is not a JSON object",
        )
    return ReportState(name=name, path=path, exists=True, data=payload)


def _evidence_rows_from_summary(
    summary: DashboardSummaryResponse,
) -> list[DashboardEvidenceRow]:
    rows: list[DashboardEvidenceRow] = []
    for module_key, module in summary.modules.items():
        for metric in module.key_metrics:
            rows.append(_evidence_row(module_key, metric))
    return rows


def _evidence_row(module_key: str, metric: DashboardMetric) -> DashboardEvidenceRow:
    return DashboardEvidenceRow(
        row_id=f"{module_key}:{metric.metric_key}",
        module=module_key,
        metric_key=metric.metric_key,
        display_name=metric.display_name,
        value=metric.value,
        value_text=_evidence_value_text(metric),
        unit=metric.unit,
        status=metric.status,
        source=metric.source,
        source_badge=metric.source_badge,
        observation_date=metric.observation_date,
        generated_at=metric.generated_at,
        freshness_status=metric.freshness_status,
        missing_reason=metric.missing_reason,
        interpretation_hint=metric.interpretation_hint,
        ai_context_allowed=_evidence_ai_context_allowed(metric),
    )


def _evidence_value_text(metric: DashboardMetric) -> str:
    text = str(metric.value_text or "").strip()
    if text and text != "--":
        return text
    return _missing_value_text(metric.status)


def _evidence_ai_context_allowed(metric: DashboardMetric) -> bool:
    return _ai_context_allowed(
        status=metric.status,
        source=metric.source,
        source_badge=metric.source_badge,
        observation_date=metric.observation_date,
        generated_at=metric.generated_at,
        freshness_status=metric.freshness_status,
        interpretation_hint=metric.interpretation_hint,
    ) and bool(metric.ai_context_allowed)


def _evidence_row_matches(
    row: DashboardEvidenceRow,
    module: str | None,
    status: str | None,
    source_badge: str | None,
    ai_context_allowed: bool | None,
) -> bool:
    if module is not None and row.module != module:
        return False
    if status is not None and row.status != status:
        return False
    if source_badge is not None and row.source_badge != source_badge:
        return False
    if ai_context_allowed is not None and row.ai_context_allowed != ai_context_allowed:
        return False
    return True


def _evidence_filters(
    rows: list[DashboardEvidenceRow],
    module: str | None,
    status: str | None,
    source_badge: str | None,
    ai_context_allowed: bool | None,
) -> dict[str, Any]:
    return {
        "available": {
            "modules": sorted({row.module for row in rows}),
            "statuses": sorted({row.status for row in rows}),
            "source_badges": sorted({row.source_badge for row in rows}),
            "ai_context_allowed": sorted({row.ai_context_allowed for row in rows}),
        },
        "applied": {
            "module": module,
            "status": status,
            "source_badge": source_badge,
            "ai_context_allowed": ai_context_allowed,
        },
    }


def _provider_health_summary(health_path: Path) -> dict:
    response = provider_service.build_provider_health(health_path)
    payload = _model_to_dict(response)
    return {
        "generated_at": payload.get("generated_at"),
        "overall_status": payload.get("overall_status"),
        "summary": payload.get("summary") if isinstance(payload.get("summary"), dict) else {},
        "next_action": payload.get("next_action"),
        "error_summary": payload.get("error_summary"),
    }


def _build_modules(reports: dict[str, ReportState]) -> dict[str, DashboardModule]:
    market = reports["market_snapshot"]
    temperature = reports["market_temperature"]
    portfolio = reports["portfolio_snapshot"]
    return {
        "credit_stress": _market_module(
            key="credit_stress",
            label="credit stress",
            reports=(market, temperature),
            signal_terms=("financial_conditions", "high_yield_spread", "credit", "vix"),
            key_metrics=_key_metrics_for_module("credit_stress", (market, temperature)),
        ),
        "rate_pressure": _market_module(
            key="rate_pressure",
            label="rate pressure",
            reports=(market,),
            signal_terms=("dgs10", "dgs30", "treasury_yields", "10y", "30y"),
            key_metrics=_key_metrics_for_module("rate_pressure", (market,)),
        ),
        "real_yield_pressure": _market_module(
            key="real_yield_pressure",
            label="real yield pressure",
            reports=(market,),
            signal_terms=("real_yield_10y", "dfii10", "real_yield"),
            key_metrics=_key_metrics_for_module("real_yield_pressure", (market,)),
        ),
        "inflation_energy_pressure": _market_module(
            key="inflation_energy_pressure",
            label="inflation and energy pressure",
            reports=(market, temperature),
            signal_terms=("cpi", "pce", "ppi", "oil", "energy", "inflation"),
            key_metrics=_key_metrics_for_module(
                "inflation_energy_pressure",
                (market, temperature),
            ),
        ),
        "equity_trend": _market_module(
            key="equity_trend",
            label="equity trend",
            reports=(market, temperature),
            signal_terms=("sp500", "nasdaq", "nasdaq100", "equity_temperature", "equity"),
            key_metrics=_key_metrics_for_module("equity_trend", (market, temperature)),
        ),
        "portfolio_deviation": _portfolio_module(portfolio),
    }


def _market_module(
    key: str,
    label: str,
    reports: tuple[ReportState, ...],
    signal_terms: tuple[str, ...],
    key_metrics: list[DashboardMetric],
) -> DashboardModule:
    error = _first_error(reports)
    if error is not None:
        return _module(
            key=key,
            status="error",
            label=label,
            summary=f"{label} report data is invalid",
            source_badge="report_error",
            error_summary=error,
            key_metrics=key_metrics,
        )

    available_reports = [report for report in reports if report.data is not None]
    if not available_reports:
        return _module(
            key=key,
            status="missing",
            label=label,
            summary=f"{label} data missing",
            source_badge="missing_report",
            next_action=_run_reports_action(),
            key_metrics=key_metrics,
        )

    if any(_contains_signal(report.data, signal_terms) for report in available_reports):
        status = _coerce_status(_first_status(available_reports), default="ok")
        return _module(
            key=key,
            status=status,
            label=label,
            summary=f"{label} compact data available",
            source_badge="cached_report",
            updated_at=_first_updated_at(available_reports),
            key_metrics=key_metrics,
        )

    return _module(
        key=key,
        status="missing",
        label=label,
        summary=f"{label} compact signal missing",
        source_badge="cached_report",
        updated_at=_first_updated_at(available_reports),
        next_action=_run_reports_action(),
        key_metrics=key_metrics,
    )


def _portfolio_module(report: ReportState) -> DashboardModule:
    if report.error_summary is not None:
        return _module(
            key="portfolio_deviation",
            status="error",
            label="portfolio deviation",
            summary="portfolio snapshot invalid",
            source_badge="report_error",
            error_summary=report.error_summary,
            key_metrics=_key_metrics_for_module("portfolio_deviation", (report,)),
        )
    if report.data is None:
        return _module(
            key="portfolio_deviation",
            status="missing",
            label="missing",
            summary="portfolio snapshot missing",
            source_badge="missing_report",
            next_action="python scripts/run_portfolio_check.py",
            key_metrics=_key_metrics_for_module("portfolio_deviation", (report,)),
        )
    return _module(
        key="portfolio_deviation",
        status=_coerce_status(report.data.get("status"), default="ok"),
        label="available",
        summary="portfolio snapshot available",
        source_badge="cached_report",
        updated_at=_string_or_none(
            report.data.get("generated_at") or report.data.get("updated_at")
        ),
        key_metrics=_key_metrics_for_module("portfolio_deviation", (report,)),
    )


def _module(
    key: str,
    status: str,
    label: str | None,
    summary: str | None,
    source_badge: str | None,
    updated_at: str | None = None,
    next_action: str | None = None,
    error_summary: str | None = None,
    key_metrics: list[DashboardMetric] | None = None,
) -> DashboardModule:
    metrics = key_metrics or []
    coerced_status = _coerce_status(status)
    adjusted_status, coverage_note = _module_status_with_coverage(
        key,
        coerced_status,
        metrics,
    )
    adjusted_summary = _summary_with_coverage_note(summary, coverage_note)
    return DashboardModule(
        key=key,
        status=adjusted_status,
        label=label,
        summary=adjusted_summary,
        source_badge=source_badge,
        updated_at=updated_at,
        next_action=next_action,
        error_summary=_safe_error_summary(error_summary),
        key_metrics=metrics,
    )


def _key_metrics_for_module(
    module_key: str,
    reports: tuple[ReportState, ...],
) -> list[DashboardMetric]:
    return [
        _build_metric(module_key, reports, spec)
        for spec in METRIC_SPECS.get(module_key, [])
    ]


def _build_metric(
    module_key: str,
    reports: tuple[ReportState, ...],
    spec: tuple[str, str, str | None, str, str],
) -> DashboardMetric:
    metric_key, display_name, unit, format_kind, missing_status = spec
    derived = _derived_metric(metric_key, reports)
    if derived is not None:
        return derived

    found = _find_metric(metric_key, reports)
    interpretation_hint = _interpretation_hint(metric_key)
    if found is None:
        return _missing_metric(
            metric_key=metric_key,
            display_name=display_name,
            unit=unit,
            status=missing_status,
            generated_at=_first_updated_at([report for report in reports if report.data is not None]),
            interpretation_hint=interpretation_hint,
        )

    value, payload, report = found
    status = _metric_status(payload)
    freshness_status = _metric_freshness(payload, report)
    if freshness_status == "stale" and status == "ok":
        status = "stale"

    source = _metric_source(payload, report)
    source_badge = _metric_source_badge(payload, report, module_key)
    observation_date = _metric_observation_date(payload)
    generated_at = _metric_generated_at(payload, report)
    missing_reason = _string_or_none(payload.get("missing_reason")) if isinstance(payload, dict) else None

    return DashboardMetric(
        metric_key=metric_key,
        display_name=display_name,
        value=value,
        value_text=_format_value(value, format_kind, status),
        unit=unit,
        status=status,
        source=source,
        source_badge=source_badge,
        observation_date=observation_date,
        generated_at=generated_at,
        freshness_status=freshness_status,
        missing_reason=missing_reason,
        interpretation_hint=interpretation_hint,
        ai_context_allowed=_ai_context_allowed(
            status=status,
            source=source,
            source_badge=source_badge,
            observation_date=observation_date,
            generated_at=generated_at,
            freshness_status=freshness_status,
            interpretation_hint=interpretation_hint,
        ),
    )


def _derived_metric(
    metric_key: str,
    reports: tuple[ReportState, ...],
) -> DashboardMetric | None:
    if metric_key == "dgs30_distance_to_5pct":
        found = _find_metric("dgs30", reports)
        if found is None or _dependency_unusable(found):
            return _blocked_dependency_metric(
                metric_key="dgs30_distance_to_5pct",
                display_name="30Y distance to 5%",
                unit="pp",
                status="missing",
                missing_reason="DGS30 is missing; distance to 5% cannot be calculated.",
                generated_at=_first_updated_at([report for report in reports if report.data is not None]),
                interpretation_hint="Distance requires daily DGS30 compact evidence.",
            )
        dgs30_value = _to_float(found[0])
        if not isinstance(dgs30_value, float):
            return _blocked_dependency_metric(
                metric_key="dgs30_distance_to_5pct",
                display_name="30Y distance to 5%",
                unit="pp",
                status="missing",
                missing_reason="DGS30 is missing; distance to 5% cannot be calculated.",
                generated_at=_first_updated_at([report for report in reports if report.data is not None]),
                interpretation_hint="Distance requires numeric daily DGS30 compact evidence.",
            )
        value = round(dgs30_value - 5.0, 4)
        return _derived_metric_response(
            metric_key,
            "30Y distance to 5%",
            value,
            "pp",
            "pp",
            found,
            "Distance is derived from daily DGS30; it is not intraday.",
        )
    if metric_key == "dgs30_breakout_confirmed":
        dgs30 = _find_metric("dgs30", reports)
        if dgs30 is None or _dependency_unusable(dgs30):
            return _blocked_dependency_metric(
                metric_key="dgs30_breakout_confirmed",
                display_name="30Y breakout confirmed",
                unit=None,
                status="missing",
                missing_reason="DGS30 is missing; breakout confirmation cannot be evaluated.",
                generated_at=_first_updated_at([report for report in reports if report.data is not None]),
                interpretation_hint="Breakout confirmation requires DGS30 and explicit compact history evidence.",
            )
        found = _find_metric("dgs30_breakout_confirmed", reports)
        if found is None:
            return None
        _, payload, report = found
        if _dependency_unusable(found):
            return None
        if not _has_breakout_history_evidence(payload):
            return _blocked_dependency_metric(
                metric_key="dgs30_breakout_confirmed",
                display_name="30Y breakout confirmed",
                unit=None,
                status="insufficient_history",
                missing_reason="DGS30 breakout confirmation requires compact history window evidence.",
                generated_at=_metric_generated_at(payload, report),
                interpretation_hint="Breakout confirmation requires explicit compact evidence; do not infer it.",
            )
    if metric_key == "nasdaq_vs_sp500_30d":
        nasdaq = _find_metric("nasdaq100_30d_return", reports)
        sp500 = _find_metric("sp500_30d_return", reports)
        if nasdaq is None or sp500 is None or _dependency_unusable(nasdaq) or _dependency_unusable(sp500):
            return _blocked_dependency_metric(
                metric_key="nasdaq_vs_sp500_30d",
                display_name="Nasdaq vs S&P 500 30D",
                unit="pp",
                status="insufficient_history",
                missing_reason="S&P 500 and Nasdaq 100 30D returns are both required.",
                generated_at=_first_updated_at([report for report in reports if report.data is not None]),
                interpretation_hint="Derived spread requires both compact 30D return metrics.",
            )
        nasdaq_value = _to_float(nasdaq[0])
        sp500_value = _to_float(sp500[0])
        if not isinstance(nasdaq_value, float) or not isinstance(sp500_value, float):
            return _blocked_dependency_metric(
                metric_key="nasdaq_vs_sp500_30d",
                display_name="Nasdaq vs S&P 500 30D",
                unit="pp",
                status="insufficient_history",
                missing_reason="S&P 500 and Nasdaq 100 30D returns must both be numeric.",
                generated_at=_first_updated_at([report for report in reports if report.data is not None]),
                interpretation_hint="Derived spread requires numeric compact 30D return metrics.",
            )
        value = round(nasdaq_value - sp500_value, 4)
        return _derived_metric_response(
            metric_key,
            "Nasdaq vs S&P 500 30D",
            value,
            "pp",
            "pp",
            nasdaq,
            "Derived spread between compact 30D return metrics.",
        )
    return None


def _derived_metric_response(
    metric_key: str,
    display_name: str,
    value: float,
    unit: str,
    format_kind: str,
    source_metric: tuple[Any, dict[str, Any], ReportState],
    interpretation_hint: str,
) -> DashboardMetric:
    _, payload, report = source_metric
    generated_at = _metric_generated_at(payload, report)
    observation_date = _metric_observation_date(payload)
    return DashboardMetric(
        metric_key=metric_key,
        display_name=display_name,
        value=value,
        value_text=_format_value(value, format_kind, "ok"),
        unit=unit,
        status="ok",
        source=_metric_source(payload, report),
        source_badge="derived",
        observation_date=observation_date,
        generated_at=generated_at,
        freshness_status=_metric_freshness(payload, report),
        missing_reason=None,
        interpretation_hint=interpretation_hint,
        ai_context_allowed=_ai_context_allowed(
            status="ok",
            source=_metric_source(payload, report),
            source_badge="derived",
            observation_date=observation_date,
            generated_at=generated_at,
            freshness_status=_metric_freshness(payload, report),
            interpretation_hint=interpretation_hint,
        ),
    )


def _blocked_dependency_metric(
    *,
    metric_key: str,
    display_name: str,
    unit: str | None,
    status: str,
    missing_reason: str,
    generated_at: str | None,
    interpretation_hint: str | None,
) -> DashboardMetric:
    normalized_status = _metric_status_value(status)
    return DashboardMetric(
        metric_key=metric_key,
        display_name=display_name,
        value=None,
        value_text=_missing_value_text(normalized_status),
        unit=unit,
        status=normalized_status,
        source=None,
        source_badge="missing",
        observation_date=None,
        generated_at=generated_at,
        freshness_status="missing"
        if normalized_status == "missing"
        else "insufficient_history",
        missing_reason=missing_reason,
        interpretation_hint=interpretation_hint,
        ai_context_allowed=False,
    )


def _missing_metric(
    metric_key: str,
    display_name: str,
    unit: str | None,
    status: str,
    generated_at: str | None,
    interpretation_hint: str | None = None,
) -> DashboardMetric:
    normalized_status = _metric_status_value(status)
    source_badge = "research_needed" if normalized_status == "research_needed" else "missing"
    return DashboardMetric(
        metric_key=metric_key,
        display_name=display_name,
        value=None,
        value_text=_missing_value_text(normalized_status),
        unit=unit,
        status=normalized_status,
        source=None,
        source_badge=source_badge,
        observation_date=None,
        generated_at=generated_at,
        freshness_status="unknown",
        missing_reason=_missing_value_text(normalized_status),
        interpretation_hint=interpretation_hint,
        ai_context_allowed=False,
    )


def _find_metric(
    metric_key: str,
    reports: tuple[ReportState, ...],
) -> tuple[Any, dict[str, Any], ReportState] | None:
    for report in reports:
        if report.data is None:
            continue
        found = _find_metric_payload(report.data, metric_key)
        if found is None:
            continue
        value, payload = found
        return value, payload, report
    return None


def _find_metric_payload(value: Any, metric_key: str) -> tuple[Any, dict[str, Any]] | None:
    if isinstance(value, dict):
        for key, child in value.items():
            if str(key).lower() == metric_key.lower():
                if isinstance(child, dict):
                    child_value = _extract_metric_value(child)
                    return child_value, child
                return child, {"value": child}
        for child in value.values():
            found = _find_metric_payload(child, metric_key)
            if found is not None:
                return found
    elif isinstance(value, list):
        for child in value:
            found = _find_metric_payload(child, metric_key)
            if found is not None:
                return found
    return None


def _extract_metric_value(payload: dict[str, Any]) -> Any:
    for key in ("value", "value_text", "status", "label", "date", "updated_at"):
        if key in payload and payload.get(key) is not None:
            return payload.get(key)
    return None


def _metric_status(payload: dict[str, Any]) -> str:
    return _metric_status_value(payload.get("status") or "ok")


def _metric_status_value(value: Any) -> str:
    status = str(value or "unknown").lower()
    return status if status in ALLOWED_METRIC_STATUSES else "unknown"


def _metric_freshness(payload: dict[str, Any], report: ReportState) -> str:
    freshness = payload.get("freshness_status")
    if freshness is None and isinstance(payload.get("freshness"), dict):
        freshness = payload["freshness"].get("freshness_status")
    if freshness is None and _contains_signal(payload, ("stale_cache",)):
        freshness = "stale"
    if freshness is None and report.data is not None and _contains_signal(report.data, ("stale_cache",)):
        freshness = "stale"
    return str(freshness or "unknown").lower()


def _metric_source(payload: dict[str, Any], report: ReportState) -> str | None:
    source = payload.get("source")
    if source is None and isinstance(payload.get("metadata"), dict):
        source = payload["metadata"].get("source")
    if source is None and isinstance(report.data, dict):
        source = report.data.get("source")
    return _string_or_none(source)


def _metric_source_badge(payload: dict[str, Any], report: ReportState, module_key: str) -> str:
    if module_key == "portfolio_deviation":
        return "local"
    badge = payload.get("source_badge") or payload.get("source_tier")
    if badge is None and isinstance(payload.get("freshness"), dict):
        badge = payload["freshness"].get("source_tier")
    if badge is None and isinstance(report.data, dict):
        badge = report.data.get("source_badge") or report.data.get("source_tier")
    badge_text = str(badge or "missing").lower()
    badge_text = SOURCE_BADGE_ALIASES.get(badge_text, badge_text)
    if badge_text in {"official", "official_fallback", "unofficial_fallback", "proxy", "search-derived"}:
        return badge_text
    return badge_text if badge_text in ALLOWED_SOURCE_BADGES else "missing"


def _metric_observation_date(payload: dict[str, Any]) -> str | None:
    return _string_or_none(
        payload.get("observation_date")
        or payload.get("date")
        or payload.get("updated_at")
    )


def _metric_generated_at(payload: dict[str, Any], report: ReportState) -> str | None:
    if payload.get("generated_at") is not None:
        return _string_or_none(payload.get("generated_at"))
    if isinstance(report.data, dict):
        return _string_or_none(report.data.get("generated_at") or report.data.get("updated_at"))
    return None


def _format_value(value: Any, format_kind: str, status: str) -> str:
    if status in {"missing", "research_needed", "insufficient_history", "not_available"}:
        return _missing_value_text(status)
    if status == "stale" and value is None:
        return "stale"
    if format_kind == "bool":
        if isinstance(value, bool):
            return "true" if value else "false"
        return "unknown"
    if format_kind == "percent":
        number = _to_float(value)
        return f"{number:.2f}%" if isinstance(number, float) else str(value)
    if format_kind == "signed_percent":
        number = _to_float(value)
        return f"{number:+.2f}%" if isinstance(number, float) else str(value)
    if format_kind == "pp":
        number = _to_float(value)
        return f"{number:+.1f}pp" if isinstance(number, float) else str(value)
    if value is None:
        return "unknown"
    return str(value)


def _missing_value_text(status: str) -> str:
    if status == "research_needed":
        return "research needed"
    if status == "insufficient_history":
        return "insufficient history"
    if status == "stale":
        return "stale"
    if status == "not_available":
        return "not available"
    return "missing"


def _to_float(value: Any) -> float | None:
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


def _interpretation_hint(metric_key: str) -> str | None:
    if metric_key in {"dgs10", "dgs30", "dgs10_5d_avg", "dgs30_distance_to_5pct"}:
        return "FRED Treasury yield series are daily, not intraday."
    if metric_key == "dgs30_breakout_confirmed":
        return "Breakout confirmation requires explicit compact evidence; do not infer it."
    if metric_key == "ppiaco_yoy":
        return "PPIACO is not final demand PPI."
    if metric_key == "cash_reserve_status":
        return "Cash reserve is not part of target allocation."
    if metric_key in {
        "max_deviation_asset",
        "max_deviation_pp",
        "equity_total_deviation_pp",
    }:
        return "Portfolio deviation is local context and is not attributed to market factors."
    return None


def _ai_context_allowed(
    status: str,
    source: str | None,
    source_badge: str,
    observation_date: str | None,
    generated_at: str | None,
    freshness_status: str,
    interpretation_hint: str | None = None,
) -> bool:
    if status in AI_BLOCKED_METRIC_STATUSES:
        return False
    if source_badge in AI_BLOCKED_SOURCE_BADGES:
        return False
    has_date = bool(observation_date or generated_at)
    if freshness_status in AI_BLOCKED_FRESHNESS_STATUSES:
        if not (source_badge == "local" and bool(generated_at)):
            return False
    if source_badge == "proxy":
        hint = (interpretation_hint or "").lower()
        if "allowed proxy" not in hint:
            return False
    if source_badge == "derived" and not interpretation_hint:
        return False
    if not source and source_badge not in {"local", "derived"}:
        return False
    return has_date


def _dependency_unusable(found: tuple[Any, dict[str, Any], ReportState]) -> bool:
    value, payload, report = found
    status = _metric_status(payload)
    freshness = _metric_freshness(payload, report)
    if status in AI_BLOCKED_METRIC_STATUSES:
        return True
    if freshness in {"missing", "insufficient_history", "stale"}:
        return True
    return value is None


def _has_breakout_history_evidence(payload: dict[str, Any]) -> bool:
    return any(
        key in payload
        for key in (
            "window_observation_count",
            "above_5pct_days_5d",
            "five_observation_average",
            "calculation",
        )
    )


def _module_status_with_coverage(
    module_key: str,
    status: str,
    key_metrics: list[DashboardMetric],
) -> tuple[str, str | None]:
    if status in {"error", "missing", "stale"}:
        return status, None
    core_metrics = [
        metric
        for metric in key_metrics
        if metric.metric_key in CORE_METRIC_KEYS.get(module_key, set())
    ]
    if not core_metrics:
        return status, None

    blocked = [
        metric for metric in core_metrics if metric.status in AI_BLOCKED_METRIC_STATUSES
    ]
    stale = [metric for metric in core_metrics if metric.freshness_status == "stale"]
    if len(blocked) == len(core_metrics):
        return "unknown", "core metric coverage unavailable"
    if stale:
        return "stale", "one or more core metrics are stale"
    if blocked and status == "ok":
        return "unknown", "partial core metric coverage"
    return status, None


def _summary_with_coverage_note(summary: str | None, coverage_note: str | None) -> str | None:
    if not coverage_note:
        return summary
    if not summary:
        return coverage_note
    if coverage_note in summary:
        return summary
    return f"{summary}; {coverage_note}"


def _missing_data(reports: dict[str, ReportState]) -> list[dict]:
    missing = []
    for name, report in reports.items():
        if not report.exists:
            missing.append(
                {
                    "key": name,
                    "status": "missing",
                    "summary": f"{report.path.name} missing",
                    "next_action": _next_action_for_report(name),
                }
            )
        elif report.error_summary is not None:
            missing.append(
                {
                    "key": name,
                    "status": "error",
                    "summary": report.error_summary,
                    "next_action": _next_action_for_report(name),
                }
            )
        else:
            compact_missing = _compact_missing_entries(report.data)
            for entry in compact_missing:
                missing.append({"key": name, **entry})
    return missing


def _compact_missing_entries(data: dict[str, Any] | None) -> list[dict]:
    if not isinstance(data, dict):
        return []
    entries = []
    for field in (
        "missing_required_inputs",
        "missing_optional_inputs",
        "research_needed",
        "not_available",
    ):
        value = data.get(field)
        if isinstance(value, list):
            entries.append(
                {
                    "status": "missing",
                    "summary": f"{field}: {len(value)} item(s)",
                }
            )
    return entries


def _data_freshness(reports: dict[str, ReportState], provider_health: dict) -> dict:
    files = {}
    for name, report in reports.items():
        files[name] = {
            "status": _report_status(report),
            "generated_at": _string_or_none(
                report.data.get("generated_at")
                if isinstance(report.data, dict)
                else None
            ),
            "stale_cache": _contains_signal(report.data, ("stale_cache",)),
            "next_action": _next_action_for_report(name)
            if _report_status(report) in {"missing", "error", "stale"}
            else None,
        }
    return {
        "status": _freshness_status(files),
        "files": files,
        "provider_health_generated_at": provider_health.get("generated_at"),
    }


def _next_actions(modules: dict[str, DashboardModule], provider_health: dict) -> list[str]:
    actions = []
    for module in modules.values():
        if module.next_action:
            actions.append(module.next_action)
    provider_action = provider_health.get("next_action")
    if provider_action:
        actions.append(str(provider_action))
    return sorted(set(actions))


def _overall_status(modules: dict[str, DashboardModule], provider_health: dict) -> str:
    statuses = {module.status for module in modules.values()}
    provider_status = provider_health.get("overall_status")
    if "error" in statuses or provider_status == "error":
        return "error"
    if statuses == {"missing"} and provider_status == "not_run_yet":
        return "missing"
    if statuses & {"missing", "stale", "degraded", "unknown"} or provider_status in {
        "degraded",
        "not_run_yet",
    }:
        return "degraded"
    if statuses == {"ok"} and provider_status in {"ok", None}:
        return "ok"
    return "unknown"


def _overall_risk_level(reports: dict[str, ReportState]) -> str | None:
    for report in (reports["market_temperature"], reports["market_snapshot"]):
        if report.data is None:
            continue
        for key in ("overall_risk_level", "risk_level", "temperature_label"):
            value = _string_or_none(report.data.get(key))
            if value:
                return value
    return None


def _first_generated_at(reports: dict[str, ReportState], provider_health: dict) -> str | None:
    for report in (
        reports["market_temperature"],
        reports["market_snapshot"],
        reports["portfolio_snapshot"],
    ):
        if report.data is None:
            continue
        value = _string_or_none(report.data.get("generated_at"))
        if value:
            return value
    return _string_or_none(provider_health.get("generated_at"))


def _first_error(reports: tuple[ReportState, ...]) -> str | None:
    for report in reports:
        if report.error_summary is not None:
            return report.error_summary
    return None


def _first_status(reports: list[ReportState]) -> str | None:
    for report in reports:
        value = _string_or_none(report.data.get("status") if report.data else None)
        if value:
            return value
    return None


def _first_updated_at(reports: list[ReportState]) -> str | None:
    for report in reports:
        if report.data is None:
            continue
        value = _string_or_none(
            report.data.get("generated_at") or report.data.get("updated_at")
        )
        if value:
            return value
    return None


def _contains_signal(value: Any, signal_terms: tuple[str, ...]) -> bool:
    terms = tuple(term.lower() for term in signal_terms)
    return _contains_signal_key(value, terms)


def _contains_signal_key(value: Any, signal_terms: tuple[str, ...]) -> bool:
    if isinstance(value, dict):
        for key, child in value.items():
            key_text = str(key).lower()
            if any(term in key_text for term in signal_terms):
                return True
            if _contains_signal_key(child, signal_terms):
                return True
    elif isinstance(value, list):
        return any(_contains_signal_key(item, signal_terms) for item in value)
    elif isinstance(value, str):
        text = value.lower()
        return any(text == term for term in signal_terms)
    return False


def _report_status(report: ReportState) -> str:
    if not report.exists:
        return "missing"
    if report.error_summary is not None:
        return "error"
    if report.data is None:
        return "unknown"
    if _contains_signal(report.data, ("stale_cache",)):
        return "stale"
    return _coerce_status(report.data.get("status"), default="ok")


def _freshness_status(files: dict[str, dict]) -> str:
    statuses = {item["status"] for item in files.values()}
    if "error" in statuses:
        return "error"
    if "stale" in statuses:
        return "stale"
    if "missing" in statuses:
        return "degraded"
    if statuses == {"ok"}:
        return "ok"
    return "unknown"


def _next_action_for_report(name: str) -> str:
    if name == "provider_health":
        return provider_service.NEXT_ACTION
    if name == "portfolio_snapshot":
        return "python scripts/run_portfolio_check.py"
    return _run_reports_action()


def _run_reports_action() -> str:
    return "python scripts/run_market_data_check.py"


def _coerce_status(value: Any, default: str = "unknown") -> str:
    allowed = {"ok", "missing", "stale", "degraded", "error", "not_run_yet", "unknown"}
    status = str(value or default).lower()
    return status if status in allowed else default


def _string_or_none(value: Any) -> str | None:
    if value is None:
        return None
    return str(value)


def _safe_error_summary(value: Any) -> str | None:
    if value is None:
        return None
    text = re.sub(r"\s+", " ", str(value)).strip()
    text = re.sub(r"sk-[A-Za-z0-9_-]{20,}", "[redacted]", text)
    text = re.sub(
        r"(?i)(api[_-]?key|apikey|token|secret)=([^&\s]+)",
        r"\1=[redacted]",
        text,
    )
    if len(text) > MAX_ERROR_SUMMARY_LENGTH:
        return text[:MAX_ERROR_SUMMARY_LENGTH].rstrip()
    return text


def _model_to_dict(value: Any) -> dict:
    if hasattr(value, "model_dump"):
        return value.model_dump()
    return value.dict()
