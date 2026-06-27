from __future__ import annotations

import pytest

from data_quality.phase_e_factor_panel import build_monthly_factor_panel
from data_quality.phase_e_return_band_diagnostics import MonthlyObservation


def test_factor_panel_aligns_only_common_months_without_imputation():
    panel = build_monthly_factor_panel(
        {
            "real_yield_10y": [_row("2024-01", 1.0), _row("2024-02", 1.1)],
            "credit_spread_hy": [_row("2024-02", 3.0), _row("2024-03", 3.1)],
        },
        factor_keys=("real_yield_10y", "credit_spread_hy"),
        min_required_months=1,
    )

    assert panel.status == "ok"
    assert panel.row_count == 1
    assert panel.first_month == "2024-02"
    assert panel.rows[0].values == {
        "real_yield_10y": 1.1,
        "credit_spread_hy": 3.0,
    }
    assert panel.missing_months_by_factor == {
        "real_yield_10y": ["2024-03"],
        "credit_spread_hy": ["2024-01"],
    }


def test_factor_panel_reports_missing_required_factor():
    panel = build_monthly_factor_panel(
        {"credit_spread_hy": [_row("2024-01", 3.0)]},
        factor_keys=("real_yield_10y", "credit_spread_hy"),
    )

    assert panel.status == "missing_factors"
    assert panel.missing_factors == ["real_yield_10y"]
    assert panel.row_count == 0


def test_factor_panel_rejects_duplicate_months():
    with pytest.raises(ValueError, match="duplicate month"):
        build_monthly_factor_panel(
            {
                "credit_spread_hy": [
                    _row("2024-01", 3.0),
                    _row("2024-01", 3.1),
                ]
            },
            factor_keys=("credit_spread_hy",),
        )


def test_factor_panel_requires_minimum_common_history():
    short_panel = build_monthly_factor_panel(
        {"credit_spread_hy": _rows(83)},
        factor_keys=("credit_spread_hy",),
    )
    full_panel = build_monthly_factor_panel(
        {"credit_spread_hy": _rows(84)},
        factor_keys=("credit_spread_hy",),
    )

    assert short_panel.status == "insufficient_common_history"
    assert full_panel.status == "ok"
    assert full_panel.row_count == 84


def test_factor_panel_as_dict_keeps_boundary_text():
    panel = build_monthly_factor_panel(
        {"credit_spread_hy": [_row("2024-01", 3.0)]},
        factor_keys=("credit_spread_hy",),
        min_required_months=1,
    )

    payload = panel.as_dict()

    assert payload["status"] == "ok"
    assert payload["rows"] == [
        {"month": "2024-01", "values": {"credit_spread_hy": 3.0}}
    ]
    assert "does not impute" in payload["semantic_boundary"]


def _rows(count: int):
    year = 2017
    month = 1
    rows = []
    for index in range(count):
        rows.append(_row(f"{year:04d}-{month:02d}", 3.0 + index / 100))
        month += 1
        if month == 13:
            year += 1
            month = 1
    return rows


def _row(month: str, value: float) -> MonthlyObservation:
    return MonthlyObservation(
        month=month,
        observation_date=f"{month}-28",
        value=value,
        source_method="test_fixture",
        source_series="TEST",
    )
