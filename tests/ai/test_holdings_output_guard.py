from __future__ import annotations

from app_backend.services.holdings_output_guard import find_holdings_output_disclosures
from tests.ai.test_agent_runtime_mocked import brief_payload
from app_backend.services.macro_brief_parser import parse_macro_brief


def test_holdings_output_guard_blocks_account_and_position_values():
    payload = brief_payload()
    payload["core_conclusion"] = "Macro Sleeve holds SPY with market value 182247."
    brief = parse_macro_brief(payload)

    findings = find_holdings_output_disclosures(
        brief=brief,
        holdings_snapshot={
            "account_name": "Macro Sleeve",
            "positions": [
                {
                    "ticker": "SPY",
                    "quantity": 250,
                    "average_cost": 420.5,
                    "market_value": 182247,
                }
            ],
        },
    )

    assert "account_name" in findings
    assert "positions[0].market_value" in findings


def test_holdings_output_guard_allows_ticker_without_sensitive_values():
    payload = brief_payload()
    payload["core_conclusion"] = "Portfolio beta is most sensitive to broad equity exposure such as SPY."
    brief = parse_macro_brief(payload)

    assert (
        find_holdings_output_disclosures(
            brief=brief,
            holdings_snapshot={
                "account_name": "Macro Sleeve",
                "positions": [
                    {
                        "ticker": "SPY",
                        "quantity": 250,
                        "average_cost": 420.5,
                        "market_value": 182247,
                    }
                ],
            },
        )
        == []
    )
