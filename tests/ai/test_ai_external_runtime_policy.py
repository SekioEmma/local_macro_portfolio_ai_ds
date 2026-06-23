"""Stage 9.3-B-0 runtime approval gate / external AI policy regression tests.

These tests lock the runtime policy contract: defaults fail closed; a
fully-approved policy passes only when every approval gate is True AND every
dangerous permission is False; every individual approval gate is required;
every individual dangerous permission is blocked; extra fields are rejected;
and the production module exposes no network, env, or file-read surface.

Stage 9.3-B real DeepSeek is NOT implemented. This file does not exercise
any external call; it only validates the policy contract.
"""
from __future__ import annotations

from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
from pydantic import ValidationError

from app_backend.schemas.ai_external import (
    ExternalAIRuntimePolicy,
    default_external_ai_runtime_policy,
)
from app_backend.services.ai_external_adapter import BlockedAdapterError
from app_backend.services.ai_external_runtime_policy import (
    assert_external_ai_runtime_policy_allowed,
    guard_external_ai_runtime_policy,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _happy_path_policy() -> ExternalAIRuntimePolicy:
    """Construct the only policy shape that passes the guard.

    Every approval gate is True; every dangerous permission is False.
    This represents the "all human and code-level approvals satisfied"
    state, not an authorization to run real DeepSeek today.
    """
    return ExternalAIRuntimePolicy(
        external_ai_enabled=True,
        provider_network_enabled=True,
        user_controlled_switch_enabled=True,
        single_request_user_approved=True,
        context_preview_confirmed=True,
        request_built_from_manifest=True,
        request_guard_passed=True,
        response_guard_required=True,
        stage9_validator_required=True,
        human_review_required=True,
        save_raw_prompt=False,
        save_raw_response=False,
        persist_chat_by_default=False,
        allow_search=False,
        allow_tavily=False,
        allow_background_call=False,
        allow_app_start_call=False,
        allow_page_load_call=False,
        allow_holdings_line_items=False,
        allow_account_values=False,
        allow_position_weights=False,
        allow_transaction_history=False,
    )


APPROVAL_GATES_TRUE_REQUIRED = (
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

DANGEROUS_PERMISSIONS_FALSE_REQUIRED = (
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


# ---------------------------------------------------------------------------
# 4.1 Default policy fail-closed
# ---------------------------------------------------------------------------


def test_default_policy_has_all_dangerous_booleans_disabled():
    policy = default_external_ai_runtime_policy()
    # Approval gates default False (except the required-flag retentions)
    assert policy.external_ai_enabled is False
    assert policy.provider_network_enabled is False
    assert policy.user_controlled_switch_enabled is False
    assert policy.single_request_user_approved is False
    assert policy.context_preview_confirmed is False
    assert policy.request_built_from_manifest is False
    assert policy.request_guard_passed is False
    # Required-flags default True so a future "may proceed" policy
    # cannot quietly turn off boundary requirements.
    assert policy.response_guard_required is True
    assert policy.stage9_validator_required is True
    assert policy.human_review_required is True
    # Dangerous permissions default False
    assert policy.save_raw_prompt is False
    assert policy.save_raw_response is False
    assert policy.persist_chat_by_default is False
    assert policy.allow_search is False
    assert policy.allow_tavily is False
    assert policy.allow_background_call is False
    assert policy.allow_app_start_call is False
    assert policy.allow_page_load_call is False
    assert policy.allow_holdings_line_items is False
    assert policy.allow_account_values is False
    assert policy.allow_position_weights is False
    assert policy.allow_transaction_history is False
    assert policy.provider == "deepseek"
    assert policy.policy_version == "stage9_3b_0"


def test_default_policy_guard_fails_closed():
    result = guard_external_ai_runtime_policy(default_external_ai_runtime_policy())
    assert result.passed is False
    assert "external_ai_disabled" in result.findings


def test_default_policy_assertion_raises_blocked_adapter_error():
    with pytest.raises(BlockedAdapterError) as exc:
        assert_external_ai_runtime_policy_allowed(default_external_ai_runtime_policy())
    assert "external_ai_disabled" in exc.value.findings


# ---------------------------------------------------------------------------
# 4.2 Happy-path approval policy passes
# ---------------------------------------------------------------------------


def test_happy_path_policy_passes_guard():
    result = guard_external_ai_runtime_policy(_happy_path_policy())
    assert result.passed is True
    assert result.findings == []


def test_happy_path_policy_passes_assertion_without_raising():
    # No exception
    assert_external_ai_runtime_policy_allowed(_happy_path_policy())


# ---------------------------------------------------------------------------
# 4.3 Each missing approval gate fails
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("flag,finding", APPROVAL_GATES_TRUE_REQUIRED)
def test_missing_approval_gate_fails_guard(flag, finding):
    policy = _happy_path_policy().model_copy(update={flag: False})
    result = guard_external_ai_runtime_policy(policy)
    assert result.passed is False
    assert finding in result.findings


@pytest.mark.parametrize("flag,finding", APPROVAL_GATES_TRUE_REQUIRED)
def test_missing_approval_gate_assertion_raises(flag, finding):
    policy = _happy_path_policy().model_copy(update={flag: False})
    with pytest.raises(BlockedAdapterError) as exc:
        assert_external_ai_runtime_policy_allowed(policy)
    assert finding in exc.value.findings


# ---------------------------------------------------------------------------
# 4.4 Each dangerous permission blocked
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("flag,finding", DANGEROUS_PERMISSIONS_FALSE_REQUIRED)
def test_dangerous_permission_true_fails_guard(flag, finding):
    policy = _happy_path_policy().model_copy(update={flag: True})
    result = guard_external_ai_runtime_policy(policy)
    assert result.passed is False
    assert finding in result.findings


@pytest.mark.parametrize("flag,finding", DANGEROUS_PERMISSIONS_FALSE_REQUIRED)
def test_dangerous_permission_true_assertion_raises(flag, finding):
    policy = _happy_path_policy().model_copy(update={flag: True})
    with pytest.raises(BlockedAdapterError) as exc:
        assert_external_ai_runtime_policy_allowed(policy)
    assert finding in exc.value.findings


# ---------------------------------------------------------------------------
# 4.5 Extra fields rejected
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "extra_field,extra_value",
    [
        ("api_key", "x"),
        ("api_key_env", "DEEPSEEK_API_KEY"),
        ("base_url", "https://example.invalid"),
        ("raw_prompt", "x"),
        ("raw_response", "x"),
        ("deepseek_endpoint", "https://api.deepseek.com/v1/chat"),
        ("tavily_endpoint", "https://api.tavily.com/search"),
        ("model_name", "deepseek-chat"),
        ("env_file_path", ".env"),
    ],
)
def test_runtime_policy_rejects_extra_field(extra_field, extra_value):
    with pytest.raises(ValidationError):
        ExternalAIRuntimePolicy(**{extra_field: extra_value})


# ---------------------------------------------------------------------------
# 4.6 Production module exposes no network / env / file-read surface
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "forbidden",
    [
        "import httpx",
        "import requests",
        "import aiohttp",
        "urllib.request",
        "socket.create_connection",
        "os.environ",
        "os.getenv",
        "open(",
        "DEEPSEEK_API_KEY",
        "TAVILY_API_KEY",
        "external_llm.yaml",
        "api.deepseek",
        "deepseek.com",
    ],
)
def test_runtime_policy_module_does_not_contain_forbidden_surface(forbidden):
    source = (
        _REPO_ROOT / "src/app_backend/services/ai_external_runtime_policy.py"
    ).read_text(encoding="utf-8")
    assert forbidden not in source, (
        f"forbidden surface marker {forbidden!r} found in runtime policy module"
    )


# ---------------------------------------------------------------------------
# 4.7 Stage 9.2 isolation still holds
# ---------------------------------------------------------------------------


STAGE_9_2_SURFACE_FILES = (
    str(_REPO_ROOT / "src/app_backend/main.py"),
    str(_REPO_ROOT / "src/app_backend/services/ai_preview_service.py"),
    str(_REPO_ROOT / "src/app_backend/services/ai_memo_renderer.py"),
    str(_REPO_ROOT / "src/app_backend/services/ai_context_service.py"),
)

FORBIDDEN_IMPORTS_IN_STAGE_9_2 = (
    "ai_external_runtime_policy",
    "guard_external_ai_runtime_policy",
    "assert_external_ai_runtime_policy_allowed",
    "ai_external_request_builder",
    "build_external_ai_request_from_manifest",
    "deepseek_adapter",
    "DeepSeekAdapter",
    "FakeDeepSeekAdapter",
)


@pytest.mark.parametrize("file_path", STAGE_9_2_SURFACE_FILES)
@pytest.mark.parametrize("forbidden", FORBIDDEN_IMPORTS_IN_STAGE_9_2)
def test_stage9_2_surface_does_not_import_runtime_policy_or_adapter(
    file_path, forbidden
):
    source = Path(file_path).read_text(encoding="utf-8")
    assert forbidden not in source, (
        f"Stage 9.2 file {file_path!r} must not reference {forbidden!r}"
    )


# ---------------------------------------------------------------------------
# 4.8 Forbidden routes still absent
# ---------------------------------------------------------------------------


FORBIDDEN_ROUTES = (
    "/api/chat",
    "/api/search",
    "/api/ai/chat",
    "/api/ai/search",
    "/api/ai/deepseek",
    "/api/ai/tavily",
    "/api/ai/external",
    "/api/ai/external-request",
    "/api/ai/external-policy",
    "/api/ai/runtime-policy",
    "/api/ai/send",
    "/api/ai/complete",
    "/api/ai/generate",
)


def test_no_forbidden_routes_present_after_runtime_policy_introduced():
    from app_backend.main import app

    route_paths = {route.path for route in app.routes}
    present = [path for path in FORBIDDEN_ROUTES if path in route_paths]
    assert not present, f"forbidden routes present: {present}"


# ---------------------------------------------------------------------------
# Bonus: importing the runtime policy module does not pull a network client
# ---------------------------------------------------------------------------


def test_importing_runtime_policy_module_does_not_register_routes():
    """Importing the runtime policy module must not register an HTTP route."""
    from app_backend.main import app
    routes_before = {route.path for route in app.routes}
    from app_backend.services import ai_external_runtime_policy  # noqa: F401
    routes_after = {route.path for route in app.routes}
    assert routes_after == routes_before


def test_runtime_policy_guard_is_pure_function():
    """Calling the guard repeatedly with the same input returns equal results
    and never raises (only the assertion helper raises)."""
    policy = default_external_ai_runtime_policy()
    first = guard_external_ai_runtime_policy(policy)
    second = guard_external_ai_runtime_policy(policy)
    assert first == second
    assert first.passed is False
