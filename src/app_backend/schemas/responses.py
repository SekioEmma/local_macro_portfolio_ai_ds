from __future__ import annotations

from typing import Any

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


class DashboardMetric(BaseModel):
    metric_key: str
    display_name: str
    value: float | str | bool | None
    value_text: str
    unit: str | None
    status: str
    source: str | None
    source_badge: str
    source_series: str | None = None
    observation_date: str | None
    generated_at: str | None
    freshness_status: str
    missing_reason: str | None
    interpretation_hint: str | None
    ai_context_allowed: bool
    input_evidence: list[dict[str, Any]] | None = None
    component_contributions: dict[str, Any] | None = None
    missing_inputs: list[str] | None = None
    interpretation_boundary: str | None = None
    lookback_window: str | None = None
    lookback_start: str | None = None
    lookback_end: str | None = None
    observation_count: int | None = None
    minimum_observation_count: int | None = None
    history_quality_status: str | None = None
    percentile: float | None = None
    percentile_band: str | None = None
    zscore: float | None = None
    zscore_band: str | None = None
    robust_zscore: float | None = None
    robust_zscore_band: str | None = None
    percentile_direction: str | None = None
    frequency_class: str | None = None
    transform_class: str | None = None
    ai_context_tier: str | None = None
    trigger_eligibility: str | None = None


class DashboardModule(BaseModel):
    key: str
    status: str
    label: str | None
    summary: str | None
    source_badge: str | None
    updated_at: str | None
    next_action: str | None
    error_summary: str | None
    key_metrics: list[DashboardMetric]


class DashboardSummaryResponse(BaseModel):
    generated_at: str | None
    overall_status: str
    overall_risk_level: str | None
    modules: dict[str, DashboardModule]
    provider_health: dict
    missing_data: list[dict]
    data_freshness: dict
    next_actions: list[str]


class DashboardEvidenceRow(BaseModel):
    row_id: str
    module: str
    metric_key: str
    display_name: str
    value: float | str | bool | None
    value_text: str
    unit: str | None
    status: str
    source: str | None
    source_badge: str
    source_series: str | None = None
    observation_date: str | None
    generated_at: str | None
    freshness_status: str
    missing_reason: str | None
    interpretation_hint: str | None
    blocked_reason: str | None = None
    ai_context_allowed: bool
    input_evidence: list[dict[str, Any]] | None = None
    component_contributions: dict[str, Any] | None = None
    missing_inputs: list[str] | None = None
    interpretation_boundary: str | None = None
    lookback_window: str | None = None
    lookback_start: str | None = None
    lookback_end: str | None = None
    observation_count: int | None = None
    minimum_observation_count: int | None = None
    history_quality_status: str | None = None
    percentile: float | None = None
    percentile_band: str | None = None
    zscore: float | None = None
    zscore_band: str | None = None
    robust_zscore: float | None = None
    robust_zscore_band: str | None = None
    percentile_direction: str | None = None
    frequency_class: str | None = None
    transform_class: str | None = None
    ai_context_tier: str | None = None
    trigger_eligibility: str | None = None


class DashboardEvidenceTableResponse(BaseModel):
    generated_at: str | None
    overall_status: str
    row_count: int
    modules: list[str]
    rows: list[DashboardEvidenceRow]
    filters: dict[str, Any]
    next_actions: list[str]


class AIContextManifestResponse(BaseModel):
    generated_at: str | None
    included_facts: list[dict[str, Any]]
    excluded_facts: list[dict[str, Any]]
    included_model_outputs: list[dict[str, Any]]
    excluded_model_outputs: list[dict[str, Any]]
    portfolio_context_policy: dict[str, Any]
    privacy_policy: dict[str, Any]
    search_policy: dict[str, Any]
    model_destination: dict[str, Any]
    persistence_policy: dict[str, Any]
    risk_boundaries: list[str]
    source_summary: dict[str, Any]


class StorageStatusResponse(BaseModel):
    storage_mode: str
    database_exists: bool
    schema_version: int | None
    initialized: bool
    error_summary: str | None


class AppSettingsResponse(BaseModel):
    settings: dict[str, Any]
    updated_at: str | None


class UpdateAppSettingsRequest(BaseModel):
    settings: dict[str, Any]


class RefreshRun(BaseModel):
    id: int
    kind: str
    status: str
    started_at: str
    finished_at: str | None
    summary: dict[str, Any]
    error_summary: str | None
    created_at: str


class CreateRefreshRunRequest(BaseModel):
    kind: str
    status: str
    started_at: str
    finished_at: str | None = None
    summary: dict[str, Any] | None = None
    error_summary: str | None = None


class FavoriteAnswer(BaseModel):
    id: int
    title: str | None
    question: str
    answer: str
    model: str | None
    context_snapshot: dict[str, Any]
    created_at: str


class CreateFavoriteAnswerRequest(BaseModel):
    title: str | None = None
    question: str
    answer: str
    model: str | None = None
    context_snapshot: dict[str, Any] | None = None
