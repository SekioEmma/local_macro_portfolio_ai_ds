from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, TextIO


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
DEFAULT_MANUAL_OAS_MONTHLY = (
    PROJECT_ROOT
    / "data"
    / "manual_capture"
    / "oas"
    / "high_yield_spread_manual_audited_monthly.csv"
)

if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from data_quality import phase_e_return_band_diagnostics as phase_e  # noqa: E402


def build_phase_e_input_audit(
    *,
    manual_oas_monthly: Path | str | None = DEFAULT_MANUAL_OAS_MONTHLY,
    real_yield_policy: str = "requires_decision",
    generated_at: str | None = None,
) -> dict[str, Any]:
    series_by_key: dict[str, list[phase_e.MonthlyObservation]] = {}
    source_files: dict[str, Any] = {}

    if manual_oas_monthly is not None:
        path = Path(manual_oas_monthly)
        source_files["manual_oas_monthly"] = _source_file_summary(path)
        if path.exists():
            try:
                rows = phase_e.load_manual_oas_monthly_csv(path)
            except (OSError, ValueError) as exc:
                return _blocked_payload(
                    generated_at=generated_at,
                    real_yield_policy=real_yield_policy,
                    source_files=source_files,
                    error_code="manual_oas_monthly_load_failed",
                    error_type=type(exc).__name__,
                )
            series_by_key["high_yield_spread"] = rows
            source_files["manual_oas_monthly"].update(
                {
                    "loaded": True,
                    "row_count": len(rows),
                    "source_method": phase_e.MANUAL_AUDITED_DOWNLOAD,
                    "source_series": sorted({row.source_series for row in rows}),
                }
            )

    diagnostics = phase_e.build_phase_e_factor_diagnostics(
        series_by_key,
        real_yield_policy=real_yield_policy,
    )
    return {
        "generated_at": generated_at or datetime.now(timezone.utc).isoformat(),
        "phase": "E",
        "status": diagnostics["status"],
        "mode": "input_audit_only",
        "safety": _safety_summary(),
        "source_files": source_files,
        "phase_e_readiness": {
            "framework_development_allowed": True,
            "numerical_return_band_allowed": diagnostics["status"] == "ok",
            "blocking_factors": diagnostics["blocking_factors"],
            "real_yield_policy": real_yield_policy,
        },
        "diagnostics": diagnostics,
    }


def main(argv: list[str] | None = None, output: TextIO | None = None) -> int:
    args = _parse_args(argv)
    payload = build_phase_e_input_audit(
        manual_oas_monthly=args.manual_oas_monthly,
        real_yield_policy=args.real_yield_policy,
    )
    rendered = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if args.save_json:
        args.save_json.parent.mkdir(parents=True, exist_ok=True)
        args.save_json.write_text(rendered, encoding="utf-8")
    print(rendered, end="", file=output or sys.stdout)
    return 0


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Audit Phase E input readiness without computing return-band values.",
    )
    parser.add_argument(
        "--manual-oas-monthly",
        type=Path,
        default=DEFAULT_MANUAL_OAS_MONTHLY,
        help="Path to the normalized manual-audited HY OAS monthly CSV.",
    )
    parser.add_argument(
        "--real-yield-policy",
        choices=("requires_decision", "dfii10"),
        default="requires_decision",
        help="Policy gate for real_yield_10y until the project semantic choice is confirmed.",
    )
    parser.add_argument(
        "--save-json",
        type=Path,
        help="Optional JSON output path. Defaults to stdout only.",
    )
    return parser.parse_args(argv)


def _blocked_payload(
    *,
    generated_at: str | None,
    real_yield_policy: str,
    source_files: dict[str, Any],
    error_code: str,
    error_type: str,
) -> dict[str, Any]:
    diagnostics = phase_e.build_phase_e_factor_diagnostics(
        {},
        real_yield_policy=real_yield_policy,
    )
    return {
        "generated_at": generated_at or datetime.now(timezone.utc).isoformat(),
        "phase": "E",
        "status": "blocked",
        "mode": "input_audit_only",
        "safety": _safety_summary(),
        "source_files": source_files,
        "error": {"code": error_code, "type": error_type},
        "phase_e_readiness": {
            "framework_development_allowed": True,
            "numerical_return_band_allowed": False,
            "blocking_factors": diagnostics["blocking_factors"],
            "real_yield_policy": real_yield_policy,
        },
        "diagnostics": diagnostics,
    }


def _source_file_summary(path: Path) -> dict[str, Any]:
    return {
        "path": _safe_path_label(path),
        "exists": path.exists(),
        "loaded": False,
    }


def _safe_path_label(path: Path) -> str:
    try:
        resolved = path.resolve()
        return resolved.relative_to(PROJECT_ROOT.resolve()).as_posix()
    except ValueError:
        return f"<external_{path.name or 'path'}>"


def _safety_summary() -> dict[str, bool]:
    return {
        "network_access": False,
        "reads_database": False,
        "writes_database": False,
        "reads_private_holdings": False,
        "emits_raw_series_values": False,
        "computes_return_band_values": False,
    }


if __name__ == "__main__":
    raise SystemExit(main())
