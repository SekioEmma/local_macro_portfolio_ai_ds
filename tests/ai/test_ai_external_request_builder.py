"""Stage 9.3-A external AI request builder regression tests.

Locks the contract that `build_external_ai_request_from_manifest`:
- consumes only sanitized AI Context Manifest material
- never accepts a raw user question / raw prompt argument
- defaults to fake mode and rejects network mode at the entry point
- runs `guard_request` before returning, so callers cannot bypass it
- never imports a real network client, env, or external_llm.yaml
- is not wired to any Stage 9.2 HTTP endpoint
"""
from __future__ import annotations

import inspect
import socket
from pathlib import Path

import pytest

from app_backend.services.ai_external_adapter import BlockedAdapterError
from app_backend.services.ai_external_request_builder import (
    DEFAULT_USER_INTENT_SUMMARY,
    build_external_ai_request_from_manifest,
)

_REPO_ROOT = Path(__file__).resolve().parents[2]


# ---------------------------------------------------------------------------
# Manifest fixtures
# ---------------------------------------------------------------------------


def _safe_manifest() -> dict:
    return {
        "generated_at": "2026-06-15T00:00:00+00:00",
        "included_facts": [
            {"module": "credit_stress", "metric_key": "high_yield_spread"},
            {"module": "credit_stress", "metric_key": "investment_grade_spread"},
        ],
        "excluded_facts": [
            {
                "module": "valuation_equity_structure",
                "metric_key": "valuation_missing_inputs",
                "excluded_reason": "status_research_needed",
            }
        ],
        "included_model_outputs": [
            {
                "module": "financial_stress_composite",
                "metric_key": "financial_stress_status",
            }
        ],
        "excluded_model_outputs": [],
        "risk_boundaries": [
            "Reference evidence only.",
            "Not an action directive.",
        ],
    }


def _unsafe_manifest_with_token_in_boundary() -> dict:
    m = _safe_manifest()
    m["risk_boundaries"] = ["data/private leaked into boundary"]
    return m


# ---------------------------------------------------------------------------
# Happy-path builder behavior
# ---------------------------------------------------------------------------


def test_builder_returns_guarded_request_in_fake_mode():
    request = build_external_ai_request_from_manifest(_safe_manifest())
    assert request.provider == "deepseek"
    assert request.mode == "fake"
    assert request.included_fact_count == 2
    assert request.included_model_output_count == 1
    assert request.validator_required is True
    assert "Not an action directive." in request.boundary_notices


def test_builder_uses_default_user_intent_summary_when_omitted():
    request = build_external_ai_request_from_manifest(_safe_manifest())
    assert request.user_intent_summary == DEFAULT_USER_INTENT_SUMMARY
    assert "no raw user question" in DEFAULT_USER_INTENT_SUMMARY.lower()


def test_builder_signature_has_no_raw_question_or_prompt_argument():
    """The builder must not expose any `question` or `prompt` parameter."""
    sig = inspect.signature(build_external_ai_request_from_manifest)
    for name in sig.parameters:
        lowered = name.lower()
        assert "question" not in lowered, (
            f"builder must not accept a question parameter, found: {name}"
        )
        assert "prompt" not in lowered, (
            f"builder must not accept a prompt parameter, found: {name}"
        )


def test_builder_falls_back_to_default_boundary_notices_when_missing():
    request = build_external_ai_request_from_manifest(
        {**_safe_manifest(), "risk_boundaries": []}
    )
    assert request.boundary_notices  # non-empty
    assert any("not an action directive" in s.lower() for s in request.boundary_notices)


# ---------------------------------------------------------------------------
# Fail-closed behavior
# ---------------------------------------------------------------------------


def test_builder_rejects_network_mode():
    with pytest.raises(BlockedAdapterError) as exc:
        build_external_ai_request_from_manifest(_safe_manifest(), mode="network")
    assert any("network" in f for f in exc.value.findings)


def test_builder_rejects_manifest_with_forbidden_token_in_boundary():
    """If a manifest accidentally surfaces a forbidden token in
    boundary_notices, the guard inside the builder must fail closed."""
    with pytest.raises(BlockedAdapterError) as exc:
        build_external_ai_request_from_manifest(
            _unsafe_manifest_with_token_in_boundary()
        )
    findings = exc.value.findings
    assert any("forbidden_token_" in f for f in findings)


def test_builder_accepts_pydantic_model_or_dict_manifest():
    request_dict = build_external_ai_request_from_manifest(_safe_manifest())
    # Now build from a pseudo-Pydantic model (object with model_dump)
    class _M:
        def model_dump(self):
            return _safe_manifest()
    request_model = build_external_ai_request_from_manifest(_M())
    assert request_dict.included_fact_count == request_model.included_fact_count


# ---------------------------------------------------------------------------
# Negative-import surface and Stage 9.2 isolation
# ---------------------------------------------------------------------------


def test_builder_module_does_not_import_network_clients():
    source = (_REPO_ROOT / "src/app_backend/services/ai_external_request_builder.py").read_text(
        encoding="utf-8"
    )
    lowered = source.lower()
    assert "import httpx" not in lowered
    assert "import requests" not in lowered
    assert "import aiohttp" not in lowered
    assert "from httpx" not in lowered
    assert "from requests" not in lowered
    assert "from aiohttp" not in lowered
    assert "urllib.request" not in lowered
    assert "socket.create_connection" not in lowered


def test_builder_module_does_not_read_env_or_external_llm_yaml():
    source = (_REPO_ROOT / "src/app_backend/services/ai_external_request_builder.py").read_text(
        encoding="utf-8"
    )
    assert "os.environ" not in source
    assert "os.getenv" not in source
    assert ".env" not in source
    assert "external_llm.yaml" not in source
    assert "open(" not in source


def test_builder_not_imported_by_stage_9_2_preview_service():
    source = (_REPO_ROOT / "src/app_backend/services/ai_preview_service.py").read_text(
        encoding="utf-8"
    )
    assert "ai_external_request_builder" not in source
    assert "build_external_ai_request_from_manifest" not in source


def test_builder_not_imported_by_ai_memo_renderer():
    source = (_REPO_ROOT / "src/app_backend/services/ai_memo_renderer.py").read_text(
        encoding="utf-8"
    )
    assert "ai_external_request_builder" not in source


def test_builder_not_imported_by_ai_context_service():
    source = (_REPO_ROOT / "src/app_backend/services/ai_context_service.py").read_text(
        encoding="utf-8"
    )
    assert "ai_external_request_builder" not in source


def test_builder_not_imported_by_main_app():
    source = (_REPO_ROOT / "src/app_backend/main.py").read_text(encoding="utf-8")
    assert "ai_external_request_builder" not in source


def test_no_network_modules_loaded_when_builder_used(monkeypatch):
    def _fail(*args, **kwargs):
        raise AssertionError("network must not be used in builder")

    monkeypatch.setattr(socket, "create_connection", _fail)
    request = build_external_ai_request_from_manifest(_safe_manifest())
    assert request.mode == "fake"


def test_no_new_http_routes_added_by_builder_import():
    from app_backend.main import app
    # Force builder import path
    from app_backend.services import ai_external_request_builder  # noqa: F401
    route_paths = {route.path for route in app.routes}
    for forbidden in (
        "/api/chat",
        "/api/search",
        "/api/ai/deepseek",
        "/api/ai/tavily",
        "/api/ai/external",
        "/api/ai/external-request",
    ):
        assert forbidden not in route_paths, f"forbidden route present: {forbidden}"
