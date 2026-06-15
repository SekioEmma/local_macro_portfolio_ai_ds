"""Stage 9.3-A DeepSeek adapter skeleton regression tests.

Covers default-disabled behavior, fake-mode determinism, network-mode
fail-closed, and the privacy / boundary fields on the fake response.

No real network call is exercised. Any accidental import of httpx /
requests / aiohttp at module import time would also be caught by the
import-surface test.
"""
from __future__ import annotations

import socket
import sys
from pathlib import Path

import pytest

from app_backend.schemas.ai_external import (
    ExternalAIAdapterConfig,
    ExternalAIRequest,
)
from app_backend.services.ai_external_adapter import BlockedAdapterError
from app_backend.services.deepseek_adapter import (
    DeepSeekAdapter,
    FakeDeepSeekAdapter,
    default_disabled_config,
    fake_only_config,
)


def _valid_request(mode: str = "fake") -> ExternalAIRequest:
    return ExternalAIRequest(
        request_id="req-test-001",
        provider="deepseek",
        mode=mode,
        user_intent_summary="Review current macro context (sanitized).",
        context_preview_summary="2 facts and 1 model output included; 1 excluded fact.",
        included_fact_count=2,
        included_model_output_count=1,
        excluded_context_summary="1 excluded fact (status_research_needed).",
        boundary_notices=[
            "Reference evidence only.",
            "Not an action directive.",
        ],
        memo_type="daily_review_memo",
        preview_type=None,
        validator_required=True,
    )


# ---------------------------------------------------------------------------
# Default disabled behavior
# ---------------------------------------------------------------------------


def test_default_config_is_disabled():
    cfg = default_disabled_config()
    assert cfg.enabled is False
    assert cfg.mode == "disabled"
    assert cfg.allow_network is False
    assert cfg.save_raw_prompt is False
    assert cfg.save_raw_response is False
    assert cfg.requires_user_switch is True
    assert cfg.requires_context_preview is True
    assert cfg.requires_validator is True


def test_default_disabled_adapter_cannot_generate():
    adapter = DeepSeekAdapter(default_disabled_config())
    with pytest.raises(BlockedAdapterError) as exc:
        adapter.generate(_valid_request())
    assert "adapter_disabled_in_stage_9_3_a" in exc.value.findings


# ---------------------------------------------------------------------------
# Fake mode behavior
# ---------------------------------------------------------------------------


def test_fake_mode_returns_deterministic_fake_response():
    adapter = FakeDeepSeekAdapter()
    first = adapter.generate(_valid_request())
    second = adapter.generate(_valid_request())
    assert first == second
    assert first.fake_response is True
    assert first.external_model_called is False


def test_fake_mode_marks_external_model_called_false():
    adapter = FakeDeepSeekAdapter()
    response = adapter.generate(_valid_request())
    assert response.external_model_called is False
    assert response.privacy_summary.external_model_called is False


def test_fake_mode_marks_fake_response_true():
    response = FakeDeepSeekAdapter().generate(_valid_request())
    assert response.fake_response is True


def test_fake_mode_requires_human_review_required_true():
    response = FakeDeepSeekAdapter().generate(_valid_request())
    assert response.human_review_required is True


def test_fake_mode_not_saved_by_default():
    response = FakeDeepSeekAdapter().generate(_valid_request())
    assert response.not_saved_by_default is True
    assert response.privacy_summary.saved_by_default is False


def test_fake_mode_uses_manifest_only_flags():
    response = FakeDeepSeekAdapter().generate(_valid_request())
    assert response.privacy_summary.uses_ai_context_manifest_only is True
    assert response.privacy_summary.uses_holdings_line_items is False
    assert response.privacy_summary.uses_raw_provider_payloads is False
    assert response.privacy_summary.uses_raw_prompts is False
    assert response.privacy_summary.search_called is False


def test_fake_mode_content_includes_boundary_phrase():
    response = FakeDeepSeekAdapter().generate(_valid_request())
    assert "not an action directive" in response.content.lower()
    assert "fake" in response.content.lower()


# ---------------------------------------------------------------------------
# Network mode fail-closed
# ---------------------------------------------------------------------------


def test_network_mode_config_fails_closed():
    """Constructing a config with network mode must be blocked at adapter init."""
    cfg = ExternalAIAdapterConfig(
        provider="deepseek",
        enabled=True,
        mode="network",
        allow_network=True,
        requires_user_switch=True,
        requires_context_preview=True,
        requires_validator=True,
        save_raw_prompt=False,
        save_raw_response=False,
    )
    with pytest.raises(BlockedAdapterError) as exc:
        DeepSeekAdapter(cfg)
    findings = exc.value.findings
    assert any("network" in f for f in findings)
    assert any("allow_network" in f for f in findings)


def test_enabled_with_allow_network_true_fails_closed():
    cfg = ExternalAIAdapterConfig(
        provider="deepseek",
        enabled=True,
        mode="fake",
        allow_network=True,
        requires_user_switch=True,
        requires_context_preview=True,
        requires_validator=True,
        save_raw_prompt=False,
        save_raw_response=False,
    )
    with pytest.raises(BlockedAdapterError) as exc:
        DeepSeekAdapter(cfg)
    assert any("allow_network" in f for f in exc.value.findings)


def test_save_raw_prompt_true_fails_closed():
    cfg = fake_only_config()
    cfg = cfg.model_copy(update={"save_raw_prompt": True})
    with pytest.raises(BlockedAdapterError) as exc:
        DeepSeekAdapter(cfg)
    assert any("save_raw_prompt" in f for f in exc.value.findings)


def test_save_raw_response_true_fails_closed():
    cfg = fake_only_config().model_copy(update={"save_raw_response": True})
    with pytest.raises(BlockedAdapterError) as exc:
        DeepSeekAdapter(cfg)
    assert any("save_raw_response" in f for f in exc.value.findings)


def test_disabled_requires_user_switch_check():
    cfg = ExternalAIAdapterConfig(
        provider="deepseek",
        enabled=True,
        mode="fake",
        allow_network=False,
        requires_user_switch=False,
        requires_context_preview=True,
        requires_validator=True,
        save_raw_prompt=False,
        save_raw_response=False,
    )
    with pytest.raises(BlockedAdapterError) as exc:
        DeepSeekAdapter(cfg)
    assert any("user_switch" in f for f in exc.value.findings)


# ---------------------------------------------------------------------------
# Import-time surface: no httpx/requests/aiohttp pulled by the adapter
# ---------------------------------------------------------------------------


def test_deepseek_adapter_module_does_not_import_network_clients():
    """Reading the source should show no network-client imports."""
    source = Path("src/app_backend/services/deepseek_adapter.py").read_text(
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


def test_ai_external_adapter_module_does_not_import_network_clients():
    source = Path("src/app_backend/services/ai_external_adapter.py").read_text(
        encoding="utf-8"
    )
    lowered = source.lower()
    assert "import httpx" not in lowered
    assert "import requests" not in lowered
    assert "import aiohttp" not in lowered


def test_no_network_modules_loaded_when_adapter_used(monkeypatch):
    """A fake-mode generate call must not touch the network."""
    def _fail(*args, **kwargs):
        raise AssertionError("network must not be used in Stage 9.3-A")

    monkeypatch.setattr(socket, "create_connection", _fail)
    # If httpx/requests/aiohttp were imported, we still want to fail-closed
    # by ensuring the adapter does not exercise any of them.
    response = FakeDeepSeekAdapter().generate(_valid_request())
    assert response.fake_response is True


def test_deepseek_module_does_not_read_env_or_external_llm_yaml():
    source = Path("src/app_backend/services/deepseek_adapter.py").read_text(
        encoding="utf-8"
    )
    assert "os.environ" not in source
    assert 'os.getenv' not in source
    assert ".env" not in source
    assert "external_llm.yaml" not in source


def test_ai_external_module_does_not_read_env_or_external_llm_yaml():
    source = Path("src/app_backend/services/ai_external_adapter.py").read_text(
        encoding="utf-8"
    )
    assert "os.environ" not in source
    assert 'os.getenv' not in source
    # The guard tokens table can mention ".env" / "external_llm.yaml" as
    # forbidden tokens, but the adapter must never READ them.
    assert "open(" not in source


# ---------------------------------------------------------------------------
# Stage 9.2 preview endpoints must not call the adapter
# ---------------------------------------------------------------------------


def test_ai_preview_service_does_not_import_deepseek_adapter():
    source = Path("src/app_backend/services/ai_preview_service.py").read_text(
        encoding="utf-8"
    )
    assert "deepseek_adapter" not in source
    assert "DeepSeekAdapter" not in source
    assert "FakeDeepSeekAdapter" not in source
    assert "ai_external_adapter" not in source


def test_ai_memo_renderer_does_not_import_deepseek_adapter():
    source = Path("src/app_backend/services/ai_memo_renderer.py").read_text(
        encoding="utf-8"
    )
    assert "deepseek_adapter" not in source
    assert "DeepSeekAdapter" not in source
    assert "ai_external_adapter" not in source


def test_ai_context_service_does_not_import_deepseek_adapter():
    source = Path("src/app_backend/services/ai_context_service.py").read_text(
        encoding="utf-8"
    )
    assert "deepseek_adapter" not in source
    assert "DeepSeekAdapter" not in source
    assert "ai_external_adapter" not in source


def test_main_app_does_not_import_deepseek_adapter():
    source = Path("src/app_backend/main.py").read_text(encoding="utf-8")
    assert "deepseek_adapter" not in source
    assert "DeepSeekAdapter" not in source
    assert "ai_external_adapter" not in source


# ---------------------------------------------------------------------------
# Endpoint surface unchanged
# ---------------------------------------------------------------------------


def test_no_deepseek_chat_search_routes_exist():
    from app_backend.main import app

    route_paths = {route.path for route in app.routes}
    assert "/api/chat" not in route_paths
    assert "/api/search" not in route_paths
    assert "/api/ai/deepseek" not in route_paths
    assert "/api/ai/tavily" not in route_paths
    assert "/api/ai/external" not in route_paths
