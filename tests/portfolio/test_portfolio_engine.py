import pytest

from portfolio.portfolio_engine import (
    calculate_deviation,
    calculate_total_assets,
    calculate_weights,
    check_dca_budget,
    classify_deviation,
    load_holdings_csv,
)


def test_weights_exclude_cash_from_target_asset_denominator():
    aggregated = {
        "sp500": {"current_value": 500, "cost_basis": 500, "profit_loss": 0},
        "nasdaq100": {"current_value": 200, "cost_basis": 200, "profit_loss": 0},
        "short_bond": {"current_value": 200, "cost_basis": 200, "profit_loss": 0},
        "gold": {"current_value": 100, "cost_basis": 100, "profit_loss": 0},
        "cash": {"current_value": 100, "cost_basis": 100, "profit_loss": 0},
    }

    totals = calculate_total_assets(aggregated)
    weights = calculate_weights(aggregated)
    weights_with_cash = calculate_weights(aggregated, include_cash=True)

    assert totals["total_assets"] == 1100
    assert totals["invested_assets"] == 1000
    assert totals["cash"] == 100
    assert weights == {
        "sp500": 0.5,
        "nasdaq100": 0.2,
        "short_bond": 0.2,
        "gold": 0.1,
    }
    assert weights_with_cash["cash"] == 0.0909


def test_deviation_direction_and_classification_thresholds():
    current_weights = {
        "sp500": 0.5,
        "nasdaq100": 0.2,
        "short_bond": 0.2,
        "gold": 0.1,
    }
    target_allocation = {
        "sp500": 0.55,
        "nasdaq100": 0.15,
        "short_bond": 0.2,
        "gold": 0.1,
    }

    deviation = calculate_deviation(current_weights, target_allocation)

    assert deviation["sp500"] == -0.05
    assert deviation["nasdaq100"] == 0.05
    assert deviation["short_bond"] == 0.0
    assert classify_deviation(deviation, threshold=0.02) == {
        "sp500": "underweight",
        "nasdaq100": "overweight",
        "short_bond": "within_range",
        "gold": "within_range",
    }


def test_dca_budget_statuses_are_deterministic():
    assert check_dca_budget(
        {"sp500": 20, "nasdaq100": 10},
        trading_days=21,
        monthly_budget_min=300,
        monthly_budget_max=500,
    )["status"] == "above_budget"

    assert check_dca_budget(
        {"sp500": 10, "nasdaq100": 10},
        trading_days=20,
        monthly_budget_min=300,
        monthly_budget_max=500,
    )["status"] == "within_budget"


def test_holdings_csv_rejects_missing_columns(tmp_path):
    holdings_path = tmp_path / "holdings.csv"
    holdings_path.write_text("asset_name,current_value\nSynthetic SP500,100\n", encoding="utf-8")

    with pytest.raises(ValueError, match="missing required field"):
        load_holdings_csv(str(holdings_path))


def test_holdings_csv_rejects_invalid_money(tmp_path):
    holdings_path = tmp_path / "holdings.csv"
    holdings_path.write_text(
        "\n".join(
            [
                "asset_name,fund_code,asset_class,current_value,cost_basis,profit_loss,currency,updated_at,notes",
                "Synthetic SP500,SYN001,sp500,not-a-number,100,0,CNY,2026-05-31,test",
            ]
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="invalid current_value"):
        load_holdings_csv(str(holdings_path))
