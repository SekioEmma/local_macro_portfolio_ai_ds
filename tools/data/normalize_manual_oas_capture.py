from __future__ import annotations

import argparse
import csv
import glob
import json
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from statistics import mean, median
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "data" / "manual_capture" / "oas"
DEFAULT_INPUT_GLOB = "G:/local_macro_portfolio_ai/**/oas_capture_raw.csv"
SOURCE_URL = "https://sc.macromicro.me/series/78167/us-ice-bofa-us-high-yield-index-option-adjusted-spread"


@dataclass(frozen=True)
class ParsedRow:
    line_number: int
    date: date
    oas_percent: float
    source_url: str
    captured_at: str
    raw_tooltip: str


def main() -> None:
    args = parse_args()
    input_path = resolve_input_path(args.input, args.input_glob)
    raw_rows = read_rows(input_path)
    unique_rows, duplicate_dates, conflicts = dedupe_by_date(raw_rows)
    monthly_rows = select_monthly_last_observations(unique_rows)
    report = build_quality_report(
        input_path=input_path,
        raw_rows=raw_rows,
        unique_rows=unique_rows,
        monthly_rows=monthly_rows,
        duplicate_dates=duplicate_dates,
        conflicts=conflicts,
    )

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    daily_path = output_dir / "high_yield_spread_manual_audited_daily.csv"
    monthly_path = output_dir / "high_yield_spread_manual_audited_monthly.csv"
    report_path = output_dir / "high_yield_spread_manual_audited_quality_report.json"
    manifest_path = output_dir / "high_yield_spread_manual_audited_manifest.json"

    write_daily_csv(daily_path, unique_rows)
    write_monthly_csv(monthly_path, monthly_rows)
    write_json(report_path, report)
    write_json(manifest_path, build_manifest(input_path, daily_path, monthly_path, report_path, report))

    print(
        json.dumps(
            {
                "input": str(input_path),
                "daily_csv": str(daily_path),
                "monthly_csv": str(monthly_path),
                "quality_report": str(report_path),
                "manifest": str(manifest_path),
                "raw_rows": len(raw_rows),
                "unique_dates": len(unique_rows),
                "monthly_rows": len(monthly_rows),
                "missing_month_count": report["monthly_coverage"]["missing_month_count"],
                "meets_phase_e_84m_gate": report["phase_e_gate_review"]["meets_84_month_minimum"],
                "meets_phase_e_60m_aux_gate": report["phase_e_gate_review"]["meets_60_month_auxiliary_minimum"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Normalize manually audited MacroMicro HY OAS tooltip captures."
    )
    parser.add_argument(
        "--input",
        type=Path,
        help="Path to oas_capture_raw.csv. If omitted, --input-glob is used.",
    )
    parser.add_argument(
        "--input-glob",
        default=DEFAULT_INPUT_GLOB,
        help="Glob used when --input is omitted.",
    )
    parser.add_argument(
        "--output-dir",
        default=DEFAULT_OUTPUT_DIR,
        help="Directory for normalized local-only outputs.",
    )
    return parser.parse_args()


def resolve_input_path(path: Path | None, input_glob: str) -> Path:
    if path is not None:
        resolved = path.expanduser().resolve()
        if not resolved.exists():
            raise FileNotFoundError(resolved)
        return resolved

    matches = sorted(Path(match) for match in glob.glob(input_glob, recursive=True))
    if not matches:
        raise FileNotFoundError(f"no files matched {input_glob!r}")
    return max(matches, key=lambda item: item.stat().st_mtime)


def read_rows(path: Path) -> list[ParsedRow]:
    rows: list[ParsedRow] = []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        required = {"date", "oas_percent", "source_url", "captured_at", "raw_tooltip"}
        missing = required - set(reader.fieldnames or [])
        if missing:
            raise ValueError(f"missing required columns: {sorted(missing)}")
        for line_number, row in enumerate(reader, start=2):
            observation_date = date.fromisoformat(str(row["date"]).strip())
            oas_percent = float(str(row["oas_percent"]).strip())
            if not 0 <= oas_percent <= 100:
                raise ValueError(f"line {line_number}: oas_percent out of range")
            rows.append(
                ParsedRow(
                    line_number=line_number,
                    date=observation_date,
                    oas_percent=oas_percent,
                    source_url=str(row["source_url"]).strip(),
                    captured_at=str(row["captured_at"]).strip(),
                    raw_tooltip=str(row["raw_tooltip"]).strip(),
                )
            )
    return rows


def dedupe_by_date(
    rows: list[ParsedRow],
) -> tuple[list[ParsedRow], dict[str, list[dict[str, Any]]], dict[str, list[dict[str, Any]]]]:
    grouped: dict[date, list[ParsedRow]] = defaultdict(list)
    for row in rows:
        grouped[row.date].append(row)

    unique_rows: list[ParsedRow] = []
    duplicate_dates: dict[str, list[dict[str, Any]]] = {}
    conflicts: dict[str, list[dict[str, Any]]] = {}
    for observation_date, items in grouped.items():
        sorted_items = sorted(items, key=lambda item: (item.captured_at, item.line_number))
        selected = sorted_items[-1]
        unique_rows.append(selected)
        if len(items) > 1:
            payload = [
                {
                    "line_number": item.line_number,
                    "oas_percent": item.oas_percent,
                    "captured_at": item.captured_at,
                }
                for item in sorted_items
            ]
            duplicate_dates[observation_date.isoformat()] = payload
            if len({item.oas_percent for item in items}) > 1:
                conflicts[observation_date.isoformat()] = payload
    return sorted(unique_rows, key=lambda item: item.date), duplicate_dates, conflicts


def select_monthly_last_observations(rows: list[ParsedRow]) -> list[ParsedRow]:
    selected: dict[tuple[int, int], ParsedRow] = {}
    for row in rows:
        month_key = (row.date.year, row.date.month)
        current = selected.get(month_key)
        if current is None or (row.date, row.captured_at) > (current.date, current.captured_at):
            selected[month_key] = row
    return [selected[key] for key in sorted(selected)]


def build_quality_report(
    *,
    input_path: Path,
    raw_rows: list[ParsedRow],
    unique_rows: list[ParsedRow],
    monthly_rows: list[ParsedRow],
    duplicate_dates: dict[str, list[dict[str, Any]]],
    conflicts: dict[str, list[dict[str, Any]]],
) -> dict[str, Any]:
    values = [row.oas_percent for row in unique_rows]
    monthly_values = [row.oas_percent for row in monthly_rows]
    missing_months = list_missing_months(monthly_rows)
    gaps = list_gaps(unique_rows, minimum_days=45)
    monthly_gaps = list_month_gaps(monthly_rows)
    trailing_windows = count_trailing_windows_with_min_observations(monthly_rows, 120, 84)
    now = datetime.now(timezone.utc).isoformat()

    return {
        "generated_at": now,
        "input_path": str(input_path),
        "source_url": SOURCE_URL,
        "series": {
            "metric_key": "high_yield_spread",
            "phase_e_factor": "credit_spread_hy",
            "source_series": "BAMLH0A0HYM2",
            "unit": "percent",
            "source_page": "MacroMicro",
            "upstream_source": "ICE BofA US High Yield Index Option-Adjusted Spread",
            "source_method": "manual_audited_download",
            "user_review_note": "User reported overlap with FRED matched and requested manual audited/downloaded source marking.",
        },
        "raw_capture": {
            "raw_rows": len(raw_rows),
            "unique_dates": len(unique_rows),
            "duplicate_date_count": len(duplicate_dates),
            "conflict_date_count": len(conflicts),
            "first_date": unique_rows[0].date.isoformat() if unique_rows else None,
            "last_date": unique_rows[-1].date.isoformat() if unique_rows else None,
            "min_oas_percent": min(values) if values else None,
            "max_oas_percent": max(values) if values else None,
            "mean_oas_percent": round(mean(values), 6) if values else None,
            "median_oas_percent": round(median(values), 6) if values else None,
            "gaps_over_45_calendar_days": gaps,
            "duplicate_dates": duplicate_dates,
            "conflicts": conflicts,
        },
        "monthly_coverage": {
            "normalization_rule": "one row per calendar month, selected by latest observation_date in that month; captured_at is preserved from the selected scan row",
            "monthly_rows": len(monthly_rows),
            "first_month": month_label(monthly_rows[0]) if monthly_rows else None,
            "last_month": month_label(monthly_rows[-1]) if monthly_rows else None,
            "month_span_inclusive": month_span(monthly_rows),
            "missing_month_count": len(missing_months),
            "missing_months": missing_months,
            "month_gaps": monthly_gaps,
            "min_oas_percent": min(monthly_values) if monthly_values else None,
            "max_oas_percent": max(monthly_values) if monthly_values else None,
        },
        "phase_e_gate_review": {
            "required_main_window_months": 84,
            "required_auxiliary_window_months": 60,
            "available_monthly_observations": len(monthly_rows),
            "meets_84_month_minimum": len(monthly_rows) >= 84,
            "meets_60_month_auxiliary_minimum": len(monthly_rows) >= 60,
            "trailing_120m_windows_with_at_least_84_observed": trailing_windows["eligible_count"],
            "first_eligible_120m_window_end": trailing_windows["first_eligible_end"],
            "last_eligible_120m_window_end": trailing_windows["last_eligible_end"],
            "caveat": "This review checks history length only. Phase E still needs factor alignment, ETF return history, event templates, and explicit admission policy.",
        },
    }


def build_manifest(
    input_path: Path,
    daily_path: Path,
    monthly_path: Path,
    report_path: Path,
    report: dict[str, Any],
) -> dict[str, Any]:
    return {
        "generated_at": report["generated_at"],
        "input_path": str(input_path),
        "outputs": {
            "daily_csv": str(daily_path),
            "monthly_csv": str(monthly_path),
            "quality_report": str(report_path),
        },
        "series": report["series"],
        "privacy_boundary": {
            "raw_capture_policy": "local_only",
            "commit_raw_or_normalized_series": False,
            "write_market_history_sqlite": False,
        },
        "phase_e_use": {
            "candidate_unblocks_hy_oas_history_length": report["phase_e_gate_review"][
                "meets_84_month_minimum"
            ],
            "requires_user_approval_before_import": True,
        },
    }


def write_daily_csv(path: Path, rows: list[ParsedRow]) -> None:
    fieldnames = output_fieldnames(include_month=False)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(output_row(row))


def write_monthly_csv(path: Path, rows: list[ParsedRow]) -> None:
    fieldnames = output_fieldnames(include_month=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            payload = output_row(row)
            payload["month"] = month_label(row)
            writer.writerow(payload)


def output_fieldnames(*, include_month: bool) -> list[str]:
    fields = [
        "metric_key",
        "phase_e_factor",
        "observation_date",
        "oas_percent",
        "unit",
        "source_method",
        "source_page",
        "upstream_source",
        "source_series",
        "source_url",
        "captured_at",
        "raw_tooltip",
    ]
    if include_month:
        fields.insert(2, "month")
    return fields


def output_row(row: ParsedRow) -> dict[str, Any]:
    return {
        "metric_key": "high_yield_spread",
        "phase_e_factor": "credit_spread_hy",
        "observation_date": row.date.isoformat(),
        "oas_percent": f"{row.oas_percent:.6g}",
        "unit": "percent",
        "source_method": "manual_audited_download",
        "source_page": "MacroMicro",
        "upstream_source": "ICE BofA US High Yield Index Option-Adjusted Spread",
        "source_series": "BAMLH0A0HYM2",
        "source_url": row.source_url,
        "captured_at": row.captured_at,
        "raw_tooltip": row.raw_tooltip,
    }


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def list_missing_months(rows: list[ParsedRow]) -> list[str]:
    if not rows:
        return []
    observed = {(row.date.year, row.date.month) for row in rows}
    missing: list[str] = []
    year, month = rows[0].date.year, rows[0].date.month
    end = (rows[-1].date.year, rows[-1].date.month)
    while (year, month) <= end:
        if (year, month) not in observed:
            missing.append(f"{year:04d}-{month:02d}")
        year, month = next_month(year, month)
    return missing


def list_gaps(rows: list[ParsedRow], *, minimum_days: int) -> list[dict[str, Any]]:
    gaps: list[dict[str, Any]] = []
    for previous, current in zip(rows, rows[1:]):
        days = (current.date - previous.date).days
        if days > minimum_days:
            gaps.append(
                {
                    "from": previous.date.isoformat(),
                    "to": current.date.isoformat(),
                    "calendar_days": days,
                }
            )
    return gaps


def list_month_gaps(rows: list[ParsedRow]) -> list[dict[str, Any]]:
    gaps: list[dict[str, Any]] = []
    for previous, current in zip(rows, rows[1:]):
        months = (
            (current.date.year - previous.date.year) * 12
            + current.date.month
            - previous.date.month
        )
        if months > 1:
            gaps.append(
                {
                    "from_month": month_label(previous),
                    "to_month": month_label(current),
                    "missing_months_between": months - 1,
                }
            )
    return gaps


def count_trailing_windows_with_min_observations(
    rows: list[ParsedRow],
    window_months: int,
    minimum_observations: int,
) -> dict[str, Any]:
    if not rows:
        return {"eligible_count": 0, "first_eligible_end": None, "last_eligible_end": None}
    observed = {(row.date.year, row.date.month) for row in rows}
    months: list[tuple[int, int, bool]] = []
    year, month = rows[0].date.year, rows[0].date.month
    end = (rows[-1].date.year, rows[-1].date.month)
    while (year, month) <= end:
        months.append((year, month, (year, month) in observed))
        year, month = next_month(year, month)

    eligible: list[tuple[int, int]] = []
    for index, item in enumerate(months):
        window = months[max(0, index - window_months + 1) : index + 1]
        observed_count = sum(1 for _, _, has_observation in window if has_observation)
        if len(window) >= minimum_observations and observed_count >= minimum_observations:
            eligible.append((item[0], item[1]))
    return {
        "eligible_count": len(eligible),
        "first_eligible_end": format_month(eligible[0]) if eligible else None,
        "last_eligible_end": format_month(eligible[-1]) if eligible else None,
    }


def month_span(rows: list[ParsedRow]) -> int:
    if not rows:
        return 0
    return (
        (rows[-1].date.year - rows[0].date.year) * 12
        + rows[-1].date.month
        - rows[0].date.month
        + 1
    )


def month_label(row: ParsedRow) -> str:
    return f"{row.date.year:04d}-{row.date.month:02d}"


def format_month(month: tuple[int, int]) -> str:
    return f"{month[0]:04d}-{month[1]:02d}"


def next_month(year: int, month: int) -> tuple[int, int]:
    month += 1
    if month == 13:
        return year + 1, 1
    return year, month


if __name__ == "__main__":
    main()
