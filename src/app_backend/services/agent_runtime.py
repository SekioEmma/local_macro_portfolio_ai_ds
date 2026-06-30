"""Phase F5 internal agent runtime.

The runtime is deliberately service-only: it does not expose routes, call the
network directly, persist trace files, or read holdings from disk. Provider,
tool, and optional holdings context are all injected by callers.
"""
from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from datetime import date
from time import monotonic
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from app_backend.schemas.macro_brief import MacroBrief
from app_backend.services.agent_tool_registry import (
    FINALIZE_TOOL_NAME,
    AgentToolRegistry,
    ToolBudgetClass,
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
from app_backend.services.macro_brief_evidence_projection import (
    project_macro_brief_sources_from_ledger,
)
from app_backend.services.macro_brief_prompt import build_macro_brief_prompt
from app_backend.services.agent_trace_service import AgentTraceService, sha256_json
from app_backend.services.claim_evidence_validator import validate_macro_brief_claim_evidence
from app_backend.services.agent_evidence_ledger_registration import (
    register_tool_result_evidence,
)
from app_backend.services.run_evidence_ledger import RunEvidenceLedger
from app_backend.services.temporal_alignment_service import build_temporal_envelope


FinalStatus = Literal["ok", "incomplete", "validation_failed", "cancelled"]
AgentPhase = Literal["research", "writing"]
CancellationRequested = Callable[[], bool]

AGENT_MODEL_NAME = "deepseek-v4-pro"
SEARCH_TOOL_NAME = "search_tavily"
RAG_TOOL_NAME = "rag_retrieve"
PLAIN_TEXT_WARNING = "plain_text_without_tool_calls"
INCOMPLETE_WARNING = "agent_incomplete"
BUDGET_WARNING_PREFIX = "budget_exceeded"
VALIDATION_RETRY_WARNING = "validation_retry"
VALIDATION_FAILED_WARNING = "validation_failed"
TOOL_DISABLED_WARNING_PREFIX = "tool_disabled"
AGENT_CANCELLED_WARNING = "agent_cancelled"

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


RuntimeEventCallback = Callable[[AgentRuntimeEvent], None]
MonotonicClock = Callable[[], float]


class AgentRuntimeConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    model_name: str = AGENT_MODEL_NAME
    max_tokens_per_call: int = Field(default=8192, gt=0)
    converge_after_plain_text: bool = True

    # F5-4/F5-5 fields are defined now so callers can pin config without
    # changing the service API as later runtime controls are filled in.
    max_tool_failures: int = Field(default=3, gt=0)
    two_phase_mode: bool = True
    research_max_steps: int = Field(default=12, gt=0)
    writing_max_steps: int = Field(default=3, gt=0)
    force_writing_phase: bool = False
    max_wall_clock_seconds: float = Field(default=180.0, gt=0)
    max_provider_call_seconds: float = Field(default=120.0, gt=0)
    max_tool_call_seconds: float = Field(default=30.0, gt=0)


class AgentBudget(BaseModel):
    model_config = ConfigDict(extra="forbid")

    max_steps: int = Field(default=18, gt=0)
    max_search_calls: int = Field(default=5, ge=0)
    max_rag_calls: int = Field(default=5, ge=0)
    max_external_quote_calls: int = Field(default=5, ge=0)
    max_tokens_total: int = Field(default=40000, ge=0)

    steps_used: int = Field(default=0, ge=0)
    search_calls_used: int = Field(default=0, ge=0)
    rag_calls_used: int = Field(default=0, ge=0)
    external_quote_calls_used: int = Field(default=0, ge=0)
    tokens_used: int = Field(default=0, ge=0)

    def has_step(self) -> bool:
        return self.steps_used < self.max_steps

    def record_step(self) -> None:
        self.steps_used += 1

    def record_tokens(self, usage: TokenUsage) -> None:
        self.tokens_used += usage.total_tokens

    def record_tool_call(self, budget_class: ToolBudgetClass | None) -> None:
        if budget_class == "external_search":
            if self.search_calls_used >= self.max_search_calls:
                raise BudgetExceeded("search")
            self.search_calls_used += 1
            return
        if budget_class == "rag_retrieval":
            if self.rag_calls_used >= self.max_rag_calls:
                raise BudgetExceeded("rag")
            self.rag_calls_used += 1
            return
        if budget_class == "external_quote":
            if self.external_quote_calls_used >= self.max_external_quote_calls:
                raise BudgetExceeded("external_quote")
            self.external_quote_calls_used += 1

    def token_budget_exceeded(self) -> bool:
        return self.tokens_used > self.max_tokens_total

    def remaining_step_ratio(self) -> float:
        remaining = max(self.max_steps - self.steps_used, 0)
        return remaining / self.max_steps


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
    trace_service: AgentTraceService | None = None,
    event_callback: RuntimeEventCallback | None = None,
    evidence_ledger: RunEvidenceLedger | None = None,
    cancellation_requested: CancellationRequested | None = None,
    monotonic_clock: MonotonicClock | None = None,
) -> AgentSessionResult:
    """Run the internal MacroBrief agent loop against injected dependencies."""
    cfg = config or AgentRuntimeConfig()
    run_budget = budget or AgentBudget()
    clock = monotonic_clock or monotonic
    run_started_at = clock()
    warnings: list[AgentRuntimeWarning] = []
    events: list[AgentRuntimeEvent] = []
    validation_failures = 0
    tool_failure_counts: dict[str, int] = {}
    disabled_tools: set[str] = set()
    current_evidence_ledger = evidence_ledger
    phase: AgentPhase = "writing" if cfg.two_phase_mode and cfg.force_writing_phase else "research"
    research_steps_used = 0
    writing_steps_used = 0
    consecutive_no_tool_calls = 0
    if trace_service is not None:
        trace_service.start_session(
            session_id=session_id,
            user_question=user_question,
            holdings_included=include_holdings,
            holdings_snapshot_sha256=sha256_json(holdings_snapshot) if include_holdings else None,
            current_date=current_date.isoformat(),
        )

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

    while run_budget.has_step():
        step = run_budget.steps_used + 1
        if _wall_clock_exceeded(
            started_at=run_started_at,
            clock=clock,
            config=cfg,
        ):
            return _finish_with_trace(
                _timeout_result(
                    session_id=session_id,
                    warnings=warnings,
                    events=events,
                    event_callback=event_callback,
                    steps=run_budget.steps_used,
                    step=step,
                    kind="wall_clock",
                    message="Agent exceeded max_wall_clock_seconds before the next provider call.",
                ),
                trace_service,
            )
        if _is_cancellation_requested(cancellation_requested):
            return _finish_with_trace(
                _cancelled_result(
                    session_id=session_id,
                    warnings=warnings,
                    events=events,
                    event_callback=event_callback,
                    steps=run_budget.steps_used,
                    step=step,
                ),
                trace_service,
            )
        current_phase = phase
        tool_schema = _tool_schema_for_names(
            tool_registry,
            _tool_names_for_phase(tool_names, phase),
            disabled_tools=disabled_tools,
        )
        try:
            _append_event(
                events,
                AgentRuntimeEvent(
                    type="provider_call_started",
                    step=step,
                    data={"phase": current_phase, "tool_count": len(tool_schema)},
                ),
                event_callback,
            )
            provider_started_at = clock()
            response = provider.chat(
                model=cfg.model_name,
                messages=messages,
                tools=tool_schema,
                tool_choice="auto",
                response_format=prompt.response_format,
                max_tokens=cfg.max_tokens_per_call,
            )
            provider_elapsed_seconds = clock() - provider_started_at
        except Exception as exc:  # noqa: BLE001 - provider failures degrade to incomplete
            warnings.append(
                AgentRuntimeWarning(
                    code="provider_error",
                    message=f"{type(exc).__name__}: provider chat failed.",
                )
            )
            _append_event(
                events,
                AgentRuntimeEvent(
                    type="provider_error",
                    step=step,
                    data={"error_type": type(exc).__name__},
                ),
                event_callback,
            )
            return _finish_with_trace(
                AgentSessionResult(
                    session_id=session_id,
                    final_status="incomplete",
                    warnings=warnings,
                    events=events,
                    steps=run_budget.steps_used,
                ),
                trace_service,
            )
        run_budget.record_step()
        if provider_elapsed_seconds > cfg.max_provider_call_seconds:
            return _finish_with_trace(
                _timeout_result(
                    session_id=session_id,
                    warnings=warnings,
                    events=events,
                    event_callback=event_callback,
                    steps=run_budget.steps_used,
                    step=step,
                    kind="provider_call",
                    message="Provider call exceeded max_provider_call_seconds.",
                    elapsed_seconds=provider_elapsed_seconds,
                ),
                trace_service,
            )
        if current_phase == "writing":
            writing_steps_used += 1
        else:
            research_steps_used += 1
        run_budget.record_tokens(response.usage)
        _record_completion_event(events, step, response, event_callback)
        if _wall_clock_exceeded(
            started_at=run_started_at,
            clock=clock,
            config=cfg,
        ):
            return _finish_with_trace(
                _timeout_result(
                    session_id=session_id,
                    warnings=warnings,
                    events=events,
                    event_callback=event_callback,
                    steps=run_budget.steps_used,
                    step=step,
                    kind="wall_clock",
                    message="Agent exceeded max_wall_clock_seconds after provider return.",
                ),
                trace_service,
            )
        if _is_cancellation_requested(cancellation_requested):
            return _finish_with_trace(
                _cancelled_result(
                    session_id=session_id,
                    warnings=warnings,
                    events=events,
                    event_callback=event_callback,
                    steps=run_budget.steps_used,
                    step=step,
                ),
                trace_service,
            )
        token_budget_exceeded = _handle_token_budget(
            budget=run_budget,
            warnings=warnings,
            messages=messages,
        )
        if token_budget_exceeded:
            phase = _switch_to_writing_phase(
                phase=phase,
                events=events,
                event_callback=event_callback,
                step=step,
                reason="token_budget_exceeded",
                config=cfg,
            )

        if response.tool_calls:
            messages.append(
                ChatMessage(
                    role="assistant",
                    content=response.content or "",
                    tool_calls=[
                        _tool_call_message_payload(tool_call)
                        for tool_call in response.tool_calls
                    ],
                )
            )
        elif response.content:
            messages.append(ChatMessage(role="assistant", content=response.content))

        if not response.tool_calls:
            consecutive_no_tool_calls += 1
            _handle_plain_text_turn(messages, warnings, cfg)
            phase = _maybe_switch_to_writing_phase(
                phase=phase,
                budget=run_budget,
                config=cfg,
                research_steps_used=research_steps_used,
                consecutive_no_tool_calls=consecutive_no_tool_calls,
                events=events,
                event_callback=event_callback,
                step=step,
            )
            if _writing_phase_exhausted(current_phase, writing_steps_used, cfg):
                break
            continue

        consecutive_no_tool_calls = 0
        for tool_call in response.tool_calls:
            if _wall_clock_exceeded(
                started_at=run_started_at,
                clock=clock,
                config=cfg,
            ):
                return _finish_with_trace(
                    _timeout_result(
                        session_id=session_id,
                        warnings=warnings,
                        events=events,
                        event_callback=event_callback,
                        steps=run_budget.steps_used,
                        step=step,
                        kind="wall_clock",
                        message="Agent exceeded max_wall_clock_seconds before the next tool call.",
                    ),
                    trace_service,
                )
            if _is_cancellation_requested(cancellation_requested):
                return _finish_with_trace(
                    _cancelled_result(
                        session_id=session_id,
                        warnings=warnings,
                        events=events,
                        event_callback=event_callback,
                        steps=run_budget.steps_used,
                        step=step,
                    ),
                    trace_service,
                )
            if tool_call.name == FINALIZE_TOOL_NAME:
                result, validation_failures = _handle_finalize_attempt(
                    session_id=session_id,
                    budget=run_budget,
                    warnings=warnings,
                    events=events,
                    event_callback=event_callback,
                    messages=messages,
                    tool_call=tool_call,
                    validation_failures=validation_failures,
                    evidence_ledger=current_evidence_ledger,
                    report_generated_at=f"{current_date.isoformat()}T00:00:00Z",
                )
                if result is not None:
                    return _finish_with_trace(result, trace_service)
                break
            if current_phase == "writing":
                _append_writing_phase_tool_message(
                    tool_call=tool_call,
                    messages=messages,
                    events=events,
                    event_callback=event_callback,
                    step=step,
                )
                continue
            if token_budget_exceeded:
                _append_budget_exceeded_tool_message(
                    tool_call=tool_call,
                    kind="tokens",
                    messages=messages,
                    events=events,
                    event_callback=event_callback,
                    step=step,
                )
                continue
            current_evidence_ledger = _dispatch_tool_call(
                tool_registry=tool_registry,
                tool_call=tool_call,
                messages=messages,
                events=events,
                event_callback=event_callback,
                step=step,
                budget=run_budget,
                warnings=warnings,
                config=cfg,
                tool_failure_counts=tool_failure_counts,
                disabled_tools=disabled_tools,
                evidence_ledger=current_evidence_ledger,
                clock=clock,
            )
            if _has_budget_warning(warnings):
                phase = _switch_to_writing_phase(
                    phase=phase,
                    events=events,
                    event_callback=event_callback,
                    step=step,
                    reason="budget_exceeded",
                    config=cfg,
                )

        phase = _maybe_switch_to_writing_phase(
            phase=phase,
            budget=run_budget,
            config=cfg,
            research_steps_used=research_steps_used,
            consecutive_no_tool_calls=consecutive_no_tool_calls,
            events=events,
            event_callback=event_callback,
            step=step,
        )
        if _writing_phase_exhausted(current_phase, writing_steps_used, cfg):
            break

    _append_budget_warning(warnings, "steps", "Agent exhausted max_steps before finalize.")
    warnings.append(
        AgentRuntimeWarning(
            code=INCOMPLETE_WARNING,
            message=f"Agent did not call {FINALIZE_TOOL_NAME} within max_steps.",
        )
    )
    return _finish_with_trace(AgentSessionResult(
        session_id=session_id,
        final_status="incomplete",
        warnings=warnings,
        events=events,
        steps=run_budget.steps_used,
    ), trace_service)


def _finish_with_trace(
    result: AgentSessionResult,
    trace_service: AgentTraceService | None,
) -> AgentSessionResult:
    if trace_service is not None:
        trace_service.write_runtime_events(
            session_id=result.session_id,
            events=result.events,
        )
        trace_service.end_session(
            session_id=result.session_id,
            final_status=result.final_status,
            steps=result.steps,
            warnings=result.warnings,
        )
    return result


def _is_cancellation_requested(
    cancellation_requested: CancellationRequested | None,
) -> bool:
    if cancellation_requested is None:
        return False
    try:
        return bool(cancellation_requested())
    except Exception:
        return False


def _cancelled_result(
    *,
    session_id: str,
    warnings: list[AgentRuntimeWarning],
    events: list[AgentRuntimeEvent],
    event_callback: RuntimeEventCallback | None,
    steps: int,
    step: int | None,
) -> AgentSessionResult:
    if not any(warning.code == AGENT_CANCELLED_WARNING for warning in warnings):
        warnings.append(
            AgentRuntimeWarning(
                code=AGENT_CANCELLED_WARNING,
                message="Agent run cancelled before the next provider or tool call.",
            )
        )
    _append_event(
        events,
        AgentRuntimeEvent(
            type="run_cancelled",
            step=step,
            data={"status": "cancelled"},
        ),
        event_callback,
    )
    return AgentSessionResult(
        session_id=session_id,
        final_status="cancelled",
        warnings=warnings,
        events=events,
        steps=steps,
    )


def _wall_clock_exceeded(
    *,
    started_at: float,
    clock: MonotonicClock,
    config: AgentRuntimeConfig,
) -> bool:
    return clock() - started_at > config.max_wall_clock_seconds


def _timeout_result(
    *,
    session_id: str,
    warnings: list[AgentRuntimeWarning],
    events: list[AgentRuntimeEvent],
    event_callback: RuntimeEventCallback | None,
    steps: int,
    step: int | None,
    kind: str,
    message: str,
    elapsed_seconds: float | None = None,
) -> AgentSessionResult:
    _append_timeout_warning(warnings, kind, message)
    payload: dict[str, Any] = {"kind": kind, "status": "timeout"}
    if elapsed_seconds is not None:
        payload["elapsed_seconds"] = round(elapsed_seconds, 3)
    _append_event(
        events,
        AgentRuntimeEvent(
            type="runtime_timeout",
            step=step,
            data=payload,
        ),
        event_callback,
    )
    return AgentSessionResult(
        session_id=session_id,
        final_status="incomplete",
        warnings=warnings,
        events=events,
        steps=steps,
    )


def _tool_schema_for_names(
    tool_registry: AgentToolRegistry,
    tool_names: list[str],
    *,
    disabled_tools: set[str] | None = None,
) -> list[dict[str, Any]]:
    allowed = set(tool_names)
    disabled = disabled_tools or set()
    return [
        schema
        for schema in tool_registry.openai_schema()
        if schema.get("function", {}).get("name") in allowed
        and schema.get("function", {}).get("name") not in disabled
    ]


def _tool_names_for_phase(tool_names: list[str], phase: AgentPhase) -> list[str]:
    if phase == "writing":
        return [FINALIZE_TOOL_NAME] if FINALIZE_TOOL_NAME in tool_names else []
    return tool_names


def _maybe_switch_to_writing_phase(
    *,
    phase: AgentPhase,
    budget: AgentBudget,
    config: AgentRuntimeConfig,
    research_steps_used: int,
    consecutive_no_tool_calls: int,
    events: list[AgentRuntimeEvent],
    event_callback: RuntimeEventCallback | None,
    step: int,
) -> AgentPhase:
    if not config.two_phase_mode or phase == "writing":
        return phase
    reason: str | None = None
    if budget.remaining_step_ratio() < 0.30:
        reason = "low_step_budget"
    elif research_steps_used >= config.research_max_steps:
        reason = "research_max_steps"
    elif consecutive_no_tool_calls >= 2:
        reason = "no_tool_calls"
    if reason is None:
        return phase
    return _switch_to_writing_phase(
        phase=phase,
        events=events,
        event_callback=event_callback,
        step=step,
        reason=reason,
        config=config,
    )


def _switch_to_writing_phase(
    *,
    phase: AgentPhase,
    events: list[AgentRuntimeEvent],
    event_callback: RuntimeEventCallback | None,
    step: int,
    reason: str,
    config: AgentRuntimeConfig,
) -> AgentPhase:
    if not config.two_phase_mode or phase == "writing":
        return phase
    _append_event(
        events,
        AgentRuntimeEvent(
            type="agent_phase",
            step=step,
            data={"phase": "writing", "reason": reason},
        ),
        event_callback,
    )
    return "writing"


def _writing_phase_exhausted(
    current_phase: AgentPhase,
    writing_steps_used: int,
    config: AgentRuntimeConfig,
) -> bool:
    return config.two_phase_mode and current_phase == "writing" and writing_steps_used >= config.writing_max_steps


def _has_budget_warning(warnings: list[AgentRuntimeWarning]) -> bool:
    return any(warning.code.startswith(f"{BUDGET_WARNING_PREFIX}:") for warning in warnings)


def _record_completion_event(
    events: list[AgentRuntimeEvent],
    step: int,
    response: ChatResponse,
    event_callback: RuntimeEventCallback | None,
) -> None:
    _append_event(
        events,
        AgentRuntimeEvent(
            type="llm_completion",
            step=step,
            data={
                "finish_reason": response.finish_reason,
                "tool_calls": [tool_call.name for tool_call in response.tool_calls],
                "tokens": response.usage.total_tokens,
            },
        ),
        event_callback,
    )


def _handle_plain_text_turn(
    messages: list[ChatMessage],
    warnings: list[AgentRuntimeWarning],
    config: AgentRuntimeConfig,
) -> None:
    if not config.converge_after_plain_text:
        return
    _append_finalize_convergence_message(messages)
    if not any(warning.code == PLAIN_TEXT_WARNING for warning in warnings):
        warnings.append(
            AgentRuntimeWarning(
                code=PLAIN_TEXT_WARNING,
                message="Provider returned text without tool calls; runtime requested finalize.",
            )
        )


def _append_finalize_convergence_message(messages: list[ChatMessage]) -> None:
    messages.append(ChatMessage(role="user", content=_FINALIZE_CONVERGENCE_MESSAGE))


def _handle_token_budget(
    *,
    budget: AgentBudget,
    warnings: list[AgentRuntimeWarning],
    messages: list[ChatMessage],
) -> bool:
    if not budget.token_budget_exceeded():
        return False
    _append_budget_warning(warnings, "tokens", "Agent exceeded max_tokens_total.")
    _append_finalize_convergence_message(messages)
    return True


def _dispatch_tool_call(
    *,
    tool_registry: AgentToolRegistry,
    tool_call: ToolCall,
    messages: list[ChatMessage],
    events: list[AgentRuntimeEvent],
    event_callback: RuntimeEventCallback | None,
    step: int,
    budget: AgentBudget,
    warnings: list[AgentRuntimeWarning],
    config: AgentRuntimeConfig,
    tool_failure_counts: dict[str, int],
    disabled_tools: set[str],
    evidence_ledger: RunEvidenceLedger | None,
    clock: MonotonicClock,
) -> RunEvidenceLedger | None:
    if tool_call.name in disabled_tools:
        _append_disabled_tool_message(
            tool_call=tool_call,
            messages=messages,
            events=events,
            event_callback=event_callback,
            step=step,
        )
        return evidence_ledger

    try:
        spec = tool_registry.get(tool_call.name)
        budget.record_tool_call(spec.budget_class if spec is not None else None)
    except BudgetExceeded as exc:
        _append_budget_warning(
            warnings,
            exc.kind,
            f"{tool_call.name} exceeded the {exc.kind} call budget.",
        )
        _append_budget_exceeded_tool_message(
            tool_call=tool_call,
            kind=exc.kind,
            messages=messages,
            events=events,
            event_callback=event_callback,
            step=step,
        )
        _append_finalize_convergence_message(messages)
        return evidence_ledger

    tool_started_at = clock()
    result = tool_registry.dispatch(tool_call.name, tool_call.arguments)
    tool_elapsed_seconds = clock() - tool_started_at
    if tool_elapsed_seconds > config.max_tool_call_seconds:
        _append_timeout_warning(
            warnings,
            "tool_call",
            f"{tool_call.name} exceeded max_tool_call_seconds.",
        )
        _append_event(
            events,
            AgentRuntimeEvent(
                type="tool_timeout",
                step=step,
                data={
                    "tool_name": tool_call.name,
                    "elapsed_seconds": round(tool_elapsed_seconds, 3),
                    "max_tool_call_seconds": config.max_tool_call_seconds,
                },
            ),
            event_callback,
        )
        _append_tool_timeout_message(
            tool_call=tool_call,
            messages=messages,
            events=events,
            event_callback=event_callback,
            step=step,
        )
        return evidence_ledger
    message_result = result
    evidence_ids: list[str] = []
    if evidence_ledger is not None:
        registered = register_tool_result_evidence(
            evidence_ledger,
            tool_name=tool_call.name,
            result=result,
        )
        evidence_ledger = registered.ledger
        message_result = registered.result
        evidence_ids = registered.evidence_ids
    _record_tool_failure_state(
        result=result,
        tool_call=tool_call,
        config=config,
        warnings=warnings,
        events=events,
        event_callback=event_callback,
        step=step,
        tool_failure_counts=tool_failure_counts,
        disabled_tools=disabled_tools,
    )
    _append_event(
        events,
        AgentRuntimeEvent(
            type="tool_result",
            step=step,
            data={
                "tool_name": tool_call.name,
                "status": result.status,
                "error_code": result.error_code,
                "evidence_ids": evidence_ids,
            },
        ),
        event_callback,
    )
    _append_tool_message(messages, tool_call, message_result)
    return evidence_ledger


def _record_tool_failure_state(
    *,
    result: ToolResult,
    tool_call: ToolCall,
    config: AgentRuntimeConfig,
    warnings: list[AgentRuntimeWarning],
    events: list[AgentRuntimeEvent],
    event_callback: RuntimeEventCallback | None,
    step: int,
    tool_failure_counts: dict[str, int],
    disabled_tools: set[str],
) -> None:
    if result.status == "ok":
        tool_failure_counts[tool_call.name] = 0
        return

    failure_count = tool_failure_counts.get(tool_call.name, 0) + 1
    tool_failure_counts[tool_call.name] = failure_count
    if failure_count < config.max_tool_failures or tool_call.name in disabled_tools:
        return

    disabled_tools.add(tool_call.name)
    warnings.append(
        AgentRuntimeWarning(
            code=f"{TOOL_DISABLED_WARNING_PREFIX}:{tool_call.name}",
            message=f"{tool_call.name} disabled after {failure_count} consecutive errors.",
        )
    )
    _append_event(
        events,
        AgentRuntimeEvent(
            type="tool_disabled",
            step=step,
            data={"tool_name": tool_call.name, "failure_count": failure_count},
        ),
        event_callback,
    )


def _append_disabled_tool_message(
    *,
    tool_call: ToolCall,
    messages: list[ChatMessage],
    events: list[AgentRuntimeEvent],
    event_callback: RuntimeEventCallback | None,
    step: int,
) -> None:
    result = ToolResult(
        status="error",
        error_code="tool_disabled",
        error_message=f"{tool_call.name} has been disabled after repeated errors.",
    )
    _append_event(
        events,
        AgentRuntimeEvent(
            type="tool_result",
            step=step,
            data={
                "tool_name": tool_call.name,
                "status": result.status,
                "error_code": result.error_code,
            },
        ),
        event_callback,
    )
    _append_tool_message(messages, tool_call, result)


def _append_writing_phase_tool_message(
    *,
    tool_call: ToolCall,
    messages: list[ChatMessage],
    events: list[AgentRuntimeEvent],
    event_callback: RuntimeEventCallback | None,
    step: int,
) -> None:
    result = ToolResult(
        status="error",
        error_code="tool_unavailable_in_writing_phase",
        error_message=f"{tool_call.name} is unavailable in writing phase; call {FINALIZE_TOOL_NAME}.",
    )
    _append_event(
        events,
        AgentRuntimeEvent(
            type="tool_result",
            step=step,
            data={
                "tool_name": tool_call.name,
                "status": result.status,
                "error_code": result.error_code,
            },
        ),
        event_callback,
    )
    _append_tool_message(messages, tool_call, result)


def _append_budget_exceeded_tool_message(
    *,
    tool_call: ToolCall,
    kind: str,
    messages: list[ChatMessage],
    events: list[AgentRuntimeEvent],
    event_callback: RuntimeEventCallback | None,
    step: int,
) -> None:
    result = ToolResult(
        status="error",
        error_code="budget_exceeded",
        error_message=f"{kind} budget exceeded; continue to finalize with available evidence.",
    )
    _append_event(
        events,
        AgentRuntimeEvent(
            type="tool_result",
            step=step,
            data={
                "tool_name": tool_call.name,
                "status": result.status,
                "error_code": result.error_code,
                "budget_kind": kind,
            },
        ),
        event_callback,
    )
    _append_tool_message(messages, tool_call, result)


def _append_tool_timeout_message(
    *,
    tool_call: ToolCall,
    messages: list[ChatMessage],
    events: list[AgentRuntimeEvent],
    event_callback: RuntimeEventCallback | None,
    step: int,
) -> None:
    result = ToolResult(
        status="error",
        error_code="tool_timeout",
        error_message=f"{tool_call.name} exceeded max_tool_call_seconds; continue with available evidence.",
    )
    _append_event(
        events,
        AgentRuntimeEvent(
            type="tool_result",
            step=step,
            data={
                "tool_name": tool_call.name,
                "status": result.status,
                "error_code": result.error_code,
            },
        ),
        event_callback,
    )
    _append_tool_message(messages, tool_call, result)


def _append_budget_warning(
    warnings: list[AgentRuntimeWarning],
    kind: str,
    message: str,
) -> None:
    code = f"{BUDGET_WARNING_PREFIX}:{kind}"
    if any(warning.code == code for warning in warnings):
        return
    warnings.append(AgentRuntimeWarning(code=code, message=message))


def _append_timeout_warning(
    warnings: list[AgentRuntimeWarning],
    kind: str,
    message: str,
) -> None:
    code = f"timeout:{kind}"
    if any(warning.code == code for warning in warnings):
        return
    warnings.append(AgentRuntimeWarning(code=code, message=message))


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


def _tool_call_message_payload(tool_call: ToolCall) -> dict[str, Any]:
    return {
        "id": tool_call.id,
        "type": "function",
        "function": {
            "name": tool_call.name,
            "arguments": json.dumps(
                tool_call.arguments,
                ensure_ascii=False,
                sort_keys=True,
            ),
        },
    }


def _handle_finalize_attempt(
    *,
    session_id: str,
    budget: AgentBudget,
    warnings: list[AgentRuntimeWarning],
    events: list[AgentRuntimeEvent],
    event_callback: RuntimeEventCallback | None,
    messages: list[ChatMessage],
    tool_call: ToolCall,
    validation_failures: int,
    evidence_ledger: RunEvidenceLedger | None,
    report_generated_at: str,
) -> tuple[AgentSessionResult | None, int]:
    brief_payload = tool_call.arguments.get("brief")
    projected_payload = (
        project_macro_brief_sources_from_ledger(brief_payload, evidence_ledger)
        if evidence_ledger is not None and isinstance(brief_payload, Mapping)
        else brief_payload
    )
    try:
        brief = parse_macro_brief(projected_payload)
    except MacroBriefValidationError as exc:
        findings = exc.to_dict()
        return _handle_finalize_validation_failure(
            session_id=session_id,
            budget=budget,
            warnings=warnings,
            events=events,
            event_callback=event_callback,
            messages=messages,
            tool_call=tool_call,
            validation_failures=validation_failures,
            brief_payload=brief_payload,
            findings=findings,
        )
    if evidence_ledger is not None:
        evidence_findings = validate_macro_brief_claim_evidence(brief, evidence_ledger)
        if evidence_findings:
            return _handle_finalize_validation_failure(
                session_id=session_id,
                budget=budget,
                warnings=warnings,
                events=events,
                event_callback=event_callback,
                messages=messages,
                tool_call=tool_call,
                validation_failures=validation_failures,
                brief_payload=brief_payload,
                findings={
                    "missing": [],
                    "errors": [],
                    "findings": evidence_findings,
                },
            )
        temporal_envelope = build_temporal_envelope(
            evidence_ledger,
            report_generated_at=report_generated_at,
        )
        brief = brief.model_copy(update=temporal_envelope.model_dump(mode="json"))
    _append_event(
        events,
        AgentRuntimeEvent(
            type="macro_brief_validation",
            step=budget.steps_used,
            data={"status": "ok"},
        ),
        event_callback,
    )
    return AgentSessionResult(
        session_id=session_id,
        final_status="ok",
        brief=brief,
        warnings=warnings,
        events=events,
        steps=budget.steps_used,
    ), validation_failures


def _handle_finalize_validation_failure(
    *,
    session_id: str,
    budget: AgentBudget,
    warnings: list[AgentRuntimeWarning],
    events: list[AgentRuntimeEvent],
    event_callback: RuntimeEventCallback | None,
    messages: list[ChatMessage],
    tool_call: ToolCall,
    validation_failures: int,
    brief_payload: Any,
    findings: dict[str, list[str]],
) -> tuple[AgentSessionResult | None, int]:
    _append_event(
        events,
        AgentRuntimeEvent(
            type="macro_brief_validation",
            step=budget.steps_used,
            data={"status": "failed", "findings": findings},
        ),
        event_callback,
    )
    if validation_failures == 0:
        _append_tool_message(
            messages,
            tool_call,
            ToolResult(
                status="error",
                error_code="macro_brief_validation_failed",
                error_message="MacroBrief validation failed; repair and call finalize again.",
            ),
        )
        warnings.append(
            AgentRuntimeWarning(
                code=VALIDATION_RETRY_WARNING,
                message="MacroBrief validation failed once; runtime requested a corrected finalize call.",
            )
        )
        messages.append(
            ChatMessage(
                role="user",
                content=json.dumps(
                    {
                        "macro_brief_validation_error": findings,
                        "instruction": (
                            f"Repair the MacroBrief and call {FINALIZE_TOOL_NAME} again. "
                            "Do not answer in plain text."
                        ),
                    },
                    ensure_ascii=False,
                    sort_keys=True,
                ),
            )
        )
        return None, validation_failures + 1

    warnings.append(
        AgentRuntimeWarning(
            code=VALIDATION_FAILED_WARNING,
            message="MacroBrief validation failed twice; returning partial brief.",
        )
    )
    return AgentSessionResult(
        session_id=session_id,
        final_status="validation_failed",
        partial_brief=brief_payload if isinstance(brief_payload, dict) else None,
        validation_findings=findings,
        warnings=warnings,
        events=events,
        steps=budget.steps_used,
    ), validation_failures + 1


def _append_event(
    events: list[AgentRuntimeEvent],
    event: AgentRuntimeEvent,
    event_callback: RuntimeEventCallback | None,
) -> None:
    events.append(event)
    if event_callback is not None:
        event_callback(event)


__all__ = [
    "AgentBudget",
    "AgentIncomplete",
    "AgentRuntimeConfig",
    "AgentRuntimeEvent",
    "AgentRuntimeWarning",
    "AgentSessionResult",
    "BudgetExceeded",
    "CancellationRequested",
    "RuntimeEventCallback",
    "ToolDisabled",
    "run_agent",
]
