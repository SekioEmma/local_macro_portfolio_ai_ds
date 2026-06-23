from __future__ import annotations

from pathlib import Path
from typing import Callable

from app_backend.schemas.responses import DashboardMetric
from app_backend.services.dashboard_historical_derived import (
    EQUITY_HISTORICAL_DERIVED_HINT_SUFFIX,
    EQUITY_HISTORICAL_DERIVED_METRIC_KEYS,
    MARKET_STRESS_HISTORICAL_DERIVED_METRIC_KEYS,
    OIL_HISTORICAL_DERIVED_HINT_SUFFIX,
    OIL_HISTORICAL_DERIVED_METRIC_KEYS,
    PPI_FINAL_DEMAND_HISTORICAL_DERIVED_METRIC_KEYS,
    PROXY_BREADTH_HISTORICAL_DERIVED_METRIC_KEYS,
)
from app_backend.services.dashboard_metric_catalog import METRIC_SPECS
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
    build_metric: BuildMetric,
    apply_historical_derived_metrics: ApplyHistoricalDerived,
    apply_ppi_final_demand_history: ApplyPpiFinalDemand,
    compact_dgs_fallback_observations: CompactDgsFallback,
    metric_specs: dict[str, list[tuple[str, str, str | None, str, str]]] = METRIC_SPECS,
    equity_historical_derived_metric_keys: set[str] = EQUITY_HISTORICAL_DERIVED_METRIC_KEYS,
    oil_historical_derived_metric_keys: set[str] = OIL_HISTORICAL_DERIVED_METRIC_KEYS,
    ppi_final_demand_historical_derived_metric_keys: set[str] = PPI_FINAL_DEMAND_HISTORICAL_DERIVED_METRIC_KEYS,
    proxy_breadth_historical_derived_metric_keys: set[str] = PROXY_BREADTH_HISTORICAL_DERIVED_METRIC_KEYS,
    market_stress_historical_derived_metric_keys: set[str] = MARKET_STRESS_HISTORICAL_DERIVED_METRIC_KEYS,
    equity_historical_derived_hint_suffix: str = EQUITY_HISTORICAL_DERIVED_HINT_SUFFIX,
    oil_historical_derived_hint_suffix: str = OIL_HISTORICAL_DERIVED_HINT_SUFFIX,
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
