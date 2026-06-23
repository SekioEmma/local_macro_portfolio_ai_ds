from pathlib import Path

from app_backend.services.dashboard_portfolio_compact import portfolio_deviation_compact
from app_backend.services.dashboard_report_loader import ReportState


def test_portfolio_deviation_compact_uses_non_cash_target_denominator():
    report = ReportState(
        name="portfolio_snapshot",
        path=Path("portfolio_snapshot.json"),
        exists=True,
        data={
            "generated_at": "2026-06-10T00:00:00+00:00",
            "holdings_updated_at": "2026-06-01",
            "weights_ex_cash": {
                "sp500": 0.54,
                "nasdaq100": 0.17,
                "short_bond": 0.19,
                "gold": 0.10,
            },
            "target_allocation": {
                "sp500": 0.50,
                "nasdaq100": 0.20,
                "short_bond": 0.20,
                "gold": 0.10,
            },
            "cash_reserve_value": 12345,
            "holdings": [{"ticker": "RAW_FUND", "amount": 999999}],
        },
    )

    compact = portfolio_deviation_compact(report)

    assert compact is not None
    assert compact.target_weights == {
        "sp500": 50.0,
        "nasdaq100": 20.0,
        "short_bond": 20.0,
        "gold": 10.0,
    }
    assert "cash" not in compact.target_weights
    assert compact.current_weights["sp500"] == 54.0
    assert compact.deviation_pp["sp500"] == 4.0
    assert compact.max_deviation_asset == "sp500"
    assert compact.max_deviation_pp == 4.0
    assert compact.equity_total_current_weight == 71.0
    assert compact.equity_total_target_weight == 70.0
    assert compact.equity_total_deviation_pp == 1.0
    assert compact.cash_reserve_status == "cash_excluded_from_target_allocation"
    assert compact.stale_status == "fresh"


def test_portfolio_deviation_compact_marks_stale_holdings():
    report = ReportState(
        name="portfolio_snapshot",
        path=Path("portfolio_snapshot.json"),
        exists=True,
        data={
            "generated_at": "2026-06-10T00:00:00+00:00",
            "holdings_updated_at": "2026-04-01",
            "weights_ex_cash": {
                "sp500": 0.50,
                "nasdaq100": 0.20,
                "short_bond": 0.20,
                "gold": 0.10,
            },
        },
    )

    compact = portfolio_deviation_compact(report)

    assert compact is not None
    assert compact.stale_status == "stale"
