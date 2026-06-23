from __future__ import annotations

from pathlib import Path

from app_backend.schemas.responses import (
    DashboardEvidenceRow,
    DashboardEvidenceTableResponse,
    DashboardSummaryResponse,
)
from app_backend.services.dashboard_cache_adapter import (
    build_dashboard_cache_key_for_request as _build_dashboard_cache_key_for_request,
    resolve_dashboard_market_history_db_path,
    shared_cache_bypass_reason,
)
from app_backend.services.dashboard_composition import compose_dashboard_builders
from app_backend.services.dashboard_context import DashboardPipelineContext
from app_backend.services.dashboard_context_cache import (
    CachedDashboardContext,
    SharedDashboardContextCache,
)
from app_backend.services.dashboard_evidence_assembly import (
    build_evidence_table_response as _build_evidence_table_response,
    evidence_request_is_unfiltered as _evidence_request_is_unfiltered,
    evidence_rows_from_summary as _evidence_rows_from_summary,
    evidence_table_from_unfiltered as _evidence_table_from_unfiltered,
)
from app_backend.services.dashboard_evidence_policy import (
    build_evidence_row as _evidence_row,
)
from app_backend.services.dashboard_historical_derived import (
    LABOR_HISTORICAL_DERIVED_METRIC_KEYS,
)
from app_backend.services.dashboard_metric_catalog import (
    LABOR_METRIC_SPECS,
)
from app_backend.services.dashboard_report_loader import (
    REPORT_FILES,
    ReportState,
    load_dashboard_reports as _load_dashboard_reports,
)
from app_backend.services.dashboard_summary_assembly import (
    data_freshness as _data_freshness,
    first_generated_at as _first_generated_at,
    missing_data as _missing_data,
    next_actions as _next_actions,
    overall_risk_level as _overall_risk_level,
    overall_status as _overall_status,
    provider_health_summary as _provider_health_summary,
)
from app_backend.services.dashboard_model_pipeline import build_dashboard_model_rows
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
    cache_allowed = _shared_cache_bypass_reason(
        reports_dir=reports_dir,
        base_dir=base_dir,
        market_history_db_path=market_history_db_path,
        dashboard_market_history_db_path=dashboard_market_history_db_path,
        write_last_good=False,
    ) is None
    if cache_allowed:
        cached = _SHARED_DASHBOARD_CONTEXT_CACHE.get(cache_key.digest)
        if cached is not None:
            if context is not None:
                context.summary = cached.summary
            return cached.summary
    with _SHARED_DASHBOARD_CONTEXT_CACHE.build_lock:
        if cache_allowed:
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
        if cache_allowed:
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
