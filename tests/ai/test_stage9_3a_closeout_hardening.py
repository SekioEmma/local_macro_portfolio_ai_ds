"""Stage 9.3-A closeout / adapter guard hardening tests."""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from app_backend.schemas.ai_external import (
    ExternalAIAdapterConfig,
    ExternalAIPrivacySummary,
    ExternalAIRequest,
    ExternalAIResponse,
)
from app_backend.schemas.ai_memo import AIMemoValidatorResult
from app_backend.services.ai_external_adapter import guard_response
from app_backend.services.deepseek_adapter import (
    DeepSeekAdapter,
    FakeDeepSeekAdapter,
    default_disabled_config,
)
from app_backend.services.ai_external_adapter import BlockedAdapterError


def test_external_ai_request_rejects_raw_prompt_extra_field():
    with pytest.raises(ValidationError) as exc:
        ExternalAIRequest(**_valid_request_payload(), raw_prompt="do not accept")
    assert "extra_forbidden" in str(exc.value)


def test_external_ai_request_rejects_api_key_extra_field():
    with pytest.raises(ValidationError) as exc:
        ExternalAIRequest(**_valid_request_payload(), api_key="do not accept")
    assert "extra_forbidden" in str(exc.value)


def test_external_ai_request_rejects_holdings_extra_field():
    with pytest.raises(ValidationError) as exc:
        ExternalAIRequest(**_valid_request_payload(), holdings="do not accept")
    assert "extra_forbidden" in str(exc.value)


def test_external_ai_response_rejects_raw_response_extra_field():
    with pytest.raises(ValidationError) as exc:
        ExternalAIResponse(**_valid_response_payload(), raw_response="do not accept")
    assert "extra_forbidden" in str(exc.value)


def test_external_ai_adapter_config_rejects_api_key_env_extra_field():
    with pytest.raises(ValidationError) as exc:
        ExternalAIAdapterConfig(api_key_env="DEEPSEEK_API_KEY")
    assert "extra_forbidden" in str(exc.value)


def test_external_ai_privacy_summary_rejects_account_values_extra_field():
    with pytest.raises(ValidationError) as exc:
        ExternalAIPrivacySummary(**_privacy_summary_payload(), account_values=True)
    assert "extra_forbidden" in str(exc.value)


def test_guard_response_blocks_failed_validator_result():
    response = _valid_response().model_copy(
        update={
            "validator_result": AIMemoValidatorResult(
                passed=False,
                blocked_terms=["fixture"],
                privacy_findings=[],
            )
        }
    )

    result = guard_response(response)

    assert result.passed is False
    assert "validator_result_must_pass" in result.findings


def test_guard_response_allows_valid_fake_response_after_hardening():
    response = FakeDeepSeekAdapter().generate(_valid_request())

    result = guard_response(response)

    assert result.passed is True
    assert result.findings == []


@pytest.mark.parametrize(
    ("term", "expected_finding"),
    [
        ("buy", "forbidden_response_term_buy"),
        ("sell", "forbidden_response_term_sell"),
        ("rebalance", "forbidden_response_term_rebalance"),
        ("target allocation", "forbidden_response_term_target_allocation"),
        ("target weight", "forbidden_response_term_target_weight"),
        ("expected return", "forbidden_response_term_expected_return"),
        ("predicted return", "forbidden_response_term_predicted_return"),
        ("future return", "forbidden_response_term_future_return"),
        (
            "market direction probability",
            "forbidden_response_term_market_direction_probability",
        ),
        ("crash probability", "forbidden_response_term_crash_probability"),
        ("recession probability", "forbidden_response_term_recession_probability"),
        ("trade signal", "forbidden_response_term_trade_signal"),
        ("guaranteed", "forbidden_response_term_guaranteed"),
        ("will rise", "forbidden_response_term_will_rise"),
        ("will fall", "forbidden_response_term_will_fall"),
    ],
)
def test_guard_response_blocks_forbidden_generated_output_terms(term, expected_finding):
    response = _valid_response().model_copy(
        update={"content": f"Unsafe fixture says: {term}."}
    )

    result = guard_response(response)

    assert result.passed is False
    assert expected_finding in result.findings


@pytest.mark.parametrize(
    ("token", "expected_fragment"),
    [
        ("DEEPSEEK_API_KEY", "deepseek_api_key"),
        ("TAVILY_API_KEY", "tavily_api_key"),
        ("sk_live_", "sk_live_"),
        ("sk_test_", "sk_test_"),
        ("current_holdings.csv", "current_holdingscsv"),
        ("data/private", "data_private"),
        ("account values", "account_values"),
        ("position weights", "position_weights"),
        ("transaction history", "transaction_history"),
        ("raw provider payload", "raw_provider_payload"),
        (".env", "env"),
        ("external_llm.yaml", "external_llmyaml"),
    ],
)
def test_guard_response_blocks_privacy_tokens_in_content(token, expected_fragment):
    response = _valid_response().model_copy(
        update={"content": f"Unsafe fixture contains {token}."}
    )

    result = guard_response(response)

    assert result.passed is False
    assert any(
        finding.startswith("forbidden_response_privacy_token_")
        and expected_fragment in finding
        for finding in result.findings
    )


def test_fake_deepseek_adapter_generate_still_passes_guard_response():
    response = FakeDeepSeekAdapter().generate(_valid_request())

    assert response.fake_response is True
    assert response.external_model_called is False
    assert guard_response(response).passed is True


def test_default_disabled_adapter_still_blocks_generate():
    adapter = DeepSeekAdapter(default_disabled_config())

    with pytest.raises(BlockedAdapterError) as exc:
        adapter.generate(_valid_request())

    assert "adapter_disabled_in_stage_9_3_a" in exc.value.findings


def _valid_request() -> ExternalAIRequest:
    return ExternalAIRequest(**_valid_request_payload())


def _valid_request_payload() -> dict:
    return {
        "request_id": "req-stage-9-3a-closeout",
        "provider": "deepseek",
        "mode": "fake",
        "user_intent_summary": "Sanitized local intent summary.",
        "context_preview_summary": "2 facts and 1 model output included.",
        "included_fact_count": 2,
        "included_model_output_count": 1,
        "excluded_context_summary": "1 excluded item remains a constraint.",
        "boundary_notices": ["Reference evidence only.", "Not an action directive."],
        "memo_type": "daily_review_memo",
        "preview_type": None,
        "validator_required": True,
    }


def _valid_response() -> ExternalAIResponse:
    return ExternalAIResponse(**_valid_response_payload())


def _valid_response_payload() -> dict:
    return {
        "provider": "deepseek",
        "mode": "fake",
        "external_model_called": False,
        "fake_response": True,
        "content": "Local fake adapter content. Not an action directive.",
        "validator_result": AIMemoValidatorResult(
            passed=True,
            blocked_terms=[],
            privacy_findings=[],
        ),
        "privacy_summary": ExternalAIPrivacySummary(**_privacy_summary_payload()),
        "not_saved_by_default": True,
        "human_review_required": True,
    }


def _privacy_summary_payload() -> dict:
    return {
        "uses_ai_context_manifest_only": True,
        "uses_holdings_line_items": False,
        "uses_raw_provider_payloads": False,
        "uses_raw_prompts": False,
        "external_model_called": False,
        "search_called": False,
        "saved_by_default": False,
    }
