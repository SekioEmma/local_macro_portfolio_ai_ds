"""Stage 9.3-A external AI adapter guard regression tests.

Tests cover guard_config, guard_request, and guard_response for the
fail-closed behavior listed in the Stage 9.3-A design document.
"""
from __future__ import annotations

import pytest

from app_backend.schemas.ai_external import (
    ExternalAIAdapterConfig,
    ExternalAIPrivacySummary,
    ExternalAIRequest,
    ExternalAIResponse,
)
from app_backend.schemas.ai_memo import AIMemoValidatorResult
from app_backend.services.ai_external_adapter import (
    BlockedAdapterError,
    ExternalAIAdapter,
    guard_config,
    guard_request,
    guard_response,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _valid_config() -> ExternalAIAdapterConfig:
    return ExternalAIAdapterConfig(
        provider="deepseek",
        enabled=False,
        mode="disabled",
        allow_network=False,
        requires_user_switch=True,
        requires_context_preview=True,
        requires_validator=True,
        save_raw_prompt=False,
        save_raw_response=False,
    )


def _valid_request(**overrides) -> ExternalAIRequest:
    base = dict(
        request_id="req-001",
        provider="deepseek",
        mode="fake",
        user_intent_summary="Sanitized intent summary.",
        context_preview_summary="2 facts, 1 model output included.",
        included_fact_count=2,
        included_model_output_count=1,
        excluded_context_summary="1 excluded fact.",
        boundary_notices=["Reference evidence only."],
        memo_type="daily_review_memo",
        preview_type=None,
        validator_required=True,
    )
    base.update(overrides)
    return ExternalAIRequest(**base)


def _valid_response(**overrides) -> ExternalAIResponse:
    base = dict(
        provider="deepseek",
        mode="fake",
        external_model_called=False,
        fake_response=True,
        content="[fake] local content. Not an action directive.",
        validator_result=AIMemoValidatorResult(
            passed=True, blocked_terms=[], privacy_findings=[]
        ),
        privacy_summary=ExternalAIPrivacySummary(
            uses_ai_context_manifest_only=True,
            uses_holdings_line_items=False,
            uses_raw_provider_payloads=False,
            uses_raw_prompts=False,
            external_model_called=False,
            search_called=False,
            saved_by_default=False,
        ),
        not_saved_by_default=True,
        human_review_required=True,
    )
    base.update(overrides)
    return ExternalAIResponse(**base)


# ---------------------------------------------------------------------------
# Config guards
# ---------------------------------------------------------------------------


def test_default_config_passes_guard():
    assert guard_config(_valid_config()).passed is True


def test_guard_blocks_allow_network_true():
    cfg = _valid_config().model_copy(update={"allow_network": True})
    result = guard_config(cfg)
    assert result.passed is False
    assert any("allow_network" in f for f in result.findings)


def test_guard_blocks_mode_network():
    cfg = _valid_config().model_copy(update={"mode": "network"})
    result = guard_config(cfg)
    assert result.passed is False
    assert any("mode_network" in f for f in result.findings)


def test_guard_blocks_enabled_without_user_switch():
    cfg = _valid_config().model_copy(
        update={"enabled": True, "mode": "fake", "requires_user_switch": False}
    )
    result = guard_config(cfg)
    assert result.passed is False
    assert any("user_switch" in f for f in result.findings)


def test_guard_blocks_enabled_but_mode_disabled():
    cfg = _valid_config().model_copy(update={"enabled": True})
    result = guard_config(cfg)
    assert result.passed is False
    assert any("inconsistent" in f for f in result.findings)


def test_guard_blocks_requires_context_preview_false():
    cfg = _valid_config().model_copy(update={"requires_context_preview": False})
    result = guard_config(cfg)
    assert result.passed is False
    assert any("context_preview" in f for f in result.findings)


def test_guard_blocks_requires_validator_false():
    cfg = _valid_config().model_copy(update={"requires_validator": False})
    result = guard_config(cfg)
    assert result.passed is False
    assert any("validator" in f for f in result.findings)


def test_guard_blocks_save_raw_prompt_true():
    cfg = _valid_config().model_copy(update={"save_raw_prompt": True})
    result = guard_config(cfg)
    assert result.passed is False
    assert any("save_raw_prompt" in f for f in result.findings)


def test_guard_blocks_save_raw_response_true():
    cfg = _valid_config().model_copy(update={"save_raw_response": True})
    result = guard_config(cfg)
    assert result.passed is False
    assert any("save_raw_response" in f for f in result.findings)


# ---------------------------------------------------------------------------
# Request guards
# ---------------------------------------------------------------------------


def test_valid_request_passes_guard():
    assert guard_request(_valid_request()).passed is True


def test_guard_blocks_missing_context_preview_summary():
    request = _valid_request(context_preview_summary="   ")
    result = guard_request(request)
    assert result.passed is False
    assert "missing_context_preview_summary" in result.findings


def test_guard_blocks_missing_boundary_notices():
    request = _valid_request(boundary_notices=[])
    result = guard_request(request)
    assert result.passed is False
    assert "missing_boundary_notices" in result.findings


def test_guard_blocks_validator_required_false():
    request = _valid_request(validator_required=False)
    result = guard_request(request)
    assert result.passed is False
    assert "validator_required_must_be_true" in result.findings


def test_guard_blocks_mode_network_on_request():
    request = _valid_request(mode="network")
    result = guard_request(request)
    assert result.passed is False
    assert any("mode_network" in f for f in result.findings)


@pytest.mark.parametrize(
    "field_name",
    [
        "raw_prompt",
        "raw_question",
        "api_key",
        "deepseek_api_key",
        "tavily_api_key",
        "holdings",
        "holdings_line_items",
        "account_values",
        "position_weights",
        "transaction_history",
        "raw_provider_payload",
        "raw_manifest",
        "env_value",
        "file_path",
        "local_path",
        "search_results",
    ],
)
def test_guard_blocks_forbidden_raw_field_in_dict(field_name):
    request = _valid_request()
    raw = {**request.model_dump(), field_name: "some_value"}
    result = guard_request(request, raw_request=raw)
    assert result.passed is False
    assert f"forbidden_field_{field_name}" in result.findings


@pytest.mark.parametrize(
    "leaking_text",
    [
        "API_KEY=sk_live_secret_value_here_test",
        "Bearer ABCDEF1234567890",
        "current_holdings.csv loaded with 12 rows",
        "data/private/notes.md content",
        "G:\\local_macro_portfolio_ai is the project root",
        "transaction history attached",
        "holdings line items provided",
        "account values: $1,234,567",
        "position weights: 50/30/15/5",
        "raw provider payload attached",
        ".env contents leaked",
        "external_llm.yaml secrets",
    ],
)
def test_guard_blocks_forbidden_token_in_request_text(leaking_text):
    request = _valid_request(context_preview_summary=leaking_text)
    result = guard_request(request)
    assert result.passed is False
    assert any("forbidden_token_" in f for f in result.findings)


# ---------------------------------------------------------------------------
# Response guards
# ---------------------------------------------------------------------------


def test_valid_response_passes_guard():
    assert guard_response(_valid_response()).passed is True


def test_guard_blocks_external_model_called_true_on_response():
    response = _valid_response(external_model_called=True)
    result = guard_response(response)
    assert result.passed is False
    assert any("external_model_called" in f for f in result.findings)


def test_guard_blocks_privacy_external_model_called_true():
    response = _valid_response()
    response = response.model_copy(
        update={
            "privacy_summary": response.privacy_summary.model_copy(
                update={"external_model_called": True}
            )
        }
    )
    result = guard_response(response)
    assert result.passed is False
    assert any("privacy_external_model_called" in f for f in result.findings)


def test_guard_blocks_privacy_search_called_true():
    response = _valid_response()
    response = response.model_copy(
        update={
            "privacy_summary": response.privacy_summary.model_copy(
                update={"search_called": True}
            )
        }
    )
    assert guard_response(response).passed is False


def test_guard_blocks_privacy_saved_by_default_true():
    response = _valid_response()
    response = response.model_copy(
        update={
            "privacy_summary": response.privacy_summary.model_copy(
                update={"saved_by_default": True}
            )
        }
    )
    assert guard_response(response).passed is False


def test_guard_blocks_uses_holdings_line_items_true():
    response = _valid_response()
    response = response.model_copy(
        update={
            "privacy_summary": response.privacy_summary.model_copy(
                update={"uses_holdings_line_items": True}
            )
        }
    )
    assert guard_response(response).passed is False


def test_guard_blocks_uses_raw_prompts_true():
    response = _valid_response()
    response = response.model_copy(
        update={
            "privacy_summary": response.privacy_summary.model_copy(
                update={"uses_raw_prompts": True}
            )
        }
    )
    assert guard_response(response).passed is False


def test_guard_blocks_not_saved_by_default_false():
    response = _valid_response(not_saved_by_default=False)
    assert guard_response(response).passed is False


def test_guard_blocks_human_review_required_false():
    response = _valid_response(human_review_required=False)
    assert guard_response(response).passed is False


def test_guard_blocks_uses_manifest_only_false():
    response = _valid_response()
    response = response.model_copy(
        update={
            "privacy_summary": response.privacy_summary.model_copy(
                update={"uses_ai_context_manifest_only": False}
            )
        }
    )
    assert guard_response(response).passed is False


def test_guard_blocks_response_mode_network():
    """The Pydantic mode union allows 'network', but guard_response fails closed."""
    response = _valid_response(mode="network")
    result = guard_response(response)
    assert result.passed is False
    assert any("network" in f for f in result.findings)


def test_guard_blocks_fake_mode_with_fake_response_false():
    response = _valid_response(fake_response=False)
    result = guard_response(response)
    assert result.passed is False
    assert any("fake_response" in f for f in result.findings)


# ---------------------------------------------------------------------------
# Base class init also runs config guard
# ---------------------------------------------------------------------------


def test_base_adapter_init_runs_config_guard():
    cfg = _valid_config().model_copy(update={"allow_network": True})
    with pytest.raises(BlockedAdapterError):
        ExternalAIAdapter(cfg)


def test_base_adapter_generate_must_be_implemented():
    adapter = ExternalAIAdapter(_valid_config())
    with pytest.raises(NotImplementedError):
        adapter.generate(_valid_request())


# ---------------------------------------------------------------------------
# Nested raw_request guard (Stage 9.3-A audit hardening)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "forbidden_field",
    [
        "raw_prompt",
        "api_key",
        "holdings_line_items",
        "account_values",
        "position_weights",
        "transaction_history",
        "raw_provider_payload",
        "search_results",
    ],
)
def test_guard_blocks_nested_forbidden_field_name_in_raw_request(forbidden_field):
    """A nested key like {'meta': {'<forbidden>': 'x'}} must also be caught."""
    request = _valid_request()
    raw = {
        **request.model_dump(),
        "meta": {"inner": {forbidden_field: "leaked"}},
    }
    result = guard_request(request, raw_request=raw)
    assert result.passed is False
    assert f"forbidden_field_{forbidden_field}" in result.findings


@pytest.mark.parametrize(
    "leaking_text",
    [
        "current_holdings.csv path attached",
        "data/private/notes",
        "API_KEY=sk_live_secret_value_test",
        "Bearer ABCDEF1234567890",
        "G:\\local_macro_portfolio_ai project root",
        "holdings line items: 10 rows",
        "account values: $1,234,567",
        "transaction history: 100 trades",
        ".env file contents",
        "external_llm.yaml secrets",
    ],
)
def test_guard_blocks_nested_forbidden_token_in_raw_request_string_value(leaking_text):
    """Forbidden tokens in nested string values of raw_request must also be caught."""
    request = _valid_request()
    raw = {
        **request.model_dump(),
        "meta": {"deeply": {"nested": {"note": leaking_text}}},
    }
    result = guard_request(request, raw_request=raw)
    assert result.passed is False
    assert any("forbidden_raw_token_" in f for f in result.findings)


def test_guard_safe_nested_raw_request_passes():
    request = _valid_request()
    raw = {
        **request.model_dump(),
        "meta": {"trace_id": "abc-123", "user_locale": "zh-CN"},
    }
    result = guard_request(request, raw_request=raw)
    assert result.passed is True


def test_guard_blocks_forbidden_field_inside_list_in_raw_request():
    """List items containing a forbidden-field-bearing dict must also be caught."""
    request = _valid_request()
    raw = {
        **request.model_dump(),
        "trace_steps": [
            {"step": 1, "note": "ok"},
            {"step": 2, "api_key": "sk_live_secret"},
        ],
    }
    result = guard_request(request, raw_request=raw)
    assert result.passed is False
    assert "forbidden_field_api_key" in result.findings
