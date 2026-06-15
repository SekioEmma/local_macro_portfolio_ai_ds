from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel

from app_backend.schemas.ai_memo import (
    AIMemoContextUsedSummary,
    AIMemoPreview,
    AIMemoPrivacySummary,
    AIMemoSection,
    AIMemoValidatorResult,
)
from app_backend.schemas.responses import AIContextManifestResponse


class AIContextPreviewResponse(AIContextManifestResponse):
    mode: Literal["local_preview"]
    model_destination: dict[str, Any]
    search_enabled: bool
    external_model_called: bool
    search_called: bool
    saved_by_default: bool
    included_fact_count: int
    excluded_fact_count: int
    included_model_output_count: int
    excluded_model_output_count: int
    context_stats: dict[str, Any]
    last_generated_at: str | None


class AIPreviewChatRequest(BaseModel):
    question: str
    style: Literal["natural", "structured"] = "natural"
    context_mode: Literal["full_sanitized", "model_outputs_only", "facts_only"] = "full_sanitized"


class AIPreviewChatResponse(BaseModel):
    mode: Literal["local_preview"]
    answer_preview: str
    sections: list[AIMemoSection]
    context_used_summary: AIMemoContextUsedSummary
    privacy_summary: AIMemoPrivacySummary
    validator_result: AIMemoValidatorResult
    not_sent_to_external_model: bool
    human_review_required: bool
    interpretation_boundary: str


class AIPreviewMemoRequest(BaseModel):
    memo_type: Literal[
        "daily_review_memo",
        "risk_review_memo",
        "scenario_review_memo",
        "portfolio_overlay_review",
    ]
    style: Literal["concise", "detailed"] = "concise"


class AIPreviewReportRequest(BaseModel):
    report_type: Literal["macro_risk_report", "evidence_audit_report"]
    style: Literal["outline", "narrative_preview"] = "outline"


class AIPreviewMemoResponse(AIMemoPreview):
    mode: Literal["local_preview"]
    not_sent_to_external_model: bool
