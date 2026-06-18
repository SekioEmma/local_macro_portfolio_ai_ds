from __future__ import annotations

from app_backend.services.ai_semantic_validator import (
    SEMANTIC_RULES,
    explain_findings,
    validate_financial_semantics,
)


def test_clean_unrelated_text_passes():
    result = validate_financial_semantics(
        "Local preview only. Manifest-backed evidence summary; reference context only."
    )
    assert result.passed is True
    assert result.findings == []


def test_systemic_risk_without_credit_or_funding_fails():
    text = "Current evidence indicates systemic risk based on VIX spike alone."
    result = validate_financial_semantics(text)

    assert result.passed is False
    rules = {f.rule for f in result.findings}
    assert "systemic_risk_requires_credit_funding_transmission" in rules


def test_systemic_risk_with_credit_funding_transmission_passes():
    text = (
        "Systemic risk would require credit (HY OAS widening), funding/liquidity "
        "stress (SOFR/IORB spreads), and transmission channels to equity. "
        "Current evidence does not confirm all three."
    )
    result = validate_financial_semantics(text)

    rules = {f.rule for f in result.findings}
    assert "systemic_risk_requires_credit_funding_transmission" not in rules


def test_credit_warning_anchored_only_on_vix_proxy_fails():
    text = "Credit warning: VIX above 25 and HYG/LQD price gap widening."
    result = validate_financial_semantics(text)

    rules = {f.rule for f in result.findings}
    assert "credit_warning_cannot_rely_only_on_vix_or_etf_proxy" in rules


def test_credit_warning_with_hy_oas_reference_passes():
    text = (
        "Credit warning is conditional on HY OAS widening above its 90th "
        "percentile band, not on VIX or ETF proxies alone."
    )
    result = validate_financial_semantics(text)

    rules = {f.rule for f in result.findings}
    assert "credit_warning_cannot_rely_only_on_vix_or_etf_proxy" not in rules


def test_valuation_pressure_without_missing_constraint_fails():
    text = "Valuation pressure is elevated based on equity index levels."
    result = validate_financial_semantics(text)

    rules = {f.rule for f in result.findings}
    assert "valuation_pressure_must_acknowledge_missing_or_proxy" in rules


def test_valuation_pressure_with_missing_constraint_passes():
    text = (
        "Valuation pressure cannot be confirmed: forward PE is research_needed and "
        "true breadth data is missing; only proxy values are available."
    )
    result = validate_financial_semantics(text)

    rules = {f.rule for f in result.findings}
    assert "valuation_pressure_must_acknowledge_missing_or_proxy" not in rules


def test_scenario_without_not_forecast_notice_fails():
    text = "The Scenario Stress Matrix shows credit_spread_widening as elevated."
    result = validate_financial_semantics(text)

    rules = {f.rule for f in result.findings}
    assert "scenario_requires_not_a_forecast_notice" in rules


def test_scenario_with_chinese_not_forecast_notice_passes():
    text = (
        "情景压力矩阵显示 credit_spread_widening 处于 elevated band；"
        "该结果不构成预测，不构成事件概率，不构成仓位指令。"
    )
    result = validate_financial_semantics(text)

    rules = {f.rule for f in result.findings}
    assert "scenario_requires_not_a_forecast_notice" not in rules


def test_historical_validation_without_backtest_notice_fails():
    text = "Historical validation shows the 2008 event window matches."
    result = validate_financial_semantics(text)

    rules = {f.rule for f in result.findings}
    assert "historical_validation_requires_not_a_backtest_notice" in rules


def test_historical_validation_with_event_window_replay_notice_passes():
    text = (
        "Historical validation is an event-window replay (reference-only) and "
        "is not a backtest or prediction accuracy metric."
    )
    result = validate_financial_semantics(text)

    rules = {f.rule for f in result.findings}
    assert "historical_validation_requires_not_a_backtest_notice" not in rules


def test_portfolio_without_sanitized_local_notice_fails():
    text = "The portfolio exposure suggests rates_pressure is the dominant channel."
    result = validate_financial_semantics(text)

    rules = {f.rule for f in result.findings}
    assert "portfolio_requires_local_sanitized_no_allocation" in rules


def test_portfolio_with_sanitized_compact_notice_passes():
    text = (
        "Portfolio exposure overlay uses sanitized compact_summary_only context "
        "and is not an action directive."
    )
    result = validate_financial_semantics(text)

    rules = {f.rule for f in result.findings}
    assert "portfolio_requires_local_sanitized_no_allocation" not in rules


def test_financial_stress_score_without_pressure_temperature_clarification_fails():
    text = "Financial stress score reached 0.62 last week."
    result = validate_financial_semantics(text)

    rules = {f.rule for f in result.findings}
    assert "financial_stress_score_must_clarify_pressure_temperature" in rules


def test_financial_stress_score_with_pressure_temperature_clarification_passes():
    text = (
        "Financial stress score is a pressure temperature reading, not a "
        "probability of crisis or any forecast."
    )
    result = validate_financial_semantics(text)

    rules = {f.rule for f in result.findings}
    assert "financial_stress_score_must_clarify_pressure_temperature" not in rules


def test_explain_findings_returns_chinese_lines():
    text = "Systemic risk is rising."
    result = validate_financial_semantics(text)
    lines = explain_findings(result, language="zh")

    assert lines
    assert any("系统性风险" in line for line in lines)


def test_explain_findings_returns_empty_for_passing_payload():
    text = (
        "Local preview only. Manifest evidence: HY OAS, IG OAS reference "
        "context only."
    )
    result = validate_financial_semantics(text)

    assert result.passed is True
    assert explain_findings(result) == []


def test_validator_accepts_dict_payload():
    payload = {
        "sections": [
            {"content": "Systemic risk is unconfirmed because credit and funding "
             "transmission channels do not show widening."}
        ]
    }
    result = validate_financial_semantics(payload)
    rules = {f.rule for f in result.findings}
    assert "systemic_risk_requires_credit_funding_transmission" not in rules


def test_rule_catalog_has_all_seven_rules():
    rule_names = {rule.name for rule in SEMANTIC_RULES}
    assert rule_names == {
        "systemic_risk_requires_credit_funding_transmission",
        "credit_warning_cannot_rely_only_on_vix_or_etf_proxy",
        "valuation_pressure_must_acknowledge_missing_or_proxy",
        "scenario_requires_not_a_forecast_notice",
        "historical_validation_requires_not_a_backtest_notice",
        "portfolio_requires_local_sanitized_no_allocation",
        "financial_stress_score_must_clarify_pressure_temperature",
    }
