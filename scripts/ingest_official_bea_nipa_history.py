from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Callable


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from data_providers import bea_history_provider, market_history_store  # noqa: E402
from data_providers.source_registry import source_audit_metadata  # noqa: E402


def build_market_observation(row: dict[str, Any]) -> dict[str, Any]:
    audit = source_audit_metadata(
        "bea",
        source_series=f"NIPA:{row['table']}:{row['line']}",
        retrieval_method="api",
        freshness_policy="monthly_release"
        if row["frequency"] == "M"
        else "quarterly_release",
        ingested_at=row["ingested_at"],
        extra={
            "table": row["table"],
            "line": row["line"],
            "frequency": row["frequency"],
            "line_description": row["line_description"],
            "series_code": row["series_code"],
            "source_priority": "primary_over_fred",
            "transform": row["transform"],
        },
    )
    if row["transform"] == "yoy":
        audit["prior_observation_date"] = row["prior_observation_date"]
    return {
        "metric_key": row["metric_key"],
        "observation_date": row["observation_date"],
        "value": row["value"],
        "value_text": f"{row['value']:.4f}",
        "unit": row["unit"],
        "status": "ok",
        "source": "BEA",
        "source_badge": "official",
        "provider": "bea",
        "source_series": f"NIPA:{row['table']}:{row['line']}",
        "fetched_at": row["ingested_at"],
        "freshness_status": "historical",
        "ai_context_allowed": True,
        "metric_kind": "derived" if row["transform"] == "yoy" else "raw",
        "lineage": audit,
    }


def build_ingest_summary(
    *,
    db_path: Path | str | None = None,
    year: str = "X",
    dry_run: bool = True,
    live: bool = False,
    requester: Callable[[dict[str, str]], dict[str, Any]] | None = None,
    api_key: str | None = None,
) -> dict[str, Any]:
    summary: dict[str, Any] = {
        "configured_metrics": list(bea_history_provider.BEA_NIPA_MAPPINGS),
        "normalized_observations": 0,
        "inserted_count": 0,
        "updated_count": 0,
        "errors": [],
        "dry_run": dry_run,
        "live": live,
    }
    if not live:
        summary["errors"].append("live_disabled")
        return summary
    active_key = api_key or bea_history_provider.load_bea_api_key()
    if not active_key:
        summary["errors"].append("BEA_API_KEY not configured")
        return summary
    active_requester = requester or bea_history_provider.request_bea
    grouped: dict[tuple[str, str], list[str]] = {}
    for metric_key, mapping in bea_history_provider.BEA_NIPA_MAPPINGS.items():
        grouped.setdefault((mapping["table"], mapping["frequency"]), []).append(metric_key)
    for (table, frequency), metric_keys in grouped.items():
        result = active_requester(
            bea_history_provider.build_bea_getdata_params(
                api_key=active_key,
                table=table,
                frequency=frequency,
                year=year,
            )
        )
        if result.get("status") != "ok":
            summary["errors"].append(f"{table}:{result.get('error') or 'fetch_failed'}")
            continue
        for metric_key in metric_keys:
            try:
                raw_rows = bea_history_provider.normalize_table_rows(
                    result["payload"],
                    metric_key=metric_key,
                    ingested_at=str(result.get("retrieved_at") or ""),
                )
                rows = bea_history_provider.calculate_bea_metric(raw_rows)
            except ValueError as exc:
                summary["errors"].append(str(exc))
                continue
            summary["normalized_observations"] += len(rows)
            for row in rows:
                if dry_run:
                    continue
                write_result = market_history_store.upsert_market_observation(
                    build_market_observation(row), db_path=db_path
                )
                summary[f"{write_result['status']}_count"] += 1
    return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Ingest confirmed BEA NIPA PCE and GDP history.")
    parser.add_argument("--year", default="X")
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--db-path", type=Path, default=None)
    args = parser.parse_args(argv)
    summary = build_ingest_summary(
        db_path=args.db_path,
        year=args.year,
        dry_run=args.dry_run or not args.write,
        live=args.live,
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
