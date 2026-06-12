from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from app_backend.schemas.responses import DashboardEvidenceRow  # noqa: E402
from app_backend.services import dashboard_service  # noqa: E402
from data_quality import market_history_store  # noqa: E402


BLOCKED_SOURCE_BADGES = {"missing", "research_needed", "search-derived"}
BLOCKED_STATUSES = {
    "missing",
    "research_needed",
    "not_available",
    "insufficient_history",
    "stale",
}


def build_ingest_summary(
    *,
    db_path: Path | str | None = None,
    reports_dir: Path | str | None = None,
    dry_run: bool = True,
    limit: int | None = None,
) -> dict[str, Any]:
    evidence = dashboard_service.build_dashboard_evidence_table(
        reports_dir=reports_dir,
        write_last_good=False,
    )
    rows = evidence.rows[:limit] if limit is not None else evidence.rows
    summary: dict[str, Any] = {
        "dry_run": dry_run,
        "db_path": str(db_path or market_history_store.get_default_market_history_db_path()),
        "candidate_count": 0,
        "inserted_count": 0,
        "updated_count": 0,
        "skipped_count": 0,
        "skipped_reasons": {},
        "metric_counts": {},
    }

    connection = None
    if not dry_run:
        path = market_history_store.initialize_market_history_db(db_path)
        connection = market_history_store.connect_market_history_db(path)

    try:
        for row in rows:
            observation, reason = observation_from_evidence_row(row)
            if observation is None:
                _record_skip(summary, reason)
                continue
            summary["candidate_count"] += 1
            metric_key = observation["metric_key"]
            summary["metric_counts"][metric_key] = summary["metric_counts"].get(metric_key, 0) + 1
            if dry_run:
                continue
            try:
                result = market_history_store.upsert_market_observation(
                    observation,
                    connection=connection,
                )
            except market_history_store.MarketHistoryValidationError as exc:
                _record_skip(summary, str(exc))
                continue
            if result["status"] == "inserted":
                summary["inserted_count"] += 1
            elif result["status"] == "updated":
                summary["updated_count"] += 1
        if connection is not None:
            connection.commit()
    finally:
        if connection is not None:
            connection.close()

    return summary


def observation_from_evidence_row(
    row: DashboardEvidenceRow,
) -> tuple[dict[str, Any] | None, str]:
    if row.module == "portfolio_deviation" or row.metric_key == "holdings_updated_at":
        return None, "portfolio_local_row"
    if row.value is None:
        return None, "value_missing"
    if not row.observation_date:
        return None, "observation_date_missing"
    if row.source_badge in BLOCKED_SOURCE_BADGES:
        return None, f"source_badge_{row.source_badge}"
    if row.status in BLOCKED_STATUSES:
        return None, f"status_{row.status}"

    metric_kind = _metric_kind(row)
    lineage = _lineage(row, metric_kind)
    if metric_kind == "derived" and not lineage:
        return None, "derived_lineage_missing"
    return {
        "metric_key": row.metric_key,
        "observation_date": row.observation_date,
        "value": row.value,
        "value_text": row.value_text,
        "unit": row.unit,
        "status": row.status,
        "source": row.source,
        "source_badge": row.source_badge,
        "provider": row.source,
        "source_series": row.source_series,
        "generated_at": row.generated_at,
        "fetched_at": row.generated_at,
        "freshness_status": row.freshness_status,
        "ai_context_allowed": row.ai_context_allowed,
        "metric_kind": metric_kind,
        "lineage": lineage,
        "raw_hash": None,
    }, "eligible"


def _metric_kind(row: DashboardEvidenceRow) -> str:
    if row.source_badge == "derived":
        return "derived"
    if row.source_badge == "proxy":
        return "proxy"
    return "raw"


def _lineage(row: DashboardEvidenceRow, metric_kind: str) -> dict[str, Any]:
    if not row.interpretation_hint and metric_kind == "raw":
        return {}
    return {
        "module": row.module,
        "source_badge": row.source_badge,
        "interpretation_hint": row.interpretation_hint,
    }


def _record_skip(summary: dict[str, Any], reason: str) -> None:
    reason_key = reason or "not_eligible"
    summary["skipped_count"] += 1
    skipped = summary["skipped_reasons"]
    skipped[reason_key] = skipped.get(reason_key, 0) + 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Dry-run or ingest Dashboard market evidence rows into the local market history store."
    )
    parser.add_argument("--dry-run", action="store_true", help="Preview ingest without creating or writing the DB.")
    parser.add_argument("--write", action="store_true", help="Write eligible rows to the market history DB.")
    parser.add_argument("--db-path", type=Path, default=None, help="Optional SQLite DB path.")
    parser.add_argument("--reports-dir", type=Path, default=None, help="Optional reports directory for tests.")
    parser.add_argument("--limit", type=int, default=None, help="Optional row processing limit.")
    args = parser.parse_args(argv)

    dry_run = not args.write
    if args.dry_run:
        dry_run = True
    summary = build_ingest_summary(
        db_path=args.db_path,
        reports_dir=args.reports_dir,
        dry_run=dry_run,
        limit=args.limit,
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
