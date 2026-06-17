"""Stage 9.3-B-2a DeepSeek mocked transport adapter regression tests.

This stage wires the adapter seam through an injected mocked transport only.
There is no real HTTP transport, no API key read, no env read, and no new
endpoint.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from app_backend.schemas.ai_external import (
    DeepSeekTransportRequest,
    DeepSeekTransportResponse,
    ExternalAIAdapterConfig,
    ExternalAIRequest,
    ExternalAIRuntimePolicy,
)
from app_backend.services.ai_external_adapter import BlockedAdapterError
from app_backend.services.deepseek_adapter import (
    DeepSeekNetworkAdapter,
    fake_only_config,
    mocked_transport_only_config,
)
from app_backend.services.deepseek_transport_contract import (
    DeepSeekTransportError,
    MockDeepSeekTransport,
)


def _valid_request(**overrides) -> ExternalAIRequest:
    base = dict(
        request_id="req-mocked-001",
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


def _happy_path_policy(**overrides) -> ExternalAIRuntimePolicy:
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


class SpyTransport:
    def __init__(self, response: DeepSeekTransportResponse | None = None) -> None:
        self.calls: list[DeepSeekTransportRequest] = []
        self._response = response

    def send(self, request: DeepSeekTransportRequest) -> DeepSeekTransportResponse:
        self.calls.append(request)
        if self._response is not None:
            return self._response
        return DeepSeekTransportResponse(
            request_id=request.request_id,
            provider=request.provider,
            mode=request.mode,
            content_text=(
                "Mocked transport reply. Reference evidence only. "
                "Not an action directive. Human review is required."
            ),
        )


class MalformedTransport:
    def send(self, request: DeepSeekTransportRequest):  # noqa: ANN001
        return {"content_text": "not a schema object"}


def test_default_disabled_adapter_does_not_touch_transport():
    transport = SpyTransport()
    adapter = DeepSeekNetworkAdapter(
        transport=transport,
        runtime_policy=_happy_path_policy(),
    )

    with pytest.raises(BlockedAdapterError) as exc:
        adapter.generate(_valid_request())

    assert "adapter_disabled_in_stage_9_3_a" in exc.value.findings
    assert transport.calls == []


def test_mocked_transport_config_is_disabled_by_default():
    cfg = mocked_transport_only_config()
    assert cfg.enabled is False
    assert cfg.mode == "disabled"
    assert cfg.allow_network is False


def test_missing_transport_fails_closed():
    adapter = DeepSeekNetworkAdapter(
        config=fake_only_config(),
        runtime_policy=_happy_path_policy(),
    )

    with pytest.raises(BlockedAdapterError) as exc:
        adapter.generate(_valid_request())

    assert "missing_transport" in exc.value.findings


def test_runtime_policy_failure_does_not_touch_transport():
    transport = SpyTransport()
    adapter = DeepSeekNetworkAdapter(
        config=fake_only_config(),
        transport=transport,
        runtime_policy=_happy_path_policy(single_request_user_approved=False),
    )

    with pytest.raises(BlockedAdapterError) as exc:
        adapter.generate(_valid_request())

    assert "missing_single_request_user_approval" in exc.value.findings
    assert transport.calls == []


def test_guard_request_failure_does_not_touch_transport():
    transport = SpyTransport()
    adapter = DeepSeekNetworkAdapter(
        config=fake_only_config(),
        transport=transport,
        runtime_policy=_happy_path_policy(),
    )

    with pytest.raises(BlockedAdapterError) as exc:
        adapter.generate(_valid_request(boundary_notices=[]))

    assert "missing_boundary_notices" in exc.value.findings
    assert transport.calls == []


def test_network_mode_request_is_blocked_by_guard_request():
    transport = SpyTransport()
    adapter = DeepSeekNetworkAdapter(
        config=fake_only_config(),
        transport=transport,
        runtime_policy=_happy_path_policy(),
    )

    with pytest.raises(BlockedAdapterError) as exc:
        adapter.generate(_valid_request(mode="network"))

    assert "mode_network_blocked_in_stage_9_3_a" in exc.value.findings
    assert transport.calls == []


def test_network_mode_config_remains_blocked_at_adapter_init():
    cfg = ExternalAIAdapterConfig(
        provider="deepseek",
        enabled=True,
        mode="network",
        allow_network=False,
        requires_user_switch=True,
        requires_context_preview=True,
        requires_validator=True,
        save_raw_prompt=False,
        save_raw_response=False,
    )

    with pytest.raises(BlockedAdapterError):
        DeepSeekNetworkAdapter(config=cfg)


def test_happy_path_returns_guarded_external_ai_response():
    transport = SpyTransport()
    adapter = DeepSeekNetworkAdapter(
        config=fake_only_config(),
        transport=transport,
        runtime_policy=_happy_path_policy(),
    )

    response = adapter.generate(_valid_request())

    assert response.provider == "deepseek"
    assert response.mode == "fake"
    assert response.fake_response is True
    assert response.external_model_called is False
    assert response.privacy_summary.external_model_called is False
    assert response.privacy_summary.uses_ai_context_manifest_only is True
    assert response.privacy_summary.uses_raw_provider_payloads is False
    assert response.privacy_summary.uses_raw_prompts is False
    assert response.not_saved_by_default is True
    assert response.human_review_required is True
    assert response.validator_result.passed is True
    assert "human review is required" in response.content.lower()
    assert len(transport.calls) == 1
    assert transport.calls[0].request_id == "req-mocked-001"


@pytest.mark.parametrize("kind", ["timeout", "http_error", "malformed"])
def test_transport_error_kinds_fail_closed(kind):
    adapter = DeepSeekNetworkAdapter(
        config=fake_only_config(),
        transport=MockDeepSeekTransport(forced_error_kind=kind),
        runtime_policy=_happy_path_policy(),
    )

    with pytest.raises(BlockedAdapterError) as exc:
        adapter.generate(_valid_request())

    assert f"transport_error_{kind}" in exc.value.findings


def test_unexpected_transport_exception_fails_closed_without_detail_leak():
    class ExplodingTransport:
        def send(self, request: DeepSeekTransportRequest) -> DeepSeekTransportResponse:
            raise RuntimeError("raw provider payload should not leak")

    adapter = DeepSeekNetworkAdapter(
        config=fake_only_config(),
        transport=ExplodingTransport(),
        runtime_policy=_happy_path_policy(),
    )

    with pytest.raises(BlockedAdapterError) as exc:
        adapter.generate(_valid_request())

    assert exc.value.findings == ["transport_unknown_error"]
    assert "raw provider payload" not in str(exc.value).lower()


def test_malformed_transport_response_fails_closed():
    adapter = DeepSeekNetworkAdapter(
        config=fake_only_config(),
        transport=MalformedTransport(),
        runtime_policy=_happy_path_policy(),
    )

    with pytest.raises(BlockedAdapterError) as exc:
        adapter.generate(_valid_request())

    assert "transport_malformed_response" in exc.value.findings


def test_provider_response_with_forbidden_output_term_is_blocked():
    adapter = DeepSeekNetworkAdapter(
        config=fake_only_config(),
        transport=MockDeepSeekTransport(content_text="This says buy now."),
        runtime_policy=_happy_path_policy(),
    )

    with pytest.raises(BlockedAdapterError) as exc:
        adapter.generate(_valid_request())

    assert any("forbidden_response_term" in f for f in exc.value.findings)


def test_provider_response_with_privacy_token_is_blocked():
    adapter = DeepSeekNetworkAdapter(
        config=fake_only_config(),
        transport=MockDeepSeekTransport(content_text="api_key should never appear."),
        runtime_policy=_happy_path_policy(),
    )

    with pytest.raises(BlockedAdapterError) as exc:
        adapter.generate(_valid_request())

    assert any("forbidden_response_privacy_token" in f for f in exc.value.findings)


def test_raw_prompt_and_raw_response_are_not_response_fields():
    response = DeepSeekNetworkAdapter(
        config=fake_only_config(),
        transport=SpyTransport(),
        runtime_policy=_happy_path_policy(),
    ).generate(_valid_request())

    dumped = response.model_dump()
    assert "raw_prompt" not in dumped
    assert "raw_response" not in dumped
    assert response.privacy_summary.uses_raw_prompts is False
    assert response.privacy_summary.uses_raw_provider_payloads is False


def test_transport_request_schema_rejects_key_url_endpoint_model_and_raw_fields():
    request = _valid_request()
    response = DeepSeekNetworkAdapter(
        config=fake_only_config(),
        transport=SpyTransport(),
        runtime_policy=_happy_path_policy(),
    ).generate(request)
    assert response.validator_result.passed is True

    schema_fields = set(DeepSeekTransportRequest.model_fields)
    forbidden = {
        "api_key",
        "api_key_env",
        "base_url",
        "endpoint",
        "model",
        "model_name",
        "raw_prompt",
        "raw_response",
        "holdings_line_items",
        "account_values",
        "position_weights",
        "transaction_history",
        "local_path",
    }
    assert schema_fields.isdisjoint(forbidden)


def test_no_new_routes_after_mocked_transport_adapter():
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
        "deepseek_adapter",
        "DeepSeekNetworkAdapter",
        "deepseek_transport_contract",
        "DeepSeekTransport",
        "ai_external_runtime_policy",
        "build_deepseek_provider_payload",
    ],
)
def test_stage9_2_files_still_do_not_import_adapter_transport_policy_or_builder(
    file_path, forbidden
):
    source = Path(file_path).read_text(encoding="utf-8")
    assert forbidden not in source


@pytest.mark.parametrize(
    "file_path",
    [
        "src/app_backend/services/deepseek_adapter.py",
        "src/app_backend/services/deepseek_transport_contract.py",
    ],
)
@pytest.mark.parametrize(
    "forbidden",
    [
        "import httpx",
        "import requests",
        "import aiohttp",
        "from httpx",
        "from requests",
        "from aiohttp",
        "urllib.request",
        "socket.create_connection",
        "os.environ",
        "os.getenv",
        "DEEPSEEK_API_KEY",
        "api.deepseek",
        "deepseek.com",
    ],
)
def test_mocked_adapter_and_transport_have_no_real_network_or_env_surface(
    file_path, forbidden
):
    source = Path(file_path).read_text(encoding="utf-8")
    assert forbidden not in source

