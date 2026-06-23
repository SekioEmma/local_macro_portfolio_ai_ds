from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from functools import partial
from typing import Any

from app_backend.services import (
    dashboard_derived_metrics,
    dashboard_historical_derived,
    dashboard_key_metrics,
    dashboard_metric_builder,
    dashboard_module_builder,
    dashboard_portfolio_compact,
)


@dataclass(frozen=True)
class DashboardBuilders:
    build_metric: Callable[..., Any]
    key_metrics_for_module: Callable[..., Any]
    build_modules: Callable[..., Any]
    apply_historical_derived_metrics: Callable[..., Any]
    apply_labor_history_fallback: Callable[..., Any]


def compose_dashboard_builders() -> DashboardBuilders:
    build_metric = partial(
        dashboard_metric_builder.build_metric,
        derived_metric=dashboard_derived_metrics.derived_metric,
        portfolio_compact_metric=dashboard_portfolio_compact.portfolio_compact_metric,
    )
    key_metrics_for_module = partial(
        dashboard_key_metrics.key_metrics_for_module,
        build_metric=build_metric,
        apply_historical_derived_metrics=dashboard_historical_derived.apply_historical_derived_metrics,
        apply_ppi_final_demand_history=dashboard_historical_derived.apply_ppi_final_demand_history,
        compact_dgs_fallback_observations=dashboard_historical_derived.compact_dgs_fallback_observations,
    )
    build_modules = partial(
        dashboard_module_builder.build_modules,
        key_metrics_for_module=key_metrics_for_module,
        portfolio_deviation_compact=dashboard_portfolio_compact.portfolio_deviation_compact,
        portfolio_compact_module_status=dashboard_portfolio_compact.portfolio_compact_module_status,
    )
    return DashboardBuilders(
        build_metric=build_metric,
        key_metrics_for_module=key_metrics_for_module,
        build_modules=build_modules,
        apply_historical_derived_metrics=dashboard_historical_derived.apply_historical_derived_metrics,
        apply_labor_history_fallback=dashboard_historical_derived.apply_labor_history_fallback,
    )
