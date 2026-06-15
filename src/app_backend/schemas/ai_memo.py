from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class AIMemoSection(BaseModel):
    key: str
    title: str
    content: str
    source_context: list[str]


class AIMemoContextUsedSummary(BaseModel):
    included_fact_count: int
    excluded_fact_count: int
    included_model_output_count: int
    excluded_model_output_count: int


class AIMemoPrivacySummary(BaseModel):
    uses_ai_context_manifest_only: bool
    uses_holdings_line_items: bool
    uses_raw_provider_payloads: bool
    uses_raw_prompts: bool
    external_model_called: bool
    search_called: bool
    saved_by_default: bool


class AIMemoValidatorResult(BaseModel):
    passed: bool
    blocked_terms: list[str]
    privacy_findings: list[str]


class AIMemoPreview(BaseModel):
    memo_type: str
    mode: str
    title: str
    sections: list[AIMemoSection]
    context_used_summary: AIMemoContextUsedSummary
    privacy_summary: AIMemoPrivacySummary
    validator_result: AIMemoValidatorResult
    human_review_required: bool
    interpretation_boundary: str

    def as_dict(self) -> dict[str, Any]:
        if hasattr(self, "model_dump"):
            return self.model_dump()
        return self.dict()
