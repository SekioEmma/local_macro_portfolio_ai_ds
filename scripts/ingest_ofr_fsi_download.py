from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from data_providers import market_history_store, ofr_fsi_provider  # noqa: E402
from data_providers.source_registry import source_audit_metadata  # noqa: E402


def build_market_observation(row: dict, *, metadata: dict) -> dict:
    audit = source_audit_metadata(
        "ofr",
        source_series=row["source_series"],
        retrieval_method=metadata["retrieval_method"],
        freshness_policy="business_daily_two_day_lag",
        source_badge="official_reference",
        ingested_at=row["ingested_at"],
        extra={
            "download_location": metadata["url"],
            "last_modified": metadata.get("last_modified"),
            "raw_payload_hash": metadata["raw_payload_hash"],
            "model_boundary": ["D10_not_replaced", "D11_not_replaced"],
        },
    )
    return {
        "metric_key": row["metric_key"],
        "observation_date": row["observation_date"],
        "value": row["value"],
        "value_text": str(row["value"]),
        "unit": "index_contribution",
        "status": "ok",
        "source": "OFR",
        "source_badge": "official_reference",
        "provider": "ofr",
        "source_series": row["source_series"],
        "fetched_at": row["ingested_at"],
        "freshness_status": "historical",
        "ai_context_allowed": True,
        "metric_kind": "raw",
        "lineage": audit,
        "raw_hash": metadata["raw_payload_hash"],
    }


def build_ingest_summary(
    *,
    file_path: Path | None = None,
    url: str | None = None,
    db_path: Path | str | None = None,
    dry_run: bool = True,
) -> dict:
    active_url = url
    if file_path is None and active_url is None:
        active_url = ofr_fsi_provider.OFR_FSI_FALLBACK_URL
    metadata = ofr_fsi_provider.load_csv_source(
        file_path=file_path,
        url=active_url,
    )
    if metadata.get("status") != "ok":
        return {
            "status": "error",
            "error": metadata.get("error"),
            "normalized_observations": 0,
            "inserted_count": 0,
            "updated_count": 0,
        }
    rows = ofr_fsi_provider.parse_fsi_csv(
        metadata["content"], ingested_at=metadata["retrieved_at"]
    )
    summary = {
        "status": "ok",
        "download_location": metadata["url"],
        "retrieval_method": metadata["retrieval_method"],
        "raw_payload_hash": metadata["raw_payload_hash"],
        "normalized_observations": len(rows),
        "inserted_count": 0,
        "updated_count": 0,
        "dry_run": dry_run,
    }
    for row in rows:
        if dry_run:
            continue
        result = market_history_store.upsert_market_observation(
            build_market_observation(row, metadata=metadata),
            db_path=db_path,
        )
        summary[f"{result['status']}_count"] += 1
    return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Ingest the official OFR Financial Stress Index download."
    )
    source = parser.add_mutually_exclusive_group()
    source.add_argument("--file", type=Path)
    source.add_argument("--url")
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--db-path", type=Path, default=None)
    args = parser.parse_args(argv)
    summary = build_ingest_summary(
        file_path=args.file,
        url=args.url,
        db_path=args.db_path,
        dry_run=args.dry_run or not args.write,
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if summary["status"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
