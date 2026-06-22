from __future__ import annotations

import pytest

from app_backend.schemas.ai_preview import (
    AIConstraintSummary,
    AIDeepSeekResearchRequest,
    AISelectedPromptContext,
)
from app_backend.services import ai_deepseek_research_service as service
from app_backend.services.ai_external_runtime_policy import (
    guard_external_ai_runtime_policy,
)


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


def test_runtime_policy_passes_when_external_ai_enabled_and_context_ready():
    policy = service._build_runtime_policy(
        external_ai_enabled=True,
        context_preview_ready=True,
    )
    result = guard_external_ai_runtime_policy(policy)
    assert result.passed is True
    assert result.findings == []


def test_runtime_policy_fails_closed_without_external_ai_enabled():
    """No provider key / switch off must make the guard fail closed, not pass."""
    policy = service._build_runtime_policy(
        external_ai_enabled=False,
        context_preview_ready=True,
    )
    result = guard_external_ai_runtime_policy(policy)
    assert result.passed is False
    assert "external_ai_disabled" in result.findings
    # Gates must reflect real state, not be hardcoded True.
    assert policy.external_ai_enabled is False
    assert policy.provider_network_enabled is False
    assert policy.user_controlled_switch_enabled is False


def test_runtime_policy_fails_closed_when_context_not_ready():
    policy = service._build_runtime_policy(
        external_ai_enabled=True,
        context_preview_ready=False,
    )
    result = guard_external_ai_runtime_policy(policy)
    assert result.passed is False
    assert "request_not_built_from_manifest" in result.findings


def test_external_ai_capability_unavailable_when_key_missing(monkeypatch):
    from app_backend.services.deepseek_transport_contract import (
        DeepSeekTransportError,
    )

    def _no_key():
        raise DeepSeekTransportError(kind="missing_key", detail="deepseek_api_key_missing")

    monkeypatch.setattr(service, "load_deepseek_api_key_from_env", _no_key)
    available, api_key = service._external_ai_capability()
    assert available is False
    assert api_key == ""


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
