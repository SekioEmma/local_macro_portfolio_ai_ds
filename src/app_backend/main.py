from __future__ import annotations

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

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
from app_backend.services import (
    ai_context_service,
    dashboard_service,
    provider_service,
    storage_service,
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


@app.get("/api/ai/context-preview", response_model=AIContextManifestResponse)
def get_ai_context_preview() -> AIContextManifestResponse:
    return ai_context_service.build_ai_context_manifest()


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
