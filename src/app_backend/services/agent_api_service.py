"""Phase F7 backend service for MacroBrief agent API endpoints."""
from __future__ import annotations

import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from typing import Any
from zoneinfo import ZoneInfo

from app_backend.schemas.agent_api import (
    AgentApiWarning,
    AgentRunRequest,
    AgentRunResponse,
)
from app_backend.services.agent_evidence_pack import EvidencePack, build_evidence_pack
from app_backend.services.agent_evidence_writer import build_evidence_writer_prompt
from app_backend.services.agent_information_plan import (
    build_agent_information_plan,
    information_plan_trace_event,
)
from app_backend.services.agent_runtime import (
    AgentBudget,
    AgentRuntimeConfig,
    AgentRuntimeEvent,
    AgentSessionResult,
    CancellationRequested,
    RuntimeEventCallback,
    run_agent,
)
from app_backend.services.agent_tool_plan_runner import PlannedToolRunResult, run_agent_tool_plan
from app_backend.services.agent_tool_registry import (
    AgentToolRegistry,
    build_f1_read_only_tools,
    make_commodity_quote_tool,
    make_finalize_macro_brief_tool,
    make_quote_dxy_tool,
    make_rag_retrieve_tool,
    make_search_tavily_tool,
)
from app_backend.services.agent_trace_service import AgentTraceEvent, AgentTraceService
from app_backend.services.commodity_quote_service import CommodityQuoteService
from app_backend.services.deepseek_real_transport import DeepSeekRealTransport
from app_backend.services.economic_calendar_service import (
    build_default_economic_calendar_service,
)
from app_backend.services.llm_provider_adapter import LLMProviderAdapter
from app_backend.services.llm_provider_adapter import DeepSeekProviderAdapter
from app_backend.services.holdings_consent_service import (
    HoldingsConsentError,
    HoldingsConsentService,
)
from app_backend.services.holdings_external_context_service import (
    HoldingsContextError,
    HoldingsExternalContextService,
)
from app_backend.services.holdings_output_guard import (
    DISCLOSURE_WARNING_CODE,
    find_holdings_text_disclosures,
)
from app_backend.services.llm_provider_adapter import ProviderChatError
from app_backend.services.local_rag_runtime_factory import build_local_rag_runtime
from app_backend.services.macro_brief_renderer import render_macro_brief_markdown
from app_backend.services.macro_brief_sources import (
    build_macro_brief_source_references,
    filter_macro_brief_sources,
)
from app_backend.services.realtime_quote_service import build_default_realtime_quote_service
from app_backend.services.run_evidence_ledger import RunEvidenceLedger
from app_backend.services.search_execution_service import (
    TavilySearchExecutionService,
    build_default_tavily_search_execution_service,
)
from app_backend.schemas.search_external import SearchRequest, SearchResponse, TavilySearchApiRequest
from app_backend.services import dashboard_service
from data_providers import fred_provider


RuntimeFn = Callable[..., AgentSessionResult]
ProviderFactory = Callable[[], LLMProviderAdapter]
RegistryFactory = Callable[[bool], AgentToolRegistry]
TraceFactory = Callable[[], AgentTraceService]
CurrentDateProvider = Callable[[], date]
_NEW_YORK = ZoneInfo("America/New_York")

_LOCAL_TOOL_NAMES = [
    "dashboard_query",
    "evidence_lookup",
    "quote_etf",
    "treasury_curve",
    "calendar_lookup",
    "rag_retrieve",
    "finalize_macro_brief",
]
_EXTERNAL_TOOL_NAMES = [
    "search_tavily",
    "commodity_quote",
    "quote_dxy",
]


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
    current_date_provider: CurrentDateProvider = lambda: datetime.now(_NEW_YORK).date()
    holdings_consent_service: HoldingsConsentService | None = None
    holdings_context_service: HoldingsExternalContextService | None = None
    enable_evidence_ledger: bool = True
    runtime_config: AgentRuntimeConfig = field(default_factory=AgentRuntimeConfig)
    enabled_tool_names: list[str] | None = None

    def run(
        self,
        request: AgentRunRequest,
        *,
        event_callback: RuntimeEventCallback | None = None,
        cancellation_requested: CancellationRequested | None = None,
    ) -> AgentRunResponse:
        session_id = request.session_id or uuid.uuid4().hex
        tool_names = self.enabled_tool_names or _tool_names_for_request(request)
        plan = build_agent_information_plan(
            user_question=request.user_question,
            tool_names=tool_names,
        )

        holdings_snapshot = self._resolve_holdings_snapshot(request, session_id=session_id)
        if self.provider_factory is None or self.registry_factory is None:
            raise AgentRunUnavailable("agent_runtime_dependencies_not_wired")

        trace_service = self.trace_factory()
        plan_event = information_plan_trace_event(plan)
        if event_callback is not None:
            event_callback(
                AgentRuntimeEvent(
                    type=plan_event.type,
                    step=plan_event.step,
                    data=plan_event.data,
                )
            )
        trace_service.write_event(
            AgentTraceEvent(
                type=plan_event.type,
                session_id=session_id,
                step=plan_event.step,
                data=plan_event.data,
            )
        )

        if request.output_mode == "natural_answer":
            return self._run_planned_natural_answer(
                request=request,
                session_id=session_id,
                tool_names=tool_names,
                plan=plan,
                holdings_snapshot=holdings_snapshot,
                trace_session_id=session_id,
            )

        result = self.runtime_fn(
            session_id=session_id,
            user_question=request.user_question,
            provider=self.provider_factory(),
            tool_registry=self.registry_factory(request.confirm_external_search),
            current_date=self.current_date_provider(),
            tool_names=tool_names,
            include_holdings=request.include_holdings,
            holdings_snapshot=holdings_snapshot,
            config=self.runtime_config,
            trace_service=trace_service,
            event_callback=event_callback,
            evidence_ledger=(
                RunEvidenceLedger(run_id=session_id)
                if self.enable_evidence_ledger
                else None
            ),
            cancellation_requested=cancellation_requested,
            report_generated_at=datetime.now(UTC).isoformat(),
        )
        return _response_from_result(
            request=request,
            result=result,
            plan=plan,
            trace_session_id=session_id,
        )

    def _run_planned_natural_answer(
        self,
        *,
        request: AgentRunRequest,
        session_id: str,
        tool_names: list[str],
        plan: Any,
        holdings_snapshot: dict[str, Any] | None,
        trace_session_id: str,
    ) -> AgentRunResponse:
        del tool_names
        tool_result = run_agent_tool_plan(
            plan=plan.tool_plan,
            tool_registry=self.registry_factory(request.confirm_external_search),
            ledger=RunEvidenceLedger(run_id=session_id) if self.enable_evidence_ledger else None,
            budget=AgentBudget(
                max_steps=max(len(plan.tool_plan.steps) + 2, 4),
                max_search_calls=3 if request.confirm_external_search else 0,
                max_rag_calls=5,
                max_external_quote_calls=5,
                max_tokens_total=40000,
            ),
        )
        evidence_pack = build_evidence_pack(
            ledger=tool_result.ledger,
            outcomes=tool_result.outcomes,
        )
        writer_prompt = build_evidence_writer_prompt(
            user_question=request.user_question,
            current_date=self.current_date_provider(),
            evidence_pack=evidence_pack,
            output_mode="natural_answer",
        )

        warnings = _warnings_from_planned_run(tool_result, evidence_pack)
        final_status = "ok"
        natural_answer = ""
        try:
            writer_response = self.provider_factory().chat(
                model=self.runtime_config.model_name,
                messages=writer_prompt.messages,
                tools=None,
                tool_choice="none",
                response_format=writer_prompt.response_format,
                max_tokens=self.runtime_config.writing_max_tokens_per_call,
            )
            natural_answer = (writer_response.content or "").strip()
        except ProviderChatError as exc:
            final_status = "incomplete"
            warnings.append(
                AgentApiWarning(
                    code=f"provider_error:{exc.kind}",
                    message="自然回答写作调用失败，已保留工具执行状态。",
                )
            )

        if not natural_answer and final_status == "ok":
            final_status = "incomplete"
            warnings.append(
                AgentApiWarning(
                    code="natural_answer_empty",
                    message="写作阶段没有返回可展示回答。",
                )
            )

        findings = find_holdings_text_disclosures(
            output_text=natural_answer,
            holdings_snapshot=holdings_snapshot,
        )
        if findings:
            final_status = "validation_failed"
            natural_answer = ""
            warnings.insert(
                0,
                AgentApiWarning(
                    code=DISCLOSURE_WARNING_CODE,
                    message="自然回答包含持仓明细输出，已阻断。",
                ),
            )

        return AgentRunResponse(
            session_id=session_id,
            final_status=final_status,
            trace_session_id=trace_session_id,
            source_visibility_mode=request.source_visibility_mode,
            rendered_markdown=natural_answer,
            source_markdown=_source_markdown_from_evidence_pack(evidence_pack),
            natural_answer=natural_answer,
            output_mode="natural_answer",
            information_plan=plan,
            warnings=warnings,
            search_required=bool(plan.search_topics),
            missing_topics=plan.missing_topics,
            steps=len(tool_result.outcomes) + (1 if natural_answer else 0),
        )

    def _resolve_holdings_snapshot(
        self,
        request: AgentRunRequest,
        *,
        session_id: str,
    ) -> dict[str, Any] | None:
        if not request.include_holdings:
            if request.holdings_consent_token is not None:
                raise AgentRunInputError("holdings_consent_token_without_include_holdings")
            return None
        if self.holdings_consent_service is None:
            raise AgentRunInputError("holdings_consent_service_not_wired")
        if self.holdings_context_service is None:
            raise AgentRunInputError("holdings_snapshot_backend_not_wired")
        if not self.holdings_context_service.is_wired:
            raise AgentRunInputError("holdings_snapshot_backend_not_wired")
        try:
            self.holdings_consent_service.validate(
                request.holdings_consent_token,
                session_id=session_id,
            )
            snapshot = self.holdings_context_service.load_snapshot(session_id=session_id)
            self.holdings_consent_service.consume(
                request.holdings_consent_token,
                session_id=session_id,
            )
            return snapshot
        except HoldingsConsentError as exc:
            raise AgentRunInputError(exc.code) from exc
        except HoldingsContextError as exc:
            raise AgentRunInputError(exc.code) from exc


def build_unwired_agent_run_service() -> AgentRunService:
    return AgentRunService()


def build_default_agent_run_service(
    *,
    search_service: TavilySearchExecutionService | None = None,
    holdings_consent_service: HoldingsConsentService | None = None,
    holdings_context_service: HoldingsExternalContextService | None = None,
) -> AgentRunService:
    resolved_search_service = search_service or build_default_tavily_search_execution_service()
    runtime_config = AgentRuntimeConfig()
    return AgentRunService(
        provider_factory=lambda: DeepSeekProviderAdapter(
            transport=DeepSeekRealTransport(
                timeout_seconds=runtime_config.max_provider_call_seconds,
            )
        ),
        registry_factory=lambda confirm_external_search: _build_agent_tool_registry(
            confirm_external_search=confirm_external_search,
            search_service=resolved_search_service,
        ),
        holdings_consent_service=holdings_consent_service,
        holdings_context_service=holdings_context_service,
        runtime_config=runtime_config,
    )


def _build_agent_tool_registry(
    *,
    confirm_external_search: bool,
    search_service: TavilySearchExecutionService,
) -> AgentToolRegistry:
    registry = AgentToolRegistry()
    quote_service = build_default_realtime_quote_service()
    calendar_service = build_default_economic_calendar_service()
    build_f1_read_only_tools(
        summary_fn=dashboard_service.build_dashboard_summary,
        evidence_fn=dashboard_service.build_dashboard_evidence_table,
        quote_fn=quote_service.quote_etf,
        curve_fn=quote_service.treasury_curve,
        next_releases_fn=calendar_service.next_releases,
        events_by_name_fn=calendar_service.events_by_name,
    ).register_all(registry)
    registry.register(
        make_rag_retrieve_tool(
            lambda query, top_k=5, doc_type_filter=None, include_local_only=False: (
                build_local_rag_runtime().retrieval_service.retrieve(
                    query,
                    top_k=top_k,
                    doc_type_filter=doc_type_filter,
                    include_local_only=include_local_only,
                )
            )
        )
    )
    if confirm_external_search:
        registry.register(make_search_tavily_tool(search_service.execute))
        commodity_service = CommodityQuoteService(
            search_callable=_build_commodity_search_callable(search_service)
        )
        registry.register(make_commodity_quote_tool(commodity_service.quote))
        registry.register(make_quote_dxy_tool(fred_provider.get_fred_series))
    registry.register(make_finalize_macro_brief_tool())
    return registry


def _build_commodity_search_callable(
    search_service: TavilySearchExecutionService,
):
    def _search(request: SearchRequest) -> SearchResponse:
        return search_service.execute(
            TavilySearchApiRequest(
                query=request.query,
                max_results=request.max_results,
                domain_filter=list(request.domain_filter),
                confirm_external_search=True,
            )
        )

    return _search


def _tool_names_for_request(request: AgentRunRequest) -> list[str]:
    names = list(_LOCAL_TOOL_NAMES)
    if request.confirm_external_search:
        names[-1:-1] = _EXTERNAL_TOOL_NAMES
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
        output_mode=request.output_mode,
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


def _warnings_from_planned_run(
    tool_result: PlannedToolRunResult,
    evidence_pack: EvidencePack,
) -> list[AgentApiWarning]:
    warnings: list[AgentApiWarning] = []
    for topic in tool_result.failed_required_topics:
        warnings.append(
            AgentApiWarning(
                code=f"planned_tool_failed:{topic}",
                message="计划工具调用未取得可用结果。",
            )
        )
    for topic in evidence_pack.unavailable_topics:
        if topic not in tool_result.failed_required_topics:
            warnings.append(
                AgentApiWarning(
                    code=f"topic_unavailable:{topic}",
                    message="该主题缺少可用证据。",
                )
            )
    return warnings


def _source_markdown_from_evidence_pack(evidence_pack: EvidencePack) -> str:
    lines: list[str] = []
    for card in evidence_pack.cards:
        if not card.public_visible and card.canonical_url is None:
            continue
        label = card.title
        if card.canonical_url:
            lines.append(f"- [{label}]({card.canonical_url})")
        else:
            lines.append(f"- {label}")
    return "\n".join(lines)


__all__ = [
    "AgentRunInputError",
    "AgentRunService",
    "AgentRunUnavailable",
    "build_default_agent_run_service",
    "build_unwired_agent_run_service",
]
