from __future__ import annotations

import argparse
import json
import sys
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Callable


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from research_context import gdelt_client, research_context_store  # noqa: E402
from research_context.gdelt_registry import QUERY_PRESETS  # noqa: E402


EVENT_PRESETS = [
    key for key, preset in QUERY_PRESETS.items() if preset.endpoint == "events"
]


def build_ingest_summary(
    *,
    query_key: str,
    window_start: str,
    window_end: str,
    db_path: Path | str | None = None,
    dry_run: bool = True,
    live: bool = False,
    requester: Callable[..., dict[str, Any]] | None = None,
) -> dict[str, Any]:
    gdelt_client.validate_window(window_start, window_end)
    summary = {
        "query_key": query_key,
        "window_start": window_start,
        "window_end": window_end,
        "normalized_buckets": 0,
        "upserted_buckets": 0,
        "dry_run": dry_run,
        "live": live,
        "status": "not_run",
    }
    if not live:
        summary["error"] = "live_disabled"
        return summary
    active_requester = requester or gdelt_client.fetch_summary
    result = active_requester(
        summary_kind="events",
        query_key=query_key,
        window_start=window_start,
        window_end=window_end,
    )
    if result.get("status") != "ok":
        summary["status"] = str(result.get("status") or "error")
        summary["error"] = result.get("error")
        return summary
    buckets = gdelt_client.normalize_event_summary(
        result["payload"],
        query_key=query_key,
        window_start=window_start,
        window_end=window_end,
        ingested_at=result["retrieved_at"],
        raw_payload_hash=result["raw_payload_hash"],
    )
    summary["status"] = "ok"
    summary["normalized_buckets"] = len(buckets)
    for bucket in buckets:
        if dry_run:
            continue
        research_context_store.upsert_event_bucket(bucket, db_path=db_path)
        summary["upserted_buckets"] += 1
    return summary


def main(argv: list[str] | None = None) -> int:
    today = date.today()
    parser = argparse.ArgumentParser(
        description="Ingest aggregate GDELT Cloud event summary buckets."
    )
    parser.add_argument("--preset", required=True, choices=sorted(EVENT_PRESETS))
    parser.add_argument("--start-date", default=(today - timedelta(days=6)).isoformat())
    parser.add_argument("--end-date", default=today.isoformat())
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--db-path", type=Path, default=None)
    args = parser.parse_args(argv)
    summary = build_ingest_summary(
        query_key=args.preset,
        window_start=args.start_date,
        window_end=args.end_date,
        db_path=args.db_path,
        dry_run=args.dry_run or not args.write,
        live=args.live,
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if summary["status"] in {"ok", "not_run", "not_available"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
