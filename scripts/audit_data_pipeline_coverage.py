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


def build_coverage_audit(reports_dir: Path | str | None = None) -> dict[str, Any]:
    summary = dashboard_service.build_dashboard_summary(reports_dir=reports_dir)
    evidence = dashboard_service.build_dashboard_evidence_table(reports_dir=reports_dir)
    rows = evidence.rows

    metadata_anomalies = _metadata_anomalies(rows)
    dependency_anomalies = _dependency_anomalies(summary.modules, rows)
    portfolio_compact = _portfolio_compact_audit(rows)

    return {
        "generated_at": summary.generated_at,
        "overall_status": summary.overall_status,
        "coverage_summary": _coverage_summary(rows),
        "module_coverage": _module_coverage(summary.modules, rows),
        "portfolio_compact": portfolio_compact,
        "metadata_anomalies": metadata_anomalies,
        "derived_dependency_anomalies": dependency_anomalies,
        "blocked_reason_counts": _blocked_reason_counts(rows),
        "source_badge_distribution": _source_badge_distribution(rows),
        "ai_context_allowed_by_module": _ai_context_allowed_by_module(rows),
        "recommendations": _recommendations(
            metadata_anomalies,
            dependency_anomalies,
            portfolio_compact,
        ),
    }


def _coverage_summary(rows: list[DashboardEvidenceRow]) -> dict[str, int]:
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
    }


def _module_coverage(modules: dict[str, Any], rows: list[DashboardEvidenceRow]) -> list[dict[str, Any]]:
    by_module = {module: [row for row in rows if row.module == module] for module in modules}
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
    recommendations.extend(
        [
            "implement_last_good_cache",
            "implement_historical_store",
            "add_yfinance_batch_history",
            "add_official_macro_pack",
        ]
    )
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
