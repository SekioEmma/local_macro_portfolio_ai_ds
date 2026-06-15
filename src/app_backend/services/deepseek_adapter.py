"""Stage 9.3-A DeepSeek adapter skeleton.

This module ships ONLY a disabled-by-default DeepSeek adapter shell and a
FakeDeepSeekAdapter that returns deterministic local text. There is no
HTTP client import, no environment variable read, no API key handling,
and no network attempt anywhere in this file.

Stage 9.3-B (real DeepSeek) is NOT implemented here. Bringing it in must:
- add an explicit user-controlled switch
- show context preview before send
- run the validator after response
- never persist raw prompts/responses by default
- reuse `ExternalAIRequest` / `ExternalAIResponse` and the guards in
  `ai_external_adapter.py` unchanged

Importing this module must not trigger any network or file I/O.
"""
from __future__ import annotations

from app_backend.schemas.ai_external import (
    ExternalAIAdapterConfig,
    ExternalAIPrivacySummary,
    ExternalAIRequest,
    ExternalAIResponse,
)
from app_backend.schemas.ai_memo import AIMemoValidatorResult
from app_backend.services.ai_external_adapter import (
    BlockedAdapterError,
    ExternalAIAdapter,
    guard_request,
    guard_response,
)


FAKE_BOUNDARY_NOTICE = (
    "Fake adapter output only; not an action directive, not an "
    "event-odds model, not a return-estimation model, not a position-level "
    "output, and not external-model output."
)


def default_disabled_config() -> ExternalAIAdapterConfig:
    """Stage 9.3-A default: disabled, no network, no persistence."""
    return ExternalAIAdapterConfig(
        provider="deepseek",
        enabled=False,
        mode="disabled",
        allow_network=False,
        requires_user_switch=True,
        requires_context_preview=True,
        requires_validator=True,
        save_raw_prompt=False,
        save_raw_response=False,
    )


def fake_only_config() -> ExternalAIAdapterConfig:
    """Stage 9.3-A test/preview config: fake mode, no network."""
    return ExternalAIAdapterConfig(
        provider="deepseek",
        enabled=True,
        mode="fake",
        allow_network=False,
        requires_user_switch=True,
        requires_context_preview=True,
        requires_validator=True,
        save_raw_prompt=False,
        save_raw_response=False,
    )


class DeepSeekAdapter(ExternalAIAdapter):
    """Disabled-by-default DeepSeek adapter.

    Stage 9.3-A behavior:
    - `mode="disabled"` → `generate()` raises `BlockedAdapterError`
    - `mode="fake"` → returns deterministic local text via `FakeDeepSeekAdapter`
    - `mode="network"` → blocked at config guard, never reaches `generate()`
    """

    def generate(self, request: ExternalAIRequest) -> ExternalAIResponse:
        if self.config.mode == "disabled":
            raise BlockedAdapterError(["adapter_disabled_in_stage_9_3_a"])
        if self.config.mode == "network":
            # Defensive; config guard should have blocked this already.
            raise BlockedAdapterError(["network_mode_not_implemented_in_stage_9_3_a"])
        if self.config.mode != "fake":
            raise BlockedAdapterError([f"unsupported_mode_{self.config.mode}"])

        request_guard = guard_request(request)
        if not request_guard.passed:
            raise BlockedAdapterError(request_guard.findings)

        response = _build_fake_response(self.config, request)
        response_guard = guard_response(response)
        if not response_guard.passed:
            raise BlockedAdapterError(response_guard.findings)
        return response


class FakeDeepSeekAdapter(DeepSeekAdapter):
    """Convenience alias that defaults to fake mode.

    Useful in tests so they do not have to construct a config every time.
    """

    def __init__(self, config: ExternalAIAdapterConfig | None = None) -> None:
        super().__init__(config or fake_only_config())


def _build_fake_response(
    config: ExternalAIAdapterConfig,
    request: ExternalAIRequest,
) -> ExternalAIResponse:
    content = (
        "[fake-deepseek] Local fake adapter response. "
        f"included_facts={request.included_fact_count}, "
        f"included_models={request.included_model_output_count}. "
        f"{FAKE_BOUNDARY_NOTICE}"
    )
    return ExternalAIResponse(
        provider=config.provider,
        mode="fake",
        external_model_called=False,
        fake_response=True,
        content=content,
        validator_result=AIMemoValidatorResult(
            passed=True,
            blocked_terms=[],
            privacy_findings=[],
        ),
        privacy_summary=ExternalAIPrivacySummary(
            uses_ai_context_manifest_only=True,
            uses_holdings_line_items=False,
            uses_raw_provider_payloads=False,
            uses_raw_prompts=False,
            external_model_called=False,
            search_called=False,
            saved_by_default=False,
        ),
        not_saved_by_default=True,
        human_review_required=True,
    )


__all__ = [
    "DeepSeekAdapter",
    "FakeDeepSeekAdapter",
    "FAKE_BOUNDARY_NOTICE",
    "default_disabled_config",
    "fake_only_config",
]
