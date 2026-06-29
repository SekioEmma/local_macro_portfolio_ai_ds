from __future__ import annotations

from app_backend.schemas.ai_external import (
    DeepSeekTransportRequest,
    DeepSeekTransportResponse,
)
from app_backend.services.llm_provider_adapter import (
    ChatMessage,
    ChatResponse,
    DeepSeekProviderAdapter,
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
    assert response.usage == TokenUsage()
    assert response.finish_reason == "stop"
    assert len(transport.calls) == 1
    call = transport.calls[0]
    assert call.provider == "deepseek"
    assert call.mode == "network"
    assert [message.role for message in call.messages] == [
        "system",
        "summary",
        "context",
    ]
    assert call.messages[-1].content == '{"status":"ok"}'


def test_chat_response_schema_defaults_are_agent_safe():
    response = ChatResponse(content=None)

    assert response.tool_calls == []
    assert response.usage.total_tokens == 0
    assert response.finish_reason == "stop"
