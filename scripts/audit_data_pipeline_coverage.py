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
from data_providers import yfinance_history_provider  # noqa: E402
from data_quality import historical_derived_metrics  # noqa: E402
from data_quality import last_good_cache  # noqa: E402
from data_quality import market_history_store  # noqa: E402
from data_quality import official_macro_pack  # noqa: E402


STATUS_KEYS = (
    "ok",
    "watch",
    "pressure",
    "missing",
    "research_needed",
    "insufficient_history",
    "stale",
    "unknown",
)
BAD_FRESHNESS = {"unknown", "missing", "stale"}
BAD_AI_STATUSES = {
    "missing",
    "research_needed",
    "not_available",
    "insufficient_history",
    "stale",
}
BAD_AI_SOURCE_BADGES = {"missing", "research_needed", "search-derived"}
DEFAULT_YFINANCE_HISTORY_CONFIG = PROJECT_ROOT / "configs" / "yfinance_history.yaml"


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
    yfinance_history = _yfinance_history_audit(
        rows,
        db_path=dashboard_market_history_db_path,
    )
    dashboard_derived_integration = _dashboard_derived_integration_audit(rows)
    official_macro = _official_macro_pack_audit(rows)

    return {
        "generated_at": summary.generated_at,
        "overall_status": summary.overall_status,
        "coverage_summary": _coverage_summary(rows, last_good),
        "module_coverage": _module_coverage(summary.modules, rows, last_good),
        "portfolio_compact": portfolio_compact,
        "last_good_cache": last_good,
        "historical_store": historical_store,
        "historical_derived": historical_derived,
        "yfinance_history": yfinance_history,
        "dashboard_derived_integration": dashboard_derived_integration,
        "official_macro_pack": official_macro,
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
            yfinance_history,
            dashboard_derived_integration,
            official_macro,
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
    yfinance_history: dict[str, Any] | None = None,
    dashboard_derived_integration: dict[str, Any] | None = None,
    official_macro: dict[str, Any] | None = None,
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
    if yfinance_history:
        recommendations.extend(yfinance_history.get("recommendations", []))
    if dashboard_derived_integration and dashboard_derived_integration.get(
        "equity_derived_still_insufficient_count",
        0,
    ):
        recommendations.append("check_dashboard_historical_derived_integration")
    if official_macro and official_macro.get("official_macro_missing_count", 0) > 0:
        recommendations.append("fill_official_macro_compact_reports")
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


def _audit_market_history_db_path(
    reports_dir: Path | str | None,
    market_history_db_path: Path | str | None,
) -> Path | str | None:
    if market_history_db_path is not None:
        return market_history_db_path
    if reports_dir is None:
        return None
    return Path(reports_dir) / ".market_history" / "market_history.sqlite3"


def _historical_store_audit(
    rows: list[DashboardEvidenceRow],
    *,
    db_path: Path | str | None = None,
) -> dict[str, Any]:
    summary = market_history_store.get_market_history_summary(db_path=db_path)
    observations_by_metric = summary["observations_by_metric"]
    metrics_with_history = set(observations_by_metric)
    insufficient_rows = [row for row in rows if row.status == "insufficient_history"]
    insufficient_empty = sorted(
        {
            row.metric_key
            for row in insufficient_rows
            if row.metric_key not in metrics_with_history
        }
    )
    actions: list[str] = []
    if not summary["market_history_db_exists"]:
        actions.extend(
            [
                "initialize_market_history_store",
                "ingest_market_history_from_dashboard",
            ]
        )
    elif summary["market_history_observation_count"] == 0:
        actions.append("ingest_market_history_from_dashboard")
    if insufficient_empty:
        actions.append("ingest_market_history_from_dashboard")

    return {
        "market_history_available": bool(summary["market_history_observation_count"]),
        "market_history_db_exists": summary["market_history_db_exists"],
        "market_history_schema_version": summary["market_history_schema_version"],
        "market_history_metric_count": summary["market_history_metric_count"],
        "market_history_observation_count": summary["market_history_observation_count"],
        "observations_by_metric": observations_by_metric,
        "latest_observation_by_metric": summary["latest_observation_by_metric"],
        "dashboard_metrics_with_history_count": sum(
            1 for row in rows if row.metric_key in metrics_with_history
        ),
        "insufficient_history_rows_count": len(insufficient_rows),
        "metrics_insufficient_history_but_store_empty": insufficient_empty,
        "recommended_history_actions": sorted(set(actions)),
    }


def _historical_derived_audit(
    rows: list[DashboardEvidenceRow],
    *,
    db_path: Path | str | None = None,
) -> dict[str, Any]:
    db_exists = Path(db_path).exists() if db_path is not None else market_history_store.get_default_market_history_db_path().exists()
    by_module = historical_derived_metrics.build_historical_dashboard_candidates(db_path=db_path)
    all_metrics = [item for items in by_module.values() for item in items]
    details = [
        {
            "metric_key": item.metric_key,
            "status": item.status,
            "dependency_keys": item.dependency_keys,
            "history_points_used": item.history_points_used,
            "history_points_required": item.history_points_required,
            "missing_reason": item.missing_reason,
        }
        for item in all_metrics
    ]
    insufficient_dashboard_keys = {
        row.metric_key for row in rows if row.status == "insufficient_history"
    }
    ok_derived_keys = {item.metric_key for item in all_metrics if item.status == "ok"}
    potentially_resolvable = insufficient_dashboard_keys & ok_derived_keys
    actions: list[str] = []
    if not db_exists:
        actions.append("initialize_and_ingest_market_history")
    if any(item.status == "insufficient_history" for item in all_metrics):
        actions.extend(["ingest_more_history", "run_yfinance_history_ingest_live"])
    return {
        "historical_derived_available": any(item.status == "ok" for item in all_metrics),
        "derived_metric_count": len(all_metrics),
        "derived_metric_ok_count": sum(1 for item in all_metrics if item.status == "ok"),
        "derived_metric_insufficient_history_count": sum(
            1 for item in all_metrics if item.status == "insufficient_history"
        ),
        "derived_metric_missing_dependency_count": sum(
            1
            for item in all_metrics
            if item.status != "ok" and "missing" in (item.missing_reason or "")
        ),
        "derived_metrics_by_module": {
            module: {
                "count": len(items),
                "ok_count": sum(1 for item in items if item.status == "ok"),
                "insufficient_history_count": sum(
                    1 for item in items if item.status == "insufficient_history"
                ),
            }
            for module, items in sorted(by_module.items())
        },
        "derived_metric_details": details,
        "dashboard_insufficient_history_potentially_resolvable_count": len(
            potentially_resolvable
        ),
        "dashboard_insufficient_history_still_blocked_count": len(
            insufficient_dashboard_keys - ok_derived_keys
        ),
        "recommended_history_actions": sorted(set(actions)),
    }


def _official_macro_pack_audit(rows: list[DashboardEvidenceRow]) -> dict[str, Any]:
    row_by_key = {row.metric_key: row for row in rows}
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
            for key in ("unemployment_rate", "initial_jobless_claims")
        ),
        "dgs2_status": status_by_key["dgs2"],
        "dgs30_status": status_by_key["dgs30"],
        "dfii10_status": status_by_key["dfii10"],
        "t10yie_status": status_by_key["t10yie"],
        "core_cpi_yoy_status": status_by_key["core_cpi_yoy"],
        "core_pce_yoy_status": status_by_key["core_pce_yoy"],
        "ppiaco_yoy_status": status_by_key["ppiaco_yoy"],
        "ppi_final_demand_status": official_macro_pack.ppi_final_demand_status(),
        "unemployment_rate_status": status_by_key["unemployment_rate"],
        "initial_jobless_claims_status": status_by_key["initial_jobless_claims"],
        "suspicious_yoy_count": sum(1 for row in rows if _yoy_metric_suspiciously_large(row)),
        "blocked_due_to_index_level_count": sum(
            1 for row in rows if _blocked_due_to_index_level(row)
        ),
        "details": details,
    }


def _official_macro_row_available(
    row: DashboardEvidenceRow | None,
    metric: official_macro_pack.OfficialMacroMetric,
) -> bool:
    if metric.status_when_missing == "research_needed":
        return False
    return bool(
        row is not None
        and row.status == "ok"
        and _has_value(row)
        and row.source_badge == "official"
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


def _yfinance_history_audit(
    rows: list[DashboardEvidenceRow],
    *,
    db_path: Path | str | None = None,
) -> dict[str, Any]:
    config = (
        yfinance_history_provider.load_yfinance_history_config(DEFAULT_YFINANCE_HISTORY_CONFIG)
        if DEFAULT_YFINANCE_HISTORY_CONFIG.exists()
        else {}
    )
    yfinance_summary = _yfinance_observation_summary(db_path=db_path)
    observations_by_metric = yfinance_summary["observations_by_metric"]
    latest_by_metric = yfinance_summary["latest_observation_by_metric"]
    source_badges = yfinance_summary["source_badges"]
    observation_count = yfinance_summary["observation_count"]
    configured_metric_keys = {item["metric_key"] for item in config.values()}
    potentially_resolvable = _insufficient_history_potentially_resolvable_by_yfinance(
        rows,
        configured_metric_keys,
    )
    recommendations = ["keep_proxy_out_of_official_layer"]
    if observation_count == 0:
        recommendations.append("run_yfinance_history_ingest_live")
    if potentially_resolvable:
        recommendations.append("integrate_historical_derived_metrics")
    return {
        "yfinance_history_configured": bool(config),
        "yfinance_enabled_symbol_count": len(config),
        "yfinance_observation_count": observation_count,
        "yfinance_observations_by_metric": dict(sorted(observations_by_metric.items())),
        "yfinance_latest_observation_by_metric": dict(sorted(latest_by_metric.items())),
        "yfinance_proxy_metric_count": sum(
            1 for item in config.values() if item.get("source_badge") == "proxy"
        ),
        "yfinance_unofficial_fallback_metric_count": sum(
            1
            for item in config.values()
            if item.get("source_badge") == "unofficial_fallback"
        ),
        "historical_store_proxy_observation_count": source_badges.get("proxy", 0),
        "historical_store_unofficial_observation_count": source_badges.get(
            "unofficial_fallback", 0
        ),
        "insufficient_history_potentially_resolvable_by_yfinance": potentially_resolvable,
        "recommendations": sorted(set(recommendations)),
    }


def _yfinance_observation_summary(
    *,
    db_path: Path | str | None = None,
) -> dict[str, Any]:
    path = Path(db_path) if db_path is not None else market_history_store.get_default_market_history_db_path()
    if not path.exists():
        return {
            "observation_count": 0,
            "observations_by_metric": {},
            "latest_observation_by_metric": {},
            "source_badges": {},
        }
    try:
        with market_history_store.connect_market_history_db(path) as connection:
            metric_rows = connection.execute(
                """
                SELECT metric_key, COUNT(*) AS count, MAX(observation_date) AS latest
                FROM market_observations
                WHERE provider = ?
                GROUP BY metric_key
                ORDER BY metric_key
                """,
                ("yfinance",),
            ).fetchall()
            badge_rows = connection.execute(
                """
                SELECT source_badge, COUNT(*) AS count
                FROM market_observations
                WHERE provider = ?
                GROUP BY source_badge
                ORDER BY source_badge
                """,
                ("yfinance",),
            ).fetchall()
    except Exception:
        return {
            "observation_count": 0,
            "observations_by_metric": {},
            "latest_observation_by_metric": {},
            "source_badges": {},
        }
    observations_by_metric = {
        row["metric_key"]: int(row["count"]) for row in metric_rows
    }
    latest_by_metric = {
        row["metric_key"]: row["latest"] for row in metric_rows if row["latest"]
    }
    source_badges = {row["source_badge"]: int(row["count"]) for row in badge_rows}
    return {
        "observation_count": sum(observations_by_metric.values()),
        "observations_by_metric": observations_by_metric,
        "latest_observation_by_metric": latest_by_metric,
        "source_badges": source_badges,
    }


def _insufficient_history_potentially_resolvable_by_yfinance(
    rows: list[DashboardEvidenceRow],
    configured_metric_keys: set[str],
) -> list[str]:
    result: list[str] = []
    for row in rows:
        if row.status != "insufficient_history":
            continue
        spec = historical_derived_metrics.DERIVED_METRIC_SPECS.get(row.metric_key)
        if not spec:
            continue
        dependencies = {
            value
            for key, value in spec.items()
            if key in {"metric_key", "numerator_metric_key", "denominator_metric_key"}
        }
        if dependencies and dependencies.issubset(configured_metric_keys):
            result.append(row.metric_key)
    return sorted(set(result))


def _portfolio_compact_audit(rows: list[DashboardEvidenceRow]) -> dict[str, Any]:
    portfolio_rows = [row for row in rows if row.module == "portfolio_deviation"]
    compact_keys = {
        "max_deviation_asset",
        "max_deviation_pp",
        "equity_total_deviation_pp",
        "cash_reserve_status",
        "holdings_updated_at",
    }
    compact_rows = [row for row in portfolio_rows if row.metric_key in compact_keys]
    value_rows = [row for row in compact_rows if _has_value(row)]
    missing_rows = [row for row in compact_rows if not _has_value(row)]
    required_keys = {
        "max_deviation_asset",
        "max_deviation_pp",
        "equity_total_deviation_pp",
        "cash_reserve_status",
    }
    keys_with_values = {row.metric_key for row in value_rows}
    holdings_row = next(
        (row for row in compact_rows if row.metric_key == "holdings_updated_at"),
        None,
    )
    return {
        "portfolio_compact_available": required_keys.issubset(keys_with_values),
        "portfolio_deviation_value_count": len(value_rows),
        "portfolio_deviation_missing_count": len(missing_rows),
        "portfolio_deviation_ai_context_allowed_count": sum(
            1 for row in compact_rows if row.ai_context_allowed
        ),
        "portfolio_has_raw_holdings_leak": _portfolio_has_raw_holdings_leak(compact_rows),
        "portfolio_cash_excluded_from_target": _portfolio_cash_excluded_from_target(compact_rows),
        "portfolio_stale_status": holdings_row.freshness_status if holdings_row else "unknown",
    }


def _portfolio_has_raw_holdings_leak(rows: list[DashboardEvidenceRow]) -> bool:
    forbidden_tokens = (
        "holding",
        "holdings",
        "ticker",
        "fund_code",
        "fund code",
        "amount",
        "current_value",
        "market_value",
        "cost_basis",
        "profit_loss",
        "raw_fund",
    )
    safe_tokens = {
        "holdings_updated_at",
        "holdings updated at",
    }
    for row in rows:
        payload = json.dumps(_row_payload(row), ensure_ascii=False).lower()
        for token in safe_tokens:
            payload = payload.replace(token, "")
        if any(token in payload for token in forbidden_tokens):
            return True
    return False


def _row_payload(row: DashboardEvidenceRow) -> dict[str, Any]:
    if hasattr(row, "model_dump"):
        return row.model_dump()
    return row.dict()


def _portfolio_cash_excluded_from_target(rows: list[DashboardEvidenceRow]) -> bool:
    for row in rows:
        if row.metric_key != "cash_reserve_status":
            continue
        text = " ".join(
            str(item or "")
            for item in (
                row.value,
                row.value_text,
                row.interpretation_hint,
            )
        ).lower()
        return "cash" in text and "excluded" in text and "target allocation" in text
    return False


def _anomaly(
    row: DashboardEvidenceRow | None,
    anomaly_type: str,
    reason: str | None = None,
) -> dict[str, Any]:
    return {
        "type": anomaly_type,
        "reason": reason or (row.blocked_reason if row is not None else None),
        "module": row.module if row is not None else None,
        "metric_key": row.metric_key if row is not None else None,
        "row_id": row.row_id if row is not None else None,
        "detail": _anomaly_detail(row),
    }


def _anomaly_detail(row: DashboardEvidenceRow | None) -> str:
    if row is None:
        return "referenced row is absent"
    return (
        f"status={row.status}; source_badge={row.source_badge}; "
        f"freshness_status={row.freshness_status}; ai_context_allowed={row.ai_context_allowed}"
    )


def _has_value(row: DashboardEvidenceRow) -> bool:
    return row.value is not None


def _yoy_metric_suspiciously_large(row: DashboardEvidenceRow) -> bool:
    if "yoy" not in row.metric_key.lower() or not _has_value(row):
        return False
    try:
        value = float(row.value)
    except (TypeError, ValueError):
        return False
    return abs(value) > 50.0


def _is_missing_source_badge(value: str | None) -> bool:
    return value in {None, "", "missing"}


def _has_complete_metadata(row: DashboardEvidenceRow) -> bool:
    if _is_missing_source_badge(row.source_badge):
        return False
    if row.freshness_status in {"unknown", "missing", "stale", "insufficient_history"}:
        return False
    return bool(row.observation_date or row.generated_at)


def _provenance_missing(row: DashboardEvidenceRow) -> bool:
    return (
        _is_missing_source_badge(row.source_badge)
        or row.freshness_status in {"unknown", "missing"}
        or (not row.observation_date and not row.generated_at)
    )


def _source_missing(row: DashboardEvidenceRow | None) -> bool:
    if row is None:
        return True
    if row.value is None:
        return True
    if row.status in BAD_AI_STATUSES:
        return True
    if row.freshness_status in {"missing", "insufficient_history", "stale"}:
        return True
    return False


def _row_has_ok_value(row: DashboardEvidenceRow | None) -> bool:
    return bool(row is not None and row.status == "ok" and row.value is not None)


def _has_clear_history_hint(row: DashboardEvidenceRow | None) -> bool:
    if row is None:
        return False
    hint = (row.interpretation_hint or "").lower()
    reason = (row.missing_reason or "").lower()
    return "30 day" in hint or "30d" in hint or "history" in hint or "history" in reason


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
    lines.extend(["", "## yfinance History", ""])
    for key, value in audit["yfinance_history"].items():
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
