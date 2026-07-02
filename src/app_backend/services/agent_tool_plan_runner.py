"""Deterministic execution for planned MacroBrief agent tools."""
from __future__ import annotations

import json
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app_backend.services.agent_evidence_ledger_registration import (
    register_tool_result_evidence,
)
from app_backend.services.agent_information_plan import AgentToolPlan, AgentToolPlanStep
from app_backend.services.agent_runtime import AgentBudget, BudgetExceeded
from app_backend.services.agent_tool_registry import AgentToolRegistry, ToolResult
from app_backend.services.run_evidence_ledger import RunEvidenceLedger


class PlannedToolOutcome(BaseModel):
    model_config = ConfigDict(extra="forbid")

    topic: str
    tool_name: str
    args: dict[str, Any] = Field(default_factory=dict)
    status: str
    required: bool = True
    error_code: str | None = None
    error_message: str = ""
    evidence_ids: list[str] = Field(default_factory=list)
    evidence_tiers: list[str] = Field(default_factory=list)
    content: Any = None


class PlannedToolRunResult(BaseModel):
    model_config = ConfigDict(extra="forbid", arbitrary_types_allowed=True)

    ledger: RunEvidenceLedger | None = None
    outcomes: list[PlannedToolOutcome] = Field(default_factory=list)

    @property
    def evidence_count(self) -> int:
        return sum(len(outcome.evidence_ids) for outcome in self.outcomes)

    @property
    def failed_required_topics(self) -> list[str]:
        return [
            outcome.topic
            for outcome in self.outcomes
            if outcome.required and outcome.status != "ok"
        ]


def run_agent_tool_plan(
    *,
    plan: AgentToolPlan,
    tool_registry: AgentToolRegistry,
    ledger: RunEvidenceLedger | None,
    budget: AgentBudget | None = None,
) -> PlannedToolRunResult:
    """Execute a deterministic tool plan without model-driven retries.

    Tool errors are represented as outcomes instead of aborting the run. This
    gives the writer phase a complete evidence/unavailable picture and avoids
    repeated Tavily/RAG calls caused by open-ended ReAct loops.
    """
    run_budget = budget or AgentBudget()
    outcomes: list[PlannedToolOutcome] = []
    seen: set[str] = set()
    current_ledger = ledger

    for step in plan.steps:
        step_args = step.args or [{}]
        for args in step_args[: step.max_calls]:
            normalized_args = dict(args)
            dedupe_key = _dedupe_key(step, normalized_args)
            if dedupe_key in seen:
                continue
            seen.add(dedupe_key)

            spec = tool_registry.get(step.tool_name)
            if spec is None:
                outcomes.append(
                    _error_outcome(
                        step=step,
                        args=normalized_args,
                        code="unknown_tool",
                        message=f"tool not registered: {step.tool_name}",
                    )
                )
                continue

            try:
                run_budget.record_tool_call(spec.budget_class)
            except BudgetExceeded as exc:
                outcomes.append(
                    _error_outcome(
                        step=step,
                        args=normalized_args,
                        code=f"budget_exceeded:{exc.kind}",
                        message=f"{step.tool_name} exceeded the {exc.kind} budget.",
                    )
                )
                continue

            result = tool_registry.dispatch(step.tool_name, normalized_args)
            if result.status != "ok":
                outcomes.append(_outcome_from_result(step=step, args=normalized_args, result=result))
                continue

            if current_ledger is None:
                outcomes.append(
                    PlannedToolOutcome(
                        topic=step.topic,
                        tool_name=step.tool_name,
                        args=normalized_args,
                        status=result.status,
                        required=step.required,
                        content=result.content,
                    )
                )
                continue

            registration = register_tool_result_evidence(
                ledger=current_ledger,
                tool_name=step.tool_name,
                result=result,
            )
            current_ledger = registration.ledger
            outcomes.append(
                PlannedToolOutcome(
                    topic=step.topic,
                    tool_name=step.tool_name,
                    args=normalized_args,
                    status=registration.result.status,
                    required=step.required,
                    content=registration.result.content,
                    evidence_ids=registration.evidence_ids,
                    evidence_tiers=registration.evidence_tiers,
                )
            )

    return PlannedToolRunResult(ledger=current_ledger, outcomes=outcomes)


def _outcome_from_result(
    *,
    step: AgentToolPlanStep,
    args: dict[str, Any],
    result: ToolResult,
) -> PlannedToolOutcome:
    return PlannedToolOutcome(
        topic=step.topic,
        tool_name=step.tool_name,
        args=args,
        status=result.status,
        required=step.required,
        error_code=result.error_code,
        error_message=result.error_message or "",
        content=result.content,
    )


def _error_outcome(
    *,
    step: AgentToolPlanStep,
    args: dict[str, Any],
    code: str,
    message: str,
) -> PlannedToolOutcome:
    return PlannedToolOutcome(
        topic=step.topic,
        tool_name=step.tool_name,
        args=args,
        status="error",
        required=step.required,
        error_code=code,
        error_message=message,
    )


def _dedupe_key(step: AgentToolPlanStep, args: dict[str, Any]) -> str:
    return json.dumps(
        {
            "topic": step.topic,
            "tool_name": step.tool_name,
            "args": args,
        },
        ensure_ascii=True,
        sort_keys=True,
        default=str,
    )


__all__ = [
    "PlannedToolOutcome",
    "PlannedToolRunResult",
    "run_agent_tool_plan",
]
