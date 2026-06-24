from __future__ import annotations

import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from portfolio.portfolio_engine import generate_portfolio_snapshot  # noqa: E402


CURRENT_HOLDINGS_PATH = PROJECT_ROOT / "data" / "holdings" / "current_holdings.csv"
EXAMPLE_HOLDINGS_PATH = PROJECT_ROOT / "data" / "holdings" / "current_holdings.example.csv"
DEFAULT_PROFILE_PATH = PROJECT_ROOT / "configs" / "user_profile.yaml"
DEFAULT_OUTPUT_PATH = PROJECT_ROOT / "outputs" / "reports" / "portfolio_snapshot.json"


def main() -> int:
    holdings_path, holdings_source = _select_holdings_file()
    try:
        snapshot = generate_portfolio_snapshot(
            holdings_path=str(holdings_path),
            profile_path=str(DEFAULT_PROFILE_PATH),
            trading_days=21,
        )
    except ValueError as exc:
        _print_holdings_validation_error(exc, holdings_path)
        return 1
    snapshot["holdings_source"] = holdings_source

    formatted_json = json.dumps(snapshot, ensure_ascii=False, indent=2)
    print(formatted_json)

    DEFAULT_OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    DEFAULT_OUTPUT_PATH.write_text("\ufeff" + formatted_json + "\n", encoding="utf-8")
    return 0


def _select_holdings_file() -> tuple[Path, dict]:
    if CURRENT_HOLDINGS_PATH.exists():
        return CURRENT_HOLDINGS_PATH, {
            "path": str(CURRENT_HOLDINGS_PATH),
            "mode": "current_holdings",
            "warning": (
                "Using user-provided current_holdings.csv local snapshot. "
                "It was manually entered from a user-confirmed holdings screenshot "
                "and is not guaranteed to be real-time."
            ),
            "cash_reserve_note": (
                "asset_class=cash is treated as cash reserve and DCA deduction source; "
                "it is excluded from target-allocation weights. Current cash reserve may "
                "already reflect this month's transfer and several trading-day deductions; "
                "do not treat it as remaining monthly contribution amount."
            ),
        }

    return EXAMPLE_HOLDINGS_PATH, {
        "path": str(EXAMPLE_HOLDINGS_PATH),
        "mode": "example_holdings",
        "warning": (
            "Using committed placeholder holdings because current_holdings.csv was not found. "
            "Create data/holdings/current_holdings.csv for real local use; it is ignored by Git."
        ),
        "cash_reserve_note": (
            "asset_class=cash is treated as cash reserve and excluded from target-allocation weights."
        ),
    }


def _print_holdings_validation_error(exc: ValueError, holdings_path: Path) -> None:
    summary = {
        "status": "input_error",
        "input": str(holdings_path),
        "error": _sanitize_validation_message(str(exc)),
        "template_path": str(EXAMPLE_HOLDINGS_PATH),
        "hint": (
            "Check required columns and numeric money fields. "
            "Do not commit data/holdings/current_holdings.csv."
        ),
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2), file=sys.stderr)


def _sanitize_validation_message(message: str) -> str:
    for field in ("current_value", "cost_basis", "profit_loss"):
        marker = f"has invalid {field}: "
        if marker in message:
            return message.split(marker, 1)[0] + marker + "<redacted>."
    return message


if __name__ == "__main__":
    raise SystemExit(main())
