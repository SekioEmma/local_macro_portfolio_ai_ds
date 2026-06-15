"""Stage 9.3-B-0 runtime approval gate / external AI policy contract.

This module defines the runtime guard that decides whether a future real
external AI call may proceed. Stage 9.3-B-0 does NOT implement the real
call; it only ships the policy schema (in ``ai_external.py``) and the
guard implemented here.

The guard returns ``passed=True`` only when ALL of the following are true:

- Every approval gate flag is ``True``:
  ``external_ai_enabled``, ``provider_network_enabled``,
  ``user_controlled_switch_enabled``, ``single_request_user_approved``,
  ``context_preview_confirmed``, ``request_built_from_manifest``,
  ``request_guard_passed``, ``response_guard_required``,
  ``stage9_validator_required``, ``human_review_required``.
- Every dangerous permission flag is ``False``:
  ``save_raw_prompt``, ``save_raw_response``, ``persist_chat_by_default``,
  ``allow_search``, ``allow_tavily``, ``allow_background_call``,
  ``allow_app_start_call``, ``allow_page_load_call``,
  ``allow_holdings_line_items``, ``allow_account_values``,
  ``allow_position_weights``, ``allow_transaction_history``.

The default policy fails closed. The Stage 9.2 preview endpoints do NOT
consume this guard (Stage 9.2 stays local / deterministic / manifest only).
The future Stage 9.3-B real DeepSeek call must call this guard immediately
before the external network step and must abort if it does not pass.

No network client is imported here. No environment variable is read. No
file is opened. No API key, URL, or model endpoint string lives in this
module.
"""
from __future__ import annotations

from app_backend.schemas.ai_external import (
    ExternalAIGuardResult,
    ExternalAIRuntimePolicy,
)
from app_backend.services.ai_external_adapter import BlockedAdapterError


# Approval gates that must be True for a runtime call to proceed.
# Order is kept stable so test findings remain predictable.
_REQUIRED_TRUE_FLAGS: tuple[tuple[str, str], ...] = (
    ("external_ai_enabled", "external_ai_disabled"),
    ("provider_network_enabled", "provider_network_disabled"),
    ("user_controlled_switch_enabled", "missing_user_controlled_switch"),
    ("single_request_user_approved", "missing_single_request_user_approval"),
    ("context_preview_confirmed", "missing_context_preview_confirmation"),
    ("request_built_from_manifest", "request_not_built_from_manifest"),
    ("request_guard_passed", "request_guard_not_passed"),
    ("response_guard_required", "response_guard_not_required"),
    ("stage9_validator_required", "stage9_validator_not_required"),
    ("human_review_required", "human_review_not_required"),
)

# Dangerous permissions that must be False for a runtime call to proceed.
_REQUIRED_FALSE_FLAGS: tuple[tuple[str, str], ...] = (
    ("save_raw_prompt", "save_raw_prompt_blocked"),
    ("save_raw_response", "save_raw_response_blocked"),
    ("persist_chat_by_default", "persist_chat_by_default_blocked"),
    ("allow_search", "search_not_allowed_in_deepseek_policy"),
    ("allow_tavily", "tavily_not_allowed_in_deepseek_policy"),
    ("allow_background_call", "background_call_blocked"),
    ("allow_app_start_call", "app_start_call_blocked"),
    ("allow_page_load_call", "page_load_call_blocked"),
    ("allow_holdings_line_items", "holdings_line_items_blocked"),
    ("allow_account_values", "account_values_blocked"),
    ("allow_position_weights", "position_weights_blocked"),
    ("allow_transaction_history", "transaction_history_blocked"),
)


def guard_external_ai_runtime_policy(
    policy: ExternalAIRuntimePolicy,
) -> ExternalAIGuardResult:
    """Return ``passed=True`` only when every approval gate is True and every
    dangerous permission is False. Otherwise return ``passed=False`` with a
    deterministic, stable list of findings.

    This guard does not perform any network, file, or env read. It is a pure
    function over the supplied policy object.
    """
    findings: list[str] = []

    for attr_name, finding in _REQUIRED_TRUE_FLAGS:
        if getattr(policy, attr_name) is not True:
            findings.append(finding)

    for attr_name, finding in _REQUIRED_FALSE_FLAGS:
        if getattr(policy, attr_name) is not False:
            findings.append(finding)

    return ExternalAIGuardResult(passed=not findings, findings=findings)


def assert_external_ai_runtime_policy_allowed(
    policy: ExternalAIRuntimePolicy,
) -> None:
    """Raise ``BlockedAdapterError`` when the runtime policy guard does not
    pass. Use this in any future real-adapter path immediately before the
    external network step.

    Stage 9.3-B-0 does not wire this assertion to any HTTP endpoint. It is
    only exposed as a contract for Stage 9.3-B reviewers and future code.
    """
    result = guard_external_ai_runtime_policy(policy)
    if not result.passed:
        raise BlockedAdapterError(result.findings)


__all__ = [
    "assert_external_ai_runtime_policy_allowed",
    "guard_external_ai_runtime_policy",
]
