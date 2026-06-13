from __future__ import annotations

from pathlib import Path
from typing import Any

from app_backend.schemas.responses import DashboardEvidenceRow
from data_providers import market_data_service
from data_providers import yfinance_history_provider
from data_quality import historical_derived_metrics, liquidity_funding_stress as d14_liquidity_funding
from data_quality import market_history_store
import ingest_core_risk_history

from .common import (
    CORE_RISK_DERIVED_METRIC_KEYS,
    CORE_RISK_RAW_METRIC_KEYS,
    DEFAULT_YFINANCE_HISTORY_CONFIG,
    LIQUIDITY_FUNDING_DERIVED_METRIC_KEYS,
    LIQUIDITY_FUNDING_RAW_METRIC_KEYS,
    PROJECT_ROOT,
    _badge_count_map,
    _compact_dgs_fallback_observations,
    _metric_count_map,
    _row_status,
)


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
    by_module = historical_derived_metrics.build_historical_dashboard_candidates(
        db_path=db_path,
        fallback_observations=_compact_dgs_fallback_observations(rows),
    )
    all_metrics = [item for items in by_module.values() for item in items]
    details = [
        {
            "metric_key": item.metric_key,
            "status": item.status,
            "dependency_keys": item.dependency_keys,
            "history_points_used": item.history_points_used,
            "history_points_required": item.history_points_required,
            "missing_reason": item.missing_reason,
            "dependency_source_series": item.dependency_source_series,
            "dependency_observation_dates": item.dependency_observation_dates,
            "dependency_freshness_statuses": item.dependency_freshness_statuses,
            "input_evidence": item.input_evidence,
            "missing_inputs": item.missing_inputs,
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
    if any(
        item.metric_key in {"wti_30d_change", "brent_30d_change"}
        and item.status == "insufficient_history"
        for item in all_metrics
    ):
        actions.append("run_official_energy_history_ingest_live")
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

def _energy_history_audit(
    rows: list[DashboardEvidenceRow],
    historical_store: dict[str, Any],
) -> dict[str, Any]:
    observations = historical_store.get("observations_by_metric", {})
    rows_by_key = {row.metric_key: row for row in rows}
    wti_count = int(observations.get("wti") or 0)
    brent_count = int(observations.get("brent") or 0)
    ppifis_count = int(observations.get("ppi_final_demand") or 0)
    actions: list[str] = []
    if wti_count == 0 or brent_count == 0:
        actions.append("run_official_energy_history_ingest_live")
    if _row_status(rows_by_key.get("wti_30d_change")) == "insufficient_history" or _row_status(
        rows_by_key.get("brent_30d_change")
    ) == "insufficient_history":
        actions.append("ingest_official_energy_history")
    return {
        "energy_history_available": wti_count > 0 and brent_count > 0,
        "wti_history_observation_count": wti_count,
        "brent_history_observation_count": brent_count,
        "wti_30d_change_status": _row_status(rows_by_key.get("wti_30d_change")),
        "brent_30d_change_status": _row_status(rows_by_key.get("brent_30d_change")),
        "real_yield_pressure_status_status": _row_status(
            rows_by_key.get("real_yield_pressure_status")
        ),
        "dgs30_breakout_confirmed_status": _row_status(
            rows_by_key.get("dgs30_breakout_confirmed")
        ),
        "ppi_final_demand_status": _row_status(rows_by_key.get("ppi_final_demand")),
        "ppifis_history_observation_count": ppifis_count,
        "recommended_history_actions": sorted(set(actions)),
    }

def _liquidity_funding_history_audit(
    *,
    db_path: Path | str | None,
) -> dict[str, Any]:
    summary = d14_liquidity_funding.latest_history_summary(db_path=db_path)
    raw_counts = summary["raw_history_counts"]
    derived_counts = summary["derived_history_counts"]
    history_missing = [
        key
        for key, count in {**raw_counts, **derived_counts}.items()
        if count == 0
    ]
    recommendations = []
    if history_missing:
        recommendations.append("run_liquidity_funding_history_live_write")
    return {
        "raw_history_counts": raw_counts,
        "derived_history_counts": derived_counts,
        "latest_observation_by_metric": summary["latest_observation_by_metric"],
        "missing_history_metric_keys": sorted(history_missing),
        "source_badge_distribution": summary["source_badge_distribution"],
        "recommendations": recommendations,
    }

def _core_risk_history_audit(
    *,
    db_path: Path | str | None,
    historical_risk_percentile: dict[str, Any],
) -> dict[str, Any]:
    path = Path(db_path) if db_path is not None else market_history_store.get_default_market_history_db_path()
    mappings, missing_mappings = ingest_core_risk_history.load_official_mappings(
        market_data_service.load_data_source_config(str(DEFAULT_YFINANCE_HISTORY_CONFIG.parent / "data_sources.yaml"))
        if (DEFAULT_YFINANCE_HISTORY_CONFIG.parent / "data_sources.yaml").exists()
        else {}
    )
    yfinance_mappings = (
        ingest_core_risk_history.load_yfinance_core_mappings(DEFAULT_YFINANCE_HISTORY_CONFIG)
        if DEFAULT_YFINANCE_HISTORY_CONFIG.exists()
        else {}
    )
    if not path.exists():
        return {
            "raw_history_counts": {},
            "derived_history_counts": {},
            "missing_source_mappings": missing_mappings,
            "history_sufficient_for_d13": False,
            "official_count": 0,
            "unofficial_fallback_count": 0,
            "proxy_count": 0,
            "derived_count": 0,
            "missing_history_source_metrics": sorted(CORE_RISK_RAW_METRIC_KEYS),
            "history_sufficiency_reason": "market_history_db_missing",
            "planned_official_series": mappings,
            "planned_proxy_unofficial_series": yfinance_mappings,
        }
    try:
        with market_history_store.connect_market_history_db(path) as connection:
            raw_rows = connection.execute(
                """
                SELECT metric_key, source_badge, COUNT(*) AS count
                FROM market_observations
                WHERE metric_key IN ({})
                GROUP BY metric_key, source_badge
                """.format(",".join("?" for _ in CORE_RISK_RAW_METRIC_KEYS)),
                tuple(sorted(CORE_RISK_RAW_METRIC_KEYS)),
            ).fetchall()
            derived_rows = connection.execute(
                """
                SELECT metric_key, source_badge, COUNT(*) AS count
                FROM market_observations
                WHERE metric_key IN ({})
                GROUP BY metric_key, source_badge
                """.format(",".join("?" for _ in CORE_RISK_DERIVED_METRIC_KEYS)),
                tuple(sorted(CORE_RISK_DERIVED_METRIC_KEYS)),
            ).fetchall()
    except Exception as exc:
        return {
            "raw_history_counts": {},
            "derived_history_counts": {},
            "missing_source_mappings": missing_mappings,
            "history_sufficient_for_d13": False,
            "official_count": 0,
            "unofficial_fallback_count": 0,
            "proxy_count": 0,
            "derived_count": 0,
            "missing_history_source_metrics": sorted(CORE_RISK_RAW_METRIC_KEYS),
            "history_sufficiency_reason": f"market_history_read_error:{exc.__class__.__name__}",
            "planned_official_series": mappings,
            "planned_proxy_unofficial_series": yfinance_mappings,
        }
    raw_counts = _metric_count_map(raw_rows)
    derived_counts = _metric_count_map(derived_rows)
    badge_counts = _badge_count_map(list(raw_rows) + list(derived_rows))
    missing_history = sorted(
        metric
        for metric in CORE_RISK_RAW_METRIC_KEYS.union(CORE_RISK_DERIVED_METRIC_KEYS)
        if raw_counts.get(metric, 0) + derived_counts.get(metric, 0) == 0
    )
    computed = int(historical_risk_percentile.get("computed_count") or 0)
    configured = int(historical_risk_percentile.get("configured_count") or 0)
    return {
        "raw_history_counts": raw_counts,
        "derived_history_counts": derived_counts,
        "missing_source_mappings": missing_mappings,
        "history_sufficient_for_d13": bool(configured and computed == configured),
        "official_count": badge_counts.get("official", 0),
        "unofficial_fallback_count": badge_counts.get("unofficial_fallback", 0),
        "proxy_count": badge_counts.get("proxy", 0),
        "derived_count": badge_counts.get("derived", 0),
        "missing_history_source_metrics": missing_history,
        "history_sufficiency_reason": (
            "all_configured_d13_rows_computed"
            if configured and computed == configured
            else f"computed={computed}; configured={configured}; missing_history={missing_history}"
        ),
        "planned_official_series": mappings,
        "planned_proxy_unofficial_series": yfinance_mappings,
    }

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
