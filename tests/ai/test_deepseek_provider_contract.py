"""Stage 9.3-B-1 DeepSeek provider payload contract regression tests.

Locks the contract that ``build_deepseek_provider_payload``:
- only accepts a guarded ``ExternalAIRequest``
- fails closed on any ``guard_request`` finding
- does not accept or expose a raw question / prompt parameter
- does not carry API key, env var name, endpoint, model name, holdings,
  account values, position weights, transaction history, raw provider
  payload, search results, or local file paths
- rejects extra fields at the schema level
- exposes no network / env / file-read surface
- is not imported by any Stage 9.2 surface
- adds no HTTP route

Stage 9.3-B-2 real DeepSeek is NOT implemented.
"""
from __future__ import annotations

import inspect
from pathlib import Path

import pytest
from pydantic import ValidationError

from app_backend.schemas.ai_external import (
    DeepSeekProviderMessage,
    DeepSeekProviderPayload,
    ExternalAIRequest,
)
from app_backend.services.ai_external_adapter import BlockedAdapterError
from app_backend.services.deepseek_provider_contract import (
    build_deepseek_provider_payload,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _valid_request(**overrides) -> ExternalAIRequest:
    base = dict(
        request_id="req-001",
        provider="deepseek",
        mode="fake",
        user_intent_summary="Sanitized intent summary.",
        context_preview_summary="2 facts, 1 model output included.",
        included_fact_count=2,
        included_model_output_count=1,
        excluded_context_summary="1 excluded fact.",
        boundary_notices=["Reference evidence only.", "Not an action directive."],
        memo_type="daily_review_memo",
        preview_type=None,
        validator_required=True,
    )
    base.update(overrides)
    return ExternalAIRequest(**base)


# ---------------------------------------------------------------------------
# 8.1 Payload only constructible from ExternalAIRequest via the builder
# ---------------------------------------------------------------------------


def test_builder_signature_accepts_only_external_ai_request():
    sig = inspect.signature(build_deepseek_provider_payload)
    params = list(sig.parameters.values())
    assert len(params) == 1
    # Annotation must be the ExternalAIRequest class (or its name)
    annot = params[0].annotation
    annot_name = getattr(annot, "__name__", str(annot))
    assert annot_name == "ExternalAIRequest"


def test_builder_signature_has_no_raw_question_or_prompt_parameter():
    sig = inspect.signature(build_deepseek_provider_payload)
    for name in sig.parameters:
        lowered = name.lower()
        assert "question" not in lowered, f"builder must not accept {name}"
        assert "prompt" not in lowered, f"builder must not accept {name}"
        assert "api_key" not in lowered, f"builder must not accept {name}"
        assert "endpoint" not in lowered, f"builder must not accept {name}"
        assert "url" not in lowered, f"builder must not accept {name}"
        assert "model" not in lowered, f"builder must not accept {name}"


def test_builder_returns_sanitized_payload():
    payload = build_deepseek_provider_payload(_valid_request())
    assert isinstance(payload, DeepSeekProviderPayload)
    assert payload.provider == "deepseek"
    assert payload.mode == "fake"
    assert payload.included_fact_count == 2
    assert payload.included_model_output_count == 1
    assert payload.validator_required is True
    assert payload.memo_type == "daily_review_memo"


def test_payload_messages_have_restricted_roles():
    """Roles must be system / context / summary only — no user role."""
    payload = build_deepseek_provider_payload(_valid_request())
    roles = {m.role for m in payload.messages}
    assert roles <= {"system", "context", "summary"}
    assert "user" not in roles


def test_payload_messages_carry_only_request_summaries():
    payload = build_deepseek_provider_payload(_valid_request())
    contents = " ".join(m.content for m in payload.messages)
    # Sanitized request summaries must appear in payload messages
    assert "Sanitized intent summary." in contents
    assert "2 facts, 1 model output included." in contents
    assert "1 excluded fact." in contents
    assert "Reference evidence only." in contents
    # The system boundary phrase is hard-coded and contains the phrase
    assert "not an action directive" in contents.lower()


def test_user_intent_is_the_final_non_system_message():
    payload = build_deepseek_provider_payload(_valid_request())
    non_system_messages = [
        message for message in payload.messages if message.role != "system"
    ]

    assert non_system_messages[-1].role == "summary"
    assert non_system_messages[-1].content == "Sanitized intent summary."


# ---------------------------------------------------------------------------
# 8.2 Unsafe request blocked by guard_request, no payload returned
# ---------------------------------------------------------------------------


def test_builder_blocks_request_with_empty_boundary_notices():
    request = _valid_request(boundary_notices=[])
    with pytest.raises(BlockedAdapterError) as exc:
        build_deepseek_provider_payload(request)
    assert "missing_boundary_notices" in exc.value.findings


def test_builder_blocks_request_with_empty_context_preview_summary():
    request = _valid_request(context_preview_summary="   ")
    with pytest.raises(BlockedAdapterError) as exc:
        build_deepseek_provider_payload(request)
    assert "missing_context_preview_summary" in exc.value.findings


def test_builder_blocks_request_with_validator_required_false():
    request = _valid_request(validator_required=False)
    with pytest.raises(BlockedAdapterError) as exc:
        build_deepseek_provider_payload(request)
    assert "validator_required_must_be_true" in exc.value.findings


def test_builder_accepts_request_with_network_mode():
    request = _valid_request(mode="network")
    payload = build_deepseek_provider_payload(request)
    assert payload.mode == "network"


@pytest.mark.parametrize(
    "leaking_text",
    [
        "API_KEY=sk_live_secret_value_test",
        "current_holdings.csv loaded",
        "account values: $1,234,567",
        "position weights: 50/30/15/5",
        "transaction history: 100 trades",
        "data/private/notes.md",
        "G:\\local_macro_portfolio_ai",
        "external_llm.yaml secrets",
    ],
)
def test_builder_blocks_request_with_forbidden_token_in_summary(leaking_text):
    request = _valid_request(context_preview_summary=leaking_text)
    with pytest.raises(BlockedAdapterError):
        build_deepseek_provider_payload(request)


# ---------------------------------------------------------------------------
# 8.3 Schema rejects extra fields and forbidden field names
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "extra_field,extra_value",
    [
        ("api_key", "sk_live_secret"),
        ("api_key_env", "DEEPSEEK_API_KEY"),
        ("base_url", "https://api.deepseek.com/v1/chat"),
        ("endpoint", "/v1/chat/completions"),
        ("model", "deepseek-chat"),
        ("model_name", "deepseek-chat"),
        ("raw_question", "what is going on"),
        ("raw_prompt", "system: you are..."),
        ("holdings_line_items", []),
        ("account_values", {}),
        ("position_weights", {}),
        ("transaction_history", []),
        ("raw_provider_payload", {}),
        ("search_results", []),
        ("local_path", "G:/data/private"),
        ("env_file_path", ".env"),
    ],
)
def test_provider_payload_rejects_extra_field(extra_field, extra_value):
    """Any forbidden extra field must be rejected at construction time."""
    base = dict(
        request_id="r",
        provider="deepseek",
        mode="fake",
        user_intent_summary="ok",
        context_preview_summary="ok",
        included_fact_count=0,
        included_model_output_count=0,
        excluded_context_summary="ok",
        boundary_notices=["Reference."],
        validator_required=True,
        messages=[
            DeepSeekProviderMessage(role="system", content="ok"),
        ],
    )
    base[extra_field] = extra_value
    with pytest.raises(ValidationError):
        DeepSeekProviderPayload(**base)


@pytest.mark.parametrize(
    "extra_field,extra_value",
    [
        ("api_key", "sk_live_secret"),
        ("raw_prompt", "system: you are..."),
        ("endpoint", "/v1/chat/completions"),
        ("model", "deepseek-chat"),
    ],
)
def test_provider_message_rejects_extra_field(extra_field, extra_value):
    base = dict(role="system", content="ok")
    base[extra_field] = extra_value
    with pytest.raises(ValidationError):
        DeepSeekProviderMessage(**base)


def test_provider_message_rejects_user_role():
    with pytest.raises(ValidationError):
        DeepSeekProviderMessage(role="user", content="any")


# ---------------------------------------------------------------------------
# 8.4 Source surface scan: no network / env / file-read in provider module
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
def test_provider_contract_module_has_no_forbidden_surface(forbidden):
    source = Path(
        "src/app_backend/services/deepseek_provider_contract.py"
    ).read_text(encoding="utf-8")
    assert forbidden not in source, (
        f"forbidden surface marker {forbidden!r} found in provider contract module"
    )


# ---------------------------------------------------------------------------
# 8.5 Stage 9.2 isolation still holds
# ---------------------------------------------------------------------------


STAGE_9_2_SURFACE_FILES = (
    "src/app_backend/main.py",
    "src/app_backend/services/ai_preview_service.py",
    "src/app_backend/services/ai_memo_renderer.py",
    "src/app_backend/services/ai_context_service.py",
)

FORBIDDEN_IMPORTS_IN_STAGE_9_2 = (
    "deepseek_provider_contract",
    "build_deepseek_provider_payload",
    "DeepSeekProviderPayload",
    "DeepSeekProviderMessage",
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
def test_stage9_2_surface_does_not_import_provider_contract(file_path, forbidden):
    source = Path(file_path).read_text(encoding="utf-8")
    assert forbidden not in source, (
        f"Stage 9.2 file {file_path!r} must not reference {forbidden!r}"
    )


# ---------------------------------------------------------------------------
# 8.6 Forbidden routes still absent
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
    "/api/ai/provider-payload",
    "/api/ai/send",
    "/api/ai/complete",
    "/api/ai/generate",
)


def test_no_forbidden_routes_present_after_provider_contract_introduced():
    from app_backend.main import app

    route_paths = {route.path for route in app.routes}
    present = [path for path in FORBIDDEN_ROUTES if path in route_paths]
    assert not present, f"forbidden routes present: {present}"


def test_importing_provider_contract_module_does_not_register_routes():
    from app_backend.main import app
    routes_before = {route.path for route in app.routes}
    from app_backend.services import deepseek_provider_contract  # noqa: F401
    routes_after = {route.path for route in app.routes}
    assert routes_after == routes_before


# ---------------------------------------------------------------------------
# 8.7 No raw question is echoed in payload regardless of intent summary
# ---------------------------------------------------------------------------


def test_payload_does_not_echo_a_raw_question_marker():
    """If a downstream caller smuggles a raw-question-like marker through
    ``user_intent_summary``, the payload still must not present it as a
    'user' role. Roles are restricted at the schema level."""
    request = _valid_request(
        user_intent_summary="RAW_QUESTION_MARKER_FOR_AUDIT — sanitized?"
    )
    payload = build_deepseek_provider_payload(request)
    for m in payload.messages:
        assert m.role != "user"
    # Marker may appear in summary message, but never as a 'user' role
    user_role_contents = [m.content for m in payload.messages if m.role == "user"]
    assert user_role_contents == []
