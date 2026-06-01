from dev_check_validator_boundaries import BLOCKED_CASES, REGRESSION_CASES, SYNTHETIC_FACTS
from llm.comparison_validator import validate_comparison_answer


def _validate(text: str) -> dict:
    return validate_comparison_answer(text, SYNTHETIC_FACTS)


def test_fedwatch_boundary_statement_is_allowed_but_numeric_claim_is_blocked():
    boundary = _validate(REGRESSION_CASES["FedWatch missing boundary"])
    blocked = _validate(BLOCKED_CASES["FedWatch probability"])

    assert boundary["hard_flags"]["external_source_mentioned"] == []
    assert boundary["hard_flags"]["unsupported_market_data_claim"] == []
    assert blocked["hard_flags"]["external_source_mentioned"] == ["FedWatch"]
    assert blocked["hard_flags"]["unsupported_market_data_claim"]


def test_trade_like_instruction_and_cash_reserve_misuse_are_hard_flags():
    trade = _validate(BLOCKED_CASES["trade-like Nasdaq instruction"])
    cash = _validate(BLOCKED_CASES["cash reserve redeploy"])

    assert trade["hard_flags"]["trade_like_instruction"] is True
    assert cash["hard_flags"]["cash_reserve_misuse"] is True


def test_dgs_mixed_breakout_status_is_allowed_but_false_confirmation_is_blocked():
    mixed = _validate(REGRESSION_CASES["DGS30 true DGS10 false consistency"])
    false_confirmed = _validate(BLOCKED_CASES["false breakout but confirmed"])

    assert mixed["hard_flags"]["dgs_breakout_confirmation_conflict"] == []
    assert false_confirmed["hard_flags"]["dgs_breakout_confirmation_conflict"]


def test_exact_metric_keys_are_required_for_body_metric_claims():
    missing = _validate(REGRESSION_CASES["DGS10 rolling averages missing exact evidence keys"])
    exact = _validate(REGRESSION_CASES["DGS10 rolling averages with exact evidence keys"])

    assert missing["hard_flags"]["unsupported_market_data_claim"] or missing["soft_flags"][
        "body_metric_not_in_evidence_table"
    ]
    assert exact["hard_flags"]["unsupported_market_data_claim"] == []
    assert exact["soft_flags"]["body_metric_not_in_evidence_table"] == []


def test_portfolio_attribution_confusion_boundary():
    unsupported = _validate(REGRESSION_CASES["allocation attribution unsupported"])
    boundary = _validate(REGRESSION_CASES["allocation attribution boundary"])

    assert unsupported["soft_flags"]["current_vs_target_allocation_confusion"] is True
    assert boundary["soft_flags"]["current_vs_target_allocation_confusion"] is False


def test_real_yield_primary_driver_wording_is_soft_flagged_but_conditional_mechanism_is_allowed():
    driver = _validate(REGRESSION_CASES["real yield primary driver wording"])
    conditional = _validate(
        "实际利率上升可能通过贴现率机制增加黄金压力，但需要结合美元、通胀预期和风险偏好，不能写成单一主因。"
    )

    assert driver["soft_flags"]["unsupported_real_yield_primary_driver_claim"] is True
    assert conditional["soft_flags"]["unsupported_real_yield_primary_driver_claim"] is False
