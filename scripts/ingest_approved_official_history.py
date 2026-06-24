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

from app_backend.services.official_history_ingest_service import (  # noqa: E402
    OfficialHistoryIngestService,
    build_default_official_history_ingest_service,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run an explicitly approved official-history ingest route."
    )
    parser.add_argument("--route", choices=("fred_rates", "bls_cpi"), required=True)
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--fred-limit", type=int, default=5000)
    parser.add_argument("--start-year", type=int, default=2000)
    parser.add_argument("--end-year", type=int, default=None)
    return parser


def main(
    argv: list[str] | None = None,
    *,
    service: OfficialHistoryIngestService | None = None,
    output: Any | None = None,
) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.write and not args.live:
        parser.error("--write requires --live")
    if args.fred_limit < 1:
        parser.error("--fred-limit must be >= 1")
    if args.end_year is not None and args.start_year > args.end_year:
        parser.error("--start-year must be <= --end-year")

    active_service = service or build_default_official_history_ingest_service()
    try:
        summary = active_service.run(
            args.route,
            live=args.live,
            write=args.write,
            fred_limit=args.fred_limit,
            start_year=args.start_year,
            end_year=args.end_year,
        )
    except Exception:
        summary = {
            "route_key": args.route,
            "status": "blocked",
            "live": args.live,
            "write": args.write,
            "error_codes": ["run_failed"],
        }
    print(json.dumps(summary, ensure_ascii=False, sort_keys=True), file=output or sys.stdout)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
