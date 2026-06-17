import json

from data_quality import portfolio_exposure_overlay as overlay


PRIVATE_OR_FORBIDDEN_TOKENS = (
    "RAW_FUND",
    "HOLDINGS_AMOUNT_MUST_NOT_LEAK",
    "raw_provider",
    "raw_prompt",
    "api_key",
    ".env",
    "sqlite",
    "data/private",
    "current_holdings.csv",
    "credentials",
    "C:\\Users\\",
    "G:\\local_macro_portfolio_ai",
)

FORBIDDEN_PUBLIC_LANGUAGE = (
    "crash probability",
    "recession probability",
    "market direction probability",
    "expected return",
    "predicted return",
    "future return",
    "trade signal",
    "buy",
    "sell",
    "hedge",
    "rebalance",
    "target allocation",
    "target weight",
    "ideal allocation",
    "add position",
    "reduce position",
    "clear position",
    "de-risk",
    "rotate into",
    "overweight",
    "underweight",
    "strategy return",
    "trading performance",
    "sharpe",
    "guaranteed",
    "will rise",
    "will fall",
)


def test_stage8_overlay_uses_sanitized_context_and_does_not_leak_private_values():
    rows = overlay.build_portfolio_exposure_overlay_rows(
        [
            _base_row("max_deviation_asset", "equity", module="portfolio_deviation"),
            _base_row("max_deviation_pp", 2.5, module="portfolio_deviation"),
            _base_row("financial_stress_status", "watch", module="financial_stress_composite"),
            {
                "module": "portfolio_deviation",
                "metric_key": "holdings",
                "value": [{"ticker": "RAW_FUND", "amount": "HOLDINGS_AMOUNT_MUST_NOT_LEAK"}],
                "raw_provider": "must_not_leak",
                "raw_prompt": "must_not_leak",
            },
        ]
    )
    body = json.dumps(rows, sort_keys=True).lower()
    status = next(row for row in rows if row["metric_key"] == "portfolio_exposure_overlay_status")

    for token in PRIVATE_OR_FORBIDDEN_TOKENS:
        assert token.lower() not in body
    for token in FORBIDDEN_PUBLIC_LANGUAGE:
        assert token not in body
    gates = status["component_contributions"]["hard_gates"]
    assert gates["reads_holdings_line_items"] is False
    assert gates["returns_holdings_line_items"] is False
    assert gates["returns_position_weights"] is False
    assert gates["returns_account_values"] is False
    assert gates["uses_sanitized_portfolio_context_only"] is True


def test_missing_sanitized_context_is_private_inputs_excluded_not_exposure_signal():
    rows = overlay.build_portfolio_exposure_overlay_rows([])
    by_key = {row["metric_key"]: row for row in rows}

    assert by_key["portfolio_exposure_overlay_status"]["value"] == "private_inputs_excluded"
    assert by_key["portfolio_exposure_overlay_status"]["status"] == "insufficient_evidence"
    assert "sanitized_portfolio_context" in by_key["portfolio_exposure_missing_inputs"]["value"]
    channels = by_key["portfolio_exposure_overlay_status"]["component_contributions"]["channels"]
    assert all(item["status"] == "private_input_excluded" for item in channels.values())


def _base_row(metric_key, value, *, module):
    return {
        "module": module,
        "metric_key": metric_key,
        "value": value,
        "value_text": str(value),
        "status": "ok",
        "source_badge": "local" if module == "portfolio_deviation" else "derived",
        "freshness_status": "fresh",
        "ai_context_allowed": True,
        "observation_date": "2026-06-01",
    }
