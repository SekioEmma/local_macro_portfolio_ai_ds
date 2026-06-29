from __future__ import annotations

import pytest

from app_backend.schemas.ai_external import (
    DeepSeekTransportRequest,
    DeepSeekTransportResponse,
    DeepSeekTransportToolCall,
    DeepSeekTransportUsage,
)
from app_backend.services.llm_provider_adapter import (
    ChatMessage,
    ChatResponse,
    ClaudeProviderAdapter,
    DeepSeekProviderAdapter,
    GPTProviderAdapter,
    TokenUsage,
)


class SpyTransport:
    def __init__(self) -> None:
        self.calls: list[DeepSeekTransportRequest] = []

    def send(self, request: DeepSeekTransportRequest) -> DeepSeekTransportResponse:
        self.calls.append(request)
        return DeepSeekTransportResponse(
            request_id=request.request_id,
            provider=request.provider,
            mode=request.mode,
            content_text="Reference evidence only. Human review is required.",
            finish_reason="stop",
            usage=DeepSeekTransportUsage(
                input_tokens=10,
                output_tokens=20,
                total_tokens=30,
            ),
        )


def test_deepseek_provider_adapter_maps_chat_to_transport_request():
    transport = SpyTransport()
    adapter = DeepSeekProviderAdapter(transport=transport)

    response = adapter.chat(
        model="deepseek-v4-pro",
        messages=[
            ChatMessage(role="system", content="system rules"),
            ChatMessage(role="user", content="user question"),
            ChatMessage(role="tool", content='{"status":"ok"}', tool_call_id="call_1"),
        ],
        tools=[{"type": "function", "function": {"name": "finalize_macro_brief"}}],
        tool_choice="auto",
        response_format={"type": "json_object"},
        max_tokens=1024,
    )

    assert isinstance(response, ChatResponse)
    assert response.content == "Reference evidence only. Human review is required."
    assert response.tool_calls == []
    assert response.usage == TokenUsage(input_tokens=10, output_tokens=20, total_tokens=30)
    assert response.finish_reason == "stop"
    assert len(transport.calls) == 1
    call = transport.calls[0]
    assert call.provider == "deepseek"
    assert call.mode == "network"
    assert [message.role for message in call.messages] == ["system", "user", "tool"]
    assert call.messages[-1].content == '{"status":"ok"}'
    assert call.messages[-1].tool_call_id == "call_1"
    assert call.tools == [{"type": "function", "function": {"name": "finalize_macro_brief"}}]
    assert call.tool_choice == "auto"
    assert call.response_format == {"type": "json_object"}
    assert call.max_tokens == 1024


def test_chat_response_schema_defaults_are_agent_safe():
    response = ChatResponse(content=None)

    assert response.tool_calls == []
    assert response.usage.total_tokens == 0
    assert response.finish_reason == "stop"


def test_deepseek_provider_adapter_maps_transport_tool_calls():
    class ToolCallTransport(SpyTransport):
        def send(self, request: DeepSeekTransportRequest) -> DeepSeekTransportResponse:
            self.calls.append(request)
            return DeepSeekTransportResponse(
                request_id=request.request_id,
                provider=request.provider,
                mode=request.mode,
                content_text="",
                finish_reason="tool_calls",
                tool_calls=[
                    DeepSeekTransportToolCall(
                        id="call_1",
                        name="dashboard_query",
                        arguments={"module_key": "rate_pressure"},
                    )
                ],
            )

    response = DeepSeekProviderAdapter(transport=ToolCallTransport()).chat(
        model="deepseek-v4-pro",
        messages=[ChatMessage(role="user", content="x")],
    )

    assert response.content == ""
    assert response.finish_reason == "tool_calls"
    assert response.tool_calls[0].id == "call_1"
    assert response.tool_calls[0].name == "dashboard_query"
    assert response.tool_calls[0].arguments == {"module_key": "rate_pressure"}


def test_claude_and_gpt_adapters_are_unwired_skeletons():
    for adapter in (ClaudeProviderAdapter(), GPTProviderAdapter()):
        with pytest.raises(NotImplementedError, match="not wired in Phase F"):
            adapter.chat(
                model="future-model",
                messages=[ChatMessage(role="user", content="x")],
            )
