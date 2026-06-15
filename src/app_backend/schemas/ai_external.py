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


__all__ = [
    "AdapterProvider",
    "AdapterMode",
    "ExternalAIAdapterConfig",
    "ExternalAIRequest",
    "ExternalAIPrivacySummary",
    "ExternalAIResponse",
    "ExternalAIGuardResult",
]
