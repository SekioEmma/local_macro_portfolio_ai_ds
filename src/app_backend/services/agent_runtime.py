"""Phase F5 internal agent runtime.

The runtime is deliberately service-only: it does not expose routes, call the
network directly, persist trace files, or read holdings from disk. Provider,
tool, and optional holdings context are all injected by callers.
"""
from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import date
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from app_backend.schemas.macro_brief import MacroBrief
from app_backend.services.agent_tool_registry import (
    FINALIZE_TOOL_NAME,
    AgentToolRegistry,
    ToolResult,
)
from app_backend.services.llm_provider_adapter import (
    ChatMessage,
    ChatResponse,
    LLMProviderAdapter,
    TokenUsage,
    ToolCall,
)
from app_backend.services.macro_brief_parser import (
    MacroBriefValidationError,
    parse_macro_brief,
)
from app_backend.services.macro_brief_prompt import build_macro_brief_prompt


FinalStatus = Literal["ok", "incomplete", "validation_failed"]

AGENT_MODEL_NAME = "deepseek-v4-pro"
PLAIN_TEXT_WARNING = "plain_text_without_tool_calls"
INCOMPLETE_WARNING = "agent_incomplete"

_FINALIZE_CONVERGENCE_MESSAGE = (
    "You must continue with tool calls. If the MacroBrief is ready, call "
    f"{FINALIZE_TOOL_NAME} with the complete brief JSON. Plain text is not "
    "a valid final response."
)


class AgentRuntimeWarning(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str
    message: str = ""


class AgentRuntimeEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: str
    step: int | None = None
    data: dict[str, Any] = Field(default_factory=dict)


class AgentRuntimeConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    model_name: str = AGENT_MODEL_NAME
    max_tokens_per_call: int = Field(default=4000, gt=0)
    converge_after_plain_text: bool = True

    # F5-4/F5-5 fields are defined now so callers can pin config without
    # changing the service API as later runtime controls are filled in.
    max_tool_failures: int = Field(default=3, gt=0)
    two_phase_mode: bool = False
    research_max_steps: int = Field(default=12, gt=0)
    writing_max_steps: int = Field(default=2, gt=0)
    force_writing_phase: bool = False


class AgentBudget(BaseModel):
    model_config = ConfigDict(extra="forbid")

    max_steps: int = Field(default=18, gt=0)
    max_search_calls: int = Field(default=5, ge=0)
    max_rag_calls: int = Field(default=5, ge=0)
    max_tokens_total: int = Field(default=40000, ge=0)

    steps_used: int = Field(default=0, ge=0)
    search_calls_used: int = Field(default=0, ge=0)
    rag_calls_used: int = Field(default=0, ge=0)
    tokens_used: int = Field(default=0, ge=0)

    def has_step(self) -> bool:
        return self.steps_used < self.max_steps

    def record_step(self) -> None:
        self.steps_used += 1

    def record_tokens(self, usage: TokenUsage) -> None:
        self.tokens_used += usage.total_tokens


class AgentIncomplete(RuntimeError):
    """Raised internally when the loop cannot reach finalize in budget."""


class BudgetExceeded(RuntimeError):
    """Raised internally when a runtime budget is exhausted."""

    def __init__(self, kind: str) -> None:
        self.kind = kind
        super().__init__(f"agent budget exceeded: {kind}")


class ToolDisabled(RuntimeError):
    """Raised internally when a disabled tool is requested."""

    def __init__(self, name: str) -> None:
        self.name = name
        super().__init__(f"agent tool disabled: {name}")


class AgentSessionResult(BaseModel):
    model_config = ConfigDict(extra="forbid", arbitrary_types_allowed=True)

    session_id: str
    final_status: FinalStatus
    brief: MacroBrief | None = None
    partial_brief: dict[str, Any] | None = None
    validation_findings: dict[str, list[str]] | None = None
    warnings: list[AgentRuntimeWarning] = Field(default_factory=list)
    events: list[AgentRuntimeEvent] = Field(default_factory=list)
    steps: int = 0


def run_agent(
    *,
    session_id: str,
    user_question: str,
    provider: LLMProviderAdapter,
    tool_registry: AgentToolRegistry,
    current_date: date,
    tool_names: list[str],
    include_holdings: bool = False,
    holdings_snapshot: Mapping[str, Any] | None = None,
    config: AgentRuntimeConfig | None = None,
    budget: AgentBudget | None = None,
) -> AgentSessionResult:
    """Run the internal MacroBrief agent loop against injected dependencies."""
    cfg = config or AgentRuntimeConfig()
    run_budget = budget or AgentBudget()
    warnings: list[AgentRuntimeWarning] = []
    events: list[AgentRuntimeEvent] = []

    prompt = build_macro_brief_prompt(
        user_question=user_question,
        current_date=current_date,
        tool_names=tool_names,
        include_holdings=include_holdings,
        holdings_snapshot=holdings_snapshot,
    )
    messages = [
        ChatMessage(role=message["role"], content=message["content"])
        for message in prompt.messages()
    ]
    tool_schema = _tool_schema_for_names(tool_registry, tool_names)

    while run_budget.has_step():
        step = run_budget.steps_used + 1
        response = provider.chat(
            model=cfg.model_name,
            messages=messages,
            tools=tool_schema,
            tool_choice="auto",
            response_format=prompt.response_format,
            max_tokens=cfg.max_tokens_per_call,
        )
        run_budget.record_step()
        run_budget.record_tokens(response.usage)
        _record_completion_event(events, step, response)

        if response.content:
            messages.append(ChatMessage(role="assistant", content=response.content))

        if not response.tool_calls:
            _handle_plain_text_turn(messages, warnings, cfg)
            continue

        for tool_call in response.tool_calls:
            if tool_call.name == FINALIZE_TOOL_NAME:
                return _finalize_result(
                    session_id=session_id,
                    budget=run_budget,
                    warnings=warnings,
                    events=events,
                    tool_call=tool_call,
                )
            _dispatch_tool_call(
                tool_registry=tool_registry,
                tool_call=tool_call,
                messages=messages,
                events=events,
                step=step,
            )

    warnings.append(
        AgentRuntimeWarning(
            code=INCOMPLETE_WARNING,
            message=f"Agent did not call {FINALIZE_TOOL_NAME} within max_steps.",
        )
    )
    return AgentSessionResult(
        session_id=session_id,
        final_status="incomplete",
        warnings=warnings,
        events=events,
        steps=run_budget.steps_used,
    )


def _tool_schema_for_names(
    tool_registry: AgentToolRegistry,
    tool_names: list[str],
) -> list[dict[str, Any]]:
    allowed = set(tool_names)
    return [
        schema
        for schema in tool_registry.openai_schema()
        if schema.get("function", {}).get("name") in allowed
    ]


def _record_completion_event(
    events: list[AgentRuntimeEvent],
    step: int,
    response: ChatResponse,
) -> None:
    events.append(
        AgentRuntimeEvent(
            type="llm_completion",
            step=step,
            data={
                "finish_reason": response.finish_reason,
                "tool_calls": [tool_call.name for tool_call in response.tool_calls],
                "tokens": response.usage.total_tokens,
            },
        )
    )


def _handle_plain_text_turn(
    messages: list[ChatMessage],
    warnings: list[AgentRuntimeWarning],
    config: AgentRuntimeConfig,
) -> None:
    if not config.converge_after_plain_text:
        return
    if not any(warning.code == PLAIN_TEXT_WARNING for warning in warnings):
        warnings.append(
            AgentRuntimeWarning(
                code=PLAIN_TEXT_WARNING,
                message="Provider returned text without tool calls; runtime requested finalize.",
            )
        )
    messages.append(ChatMessage(role="user", content=_FINALIZE_CONVERGENCE_MESSAGE))


def _dispatch_tool_call(
    *,
    tool_registry: AgentToolRegistry,
    tool_call: ToolCall,
    messages: list[ChatMessage],
    events: list[AgentRuntimeEvent],
    step: int,
) -> None:
    result = tool_registry.dispatch(tool_call.name, tool_call.arguments)
    events.append(
        AgentRuntimeEvent(
            type="tool_result",
            step=step,
            data={
                "tool_name": tool_call.name,
                "status": result.status,
                "error_code": result.error_code,
            },
        )
    )
    _append_tool_message(messages, tool_call, result)


def _append_tool_message(
    messages: list[ChatMessage],
    tool_call: ToolCall,
    result: ToolResult,
) -> None:
    messages.append(
        ChatMessage(
            role="tool",
            tool_call_id=tool_call.id,
            content=json.dumps(result.to_json_payload(), ensure_ascii=False, sort_keys=True),
        )
    )


def _finalize_result(
    *,
    session_id: str,
    budget: AgentBudget,
    warnings: list[AgentRuntimeWarning],
    events: list[AgentRuntimeEvent],
    tool_call: ToolCall,
) -> AgentSessionResult:
    brief_payload = tool_call.arguments.get("brief")
    try:
        brief = parse_macro_brief(brief_payload)
    except MacroBriefValidationError as exc:
        return AgentSessionResult(
            session_id=session_id,
            final_status="validation_failed",
            partial_brief=brief_payload if isinstance(brief_payload, dict) else None,
            validation_findings=exc.to_dict(),
            warnings=warnings,
            events=events,
            steps=budget.steps_used,
        )
    return AgentSessionResult(
        session_id=session_id,
        final_status="ok",
        brief=brief,
        warnings=warnings,
        events=events,
        steps=budget.steps_used,
    )


__all__ = [
    "AgentBudget",
    "AgentIncomplete",
    "AgentRuntimeConfig",
    "AgentRuntimeEvent",
    "AgentRuntimeWarning",
    "AgentSessionResult",
    "BudgetExceeded",
    "ToolDisabled",
    "run_agent",
]
