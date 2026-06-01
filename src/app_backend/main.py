from __future__ import annotations

from fastapi import FastAPI

from app_backend.schemas.responses import (
    DashboardSummaryResponse,
    ProviderHealthResponse,
    StatusResponse,
)
from app_backend.services import dashboard_service, provider_service
from app_backend.services.status_service import build_status


app = FastAPI(title="Local Macro Portfolio AI DS App Backend")


@app.get("/api/status", response_model=StatusResponse)
def get_status() -> StatusResponse:
    return build_status()


@app.get("/api/provider-health", response_model=ProviderHealthResponse)
def get_provider_health() -> ProviderHealthResponse:
    return provider_service.build_provider_health()


@app.get("/api/dashboard/summary", response_model=DashboardSummaryResponse)
def get_dashboard_summary() -> DashboardSummaryResponse:
    return dashboard_service.build_dashboard_summary()
