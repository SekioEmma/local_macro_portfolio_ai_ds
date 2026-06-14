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
    args = parser.parse_args(argv)

    summary = historical_validation.build_historical_validation_summary(
        db_path=str(args.market_history_db) if args.market_history_db else None
    )
    payload = json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True)
    print(payload)
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(payload + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
