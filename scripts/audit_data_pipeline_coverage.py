from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
DEFAULT_SAVE_JSON = PROJECT_ROOT / "outputs" / "reports" / "data_pipeline_coverage.json"
DEFAULT_SAVE_MD = PROJECT_ROOT / "outputs" / "reports" / "data_pipeline_coverage.md"

if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from app_backend.schemas.responses import DashboardEvidenceRow  # noqa: E402
from app_backend.services import dashboard_service  # noqa: E402
from data_providers import market_data_service  # noqa: E402
from data_quality import last_good_cache  # noqa: E402
from data_quality import official_macro_pack  # noqa: E402
from audit_sections.common import (  # noqa: E402
    BAD_AI_SOURCE_BADGES,
    BAD_AI_STATUSES,
    BAD_FRESHNESS,
    STATUS_KEYS,
    _anomaly,
    _anomaly_detail,
    _compact_dgs_fallback_observations,
    _has_clear_history_hint,
    _has_complete_metadata,
    _has_value,
    _is_missing_source_badge,
    _provenance_missing,
    _row_has_ok_value,
    _row_status,
    _source_missing,
    _yoy_metric_suspiciously_large,
)
from audit_sections.history_audits import (  # noqa: E402
    _audit_market_history_db_path,
    _core_risk_history_audit,
    _energy_history_audit,
    _historical_derived_audit,
    _historical_store_audit,
    _liquidity_funding_history_audit,
    _yfinance_history_audit,
)
from audit_sections.manifest_audit import _ai_context_manifest_audit  # noqa: E402
from audit_sections.module_audits import (  # noqa: E402
    _financial_stress_composite_audit,
    _historical_validation_audit,
    _historical_risk_percentile_audit,
    _liquidity_funding_stress_audit,
    _macro_regime_review_audit,
    _market_stress_derived_audit,
    _portfolio_compact_audit,
    _ppi_final_demand_row_available,
    _proxy_breadth_audit,
    _pullback_systemic_checklist_audit,
    _valuation_research_audit,
)


def build_coverage_audit(
    reports_dir: Path | str | None = None,
    last_good_cache_dir: Path | str | None = None,
    market_history_db_path: Path | str | None = None,
) -> dict[str, Any]:
    dashboard_market_history_db_path = _audit_market_history_db_path(
        reports_dir,
        market_history_db_path,
    )
    summary = dashboard_service.build_dashboard_summary(
        reports_dir=reports_dir,
        market_history_db_path=dashboard_market_history_db_path,
    )
    evidence = dashboard_service.build_dashboard_evidence_table(
        reports_dir=reports_dir,
        market_history_db_path=dashboard_market_history_db_path,
        write_last_good=False,
    )
    rows = evidence.rows

    metadata_anomalies = _metadata_anomalies(rows)
    dependency_anomalies = _dependency_anomalies(summary.modules, rows)
    portfolio_compact = _portfolio_compact_audit(rows)
    last_good = _last_good_cache_audit(
        rows,
        cache_dir=_audit_last_good_cache_dir(reports_dir, last_good_cache_dir),
    )
    historical_store = _historical_store_audit(
        rows,
        db_path=_audit_market_history_db_path(reports_dir, market_history_db_path),
    )
    historical_derived = _historical_derived_audit(
        rows,
        db_path=_audit_market_history_db_path(reports_dir, market_history_db_path),
    )
    energy_history = _energy_history_audit(rows, historical_store)
    yfinance_history = _yfinance_history_audit(
        rows,
        db_path=dashboard_market_history_db_path,
    )
    proxy_breadth = _proxy_breadth_audit(rows)
    market_stress_derived = _market_stress_derived_audit(rows)
    financial_stress_composite = _financial_stress_composite_audit(rows)
    pullback_systemic_risk_checklist = _pullback_systemic_checklist_audit(rows)
    historical_risk_percentile = _historical_risk_percentile_audit(rows)
    historical_validation = _historical_validation_audit(rows)
    liquidity_funding = _liquidity_funding_stress_audit(rows)
    macro_regime_review = _macro_regime_review_audit(rows)
    liquidity_funding_history = _liquidity_funding_history_audit(
        db_path=_audit_market_history_db_path(reports_dir, market_history_db_path)
    )
    core_risk_history = _core_risk_history_audit(
        db_path=_audit_market_history_db_path(reports_dir, market_history_db_path),
        historical_risk_percentile=historical_risk_percentile,
    )
    dashboard_derived_integration = _dashboard_derived_integration_audit(rows)
    official_macro = _official_macro_pack_audit(rows, historical_store)
    valuation_research = _valuation_research_audit(rows)
    provider_health = _provider_health_audit(summary.provider_health)
    ai_context_manifest = _ai_context_manifest_audit()
    module_coverage = _module_coverage(summary.modules, rows, last_good)

    return {
        "generated_at": summary.generated_at,
        "overall_status": summary.overall_status,
        "coverage_summary": _coverage_summary(rows, last_good),
        "module_coverage": module_coverage,
        "module_coverage_summary": _module_coverage_summary(module_coverage, rows),
        "top_missing_metrics": _top_gap_metrics(rows, "missing"),
        "top_research_needed_metrics": _top_gap_metrics(rows, "research_needed"),
        "top_insufficient_history_metrics": _top_gap_metrics(rows, "insufficient_history"),
        "dashboard_overall_degraded_reasons": _dashboard_overall_degraded_reasons(
            summary.overall_status,
            summary.modules,
            provider_health,
            rows,
        ),
        "data_sufficiency_assessment": _data_sufficiency_assessment(rows),
        "portfolio_compact": portfolio_compact,
        "last_good_cache": last_good,
        "historical_store": historical_store,
        "historical_derived": historical_derived,
        "energy_history": energy_history,
        "yfinance_history": yfinance_history,
        "proxy_breadth": proxy_breadth,
        "market_stress_derived": market_stress_derived,
        "financial_stress_composite": financial_stress_composite,
        "pullback_systemic_risk_checklist": pullback_systemic_risk_checklist,
        "historical_risk_percentile": historical_risk_percentile,
        "historical_validation": historical_validation,
        "liquidity_funding_stress": liquidity_funding,
        "macro_regime_review": macro_regime_review,
        "liquidity_funding_history": liquidity_funding_history,
        "core_risk_history": core_risk_history,
        "valuation_research": valuation_research,
        "dashboard_derived_integration": dashboard_derived_integration,
        "official_macro_pack": official_macro,
        "provider_health": provider_health,
        "ai_context_manifest": ai_context_manifest,
        "metadata_anomalies": metadata_anomalies,
        "derived_dependency_anomalies": dependency_anomalies,
        "blocked_reason_counts": _blocked_reason_counts(rows),
        "source_badge_distribution": _source_badge_distribution(rows),
        "ai_context_allowed_by_module": _ai_context_allowed_by_module(rows),
        "recommendations": _recommendations(
            metadata_anomalies,
            dependency_anomalies,
            portfolio_compact,
            last_good,
            historical_store,
            historical_derived,
            energy_history,
            yfinance_history,
            liquidity_funding_history,
            core_risk_history,
            dashboard_derived_integration,
            official_macro,
            valuation_research,
        ),
    }


def _coverage_summary(
    rows: list[DashboardEvidenceRow],
    last_good: dict[str, Any],
) -> dict[str, int]:
    statuses = {key: 0 for key in STATUS_KEYS}
    for row in rows:
        if row.status in statuses:
            statuses[row.status] += 1
    return {
        "total_rows": len(rows),
        "rows_with_value": sum(1 for row in rows if _has_value(row)),
        "rows_missing_value": sum(1 for row in rows if not _has_value(row)),
        "rows_with_value_and_complete_metadata": sum(
            1 for row in rows if _has_value(row) and _has_complete_metadata(row)
        ),
        "rows_with_value_but_blocked": sum(
            1 for row in rows if _has_value(row) and not row.ai_context_allowed
        ),
        "ok_count": statuses["ok"],
        "watch_count": statuses["watch"],
        "pressure_count": statuses["pressure"],
        "missing_count": statuses["missing"],
        "research_needed_count": statuses["research_needed"],
        "insufficient_history_count": statuses["insufficient_history"],
        "insufficient_evidence_count": statuses["insufficient_evidence"],
        "stale_count": statuses["stale"],
        "unknown_count": statuses["unknown"],
        "source_badge_missing_count": sum(
            1 for row in rows if _is_missing_source_badge(row.source_badge)
        ),
        "provenance_missing_count": sum(
            1 for row in rows if _has_value(row) and _provenance_missing(row)
        ),
        "freshness_unknown_count": sum(
            1 for row in rows if row.freshness_status in {"unknown", "missing"}
        ),
        "freshness_missing_or_unknown_count": sum(
            1 for row in rows if row.freshness_status in {"unknown", "missing"}
        ),
        "observation_date_missing_count": sum(
            1 for row in rows if not row.observation_date
        ),
        "date_missing_count": sum(
            1 for row in rows if _has_value(row) and not row.observation_date and not row.generated_at
        ),
        "ai_context_allowed_true_count": sum(1 for row in rows if row.ai_context_allowed),
        "ai_context_allowed_false_count": sum(1 for row in rows if not row.ai_context_allowed),
        "last_good_metric_count": last_good["last_good_metric_count"],
        "last_good_usable_count": last_good["last_good_usable_count"],
        "last_good_stale_count": last_good["last_good_stale_count"],
        "last_good_expired_count": last_good["last_good_expired_count"],
        "last_good_error_count": last_good["last_good_error_count"],
        "last_good_not_used_count": last_good["last_good_not_used_count"],
    }


def _module_coverage(
    modules: dict[str, Any],
    rows: list[DashboardEvidenceRow],
    last_good: dict[str, Any],
) -> list[dict[str, Any]]:
    by_module = {module: [row for row in rows if row.module == module] for module in modules}
    metrics_with_last_good = set(last_good["metrics_with_last_good"])
    missing_but_last_good = set(last_good["metrics_missing_but_last_good_available"])
    coverage = []
    for module, module_rows in by_module.items():
        usable = sum(1 for row in module_rows if row.ai_context_allowed)
        row_count = len(module_rows)
        coverage.append(
            {
                "module": module,
                "row_count": row_count,
                "ok_count": sum(1 for row in module_rows if row.status == "ok"),
                "watch_count": sum(1 for row in module_rows if row.status == "watch"),
                "pressure_count": sum(1 for row in module_rows if row.status == "pressure"),
                "missing_count": sum(1 for row in module_rows if row.status == "missing"),
                "research_needed_count": sum(
                    1 for row in module_rows if row.status == "research_needed"
                ),
                "insufficient_history_count": sum(
                    1 for row in module_rows if row.status == "insufficient_history"
                ),
                "stale_count": sum(1 for row in module_rows if row.status == "stale"),
                "usable_fact_count": usable,
                "ai_context_allowed_count": usable,
                "last_good_available_count": sum(
                    1 for row in module_rows if row.metric_key in metrics_with_last_good
                ),
                "missing_but_last_good_available_count": sum(
                    1 for row in module_rows if row.metric_key in missing_but_last_good
                ),
                "module_coverage_status": _module_coverage_status(usable, row_count),
            }
        )
    return coverage


def _module_coverage_status(usable: int, total: int) -> str:
    if total <= 0 or usable == 0:
        return "unavailable"
    if usable == total:
        return "usable"
    if usable / total >= 0.5:
        return "partial"
    return "weak"


def _module_coverage_summary(
    module_coverage: list[dict[str, Any]],
    rows: list[DashboardEvidenceRow],
) -> dict[str, Any]:
    rows_by_module = {
        item["module"]: [row for row in rows if row.module == item["module"]]
        for item in module_coverage
    }
    modules = [item["module"] for item in module_coverage]
    return {
        "usable_row_count_by_module": {
            item["module"]: item["usable_fact_count"] for item in module_coverage
        },
        "missing_count_by_module": {
            item["module"]: item["missing_count"] for item in module_coverage
        },
        "research_needed_count_by_module": {
            item["module"]: item["research_needed_count"] for item in module_coverage
        },
        "insufficient_history_count_by_module": {
            item["module"]: item["insufficient_history_count"] for item in module_coverage
        },
        "official_count_by_module": {
            module: sum(1 for row in rows_by_module[module] if row.source_badge == "official")
            for module in modules
        },
        "derived_or_proxy_count_by_module": {
            module: sum(
                1
                for row in rows_by_module[module]
                if row.source_badge in {"derived", "proxy", "unofficial_fallback"}
            )
            for module in modules
        },
        "ai_context_allowed_count_by_module": {
            item["module"]: item["ai_context_allowed_count"] for item in module_coverage
        },
        "coverage_status_by_module": {
            item["module"]: item["module_coverage_status"] for item in module_coverage
        },
    }


def _top_gap_metrics(
    rows: list[DashboardEvidenceRow],
    status: str,
    *,
    limit: int = 10,
) -> list[dict[str, Any]]:
    return [
        {
            "module": row.module,
            "metric_key": row.metric_key,
            "status": row.status,
            "source_badge": row.source_badge,
            "missing_reason": row.missing_reason,
            "blocked_reason": row.blocked_reason,
        }
        for row in rows
        if row.status == status
    ][:limit]


def _dashboard_overall_degraded_reasons(
    overall_status: str,
    modules: dict[str, Any],
    provider_health: dict[str, Any],
    rows: list[DashboardEvidenceRow],
) -> list[str]:
    reasons: list[str] = []
    if overall_status == "ok":
        return reasons
    for module_key, module in modules.items():
        if module.status != "ok":
            reasons.append(f"{module_key}: module_status={module.status}")
        blocked_core = [
            row.metric_key
            for row in rows
            if row.module == module_key
            and row.metric_key in dashboard_service.CORE_METRIC_KEYS.get(module_key, set())
            and row.status in BAD_AI_STATUSES
        ]
        if blocked_core:
            reasons.append(f"{module_key}: blocked_core_metrics={','.join(sorted(blocked_core))}")
    provider_status = provider_health.get("overall_status")
    if provider_status not in {None, "ok"}:
        reasons.append(f"provider_health={provider_status}")
    return sorted(set(reasons))


def _data_sufficiency_assessment(rows: list[DashboardEvidenceRow]) -> dict[str, Any]:
    usable_by_module = {
        module: sum(1 for row in rows if row.module == module and row.ai_context_allowed)
        for module in sorted({row.module for row in rows})
    }
    return {
        "daily_macro_monitoring": (
            "partial_but_usable"
            if all(
                usable_by_module.get(module, 0) > 0
                for module in (
                    "credit_stress",
                    "rate_pressure",
                    "real_yield_pressure",
                    "inflation_energy_pressure",
                    "equity_trend",
                    "portfolio_deviation",
                )
            )
            else "insufficient"
        ),
        "insufficient_for_crisis_confirmation": True,
        "insufficient_for_valuation_judgment": True,
        "insufficient_for_breadth_judgment": True,
        "notes": [
            "Daily monitoring can use available rates, inflation, labor, equity, portfolio, and partial credit evidence.",
            "Crisis confirmation still requires broader credit/funding/labor/earnings evidence than this dashboard provides.",
            "True valuation and constituent-level breadth/concentration remain outside configured audited data; proxy breadth may be available separately.",
        ],
    }


def _metadata_anomalies(rows: list[DashboardEvidenceRow]) -> list[dict[str, Any]]:
    anomalies: list[dict[str, Any]] = []
    for row in rows:
        if _has_value(row) and _is_missing_source_badge(row.source_badge):
            anomalies.append(_anomaly(row, "value_with_missing_source_badge", "source_badge_missing"))
        if _has_value(row) and row.freshness_status in {"unknown", "missing"}:
            anomalies.append(_anomaly(row, "value_with_unknown_freshness", "freshness_unknown"))
        if _has_value(row) and not row.observation_date and not row.generated_at:
            anomalies.append(_anomaly(row, "value_without_observation_or_generated_at", "date_missing"))
        if row.ai_context_allowed and _is_missing_source_badge(row.source_badge):
            anomalies.append(_anomaly(row, "ai_allowed_with_missing_source_badge", "source_badge_missing"))
        if row.ai_context_allowed and row.freshness_status in BAD_FRESHNESS:
            anomalies.append(_anomaly(row, "ai_allowed_with_bad_freshness", "freshness_unknown"))
        if row.ai_context_allowed and row.status in BAD_AI_STATUSES:
            anomalies.append(_anomaly(row, "ai_allowed_with_blocked_status", f"status_{row.status}"))
        if row.ai_context_allowed and row.source_badge in BAD_AI_SOURCE_BADGES:
            anomalies.append(_anomaly(row, "ai_allowed_with_blocked_source_badge", f"source_badge_{row.source_badge}"))
        if row.source_badge in {"proxy", "search-derived"} and not row.interpretation_hint:
            anomalies.append(_anomaly(row, "proxy_or_search_derived_without_hint", "compact_report_missing_provenance"))
        if row.status in {"missing", "research_needed"} and not row.missing_reason:
            anomalies.append(_anomaly(row, "missing_or_research_needed_without_reason", "compact_report_missing_provenance"))
        if _yoy_metric_suspiciously_large(row):
            anomalies.append(
                _anomaly(
                    row,
                    "yoy_metric_suspiciously_large",
                    "inflation_yoy_metric_blocked_due_to_index_level",
                )
            )
    return anomalies


def _dependency_anomalies(
    modules: dict[str, Any],
    rows: list[DashboardEvidenceRow],
) -> list[dict[str, Any]]:
    rows_by_key = {row.metric_key: row for row in rows}
    anomalies: list[dict[str, Any]] = []

    dgs30 = rows_by_key.get("dgs30")
    dgs30_distance = rows_by_key.get("dgs30_distance_to_5pct")
    if _source_missing(dgs30) and _row_has_ok_value(dgs30_distance):
        anomalies.append(
            _anomaly(dgs30_distance, "dgs30_distance_ok_while_dgs30_missing", "dependency_metadata_incomplete")
        )

    dgs30_breakout = rows_by_key.get("dgs30_breakout_confirmed")
    if _source_missing(dgs30) and _row_has_ok_value(dgs30_breakout):
        anomalies.append(
            _anomaly(dgs30_breakout, "dgs30_breakout_ok_while_dgs30_missing", "dependency_metadata_incomplete")
        )

    nasdaq_spread = rows_by_key.get("nasdaq_vs_sp500_30d")
    if (
        _source_missing(rows_by_key.get("sp500_30d_return"))
        or _source_missing(rows_by_key.get("nasdaq100_30d_return"))
    ) and _row_has_ok_value(nasdaq_spread):
        anomalies.append(
            _anomaly(nasdaq_spread, "nasdaq_vs_sp500_ok_while_dependency_missing", "dependency_metadata_incomplete")
        )

    for metric_key in ("wti_30d_change", "brent_30d_change"):
        row = rows_by_key.get(metric_key)
        if _row_has_ok_value(row) and not _has_clear_history_hint(row):
            anomalies.append(_anomaly(row, f"{metric_key}_ok_without_history_hint", "dependency_metadata_incomplete"))

    for module_key, module in modules.items():
        core_keys = dashboard_service.CORE_METRIC_KEYS.get(module_key, set())
        core_rows = [row for row in rows if row.module == module_key and row.metric_key in core_keys]
        if not core_rows:
            continue
        blocked = [row for row in core_rows if _source_missing(row)]
        if module.status == "ok" and len(blocked) >= max(1, len(core_rows) // 2 + 1):
            anomalies.append(
                {
                    "type": "module_ok_while_core_metrics_mostly_missing",
                    "reason": "dependency_metadata_incomplete",
                    "module": module_key,
                    "metric_key": None,
                    "row_id": None,
                    "detail": f"{len(blocked)} of {len(core_rows)} core metrics are unavailable",
                }
            )
    return anomalies


def _recommendations(
    metadata_anomalies: list[dict[str, Any]],
    dependency_anomalies: list[dict[str, Any]],
    portfolio_compact: dict[str, Any] | None = None,
    last_good: dict[str, Any] | None = None,
    historical_store: dict[str, Any] | None = None,
    historical_derived: dict[str, Any] | None = None,
    energy_history: dict[str, Any] | None = None,
    yfinance_history: dict[str, Any] | None = None,
    liquidity_funding_history: dict[str, Any] | None = None,
    core_risk_history: dict[str, Any] | None = None,
    dashboard_derived_integration: dict[str, Any] | None = None,
    official_macro: dict[str, Any] | None = None,
    valuation_research: dict[str, Any] | None = None,
) -> list[str]:
    recommendations: list[str] = []
    if metadata_anomalies:
        recommendations.append("fix_metadata_semantics")
    if any("dgs30" in item["type"] or "nasdaq" in item["type"] or "30d_change" in item["type"] for item in dependency_anomalies):
        recommendations.append("fix_derived_dependency_validation")
    if any(item["type"] == "module_ok_while_core_metrics_mostly_missing" for item in dependency_anomalies):
        recommendations.append("fix_module_status_aggregation")
    if portfolio_compact:
        if not portfolio_compact.get("portfolio_compact_available"):
            recommendations.append("fill_portfolio_deviation_compact")
        if portfolio_compact.get("portfolio_stale_status") == "stale":
            recommendations.append("update_holdings_snapshot")
        if portfolio_compact.get("portfolio_has_raw_holdings_leak"):
            recommendations.append("privacy_blocker")
    if last_good:
        if last_good.get("last_good_error_count", 0) > 0:
            recommendations.append("clear_or_rebuild_last_good_cache")
        if (
            last_good.get("last_good_stale_count", 0) > 0
            or last_good.get("last_good_expired_count", 0) > 0
        ):
            recommendations.append("refresh_market_snapshot")
    if historical_store:
        recommendations.extend(historical_store.get("recommended_history_actions", []))
    if historical_derived:
        recommendations.extend(historical_derived.get("recommended_history_actions", []))
    if energy_history:
        recommendations.extend(energy_history.get("recommended_history_actions", []))
    if yfinance_history:
        recommendations.extend(yfinance_history.get("recommendations", []))
    if liquidity_funding_history:
        recommendations.extend(liquidity_funding_history.get("recommendations", []))
    if core_risk_history and not core_risk_history.get("history_sufficient_for_d13"):
        recommendations.append("run_core_risk_history_backfill_live_write")
    if dashboard_derived_integration and dashboard_derived_integration.get(
        "equity_derived_still_insufficient_count",
        0,
    ):
        recommendations.append("check_dashboard_historical_derived_integration")
    if official_macro and official_macro.get("official_macro_missing_count", 0) > 0:
        recommendations.append("fill_official_macro_compact_reports")
    if official_macro and not official_macro.get("ppi_final_demand_available"):
        recommendations.append("confirm_and_ingest_ppi_final_demand_ppifis")
    if official_macro and official_macro.get("ppifis_history_observation_count", 0) < 13:
        recommendations.append("ingest_official_ppifis_history")
    if valuation_research and valuation_research.get("source_research_document_exists"):
        recommendations.append("design_manual_or_citation_valuation_context_gate")
    return sorted(set(recommendations))


def _blocked_reason_counts(rows: list[DashboardEvidenceRow]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        if row.ai_context_allowed:
            continue
        reason = row.blocked_reason or "not_eligible"
        counts[reason] = counts.get(reason, 0) + 1
    return dict(sorted(counts.items()))


def _source_badge_distribution(rows: list[DashboardEvidenceRow]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        counts[row.source_badge] = counts.get(row.source_badge, 0) + 1
    return dict(sorted(counts.items()))


def _ai_context_allowed_by_module(rows: list[DashboardEvidenceRow]) -> dict[str, dict[str, int]]:
    result: dict[str, dict[str, int]] = {}
    for row in rows:
        item = result.setdefault(row.module, {"true": 0, "false": 0})
        item["true" if row.ai_context_allowed else "false"] += 1
    return dict(sorted(result.items()))


def _last_good_cache_audit(
    rows: list[DashboardEvidenceRow],
    *,
    cache_dir: Path | str | None = None,
) -> dict[str, Any]:
    results = last_good_cache.list_last_good_cache(cache_dir=cache_dir)
    statuses = {
        "usable": 0,
        "stale": 0,
        "expired": 0,
        "unavailable": 0,
        "error": 0,
    }
    metrics_with_last_good: list[str] = []
    for result in results:
        status = result.get("status") or "error"
        statuses[status] = statuses.get(status, 0) + 1
        if status not in {"unavailable", "error"}:
            metrics_with_last_good.append(str(result.get("metric_key")))
    available_keys = set(metrics_with_last_good)
    missing_but_last_good = sorted(
        {
            row.metric_key
            for row in rows
            if not _has_value(row) and row.metric_key in available_keys
        }
    )
    return {
        "last_good_cache_available": bool(results),
        "last_good_metric_count": len(metrics_with_last_good),
        "last_good_usable_count": statuses.get("usable", 0),
        "last_good_stale_count": statuses.get("stale", 0),
        "last_good_expired_count": statuses.get("expired", 0),
        "last_good_error_count": statuses.get("error", 0),
        "metrics_with_last_good": sorted(metrics_with_last_good),
        "metrics_missing_but_last_good_available": missing_but_last_good,
        "last_good_not_used_count": len(missing_but_last_good),
    }


def _audit_last_good_cache_dir(
    reports_dir: Path | str | None,
    last_good_cache_dir: Path | str | None,
) -> Path | str | None:
    if last_good_cache_dir is not None:
        return last_good_cache_dir
    if reports_dir is None:
        return None
    return Path(reports_dir) / ".last_good_cache"


def _official_macro_pack_audit(
    rows: list[DashboardEvidenceRow],
    historical_store: dict[str, Any],
) -> dict[str, Any]:
    row_by_key = {row.metric_key: row for row in rows}
    observations = historical_store.get("observations_by_metric", {})
    latest = historical_store.get("latest_observation_by_metric", {})
    ppifis_count = int(observations.get("ppi_final_demand") or 0)
    metrics = official_macro_pack.OFFICIAL_MACRO_METRICS
    configured_keys = sorted(metrics)
    available_keys = sorted(
        key
        for key, metric in metrics.items()
        if _official_macro_row_available(row_by_key.get(key), metric)
    )
    missing_keys = sorted(set(configured_keys) - set(available_keys))
    details = [
        {
            "metric_key": key,
            "module": metric.module,
            "status": _official_macro_row_status(row_by_key.get(key), metric),
            "source": metric.source,
            "source_badge": metric.source_badge,
            "source_series": metric.source_series,
            "expected_frequency": metric.expected_frequency,
            "dashboard_enabled": metric.dashboard_enabled,
            "missing_reason": (
                row_by_key[key].missing_reason
                if key in row_by_key and row_by_key[key].missing_reason
                else metric.missing_reason
            ),
        }
        for key, metric in sorted(metrics.items())
    ]
    status_by_key = {
        key: _official_macro_row_status(row_by_key.get(key), metrics[key])
        for key in configured_keys
    }
    rate_macro_keys = ("dgs2", "dgs30")
    ppi_final_demand_available = _ppi_final_demand_row_available(
        row_by_key.get("ppi_final_demand")
    )
    labor_keys = (
        "unemployment_rate",
        "initial_jobless_claims",
        "nonfarm_payrolls",
        "continuing_claims",
    )
    labor_derived_keys = (
        "unemployment_rate_3m_avg",
        "unemployment_rate_12m_low_gap",
        "initial_claims_4w_avg",
        "continuing_claims_4w_avg",
        "sahm_rule_proxy_status",
        "labor_deterioration_status",
    )
    labor_history_counts = {
        key: int(observations.get(key) or 0)
        for key in labor_keys
    }
    labor_current_available = {
        key: _official_macro_row_available(row_by_key.get(key), metrics[key])
        for key in labor_keys
    }
    labor_history_fallback_available = {
        key: bool(
            labor_current_available[key]
            and row_by_key.get(key)
            and row_by_key[key].freshness_status == "historical"
            and labor_history_counts[key] > 0
        )
        for key in labor_keys
    }
    labor_compact_current_available = {
        key: bool(
            labor_current_available[key]
            and row_by_key.get(key)
            and row_by_key[key].freshness_status != "historical"
        )
        for key in labor_keys
    }
    labor_deterioration_row = row_by_key.get("labor_deterioration_status")
    return {
        "official_macro_configured_count": len(configured_keys),
        "official_macro_available_count": len(available_keys),
        "official_macro_missing_count": len(missing_keys),
        "rate_macro_available_count": sum(
            1
            for key in rate_macro_keys
            if _official_macro_row_available(row_by_key.get(key), metrics[key])
        ),
        "available_metric_keys": available_keys,
        "missing_metric_keys": missing_keys,
        "real_yield_available": all(
            _official_macro_row_available(row_by_key.get(key), metrics[key])
            for key in ("dfii10", "t10yie")
        ),
        "inflation_core_available": all(
            _official_macro_row_available(row_by_key.get(key), metrics[key])
            for key in ("core_cpi_yoy", "core_pce_yoy")
        ),
        "labor_available": all(
            _official_macro_row_available(row_by_key.get(key), metrics[key])
            for key in labor_keys
        ),
        "labor_official_compact_current_available": all(labor_compact_current_available.values()),
        "labor_history_fallback_available": any(labor_history_fallback_available.values()),
        "labor_available_by_source": {
            "official_compact_current": labor_compact_current_available,
            "history_fallback": labor_history_fallback_available,
            "derived_labor": {
                "labor_deterioration_status": bool(
                    labor_deterioration_row is not None
                    and labor_deterioration_row.status in {"ok", "watch", "pressure"}
                    and labor_deterioration_row.ai_context_allowed
                )
            },
        },
        "labor_missing_count": sum(
            1
            for key in labor_keys
            if not _official_macro_row_available(row_by_key.get(key), metrics[key])
        ),
        "dgs2_status": status_by_key["dgs2"],
        "dgs30_status": status_by_key["dgs30"],
        "dfii10_status": status_by_key["dfii10"],
        "t10yie_status": status_by_key["t10yie"],
        "core_cpi_yoy_status": status_by_key["core_cpi_yoy"],
        "core_pce_yoy_status": status_by_key["core_pce_yoy"],
        "ppiaco_yoy_status": status_by_key["ppiaco_yoy"],
        "ppi_final_demand_available": ppi_final_demand_available,
        "ppi_final_demand_status": status_by_key["ppi_final_demand"],
        "ppi_final_demand_yoy_status": status_by_key["ppi_final_demand_yoy"],
        "ppifis_history_observation_count": ppifis_count,
        "ppifis_latest_observation_date": latest.get("ppi_final_demand"),
        "ppifis_history_sufficient_for_yoy": ppifis_count >= 13,
        "ppi_final_demand_ai_context_allowed": bool(
            row_by_key.get("ppi_final_demand")
            and row_by_key["ppi_final_demand"].ai_context_allowed
        ),
        "unemployment_rate_status": status_by_key["unemployment_rate"],
        "initial_jobless_claims_status": status_by_key["initial_jobless_claims"],
        "nonfarm_payrolls_status": status_by_key["nonfarm_payrolls"],
        "continuing_claims_status": status_by_key["continuing_claims"],
        "labor_derived_statuses": {
            key: _row_status(row_by_key.get(key)) for key in labor_derived_keys
        },
        "labor_deterioration_status": _row_status(
            row_by_key.get("labor_deterioration_status")
        ),
        "labor_deterioration_missing_inputs": _labor_deterioration_missing_inputs(
            row_by_key.get("labor_deterioration_status")
        ),
        "labor_history_observation_counts": labor_history_counts,
        "unemployment_rate_history_observation_count": labor_history_counts["unemployment_rate"],
        "initial_jobless_claims_history_observation_count": labor_history_counts["initial_jobless_claims"],
        "nonfarm_payrolls_history_observation_count": labor_history_counts["nonfarm_payrolls"],
        "continuing_claims_history_observation_count": labor_history_counts["continuing_claims"],
        "labor_history_sufficient_for_derived": (
            labor_history_counts["unemployment_rate"] >= 12
            and labor_history_counts["initial_jobless_claims"] >= 8
            and labor_history_counts["continuing_claims"] >= 8
            and labor_history_counts["nonfarm_payrolls"] >= 2
        ),
        "suspicious_yoy_count": sum(1 for row in rows if _yoy_metric_suspiciously_large(row)),
        "blocked_due_to_index_level_count": sum(
            1 for row in rows if _blocked_due_to_index_level(row)
        ),
        "official_macro_missing_reasons": {
            key: _official_macro_missing_reason(row_by_key.get(key), metrics[key])
            for key in missing_keys
        },
        "details": details,
    }


def _official_macro_row_available(
    row: DashboardEvidenceRow | None,
    metric: official_macro_pack.OfficialMacroMetric,
) -> bool:
    return bool(
        row is not None
        and row.status == "ok"
        and _has_value(row)
        and row.source_badge in {"official", "official_fallback", "derived"}
        and row.source
        and (row.observation_date or row.generated_at)
        and row.freshness_status not in BAD_FRESHNESS
    )


def _official_macro_row_status(
    row: DashboardEvidenceRow | None,
    metric: official_macro_pack.OfficialMacroMetric,
) -> str:
    if row is None:
        return metric.status_when_missing
    return row.status


def _blocked_due_to_index_level(row: DashboardEvidenceRow) -> bool:
    return bool(
        "yoy" in row.metric_key.lower()
        and row.status == "insufficient_history"
        and row.missing_reason
        and "Only index level is available" in row.missing_reason
    )


def _official_macro_missing_reason(
    row: DashboardEvidenceRow | None,
    metric: official_macro_pack.OfficialMacroMetric,
) -> str:
    if row is not None and row.missing_reason:
        return row.missing_reason
    return metric.missing_reason


def _labor_deterioration_missing_inputs(row: DashboardEvidenceRow | None) -> list[str]:
    if row is None or not row.interpretation_hint:
        return []
    marker = "missing_inputs="
    if marker not in row.interpretation_hint:
        return []
    raw = row.interpretation_hint.split(marker, 1)[1].split(".", 1)[0]
    return [
        item.strip().strip("'\"[]")
        for item in raw.split(",")
        if item.strip().strip("'\"[]")
    ]


def _provider_health_audit(provider_health: dict[str, Any]) -> dict[str, Any]:
    checks = provider_health.get("checks")
    compact_checks = checks if isinstance(checks, list) else []
    transient = [
        check
        for check in compact_checks
        if isinstance(check, dict)
        and (
            check.get("status") == "transient_error"
            or check.get("error_type") == "transient_network"
        )
    ]
    official_fallback_ok = [
        str(check.get("provider"))
        for check in compact_checks
        if isinstance(check, dict)
        and check.get("status") == "ok"
        and str(check.get("provider") or "")
        in {"U.S. Treasury", "BLS", "BEA", "New York Fed"}
    ]
    return {
        "overall_status": provider_health.get("overall_status"),
        "provider_health_transient_error_count": len(transient),
        "official_fallback_ok_count": len(official_fallback_ok),
        "official_fallback_ok_providers": sorted(set(official_fallback_ok)),
    }


def _dashboard_derived_integration_audit(
    rows: list[DashboardEvidenceRow],
) -> dict[str, Any]:
    equity_keys = {
        "sp500_30d_return",
        "sp500_60d_return",
        "nasdaq100_30d_return",
        "nasdaq100_60d_return",
        "nasdaq_vs_sp500_30d",
    }
    equity_rows = [
        row for row in rows if row.module == "equity_trend" and row.metric_key in equity_keys
    ]
    integrated = [
        row
        for row in equity_rows
        if row.status == "ok" and row.source_badge == "derived" and _has_value(row)
    ]
    still_insufficient = [
        row for row in equity_rows if row.status == "insufficient_history"
    ]
    historical_derived_used = [
        row
        for row in rows
        if row.source_badge == "derived"
        and row.status == "ok"
        and _has_value(row)
        and _hint_mentions_local_market_history(row.interpretation_hint)
    ]
    return {
        "equity_derived_integrated_count": len(integrated),
        "equity_derived_still_insufficient_count": len(still_insufficient),
        "historical_derived_used_in_dashboard_count": len(historical_derived_used),
        "dashboard_insufficient_history_remaining_count": sum(
            1 for row in rows if row.status == "insufficient_history"
        ),
        "dashboard_equity_trend_value_count": sum(
            1 for row in equity_rows if _has_value(row)
        ),
        "integrated_metric_keys": sorted(row.metric_key for row in integrated),
        "still_insufficient_metric_keys": sorted(
            row.metric_key for row in still_insufficient
        ),
    }


def _hint_mentions_local_market_history(value: str | None) -> bool:
    text = (value or "").lower()
    return "derived from local market history" in text


def _write_markdown(audit: dict[str, Any], path: Path) -> None:
    lines = [
        "# Data Pipeline Coverage Audit",
        "",
        f"- overall_status: {audit['overall_status']}",
        f"- generated_at: {audit['generated_at'] or 'not available'}",
        "",
        "## Coverage Summary",
        "",
    ]
    for key, value in audit["coverage_summary"].items():
        lines.append(f"- {key}: {value}")
    lines.extend(["", "## Module Coverage Summary", ""])
    for key, value in audit["module_coverage_summary"].items():
        lines.append(f"- {key}: {value}")
    lines.extend(["", "## Dashboard Degraded Reasons", ""])
    for reason in audit["dashboard_overall_degraded_reasons"]:
        lines.append(f"- {reason}")
    lines.extend(["", "## Data Sufficiency Assessment", ""])
    for key, value in audit["data_sufficiency_assessment"].items():
        lines.append(f"- {key}: {value}")
    lines.extend(["", "## Top Gaps", ""])
    for key in (
        "top_missing_metrics",
        "top_research_needed_metrics",
        "top_insufficient_history_metrics",
    ):
        lines.append(f"- {key}: {audit[key]}")
    lines.extend(["", "## Module Coverage", ""])
    for item in audit["module_coverage"]:
        lines.append(
            f"- {item['module']}: {item['module_coverage_status']} "
            f"({item['usable_fact_count']}/{item['row_count']} usable)"
        )
    lines.extend(["", "## Portfolio Compact", ""])
    for key, value in audit["portfolio_compact"].items():
        lines.append(f"- {key}: {value}")
    lines.extend(["", "## Last-good Cache", ""])
    for key, value in audit["last_good_cache"].items():
        lines.append(f"- {key}: {value}")
    lines.extend(["", "## Historical Store", ""])
    for key, value in audit["historical_store"].items():
        lines.append(f"- {key}: {value}")
    lines.extend(["", "## Historical Derived Metrics", ""])
    for key, value in audit["historical_derived"].items():
        lines.append(f"- {key}: {value}")
    lines.extend(["", "## Energy History", ""])
    for key, value in audit["energy_history"].items():
        lines.append(f"- {key}: {value}")
    lines.extend(["", "## yfinance History", ""])
    for key, value in audit["yfinance_history"].items():
        lines.append(f"- {key}: {value}")
    lines.extend(["", "## Core Risk History", ""])
    for key, value in audit["core_risk_history"].items():
        lines.append(f"- {key}: {value}")
    lines.extend(["", "## Historical Risk Percentile", ""])
    for key, value in audit["historical_risk_percentile"].items():
        lines.append(f"- {key}: {value}")
    lines.extend(["", "## Historical Validation", ""])
    for key, value in audit["historical_validation"].items():
        lines.append(f"- {key}: {value}")
    lines.extend(["", "## Liquidity/Funding Stress", ""])
    for key, value in audit["liquidity_funding_stress"].items():
        lines.append(f"- {key}: {value}")
    lines.extend(["", "## Liquidity/Funding History", ""])
    for key, value in audit["liquidity_funding_history"].items():
        lines.append(f"- {key}: {value}")
    lines.extend(["", "## Proxy Breadth", ""])
    for key, value in audit["proxy_breadth"].items():
        lines.append(f"- {key}: {value}")
    lines.extend(["", "## Valuation Research", ""])
    for key, value in audit["valuation_research"].items():
        lines.append(f"- {key}: {value}")
    lines.extend(["", "## Dashboard Derived Integration", ""])
    for key, value in audit["dashboard_derived_integration"].items():
        lines.append(f"- {key}: {value}")
    lines.extend(["", "## Official Macro Pack", ""])
    for key, value in audit["official_macro_pack"].items():
        lines.append(f"- {key}: {value}")
    lines.extend(["", "## Metadata Anomalies", ""])
    for item in audit["metadata_anomalies"]:
        lines.append(f"- {item['type']} ({item.get('reason') or 'unknown'}): {item['row_id']}")
    lines.extend(["", "## Derived Dependency Anomalies", ""])
    for item in audit["derived_dependency_anomalies"]:
        lines.append(f"- {item['type']}: {item.get('row_id') or item.get('module')}")
    lines.extend(["", "## Blocked Reasons", ""])
    for reason, count in audit["blocked_reason_counts"].items():
        lines.append(f"- {reason}: {count}")
    lines.extend(["", "## Source Badge Distribution", ""])
    for badge, count in audit["source_badge_distribution"].items():
        lines.append(f"- {badge}: {count}")
    lines.extend(["", "## Recommendations", ""])
    for item in audit["recommendations"]:
        lines.append(f"- {item}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Audit local dashboard data coverage.")
    parser.add_argument(
        "--reports-dir",
        type=Path,
        default=None,
        help="Optional local reports directory for tests or dry audits.",
    )
    parser.add_argument("--save", action="store_true", help="Save ignored audit artifacts.")
    args = parser.parse_args(argv)

    audit = build_coverage_audit(reports_dir=args.reports_dir)
    print(json.dumps(audit, ensure_ascii=False, indent=2, sort_keys=True))
    if args.save:
        DEFAULT_SAVE_JSON.parent.mkdir(parents=True, exist_ok=True)
        DEFAULT_SAVE_JSON.write_text(
            json.dumps(audit, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        _write_markdown(audit, DEFAULT_SAVE_MD)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
