"""Stage 9.3-A external AI adapter schemas (disabled-by-default skeleton).

All schemas here are internal to the adapter skeleton. They are NOT wired
to any HTTP endpoint in Stage 9.3-A. The real DeepSeek (Stage 9.3-B) and
Tavily (Stage 9.4) work must reuse these contracts and may only extend
them in a backwards-compatible way.

Privacy / boundary policy:
- The request must carry only sanitized AI Context Manifest material.
- No raw prompt, no holdings, no account values, no API keys, no file paths.
- Default mode is "disabled"; "fake" returns deterministic local text.
- "network" mode is reserved for Stage 9.3-B and must fail closed here.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict

from app_backend.schemas.ai_memo import AIMemoValidatorResult


AdapterProvider = Literal["deepseek"]
AdapterMode = Literal["disabled", "fake", "network"]


class ExternalAIAdapterConfig(BaseModel):
    """Disabled-by-default configuration for the external AI adapter.

    Defaults are chosen so that an unconfigured adapter cannot call any
    external model, cannot reach the network, and cannot persist prompts
    or responses.
    """

    model_config = ConfigDict(extra="forbid")

    provider: AdapterProvider = "deepseek"
    enabled: bool = False
    mode: AdapterMode = "disabled"
    allow_network: bool = False
    requires_user_switch: bool = True
    requires_context_preview: bool = True
    requires_validator: bool = True
    save_raw_prompt: bool = False
    save_raw_response: bool = False


class ExternalAIRequest(BaseModel):
    """Sanitized request envelope for the external AI adapter.

    Fields here are the ONLY material that may be sent to a future external
    provider. They are derived from the AI Context Manifest. Any forbidden
    field (raw prompt, holdings, API key, etc.) must be rejected by the
    guard layer before the adapter is invoked.
    """

    model_config = ConfigDict(extra="forbid")

    request_id: str
    provider: AdapterProvider
    mode: AdapterMode
    user_intent_summary: str
    context_preview_summary: str
    included_fact_count: int
    included_model_output_count: int
    excluded_context_summary: str
    boundary_notices: list[str]
    memo_type: str | None = None
    preview_type: str | None = None
    validator_required: bool = True


class ExternalAIPrivacySummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    uses_ai_context_manifest_only: bool
    uses_holdings_line_items: bool
    uses_raw_provider_payloads: bool
    uses_raw_prompts: bool
    external_model_called: bool
    search_called: bool
    saved_by_default: bool


class ExternalAIResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider: AdapterProvider
    mode: AdapterMode
    external_model_called: bool
    fake_response: bool
    content: str
    validator_result: AIMemoValidatorResult
    privacy_summary: ExternalAIPrivacySummary
    not_saved_by_default: bool
    human_review_required: bool


class ExternalAIGuardResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    passed: bool
    findings: list[str]


class ExternalAIRuntimePolicy(BaseModel):
    """Stage 9.3-B-0 runtime approval gate / external AI policy contract.

    This policy is a code-level expression of "may a future real external AI
    call proceed at runtime". Stage 9.3-B-0 does NOT implement the call. The
    default constructed policy is fully fail-closed: every approval gate is
    `False`, every dangerous permission is `False`. The guard function in
    `ai_external_runtime_policy.py` only returns `passed=True` when every
    approval gate is `True` AND every dangerous permission is `False`.

    No API key, env var name, URL, model endpoint, raw prompt, or raw
    response may be stored here. Extra fields are rejected by Pydantic.
    """

    model_config = ConfigDict(extra="forbid")

    provider: AdapterProvider = "deepseek"

    # Approval gates — all must be True for runtime to proceed.
    external_ai_enabled: bool = False
    provider_network_enabled: bool = False
    user_controlled_switch_enabled: bool = False
    single_request_user_approved: bool = False
    context_preview_confirmed: bool = False
    request_built_from_manifest: bool = False
    request_guard_passed: bool = False
    response_guard_required: bool = True
    stage9_validator_required: bool = True
    human_review_required: bool = True

    # Dangerous permissions — all must be False for runtime to proceed.
    save_raw_prompt: bool = False
    save_raw_response: bool = False
    persist_chat_by_default: bool = False
    allow_search: bool = False
    allow_tavily: bool = False
    allow_background_call: bool = False
    allow_app_start_call: bool = False
    allow_page_load_call: bool = False
    allow_holdings_line_items: bool = False
    allow_account_values: bool = False
    allow_position_weights: bool = False
    allow_transaction_history: bool = False

    policy_version: str = "stage9_3b_0"


def default_external_ai_runtime_policy() -> ExternalAIRuntimePolicy:
    """Return a fully fail-closed default runtime policy.

    Every approval gate is False; every dangerous permission is False.
    The required-flag gates (`response_guard_required`,
    `stage9_validator_required`, `human_review_required`) are True so that
    when a future policy is constructed to "may proceed" status, those
    requirements remain on.
    """
    return ExternalAIRuntimePolicy()


__all__ = [
    "AdapterProvider",
    "AdapterMode",
    "ExternalAIAdapterConfig",
    "ExternalAIRequest",
    "ExternalAIPrivacySummary",
    "ExternalAIResponse",
    "ExternalAIGuardResult",
    "ExternalAIRuntimePolicy",
    "default_external_ai_runtime_policy",
]
