from __future__ import annotations

from datetime import date
from typing import Any

from app_backend.services.agent_runtime import AgentBudget, run_agent
from app_backend.services.agent_tool_registry import FINALIZE_TOOL_NAME, ToolSpec
from app_backend.services.llm_provider_adapter import ChatResponse, TokenUsage, ToolCall
from tests.ai.test_agent_runtime_mocked import MockProvider, finalize_call, make_registry


def _tool_names() -> list[str]:
    return [
        "dashboard_query",
        "search_tavily",
        "rag_retrieve",
        FINALIZE_TOOL_NAME,
    ]


def _budget_registry(
    *,
    search_calls: list[dict[str, Any]] | None = None,
    rag_calls: list[dict[str, Any]] | None = None,
    dashboard_calls: list[dict[str, Any]] | None = None,
):
    registry = make_registry(on_dashboard=dashboard_calls)

    def search_handler(args: dict[str, Any]) -> dict[str, Any]:
        if search_calls is not None:
            search_calls.append(args)
        return {"results": [{"title": "mock search"}]}

    def rag_handler(args: dict[str, Any]) -> dict[str, Any]:
        if rag_calls is not None:
            rag_calls.append(args)
        return {"chunks": [{"doc_id": "mock-doc"}]}

    registry.register(
        ToolSpec(
            name="search_tavily",
            description="Mock search.",
            parameters_schema={"type": "object", "properties": {}, "required": [], "additionalProperties": True},
            handler=search_handler,
        )
    )
    registry.register(
        ToolSpec(
            name="rag_retrieve",
            description="Mock RAG.",
            parameters_schema={"type": "object", "properties": {}, "required": [], "additionalProperties": True},
            handler=rag_handler,
        )
    )
    return registry


def test_step_budget_records_budget_warning_when_exhausted():
    provider = MockProvider([ChatResponse(content="no finalize")])

    result = run_agent(
        session_id="budget-step",
        user_question="Build a macro brief.",
        provider=provider,
        tool_registry=_budget_registry(),
        current_date=date(2026, 6, 30),
        tool_names=_tool_names(),
        budget=AgentBudget(max_steps=1),
    )

    assert result.final_status == "incomplete"
    assert any(warning.code == "budget_exceeded:steps" for warning in result.warnings)


def test_search_budget_exceeded_skips_dispatch_and_requests_finalize():
    search_calls: list[dict[str, Any]] = []
    provider = MockProvider(
        [
            ChatResponse(
                tool_calls=[ToolCall(id="search-1", name="search_tavily", arguments={"query": "CPI"})],
                finish_reason="tool_calls",
            ),
            ChatResponse(tool_calls=[finalize_call()], finish_reason="tool_calls"),
        ]
    )

    result = run_agent(
        session_id="budget-search",
        user_question="Build a macro brief.",
        provider=provider,
        tool_registry=_budget_registry(search_calls=search_calls),
        current_date=date(2026, 6, 30),
        tool_names=_tool_names(),
        budget=AgentBudget(max_search_calls=0),
    )

    assert result.final_status == "ok"
    assert search_calls == []
    assert any(warning.code == "budget_exceeded:search" for warning in result.warnings)
    assert any("budget_exceeded" in message.content for message in provider.calls[1]["messages"] if message.role == "tool")


def test_rag_budget_exceeded_skips_dispatch_and_requests_finalize():
    rag_calls: list[dict[str, Any]] = []
    provider = MockProvider(
        [
            ChatResponse(
                tool_calls=[ToolCall(id="rag-1", name="rag_retrieve", arguments={"query": "credit"})],
                finish_reason="tool_calls",
            ),
            ChatResponse(tool_calls=[finalize_call()], finish_reason="tool_calls"),
        ]
    )

    result = run_agent(
        session_id="budget-rag",
        user_question="Build a macro brief.",
        provider=provider,
        tool_registry=_budget_registry(rag_calls=rag_calls),
        current_date=date(2026, 6, 30),
        tool_names=_tool_names(),
        budget=AgentBudget(max_rag_calls=0),
    )

    assert result.final_status == "ok"
    assert rag_calls == []
    assert any(warning.code == "budget_exceeded:rag" for warning in result.warnings)


def test_token_budget_exceeded_stops_research_dispatch_and_requests_finalize():
    search_calls: list[dict[str, Any]] = []
    provider = MockProvider(
        [
            ChatResponse(
                tool_calls=[ToolCall(id="search-1", name="search_tavily", arguments={"query": "CPI"})],
                usage=TokenUsage(total_tokens=5),
                finish_reason="tool_calls",
            ),
            ChatResponse(tool_calls=[finalize_call()], finish_reason="tool_calls"),
        ]
    )

    result = run_agent(
        session_id="budget-token",
        user_question="Build a macro brief.",
        provider=provider,
        tool_registry=_budget_registry(search_calls=search_calls),
        current_date=date(2026, 6, 30),
        tool_names=_tool_names(),
        budget=AgentBudget(max_tokens_total=1),
    )

    assert result.final_status == "ok"
    assert search_calls == []
    assert any(warning.code == "budget_exceeded:tokens" for warning in result.warnings)


def test_non_search_tool_does_not_consume_search_budget():
    dashboard_calls: list[dict[str, Any]] = []
    budget = AgentBudget(max_search_calls=0)
    provider = MockProvider(
        [
            ChatResponse(
                tool_calls=[ToolCall(id="dash-1", name="dashboard_query", arguments={"series": "DGS10"})],
                finish_reason="tool_calls",
            ),
            ChatResponse(tool_calls=[finalize_call()], finish_reason="tool_calls"),
        ]
    )

    result = run_agent(
        session_id="budget-non-search",
        user_question="Build a macro brief.",
        provider=provider,
        tool_registry=_budget_registry(dashboard_calls=dashboard_calls),
        current_date=date(2026, 6, 30),
        tool_names=_tool_names(),
        budget=budget,
    )

    assert result.final_status == "ok"
    assert dashboard_calls == [{"series": "DGS10"}]
    assert budget.search_calls_used == 0
