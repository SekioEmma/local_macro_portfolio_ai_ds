from __future__ import annotations

from pydantic import BaseModel


class StatusResponse(BaseModel):
    app_name: str
    mode: str
    storage_mode: str
    api_keys_configured: dict[str, bool]
    privacy_boundaries: list[str]
    project_root_exists: bool


class ProviderHealthCheck(BaseModel):
    key: str
    provider: str
    status: str
    source: str | None
    observation_date: str | None
    value_present: bool | None
    error_type: str | None
    error_summary: str | None


class ProviderHealthResponse(BaseModel):
    generated_at: str | None
    overall_status: str
    summary: dict
    checks: list[ProviderHealthCheck]
    next_action: str | None = None
    error_summary: str | None = None
