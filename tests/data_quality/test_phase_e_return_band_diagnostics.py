from __future__ import annotations

import csv
from pathlib import Path

from data_quality import phase_e_return_band_diagnostics as diagnostics


def _monthly_rows(count: int, *, start_year: int = 2017, start_month: int = 1):
    rows = []
    year = start_year
    month = start_month
    for index in range(count):
        rows.append(
            diagnostics.MonthlyObservation(
                month=f"{year:04d}-{month:02d}",
                observation_date=f"{year:04d}-{month:02d}-28",
                value=3.0 + index / 100,
                source_method=diagnostics.MANUAL_AUDITED_DOWNLOAD,
                source_series="BAMLH0A0HYM2",
                source_url=None,
                captured_at="2026-06-26T13:00:00Z",
            )
        )
        month += 1
        if month == 13:
            year += 1
            month = 1
    return rows


def test_coverage_for_series_passes_phase_e_month_gates():
    coverage = diagnostics.coverage_for_series("high_yield_spread", _monthly_rows(84))

    assert coverage.status == "ok"
    assert coverage.observation_count == 84
    assert coverage.meets_84_month_minimum is True
    assert coverage.meets_60_month_auxiliary_minimum is True
    assert coverage.missing_months == []


def test_coverage_for_series_flags_missing_months_and_short_history():
    rows = [
        diagnostics.MonthlyObservation(
            month="2024-01",
            observation_date="2024-01-31",
            value=3.0,
            source_method="manual",
            source_series="BAMLH0A0HYM2",
        ),
        diagnostics.MonthlyObservation(
            month="2024-03",
            observation_date="2024-03-31",
            value=3.4,
            source_method="manual",
            source_series="BAMLH0A0HYM2",
        ),
    ]

    coverage = diagnostics.coverage_for_series("high_yield_spread", rows)

    assert coverage.status == "insufficient_history"
    assert coverage.missing_months == ["2024-02"]
    assert coverage.longest_consecutive_run_months == 1


def test_phase_e_diagnostics_remains_blocked_until_real_yield_policy_is_decided():
    result = diagnostics.build_phase_e_factor_diagnostics(
        {"high_yield_spread": _monthly_rows(120)}
    )

    assert result["status"] == "insufficient_inputs"
    assert result["mode"] == "diagnostic_only"
    assert result["no_return_band_values"] is True
    assert "real_yield_10y" in result["blocking_factors"]
    assert "growth_momentum_zscore" in result["blocking_factors"]
    assert "credit_spread_hy" not in result["blocking_factors"]


def test_phase_e_diagnostics_passes_when_all_factor_series_are_supplied():
    series = {
        "real_yield_10y": _monthly_rows(120),
        "high_yield_spread": _monthly_rows(120),
        "growth_momentum_zscore": _monthly_rows(120),
        "vix": _monthly_rows(120),
        "ust_slope": _monthly_rows(120),
        "brent": _monthly_rows(120),
    }

    result = diagnostics.build_phase_e_factor_diagnostics(
        series,
        real_yield_policy="dfii10",
    )

    assert result["status"] == "ok"
    assert result["blocking_factors"] == []
    assert result["no_return_band_values"] is True


def test_load_manual_oas_monthly_csv_requires_manual_audited_source(tmp_path: Path):
    path = tmp_path / "oas_monthly.csv"
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "month",
                "observation_date",
                "oas_percent",
                "source_method",
                "source_series",
                "source_url",
                "captured_at",
            ],
        )
        writer.writeheader()
        writer.writerow(
            {
                "month": "2026-06",
                "observation_date": "2026-06-23",
                "oas_percent": "2.71",
                "source_method": diagnostics.MANUAL_AUDITED_DOWNLOAD,
                "source_series": "BAMLH0A0HYM2",
                "source_url": "https://example.test",
                "captured_at": "2026-06-26T13:32:39.599Z",
            }
        )

    rows = diagnostics.load_manual_oas_monthly_csv(path)

    assert len(rows) == 1
    assert rows[0].month == "2026-06"
    assert rows[0].value == 2.71
    assert rows[0].captured_at == "2026-06-26T13:32:39.599Z"


def test_load_manual_oas_monthly_csv_rejects_non_manual_audited_source(tmp_path: Path):
    path = tmp_path / "oas_monthly.csv"
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "month",
                "observation_date",
                "oas_percent",
                "source_method",
                "source_series",
                "source_url",
                "captured_at",
            ],
        )
        writer.writeheader()
        writer.writerow(
            {
                "month": "2026-06",
                "observation_date": "2026-06-23",
                "oas_percent": "2.71",
                "source_method": "official",
                "source_series": "BAMLH0A0HYM2",
                "source_url": "https://example.test",
                "captured_at": "2026-06-26T13:32:39.599Z",
            }
        )

    try:
        diagnostics.load_manual_oas_monthly_csv(path)
    except ValueError as exc:
        assert "unexpected source_method" in str(exc)
    else:
        raise AssertionError("expected source_method validation failure")
