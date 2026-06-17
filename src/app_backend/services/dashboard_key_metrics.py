from __future__ import annotations

from pathlib import Path
from typing import Callable

from app_backend.schemas.responses import DashboardMetric
from app_backend.services.dashboard_report_loader import ReportState


BuildMetric = Callable[
    [str, tuple[ReportState, ...], tuple[str, str, str | None, str, str]],
    DashboardMetric,
]
ApplyHistoricalDerived = Callable[..., list[DashboardMetric]]
ApplyPpiFinalDemand = Callable[..., list[DashboardMetric]]
CompactDgsFallback = Callable[[tuple[ReportState, ...]], dict[str, dict[str, object]]]


def key_metrics_for_module(
    module_key: str,
    reports: tuple[ReportState, ...],
    *,
    market_history_db_path: Path | str | None = None,
    metric_specs: dict[str, list[tuple[str, str, str | None, str, str]]],
    build_metric: BuildMetric,
    apply_historical_derived_metrics: ApplyHistoricalDerived,
    apply_ppi_final_demand_history: ApplyPpiFinalDemand,
    compact_dgs_fallback_observations: CompactDgsFallback,
    equity_historical_derived_metric_keys: set[str],
    oil_historical_derived_metric_keys: set[str],
    ppi_final_demand_historical_derived_metric_keys: set[str],
    proxy_breadth_historical_derived_metric_keys: set[str],
    market_stress_historical_derived_metric_keys: set[str],
    equity_historical_derived_hint_suffix: str,
    oil_historical_derived_hint_suffix: str,
) -> list[DashboardMetric]:
    metrics = [
        build_metric(module_key, reports, spec)
        for spec in metric_specs.get(module_key, [])
    ]
    if module_key == "equity_trend":
        return apply_historical_derived_metrics(
            metrics,
            module_key="equity_trend",
            metric_keys=equity_historical_derived_metric_keys,
            hint_suffix=equity_historical_derived_hint_suffix,
            fallback_source="local_market_history",
            db_path=market_history_db_path,
        )
    if module_key == "inflation_energy_pressure":
        metrics = apply_ppi_final_demand_history(
            metrics,
            db_path=market_history_db_path,
        )
        metrics = apply_historical_derived_metrics(
            metrics,
            module_key="inflation_energy_pressure",
            metric_keys=oil_historical_derived_metric_keys,
            hint_suffix=oil_historical_derived_hint_suffix,
            fallback_source="local_market_history",
            required_dependency_source_badges={"official"},
            replace_existing=True,
            db_path=market_history_db_path,
        )
        return apply_historical_derived_metrics(
            metrics,
            module_key="inflation_energy_pressure",
            metric_keys=ppi_final_demand_historical_derived_metric_keys,
            hint_suffix="",
            fallback_source="local_market_history",
            required_dependency_source_badges={"official"},
            replace_existing=True,
            db_path=market_history_db_path,
        )
    if module_key == "breadth_concentration_proxy":
        return apply_historical_derived_metrics(
            metrics,
            module_key="breadth_concentration_proxy",
            metric_keys=proxy_breadth_historical_derived_metric_keys,
            hint_suffix="",
            fallback_source="local_market_history",
            required_dependency_source_badges={"proxy"},
            db_path=market_history_db_path,
        )
    if module_key == "market_stress_derived":
        return apply_historical_derived_metrics(
            metrics,
            module_key="market_stress_derived",
            metric_keys=market_stress_historical_derived_metric_keys,
            hint_suffix="",
            fallback_source="local_market_history",
            fallback_observations=compact_dgs_fallback_observations(reports),
            db_path=market_history_db_path,
        )
    return metrics
