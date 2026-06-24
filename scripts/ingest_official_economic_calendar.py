#!/usr/bin/env python
"""Manual CLI for official economic calendar acquisition.

Default mode is planned (no fetch, no write). Use --live for fetch+parse,
and --live --write for actual DB writes. Only BLS and BEA are supported.

Usage:
    python scripts/ingest_official_economic_calendar.py
    python scripts/ingest_official_economic_calendar.py --source bls --source bea --live
    python scripts/ingest_official_economic_calendar.py --source bls --source bea --live --write
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from app_backend.services.official_calendar_acquisition_service import (  # noqa: E402
    build_default_official_calendar_acquisition_service,
)

_ALLOWED_SOURCES = ("bls", "bea")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Guarded official economic calendar acquisition",
    )
    parser.add_argument(
        "--source",
        action="append",
        choices=_ALLOWED_SOURCES,
        help="Source to ingest (repeatable; default: bls + bea)",
    )
    parser.add_argument("--start-date", default=None, help="ISO start date")
    parser.add_argument("--end-date", default=None, help="ISO end date")
    parser.add_argument("--live", action="store_true", help="Enable live fetch")
    parser.add_argument("--write", action="store_true", help="Enable DB write (requires --live)")
    args = parser.parse_args()

    sources = tuple(args.source) if args.source else ("bls", "bea")

    service = build_default_official_calendar_acquisition_service()
    try:
        summary = service.run(
            source_keys=sources,
            start_date=args.start_date,
            end_date=args.end_date,
            live=args.live,
            write=args.write,
        )
    except ValueError as exc:
        print(json.dumps({"status": "error", "code": str(exc)}, indent=2))
        return 1

    output = {
        "status": summary.status,
        "live": summary.live,
        "write": summary.write,
        "selected_sources": list(summary.selected_sources),
        "start_date": summary.start_date,
        "end_date": summary.end_date,
        "event_count": summary.event_count,
        "event_key_counts": summary.event_key_counts,
        "created_count": summary.created_count,
        "updated_count": summary.updated_count,
        "unavailable_event_keys": list(summary.unavailable_event_keys),
        "error_codes": summary.error_codes,
    }
    print(json.dumps(output, indent=2))
    return 0 if summary.status in ("ok", "planned", "dry_run") else 1


if __name__ == "__main__":
    sys.exit(main())
