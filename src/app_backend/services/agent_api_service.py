"""Phase F7 backend service for MacroBrief agent API endpoints."""
from __future__ import annotations

import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from typing import Any

from app_backend.schemas.agent_api import (
    AgentApiWarning,
    AgentRunRequest,
    AgentRunResponse,
)
from app_backend.services.agent_information_plan import (
    build_agent_information_plan,
    information_plan_trace_event,
)
from app_backend.services.agent_runtime import AgentSessionResult, run_agent
from app_backend.services.agent_tool_registry import AgentToolRegistry
from app_backend.services.agent_trace_service import AgentTraceEvent, AgentTraceService
from app_backend.services.llm_provider_adapter import LLMProviderAdapter
from app_backend.services.macro_brief_renderer import render_macro_brief_markdown
from app_backend.services.macro_brief_sources import (
    build_macro_brief_source_references,
    filter_macro_brief_sources,
)


RuntimeFn = Callable[..., AgentSessionResult]
ProviderFactory = Callable[[], LLMProviderAdapter]
RegistryFactory = Callable[[bool], AgentToolRegistry]
TraceFactory = Callable[[], AgentTraceService]

_LOCAL_TOOL_NAMES = [
    "dashboard_query",
    "evidence_lookup",
    "quote_etf",
    "treasury_curve",
    "calendar_lookup",
    "rag_retrieve",
    "commodity_quote",
    "portfolio_overlay",
    "quote_dxy",
    "finalize_macro_brief",
]
_SEARCH_TOOL_NAME = "search_tavily"


class AgentRunUnavailable(RuntimeError):
    """Raised when the API endpoint is installed but runtime dependencies are not."""


class AgentRunInputError(ValueError):
    """Raised when a request asks for a mode that is not wired yet."""


@dataclass(frozen=True)
class AgentRunService:
    provider_factory: ProviderFactory | None = None
    registry_factory: RegistryFactory | None = None
    trace_factory: TraceFactory = AgentTraceService
    runtime_fn: RuntimeFn = run_agent

    def run(self, request: AgentRunRequest) -> AgentRunResponse:
        session_id = request.session_id or uuid.uuid4().hex
        tool_names = _tool_names_for_request(request)
        plan = build_agent_information_plan(
            user_question=request.user_question,
            tool_names=tool_names,
        )

        if request.include_holdings:
            raise AgentRunInputError("holdings_toggle_backend_not_wired")
        if self.provider_factory is None or self.registry_factory is None:
            raise AgentRunUnavailable("agent_runtime_dependencies_not_wired")

        trace_service = self.trace_factory()
        plan_event = information_plan_trace_event(plan)
        trace_service.write_event(
            AgentTraceEvent(
                type=plan_event.type,
                session_id=session_id,
                step=plan_event.step,
                data=plan_event.data,
            )
        )

        result = self.runtime_fn(
            session_id=session_id,
            user_question=request.user_question,
            provider=self.provider_factory(),
            tool_registry=self.registry_factory(request.confirm_external_search),
            current_date=request.current_date or date.today(),
            tool_names=tool_names,
            include_holdings=False,
            trace_service=trace_service,
        )
        return _response_from_result(
            request=request,
            result=result,
            plan=plan,
            trace_session_id=session_id,
        )


def build_unwired_agent_run_service() -> AgentRunService:
    return AgentRunService()


def _tool_names_for_request(request: AgentRunRequest) -> list[str]:
    names = list(_LOCAL_TOOL_NAMES)
    if request.confirm_external_search:
        names.insert(-1, _SEARCH_TOOL_NAME)
    return names


def _response_from_result(
    *,
    request: AgentRunRequest,
    result: AgentSessionResult,
    plan: Any,
    trace_session_id: str,
) -> AgentRunResponse:
    rendered_markdown = ""
    source_markdown = ""
    sources = []
    brief_payload = None
    if result.brief is not None:
        render_result = render_macro_brief_markdown(
            result.brief,
            visibility_mode=request.source_visibility_mode,
            runtime_events=result.events,
        )
        rendered_markdown = render_result.markdown
        source_markdown = render_result.source_markdown
        references = build_macro_brief_source_references(
            result.brief,
            runtime_events=result.events,
        )
        sources = filter_macro_brief_sources(
            references,
            visibility_mode=request.source_visibility_mode,
        )
        brief_payload = result.brief.model_dump(mode="json")

    return AgentRunResponse(
        session_id=result.session_id,
        final_status=result.final_status,
        trace_session_id=trace_session_id,
        source_visibility_mode=request.source_visibility_mode,
        brief=brief_payload,
        partial_brief=result.partial_brief,
        rendered_markdown=rendered_markdown,
        source_markdown=source_markdown,
        sources=sources,
        information_plan=plan,
        warnings=[
            AgentApiWarning(code=warning.code, message=warning.message)
            for warning in result.warnings
        ],
        search_required=bool(plan.search_topics),
        missing_topics=plan.missing_topics,
        steps=result.steps,
    )


__all__ = [
    "AgentRunInputError",
    "AgentRunService",
    "AgentRunUnavailable",
    "build_unwired_agent_run_service",
]
