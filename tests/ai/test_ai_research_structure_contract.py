from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from app_backend.services.ai_memo_renderer import (
    render_ai_memo_preview,
    validate_ai_memo_preview,
)
from app_backend.services.ai_research_renderer import (
    SYSTEM_BOUNDARY_ZH,
    render_research_preview,
)
from app_backend.services.ai_research_validator import validate_research_domains

_REPO_ROOT = Path(__file__).resolve().parents[2]


FIXTURE_DIR = (_REPO_ROOT / "tests/fixtures/ai_golden")
FIXTURE_PATHS = sorted(FIXTURE_DIR.glob("*.json"))
FIXTURES = [
    json.loads(path.read_text(encoding="utf-8"))
    for path in FIXTURE_PATHS
]

REFUSAL_PHRASES = {
    "must_refuse_action": "不构成配置建议或仓位指令",
    "must_refuse_probability": "不是预测、事件概率、收益路径",
    "must_refuse_holdings_exposure": "不读取持仓行项目",
    "must_refuse_source_substitution": (
        "不能被升级为事实，也不能用于触发强结论"
    ),
}


def test_golden_fixture_catalogue_is_within_required_size_and_unique():
    assert 60 <= len(FIXTURES) <= 100
    assert len(FIXTURES) == len(FIXTURE_PATHS)
    assert len({fixture["test_id"] for fixture in FIXTURES}) == len(FIXTURES)
    assert all(
        path.stem == fixture["test_id"]
        for path, fixture in zip(FIXTURE_PATHS, FIXTURES, strict=True)
    )


@pytest.mark.parametrize(
    "fixture",
    FIXTURES,
    ids=[fixture["test_id"] for fixture in FIXTURES],
)
def test_ai_research_structure_contract_over_golden_fixture(fixture):
    manifest = _manifest_fixture()
    preview = render_research_preview(
        manifest,
        answer_mode=fixture["answer_mode"],
        detail_level=fixture["detail_level"],
    )

    assert preview.answer_mode == fixture["answer_mode"]
    assert preview.detail_level == fixture["detail_level"]
    assert [section.key for section in preview.research_sections] == (
        fixture["required_structure"]
    )
    assert all(section.source_context for section in preview.research_sections)

    answer_lower = preview.answer_preview.lower()
    for phrase in fixture["must_contain_phrases_zh"]:
        assert phrase in preview.answer_preview
    for phrase in fixture["must_contain_phrases_en"]:
        assert phrase.lower() in answer_lower
    for phrase in fixture["must_not_contain_phrases_en"]:
        assert phrase.lower() not in answer_lower
    for phrase in fixture["must_not_contain_phrases_zh"]:
        _assert_zh_prohibited_phrase_absent(
            preview.answer_preview,
            phrase,
        )

    legacy_preview = render_ai_memo_preview(
        preview.legacy_memo_type,
        manifest,
    )
    assert validate_ai_memo_preview(legacy_preview).passed is True

    legacy_validator, domain_validator = validate_research_domains(
        system_boundary=SYSTEM_BOUNDARY_ZH,
        task_instruction="golden fixture local equivalent",
        selected_context=preview.selected_prompt_context.selected_context_text,
        model_answer=preview.answer_preview,
        validator_explanation="fixture contract validation",
        sections=preview.research_sections,
        selected_cards=preview.selected_prompt_context.selected_cards,
        prompt_ready=preview.prompt_budget.ready,
    )
    assert legacy_validator.passed is True

    if fixture["adversarial"]:
        refusal_phrase = REFUSAL_PHRASES[fixture["expected_outcome"]]
        assert (
            domain_validator.blocked
            or refusal_phrase in preview.answer_preview
        )
        assert fixture["user_question"] not in preview.answer_preview
    else:
        assert domain_validator.blocked is False
        assert not any(
            finding.severity == "blocker"
            for finding in domain_validator.findings
        )


def _assert_zh_prohibited_phrase_absent(answer: str, phrase: str) -> None:
    if phrase == "危机概率":
        answer = answer.replace("不是危机概率", "")
        answer = answer.replace("不构成危机概率", "")
    assert phrase not in answer


def _manifest_fixture() -> dict[str, Any]:
    included_facts = [
        _row("credit_stress", "hy_oas", "HY OAS", value_text="320bp"),
        _row(
            "liquidity_funding_stress",
            "funding_status",
            "Funding status",
            status="ok",
        ),
        _row("rate_pressure", "dgs10", "10Y Treasury", value_text="4.40%"),
        _row(
            "real_yield_pressure",
            "dfii10",
            "10Y real yield",
            value_text="2.10%",
        ),
        _row(
            "inflation_energy_pressure",
            "core_inflation",
            "Core inflation",
            value_text="moderating",
        ),
        _row(
            "growth_inflation_macro_pack",
            "growth_macro_status",
            "Growth context",
            value_text="mixed",
        ),
        _row(
            "equity_trend",
            "spx_30d",
            "S&P 500 30D",
            value_text="+1.2%",
        ),
        _row(
            "market_stress_derived",
            "vix",
            "VIX",
            value_text="18.2",
        ),
        _row(
            "breadth_concentration_proxy",
            "top200_distance",
            "Breadth proxy",
            source_badge="proxy",
        ),
    ]
    included_models = [
        _row(
            "macro_regime_review",
            "macro_regime_label",
            "Macro regime",
            value_text="rates_pressure",
        ),
        _row(
            "financial_stress_composite",
            "financial_stress_score",
            "Financial stress score",
            value_text="34/100",
        ),
        _row(
            "pullback_systemic_risk_checklist",
            "pullback_classification",
            "Pullback review",
            value_text="macro_pressure",
        ),
        _row(
            "scenario_stress",
            "scenario_status",
            "Scenario stress",
            value_text="limited",
        ),
        _row(
            "historical_validation",
            "history_status",
            "Historical validation",
            value_text="reference_only",
        ),
        _row(
            "portfolio_exposure_overlay",
            "portfolio_overlay_status",
            "Portfolio overlay",
            value_text="local_compact",
            source_badge="local",
        ),
    ]
    excluded_facts = [
        {
            **_row(
                "valuation_equity_structure",
                "forward_pe",
                "Forward PE",
                status="research_needed",
                source_badge="research_needed",
                freshness_status="missing",
            ),
            "excluded_reason": "status_research_needed",
        },
        {
            **_row(
                "breadth_concentration_proxy",
                "true_breadth",
                "True breadth",
                status="not_available",
                source_badge="research_needed",
                freshness_status="missing",
            ),
            "excluded_reason": "status_not_available",
        },
    ]
    excluded_models = [
        {
            **_row(
                "historical_validation",
                "extended_history_status",
                "Extended historical validation",
                status="insufficient_history",
                freshness_status="insufficient_history",
            ),
            "excluded_reason": "status_insufficient_history",
        }
    ]
    return {
        "generated_at": "2026-06-19T00:00:00+00:00",
        "included_facts": included_facts,
        "excluded_facts": excluded_facts,
        "included_model_outputs": included_models,
        "excluded_model_outputs": excluded_models,
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
        "source_summary": {"total_evidence_rows": 18},
    }


def _row(
    module: str,
    metric_key: str,
    display_name: str,
    *,
    value_text: str = "available",
    status: str = "ok",
    source_badge: str = "official",
    freshness_status: str = "fresh",
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
        "freshness_status": freshness_status,
        "missing_reason": None,
        "interpretation_hint": "fixture context",
        "interpretation_boundary": "Reference context only.",
        "ai_context_allowed": status == "ok",
    }
