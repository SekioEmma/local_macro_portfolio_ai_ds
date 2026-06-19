from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from app_backend.schemas.ai_memo import (
    AIMemoContextUsedSummary,
    AIMemoPreview,
    AIMemoPrivacySummary,
    AIMemoSection,
    AIMemoValidatorResult,
)
from app_backend.schemas.responses import AIContextManifestResponse


AnswerMode = Literal[
    "daily_brief",
    "risk_review",
    "scenario_review",
    "portfolio_overlay",
    "evidence_audit",
    "research_memo",
]
DetailLevel = Literal["brief", "standard", "deep"]
ValidationSeverity = Literal["info", "warning", "error", "blocker"]


class AIContextCard(BaseModel):
    model_config = ConfigDict(extra="allow")

    card_type: str
    module: str
    module_display_zh: str
    metric_key: str
    display_name: str
    priority: int
    priority_label_zh: str
    value_text: str | None = None
    status: str | None = None
    status_display_zh: str | None = None
    source_badge: str | None = None
    source_badge_display_zh: str | None = None
    freshness_status: str | None = None
    freshness_display_zh: str | None = None
    observation_date: str | None = None
    interpretation_hint: str | None = None
    interpretation_boundary: str | None = None
    trigger_eligibility: str | None = None
    trigger_eligibility_display_zh: str | None = None
    support_band: str | None = None
    severity_band: str | None = None
    uncertainty_band: str | None = None
    evidence_quality_band: str | None = None
    conflict_band: str | None = None
    missing_input_count: int | None = None
    excluded_reason: str | None = None
    excluded_reason_display_zh: str | None = None
    effect_zh: str | None = None
    boundary_notice_zh: str


class AIFullContextCatalogue(BaseModel):
    evidence_cards: list[AIContextCard]
    model_output_cards: list[AIContextCard]
    excluded_constraint_cards: list[AIContextCard]
    total_card_count: int
    priority_counts: dict[str, int]
    source_badge_distribution: dict[str, int]
    excluded_reason_distribution: dict[str, int]


class AIConstraintSummary(BaseModel):
    total_count: int
    excluded_reason_distribution: dict[str, int]
    module_distribution: dict[str, int]
    freshness_distribution: dict[str, int]
    summary_zh: str


class AIPromptBudgetSummary(BaseModel):
    card_limit: int
    char_limit: int
    estimated_token_limit: int
    selected_card_count: int
    selected_char_count: int
    estimated_token_count: int
    omitted_card_count: int
    omitted_by_priority: dict[str, int]
    omitted_by_reason: dict[str, int]
    ready: bool
    status_reason: str


class AISelectedPromptContext(BaseModel):
    selected_cards: list[AIContextCard]
    constraint_summary: AIConstraintSummary
    selected_context_text: str
    selection_notes: list[str]


class AISemanticFinding(BaseModel):
    code: str
    category: str
    severity: ValidationSeverity
    message_zh: str
    matched_claims: list[str] = Field(default_factory=list)
    cited_context_ids: list[str] = Field(default_factory=list)
    required_context: list[str] = Field(default_factory=list)


class AIResearchValidationResult(BaseModel):
    passed: bool
    blocked: bool
    max_severity: ValidationSeverity | None
    findings: list[AISemanticFinding]
    domain_checks: dict[str, str]


class AIResearchSection(BaseModel):
    key: Literal[
        "current_conclusion",
        "supporting_evidence",
        "counter_evidence",
        "data_constraints",
        "macro_explanation",
        "portfolio_channels",
        "watchlist_and_boundaries",
    ]
    title: str
    content: str
    source_context: list[str]
    claim_tags: list[str]


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
    full_context_catalogue: AIFullContextCatalogue
    priority_counts: dict[str, int]
    excluded_reason_distribution: dict[str, int]


class AIResearchPreviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    answer_mode: AnswerMode = "risk_review"
    detail_level: DetailLevel = "standard"


class AIPromptPreviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    answer_mode: AnswerMode = "risk_review"
    detail_level: DetailLevel = "standard"


class AIResearchPreviewResponse(BaseModel):
    mode: Literal["local_controlled_research_preview"]
    answer_mode: AnswerMode
    legacy_memo_type: str
    detail_level: DetailLevel
    title: str
    answer_preview: str
    research_sections: list[AIResearchSection]
    selected_prompt_context: AISelectedPromptContext
    prompt_budget: AIPromptBudgetSummary
    context_used_summary: AIMemoContextUsedSummary
    privacy_summary: AIMemoPrivacySummary
    validator_result: AIMemoValidatorResult
    semantic_validator_result: AIResearchValidationResult
    not_sent_to_external_model: bool
    human_review_required: bool
    interpretation_boundary: str


class AIPromptPreviewResponse(BaseModel):
    mode: Literal["local_prompt_preview"]
    status: Literal["ready", "not_ready"]
    answer_mode: AnswerMode
    legacy_memo_type: str
    detail_level: DetailLevel
    system_boundary: str
    task_instruction: str
    selected_prompt_context: AISelectedPromptContext
    output_contract: list[str]
    preflight_checklist: list[str]
    prompt_budget: AIPromptBudgetSummary
    prompt_text: str
    semantic_validator_result: AIResearchValidationResult
    not_sent_to_external_model: bool
    search_called: bool
    saved_by_default: bool


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
    answer_mode: AnswerMode | None = None
    research_sections: list[AIResearchSection] = Field(default_factory=list)
    selected_prompt_context: AISelectedPromptContext | None = None
    prompt_budget: AIPromptBudgetSummary | None = None
    semantic_validator_result: AIResearchValidationResult | None = None


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
    answer_mode: AnswerMode | None = None
    research_sections: list[AIResearchSection] = Field(default_factory=list)
    selected_prompt_context: AISelectedPromptContext | None = None
    prompt_budget: AIPromptBudgetSummary | None = None
    semantic_validator_result: AIResearchValidationResult | None = None


class AIDeepSeekResearchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    answer_mode: AnswerMode = "risk_review"
    detail_level: DetailLevel = "standard"
    user_question: str = Field(
        ..., min_length=2, max_length=500,
        description="用户的宏观研究问题（中文或英文）",
    )


class AIDeepSeekClaimMetadata(BaseModel):
    """Structured claim_type and threshold_source metadata extracted from DS output."""
    claim_type_counts: dict[str, int] = Field(default_factory=dict)
    threshold_source_counts: dict[str, int] = Field(default_factory=dict)
    total_claims: int = 0


class AIDeepSeekResearchResponse(BaseModel):
    mode: Literal["deepseek_single_turn"]
    answer_mode: AnswerMode
    detail_level: DetailLevel
    user_question: str
    deepseek_raw_output: str
    deepseek_memo_output: str = ""
    claim_metadata: AIDeepSeekClaimMetadata = Field(
        default_factory=AIDeepSeekClaimMetadata
    )
    finish_reason: str
    selected_prompt_context: AISelectedPromptContext
    prompt_budget: AIPromptBudgetSummary
    prompt_text: str
    context_used_summary: AIMemoContextUsedSummary
    privacy_summary: AIMemoPrivacySummary
    validator_result: AIMemoValidatorResult
    semantic_validator_result: AIResearchValidationResult
    input_validation_passed: bool
    input_validation_findings: list[str]
    output_blocked: bool
    human_review_required: bool = True
    interpretation_boundary: str
    elapsed_seconds: float | None = None
    model_provider: str = "deepseek"
    not_saved_by_default: bool = True
