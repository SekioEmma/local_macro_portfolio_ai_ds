from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from data_providers import fred_provider, market_history_store  # noqa: E402
from data_providers.source_registry import source_audit_metadata  # noqa: E402


RATE_SERIES: dict[str, dict[str, str]] = {
    "DGS2": {"metric_key": "dgs2", "unit": "percent", "freshness_policy": "business_daily"},
    "DGS10": {"metric_key": "dgs10", "unit": "percent", "freshness_policy": "business_daily"},
    "DGS30": {"metric_key": "dgs30", "unit": "percent", "freshness_policy": "business_daily"},
    "T10Y2Y": {
        "metric_key": "t10y2y",
        "unit": "percentage_points",
        "freshness_policy": "business_daily",
    },
    "T10YIE": {
        "metric_key": "t10yie",
        "unit": "percent",
        "freshness_policy": "business_daily",
    },
    "DFII10": {
        "metric_key": "dfii10",
        "unit": "percent",
        "freshness_policy": "business_daily",
    },
}


def normalize_fred_series(
    payload: dict[str, Any],
    *,
    series_id: str,
    ingested_at: str,
) -> list[dict[str, Any]]:
    expected = RATE_SERIES[series_id]
    if payload.get("status") != "ok":
        return []
    actual_series = str(payload.get("series_id") or series_id).upper()
    if actual_series != series_id:
        raise ValueError(f"unexpected_series_id:{actual_series}")
    records: list[dict[str, Any]] = []
    for item in payload.get("data", []):
        observation_date = str(item.get("date") or "").strip()
        value = _to_float_or_none(item.get("value"))
        if not observation_date or value is None:
            continue
        audit = source_audit_metadata(
            "fred",
            source_series=series_id,
            retrieval_method="api",
            freshness_policy=expected["freshness_policy"],
            ingested_at=ingested_at,
            extra={
                "metric_key": expected["metric_key"],
                "source_priority": "official_fallback",
            },
        )
        records.append(
            {
                "metric_key": expected["metric_key"],
                "observation_date": observation_date,
                "value": value,
                "value_text": str(value),
                "unit": expected["unit"],
                "status": "ok",
                "source": "FRED",
                "source_badge": "official_fallback",
                "provider": "fred",
                "source_series": series_id,
                "generated_at": payload.get("timestamp") or ingested_at,
                "fetched_at": ingested_at,
                "freshness_status": "historical",
                "ai_context_allowed": True,
                "metric_kind": "raw",
                "lineage": audit,
            }
        )
    records.sort(key=lambda item: item["observation_date"])
    return records


def build_ingest_summary(
    *,
    db_path: Path | str | None = None,
    limit: int = 5000,
    dry_run: bool = True,
    live: bool = False,
    fetcher: Callable[[str, int], dict[str, Any]] | None = None,
) -> dict[str, Any]:
    summary: dict[str, Any] = {
        "configured_series": list(RATE_SERIES),
        "normalized_observations": 0,
        "inserted_count": 0,
        "updated_count": 0,
        "skipped_count": 0,
        "errors": [],
        "dry_run": dry_run,
        "live": live,
        "db_path": str(db_path or market_history_store.get_default_market_history_db_path()),
    }
    if not live:
        summary["skipped_count"] = len(RATE_SERIES)
        summary["errors"].append("live_disabled")
        return summary
    active_fetcher = fetcher or fred_provider.get_fred_series
    ingested_at = _utc_now()
    pending_observations: list[dict[str, Any]] = []
    for series_id in RATE_SERIES:
        payload = active_fetcher(series_id, limit)
        if payload.get("status") != "ok":
            summary["skipped_count"] += 1
            summary["errors"].append(
                f"{series_id}:{payload.get('error') or 'fetch_failed'}"
            )
            continue
        observations = normalize_fred_series(
            payload,
            series_id=series_id,
            ingested_at=ingested_at,
        )
        summary["normalized_observations"] += len(observations)
        pending_observations.extend(observations)
    if not dry_run:
        write_result = market_history_store.upsert_market_observations(
            pending_observations, db_path=db_path
        )
        summary["inserted_count"] = write_result["inserted_count"]
        summary["updated_count"] = write_result["updated_count"]
    return summary


def _to_float_or_none(value: Any) -> float | None:
    if value is None or str(value).strip() == ".":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Ingest FRED Treasury, curve, breakeven, and real-yield history."
    )
    parser.add_argument("--live", action="store_true", help="Allow live FRED API calls.")
    parser.add_argument("--write", action="store_true", help="Write to market_history.")
    parser.add_argument("--dry-run", action="store_true", help="Never write observations.")
    parser.add_argument("--limit", type=int, default=5000)
    parser.add_argument("--db-path", type=Path, default=None)
    args = parser.parse_args(argv)
    summary = build_ingest_summary(
        db_path=args.db_path,
        limit=max(1, args.limit),
        dry_run=args.dry_run or not args.write,
        live=args.live,
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
