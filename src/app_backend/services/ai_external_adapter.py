"""Stage 9.3-A external AI adapter base class and guard helpers.

This module defines the internal `ExternalAIAdapter` base class and the
guard functions that fail-closed on unsafe config, unsafe requests, and
unsafe responses. No real network call is made or imported here.

Stage 9.3-A scope:
- adapter base class with a `generate()` method that subclasses must implement
- config / request / response guards
- a `BlockedAdapterError` raised when any guard fails

Stage 9.3-B (real DeepSeek) is NOT implemented here. It must reuse these
guards and the same `ExternalAIRequest` / `ExternalAIResponse` contracts.
"""
from __future__ import annotations

from typing import Any

from app_backend.schemas.ai_external import (
    ExternalAIAdapterConfig,
    ExternalAIGuardResult,
    ExternalAIRequest,
    ExternalAIResponse,
)


# Tokens that must never appear in any request field. These are conservative
# substring checks: if any token shows up in the serialized request, the
# guard fails closed.
FORBIDDEN_REQUEST_TOKENS = (
    # raw prompt / API key surface
    "api_key",
    "api-key",
    "bearer ",
    "sk_live_",
    "sk_test_",
    "deepseek_api_key",
    "tavily_api_key",
    # holdings / account / private content
    "holdings line items",
    "account values",
    "position weights",
    "transaction history",
    "raw provider payload",
    "raw_provider_payload",
    "current_holdings.csv",
    "data/private",
    # local private paths
    "g:\\local_macro_portfolio_ai",
    "/mnt/data",
    "c:\\users\\",
    # config files
    ".env",
    "external_llm.yaml",
)

FORBIDDEN_RESPONSE_OUTPUT_TERMS = (
    "buy",
    "sell",
    "add position",
    "reduce position",
    "clear position",
    "hedge",
    "rebalance",
    "target allocation",
    "target weight",
    "expected return",
    "predicted return",
    "future return",
    "market direction probability",
    "crash probability",
    "recession probability",
    "trade signal",
    "guaranteed",
    "will rise",
    "will fall",
)

FORBIDDEN_RESPONSE_PRIVACY_TOKENS = (
    "api_key",
    "api-key",
    "bearer ",
    "sk_live_",
    "sk_test_",
    "deepseek_api_key",
    "tavily_api_key",
    "holdings line items",
    "account values",
    "position weights",
    "transaction history",
    "raw provider payload",
    "raw_provider_payload",
    "current_holdings.csv",
    "data/private",
    "g:\\local_macro_portfolio_ai",
    "/mnt/data",
    "c:\\users\\",
    ".env",
    "external_llm.yaml",
)

# Field names that, if present in the raw request dict, indicate the caller
# tried to attach a forbidden field rather than just summarized text.
FORBIDDEN_REQUEST_FIELD_NAMES = (
    "raw_prompt",
    "raw_question",
    "api_key",
    "deepseek_api_key",
    "tavily_api_key",
    "holdings",
    "holdings_line_items",
    "account_values",
    "position_weights",
    "transaction_history",
    "raw_provider_payload",
    "raw_manifest",
    "env_value",
    "file_path",
    "local_path",
    "search_results",
)


class BlockedAdapterError(RuntimeError):
    """Raised when a guard rejects a config, request, or response."""

    def __init__(self, findings: list[str]) -> None:
        super().__init__("; ".join(findings) or "blocked")
        self.findings = list(findings)


class ExternalAIAdapter:
    """Base class for any external AI adapter.

    Stage 9.3-A only ships a `FakeDeepSeekAdapter` subclass. Real network
    adapters (Stage 9.3-B / Stage 9.4) must subclass this and call
    `guard_*` helpers before any external call.
    """

    def __init__(self, config: ExternalAIAdapterConfig) -> None:
        guard = guard_config(config)
        if not guard.passed:
            raise BlockedAdapterError(guard.findings)
        self.config = config

    def generate(self, request: ExternalAIRequest) -> ExternalAIResponse:
        raise NotImplementedError(
            "Subclasses must implement generate() with guard checks."
        )


# ---------------------------------------------------------------------------
# Guards
# ---------------------------------------------------------------------------


def guard_config(config: ExternalAIAdapterConfig) -> ExternalAIGuardResult:
    findings: list[str] = []

    if config.enabled and not config.requires_user_switch:
        findings.append("enabled_without_user_switch")
    if config.allow_network:
        findings.append("allow_network_true_blocked_in_stage_9_3_a")
    if config.mode == "network":
        findings.append("mode_network_not_implemented_in_stage_9_3_a")
    if config.enabled and config.mode == "disabled":
        findings.append("enabled_but_mode_disabled_inconsistent")
    if not config.requires_context_preview:
        findings.append("requires_context_preview_must_be_true")
    if not config.requires_validator:
        findings.append("requires_validator_must_be_true")
    if config.save_raw_prompt:
        findings.append("save_raw_prompt_must_be_false")
    if config.save_raw_response:
        findings.append("save_raw_response_must_be_false")

    return ExternalAIGuardResult(passed=not findings, findings=findings)


def guard_request(
    request: ExternalAIRequest,
    raw_request: dict[str, Any] | None = None,
) -> ExternalAIGuardResult:
    findings: list[str] = []

    if not request.context_preview_summary or not request.context_preview_summary.strip():
        findings.append("missing_context_preview_summary")
    if not request.boundary_notices:
        findings.append("missing_boundary_notices")
    if request.validator_required is not True:
        findings.append("validator_required_must_be_true")
    if request.mode == "network":
        findings.append("mode_network_blocked_in_stage_9_3_a")

    # Field-name guard against the raw request dict, if supplied.
    if raw_request is not None:
        lowered_keys = {str(k).lower() for k in raw_request.keys()}
        for forbidden in FORBIDDEN_REQUEST_FIELD_NAMES:
            if forbidden in lowered_keys:
                findings.append(f"forbidden_field_{forbidden}")

    # Token guard against any string value in the validated request.
    serialized = " ".join(
        str(v).lower()
        for v in request.model_dump().values()
        if v is not None and not isinstance(v, (int, float, bool))
    )
    # Lists of boundary notices serialize as a string already via str().
    for token in FORBIDDEN_REQUEST_TOKENS:
        if token in serialized:
            findings.append(f"forbidden_token_{token.strip()}")

    return ExternalAIGuardResult(passed=not findings, findings=findings)


def guard_response(response: ExternalAIResponse) -> ExternalAIGuardResult:
    findings: list[str] = []

    if response.external_model_called:
        findings.append("external_model_called_blocked_in_stage_9_3_a")
    if response.privacy_summary.external_model_called:
        findings.append("privacy_external_model_called_blocked")
    if response.privacy_summary.search_called:
        findings.append("privacy_search_called_blocked")
    if response.privacy_summary.saved_by_default:
        findings.append("privacy_saved_by_default_blocked")
    if not response.privacy_summary.uses_ai_context_manifest_only:
        findings.append("must_use_ai_context_manifest_only")
    if response.privacy_summary.uses_holdings_line_items:
        findings.append("uses_holdings_line_items_blocked")
    if response.privacy_summary.uses_raw_provider_payloads:
        findings.append("uses_raw_provider_payloads_blocked")
    if response.privacy_summary.uses_raw_prompts:
        findings.append("uses_raw_prompts_blocked")
    if not response.not_saved_by_default:
        findings.append("not_saved_by_default_must_be_true")
    if not response.human_review_required:
        findings.append("human_review_required_must_be_true")
    if response.mode == "fake" and not response.fake_response:
        findings.append("fake_mode_requires_fake_response_true")
    if response.mode == "network":
        findings.append("response_mode_network_blocked_in_stage_9_3_a")
    if response.validator_result.passed is not True:
        findings.append("validator_result_must_pass")

    content = response.content.lower()
    for term in FORBIDDEN_RESPONSE_OUTPUT_TERMS:
        if term in content:
            findings.append(f"forbidden_response_term_{_finding_token(term)}")
    for token in FORBIDDEN_RESPONSE_PRIVACY_TOKENS:
        if token in content:
            findings.append(f"forbidden_response_privacy_token_{_finding_token(token)}")

    return ExternalAIGuardResult(passed=not findings, findings=findings)


def _finding_token(value: str) -> str:
    return (
        value.strip()
        .replace("\\", "_")
        .replace("/", "_")
        .replace(" ", "_")
        .replace("-", "_")
        .replace(".", "")
        .replace(":", "")
    )


__all__ = [
    "BlockedAdapterError",
    "ExternalAIAdapter",
    "FORBIDDEN_REQUEST_FIELD_NAMES",
    "FORBIDDEN_REQUEST_TOKENS",
    "FORBIDDEN_RESPONSE_OUTPUT_TERMS",
    "FORBIDDEN_RESPONSE_PRIVACY_TOKENS",
    "guard_config",
    "guard_request",
    "guard_response",
]
