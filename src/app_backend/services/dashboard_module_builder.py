from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

from app_backend.schemas.responses import DashboardMetric, DashboardModule
from app_backend.services.dashboard_report_loader import ReportState
from app_backend.services.dashboard_summary_assembly import (
    coerce_status,
    contains_signal,
    first_error,
    first_status,
    first_updated_at,
    run_reports_action,
    safe_error_summary,
    string_or_none,
)


KeyMetricsForModule = Callable[..., list[DashboardMetric]]
PortfolioCompactBuilder = Callable[[ReportState], Any]
PortfolioCompactStatusBuilder = Callable[[Any], str]


def build_modules(
    reports: dict[str, ReportState],
    *,
    market_history_db_path: Path | str | None = None,
    key_metrics_for_module: KeyMetricsForModule,
    portfolio_deviation_compact: PortfolioCompactBuilder,
    portfolio_compact_module_status: PortfolioCompactStatusBuilder,
    core_metric_keys: dict[str, set[str]],
    ai_blocked_metric_statuses: set[str],
    equity_historical_derived_metric_keys: set[str],
    proxy_historical_derived_metric_keys: set[str],
    market_stress_historical_derived_metric_keys: set[str],
) -> dict[str, DashboardModule]:
    market = reports["market_snapshot"]
    temperature = reports["market_temperature"]
    portfolio = reports["portfolio_snapshot"]
    llm_context = reports.get("llm_context_pack")
    market_metadata_reports = (market, llm_context) if llm_context else (market,)
    market_temperature_metadata_reports = (
        market,
        temperature,
        llm_context,
    ) if llm_context else (market, temperature)
    return {
        "credit_stress": market_module(
            key="credit_stress",
            label="credit stress",
            reports=market_temperature_metadata_reports,
            signal_terms=("financial_conditions", "high_yield_spread", "credit", "vix"),
            key_metrics=key_metrics_for_module("credit_stress", market_temperature_metadata_reports),
            core_metric_keys=core_metric_keys,
            ai_blocked_metric_statuses=ai_blocked_metric_statuses,
            equity_historical_derived_metric_keys=equity_historical_derived_metric_keys,
            proxy_historical_derived_metric_keys=proxy_historical_derived_metric_keys,
            market_stress_historical_derived_metric_keys=market_stress_historical_derived_metric_keys,
        ),
        "rate_pressure": market_module(
            key="rate_pressure",
            label="rate pressure",
            reports=market_metadata_reports,
            signal_terms=("dgs10", "dgs30", "treasury_yields", "10y", "30y"),
            key_metrics=key_metrics_for_module("rate_pressure", market_metadata_reports),
            core_metric_keys=core_metric_keys,
            ai_blocked_metric_statuses=ai_blocked_metric_statuses,
            equity_historical_derived_metric_keys=equity_historical_derived_metric_keys,
            proxy_historical_derived_metric_keys=proxy_historical_derived_metric_keys,
            market_stress_historical_derived_metric_keys=market_stress_historical_derived_metric_keys,
        ),
        "real_yield_pressure": market_module(
            key="real_yield_pressure",
            label="real yield pressure",
            reports=market_metadata_reports,
            signal_terms=("real_yield_10y", "dfii10", "real_yield"),
            key_metrics=key_metrics_for_module("real_yield_pressure", market_metadata_reports),
            core_metric_keys=core_metric_keys,
            ai_blocked_metric_statuses=ai_blocked_metric_statuses,
            equity_historical_derived_metric_keys=equity_historical_derived_metric_keys,
            proxy_historical_derived_metric_keys=proxy_historical_derived_metric_keys,
            market_stress_historical_derived_metric_keys=market_stress_historical_derived_metric_keys,
        ),
        "inflation_energy_pressure": market_module(
            key="inflation_energy_pressure",
            label="inflation and energy pressure",
            reports=market_temperature_metadata_reports,
            signal_terms=("cpi", "pce", "ppi", "oil", "energy", "inflation"),
            key_metrics=key_metrics_for_module(
                "inflation_energy_pressure",
                market_temperature_metadata_reports,
                market_history_db_path=market_history_db_path,
            ),
            core_metric_keys=core_metric_keys,
            ai_blocked_metric_statuses=ai_blocked_metric_statuses,
            equity_historical_derived_metric_keys=equity_historical_derived_metric_keys,
            proxy_historical_derived_metric_keys=proxy_historical_derived_metric_keys,
            market_stress_historical_derived_metric_keys=market_stress_historical_derived_metric_keys,
        ),
        "equity_trend": market_module(
            key="equity_trend",
            label="equity trend",
            reports=market_temperature_metadata_reports,
            signal_terms=("sp500", "nasdaq", "nasdaq100", "equity_temperature", "equity"),
            key_metrics=key_metrics_for_module(
                "equity_trend",
                market_temperature_metadata_reports,
                market_history_db_path=market_history_db_path,
            ),
            core_metric_keys=core_metric_keys,
            ai_blocked_metric_statuses=ai_blocked_metric_statuses,
            equity_historical_derived_metric_keys=equity_historical_derived_metric_keys,
            proxy_historical_derived_metric_keys=proxy_historical_derived_metric_keys,
            market_stress_historical_derived_metric_keys=market_stress_historical_derived_metric_keys,
        ),
        "breadth_concentration_proxy": market_module(
            key="breadth_concentration_proxy",
            label="proxy breadth and concentration",
            reports=market_temperature_metadata_reports,
            signal_terms=("breadth", "concentration", "spy_proxy", "rsp_proxy", "qqq_proxy"),
            key_metrics=key_metrics_for_module(
                "breadth_concentration_proxy",
                market_temperature_metadata_reports,
                market_history_db_path=market_history_db_path,
            ),
            core_metric_keys=core_metric_keys,
            ai_blocked_metric_statuses=ai_blocked_metric_statuses,
            equity_historical_derived_metric_keys=equity_historical_derived_metric_keys,
            proxy_historical_derived_metric_keys=proxy_historical_derived_metric_keys,
            market_stress_historical_derived_metric_keys=market_stress_historical_derived_metric_keys,
        ),
        "market_stress_derived": market_module(
            key="market_stress_derived",
            label="market stress derived",
            reports=market_temperature_metadata_reports,
            signal_terms=("drawdown", "curve", "tlt_proxy", "gld_proxy", "shy_proxy"),
            key_metrics=key_metrics_for_module(
                "market_stress_derived",
                market_temperature_metadata_reports,
                market_history_db_path=market_history_db_path,
            ),
            core_metric_keys=core_metric_keys,
            ai_blocked_metric_statuses=ai_blocked_metric_statuses,
            equity_historical_derived_metric_keys=equity_historical_derived_metric_keys,
            proxy_historical_derived_metric_keys=proxy_historical_derived_metric_keys,
            market_stress_historical_derived_metric_keys=market_stress_historical_derived_metric_keys,
        ),
        "portfolio_deviation": portfolio_module(
            portfolio,
            key_metrics_for_module=key_metrics_for_module,
            portfolio_deviation_compact=portfolio_deviation_compact,
            portfolio_compact_module_status=portfolio_compact_module_status,
            core_metric_keys=core_metric_keys,
            ai_blocked_metric_statuses=ai_blocked_metric_statuses,
        ),
    }


def market_module(
    *,
    key: str,
    label: str,
    reports: tuple[ReportState, ...],
    signal_terms: tuple[str, ...],
    key_metrics: list[DashboardMetric],
    core_metric_keys: dict[str, set[str]],
    ai_blocked_metric_statuses: set[str],
    equity_historical_derived_metric_keys: set[str],
    proxy_historical_derived_metric_keys: set[str],
    market_stress_historical_derived_metric_keys: set[str],
) -> DashboardModule:
    error = first_error(reports)
    if error is not None:
        return module(
            key=key,
            status="error",
            label=label,
            summary=f"{label} report data is invalid",
            source_badge="report_error",
            error_summary=error,
            key_metrics=key_metrics,
            core_metric_keys=core_metric_keys,
            ai_blocked_metric_statuses=ai_blocked_metric_statuses,
        )

    available_reports = [report for report in reports if report.data is not None]
    if key == "equity_trend" and equity_historical_derived_metrics_available(
        key_metrics,
        metric_keys=equity_historical_derived_metric_keys,
    ):
        return module(
            key=key,
            status="ok",
            label=label,
            summary=(
                "equity trend historical derived metrics available; risk "
                "interpretation remains descriptive"
            ),
            source_badge="derived",
            updated_at=latest_metric_generated_at(key_metrics),
            key_metrics=key_metrics,
            core_metric_keys=core_metric_keys,
            ai_blocked_metric_statuses=ai_blocked_metric_statuses,
        )
    if key == "breadth_concentration_proxy" and proxy_historical_derived_metrics_available(
        key_metrics,
        metric_keys=proxy_historical_derived_metric_keys,
    ):
        return module(
            key=key,
            status="ok",
            label=label,
            summary=(
                "proxy breadth and concentration metrics available; yfinance ETF "
                "proxy boundary applies"
            ),
            source_badge="derived",
            updated_at=latest_metric_generated_at(key_metrics),
            key_metrics=key_metrics,
            core_metric_keys=core_metric_keys,
            ai_blocked_metric_statuses=ai_blocked_metric_statuses,
        )
    if key == "market_stress_derived" and market_stress_historical_derived_metrics_available(
        key_metrics,
        metric_keys=market_stress_historical_derived_metric_keys,
    ):
        return module(
            key=key,
            status="ok",
            label=label,
            summary=(
                "local drawdown, curve slope, and cross-asset proxy metrics "
                "available; descriptive boundaries apply"
            ),
            source_badge="derived",
            updated_at=latest_metric_generated_at(key_metrics),
            key_metrics=key_metrics,
            core_metric_keys=core_metric_keys,
            ai_blocked_metric_statuses=ai_blocked_metric_statuses,
        )
    if not available_reports:
        return module(
            key=key,
            status="missing",
            label=label,
            summary=f"{label} data missing",
            source_badge="missing_report",
            next_action=run_reports_action(),
            key_metrics=key_metrics,
            core_metric_keys=core_metric_keys,
            ai_blocked_metric_statuses=ai_blocked_metric_statuses,
        )

    if any(contains_signal(report.data, signal_terms) for report in available_reports):
        status = coerce_status(first_status(available_reports), default="ok")
        return module(
            key=key,
            status=status,
            label=label,
            summary=f"{label} compact data available",
            source_badge="cached_report",
            updated_at=first_updated_at(available_reports),
            key_metrics=key_metrics,
            core_metric_keys=core_metric_keys,
            ai_blocked_metric_statuses=ai_blocked_metric_statuses,
        )

    return module(
        key=key,
        status="missing",
        label=label,
        summary=f"{label} compact signal missing",
        source_badge="cached_report",
        updated_at=first_updated_at(available_reports),
        next_action=run_reports_action(),
        key_metrics=key_metrics,
        core_metric_keys=core_metric_keys,
        ai_blocked_metric_statuses=ai_blocked_metric_statuses,
    )


def portfolio_module(
    report: ReportState,
    *,
    key_metrics_for_module: KeyMetricsForModule,
    portfolio_deviation_compact: PortfolioCompactBuilder,
    portfolio_compact_module_status: PortfolioCompactStatusBuilder,
    core_metric_keys: dict[str, set[str]],
    ai_blocked_metric_statuses: set[str],
) -> DashboardModule:
    key_metrics = key_metrics_for_module("portfolio_deviation", (report,))
    if report.error_summary is not None:
        return module(
            key="portfolio_deviation",
            status="error",
            label="portfolio deviation",
            summary="portfolio snapshot invalid",
            source_badge="report_error",
            error_summary=report.error_summary,
            key_metrics=key_metrics,
            core_metric_keys=core_metric_keys,
            ai_blocked_metric_statuses=ai_blocked_metric_statuses,
        )
    if report.data is None:
        return module(
            key="portfolio_deviation",
            status="missing",
            label="missing",
            summary="portfolio snapshot missing",
            source_badge="missing_report",
            next_action="python scripts/run_portfolio_check.py",
            key_metrics=key_metrics,
            core_metric_keys=core_metric_keys,
            ai_blocked_metric_statuses=ai_blocked_metric_statuses,
        )
    compact = portfolio_deviation_compact(report)
    if compact is not None:
        return module(
            key="portfolio_deviation",
            status=portfolio_compact_module_status(compact),
            label="compact",
            summary="portfolio deviation compact data available",
            source_badge="cached_report",
            updated_at=compact.generated_at,
            key_metrics=key_metrics,
            core_metric_keys=core_metric_keys,
            ai_blocked_metric_statuses=ai_blocked_metric_statuses,
        )
    return module(
        key="portfolio_deviation",
        status=coerce_status(report.data.get("status"), default="ok"),
        label="available",
        summary="portfolio snapshot available",
        source_badge="cached_report",
        updated_at=string_or_none(
            report.data.get("generated_at") or report.data.get("updated_at")
        ),
        key_metrics=key_metrics,
        core_metric_keys=core_metric_keys,
        ai_blocked_metric_statuses=ai_blocked_metric_statuses,
    )


def module(
    key: str,
    status: str,
    label: str | None,
    summary: str | None,
    source_badge: str | None,
    updated_at: str | None = None,
    next_action: str | None = None,
    error_summary: str | None = None,
    key_metrics: list[DashboardMetric] | None = None,
    *,
    core_metric_keys: dict[str, set[str]],
    ai_blocked_metric_statuses: set[str],
) -> DashboardModule:
    metrics = key_metrics or []
    coerced_status = coerce_status(status)
    adjusted_status, coverage_note = module_status_with_coverage(
        key,
        coerced_status,
        metrics,
        core_metric_keys=core_metric_keys,
        ai_blocked_metric_statuses=ai_blocked_metric_statuses,
    )
    adjusted_summary = summary_with_coverage_note(summary, coverage_note)
    return DashboardModule(
        key=key,
        status=adjusted_status,
        label=label,
        summary=adjusted_summary,
        source_badge=source_badge,
        updated_at=updated_at,
        next_action=next_action,
        error_summary=safe_error_summary(error_summary),
        key_metrics=metrics,
    )


def equity_historical_derived_metrics_available(
    metrics: list[DashboardMetric],
    *,
    metric_keys: set[str],
) -> bool:
    return _historical_derived_metrics_available(metrics, metric_keys=metric_keys)


def proxy_historical_derived_metrics_available(
    metrics: list[DashboardMetric],
    *,
    metric_keys: set[str],
) -> bool:
    return _historical_derived_metrics_available(metrics, metric_keys=metric_keys)


def market_stress_historical_derived_metrics_available(
    metrics: list[DashboardMetric],
    *,
    metric_keys: set[str],
) -> bool:
    return _historical_derived_metrics_available(metrics, metric_keys=metric_keys)


def _historical_derived_metrics_available(
    metrics: list[DashboardMetric],
    *,
    metric_keys: set[str],
) -> bool:
    return any(
        metric.metric_key in metric_keys
        and metric.status == "ok"
        and metric.source_badge == "derived"
        and metric.value is not None
        for metric in metrics
    )


def latest_metric_generated_at(metrics: list[DashboardMetric]) -> str | None:
    candidates = [
        value
        for metric in metrics
        for value in [metric.generated_at or metric.observation_date]
        if value
    ]
    return max(candidates) if candidates else None


def module_status_with_coverage(
    module_key: str,
    status: str,
    key_metrics: list[DashboardMetric],
    *,
    core_metric_keys: dict[str, set[str]],
    ai_blocked_metric_statuses: set[str],
) -> tuple[str, str | None]:
    if status in {"error", "missing", "stale"}:
        return status, None
    core_metrics = [
        metric
        for metric in key_metrics
        if metric.metric_key in core_metric_keys.get(module_key, set())
    ]
    if not core_metrics:
        return status, None

    blocked = [
        metric for metric in core_metrics if metric.status in ai_blocked_metric_statuses
    ]
    stale = [metric for metric in core_metrics if metric.freshness_status == "stale"]
    if len(blocked) == len(core_metrics):
        return "unknown", "core metric coverage unavailable"
    if stale:
        return "stale", "one or more core metrics are stale"
    if blocked and status == "ok":
        return "unknown", "partial core metric coverage"
    return status, None


def summary_with_coverage_note(summary: str | None, coverage_note: str | None) -> str | None:
    if not coverage_note:
        return summary
    if not summary:
        return coverage_note
    if coverage_note in summary:
        return summary
    return f"{summary}; {coverage_note}"
