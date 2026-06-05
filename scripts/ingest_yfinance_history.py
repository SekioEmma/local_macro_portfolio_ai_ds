from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Callable


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
DEFAULT_CONFIG_PATH = PROJECT_ROOT / "configs" / "yfinance_history.yaml"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from data_providers import yfinance_history_provider  # noqa: E402
from data_quality import market_history_store  # noqa: E402


def build_ingest_summary(
    *,
    config_path: Path | str | None = None,
    db_path: Path | str | None = None,
    period: str = "6mo",
    interval: str = "1d",
    dry_run: bool = True,
    live: bool = False,
    downloader: Callable[..., Any] | None = None,
) -> dict[str, Any]:
    config = yfinance_history_provider.load_yfinance_history_config(
        config_path or DEFAULT_CONFIG_PATH
    )
    symbols = sorted(config)
    summary: dict[str, Any] = {
        "configured_symbols": len(config),
        "enabled_symbols": len(symbols),
        "fetched_symbols": 0,
        "normalized_observations": 0,
        "inserted_count": 0,
        "updated_count": 0,
        "skipped_count": 0,
        "skipped_reasons": {},
        "source_badge_distribution": {},
        "dry_run": dry_run,
        "live": live,
        "period": period,
        "interval": interval,
        "db_path": str(db_path or market_history_store.get_default_market_history_db_path()),
    }
    if not live:
        summary["skipped_reasons"]["live_disabled"] = len(symbols)
        summary["skipped_count"] = len(symbols)
        return summary

    fetched = yfinance_history_provider.fetch_yfinance_batch_history(
        symbols,
        period=period,
        interval=interval,
        downloader=downloader,
    )
    if fetched["status"] != "ok":
        summary["skipped_reasons"]["fetch_error"] = len(symbols)
        summary["skipped_count"] = len(symbols)
        summary["error"] = fetched.get("error")
        return summary

    normalized = yfinance_history_provider.normalize_yfinance_history(
        fetched["raw_data"],
        config,
        fetched_at=fetched["generated_at"],
    )
    records = normalized["records"]
    summary["fetched_symbols"] = len(symbols)
    summary["normalized_observations"] = len(records)
    for error in normalized["errors"]:
        _record_skip(summary, f"normalize_error:{error['symbol']}")

    observations = yfinance_history_provider.build_market_observations_from_yfinance(records)
    for observation in observations:
        badge = str(observation["source_badge"])
        summary["source_badge_distribution"][badge] = (
            summary["source_badge_distribution"].get(badge, 0) + 1
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
        description="Dry-run or ingest yfinance batch history into the local market history store."
    )
    parser.add_argument("--dry-run", action="store_true", help="Preview without writing.")
    parser.add_argument("--write", action="store_true", help="Write normalized observations.")
    parser.add_argument("--live", action="store_true", help="Allow live yfinance download.")
    parser.add_argument("--period", default="6mo", help="yfinance period, for example 6mo or 1y.")
    parser.add_argument("--interval", default="1d", help="yfinance interval, default 1d.")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG_PATH)
    parser.add_argument("--db-path", type=Path, default=None)
    args = parser.parse_args(argv)

    dry_run = not args.write
    if args.dry_run:
        dry_run = True
    summary = build_ingest_summary(
        config_path=args.config,
        db_path=args.db_path,
        period=args.period,
        interval=args.interval,
        dry_run=dry_run,
        live=args.live,
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
