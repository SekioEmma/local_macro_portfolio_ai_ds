from __future__ import annotations

from fastapi import FastAPI

from app_backend.schemas.responses import StatusResponse
from app_backend.services.status_service import build_status


app = FastAPI(title="Local Macro Portfolio AI DS App Backend")


@app.get("/api/status", response_model=StatusResponse)
def get_status() -> StatusResponse:
    return build_status()
