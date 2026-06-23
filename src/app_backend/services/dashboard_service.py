from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from app_backend.schemas.responses import (
    DashboardEvidenceRow,
    DashboardEvidenceTableResponse,
    DashboardMetric,
    DashboardModule,
    DashboardSummaryResponse,
)
from app_backend.services.dashboard_cache_adapter import (
    DASHBOARD_CONTEXT_CACHE_SCHEMA_MARKER,
    build_dashboard_cache_key_for_request as _build_dashboard_cache_key_for_request,
    resolve_dashboard_market_history_db_path,
    resolved_path as _resolved_path,
    same_path as _same_path,
    shared_cache_bypass_reason,
)
from app_backend.services.dashboard_context import DashboardPipelineContext
from app_backend.services.dashboard_context_cache import (
    CachedDashboardContext,
    SharedDashboardContextCache,
)
from app_backend.services.dashboard_composition import compose_dashboard_builders
from app_backend.services.dashboard_derived_metrics import (
    blocked_dependency_metric as _blocked_dependency_metric,
    credit_stress_status_metric as _derived_credit_stress_status_metric,
    credit_status_from_values as _credit_status_from_values,
    derived_metric as _derived_metrics_derived_metric,
    derived_metric_response as _derived_metric_response,
    has_breakout_history_evidence as _has_breakout_history_evidence,
    latest_metric_observation_date as _derived_latest_metric_observation_date,
    latest_metric_timestamp as _derived_latest_metric_timestamp,
    real_yield_pressure_status_metric as _derived_real_yield_pressure_status_metric,
    real_yield_status_from_values as _real_yield_status_from_values,
    usable_numeric_metric as _derived_usable_numeric_metric,
)
from app_backend.services.dashboard_evidence_assembly import (
    build_evidence_table_response as _build_evidence_table_response,
    evidence_filters as _evidence_filters,
    evidence_request_is_unfiltered as _evidence_request_is_unfiltered,
    evidence_rows_from_summary as _evidence_rows_from_summary,
    evidence_table_from_unfiltered as _evidence_table_from_unfiltered,
)
from app_backend.services.dashboard_filters import (
    apply_evidence_filters,
    evidence_row_matches,
)
from app_backend.services.dashboard_historical_derived import (
    EQUITY_HISTORICAL_DERIVED_HINT_SUFFIX,
    EQUITY_HISTORICAL_DERIVED_METRIC_KEYS,
    LABOR_HISTORICAL_DERIVED_METRIC_KEYS,
    MARKET_STRESS_HISTORICAL_DERIVED_METRIC_KEYS,
    OIL_HISTORICAL_DERIVED_HINT_SUFFIX,
    OIL_HISTORICAL_DERIVED_METRIC_KEYS,
    PPI_FINAL_DEMAND_HISTORICAL_DERIVED_METRIC_KEYS,
    PROXY_BREADTH_HISTORICAL_DERIVED_METRIC_KEYS,
    apply_historical_derived_metrics as _historical_derived_apply_historical_derived_metrics,
    apply_labor_history_fallback as _historical_derived_apply_labor_history_fallback,
    apply_ppi_final_demand_history as _historical_derived_apply_ppi_final_demand_history,
    compact_dgs_fallback_observations as _historical_derived_compact_dgs_fallback_observations,
    dashboard_historical_derived_hint as _dashboard_historical_derived_hint,
    dashboard_historical_derived_value as _dashboard_historical_derived_value,
    format_historical_derived_value as _format_historical_derived_value,
    historical_derived_metric as _historical_derived_metric,
    is_labor_official_metric as _is_labor_official_metric,
    labor_history_fallback_needed as _labor_history_fallback_needed,
    labor_history_freshness_status as _labor_history_freshness_status,
    labor_history_metric as _labor_history_metric,
    latest_official_labor_observation as _latest_official_labor_observation,
    latest_ppifis_observation as _latest_ppifis_observation,
    parse_iso_date as _parse_iso_date,
    ppi_final_demand_history_metric as _ppi_final_demand_history_metric,
)
from app_backend.services.dashboard_key_metrics import (
    key_metrics_for_module as _key_metrics_builder_key_metrics_for_module,
)
from app_backend.services.dashboard_metric_catalog import (
    CORE_METRIC_KEYS,
    DASHBOARD_MODULE_KEYS,
    DERIVED_METRIC_KEYS,
    DGS30_BREAKOUT_MISSING_REASON,
    LABOR_METRIC_SPECS,
    METRIC_ALIASES,
    METRIC_SPECS,
)
from app_backend.services.dashboard_metric_builder import (
    ALLOWED_METRIC_STATUSES,
    ALLOWED_SOURCE_BADGES,
    INDEX_LEVEL_YOY_MISSING_REASON,
    INFLATION_YOY_METRIC_KEYS,
    SOURCE_BADGE_ALIASES,
    build_metric as _metric_builder_build_metric,
    dependency_unusable as _dependency_unusable,
    find_metric as _metric_builder_find_metric,
    find_metric_payload as _find_metric_payload,
    first_metric_quality_metadata as _first_metric_quality_metadata,
    format_value as _format_value,
    interpretation_hint as _metric_builder_interpretation_hint,
    metric_freshness as _metric_freshness,
    metric_generated_at as _metric_generated_at,
    metric_interpretation_hint as _metric_builder_metric_interpretation_hint,
    metric_observation_date as _metric_observation_date,
    metric_quality_metadata as _metric_quality_metadata,
    metric_source as _metric_source,
    metric_source_badge as _metric_builder_metric_source_badge,
    metric_source_series as _metric_source_series,
    metric_status as _metric_status,
    metric_status_value as _metric_status_value,
    missing_metric as _metric_builder_missing_metric,
    normalize_inflation_yoy_value as _normalize_inflation_yoy_value,
    payload_declares_index_level as _payload_declares_index_level,
    to_float as _to_float,
)
from app_backend.services.dashboard_module_builder import (
    build_modules as _module_builder_build_modules,
    equity_historical_derived_metrics_available as _module_builder_equity_historical_derived_metrics_available,
    latest_metric_generated_at as _module_builder_latest_metric_generated_at,
    market_module as _module_builder_market_module,
    market_stress_historical_derived_metrics_available as _module_builder_market_stress_historical_derived_metrics_available,
    module as _module_builder_module,
    module_status_with_coverage as _module_builder_module_status_with_coverage,
    portfolio_module as _module_builder_portfolio_module,
    proxy_historical_derived_metrics_available as _module_builder_proxy_historical_derived_metrics_available,
    summary_with_coverage_note as _summary_with_coverage_note,
)
from app_backend.services.dashboard_report_loader import (
    OPTIONAL_METADATA_REPORT_FILES,
    REPORT_FILES,
    ReportState,
    load_dashboard_reports as _load_dashboard_reports,
    load_report as _load_report,
)
from app_backend.services.dashboard_summary_assembly import (
    MAX_ERROR_SUMMARY_LENGTH,
    coerce_status as _coerce_status,
    compact_missing_entries as _compact_missing_entries,
    contains_signal as _contains_signal,
    data_freshness as _data_freshness,
    first_error as _first_error,
    first_generated_at as _first_generated_at,
    first_status as _first_status,
    first_updated_at as _first_updated_at,
    freshness_status as _freshness_status,
    missing_data as _missing_data,
    model_to_dict as _model_to_dict,
    next_action_for_report as _next_action_for_report,
    next_actions as _next_actions,
    overall_risk_level as _overall_risk_level,
    overall_status as _overall_status,
    provider_health_summary as _provider_health_summary,
    report_status as _report_status,
    run_reports_action as _run_reports_action,
    safe_error_summary as _safe_error_summary,
    string_or_none as _string_or_none,
)
from app_backend.services import provider_service
from app_backend.services.dashboard_evidence_policy import (
    AI_BLOCKED_FRESHNESS_STATUSES,
    AI_BLOCKED_METRIC_STATUSES,
    AI_BLOCKED_SOURCE_BADGES,
    ai_context_allowed as _ai_context_allowed,
    ai_context_blocked_reason as _ai_context_blocked_reason,
    build_evidence_row as _evidence_row,
    derived_dependency_hint_complete as _derived_dependency_hint_complete,
    evidence_ai_context_allowed as _evidence_ai_context_allowed,
    evidence_value_text as _evidence_value_text,
    missing_value_text as _missing_value_text,
    ppi_observation_date_blocked_reason as _ppi_observation_date_blocked_reason,
)
from app_backend.services.dashboard_model_pipeline import build_dashboard_model_rows
from app_backend.services.dashboard_portfolio_compact import (
    PORTFOLIO_COMPACT_INTERPRETATION_HINT,
    PORTFOLIO_DEFAULT_TARGET_WEIGHTS,
    PORTFOLIO_TARGET_ASSET_CLASSES,
    PortfolioDeviationCompact,
    max_deviation_asset as _max_deviation_asset,
    parse_date as _parse_date,
    portfolio_cash_reserve_status as _portfolio_cash_reserve_status,
    portfolio_compact_metric as _portfolio_compact_metric,
    portfolio_compact_metric_status as _portfolio_compact_metric_status,
    portfolio_compact_module_status as _portfolio_compact_module_status,
    portfolio_deviation_compact as _portfolio_deviation_compact,
    portfolio_deviation_pp_map as _portfolio_deviation_pp_map,
    portfolio_deviation_status as _portfolio_deviation_status,
    portfolio_holdings_updated_at as _portfolio_holdings_updated_at,
    portfolio_stale_status as _portfolio_stale_status,
    portfolio_weight_map as _portfolio_weight_map,
    sum_weights as _sum_weights,
    weight_fraction as _weight_fraction,
)
from data_quality import last_good_cache
from data_quality.historical_derived_metrics import invalidate_historical_candidates_cache
from data_providers import market_history_store


PROJECT_ROOT = Path(__file__).resolve().parents[3]
PROJECT_REPORTS_DIR = PROJECT_ROOT / "outputs" / "reports"
DEFAULT_REPORTS_DIR = PROJECT_REPORTS_DIR
DEFAULT_MARKET_HISTORY_DB_PATH = market_history_store.get_default_market_history_db_path()
_SHARED_DASHBOARD_CONTEXT_CACHE = SharedDashboardContextCache()
_DASHBOARD_BUILDERS = compose_dashboard_builders()

def build_dashboard_summary(
    reports_dir: Path | str | None = None,
    market_history_db_path: Path | str | None = None,
    context: DashboardPipelineContext | None = None,
) -> DashboardSummaryResponse:
    if context is not None and context.summary is not None:
        return context.summary
    invalidate_historical_candidates_cache()
    base_dir = Path(reports_dir) if reports_dir is not None else DEFAULT_REPORTS_DIR
    dashboard_market_history_db_path = _dashboard_market_history_db_path(
        base_dir,
        market_history_db_path,
    )
    cache_key = _build_dashboard_cache_key_for_request(
        reports_dir=base_dir,
        market_history_db_path=dashboard_market_history_db_path,
    )
    if _shared_cache_bypass_reason(
        reports_dir=reports_dir,
        base_dir=base_dir,
        market_history_db_path=market_history_db_path,
        dashboard_market_history_db_path=dashboard_market_history_db_path,
        write_last_good=False,
    ) is None:
        cached = _SHARED_DASHBOARD_CONTEXT_CACHE.get(cache_key.digest)
        if cached is not None:
            if context is not None:
                context.summary = cached.summary
            return cached.summary
    reports = _load_dashboard_reports(base_dir)
    provider_health = _provider_health_summary(
        base_dir / REPORT_FILES["provider_health"]
    )
    modules = _DASHBOARD_BUILDERS.build_modules(
        reports,
        market_history_db_path=dashboard_market_history_db_path,
    )
    missing_data = _missing_data(reports)
    data_freshness = _data_freshness(reports, provider_health)
    next_actions = _next_actions(modules, provider_health)

    summary = DashboardSummaryResponse(
        generated_at=_first_generated_at(reports, provider_health),
        overall_status=_overall_status(modules, provider_health),
        overall_risk_level=_overall_risk_level(reports),
        modules=modules,
        provider_health=provider_health,
        missing_data=missing_data,
        data_freshness=data_freshness,
        next_actions=next_actions,
    )
    if _shared_cache_bypass_reason(
        reports_dir=reports_dir,
        base_dir=base_dir,
        market_history_db_path=market_history_db_path,
        dashboard_market_history_db_path=dashboard_market_history_db_path,
        write_last_good=False,
    ) is None:
        existing = _SHARED_DASHBOARD_CONTEXT_CACHE.get(cache_key.digest)
        if existing is None:
            _SHARED_DASHBOARD_CONTEXT_CACHE.set(
                CachedDashboardContext(
                    key_digest=cache_key.digest,
                    summary=summary,
                )
            )
    if context is not None:
        context.summary = summary
    return summary


def _try_evidence_cache_hit(
    key_digest: str,
    module: str | None,
    status: str | None,
    source_badge: str | None,
    ai_context_allowed: bool | None,
    write_last_good: bool,
    reports_dir: Path | str | None,
    context: DashboardPipelineContext | None,
) -> DashboardEvidenceTableResponse | None:
    cached = _SHARED_DASHBOARD_CONTEXT_CACHE.get(key_digest)
    if cached is None:
        return None
    if cached.unfiltered_evidence_table is not None:
        if write_last_good and _last_good_write_allowed(reports_dir):
            _save_last_good_candidates(list(cached.unfiltered_evidence_table.rows))
        evidence_table = _evidence_table_from_unfiltered(
            cached.unfiltered_evidence_table,
            module=module,
            status=status,
            source_badge=source_badge,
            ai_context_allowed=ai_context_allowed,
        )
        if context is not None:
            context.summary = cached.summary
            if _evidence_request_is_unfiltered(
                module=module,
                status=status,
                source_badge=source_badge,
                ai_context_allowed=ai_context_allowed,
            ):
                context.evidence_table = evidence_table
        return evidence_table
    if cached.summary is not None and context is not None:
        context.summary = cached.summary
    return None


def build_dashboard_evidence_table(
    reports_dir: Path | str | None = None,
    market_history_db_path: Path | str | None = None,
    module: str | None = None,
    status: str | None = None,
    source_badge: str | None = None,
    ai_context_allowed: bool | None = None,
    write_last_good: bool = True,
    context: DashboardPipelineContext | None = None,
) -> DashboardEvidenceTableResponse:
    if (
        context is not None
        and context.evidence_table is not None
        and _evidence_request_is_unfiltered(
            module=module,
            status=status,
            source_badge=source_badge,
            ai_context_allowed=ai_context_allowed,
        )
        and write_last_good is False
    ):
        return context.evidence_table
    base_dir = Path(reports_dir) if reports_dir is not None else DEFAULT_REPORTS_DIR
    context_summary_preloaded = context is not None and context.summary is not None
    dashboard_market_history_db_path = _dashboard_market_history_db_path(
        base_dir,
        market_history_db_path,
    )
    cache_key = _build_dashboard_cache_key_for_request(
        reports_dir=base_dir,
        market_history_db_path=dashboard_market_history_db_path,
    )
    path_bypass = _shared_cache_bypass_reason(
        reports_dir=reports_dir,
        base_dir=base_dir,
        market_history_db_path=market_history_db_path,
        dashboard_market_history_db_path=dashboard_market_history_db_path,
        write_last_good=False,
    )
    cache_allowed = path_bypass is None and not context_summary_preloaded
    if cache_allowed:
        hit = _try_evidence_cache_hit(
            cache_key.digest, module, status, source_badge,
            ai_context_allowed, write_last_good, reports_dir, context,
        )
        if hit is not None:
            return hit
    with _SHARED_DASHBOARD_CONTEXT_CACHE.build_lock:
        if cache_allowed:
            hit = _try_evidence_cache_hit(
                cache_key.digest, module, status, source_badge,
                ai_context_allowed, write_last_good, reports_dir, context,
            )
            if hit is not None:
                return hit
        if context is not None and context.summary is not None:
            summary = context.summary
        else:
            summary = build_dashboard_summary(
                reports_dir=reports_dir,
                market_history_db_path=market_history_db_path,
                context=context,
            )
        reports = _load_dashboard_reports(base_dir)
        base_rows = _evidence_rows_from_summary(summary) + _labor_macro_evidence_rows(
            reports,
            db_path=dashboard_market_history_db_path,
        )
        _pipeline = build_dashboard_model_rows(
            base_rows=base_rows,
            db_path=dashboard_market_history_db_path,
            build_evidence_row=_evidence_row,
        )
        all_rows = base_rows + _pipeline.rows
        if write_last_good and _last_good_write_allowed(reports_dir):
            _save_last_good_candidates(all_rows)
        unfiltered_evidence_table = _build_evidence_table_response(
            summary=summary,
            all_rows=all_rows,
            filtered_rows=all_rows,
            module=None,
            status=None,
            source_badge=None,
            ai_context_allowed=None,
        )
        if cache_allowed:
            _SHARED_DASHBOARD_CONTEXT_CACHE.set(
                CachedDashboardContext(
                    key_digest=cache_key.digest,
                    summary=summary,
                    unfiltered_evidence_table=unfiltered_evidence_table,
                )
            )
    evidence_table = _evidence_table_from_unfiltered(
        unfiltered_evidence_table,
        module=module,
        status=status,
        source_badge=source_badge,
        ai_context_allowed=ai_context_allowed,
    )
    if (
        context is not None
        and _evidence_request_is_unfiltered(
            module=module,
            status=status,
            source_badge=source_badge,
            ai_context_allowed=ai_context_allowed,
        )
        and write_last_good is False
    ):
        context.evidence_table = evidence_table
    return evidence_table


def _dashboard_market_history_db_path(
    reports_dir: Path,
    market_history_db_path: Path | str | None,
) -> Path | str:
    return resolve_dashboard_market_history_db_path(
        reports_dir,
        market_history_db_path,
        default_market_history_db_path=DEFAULT_MARKET_HISTORY_DB_PATH,
        project_reports_dir=PROJECT_REPORTS_DIR,
        current_default_provider=market_history_store.get_default_market_history_db_path,
    )


def _shared_cache_bypass_reason(
    *,
    reports_dir: Path | str | None,
    base_dir: Path,
    market_history_db_path: Path | str | None,
    dashboard_market_history_db_path: Path | str,
    write_last_good: bool,
) -> str | None:
    default_market_history_db_path = _dashboard_market_history_db_path(
        DEFAULT_REPORTS_DIR,
        None,
    )
    return shared_cache_bypass_reason(
        reports_dir=reports_dir,
        base_dir=base_dir,
        market_history_db_path=market_history_db_path,
        dashboard_market_history_db_path=dashboard_market_history_db_path,
        write_last_good=write_last_good,
        default_reports_dir=DEFAULT_REPORTS_DIR,
        default_market_history_db_path_for_default_reports=default_market_history_db_path,
    )


def _labor_macro_evidence_rows(
    reports: dict[str, ReportState],
    *,
    db_path: Path | str | None = None,
) -> list[DashboardEvidenceRow]:
    market = reports["market_snapshot"]
    llm_context = reports.get("llm_context_pack")
    metric_reports = (market, llm_context) if llm_context else (market,)
    metrics = [
        _DASHBOARD_BUILDERS.build_metric("labor_macro", metric_reports, spec)
        for spec in LABOR_METRIC_SPECS
    ]
    metrics = _DASHBOARD_BUILDERS.apply_labor_history_fallback(
        metrics,
        db_path=db_path,
    )
    metrics = _DASHBOARD_BUILDERS.apply_historical_derived_metrics(
        metrics,
        module_key="labor_macro",
        metric_keys=LABOR_HISTORICAL_DERIVED_METRIC_KEYS,
        hint_suffix="",
        fallback_source="market_history",
        required_dependency_source_badges={"official"},
        replace_existing=True,
        db_path=db_path,
    )
    return [_evidence_row("labor_macro", metric) for metric in metrics]


def _last_good_write_allowed(reports_dir: Path | str | None) -> bool:
    return reports_dir is None and Path(DEFAULT_REPORTS_DIR) == PROJECT_REPORTS_DIR


def _save_last_good_candidates(rows: list[DashboardEvidenceRow]) -> None:
    for row in rows:
        if row.module in {"portfolio_deviation", "portfolio_exposure_overlay"}:
            continue
        if not row.ai_context_allowed:
            continue
        try:
            last_good_cache.save_last_good(row)
        except (OSError, ValueError):
            continue


def _evidence_row_matches(
    row: DashboardEvidenceRow,
    module: str | None,
    status: str | None,
    source_badge: str | None,
    ai_context_allowed: bool | None,
) -> bool:
    return evidence_row_matches(
        row,
        module=module,
        status=status,
        source_badge=source_badge,
        ai_context_allowed=ai_context_allowed,
    )


def _build_modules(
    reports: dict[str, ReportState],
    *,
    market_history_db_path: Path | str | None = None,
) -> dict[str, DashboardModule]:
    return _module_builder_build_modules(
        reports,
        market_history_db_path=market_history_db_path,
        key_metrics_for_module=_key_metrics_for_module,
        portfolio_deviation_compact=_portfolio_deviation_compact,
        portfolio_compact_module_status=_portfolio_compact_module_status,
    )


def _market_module(
    key: str,
    label: str,
    reports: tuple[ReportState, ...],
    signal_terms: tuple[str, ...],
    key_metrics: list[DashboardMetric],
) -> DashboardModule:
    return _module_builder_market_module(
        key=key,
        label=label,
        reports=reports,
        signal_terms=signal_terms,
        key_metrics=key_metrics,
    )


def _portfolio_module(report: ReportState) -> DashboardModule:
    return _module_builder_portfolio_module(
        report,
        key_metrics_for_module=_key_metrics_for_module,
        portfolio_deviation_compact=_portfolio_deviation_compact,
        portfolio_compact_module_status=_portfolio_compact_module_status,
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
    return _module_builder_module(
        key,
        status,
        label,
        summary,
        source_badge,
        updated_at=updated_at,
        next_action=next_action,
        error_summary=error_summary,
        key_metrics=key_metrics,
    )


def _key_metrics_for_module(
    module_key: str,
    reports: tuple[ReportState, ...],
    *,
    market_history_db_path: Path | str | None = None,
) -> list[DashboardMetric]:
    return _key_metrics_builder_key_metrics_for_module(
        module_key,
        reports,
        market_history_db_path=market_history_db_path,
        build_metric=_build_metric,
        apply_historical_derived_metrics=_apply_historical_derived_metrics,
        apply_ppi_final_demand_history=_apply_ppi_final_demand_history,
        compact_dgs_fallback_observations=_compact_dgs_fallback_observations,
    )


def _build_metric(
    module_key: str,
    reports: tuple[ReportState, ...],
    spec: tuple[str, str, str | None, str, str],
) -> DashboardMetric:
    return _metric_builder_build_metric(
        module_key,
        reports,
        spec,
        derived_metric=_derived_metric,
        portfolio_compact_metric=_portfolio_compact_metric,
        find_metric_callback=_find_metric,
    )


def _apply_historical_derived_metrics(
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
) -> list[DashboardMetric]:
    return _historical_derived_apply_historical_derived_metrics(
        metrics,
        module_key=module_key,
        metric_keys=metric_keys,
        hint_suffix=hint_suffix,
        fallback_source=fallback_source,
        fallback_observations=fallback_observations,
        required_dependency_source_badges=required_dependency_source_badges,
        replace_existing=replace_existing,
        db_path=db_path,
    )


def _apply_ppi_final_demand_history(
    metrics: list[DashboardMetric],
    *,
    db_path: Path | str | None = None,
) -> list[DashboardMetric]:
    return _historical_derived_apply_ppi_final_demand_history(
        metrics,
        db_path=db_path,
    )


def _apply_labor_history_fallback(
    metrics: list[DashboardMetric],
    *,
    db_path: Path | str | None = None,
) -> list[DashboardMetric]:
    return _historical_derived_apply_labor_history_fallback(
        metrics,
        db_path=db_path,
    )


def _compact_dgs_fallback_observations(
    reports: tuple[ReportState, ...],
) -> dict[str, dict[str, Any]]:
    return _historical_derived_compact_dgs_fallback_observations(
        reports,
    )


def _equity_historical_derived_metrics_available(
    metrics: list[DashboardMetric],
) -> bool:
    return _module_builder_equity_historical_derived_metrics_available(
        metrics,
    )


def _proxy_historical_derived_metrics_available(
    metrics: list[DashboardMetric],
) -> bool:
    return _module_builder_proxy_historical_derived_metrics_available(
        metrics,
    )


def _market_stress_historical_derived_metrics_available(
    metrics: list[DashboardMetric],
) -> bool:
    return _module_builder_market_stress_historical_derived_metrics_available(
        metrics,
    )


def _latest_metric_generated_at(metrics: list[DashboardMetric]) -> str | None:
    return _module_builder_latest_metric_generated_at(metrics)


def _derived_metric(
    metric_key: str,
    reports: tuple[ReportState, ...],
) -> DashboardMetric | None:
    return _derived_metrics_derived_metric(
        metric_key,
        reports,
    )


def _credit_stress_status_metric(
    reports: tuple[ReportState, ...],
) -> DashboardMetric:
    return _derived_credit_stress_status_metric(
        reports,
    )


def _real_yield_pressure_status_metric(
    reports: tuple[ReportState, ...],
) -> DashboardMetric:
    return _derived_real_yield_pressure_status_metric(
        reports,
    )


def _missing_metric(
    metric_key: str,
    display_name: str,
    unit: str | None,
    status: str,
    generated_at: str | None,
    interpretation_hint: str | None = None,
    source: str | None = None,
    source_badge: str | None = None,
    missing_reason: str | None = None,
) -> DashboardMetric:
    return _metric_builder_missing_metric(
        metric_key=metric_key,
        display_name=display_name,
        unit=unit,
        status=status,
        generated_at=generated_at,
        interpretation_hint=interpretation_hint,
        source=source,
        source_badge=source_badge,
        missing_reason=missing_reason,
    )


def _find_metric(
    metric_key: str,
    reports: tuple[ReportState, ...],
    *,
    include_aliases: bool = True,
) -> tuple[Any, dict[str, Any], ReportState] | None:
    return _metric_builder_find_metric(
        metric_key,
        reports,
        include_aliases=include_aliases,
    )


def _usable_numeric_metric(
    metric_key: str,
    reports: tuple[ReportState, ...],
) -> tuple[float, dict[str, Any], ReportState] | None:
    return _derived_usable_numeric_metric(
        metric_key,
        reports,
    )


def _latest_metric_timestamp(
    found_items: list[tuple[float, dict[str, Any], ReportState]],
) -> str | None:
    return _derived_latest_metric_timestamp(found_items)


def _latest_metric_observation_date(
    found_items: list[tuple[float, dict[str, Any], ReportState]],
) -> str | None:
    return _derived_latest_metric_observation_date(found_items)


def _metric_source_badge(
    payload: dict[str, Any],
    report: ReportState,
    module_key: str,
    metric_key: str | None = None,
    quality_metadata: dict[str, Any] | None = None,
) -> str:
    return _metric_builder_metric_source_badge(
        payload,
        report,
        module_key,
        metric_key,
        quality_metadata,
    )


def _interpretation_hint(metric_key: str) -> str | None:
    return _metric_builder_interpretation_hint(
        metric_key,
    )


def _metric_interpretation_hint(metric_key: str, payload: dict[str, Any]) -> str | None:
    return _metric_builder_metric_interpretation_hint(
        metric_key,
        payload,
    )


def _module_status_with_coverage(
    module_key: str,
    status: str,
    key_metrics: list[DashboardMetric],
) -> tuple[str, str | None]:
    return _module_builder_module_status_with_coverage(
        module_key,
        status,
        key_metrics,
    )
