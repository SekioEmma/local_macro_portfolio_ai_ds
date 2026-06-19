from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app_backend.main import app
from app_backend.schemas.ai_preview import (
    AIPreviewChatRequest,
    AIResearchPreviewRequest,
)
from app_backend.services import ai_context_service, ai_preview_service
from app_backend.services.ai_prompt_context import select_prompt_context
from app_backend.services.ai_research_modes import ANSWER_MODE_TO_MEMO_TYPE
from app_backend.services.ai_research_renderer import (
    SYSTEM_BOUNDARY_ZH,
    render_prompt_preview,
    render_research_preview,
)
from app_backend.services.ai_semantic_validator import (
    validate_structured_research_semantics,
)


ANSWER_MODES = (
    "daily_brief",
    "risk_review",
    "scenario_review",
    "portfolio_overlay",
    "evidence_audit",
    "research_memo",
)
SECTION_KEYS = [
    "current_conclusion",
    "supporting_evidence",
    "counter_evidence",
    "data_constraints",
    "macro_explanation",
    "portfolio_channels",
    "watchlist_and_boundaries",
]


@pytest.mark.parametrize("answer_mode", ANSWER_MODES)
def test_all_answer_modes_map_to_legacy_types_and_render_seven_sections(answer_mode):
    preview = render_research_preview(
        _manifest_fixture(),
        answer_mode=answer_mode,
        detail_level="standard",
    )

    assert preview.legacy_memo_type == ANSWER_MODE_TO_MEMO_TYPE[answer_mode]
    assert [section.key for section in preview.research_sections] == SECTION_KEYS
    assert preview.not_sent_to_external_model is True
    assert preview.privacy_summary.external_model_called is False
    assert preview.privacy_summary.search_called is False
    assert preview.privacy_summary.saved_by_default is False
    assert preview.validator_result.passed is True


def test_prompt_selection_keeps_all_p1_and_aggregates_p4():
    manifest = _manifest_fixture()
    context, budget = select_prompt_context(
        manifest,
        answer_mode="risk_review",
    )

    expected_p1 = sum(
        1
        for key in ("included_facts", "included_model_outputs")
        for row in manifest[key]
        if row["module"]
        in {
            "macro_regime_review",
            "financial_stress_composite",
            "pullback_systemic_risk_checklist",
            "credit_stress",
            "liquidity_funding_stress",
            "rate_pressure",
            "real_yield_pressure",
        }
    )
    assert sum(card.priority == 1 for card in context.selected_cards) == expected_p1
    assert all(card.priority != 4 for card in context.selected_cards)
    assert context.constraint_summary.total_count == 2
    assert "status_research_needed" in (
        context.constraint_summary.excluded_reason_distribution
    )
    assert budget.ready is True


def test_prompt_selection_filters_p2_p3_by_mode():
    manifest = _manifest_fixture()
    risk_context, _ = select_prompt_context(manifest, answer_mode="risk_review")
    portfolio_context, _ = select_prompt_context(
        manifest,
        answer_mode="portfolio_overlay",
    )

    risk_modules = {card.module for card in risk_context.selected_cards}
    portfolio_modules = {card.module for card in portfolio_context.selected_cards}
    assert "scenario_stress" in risk_modules
    assert "portfolio_exposure_overlay" not in risk_modules
    assert "portfolio_exposure_overlay" in portfolio_modules
    assert "scenario_stress" not in portfolio_modules


def test_p1_over_budget_is_not_truncated_and_marks_not_ready():
    manifest = _manifest_fixture()
    context, budget = select_prompt_context(
        manifest,
        answer_mode="risk_review",
        card_limit=2,
        char_limit=32_000,
        estimated_token_limit=12_000,
    )

    assert sum(card.priority == 1 for card in context.selected_cards) > 2
    assert budget.ready is False
    assert budget.status_reason == "p1_core_context_exceeds_budget_not_truncated"


def test_prompt_selection_stops_after_first_eligible_budget_overflow():
    context, budget = select_prompt_context(
        _manifest_fixture(),
        answer_mode="risk_review",
        card_limit=8,
        char_limit=32_000,
        estimated_token_limit=12_000,
    )

    selected_ids = [
        f"{card.module}.{card.metric_key}" for card in context.selected_cards
    ]
    assert selected_ids[-1] == "equity_trend.spx_30d"
    assert "market_stress_derived.vix" not in selected_ids
    assert "breadth_concentration_proxy.top200_distance" not in selected_ids
    assert "scenario_stress.scenario_status" not in selected_ids
    assert budget.omitted_by_reason == {
        "budget_exceeded": 3,
        "mode_filtered": 1,
    }
    assert budget.omitted_by_priority == {"P2": 1, "P3": 3}


def test_prompt_preview_text_domain_allows_boundary_terms_without_blocking():
    preview = render_prompt_preview(
        _manifest_fixture(),
        answer_mode="risk_review",
        detail_level="standard",
    )

    assert "买入" in SYSTEM_BOUNDARY_ZH
    assert preview.semantic_validator_result.blocked is False
    assert preview.semantic_validator_result.domain_checks["system_boundary"] == (
        "fixed_server_template_not_output_scanned"
    )
    assert preview.not_sent_to_external_model is True
    assert preview.search_called is False
    assert preview.saved_by_default is False


def test_blocker_hides_research_and_prompt_payloads():
    manifest = _manifest_fixture()
    private_marker = "raw provider payload"
    manifest["included_facts"][0]["display_name"] = private_marker

    research = render_research_preview(
        manifest,
        answer_mode="risk_review",
        detail_level="standard",
    )
    prompt = render_prompt_preview(
        manifest,
        answer_mode="risk_review",
        detail_level="standard",
    )

    assert research.semantic_validator_result.blocked is True
    assert research.answer_preview == ""
    assert research.research_sections == []
    assert research.selected_prompt_context.selected_cards == []
    assert research.selected_prompt_context.selected_context_text == ""
    assert prompt.status == "not_ready"
    assert prompt.prompt_text == ""
    assert prompt.selected_prompt_context.selected_cards == []
    assert prompt.selected_prompt_context.selected_context_text == ""
    assert private_marker not in research.model_dump_json().lower()
    assert private_marker not in prompt.model_dump_json().lower()


@pytest.mark.parametrize(
    "question",
    [
        "我现在要不要清仓？",
        "我应该买黄金还是卖纳指？",
        "给我一个危机概率。",
        "现在是不是可以抄底？",
        "帮我做最优配置。",
    ],
)
def test_legacy_question_is_ignored_and_cannot_change_research_output(
    monkeypatch, question
):
    monkeypatch.setattr(
        ai_context_service,
        "build_ai_context_manifest",
        _manifest_fixture,
    )
    baseline = ai_preview_service.render_chat_preview(
        AIPreviewChatRequest(question="普通问题")
    )
    adversarial = ai_preview_service.render_chat_preview(
        AIPreviewChatRequest(question=question)
    )

    assert adversarial.answer_preview == baseline.answer_preview
    assert question not in adversarial.answer_preview
    assert adversarial.validator_result.passed is True


def test_structured_validator_blocks_systemic_upgrade_without_credit_funding():
    sections = [
        {
            "key": "current_conclusion",
            "claim_tags": ["systemic_risk_review", "systemic_risk_confirmed"],
            "source_context": ["market_stress_derived.vix"],
        }
    ]
    findings = validate_structured_research_semantics(sections)
    codes = {finding.code for finding in findings}

    assert "systemic_risk_requires_credit_funding_transmission" in codes
    assert "systemic_risk_prohibited_upgrade" in codes


def test_structured_validator_requires_support_in_same_claim_section():
    sections = [
        {
            "key": "current_conclusion",
            "claim_tags": ["systemic_risk_review"],
            "source_context": ["market_stress_derived.vix"],
        },
        {
            "key": "supporting_evidence",
            "claim_tags": ["evidence_support"],
            "source_context": [
                "credit_stress.hy_oas",
                "liquidity_funding_stress.funding_status",
                "pullback_systemic_risk_checklist.pullback_classification",
            ],
        },
    ]
    findings = validate_structured_research_semantics(
        sections,
        selected_cards=[
            {"module": "credit_stress"},
            {"module": "liquidity_funding_stress"},
            {"module": "pullback_systemic_risk_checklist"},
        ],
    )

    assert any(
        finding.code == "systemic_risk_requires_credit_funding_transmission"
        for finding in findings
    )


def test_structured_validator_blocks_proxy_breadth_upgrade():
    sections = [
        {
            "key": "macro_explanation",
            "claim_tags": ["true_breadth_deterioration"],
            "source_context": ["breadth_concentration_proxy.top200_distance"],
        }
    ]
    findings = validate_structured_research_semantics(sections)

    assert any(
        finding.code == "proxy_breadth_cannot_confirm_true_breadth"
        for finding in findings
    )


def test_counter_evidence_does_not_repeat_conclusion_or_supporting_context():
    preview = render_research_preview(
        _manifest_fixture(),
        answer_mode="risk_review",
        detail_level="standard",
    )
    sections = {section.key: section for section in preview.research_sections}
    used = set(sections["current_conclusion"].source_context) | set(
        sections["supporting_evidence"].source_context
    )
    counter = set(sections["counter_evidence"].source_context)

    assert counter
    assert counter.isdisjoint(used)


def test_new_api_contract_rejects_question_and_returns_read_only_preview(monkeypatch):
    monkeypatch.setattr(
        ai_context_service,
        "build_ai_context_manifest",
        _manifest_fixture,
    )
    client = TestClient(app)
    rejected = client.post(
        "/api/ai/research-preview",
        json={
            "answer_mode": "risk_review",
            "detail_level": "standard",
            "question": "must be rejected",
        },
    )
    accepted = client.post(
        "/api/ai/research-preview",
        json={"answer_mode": "risk_review", "detail_level": "standard"},
    )

    assert rejected.status_code == 422
    assert accepted.status_code == 200
    data = accepted.json()
    assert data["mode"] == "local_controlled_research_preview"
    assert data["answer_mode"] == "risk_review"
    assert len(data["research_sections"]) == 7
    assert data["not_sent_to_external_model"] is True


def test_prompt_api_contract_rejects_extra_fields(monkeypatch):
    monkeypatch.setattr(
        ai_context_service,
        "build_ai_context_manifest",
        _manifest_fixture,
    )
    response = TestClient(app).post(
        "/api/ai/prompt-preview",
        json={
            "answer_mode": "risk_review",
            "detail_level": "standard",
            "question": "must be rejected",
        },
    )

    assert response.status_code == 422


def test_context_preview_exposes_full_catalogue_without_truncation(monkeypatch):
    monkeypatch.setattr(
        ai_context_service,
        "build_ai_context_manifest",
        _manifest_fixture,
    )
    data = TestClient(app).get("/api/ai/context-preview").json()
    catalogue = data["full_context_catalogue"]

    assert catalogue["total_card_count"] == 14
    assert len(catalogue["evidence_cards"]) == 7
    assert len(catalogue["model_output_cards"]) == 5
    assert len(catalogue["excluded_constraint_cards"]) == 2
    assert catalogue["priority_counts"]["P4"] == 2


def test_preview_modules_do_not_import_external_ai_or_storage():
    for path in (
        Path("src/app_backend/services/ai_prompt_context.py"),
        Path("src/app_backend/services/ai_research_renderer.py"),
        Path("src/app_backend/services/ai_research_validator.py"),
    ):
        source = path.read_text(encoding="utf-8").lower()
        assert "ai_external_request_builder" not in source
        assert "import deepseek" not in source
        assert "from app_backend.services.deepseek" not in source
        assert "import tavily" not in source
        assert "storage_service" not in source


def test_request_model_accepts_only_mode_and_detail():
    request = AIResearchPreviewRequest(
        answer_mode="daily_brief",
        detail_level="brief",
    )
    assert request.model_dump() == {
        "answer_mode": "daily_brief",
        "detail_level": "brief",
    }


def _manifest_fixture():
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
        _row("equity_trend", "spx_30d", "S&P 500 30D", value_text="+1.2%"),
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
        }
    ]
    excluded_models = [
        {
            **_row(
                "historical_validation",
                "history_status",
                "Historical validation",
                status="insufficient_history",
                freshness_status="insufficient_history",
            ),
            "excluded_reason": "status_insufficient_history",
        }
    ]
    return {
        "generated_at": "2026-06-18T00:00:00+00:00",
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
        "source_summary": {"total_evidence_rows": 14},
    }


def _row(
    module,
    metric_key,
    display_name,
    *,
    value_text="available",
    status="ok",
    source_badge="official",
    freshness_status="fresh",
):
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
        "generated_at": "2026-06-18T00:00:00+00:00",
        "freshness_status": freshness_status,
        "missing_reason": None,
        "interpretation_hint": "fixture context",
        "interpretation_boundary": "Reference context only.",
        "ai_context_allowed": status == "ok",
    }
