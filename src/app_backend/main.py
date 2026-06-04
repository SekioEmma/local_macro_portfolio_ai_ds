from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app_backend.schemas.responses import (
    DashboardSummaryResponse,
    ProviderHealthResponse,
    StatusResponse,
)
from app_backend.services import dashboard_service, provider_service
from app_backend.services.status_service import build_status


ALLOWED_CORS_ORIGINS = ("http://127.0.0.1:5173", "http://localhost:5173")

app = FastAPI(title="Local Macro Portfolio AI DS App Backend")
app.add_middleware(
    CORSMiddleware,
    allow_origins=list(ALLOWED_CORS_ORIGINS),
    allow_credentials=False,
    allow_methods=["GET"],
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
