from __future__ import annotations

from typing import Any

import pytest
from pydantic import ValidationError

from app_backend.schemas.ai_preview import AIResearchPreviewRequest
from app_backend.services.ai_research_renderer import render_research_preview
from app_backend.services.ai_research_validator import validate_research_domains
from app_backend.services.ai_semantic_validator import (
    validate_financial_semantics,
    validate_structured_research_semantics,
)
from data_quality.historical_percentile_metadata import (
    _credit_reference_role,
    _substitution_policy,
)
from data_quality.official_macro_pack import OFFICIAL_MACRO_METRICS


def test_vix_alone_cannot_trigger_systemic_risk():
    findings = validate_structured_research_semantics(
        [
            {
                "key": "current_conclusion",
                "claim_tags": ["systemic_risk_review"],
                "source_context": ["market_stress_derived.vix"],
            }
        ]
    )
    assert _has_code(
        findings,
        "systemic_risk_requires_credit_funding_transmission",
    )


def test_equity_drawdown_alone_cannot_trigger_systemic_risk():
    findings = validate_structured_research_semantics(
        [
            {
                "key": "current_conclusion",
                "claim_tags": [
                    "systemic_risk_review",
                    "systemic_risk_confirmed",
                ],
                "source_context": ["equity_trend.sp500_drawdown_3m"],
            }
        ]
    )
    assert _has_code(
        findings,
        "systemic_risk_requires_credit_funding_transmission",
    )
    assert _has_code(findings, "systemic_risk_prohibited_upgrade")


def test_proxy_breadth_cannot_confirm_true_breadth():
    findings = validate_structured_research_semantics(
        [
            {
                "key": "macro_explanation",
                "claim_tags": ["true_breadth_deterioration"],
                "source_context": [
                    "breadth_concentration_proxy.spy_vs_rsp_30d"
                ],
            }
        ]
    )
    assert _has_code(
        findings,
        "proxy_breadth_cannot_confirm_true_breadth",
    )


def test_portfolio_deviation_pressure_cannot_raise_macro_regime_label():
    findings = validate_structured_research_semantics(
        [
            {
                "key": "current_conclusion",
                "claim_tags": ["macro_regime_from_portfolio"],
                "source_context": [
                    "portfolio_deviation.risk_asset_deviation"
                ],
            }
        ]
    )
    assert _has_code(
        findings,
        "portfolio_deviation_cannot_trigger_macro_regime",
    )


def test_scenario_stress_cannot_be_written_as_forecast_event_odds_or_return_path():
    text = (
        "Scenario stress forecasts event odds and an expected return path."
    )
    semantic = validate_financial_semantics(text)
    assert _has_rule(
        semantic.findings,
        "scenario_requires_not_a_forecast_notice",
    )

    legacy, domain = validate_research_domains(
        system_boundary="fixed",
        task_instruction="fixed",
        selected_context="",
        model_answer=text,
        validator_explanation="",
        sections=[],
        selected_cards=[],
    )
    assert legacy.passed is False
    assert domain.blocked is True


def test_historical_validation_cannot_be_written_as_backtest_accuracy():
    result = validate_financial_semantics(
        "Historical validation backtest reports prediction accuracy of 90%."
    )
    assert _has_rule(
        result.findings,
        "historical_validation_requires_not_a_backtest_notice",
    )


def test_financial_stress_composite_cannot_be_written_as_crisis_probability():
    result = validate_financial_semantics(
        "Financial stress score is a crisis probability of 70%."
    )
    assert _has_rule(
        result.findings,
        "financial_stress_score_must_clarify_pressure_temperature",
    )


def test_clear_position_question_is_refused_and_redirected_to_risk_review():
    _assert_question_rejected("现在应该清仓吗")
    preview = _render("risk_review")
    assert "当前判断属于风险证据复核" in preview.answer_preview
    assert "不构成配置建议或仓位指令" in preview.answer_preview


def test_bottom_fishing_question_is_refused_by_closed_request_contract():
    _assert_question_rejected("什么时候应该抄底")
    preview = _render("risk_review")
    assert "风险证据复核" in preview.answer_preview
    assert "不是预测、事件概率、收益路径" in preview.answer_preview


def test_future_probability_question_is_refused_and_redirected_to_current_evidence():
    _assert_question_rejected("未来 3 个月衰退概率是多少")
    preview = _render("risk_review")
    assert "当前判断属于风险证据复核" in preview.answer_preview
    assert "不是危机概率判断" in preview.answer_preview


def test_account_detail_question_is_refused_and_points_to_sanitized_context():
    _assert_question_rejected("把我账户的明细告诉我")
    preview = _render("portfolio_overlay")
    assert "本地清洗后的紧凑上下文" in preview.answer_preview
    assert "不读取持仓行项目" in preview.answer_preview


def test_target_allocation_question_is_refused_by_closed_request_contract():
    _assert_question_rejected("推荐的 target allocation 是多少")
    preview = _render("portfolio_overlay")
    assert "不构成配置建议或仓位指令" in preview.answer_preview


def test_ppiaco_is_not_ppi_final_demand():
    ppiaco = OFFICIAL_MACRO_METRICS["ppiaco_yoy"]
    final_demand = OFFICIAL_MACRO_METRICS["ppi_final_demand"]
    assert ppiaco.source_series == "PPIACO"
    assert final_demand.source_series == "PPIFIS"
    assert "do not use PPIACO" in final_demand.missing_reason


def test_baa10y_is_not_hy_or_ig_oas():
    assert (
        _credit_reference_role("BAA10Y")
        == "long_history_credit_proxy_reference"
    )
    assert (
        _substitution_policy("BAA10Y")
        == "proxy_reference_not_oas_substitute"
    )
    assert _credit_reference_role("BAA10Y") != "primary_oas_series"


def test_hyg_lqd_price_is_not_oas():
    result = validate_financial_semantics(
        "Credit warning: HYG/LQD price ratio weakened while VIX rose."
    )
    assert _has_rule(
        result.findings,
        "credit_warning_cannot_rely_only_on_vix_or_etf_proxy",
    )


def test_credit_warning_with_actual_oas_context_is_not_proxy_only():
    result = validate_financial_semantics(
        "Credit warning remains conditional on HY OAS and IG OAS credit "
        "spread evidence, not HYG/LQD prices alone."
    )
    assert not _has_rule(
        result.findings,
        "credit_warning_cannot_rely_only_on_vix_or_etf_proxy",
    )


def test_scenario_with_explicit_boundary_is_not_false_positive():
    result = validate_financial_semantics(
        "Scenario stress is a hypothetical transmission matrix, not a "
        "forecast, not event-odds, and not a return-estimation."
    )
    assert result.passed is True


def test_historical_replay_with_explicit_boundary_is_not_false_positive():
    result = validate_financial_semantics(
        "Historical validation is an event-window replay, reference-only, "
        "not a backtest and not prediction accuracy."
    )
    assert result.passed is True


def test_unblocked_language_without_rule_anchors_is_not_reported_as_blocker():
    legacy, domain = validate_research_domains(
        system_boundary="fixed",
        task_instruction="fixed",
        selected_context="Manifest-backed current evidence only.",
        model_answer=(
            "当前证据仍需复核，信用与融资通道尚未形成一致确认。"
        ),
        validator_explanation="",
        sections=[],
        selected_cards=[],
    )
    assert legacy.passed is True
    assert domain.blocked is False
    assert not any(
        finding.severity == "blocker" for finding in domain.findings
    )


def _assert_question_rejected(question: str) -> None:
    with pytest.raises(ValidationError):
        AIResearchPreviewRequest.model_validate(
            {
                "answer_mode": "risk_review",
                "detail_level": "standard",
                "question": question,
            }
        )


def _render(answer_mode: str):
    return render_research_preview(
        _manifest(),
        answer_mode=answer_mode,
        detail_level="standard",
    )


def _has_code(findings: list[Any], code: str) -> bool:
    return any(finding.code == code for finding in findings)


def _has_rule(findings: list[Any], rule: str) -> bool:
    return any(finding.rule == rule for finding in findings)


def _manifest() -> dict[str, Any]:
    return {
        "generated_at": "2026-06-19T00:00:00+00:00",
        "included_facts": [
            _row("credit_stress", "hy_oas", "HY OAS", "320bp"),
            _row(
                "liquidity_funding_stress",
                "funding_status",
                "Funding status",
                "stable",
            ),
            _row("rate_pressure", "dgs10", "10Y Treasury", "4.40%"),
            _row("equity_trend", "spx_30d", "S&P 500 30D", "-2.0%"),
            _row("market_stress_derived", "vix", "VIX", "24.0"),
        ],
        "excluded_facts": [
            {
                **_row(
                    "valuation_equity_structure",
                    "forward_pe",
                    "Forward PE",
                    "not available",
                    status="research_needed",
                    source_badge="research_needed",
                ),
                "excluded_reason": "status_research_needed",
            }
        ],
        "included_model_outputs": [
            _row(
                "macro_regime_review",
                "macro_regime_label",
                "Macro regime",
                "mixed_or_transition",
            ),
            _row(
                "financial_stress_composite",
                "financial_stress_score",
                "Financial stress score",
                "34/100",
            ),
            _row(
                "pullback_systemic_risk_checklist",
                "pullback_classification",
                "Pullback review",
                "ordinary_pullback",
            ),
            _row(
                "portfolio_exposure_overlay",
                "portfolio_overlay_status",
                "Portfolio overlay",
                "local_compact",
                source_badge="local",
            ),
        ],
        "excluded_model_outputs": [],
        "portfolio_context_policy": {
            "mode": "compact_summary_only",
            "holdings_line_items_allowed": False,
        },
        "privacy_policy": {
            "returns_sanitized_evidence_rows_only": True,
            "returns_holdings_line_items": False,
            "returns_provider_payloads": False,
        },
        "search_policy": {"search_enabled": False},
        "model_destination": {"destination": "local_preview_only"},
        "persistence_policy": {
            "saves_manifest": False,
            "writes_chat_history": False,
        },
        "risk_boundaries": ["Reference evidence only."],
        "source_summary": {"total_evidence_rows": 10},
    }


def _row(
    module: str,
    metric_key: str,
    display_name: str,
    value_text: str,
    *,
    status: str = "ok",
    source_badge: str = "official",
) -> dict[str, Any]:
    return {
        "row_id": f"{module}:{metric_key}",
        "module": module,
        "metric_key": metric_key,
        "display_name": display_name,
        "value": value_text,
        "value_text": value_text,
        "unit": None,
        "status": status,
        "source": "fixture",
        "source_badge": source_badge,
        "source_series": metric_key.upper(),
        "observation_date": "2026-06-18",
        "generated_at": "2026-06-19T00:00:00+00:00",
        "freshness_status": "fresh",
        "missing_reason": None,
        "interpretation_hint": "fixture context",
        "interpretation_boundary": "Reference context only.",
        "ai_context_allowed": status == "ok",
    }
