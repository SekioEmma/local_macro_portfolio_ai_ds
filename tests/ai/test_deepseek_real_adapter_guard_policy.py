"""Stage 9.3-B-2c external response guard policy tests."""
from __future__ import annotations

from pathlib import Path

import pytest

from app_backend.schemas.ai_external import (
    DeepSeekTransportRequest,
    DeepSeekTransportResponse,
    ExternalAIPrivacySummary,
    ExternalAIRequest,
    ExternalAIResponse,
    ExternalAIRuntimePolicy,
)
from app_backend.schemas.ai_memo import AIMemoValidatorResult
from app_backend.services.ai_external_adapter import (
    BlockedAdapterError,
    guard_external_model_response,
    guard_response,
)
from app_backend.services.deepseek_adapter import (
    DeepSeekNetworkAdapter,
    fake_only_config,
    network_config,
)


def _validator_result(**overrides) -> AIMemoValidatorResult:
    base = dict(passed=True, blocked_terms=[], privacy_findings=[])
    base.update(overrides)
    return AIMemoValidatorResult(**base)


def _external_response(**overrides) -> ExternalAIResponse:
    privacy = overrides.pop(
        "privacy_summary",
        ExternalAIPrivacySummary(
            uses_ai_context_manifest_only=True,
            uses_holdings_line_items=False,
            uses_raw_provider_payloads=False,
            uses_raw_prompts=False,
            external_model_called=True,
            search_called=False,
            saved_by_default=False,
        ),
    )
    base = dict(
        provider="deepseek",
        mode="network",
        external_model_called=True,
        fake_response=False,
        content="Reference evidence only. Human review is required.",
        validator_result=_validator_result(),
        privacy_summary=privacy,
        not_saved_by_default=True,
        human_review_required=True,
    )
    base.update(overrides)
    return ExternalAIResponse(**base)


def _request() -> ExternalAIRequest:
    return ExternalAIRequest(
        request_id="req-2c-001",
        provider="deepseek",
        mode="fake",
        user_intent_summary="Sanitized macro context review.",
        context_preview_summary="2 facts and 1 model output included.",
        included_fact_count=2,
        included_model_output_count=1,
        excluded_context_summary="1 excluded fact.",
        boundary_notices=["Reference evidence only.", "Not an action directive."],
        memo_type="daily_review_memo",
        preview_type=None,
        validator_required=True,
    )


def _policy() -> ExternalAIRuntimePolicy:
    return ExternalAIRuntimePolicy(
        external_ai_enabled=True,
        provider_network_enabled=True,
        user_controlled_switch_enabled=True,
        single_request_user_approved=True,
        context_preview_confirmed=True,
        request_built_from_manifest=True,
        request_guard_passed=True,
        response_guard_required=True,
        stage9_validator_required=True,
        human_review_required=True,
        save_raw_prompt=False,
        save_raw_response=False,
        persist_chat_by_default=False,
        allow_search=False,
        allow_tavily=False,
        allow_background_call=False,
        allow_app_start_call=False,
        allow_page_load_call=False,
        allow_holdings_line_items=False,
        allow_account_values=False,
        allow_position_weights=False,
        allow_transaction_history=False,
    )


class _Transport:
    def __init__(self, content: str) -> None:
        self.calls: list[DeepSeekTransportRequest] = []
        self.content = content

    def send(self, request: DeepSeekTransportRequest) -> DeepSeekTransportResponse:
        self.calls.append(request)
        return DeepSeekTransportResponse(
            request_id=request.request_id,
            provider=request.provider,
            mode=request.mode,
            content_text=self.content,
        )


def _adapter(content: str) -> DeepSeekNetworkAdapter:
    return DeepSeekNetworkAdapter(
        config=fake_only_config(),
        transport=_Transport(content),
        runtime_policy=_policy(),
    )


def _network_adapter(content: str) -> DeepSeekNetworkAdapter:
    return DeepSeekNetworkAdapter(
        config=network_config(),
        transport=_Transport(content),
        runtime_policy=_policy(),
    )


def test_default_guard_response_still_blocks_external_model_called_true():
    result = guard_response(_external_response())

    assert result.passed is False
    assert "external_model_called_blocked_in_stage_9_3_a" in result.findings


def test_explicit_external_guard_allows_compliant_external_response():
    result = guard_external_model_response(_external_response())

    assert result.passed is True
    assert result.findings == []


def test_fake_response_true_with_external_model_called_is_blocked():
    result = guard_external_model_response(_external_response(fake_response=True))

    assert result.passed is False
    assert "external_response_must_not_be_fake" in result.findings


def test_privacy_external_model_called_false_is_blocked():
    response = _external_response()
    response = response.model_copy(
        update={
            "privacy_summary": response.privacy_summary.model_copy(
                update={"external_model_called": False}
            )
        }
    )

    result = guard_external_model_response(response)

    assert result.passed is False
    assert "privacy_external_model_called_must_be_true" in result.findings


@pytest.mark.parametrize(
    "flag,finding",
    [
        ("uses_ai_context_manifest_only", "must_use_ai_context_manifest_only"),
        ("uses_holdings_line_items", "uses_holdings_line_items_blocked"),
        ("uses_raw_provider_payloads", "uses_raw_provider_payloads_blocked"),
        ("uses_raw_prompts", "uses_raw_prompts_blocked"),
        ("search_called", "privacy_search_called_blocked"),
        ("saved_by_default", "privacy_saved_by_default_blocked"),
    ],
)
def test_external_guard_blocks_privacy_flag_violations(flag, finding):
    response = _external_response()
    bad_value = False if flag == "uses_ai_context_manifest_only" else True
    response = response.model_copy(
        update={
            "privacy_summary": response.privacy_summary.model_copy(
                update={flag: bad_value}
            )
        }
    )

    result = guard_external_model_response(response)

    assert result.passed is False
    assert finding in result.findings


def test_not_saved_by_default_false_is_blocked():
    result = guard_external_model_response(
        _external_response(not_saved_by_default=False)
    )

    assert result.passed is False
    assert "not_saved_by_default_must_be_true" in result.findings


def test_human_review_required_false_is_blocked():
    result = guard_external_model_response(
        _external_response(human_review_required=False)
    )

    assert result.passed is False
    assert "human_review_required_must_be_true" in result.findings


def test_validator_result_false_is_blocked():
    result = guard_external_model_response(
        _external_response(
            validator_result=_validator_result(
                passed=False,
                blocked_terms=["buy"],
                privacy_findings=[],
            )
        )
    )

    assert result.passed is False
    assert "validator_result_must_pass" in result.findings


def test_forbidden_output_term_is_blocked():
    result = guard_external_model_response(
        _external_response(content="This response says buy now.")
    )

    assert result.passed is False
    assert any("forbidden_response_term" in finding for finding in result.findings)


def test_privacy_token_is_blocked():
    result = guard_external_model_response(
        _external_response(content="The response mentions api_key.")
    )

    assert result.passed is False
    assert any(
        "forbidden_response_privacy_token" in finding for finding in result.findings
    )


def test_adapter_real_response_path_calls_validator_before_returning(monkeypatch):
    calls: list[str] = []

    def _validator(content: str) -> AIMemoValidatorResult:
        calls.append(content)
        return _validator_result()

    monkeypatch.setattr(
        "app_backend.services.deepseek_adapter.validate_external_ai_response_content",
        _validator,
    )
    response = _network_adapter(
        "Reference evidence only. Human review is required."
    ).generate_external_response(_request())

    assert calls == ["Reference evidence only. Human review is required."]
    assert response.external_model_called is True
    assert response.fake_response is False
    assert response.mode == "network"
    assert response.validator_result.passed is True


def test_adapter_validator_failure_prevents_response_return(monkeypatch):
    def _validator(content: str) -> AIMemoValidatorResult:
        return _validator_result(
            passed=False,
            blocked_terms=["buy"],
            privacy_findings=[],
        )

    monkeypatch.setattr(
        "app_backend.services.deepseek_adapter.validate_external_ai_response_content",
        _validator,
    )

    with pytest.raises(BlockedAdapterError) as exc:
        _adapter("Reference evidence only.").generate_external_response(_request())

    assert "validator_result_must_pass" in exc.value.findings


@pytest.mark.parametrize(
    "file_path",
    [
        "src/app_backend/main.py",
        "src/app_backend/services/ai_preview_service.py",
        "src/app_backend/services/ai_memo_renderer.py",
        "src/app_backend/services/ai_context_service.py",
    ],
)
@pytest.mark.parametrize(
    "forbidden",
    [
        "DeepSeekNetworkAdapter",
        "DeepSeekRealTransport",
        "deepseek_real_transport",
        "deepseek_adapter",
        "ai_external_runtime_policy",
        "build_deepseek_provider_payload",
    ],
)
def test_stage9_2_files_still_do_not_import_real_transport_adapter_or_policy(
    file_path,
    forbidden,
):
    source = Path(file_path).read_text(encoding="utf-8")
    assert forbidden not in source


def test_no_forbidden_routes_added():
    from app_backend.main import app

    route_paths = {route.path for route in app.routes}
    forbidden = {
        "/api/chat",
        "/api/search",
        "/api/ai/deepseek",
        "/api/ai/external",
        "/api/ai/tavily",
    }
    assert route_paths.isdisjoint(forbidden)


def test_no_local_config_reads_or_raw_persistence_fields_added():
    production_files = [
        "src/app_backend/services/ai_external_adapter.py",
        "src/app_backend/services/deepseek_adapter.py",
        "src/app_backend/services/deepseek_real_transport.py",
    ]
    for file_path in production_files:
        source = Path(file_path).read_text(encoding="utf-8")
        assert "dotenv" not in source
        assert "open('.env'" not in source
        assert 'open(".env"' not in source
        assert "open('external_llm.yaml'" not in source
        assert 'open("external_llm.yaml"' not in source
        assert "save_raw_prompt=True" not in source
        assert "save_raw_response=True" not in source


def test_api_key_still_only_read_in_real_transport_loader():
    source = Path("src/app_backend/services/deepseek_real_transport.py").read_text(
        encoding="utf-8"
    )
    assert source.count("os.environ") == 1
    assert "load_deepseek_api_key_from_env" in source
