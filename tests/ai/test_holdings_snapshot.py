from __future__ import annotations

import pytest
from pydantic import ValidationError

from app_backend.schemas.holdings_snapshot import holdings_snapshot_payload


def test_holdings_snapshot_accepts_only_typed_average_cost_contract():
    payload = holdings_snapshot_payload(
        {
            "account_name": "Macro Sleeve",
            "positions": [
                {
                    "ticker": "SPY",
                    "quantity": 250,
                    "average_cost": 420.5,
                    "market_value": 182247,
                    "unrealized_pnl": 1234.5,
                }
            ],
            "asset_class_breakdown": {"equity": 0.64},
            "portfolio_risk_summary": "Equity-heavy macro beta.",
        }
    )

    assert payload["account_name"] == "Macro Sleeve"
    assert payload["positions"][0]["average_cost"] == 420.5
    assert "cost_basis" not in payload["positions"][0]


def test_holdings_snapshot_rejects_legacy_cost_basis_field():
    with pytest.raises(ValidationError):
        holdings_snapshot_payload(
            {
                "positions": [
                    {
                        "ticker": "SPY",
                        "quantity": 250,
                        "cost_basis": 170000,
                    }
                ]
            }
        )


def test_holdings_snapshot_requires_at_least_one_position():
    with pytest.raises(ValidationError):
        holdings_snapshot_payload({"positions": []})
