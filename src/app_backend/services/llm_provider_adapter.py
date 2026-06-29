"""Phase F4 provider adapter contracts for agent chat.

This module is a pure adapter layer. It does not read environment variables,
open files, create HTTP clients, or call the network directly. Real provider
I/O remains confined to the injected transport implementations.
"""
from __future__ import annotations

from typing import Any, Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field

from app_backend.schemas.ai_external import (
    DeepSeekTransportMessage,
    DeepSeekTransportRequest,
    DeepSeekTransportResponse,
    DeepSeekTransportToolCall,
)
from app_backend.services.deepseek_transport_contract import DeepSeekTransport


ProviderName = Literal["deepseek", "claude", "gpt"]
ChatMessageRole = Literal["system", "user", "assistant", "tool"]
FinishReason = Literal["stop", "tool_calls", "length", "content_filter"]


class ChatMessage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    role: ChatMessageRole
    content: str
    tool_call_id: str | None = None


class ToolCall(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    name: str
    arguments: dict[str, Any]


class TokenUsage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    input_tokens: int = Field(default=0, ge=0)
    output_tokens: int = Field(default=0, ge=0)
    total_tokens: int = Field(default=0, ge=0)


class ChatResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    content: str | None = None
    tool_calls: list[ToolCall] = Field(default_factory=list)
    usage: TokenUsage = Field(default_factory=TokenUsage)
    finish_reason: FinishReason = "stop"


class LLMProviderAdapter(Protocol):
    name: ProviderName

    def chat(
        self,
        *,
        model: str,
        messages: list[ChatMessage],
        tools: list[dict[str, Any]] | None = None,
        tool_choice: str = "auto",
        response_format: dict[str, Any] | None = None,
        max_tokens: int = 4000,
    ) -> ChatResponse:
        ...


class DeepSeekProviderAdapter:
    """DeepSeek provider adapter over an injected DeepSeekTransport."""

    name: Literal["deepseek"] = "deepseek"

    def __init__(self, *, transport: DeepSeekTransport) -> None:
        self._transport = transport

    def chat(
        self,
        *,
        model: str,
        messages: list[ChatMessage],
        tools: list[dict[str, Any]] | None = None,
        tool_choice: str = "auto",
        response_format: dict[str, Any] | None = None,
        max_tokens: int = 4000,
    ) -> ChatResponse:
        del model
        request = DeepSeekTransportRequest(
            request_id="phase_f_agent_chat",
            provider="deepseek",
            mode="network",
            messages=[
                _to_deepseek_message(message).model_dump(
                    mode="json",
                    exclude_none=True,
                )
                for message in messages
            ],
            boundary_notices=[
                "Phase F MacroBrief agent call.",
                "Human review is required.",
            ],
            validator_required=True,
            tools=tools,
            tool_choice=tool_choice,
            response_format=response_format,
            max_tokens=max_tokens,
        )
        response = self._transport.send(request)
        return _chat_response_from_transport(response)


def _to_deepseek_message(message: ChatMessage) -> DeepSeekTransportMessage:
    if message.role == "tool":
        return DeepSeekTransportMessage(
            role="tool",
            content=message.content,
            tool_call_id=message.tool_call_id,
        )
    return DeepSeekTransportMessage(role=message.role, content=message.content)


def _chat_response_from_transport(response: DeepSeekTransportResponse) -> ChatResponse:
    finish_reason: FinishReason
    if response.finish_reason in {"stop", "length", "content_filter", "tool_calls"}:
        finish_reason = response.finish_reason
    else:
        finish_reason = "stop"
    return ChatResponse(
        content=response.content_text,
        tool_calls=[_tool_call_from_transport(call) for call in response.tool_calls],
        usage=TokenUsage(
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
            total_tokens=response.usage.total_tokens,
        ),
        finish_reason=finish_reason,
    )


def _tool_call_from_transport(call: DeepSeekTransportToolCall) -> ToolCall:
    return ToolCall(id=call.id, name=call.name, arguments=dict(call.arguments))


class _NotImplementedProviderAdapter:
    name: ProviderName

    def chat(
        self,
        *,
        model: str,
        messages: list[ChatMessage],
        tools: list[dict[str, Any]] | None = None,
        tool_choice: str = "auto",
        response_format: dict[str, Any] | None = None,
        max_tokens: int = 4000,
    ) -> ChatResponse:
        del model, messages, tools, tool_choice, response_format, max_tokens
        raise NotImplementedError(f"{self.name} provider is not wired in Phase F")


class ClaudeProviderAdapter(_NotImplementedProviderAdapter):
    name: Literal["claude"] = "claude"


class GPTProviderAdapter(_NotImplementedProviderAdapter):
    name: Literal["gpt"] = "gpt"


__all__ = [
    "ChatMessage",
    "ChatMessageRole",
    "ChatResponse",
    "ClaudeProviderAdapter",
    "DeepSeekProviderAdapter",
    "FinishReason",
    "GPTProviderAdapter",
    "LLMProviderAdapter",
    "ProviderName",
    "TokenUsage",
    "ToolCall",
]
