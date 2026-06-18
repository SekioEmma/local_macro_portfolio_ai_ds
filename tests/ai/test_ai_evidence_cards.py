from __future__ import annotations

import pytest

from app_backend.services.ai_context_priority import (
    PRIORITY_CORE_MACRO_STATE,
    PRIORITY_EXCLUDED_CONSTRAINT,
)
from app_backend.services.ai_evidence_cards import (
    EVIDENCE_CARD_BOUNDARY_ZH,
    EXCLUDED_CONSTRAINT_CARD_BOUNDARY_ZH,
    MODEL_OUTPUT_CARD_BOUNDARY_ZH,
    EvidenceCard,
    ExcludedConstraintCard,
    ModelOutputCard,
    cards_as_text_blocks,
    render_evidence_card,
    render_excluded_constraint_card,
    render_manifest_cards,
    render_model_output_card,
)


def _credit_row():
    return {
        "module": "credit_stress",
        "metric_key": "high_yield_spread",
        "display_name": "High yield spread",
        "value_text": "350bp",
        "status": "watch",
        "source_badge": "official",
        "freshness_status": "fresh",
        "observation_date": "2026-06-17",
        "interpretation_hint": "HY OAS widening",
        "interpretation_boundary": "Reference context only.",
        "trigger_eligibility": "eligible",
    }


def _macro_regime_model_row():
    return {
        "module": "macro_regime_review",
        "metric_key": "macro_regime_label",
        "display_name": "Macro Regime Review",
        "value_text": "rates_pressure",
        "status": "watch",
        "source_badge": "derived",
        "freshness_status": "fresh",
        "observation_date": "2026-06-17",
        "interpretation_hint": "current evidence review",
        "interpretation_boundary": "Macro regime review is current evidence review, not future direction.",
        "component_contributions": {
            "support_band": "medium",
            "evidence_quality_band": "medium",
            "conflict_band": "low",
        },
        "missing_inputs": ["valuation_proxy"],
    }


def _excluded_valuation_row():
    return {
        "module": "valuation_equity_structure",
        "metric_key": "forward_pe",
        "display_name": "Forward P/E",
        "status": "research_needed",
        "source_badge": "research_needed",
        "freshness_status": "missing",
        "excluded_reason": "status_research_needed",
    }


def test_evidence_card_carries_chinese_module_label_and_p1_priority():
    card = render_evidence_card(_credit_row())

    assert isinstance(card, EvidenceCard)
    assert card.module == "credit_stress"
    assert "信用" in card.module_display_zh
    assert card.priority == PRIORITY_CORE_MACRO_STATE
    assert "P1" in card.priority_label_zh
    assert card.boundary_notice_zh == EVIDENCE_CARD_BOUNDARY_ZH


def test_evidence_card_text_block_includes_chinese_glosses_and_boundary():
    text = render_evidence_card(_credit_row()).as_text_block()

    assert "[证据卡片]" in text
    assert "High yield spread" in text
    assert "watch (观察)" in text
    assert "official (官方)" in text
    assert "fresh (新鲜)" in text
    assert "Reference context only." in text
    assert "boundary" in text


def test_model_output_card_extracts_bands_and_missing_input_count():
    card = render_model_output_card(_macro_regime_model_row())

    assert isinstance(card, ModelOutputCard)
    assert card.support_band == "medium"
    assert card.evidence_quality_band == "medium"
    assert card.conflict_band == "low"
    assert card.missing_input_count == 1
    assert card.boundary_notice_zh == MODEL_OUTPUT_CARD_BOUNDARY_ZH


def test_model_output_card_text_block_includes_bands_and_boundary():
    text = render_model_output_card(_macro_regime_model_row()).as_text_block()

    assert "[模型输出卡片]" in text
    assert "support_band: medium" in text
    assert "missing_input_count: 1" in text
    assert "Macro regime review is current evidence review" in text


def test_excluded_constraint_card_has_p4_and_chinese_effect():
    card = render_excluded_constraint_card(_excluded_valuation_row())

    assert isinstance(card, ExcludedConstraintCard)
    assert card.priority == PRIORITY_EXCLUDED_CONSTRAINT
    assert "P4" in card.priority_label_zh
    assert "需要研究" in card.excluded_reason_display_zh
    assert "缺少官方/可信来源映射" in card.effect_zh
    assert card.boundary_notice_zh == EXCLUDED_CONSTRAINT_CARD_BOUNDARY_ZH


def test_excluded_card_text_block_marks_not_promotable():
    text = render_excluded_constraint_card(_excluded_valuation_row()).as_text_block()

    assert "[约束卡片]" in text
    assert "forward_pe" in text
    assert "缺少官方/可信来源映射" in text
    assert "不能被升级为事实" in text


def test_render_manifest_cards_sorts_by_priority():
    manifest = {
        "included_facts": [
            {"module": "valuation_equity_structure", "metric_key": "fwd_pe"},
            {"module": "credit_stress", "metric_key": "hy_oas"},
            {"module": "equity_trend", "metric_key": "sp500_drawdown"},
        ],
        "included_model_outputs": [_macro_regime_model_row()],
        "excluded_facts": [_excluded_valuation_row()],
        "excluded_model_outputs": [],
    }
    bundle = render_manifest_cards(manifest)

    fact_modules = [card.module for card in bundle["evidence_cards"]]
    assert fact_modules.index("credit_stress") < fact_modules.index("equity_trend")
    assert fact_modules.index("equity_trend") < fact_modules.index(
        "valuation_equity_structure"
    )

    assert len(bundle["model_output_cards"]) == 1
    assert bundle["model_output_cards"][0].module == "macro_regime_review"
    assert len(bundle["excluded_constraint_cards"]) == 1


def test_cards_as_text_blocks_joins_with_blank_lines():
    cards = [
        render_evidence_card(_credit_row()),
        render_evidence_card(_credit_row()),
    ]
    joined = cards_as_text_blocks(cards)

    assert joined.count("[证据卡片]") == 2
    assert "\n\n" in joined


def test_render_evidence_card_rejects_row_without_identity():
    with pytest.raises(ValueError):
        render_evidence_card({})


def test_evidence_card_status_unknown_when_missing():
    card = render_evidence_card({"module": "credit_stress", "metric_key": "x"})
    assert card.status == "unknown"
    assert card.status_display_zh == "未知"
