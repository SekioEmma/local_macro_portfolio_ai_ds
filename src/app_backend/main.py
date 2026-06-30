from __future__ import annotations

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from app_backend.schemas.agent_api import AgentRunRequest, AgentRunResponse
from app_backend.schemas.ai_preview import (
    AIContextPreviewResponse,
    AIDeepSeekResearchRequest,
    AIDeepSeekResearchResponse,
    AIPromptPreviewRequest,
    AIPromptPreviewResponse,
    AIPreviewChatRequest,
    AIPreviewChatResponse,
    AIPreviewMemoRequest,
    AIPreviewMemoResponse,
    AIPreviewReportRequest,
    AIResearchPreviewRequest,
    AIResearchPreviewResponse,
)
from app_backend.schemas.responses import (
    AIContextManifestResponse,
    AppSettingsResponse,
    CreateFavoriteAnswerRequest,
    CreateRefreshRunRequest,
    DashboardEvidenceTableResponse,
    DashboardSummaryResponse,
    FavoriteAnswer,
    ProviderHealthResponse,
    RefreshRun,
    StatusResponse,
    StorageStatusResponse,
    UpdateAppSettingsRequest,
)
from app_backend.schemas.commodity_quote import CommodityQuoteSnapshot
from app_backend.schemas.realtime_quote import (
    FxSnapshot,
    QuoteSnapshot,
    YieldCurveSnapshot,
)
from app_backend.schemas.search_external import (
    SearchRequest,
    SearchResponse,
    TavilySearchApiRequest,
)
from app_backend.services import (
    ai_context_service,
    ai_deepseek_research_service,
    ai_preview_service,
    dashboard_service,
    provider_service,
    storage_service,
)
from app_backend.services.agent_api_service import (
    AgentRunInputError,
    AgentRunService,
    AgentRunUnavailable,
    build_unwired_agent_run_service,
)
from app_backend.services.commodity_quote_service import CommodityQuoteService
from app_backend.services.realtime_quote_service import (
    RealtimeQuoteService,
    build_default_realtime_quote_service,
)
from app_backend.services.search_execution_service import (
    TavilySearchExecutionService,
    build_default_tavily_search_execution_service,
)
from app_backend.services.status_service import build_status


ALLOWED_CORS_ORIGINS = ("http://127.0.0.1:5173", "http://localhost:5173")

app = FastAPI(title="Local Macro Portfolio AI DS App Backend")
app.add_middleware(
    CORSMiddleware,
    allow_origins=list(ALLOWED_CORS_ORIGINS),
    allow_credentials=False,
    allow_methods=["GET", "PUT", "POST"],
    allow_headers=["*"],
)


@app.get("/api/status", response_model=StatusResponse)
def get_status() -> StatusResponse:
    return build_status()


@app.get("/api/provider-health", response_model=ProviderHealthResponse)
def get_provider_health() -> ProviderHealthResponse:
    return provider_service.build_provider_health()


@app.get("/api/dashboard/summary", response_model=DashboardSummaryResponse)
def get_dashboard_summary() -> DashboardSummaryResponse:
    return dashboard_service.build_dashboard_summary()


@app.get(
    "/api/dashboard/evidence-table",
    response_model=DashboardEvidenceTableResponse,
)
def get_dashboard_evidence_table(
    module: str | None = Query(default=None),
    status: str | None = Query(default=None),
    source_badge: str | None = Query(default=None),
    ai_context_allowed: bool | None = Query(default=None),
) -> DashboardEvidenceTableResponse:
    return dashboard_service.build_dashboard_evidence_table(
        module=module,
        status=status,
        source_badge=source_badge,
        ai_context_allowed=ai_context_allowed,
    )


@app.get("/api/ai/context-preview", response_model=AIContextPreviewResponse)
def get_ai_context_preview() -> AIContextPreviewResponse:
    return ai_preview_service.build_context_preview()


@app.post("/api/ai/preview-chat", response_model=AIPreviewChatResponse)
def post_ai_preview_chat(request: AIPreviewChatRequest) -> AIPreviewChatResponse:
    return ai_preview_service.render_chat_preview(request)


@app.post("/api/ai/preview-memo", response_model=AIPreviewMemoResponse)
def post_ai_preview_memo(request: AIPreviewMemoRequest) -> AIPreviewMemoResponse:
    return ai_preview_service.render_memo_preview(request)


@app.post("/api/ai/preview-report", response_model=AIPreviewMemoResponse)
def post_ai_preview_report(request: AIPreviewReportRequest) -> AIPreviewMemoResponse:
    return ai_preview_service.render_report_preview(request)


@app.post("/api/ai/research-preview", response_model=AIResearchPreviewResponse)
def post_ai_research_preview(
    request: AIResearchPreviewRequest,
) -> AIResearchPreviewResponse:
    return ai_preview_service.render_research_preview(request)


@app.post("/api/ai/prompt-preview", response_model=AIPromptPreviewResponse)
def post_ai_prompt_preview(
    request: AIPromptPreviewRequest,
) -> AIPromptPreviewResponse:
    return ai_preview_service.render_prompt_preview(request)


@app.post(
    "/api/ai/research-deepseek",
    response_model=AIDeepSeekResearchResponse,
)
def post_ai_research_deepseek(
    request: AIDeepSeekResearchRequest,
) -> AIDeepSeekResearchResponse:
    try:
        return ai_deepseek_research_service.run_deepseek_research(request)
    except Exception as exc:
        raise HTTPException(status_code=500, detail="deepseek_research_unavailable") from exc


@app.get("/api/context/manifest", response_model=AIContextManifestResponse)
def get_context_manifest() -> AIContextManifestResponse:
    return ai_context_service.build_ai_context_manifest()


@app.get("/api/app/storage", response_model=StorageStatusResponse)
def get_app_storage() -> StorageStatusResponse:
    return storage_service.storage_status()


@app.get("/api/app/settings", response_model=AppSettingsResponse)
def get_app_settings() -> AppSettingsResponse:
    try:
        return storage_service.get_settings()
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.put("/api/app/settings", response_model=AppSettingsResponse)
def put_app_settings(request: UpdateAppSettingsRequest) -> AppSettingsResponse:
    try:
        return storage_service.update_settings(request)
    except storage_service.AppStateInputError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/api/app/refresh-runs", response_model=list[RefreshRun])
def get_refresh_runs() -> list[RefreshRun]:
    try:
        return storage_service.list_refresh_runs()
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/api/app/refresh-runs", response_model=RefreshRun)
def post_refresh_run(request: CreateRefreshRunRequest) -> RefreshRun:
    try:
        return storage_service.create_refresh_run(request)
    except storage_service.AppStateInputError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/api/app/favorites", response_model=list[FavoriteAnswer])
def get_favorites() -> list[FavoriteAnswer]:
    try:
        return storage_service.list_favorites()
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/api/app/favorites", response_model=FavoriteAnswer)
def post_favorite(request: CreateFavoriteAnswerRequest) -> FavoriteAnswer:
    try:
        return storage_service.create_favorite(request)
    except storage_service.AppStateInputError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


# ---------------------------------------------------------------------------
# B7 guarded local routes (search + read-only quotes).
#
# All calls are explicit user HTTP requests. There is no automatic refresh,
# background task, app-start call, or page-load call. Importing this module
# reads no config, env, database, or network; the realtime quote service is
# built per request and the search execution service is a process-local
# singleton whose construction touches nothing.
# ---------------------------------------------------------------------------

_SEARCH_EXECUTION_SERVICE = build_default_tavily_search_execution_service()
_AGENT_RUN_SERVICE = build_unwired_agent_run_service()


def get_realtime_quote_service() -> RealtimeQuoteService:
    return build_default_realtime_quote_service()


def get_tavily_search_execution_service() -> TavilySearchExecutionService:
    return _SEARCH_EXECUTION_SERVICE


def get_agent_run_service() -> AgentRunService:
    return _AGENT_RUN_SERVICE


def _build_commodity_search_callable(
    search_service: TavilySearchExecutionService,
):
    """Request-scoped callable for the commodity endpoint.

    The endpoint itself is the explicit user request, so the callable fixes
    confirm_external_search=true. Every other gate (config, sanitizer,
    allowlist, budget, runtime policy, adapter, transport, response guard)
    still applies inside the execution service.
    """

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


@app.post("/api/search/tavily", response_model=SearchResponse)
def post_search_tavily(
    request: TavilySearchApiRequest,
    service: TavilySearchExecutionService = Depends(
        get_tavily_search_execution_service
    ),
) -> SearchResponse:
    try:
        return service.execute(request)
    except Exception:
        return SearchResponse(
            results=[], search_available=False, guard_passed=False
        )


@app.post("/api/agent/run", response_model=AgentRunResponse)
def post_agent_run(
    request: AgentRunRequest,
    service: AgentRunService = Depends(get_agent_run_service),
) -> AgentRunResponse:
    try:
        return service.run(request)
    except AgentRunInputError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except AgentRunUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=503, detail="agent_run_unavailable") from exc


@app.get("/api/quote/etf", response_model=list[QuoteSnapshot])
def get_quote_etf(
    symbols: list[str] = Query(...),
    service: RealtimeQuoteService = Depends(get_realtime_quote_service),
) -> list[QuoteSnapshot]:
    try:
        return service.quote_etf(symbols)
    except ValueError as exc:
        raise HTTPException(
            status_code=422, detail="unsupported_symbol"
        ) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=503, detail="quote_service_unavailable"
        ) from exc


@app.get("/api/quote/treasury_curve", response_model=YieldCurveSnapshot)
def get_quote_treasury_curve(
    date: str | None = Query(default=None),
    curve_kind: str = Query(default="nominal_treasury"),
    service: RealtimeQuoteService = Depends(get_realtime_quote_service),
) -> YieldCurveSnapshot:
    if curve_kind == "nominal_treasury":
        method = service.treasury_curve
    elif curve_kind == "tips_real_yield":
        method = service.tips_curve
    else:
        raise HTTPException(status_code=422, detail="unsupported_curve_kind")
    try:
        return method(date)
    except ValueError as exc:
        raise HTTPException(
            status_code=422, detail="invalid_curve_request"
        ) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=503, detail="quote_service_unavailable"
        ) from exc


@app.get("/api/quote/fx", response_model=FxSnapshot)
def get_quote_fx(
    pair: str = Query(default="USDCNH"),
    service: RealtimeQuoteService = Depends(get_realtime_quote_service),
) -> FxSnapshot:
    try:
        return service.fx_rate(pair)
    except Exception as exc:
        raise HTTPException(
            status_code=503, detail="quote_service_unavailable"
        ) from exc


@app.get("/api/quote/commodity", response_model=CommodityQuoteSnapshot)
def get_quote_commodity(
    benchmark: str = Query(default="brent"),
    search_service: TavilySearchExecutionService = Depends(
        get_tavily_search_execution_service
    ),
) -> CommodityQuoteSnapshot:
    service = CommodityQuoteService(
        search_callable=_build_commodity_search_callable(search_service)
    )
    try:
        return service.quote(benchmark)
    except Exception as exc:
        raise HTTPException(
            status_code=503, detail="quote_service_unavailable"
        ) from exc
