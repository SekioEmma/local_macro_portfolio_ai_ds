from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from data_quality import historical_validation  # noqa: E402
from app_backend.services.historical_validation_event_registry import (  # noqa: E402
    get_historical_validation_event_registry,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run read-only D19 historical validation replay."
    )
    parser.add_argument(
        "--market-history-db",
        type=Path,
        default=None,
        help="Optional local market_history SQLite path.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Optional JSON output path. Defaults to stdout only.",
    )
    parser.add_argument(
        "--event-id",
        default=None,
        help="Optional event window id filter.",
    )
    parser.add_argument(
        "--format",
        choices=("json", "text"),
        default="json",
        help="Output format. Defaults to json.",
    )
    parser.add_argument(
        "--include-event-registry",
        action="store_true",
        help="Include the static D19 v0 event registry in JSON output.",
    )
    parser.add_argument(
        "--show-events",
        action="store_true",
        help="Print the static D19 v0 event registry and exit.",
    )
    args = parser.parse_args(argv)

    if args.show_events:
        registry = get_historical_validation_event_registry()
        payload = (
            _format_event_registry_text(registry)
            if args.format == "text"
            else json.dumps(registry, ensure_ascii=False, indent=2, sort_keys=True)
        )
        print(payload)
        return 0

    event_windows = historical_validation.EVENT_WINDOWS
    if args.event_id:
        event_windows = tuple(
            event
            for event in historical_validation.EVENT_WINDOWS
            if event.event_id == args.event_id
        )
        if not event_windows:
            parser.error(f"unknown --event-id: {args.event_id}")

    summary = historical_validation.build_historical_validation_summary(
        db_path=str(args.market_history_db) if args.market_history_db else None,
        event_windows=event_windows,
    )
    if args.include_event_registry:
        summary = {
            **summary,
            "d19_v0_event_registry": get_historical_validation_event_registry(),
        }
    payload = (
        _format_text(summary)
        if args.format == "text"
        else json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True)
    )
    print(payload)
    if args.output is not None:
        _validate_output_path(args.output)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(payload + "\n", encoding="utf-8")
    return 0


def _format_text(summary: dict) -> str:
    lines = [
        f"model_key: {summary['model_key']}",
        f"status: {summary['status']}",
        (
            "events: "
            f"{summary['event_count']} total, "
            f"{summary['available_event_count']} available, "
            f"{summary['limited_replay_event_count']} limited, "
            f"{summary['insufficient_history_event_count']} insufficient"
        ),
        f"boundary_violations: {summary['boundary_violation_count']}",
    ]
    for event in summary["events"]:
        lines.append(
            f"- {event['event_id']}: {event['coverage_status']} "
            f"({event['available_day_count']} available days)"
        )
    return "\n".join(lines)


def _format_event_registry_text(registry: list[dict]) -> str:
    lines = [f"d19_v0_event_registry_count: {len(registry)}"]
    for event in registry:
        groups = ", ".join(event["expected_pressure_groups"])
        lines.append(
            f"- {event['event_id']}: {event['event_type']} "
            f"({event['start_date']} to {event['end_date']}; groups: {groups})"
        )
    return "\n".join(lines)


def _validate_output_path(path: Path) -> None:
    lowered_parts = {part.lower() for part in path.parts}
    forbidden_parts = {"outputs", "cache", "private", "holdings"}
    forbidden_suffixes = {".db", ".sqlite", ".sqlite3"}
    if lowered_parts & forbidden_parts or path.name.lower() == ".env":
        raise SystemExit("--output may not target outputs/cache/private/holdings/.env paths")
    if path.suffix.lower() in forbidden_suffixes:
        raise SystemExit("--output must be a JSON/text file, not a database path")


if __name__ == "__main__":
    raise SystemExit(main())
