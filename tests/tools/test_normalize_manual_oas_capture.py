from __future__ import annotations

import csv
import importlib.util
import sys
from datetime import date
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = ROOT / "tools" / "data" / "normalize_manual_oas_capture.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("normalize_manual_oas_capture", MODULE_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules["normalize_manual_oas_capture"] = module
    spec.loader.exec_module(module)
    return module


normalizer = _load_module()


def _write_capture(path: Path, rows: list[dict[str, str]]) -> None:
    fieldnames = ["date", "oas_percent", "source_url", "captured_at", "raw_tooltip"]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _row(day: str, value: str, captured_at: str = "2026-06-26T13:00:00Z") -> dict[str, str]:
    return {
        "date": day,
        "oas_percent": value,
        "source_url": normalizer.SOURCE_URL,
        "captured_at": captured_at,
        "raw_tooltip": f"Monday, 01 Jan 2024● 美国-ICE BofA 高收益指数OAS利差: {value}",
    }


def test_manual_oas_capture_keeps_latest_duplicate_and_flags_conflict(tmp_path: Path):
    source = tmp_path / "oas_capture_raw.csv"
    _write_capture(
        source,
        [
            _row("2024-01-02", "3.1", "2026-06-26T13:00:00Z"),
            _row("2024-01-02", "3.2", "2026-06-26T13:10:00Z"),
            _row("2024-02-01", "3.3", "2026-06-26T13:20:00Z"),
        ],
    )

    raw_rows = normalizer.read_rows(source)
    unique_rows, duplicate_dates, conflicts = normalizer.dedupe_by_date(raw_rows)

    assert len(raw_rows) == 3
    assert len(unique_rows) == 2
    assert unique_rows[0].date == date(2024, 1, 2)
    assert unique_rows[0].oas_percent == 3.2
    assert set(duplicate_dates) == {"2024-01-02"}
    assert set(conflicts) == {"2024-01-02"}


def test_monthly_normalization_selects_latest_observation_date_not_latest_scan_time(
    tmp_path: Path,
):
    source = tmp_path / "oas_capture_raw.csv"
    _write_capture(
        source,
        [
            _row("2024-01-02", "3.1", "2026-06-26T13:20:00Z"),
            _row("2024-01-31", "3.4", "2026-06-26T13:00:00Z"),
            _row("2024-02-15", "3.5", "2026-06-26T13:10:00Z"),
        ],
    )

    raw_rows = normalizer.read_rows(source)
    unique_rows, _, _ = normalizer.dedupe_by_date(raw_rows)
    monthly_rows = normalizer.select_monthly_last_observations(unique_rows)

    assert [row.date.isoformat() for row in monthly_rows] == ["2024-01-31", "2024-02-15"]
    assert monthly_rows[0].captured_at == "2026-06-26T13:00:00Z"


def test_quality_report_marks_phase_e_gate_pass_when_84_months_available(tmp_path: Path):
    source = tmp_path / "oas_capture_raw.csv"
    rows = []
    year = 2017
    month = 1
    for index in range(84):
        rows.append(_row(f"{year:04d}-{month:02d}-28", str(3 + index / 100)))
        month += 1
        if month == 13:
            year += 1
            month = 1
    _write_capture(source, rows)

    raw_rows = normalizer.read_rows(source)
    unique_rows, duplicate_dates, conflicts = normalizer.dedupe_by_date(raw_rows)
    monthly_rows = normalizer.select_monthly_last_observations(unique_rows)
    report = normalizer.build_quality_report(
        input_path=source,
        raw_rows=raw_rows,
        unique_rows=unique_rows,
        monthly_rows=monthly_rows,
        duplicate_dates=duplicate_dates,
        conflicts=conflicts,
    )

    assert report["monthly_coverage"]["monthly_rows"] == 84
    assert report["monthly_coverage"]["missing_month_count"] == 0
    assert report["phase_e_gate_review"]["meets_84_month_minimum"] is True
    assert report["series"]["source_method"] == "manual_audited_download"


def test_output_row_preserves_capture_metadata():
    row = normalizer.ParsedRow(
        line_number=2,
        date=date(2026, 6, 23),
        oas_percent=2.71,
        source_url=normalizer.SOURCE_URL,
        captured_at="2026-06-26T13:32:39.599Z",
        raw_tooltip="Tuesday, 23 Jun 2026● 美国-ICE BofA 高收益指数OAS利差: 2.71",
    )

    payload = normalizer.output_row(row)

    assert payload["metric_key"] == "high_yield_spread"
    assert payload["phase_e_factor"] == "credit_spread_hy"
    assert payload["source_method"] == "manual_audited_download"
    assert payload["captured_at"] == "2026-06-26T13:32:39.599Z"
    assert payload["oas_percent"] == "2.71"
