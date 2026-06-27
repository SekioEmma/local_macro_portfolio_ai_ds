from __future__ import annotations

import pytest

from data_quality.phase_e_etf_returns import (
    MonthlyPriceObservation,
    compute_trailing_3m_returns,
)


def test_compute_trailing_3m_returns_uses_exact_three_month_lag():
    series = compute_trailing_3m_returns(
        [
            _price("2024-01", 100.0),
            _price("2024-02", 120.0),
            _price("2024-03", 90.0),
            _price("2024-04", 110.0),
            _price("2024-05", 126.0),
        ],
        source_key="SPY",
        min_required_months=1,
    )

    assert series.status == "ok"
    assert series.row_count == 2
    assert series.first_month == "2024-04"
    assert series.rows[0].return_3m == pytest.approx(0.10)
    assert series.rows[1].return_3m == pytest.approx(0.05)
    assert series.missing_lag_months == ["2024-01", "2024-02", "2024-03"]


def test_compute_trailing_3m_returns_skips_missing_lag_month_without_imputation():
    series = compute_trailing_3m_returns(
        [
            _price("2024-01", 100.0),
            _price("2024-03", 90.0),
            _price("2024-04", 110.0),
            _price("2024-06", 99.0),
        ],
        source_key="QQQ",
        min_required_months=1,
    )

    assert series.row_count == 2
    assert [row.month for row in series.rows] == ["2024-04", "2024-06"]
    assert series.rows[1].return_3m == pytest.approx(0.10)
    assert "2024-03" in series.missing_lag_months


def test_compute_trailing_3m_returns_rejects_duplicate_months():
    with pytest.raises(ValueError, match="duplicate month"):
        compute_trailing_3m_returns(
            [_price("2024-01", 100.0), _price("2024-01", 101.0)],
            source_key="SPY",
        )


def test_compute_trailing_3m_returns_rejects_non_positive_levels():
    with pytest.raises(ValueError, match="non-positive"):
        compute_trailing_3m_returns([_price("2024-01", 0.0)], source_key="SPY")


def test_compute_trailing_3m_returns_reports_history_gate():
    short_series = compute_trailing_3m_returns(
        _monthly_prices(86),
        source_key="SPY",
    )
    full_series = compute_trailing_3m_returns(
        _monthly_prices(87),
        source_key="SPY",
    )

    assert short_series.row_count == 83
    assert short_series.status == "insufficient_history"
    assert full_series.row_count == 84
    assert full_series.status == "ok"


def test_monthly_return_series_as_dict_preserves_boundary():
    series = compute_trailing_3m_returns(
        [_price("2024-01", 100.0), _price("2024-04", 110.0)],
        source_key="GLD",
        min_required_months=1,
    )

    payload = series.as_dict()

    assert payload["status"] == "ok"
    assert payload["rows"][0]["month"] == "2024-04"
    assert "does not forecast" in payload["semantic_boundary"]


def _monthly_prices(count: int):
    year = 2017
    month = 1
    rows = []
    for index in range(count):
        rows.append(_price(f"{year:04d}-{month:02d}", 100.0 + index))
        month += 1
        if month == 13:
            year += 1
            month = 1
    return rows


def _price(month: str, value: float) -> MonthlyPriceObservation:
    return MonthlyPriceObservation(
        month=month,
        observation_date=f"{month}-28",
        value=value,
        source_key="TEST",
    )
