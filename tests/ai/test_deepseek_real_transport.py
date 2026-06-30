"""Stage 9.3-B-2b real DeepSeek transport contract tests.

These tests use monkeypatches and mocked HTTP callables only. They never call
the live provider, never read local config files, and never persist raw prompt
or response material.
"""
from __future__ import annotations

import builtins
import inspect
import json
import socket
import urllib.error
import urllib.request
from pathlib import Path

import pytest

from app_backend.schemas.ai_external import (
    DeepSeekProviderMessage,
    DeepSeekTransportRequest,
    DeepSeekTransportResponse,
)
from app_backend.services.deepseek_real_transport import (
    DeepSeekRealTransport,
    load_deepseek_api_key_from_env,
)
from app_backend.services.deepseek_transport_contract import (
    DeepSeekTransport,
    DeepSeekTransportError,
)

_REPO_ROOT = Path(__file__).resolve().parents[2]


def _transport_request() -> DeepSeekTransportRequest:
    return DeepSeekTransportRequest(
        request_id="req-real-001",
        provider="deepseek",
        mode="fake",
        messages=[
            DeepSeekProviderMessage(
                role="system",
                content="Local-first macro context. Not an action directive.",
            ),
            DeepSeekProviderMessage(
                role="summary",
                content="Sanitized intent summary.",
            ),
            DeepSeekProviderMessage(
                role="context",
                content="2 facts and 1 model output included.",
            ),
        ],
        boundary_notices=["Reference evidence only.", "Human review is required."],
        validator_required=True,
    )


class _Response:
    def __init__(self, status: int, payload) -> None:  # noqa: ANN001
        self.status = status
        self._raw = json.dumps(payload).encode("utf-8")

    def read(self, max_bytes: int = -1) -> bytes:
        if max_bytes == -1:
            return self._raw
        return self._raw[:max_bytes]


def test_missing_deepseek_api_key_fails_closed(monkeypatch):
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)

    with pytest.raises(DeepSeekTransportError) as exc:
        load_deepseek_api_key_from_env()

    assert exc.value.kind == "missing_key"
    assert "DEEPSEEK_API_KEY" not in str(exc.value)


def test_blank_deepseek_api_key_fails_closed(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "   ")

    with pytest.raises(DeepSeekTransportError) as exc:
        load_deepseek_api_key_from_env()

    assert exc.value.kind == "missing_key"


def test_api_key_does_not_appear_in_exception_response_or_schema(monkeypatch):
    secret = "sk_live_TEST_SECRET_SHOULD_NOT_LEAK"

    def _raise_http_error(request: urllib.request.Request, timeout: float):  # noqa: ANN001
        raise urllib.error.HTTPError(
            url=request.full_url,
            code=500,
            msg=f"provider exploded with {secret}",
            hdrs=None,
            fp=None,
        )

    transport = DeepSeekRealTransport(api_key=secret, opener=_raise_http_error)

    with pytest.raises(DeepSeekTransportError) as exc:
        transport.send(_transport_request())

    assert secret not in str(exc.value)
    assert secret not in exc.value.detail
    assert secret not in _transport_request().model_dump_json()

    response = DeepSeekTransportResponse(
        request_id="r",
        provider="deepseek",
        mode="fake",
        content_text="ok",
    )
    assert secret not in response.model_dump_json()


def test_no_local_config_file_is_read(monkeypatch):
    opened: list[str] = []
    original_open = builtins.open

    def _recording_open(file, *args, **kwargs):  # noqa: ANN001
        opened.append(str(file))
        return original_open(file, *args, **kwargs)

    monkeypatch.setattr(builtins, "open", _recording_open)

    transport = DeepSeekRealTransport(
        api_key="test-key",
        opener=lambda request, timeout: _Response(
            200,
            {
                "choices": [
                    {
                        "message": {"content": "Reference only."},
                        "finish_reason": "stop",
                    }
                ]
            },
        ),
    )
    response = transport.send(_transport_request())

    assert response.content_text == "Reference only."
    assert not any(path.endswith(".env") for path in opened)
    assert not any("external_llm.yaml" in path for path in opened)


def test_constructing_real_transport_does_not_call_network_or_read_env(monkeypatch):
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    calls: list[str] = []

    def _opener(request: urllib.request.Request, timeout: float):  # noqa: ANN001
        calls.append(request.full_url)
        return _Response(200, {"choices": [{"message": {"content": "ok"}}]})

    DeepSeekRealTransport(opener=_opener)

    assert calls == []


def test_request_schema_excludes_secret_endpoint_model_and_raw_fields():
    fields = set(DeepSeekTransportRequest.model_fields)
    forbidden = {
        "api_key",
        "api_key_env",
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
    assert fields.isdisjoint(forbidden)


def test_real_transport_implements_transport_protocol():
    assert isinstance(DeepSeekRealTransport(api_key="test-key"), DeepSeekTransport)


def test_mocked_http_success_maps_to_transport_response():
    seen_body: dict | None = None
    seen_headers: dict[str, str] = {}

    def _opener(request: urllib.request.Request, timeout: float):  # noqa: ANN001
        nonlocal seen_body, seen_headers
        seen_body = json.loads(request.data.decode("utf-8"))
        seen_headers = dict(request.header_items())
        return _Response(
            200,
            {
                "choices": [
                    {
                        "message": {
                            "content": (
                                "Reference evidence only. Human review is required."
                            )
                        },
                        "finish_reason": "stop",
                    }
                ]
            },
        )

    response = DeepSeekRealTransport(
        api_key="test-key",
        opener=_opener,
    ).send(_transport_request())

    assert response.request_id == "req-real-001"
    assert response.provider == "deepseek"
    assert response.mode == "fake"
    assert response.finish_reason == "stop"
    assert "human review is required" in response.content_text.lower()
    assert seen_body is not None
    assert seen_body["stream"] is False
    assert seen_body["max_tokens"] == 2_400
    assert all(item["role"] in {"system", "user"} for item in seen_body["messages"])
    assert "Authorization" in seen_headers
    assert "test-key" not in response.model_dump_json()


def test_real_transport_serializes_tools_and_response_format():
    seen_body: dict | None = None

    request = _transport_request()
    request = request.model_copy(
        update={
            "tools": [
                {
                    "type": "function",
                    "function": {
                        "name": "finalize_macro_brief",
                        "parameters": {"type": "object"},
                    },
                }
            ],
            "tool_choice": "auto",
            "response_format": {"type": "json_object"},
            "max_tokens": 4096,
        }
    )

    def _opener(http_request: urllib.request.Request, timeout: float):  # noqa: ANN001
        nonlocal seen_body
        seen_body = json.loads(http_request.data.decode("utf-8"))
        return _Response(
            200,
            {
                "choices": [
                    {
                        "message": {"content": "ok"},
                        "finish_reason": "stop",
                    }
                ]
            },
        )

    DeepSeekRealTransport(api_key="test-key", opener=_opener).send(request)

    assert seen_body is not None
    assert seen_body["tools"][0]["function"]["name"] == "finalize_macro_brief"
    assert seen_body["tool_choice"] == "auto"
    assert seen_body["response_format"] == {"type": "json_object"}
    assert seen_body["max_tokens"] == 4096


def test_real_transport_parses_tool_calls_and_usage():
    response = DeepSeekRealTransport(
        api_key="test-key",
        opener=lambda request, timeout: _Response(
            200,
            {
                "choices": [
                    {
                        "message": {
                            "content": None,
                            "tool_calls": [
                                {
                                    "id": "call_1",
                                    "type": "function",
                                    "function": {
                                        "name": "dashboard_query",
                                        "arguments": "{\"module_key\":\"rate_pressure\"}",
                                    },
                                }
                            ],
                        },
                        "finish_reason": "tool_calls",
                    }
                ],
                "usage": {
                    "prompt_tokens": 12,
                    "completion_tokens": 8,
                    "total_tokens": 20,
                },
            },
        ),
    ).send(_transport_request())

    assert response.content_text == ""
    assert response.finish_reason == "tool_calls"
    assert response.tool_calls[0].id == "call_1"
    assert response.tool_calls[0].name == "dashboard_query"
    assert response.tool_calls[0].arguments == {"module_key": "rate_pressure"}
    assert response.usage.input_tokens == 12
    assert response.usage.output_tokens == 8
    assert response.usage.total_tokens == 20


def test_real_transport_tool_call_bad_arguments_degrades_to_empty_args():
    response = DeepSeekRealTransport(
        api_key="test-key",
        opener=lambda request, timeout: _Response(
            200,
            {
                "choices": [
                    {
                        "message": {
                            "tool_calls": [
                                {
                                    "id": "call_1",
                                    "function": {
                                        "name": "dashboard_query",
                                        "arguments": "{not-json",
                                    },
                                }
                            ]
                        },
                        "finish_reason": "tool_calls",
                    }
                ]
            },
        ),
    ).send(_transport_request())

    assert response.tool_calls[0].arguments == {}


def test_mocked_timeout_fails_closed():
    def _timeout(request: urllib.request.Request, timeout: float):  # noqa: ANN001
        raise socket.timeout("provider took too long")

    with pytest.raises(DeepSeekTransportError) as exc:
        DeepSeekRealTransport(api_key="test-key", opener=_timeout).send(
            _transport_request()
        )

    assert exc.value.kind == "timeout"
    assert "provider took too long" not in exc.value.detail


def test_mocked_non_2xx_fails_closed():
    with pytest.raises(DeepSeekTransportError) as exc:
        DeepSeekRealTransport(
            api_key="test-key",
            opener=lambda request, timeout: _Response(503, {"raw": "secret"}),
        ).send(_transport_request())

    assert exc.value.kind == "http_error"
    assert exc.value.detail == "provider_http_status_503"


def test_mocked_malformed_json_fails_closed():
    class _BadJsonResponse:
        status = 200

        def read(self, max_bytes: int = -1) -> bytes:
            return b"{not-json"

    with pytest.raises(DeepSeekTransportError) as exc:
        DeepSeekRealTransport(
            api_key="test-key",
            opener=lambda request, timeout: _BadJsonResponse(),
        ).send(_transport_request())

    assert exc.value.kind == "malformed"
    assert exc.value.detail == "provider_response_not_json"


@pytest.mark.parametrize(
    "payload,detail",
    [
        ({}, "provider_response_missing_choices"),
        ({"choices": []}, "provider_response_missing_choices"),
        ({"choices": [{"message": {}}]}, "provider_response_missing_content"),
        ({"choices": [{"message": {"content": "   "}}]}, "provider_response_missing_content"),
    ],
)
def test_mocked_missing_content_fails_closed(payload, detail):
    with pytest.raises(DeepSeekTransportError) as exc:
        DeepSeekRealTransport(
            api_key="test-key",
            opener=lambda request, timeout: _Response(200, payload),
        ).send(_transport_request())

    assert exc.value.kind == "malformed"
    assert exc.value.detail == detail


def test_provider_refusal_fails_closed():
    with pytest.raises(DeepSeekTransportError) as exc:
        DeepSeekRealTransport(
            api_key="test-key",
            opener=lambda request, timeout: _Response(
                200,
                {"choices": [{"message": {"refusal": "cannot comply"}}]},
            ),
        ).send(_transport_request())

    assert exc.value.kind == "provider_refusal"
    assert exc.value.detail == "provider_refusal"


def test_raw_provider_payload_does_not_leak_to_error_detail():
    secret_payload = {"choices": [{"message": {"content": ""}}], "raw": "SECRET"}

    with pytest.raises(DeepSeekTransportError) as exc:
        DeepSeekRealTransport(
            api_key="test-key",
            opener=lambda request, timeout: _Response(200, secret_payload),
        ).send(_transport_request())

    assert "SECRET" not in exc.value.detail
    assert "choices" not in exc.value.detail


def test_forbidden_routes_remain_absent_after_real_transport_added():
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
        str(_REPO_ROOT / "src/app_backend/main.py"),
        str(_REPO_ROOT / "src/app_backend/services/ai_preview_service.py"),
        str(_REPO_ROOT / "src/app_backend/services/ai_memo_renderer.py"),
        str(_REPO_ROOT / "src/app_backend/services/ai_context_service.py"),
    ],
)
@pytest.mark.parametrize(
    "forbidden",
    [
        "deepseek_real_transport",
        "DeepSeekRealTransport",
        "deepseek_adapter",
        "DeepSeekNetworkAdapter",
        "deepseek_transport_contract",
        "DeepSeekTransport",
        "ai_external_runtime_policy",
        "build_deepseek_provider_payload",
    ],
)
def test_stage9_2_files_do_not_import_real_transport_adapter_policy_or_builder(
    file_path,
    forbidden,
):
    source = Path(file_path).read_text(encoding="utf-8")
    assert forbidden not in source


@pytest.mark.parametrize(
    "file_path",
    [
        str(_REPO_ROOT / "src/app_backend/services/deepseek_adapter.py"),
        str(_REPO_ROOT / "src/app_backend/services/deepseek_transport_contract.py"),
        str(_REPO_ROOT / "src/app_backend/services/deepseek_provider_contract.py"),
        str(_REPO_ROOT / "src/app_backend/services/ai_external_runtime_policy.py"),
        str(_REPO_ROOT / "src/app_backend/services/ai_external_request_builder.py"),
    ],
)
@pytest.mark.parametrize(
    "forbidden",
    [
        "os.environ",
        "os.getenv",
        "import httpx",
        "import requests",
        "import aiohttp",
        "urllib.request",
        "api.deepseek",
        "deepseek.com",
    ],
)
def test_only_real_transport_module_has_env_or_real_http_surface(file_path, forbidden):
    source = Path(file_path).read_text(encoding="utf-8")
    assert forbidden not in source


def test_real_transport_env_read_occurs_only_in_loader_function():
    import app_backend.services.deepseek_real_transport as module

    source = (_REPO_ROOT / "src/app_backend/services/deepseek_real_transport.py").read_text(
        encoding="utf-8"
    )
    assert source.count("os.environ") == 1
    loader_source = inspect.getsource(module.load_deepseek_api_key_from_env)
    assert "os.environ" in loader_source


def test_no_production_file_loads_local_env_or_yaml():
    production_files = [
        str(_REPO_ROOT / "src/app_backend/services/deepseek_real_transport.py"),
        str(_REPO_ROOT / "src/app_backend/services/deepseek_adapter.py"),
        str(_REPO_ROOT / "src/app_backend/services/deepseek_transport_contract.py"),
        str(_REPO_ROOT / "src/app_backend/services/deepseek_provider_contract.py"),
        str(_REPO_ROOT / "src/app_backend/services/ai_external_runtime_policy.py"),
    ]
    forbidden = ("open('.env'", 'open(".env"', "dotenv", "external_llm.yaml")
    for file_path in production_files:
        source = Path(file_path).read_text(encoding="utf-8")
        for token in forbidden:
            assert token not in source
