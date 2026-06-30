from __future__ import annotations

from datetime import date
from typing import Any

from app_backend.schemas.macro_brief import REQUIRED_BOUNDARY_KEYWORDS, REQUIRED_MODULE_KEYS
from app_backend.services.agent_runtime import AgentBudget, AgentRuntimeConfig, run_agent
from app_backend.services.agent_tool_registry import (
    FINALIZE_TOOL_NAME,
    AgentToolRegistry,
    ToolSpec,
    make_finalize_macro_brief_tool,
)
from app_backend.services.llm_provider_adapter import ChatMessage, ChatResponse, ToolCall


class MockProvider:
    name = "deepseek"

    def __init__(self, responses: list[ChatResponse]) -> None:
        self.responses = responses
        self.calls: list[dict[str, Any]] = []

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
        self.calls.append(
            {
                "model": model,
                "messages": list(messages),
                "tools": list(tools or []),
                "tool_choice": tool_choice,
                "response_format": response_format,
                "max_tokens": max_tokens,
            }
        )
        if not self.responses:
            return ChatResponse(content="no more mocked responses")
        return self.responses.pop(0)


def brief_payload() -> dict[str, Any]:
    return {
        "core_conclusion": "Macro environment remains balanced.",
        "market_state": [
            {"symbol": symbol, "price": 400.0, "change_pct": 0.1, "as_of": "2026-06-28"}
            for symbol in ("SPY", "QQQ", "SHY", "GLD")
        ],
        "confirmed_facts": [
            {
                "id": "f1",
                "statement": "DGS10 remained elevated.",
                "value": 4.3,
                "unit": "%",
                "source_id": "s1",
                "as_of": "2026-06-27",
            },
            {
                "id": "f2",
                "statement": "HY OAS stayed inside a watch range.",
                "value": 3.1,
                "unit": "%",
                "source_id": "s2",
                "as_of": "2026-06-27",
            },
        ],
        "judgments": [
            {
                "claim": "Rate pressure is still the main transmission channel.",
                "evidence_supports": ["f1"],
            }
        ],
        "module_table": [
            {"module_key": key, "module_name_zh": key, "status": "watch", "note": None}
            for key in REQUIRED_MODULE_KEYS
        ],
        "risk_assessment": {
            "current_label": "watch",
            "summary": "Risks are balanced but data-sensitive.",
            "upgrade_triggers": ["HY OAS widens materially"],
            "downgrade_triggers": ["Inflation and yields cool together"],
        },
        "forward_indicators": [
            {"name": f"indicator_{idx}", "release_date": "2026-07-11", "relevance": "next data point"}
            for idx in range(5)
        ],
        "scenarios": {
            "base": {
                "trigger_conditions": ["growth slows gradually"],
                "transmission_path": "yields stabilize and equities consolidate",
                "note": None,
            },
            "bullish": {
                "trigger_conditions": ["inflation cools faster"],
                "transmission_path": "real yields ease and duration recovers",
                "note": None,
            },
            "bearish": {
                "trigger_conditions": ["inflation reaccelerates"],
                "transmission_path": "rate pressure tightens financial conditions",
                "note": None,
            },
            "systemic": {
                "trigger_conditions": ["credit spreads gap wider"],
                "transmission_path": "funding stress spills into risk assets",
                "note": None,
            },
        },
        "source_list": [
            {"id": "s1", "url": "https://fred.stlouisfed.org/series/DGS10", "accessed_at": "2026-06-29"},
            {"id": "s2", "rag_doc_id": "credit_snapshot", "accessed_at": "2026-06-29"},
        ],
        "boundary_notice": " ".join(REQUIRED_BOUNDARY_KEYWORDS),
    }


def make_registry(*, on_dashboard: list[dict[str, Any]] | None = None) -> AgentToolRegistry:
    registry = AgentToolRegistry()

    def dashboard_handler(args: dict[str, Any]) -> dict[str, Any]:
        if on_dashboard is not None:
            on_dashboard.append(args)
        return {"series": "DGS10", "value": 4.3}

    registry.register(
        ToolSpec(
            name="dashboard_query",
            description="Mock dashboard query.",
            parameters_schema={
                "type": "object",
                "properties": {"series": {"type": "string"}},
                "required": ["series"],
                "additionalProperties": False,
            },
            handler=dashboard_handler,
        )
    )
    registry.register(make_finalize_macro_brief_tool())
    return registry


def finalize_call(call_id: str = "final", payload: dict[str, Any] | None = None) -> ToolCall:
    return ToolCall(
        id=call_id,
        name=FINALIZE_TOOL_NAME,
        arguments={"brief": payload or brief_payload()},
    )


def tool_names_from_call(call: dict[str, Any]) -> list[str]:
    return [tool["function"]["name"] for tool in call["tools"]]


def test_run_agent_dispatches_tool_then_finalizes():
    dispatches: list[dict[str, Any]] = []
    provider = MockProvider(
        [
            ChatResponse(
                tool_calls=[
                    ToolCall(
                        id="call-1",
                        name="dashboard_query",
                        arguments={"series": "DGS10"},
                    )
                ],
                finish_reason="tool_calls",
            ),
            ChatResponse(tool_calls=[finalize_call()], finish_reason="tool_calls"),
        ]
    )

    result = run_agent(
        session_id="s1",
        user_question="Build a macro brief.",
        provider=provider,
        tool_registry=make_registry(on_dashboard=dispatches),
        current_date=date(2026, 6, 30),
        tool_names=["dashboard_query", FINALIZE_TOOL_NAME],
    )

    assert result.final_status == "ok"
    assert result.brief is not None
    assert result.steps == 2
    assert dispatches == [{"series": "DGS10"}]
    assert any(message.role == "tool" and "DGS10" in message.content for message in provider.calls[1]["messages"])


def test_run_agent_plain_text_adds_finalize_convergence_message():
    provider = MockProvider(
        [
            ChatResponse(content="Here is a prose answer."),
            ChatResponse(tool_calls=[finalize_call()], finish_reason="tool_calls"),
        ]
    )

    result = run_agent(
        session_id="s2",
        user_question="Build a macro brief.",
        provider=provider,
        tool_registry=make_registry(),
        current_date=date(2026, 6, 30),
        tool_names=["dashboard_query", FINALIZE_TOOL_NAME],
    )

    assert result.final_status == "ok"
    assert any(warning.code == "plain_text_without_tool_calls" for warning in result.warnings)
    assert any(FINALIZE_TOOL_NAME in message.content for message in provider.calls[1]["messages"] if message.role == "user")


def test_run_agent_returns_incomplete_when_finalize_never_arrives():
    provider = MockProvider([ChatResponse(content="still thinking"), ChatResponse(content="still prose")])

    result = run_agent(
        session_id="s3",
        user_question="Build a macro brief.",
        provider=provider,
        tool_registry=make_registry(),
        current_date=date(2026, 6, 30),
        tool_names=["dashboard_query", FINALIZE_TOOL_NAME],
        budget=AgentBudget(max_steps=2),
    )

    assert result.final_status == "incomplete"
    assert result.brief is None
    assert result.steps == 2
    assert any(warning.code == "agent_incomplete" for warning in result.warnings)


def test_finalize_validation_failure_retries_once_then_succeeds():
    invalid_payload = brief_payload()
    del invalid_payload["source_list"]
    provider = MockProvider(
        [
            ChatResponse(tool_calls=[finalize_call("bad-final", invalid_payload)], finish_reason="tool_calls"),
            ChatResponse(tool_calls=[finalize_call("good-final")], finish_reason="tool_calls"),
        ]
    )

    result = run_agent(
        session_id="s4",
        user_question="Build a macro brief.",
        provider=provider,
        tool_registry=make_registry(),
        current_date=date(2026, 6, 30),
        tool_names=["dashboard_query", FINALIZE_TOOL_NAME],
    )

    assert result.final_status == "ok"
    assert any(warning.code == "validation_retry" for warning in result.warnings)
    correction_messages = [
        message.content
        for message in provider.calls[1]["messages"]
        if message.role == "user" and "macro_brief_validation_error" in message.content
    ]
    assert correction_messages
    assert "source_list" in correction_messages[0]
    assert FINALIZE_TOOL_NAME in correction_messages[0]


def test_finalize_validation_failure_twice_returns_partial_brief():
    first_invalid = brief_payload()
    del first_invalid["source_list"]
    second_invalid = brief_payload()
    second_invalid["forward_indicators"] = second_invalid["forward_indicators"][:2]

    provider = MockProvider(
        [
            ChatResponse(tool_calls=[finalize_call("bad-final-1", first_invalid)], finish_reason="tool_calls"),
            ChatResponse(tool_calls=[finalize_call("bad-final-2", second_invalid)], finish_reason="tool_calls"),
        ]
    )

    result = run_agent(
        session_id="s5",
        user_question="Build a macro brief.",
        provider=provider,
        tool_registry=make_registry(),
        current_date=date(2026, 6, 30),
        tool_names=["dashboard_query", FINALIZE_TOOL_NAME],
    )

    assert result.final_status == "validation_failed"
    assert result.brief is None
    assert result.partial_brief == second_invalid
    assert result.validation_findings is not None
    assert any("forward_indicators" in finding for finding in result.validation_findings["findings"])
    assert any(warning.code == "validation_failed" for warning in result.warnings)


def test_validation_retry_message_does_not_leak_input_values():
    invalid_payload = brief_payload()
    invalid_payload["market_state"][0]["symbol"] = "SECRET_INPUT_VALUE"
    provider = MockProvider(
        [
            ChatResponse(tool_calls=[finalize_call("bad-final", invalid_payload)], finish_reason="tool_calls"),
            ChatResponse(tool_calls=[finalize_call("good-final")], finish_reason="tool_calls"),
        ]
    )

    result = run_agent(
        session_id="s6",
        user_question="Build a macro brief.",
        provider=provider,
        tool_registry=make_registry(),
        current_date=date(2026, 6, 30),
        tool_names=["dashboard_query", FINALIZE_TOOL_NAME],
    )

    assert result.final_status == "ok"
    retry_messages = [
        message.content
        for message in provider.calls[1]["messages"]
        if message.role == "user" and "macro_brief_validation_error" in message.content
    ]
    assert retry_messages
    assert "SECRET_INPUT_VALUE" not in retry_messages[0]


def test_two_phase_default_switches_after_two_plain_turns_to_finalize_only():
    provider = MockProvider(
        [
            ChatResponse(content="research note"),
            ChatResponse(content="second note"),
            ChatResponse(tool_calls=[finalize_call()], finish_reason="tool_calls"),
        ]
    )

    result = run_agent(
        session_id="s7",
        user_question="Build a macro brief.",
        provider=provider,
        tool_registry=make_registry(),
        current_date=date(2026, 6, 30),
        tool_names=["dashboard_query", FINALIZE_TOOL_NAME],
    )

    assert result.final_status == "ok"
    assert tool_names_from_call(provider.calls[2]) == [FINALIZE_TOOL_NAME]
    assert any(event.type == "agent_phase" and event.data["reason"] == "no_tool_calls" for event in result.events)


def test_two_phase_research_max_steps_switches_to_finalize_only():
    dispatches: list[dict[str, Any]] = []
    provider = MockProvider(
        [
            ChatResponse(
                tool_calls=[ToolCall(id="call-1", name="dashboard_query", arguments={"series": "DGS10"})],
                finish_reason="tool_calls",
            ),
            ChatResponse(tool_calls=[finalize_call()], finish_reason="tool_calls"),
        ]
    )

    result = run_agent(
        session_id="s8",
        user_question="Build a macro brief.",
        provider=provider,
        tool_registry=make_registry(on_dashboard=dispatches),
        current_date=date(2026, 6, 30),
        tool_names=["dashboard_query", FINALIZE_TOOL_NAME],
        config=AgentRuntimeConfig(research_max_steps=1),
    )

    assert result.final_status == "ok"
    assert dispatches == [{"series": "DGS10"}]
    assert tool_names_from_call(provider.calls[1]) == [FINALIZE_TOOL_NAME]


def test_force_writing_phase_starts_with_finalize_only():
    provider = MockProvider([ChatResponse(tool_calls=[finalize_call()], finish_reason="tool_calls")])

    result = run_agent(
        session_id="s9",
        user_question="Build a macro brief.",
        provider=provider,
        tool_registry=make_registry(),
        current_date=date(2026, 6, 30),
        tool_names=["dashboard_query", FINALIZE_TOOL_NAME],
        config=AgentRuntimeConfig(force_writing_phase=True),
    )

    assert result.final_status == "ok"
    assert tool_names_from_call(provider.calls[0]) == [FINALIZE_TOOL_NAME]


def test_two_phase_can_be_disabled_for_single_loop_behavior():
    provider = MockProvider(
        [
            ChatResponse(content="research note"),
            ChatResponse(content="second note"),
            ChatResponse(tool_calls=[finalize_call()], finish_reason="tool_calls"),
        ]
    )

    result = run_agent(
        session_id="s10",
        user_question="Build a macro brief.",
        provider=provider,
        tool_registry=make_registry(),
        current_date=date(2026, 6, 30),
        tool_names=["dashboard_query", FINALIZE_TOOL_NAME],
        config=AgentRuntimeConfig(two_phase_mode=False),
    )

    assert result.final_status == "ok"
    assert tool_names_from_call(provider.calls[2]) == ["dashboard_query", FINALIZE_TOOL_NAME]
