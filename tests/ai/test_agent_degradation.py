from __future__ import annotations

from datetime import date
from typing import Any

from app_backend.services.agent_runtime import ToolDisabled, run_agent
from app_backend.services.agent_tool_registry import FINALIZE_TOOL_NAME, AgentToolRegistry, ToolSpec, make_finalize_macro_brief_tool
from app_backend.services.llm_provider_adapter import ChatResponse, ToolCall
from tests.ai.test_agent_runtime_mocked import MockProvider, finalize_call


def _tool_names() -> list[str]:
    return ["unstable_tool", FINALIZE_TOOL_NAME]


def _failing_registry(calls: list[dict[str, Any]]) -> AgentToolRegistry:
    registry = AgentToolRegistry()

    def unstable_handler(args: dict[str, Any]) -> dict[str, Any]:
        calls.append(args)
        raise RuntimeError("simulated tool failure")

    registry.register(
        ToolSpec(
            name="unstable_tool",
            description="Mock unstable tool.",
            parameters_schema={"type": "object", "properties": {}, "required": [], "additionalProperties": True},
            handler=unstable_handler,
        )
    )
    registry.register(make_finalize_macro_brief_tool())
    return registry


def _tool_names_from_call(call: dict[str, Any]) -> list[str]:
    return [tool["function"]["name"] for tool in call["tools"]]


def test_tool_disabled_exception_carries_tool_name():
    error = ToolDisabled("search_tavily")

    assert error.name == "search_tavily"


def test_single_tool_failure_returns_tool_message_and_continues():
    calls: list[dict[str, Any]] = []
    provider = MockProvider(
        [
            ChatResponse(
                tool_calls=[ToolCall(id="unstable-1", name="unstable_tool", arguments={"try": 1})],
                finish_reason="tool_calls",
            ),
            ChatResponse(tool_calls=[finalize_call()], finish_reason="tool_calls"),
        ]
    )

    result = run_agent(
        session_id="degrade-single",
        user_question="Build a macro brief.",
        provider=provider,
        tool_registry=_failing_registry(calls),
        current_date=date(2026, 6, 30),
        tool_names=_tool_names(),
    )

    assert result.final_status == "ok"
    assert calls == [{"try": 1}]
    assert any("handler_exception" in message.content for message in provider.calls[1]["messages"] if message.role == "tool")


def test_tool_is_disabled_after_three_consecutive_errors():
    calls: list[dict[str, Any]] = []
    provider = MockProvider(
        [
            ChatResponse(
                tool_calls=[ToolCall(id="unstable-1", name="unstable_tool", arguments={"try": 1})],
                finish_reason="tool_calls",
            ),
            ChatResponse(
                tool_calls=[ToolCall(id="unstable-2", name="unstable_tool", arguments={"try": 2})],
                finish_reason="tool_calls",
            ),
            ChatResponse(
                tool_calls=[ToolCall(id="unstable-3", name="unstable_tool", arguments={"try": 3})],
                finish_reason="tool_calls",
            ),
            ChatResponse(tool_calls=[finalize_call()], finish_reason="tool_calls"),
        ]
    )

    result = run_agent(
        session_id="degrade-disable",
        user_question="Build a macro brief.",
        provider=provider,
        tool_registry=_failing_registry(calls),
        current_date=date(2026, 6, 30),
        tool_names=_tool_names(),
    )

    assert result.final_status == "ok"
    assert calls == [{"try": 1}, {"try": 2}, {"try": 3}]
    assert any(warning.code == "tool_disabled:unstable_tool" for warning in result.warnings)
    assert "unstable_tool" not in _tool_names_from_call(provider.calls[3])
    assert FINALIZE_TOOL_NAME in _tool_names_from_call(provider.calls[3])


def test_unknown_tool_uses_error_channel_and_continues():
    registry = AgentToolRegistry()
    registry.register(make_finalize_macro_brief_tool())
    provider = MockProvider(
        [
            ChatResponse(
                tool_calls=[ToolCall(id="unknown-1", name="missing_tool", arguments={})],
                finish_reason="tool_calls",
            ),
            ChatResponse(tool_calls=[finalize_call()], finish_reason="tool_calls"),
        ]
    )

    result = run_agent(
        session_id="degrade-unknown",
        user_question="Build a macro brief.",
        provider=provider,
        tool_registry=registry,
        current_date=date(2026, 6, 30),
        tool_names=["missing_tool", FINALIZE_TOOL_NAME],
    )

    assert result.final_status == "ok"
    assert any("unknown_tool" in message.content for message in provider.calls[1]["messages"] if message.role == "tool")
