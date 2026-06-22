from __future__ import annotations

import pytest

from app_backend.schemas.ai_preview import (
    AIConstraintSummary,
    AIDeepSeekResearchRequest,
    AISelectedPromptContext,
)
from app_backend.services import ai_deepseek_research_service as service


@pytest.mark.parametrize(
    "question",
    ["你好", "你好！", "hello", "What can you do?", "你能做什么？"],
)
def test_trivial_conversation_routes_to_local_guidance(question: str):
    assert service.classify_user_question(question) == "guidance"


@pytest.mark.parametrize(
    "question",
    ["你好，请分析通胀。", "hello, what does the yield curve imply?"],
)
def test_research_question_with_greeting_prefix_still_routes_to_research(
    question: str,
):
    assert service.classify_user_question(question) == "research"


def test_prompt_prioritizes_user_question_before_research_template():
    selected_context = AISelectedPromptContext(
        selected_cards=[],
        constraint_summary=AIConstraintSummary(
            total_count=0,
            excluded_reason_distribution={},
            module_distribution={},
            freshness_distribution={},
            summary_zh="无排除约束。",
        ),
        selected_context_text="示例证据上下文。",
        selection_notes=[],
    )
    question = "当前高实际利率对信用风险意味着什么？"

    prompt = service.build_deepseek_prompt(
        answer_mode="risk_review",
        detail_level="standard",
        user_question=question,
        selected_context=selected_context,
    )

    assert prompt.index("[最高优先级：回答用户问题]") < prompt.index("[任务:")
    assert prompt.index(question) < prompt.index("仅当用户提出有效的宏观研究问题时")
    assert "不要改答成通用市场综述" in prompt


def test_guidance_short_circuits_manifest_and_external_model(monkeypatch):
    def _unexpected_manifest_call():
        raise AssertionError("guidance must not build the research manifest")

    monkeypatch.setattr(
        service.ai_context_service,
        "build_ai_context_manifest",
        _unexpected_manifest_call,
    )

    response = service.run_deepseek_research(
        AIDeepSeekResearchRequest(user_question="你好")
    )

    assert response.response_kind == "guidance"
    assert response.model_provider == "local_intent_router"
    assert response.privacy_summary.external_model_called is False
    assert response.deepseek_raw_output == ""
    assert response.prompt_text == ""
    assert response.output_blocked is False
    assert "具体的宏观或市场风险问题" in response.deepseek_memo_output
