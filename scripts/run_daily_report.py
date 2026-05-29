from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from reports.daily_report import (
    build_daily_report_json,
    load_json,
    render_daily_report_markdown,
)


REPORT_DIR = PROJECT_ROOT / "outputs" / "reports"
PORTFOLIO_SNAPSHOT_PATH = REPORT_DIR / "portfolio_snapshot.json"
MARKET_SNAPSHOT_PATH = REPORT_DIR / "market_snapshot.json"
MARKET_TEMPERATURE_PATH = REPORT_DIR / "market_temperature.json"
DAILY_REPORT_JSON_PATH = REPORT_DIR / "daily_report.json"
DAILY_REPORT_MD_PATH = REPORT_DIR / "daily_report.md"

SNAPSHOT_GENERATORS = {
    PORTFOLIO_SNAPSHOT_PATH: PROJECT_ROOT / "scripts" / "run_portfolio_check.py",
    MARKET_SNAPSHOT_PATH: PROJECT_ROOT / "scripts" / "run_market_data_check.py",
    MARKET_TEMPERATURE_PATH: PROJECT_ROOT / "scripts" / "run_market_temperature_check.py",
}
SNAPSHOT_MAX_AGE_SECONDS = {
    PORTFOLIO_SNAPSHOT_PATH: 24 * 60 * 60,
    MARKET_SNAPSHOT_PATH: 24 * 60 * 60,
    MARKET_TEMPERATURE_PATH: 24 * 60 * 60,
}


def main() -> None:
    _ensure_snapshot_files()

    portfolio_snapshot = load_json(str(PORTFOLIO_SNAPSHOT_PATH))
    market_snapshot = load_json(str(MARKET_SNAPSHOT_PATH))
    market_temperature = load_json(str(MARKET_TEMPERATURE_PATH))

    report_json = build_daily_report_json(
        portfolio_snapshot=portfolio_snapshot,
        market_snapshot=market_snapshot,
        market_temperature=market_temperature,
    )
    report_markdown = render_daily_report_markdown(report_json)

    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    DAILY_REPORT_JSON_PATH.write_text(
        "\ufeff" + json.dumps(report_json, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    DAILY_REPORT_MD_PATH.write_text("\ufeff" + report_markdown + "\n", encoding="utf-8")

    print(report_markdown)


def _ensure_snapshot_files() -> None:
    for output_path, script_path in SNAPSHOT_GENERATORS.items():
        if _snapshot_is_fresh(output_path):
            print(
                json.dumps(
                    {
                        "snapshot": str(output_path.relative_to(PROJECT_ROOT)),
                        "reused_existing_snapshot": True,
                        "modified_time": _modified_time(output_path),
                    },
                    ensure_ascii=False,
                ),
                file=sys.stderr,
            )
            continue

        subprocess.run(
            [sys.executable, str(script_path)],
            cwd=str(PROJECT_ROOT),
            check=True,
            capture_output=True,
            text=True,
        )
        if not _snapshot_is_fresh(output_path):
            raise RuntimeError(
                f"Snapshot was not refreshed within max_age_seconds: {output_path}"
            )


def _snapshot_is_fresh(path: Path) -> bool:
    if not path.exists() or not path.is_file():
        return False

    max_age_seconds = SNAPSHOT_MAX_AGE_SECONDS.get(path)
    if max_age_seconds is None:
        return True

    modified_at = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
    age_seconds = (datetime.now(timezone.utc) - modified_at).total_seconds()
    return age_seconds <= max_age_seconds


def _modified_time(path: Path) -> str | None:
    if not path.exists() or not path.is_file():
        return None
    return datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc).isoformat()


if __name__ == "__main__":
    main()
