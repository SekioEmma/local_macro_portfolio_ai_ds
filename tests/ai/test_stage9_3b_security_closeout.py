"""Stage 9.3-B security closeout / external AI boundary audit tests.

This file is intentionally broad but read-only. It verifies that the Stage
9.3-A through Stage 9.3-B-2c DeepSeek seam remains internal, manifest-only,
guarded, non-persistent, and isolated from Stage 9.2 endpoints.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest
from pydantic import ValidationError

from app_backend.main import app
from app_backend.schemas.ai_external import (
    DeepSeekTransportRequest,
    DeepSeekTransportResponse,
    ExternalAIPrivacySummary,
    ExternalAIRequest,
    ExternalAIResponse,
    ExternalAIRuntimePolicy,
    default_external_ai_runtime_policy,
)
from app_backend.schemas.ai_memo import AIMemoValidatorResult
from app_backend.services.ai_external_adapter import (
    BlockedAdapterError,
    FORBIDDEN_RESPONSE_OUTPUT_TERMS,
    guard_external_model_response,
    guard_response,
)
from app_backend.services.ai_external_runtime_policy import (
    guard_external_ai_runtime_policy,
)
from app_backend.services.deepseek_adapter import DeepSeekNetworkAdapter, fake_only_config, network_config
from app_backend.services.deepseek_provider_contract import build_deepseek_provider_payload
from app_backend.services.deepseek_transport_contract import (
    DeepSeekTransportError,
    build_transport_request_from_provider_payload,
)


STAGE_9_2_SURFACE_FILES = (
    "src/app_backend/main.py",
    "src/app_backend/services/ai_preview_service.py",
    "src/app_backend/services/ai_memo_renderer.py",
    "src/app_backend/services/ai_context_service.py",
)

STAGE_9_3_PRODUCTION_FILES = (
    "src/app_backend/services/ai_external_adapter.py",
    "src/app_backend/services/ai_external_request_builder.py",
    "src/app_backend/services/ai_external_runtime_policy.py",
    "src/app_backend/services/deepseek_adapter.py",
    "src/app_backend/services/deepseek_provider_contract.py",
    "src/app_backend/services/deepseek_real_transport.py",
    "src/app_backend/services/deepseek_transport_contract.py",
    "src/app_backend/schemas/ai_external.py",
)


def _safe_request(**overrides) -> ExternalAIRequest:
    base = dict(
        request_id="req-closeout-001",
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
    base.update(overrides)
    return ExternalAIRequest(**base)


def _happy_policy(**overrides) -> ExternalAIRuntimePolicy:
    base = dict(
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
    base.update(overrides)
    return ExternalAIRuntimePolicy(**base)


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


class _SpyTransport:
    def __init__(
        self,
        *,
        content: str = "Reference evidence only. Human review is required.",
        error_kind: str | None = None,
        malformed: bool = False,
    ) -> None:
        self.calls: list[DeepSeekTransportRequest] = []
        self.content = content
        self.error_kind = error_kind
        self.malformed = malformed

    def send(self, request: DeepSeekTransportRequest):
        self.calls.append(request)
        if self.error_kind is not None:
            raise DeepSeekTransportError(kind=self.error_kind)
        if self.malformed:
            return {"content_text": self.content}
        return DeepSeekTransportResponse(
            request_id=request.request_id,
            provider=request.provider,
            mode=request.mode,
            content_text=self.content,
        )


def _adapter(transport: _SpyTransport, *, policy: ExternalAIRuntimePolicy | None = None):
    return DeepSeekNetworkAdapter(
        config=fake_only_config(),
        transport=transport,
        runtime_policy=policy or _happy_policy(),
    )


def _network_adapter(transport: _SpyTransport, *, policy: ExternalAIRuntimePolicy | None = None):
    return DeepSeekNetworkAdapter(
        config=network_config(),
        transport=transport,
        runtime_policy=policy or _happy_policy(),
    )


def test_route_surface_closeout_has_no_external_ai_or_search_routes():
    route_paths = {route.path for route in app.routes}
    forbidden_routes = {
        "/api/chat",
        "/api/search",
        "/api/ai/chat",
        "/api/ai/search",
        "/api/ai/deepseek",
        "/api/ai/external",
        "/api/ai/tavily",
        "/api/ai/send",
        "/api/ai/complete",
        "/api/ai/generate",
        "/api/ai/provider-payload",
        "/api/ai/runtime-policy",
    }

    assert route_paths.isdisjoint(forbidden_routes)
    assert "/api/ai/context-preview" in route_paths
    assert "/api/ai/preview-chat" in route_paths
    assert "/api/ai/preview-memo" in route_paths
    assert "/api/ai/preview-report" in route_paths


@pytest.mark.parametrize("file_path", STAGE_9_2_SURFACE_FILES)
@pytest.mark.parametrize(
    "forbidden",
    [
        "DeepSeekNetworkAdapter",
        "DeepSeekRealTransport",
        "deepseek_real_transport",
        "deepseek_adapter",
        "ai_external_runtime_policy",
        "guard_external_model_response",
        "generate_external_response",
        "build_deepseek_provider_payload",
        "build_transport_request_from_provider_payload",
        "load_deepseek_api_key_from_env",
    ],
)
def test_stage9_2_isolation_closeout(file_path, forbidden):
    source = Path(file_path).read_text(encoding="utf-8")
    assert forbidden not in source


def test_env_api_key_closeout_limits_key_and_env_access_to_real_transport_loader():
    locations: dict[str, list[str]] = {}
    for file_path in STAGE_9_3_PRODUCTION_FILES:
        source = Path(file_path).read_text(encoding="utf-8")
        if "DEEPSEEK_API_KEY" in source:
            locations.setdefault("DEEPSEEK_API_KEY", []).append(file_path)
        if "os.environ" in source or "os.getenv" in source:
            locations.setdefault("env_read", []).append(file_path)
        assert "dotenv" not in source
        assert "open('.env'" not in source
        assert 'open(".env"' not in source
        assert "open('external_llm.yaml'" not in source
        assert 'open("external_llm.yaml"' not in source

    assert locations.get("DEEPSEEK_API_KEY") == [
        "src/app_backend/services/deepseek_real_transport.py"
    ]
    assert locations.get("env_read") == [
        "src/app_backend/services/deepseek_real_transport.py"
    ]

    real_transport_source = Path(
        "src/app_backend/services/deepseek_real_transport.py"
    ).read_text(encoding="utf-8")
    loader_start = real_transport_source.index("def load_deepseek_api_key_from_env")
    loader_end = real_transport_source.index("\n\nclass DeepSeekRealTransport")
    loader_source = real_transport_source[loader_start:loader_end]
    assert "os.environ" in loader_source
    assert real_transport_source.count("os.environ") == 1


def test_network_surface_closeout_keeps_real_http_isolated_to_real_transport():
    for file_path in STAGE_9_3_PRODUCTION_FILES:
        source = Path(file_path).read_text(encoding="utf-8")
        if file_path == "src/app_backend/services/deepseek_real_transport.py":
            assert "urllib.request" in source
            continue
        for forbidden in (
            "urllib.request",
            "import httpx",
            "import requests",
            "import aiohttp",
            "socket.create_connection",
        ):
            assert forbidden not in source


def test_manifest_only_request_chain_excludes_raw_and_private_fields():
    request = _safe_request()
    with pytest.raises(ValidationError):
        ExternalAIRequest(**{**request.model_dump(), "raw_prompt": "secret"})
    with pytest.raises(ValidationError):
        ExternalAIRequest(**{**request.model_dump(), "raw_question": "secret"})

    payload = build_deepseek_provider_payload(request)
    payload_dump = payload.model_dump()
    payload_text = str(payload_dump).lower()
    assert "raw_question" not in payload_dump
    assert "raw_prompt" not in payload_dump
    assert "raw question" not in payload_text
    assert "raw prompt" not in payload_text

    transport_request = build_transport_request_from_provider_payload(payload)
    forbidden_transport_fields = {
        "api_key",
        "base_url",
        "endpoint",
        "model",
        "model_name",
        "raw_prompt",
        "raw_response",
        "holdings",
        "holdings_line_items",
        "account",
        "account_values",
        "position",
        "position_weights",
        "transaction",
        "transaction_history",
    }
    assert set(transport_request.model_dump()).isdisjoint(forbidden_transport_fields)

    with pytest.raises(BlockedAdapterError):
        build_deepseek_provider_payload(
            _safe_request(context_preview_summary="api_key=sk_live_secret")
        )


def test_runtime_policy_gate_closeout():
    default_result = guard_external_ai_runtime_policy(default_external_ai_runtime_policy())
    assert default_result.passed is False
    assert "external_ai_disabled" in default_result.findings

    assert guard_external_ai_runtime_policy(_happy_policy()).passed is True

    dangerous_flags = [
        "save_raw_prompt",
        "save_raw_response",
        "persist_chat_by_default",
        "allow_search",
        "allow_tavily",
        "allow_background_call",
        "allow_app_start_call",
        "allow_page_load_call",
        "allow_holdings_line_items",
        "allow_account_values",
        "allow_position_weights",
        "allow_transaction_history",
    ]
    for flag in dangerous_flags:
        result = guard_external_ai_runtime_policy(_happy_policy(**{flag: True}))
        assert result.passed is False, flag


def test_real_external_response_guard_closeout():
    assert guard_response(_external_response()).passed is False
    assert guard_external_model_response(_external_response()).passed is True

    blocked_cases = [
        _external_response(fake_response=True),
        _external_response(mode="fake"),
        _external_response(not_saved_by_default=False),
        _external_response(human_review_required=False),
        _external_response(
            validator_result=_validator_result(
                passed=False,
                blocked_terms=[],
                privacy_findings=["validator_failure"],
            )
        ),
        _external_response(content="This says buy now."),
        _external_response(content="This leaks api_key."),
    ]

    privacy_updates = [
        {"external_model_called": False},
        {"uses_ai_context_manifest_only": False},
        {"uses_holdings_line_items": True},
        {"uses_raw_provider_payloads": True},
        {"uses_raw_prompts": True},
        {"search_called": True},
        {"saved_by_default": True},
    ]
    for update in privacy_updates:
        response = _external_response()
        blocked_cases.append(
            response.model_copy(
                update={
                    "privacy_summary": response.privacy_summary.model_copy(
                        update=update
                    )
                }
            )
        )

    for response in blocked_cases:
        result = guard_external_model_response(response)
        assert result.passed is False, response


def test_adapter_external_path_closeout(monkeypatch):
    validator_calls: list[str] = []

    def _validator(content: str) -> AIMemoValidatorResult:
        validator_calls.append(content)
        return _validator_result()

    monkeypatch.setattr(
        "app_backend.services.deepseek_adapter.validate_external_ai_response_content",
        _validator,
    )
    transport = _SpyTransport()
    response = _network_adapter(transport).generate_external_response(_safe_request())

    assert validator_calls == ["Reference evidence only. Human review is required."]
    assert len(transport.calls) == 1
    assert response.external_model_called is True
    assert response.fake_response is False
    assert response.mode == "network"
    assert response.not_saved_by_default is True
    assert response.human_review_required is True
    assert response.privacy_summary.uses_ai_context_manifest_only is True
    assert response.privacy_summary.uses_raw_provider_payloads is False
    assert response.privacy_summary.uses_raw_prompts is False
    assert response.privacy_summary.uses_holdings_line_items is False
    assert response.privacy_summary.search_called is False
    assert response.privacy_summary.saved_by_default is False


def test_adapter_external_path_blocks_validator_failure(monkeypatch):
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
        _adapter(_SpyTransport()).generate_external_response(_safe_request())

    assert "validator_result_must_pass" in exc.value.findings


@pytest.mark.parametrize(
    "transport",
    [
        _SpyTransport(error_kind="timeout"),
        _SpyTransport(malformed=True),
    ],
)
def test_adapter_external_path_blocks_transport_error_or_malformed_response(transport):
    with pytest.raises(BlockedAdapterError):
        _adapter(transport).generate_external_response(_safe_request())


def test_adapter_external_path_request_guard_failure_does_not_call_transport():
    transport = _SpyTransport()
    with pytest.raises(BlockedAdapterError):
        _adapter(transport).generate_external_response(
            _safe_request(boundary_notices=[])
        )
    assert transport.calls == []


def test_adapter_external_path_runtime_policy_failure_does_not_call_transport():
    transport = _SpyTransport()
    with pytest.raises(BlockedAdapterError):
        _adapter(
            transport,
            policy=_happy_policy(single_request_user_approved=False),
        ).generate_external_response(_safe_request())
    assert transport.calls == []


def test_no_persistence_closeout_distinguishes_forbidden_tokens_from_save_behavior():
    dangerous_assignment_patterns = (
        r"\bsave_raw_prompt=True",
        r"\bsave_raw_response=True",
        r"(?<!not_)\bsaved_by_default=True",
        r"\bpersist_chat_by_default=True",
    )
    forbidden_persistence_paths = (
        "chat_history",
        "favorite_ai_output",
        "report_export_ai_output",
    )
    for file_path in STAGE_9_3_PRODUCTION_FILES:
        source = Path(file_path).read_text(encoding="utf-8")
        for pattern in dangerous_assignment_patterns:
            assert re.search(pattern, source) is None
        for token in forbidden_persistence_paths:
            assert token not in source

    response_fields = set(ExternalAIResponse.model_fields)
    assert "raw_prompt" not in response_fields
    assert "raw_response" not in response_fields
    assert "raw_provider_payload" not in response_fields


def test_no_financial_advice_expansion_in_forbidden_output_terms():
    expected_terms = {
        "buy",
        "sell",
        "add position",
        "reduce position",
        "clear position",
        "hedge",
        "rebalance",
        "target allocation",
        "target weight",
        "expected return",
        "predicted return",
        "future return",
        "market direction probability",
        "crash probability",
        "recession probability",
        "trade signal",
        "guaranteed",
        "will rise",
        "will fall",
    }

    assert expected_terms <= set(FORBIDDEN_RESPONSE_OUTPUT_TERMS)
    assert "return" not in FORBIDDEN_RESPONSE_OUTPUT_TERMS
