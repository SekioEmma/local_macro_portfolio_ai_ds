from __future__ import annotations

from app_backend.services.agent_information_plan import AgentToolPlan, AgentToolPlanStep
from app_backend.services.agent_runtime import AgentBudget
from app_backend.services.agent_tool_plan_runner import run_agent_tool_plan
from app_backend.services.agent_tool_registry import AgentToolRegistry, ToolSpec
from app_backend.services.run_evidence_ledger import RunEvidenceLedger


def test_planned_tool_runner_executes_and_registers_evidence():
    registry = AgentToolRegistry()
    registry.register(
        ToolSpec(
            name="quote_etf",
            description="fake quote",
            parameters_schema={"type": "object"},
            handler=lambda args: {
                "quotes": [
                    {
                        "symbol": args["symbol"],
                        "value": 500.25,
                        "unit": "USD",
                        "status": "ok",
                        "observation_date": "2026-07-01",
                    }
                ]
            },
        )
    )
    plan = AgentToolPlan(
        steps=[
            AgentToolPlanStep(
                topic="equity_market",
                tool_name="quote_etf",
                reason="need equity quote",
                args=[{"symbol": "SPY"}],
            )
        ]
    )

    result = run_agent_tool_plan(
        plan=plan,
        tool_registry=registry,
        ledger=RunEvidenceLedger(run_id="run-1"),
    )

    assert result.evidence_count == 1
    assert len(result.ledger.records) == 1
    outcome = result.outcomes[0]
    assert outcome.status == "ok"
    assert outcome.evidence_ids == [result.ledger.records[0].evidence_id]
    assert outcome.content["quotes"][0]["evidence_id"] == result.ledger.records[0].evidence_id
    assert result.ledger.records[0].atomic_observations[0].value == 500.25


def test_planned_tool_runner_degrades_tool_errors_without_aborting():
    registry = AgentToolRegistry()
    registry.register(
        ToolSpec(
            name="dashboard_query",
            description="fake dashboard",
            parameters_schema={"type": "object"},
            handler=lambda _args: (_ for _ in ()).throw(RuntimeError("boom secret path C:\\private")),
        )
    )
    plan = AgentToolPlan(
        steps=[
            AgentToolPlanStep(
                topic="dashboard_overview",
                tool_name="dashboard_query",
                reason="need dashboard",
            ),
            AgentToolPlanStep(
                topic="missing",
                tool_name="unknown_tool",
                reason="not registered",
                required=False,
            ),
        ]
    )

    result = run_agent_tool_plan(
        plan=plan,
        tool_registry=registry,
        ledger=RunEvidenceLedger(run_id="run-1"),
    )

    assert [outcome.status for outcome in result.outcomes] == ["error", "error"]
    assert result.outcomes[0].error_code == "handler_exception"
    assert "C:\\private" not in result.outcomes[0].error_message
    assert result.outcomes[1].error_code == "unknown_tool"
    assert result.failed_required_topics == ["dashboard_overview"]


def test_planned_tool_runner_dedupes_and_respects_budget():
    calls: list[dict] = []
    registry = AgentToolRegistry()
    registry.register(
        ToolSpec(
            name="search_tavily",
            description="fake search",
            parameters_schema={"type": "object"},
            handler=lambda args: calls.append(args) or {"results": []},
        )
    )
    plan = AgentToolPlan(
        steps=[
            AgentToolPlanStep(
                topic="current_public_news",
                tool_name="search_tavily",
                reason="need news",
                max_calls=3,
                args=[
                    {"query": "rates"},
                    {"query": "rates"},
                    {"query": "inflation"},
                ],
            )
        ]
    )

    result = run_agent_tool_plan(
        plan=plan,
        tool_registry=registry,
        ledger=RunEvidenceLedger(run_id="run-1"),
        budget=AgentBudget(max_search_calls=1),
    )

    assert calls == [{"query": "rates"}]
    assert [outcome.status for outcome in result.outcomes] == ["ok", "error"]
    assert result.outcomes[1].error_code == "budget_exceeded:search"
