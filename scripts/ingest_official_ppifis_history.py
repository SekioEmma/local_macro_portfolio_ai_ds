from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Callable


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
DEFAULT_CONFIG_PATH = PROJECT_ROOT / "configs" / "data_sources.yaml"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from data_providers import market_data_service, official_ppi_history_provider  # noqa: E402
from data_quality import market_history_store  # noqa: E402


def build_ingest_summary(
    *,
    config_path: Path | str | None = None,
    db_path: Path | str | None = None,
    limit: int = 180,
    dry_run: bool = True,
    live: bool = False,
    fetcher: Callable[[str, int], dict[str, Any]] | None = None,
) -> dict[str, Any]:
    data_sources = market_data_service.load_data_source_config(str(config_path or DEFAULT_CONFIG_PATH))
    config = official_ppi_history_provider.load_official_ppi_history_config(data_sources)
    metric_keys = sorted(config)
    summary: dict[str, Any] = {
        "configured_metrics": len(config),
        "enabled_metrics": metric_keys,
        "fetched_metrics": 0,
        "normalized_observations": 0,
        "inserted_count": 0,
        "updated_count": 0,
        "skipped_count": 0,
        "skipped_reasons": {},
        "source_badge_distribution": {},
        "source_series_distribution": {},
        "dry_run": dry_run,
        "live": live,
        "limit": limit,
        "db_path": str(db_path or market_history_store.get_default_market_history_db_path()),
    }
    if not live:
        summary["skipped_count"] = len(metric_keys)
        summary["skipped_reasons"]["live_disabled"] = len(metric_keys)
        return summary

    fetched = official_ppi_history_provider.fetch_official_ppi_history(
        config,
        limit=limit,
        fetcher=fetcher,
    )
    summary["fetched_metrics"] = len(fetched.get("raw_data", {}))
    for error in fetched.get("errors", []):
        _record_skip(summary, f"fetch_error:{error.get('metric_key')}")

    normalized = official_ppi_history_provider.normalize_official_ppi_history(
        fetched.get("raw_data", {}),
        config,
        fetched_at=fetched.get("generated_at"),
    )
    records = normalized["records"]
    summary["normalized_observations"] = len(records)
    for error in normalized["errors"]:
        _record_skip(summary, f"normalize_error:{error.get('metric_key')}")

    observations = official_ppi_history_provider.build_market_observations(records)
    for observation in observations:
        badge = str(observation["source_badge"])
        series = str(observation["source_series"])
        summary["source_badge_distribution"][badge] = (
            summary["source_badge_distribution"].get(badge, 0) + 1
        )
        summary["source_series_distribution"][series] = (
            summary["source_series_distribution"].get(series, 0) + 1
        )
        if dry_run:
            continue
        try:
            result = market_history_store.upsert_market_observation(
                observation,
                db_path=db_path,
            )
        except market_history_store.MarketHistoryValidationError as exc:
            _record_skip(summary, str(exc))
            continue
        if result["status"] == "inserted":
            summary["inserted_count"] += 1
        elif result["status"] == "updated":
            summary["updated_count"] += 1
    return summary


def _record_skip(summary: dict[str, Any], reason: str) -> None:
    key = reason or "not_eligible"
    summary["skipped_count"] += 1
    summary["skipped_reasons"][key] = summary["skipped_reasons"].get(key, 0) + 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Dry-run or ingest official FRED PPIFIS PPI Final Demand history into market_history."
    )
    parser.add_argument("--dry-run", action="store_true", help="Preview without writing.")
    parser.add_argument("--write", action="store_true", help="Write normalized observations.")
    parser.add_argument("--live", action="store_true", help="Allow live FRED download.")
    parser.add_argument("--limit", type=int, default=180, help="FRED observation limit.")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG_PATH)
    parser.add_argument("--db-path", type=Path, default=None)
    args = parser.parse_args(argv)

    dry_run = not args.write
    if args.dry_run:
        dry_run = True
    summary = build_ingest_summary(
        config_path=args.config,
        db_path=args.db_path,
        limit=args.limit,
        dry_run=dry_run,
        live=args.live,
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
