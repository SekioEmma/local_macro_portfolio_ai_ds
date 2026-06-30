from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app_backend.main import app, get_agent_run_service
from app_backend.schemas.agent_api import AgentRunRequest
from app_backend.services.agent_api_service import AgentRunService
from app_backend.services.agent_tool_registry import FINALIZE_TOOL_NAME
from app_backend.services.agent_tool_registry import ToolSpec
from app_backend.services.agent_trace_service import AgentTraceService
from app_backend.services.llm_provider_adapter import ChatResponse
from tests.ai.test_agent_runtime_mocked import MockProvider, finalize_call, make_registry


@pytest.fixture(autouse=True)
def _clear_overrides():
    yield
    app.dependency_overrides.clear()


def _client() -> TestClient:
    return TestClient(app)


def _service(tmp_path: Path, provider: MockProvider) -> AgentRunService:
    def registry_factory(confirm_external_search: bool):
        registry = make_registry()
        if confirm_external_search:
            for name in ["search_tavily", "commodity_quote", "quote_dxy"]:
                registry.register(
                    ToolSpec(
                        name=name,
                        description=f"Fake {name} tool.",
                        parameters_schema={
                            "type": "object",
                            "properties": {},
                            "required": [],
                            "additionalProperties": True,
                        },
                        handler=lambda args: {"results": [], "args": args},
                    )
                )
        return registry

    return AgentRunService(
        provider_factory=lambda: provider,
        registry_factory=registry_factory,
        trace_factory=lambda: AgentTraceService(root_dir=tmp_path),
        current_date_provider=lambda: date(2026, 6, 30),
    )


def _install_service(service: AgentRunService) -> None:
    app.dependency_overrides[get_agent_run_service] = lambda: service


def test_agent_run_endpoint_returns_rendered_public_brief(tmp_path):
    provider = MockProvider([ChatResponse(tool_calls=[finalize_call()], finish_reason="tool_calls")])
    _install_service(_service(tmp_path, provider))

    response = _client().post(
        "/api/agent/run",
        json={
            "session_id": "agent-session-1",
            "user_question": "Build a macro brief.",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["session_id"] == "agent-session-1"
    assert body["final_status"] == "ok"
    assert body["source_visibility_mode"] == "public"
    assert "rendered_markdown" in body
    assert body["brief"]["core_conclusion"] == "Macro environment remains balanced."
    assert body["sources"][0]["url"] == "https://fred.stlouisfed.org/series/DGS10"
    assert "credit_snapshot" not in body["rendered_markdown"]
    assert "Build a macro brief." not in response.text


def test_agent_run_endpoint_debug_mode_returns_internal_sources(tmp_path):
    provider = MockProvider([ChatResponse(tool_calls=[finalize_call()], finish_reason="tool_calls")])
    _install_service(_service(tmp_path, provider))

    response = _client().post(
        "/api/agent/run",
        json={
            "session_id": "agent-session-2",
            "user_question": "Build a macro brief.",
            "source_visibility_mode": "debug",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["source_visibility_mode"] == "debug"
    assert any(source["origin"] == "rag" for source in body["sources"])
    assert "rag_doc_id=credit_snapshot" in body["source_markdown"]


def test_agent_run_without_search_confirmation_does_not_expose_search_tool(tmp_path):
    provider = MockProvider([ChatResponse(tool_calls=[finalize_call()], finish_reason="tool_calls")])
    _install_service(_service(tmp_path, provider))

    response = _client().post(
        "/api/agent/run",
        json={
            "session_id": "agent-session-3",
            "user_question": "latest geopolitical oil news",
            "confirm_external_search": False,
        },
    )

    assert response.status_code == 200
    tool_names = [
        tool["function"]["name"]
        for tool in provider.calls[0]["tools"]
    ]
    assert "search_tavily" not in tool_names
    assert "commodity_quote" not in tool_names
    assert "quote_dxy" not in tool_names
    assert "current_public_news" in response.json()["missing_topics"]


def test_agent_run_with_search_confirmation_exposes_search_tool_to_runtime(tmp_path):
    provider = MockProvider([ChatResponse(tool_calls=[finalize_call()], finish_reason="tool_calls")])
    _install_service(_service(tmp_path, provider))

    response = _client().post(
        "/api/agent/run",
        json={
            "session_id": "agent-session-4",
            "user_question": "latest geopolitical oil news",
            "confirm_external_search": True,
        },
    )

    assert response.status_code == 200
    tool_names = [
        tool["function"]["name"]
        for tool in provider.calls[0]["tools"]
    ]
    assert "search_tavily" in tool_names
    assert "commodity_quote" in tool_names
    assert "quote_dxy" in tool_names
    body = response.json()
    assert body["search_required"] is True
    assert any(
        need["topic"] == "current_public_news" and need["status"] == "search_required"
        for need in body["information_plan"]["needs"]
    )


def test_default_agent_run_service_wires_registry_without_eager_external_calls():
    service = get_agent_run_service()

    local_registry = service.registry_factory(False)
    external_registry = service.registry_factory(True)

    assert FINALIZE_TOOL_NAME in local_registry.names()
    assert "rag_retrieve" in local_registry.names()
    assert "search_tavily" not in local_registry.names()
    assert "commodity_quote" not in local_registry.names()
    assert "quote_dxy" not in local_registry.names()
    assert "search_tavily" in external_registry.names()
    assert "commodity_quote" in external_registry.names()
    assert "quote_dxy" in external_registry.names()
    assert service.provider_factory().name == "deepseek"


def test_agent_run_rejects_holdings_until_server_side_snapshot_is_wired(tmp_path):
    provider = MockProvider([ChatResponse(tool_calls=[finalize_call()], finish_reason="tool_calls")])
    _install_service(_service(tmp_path, provider))

    response = _client().post(
        "/api/agent/run",
        json={
            "user_question": "Build a macro brief.",
            "include_holdings": True,
        },
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "holdings_toggle_backend_not_wired"


def test_agent_run_request_schema_defaults_are_public_and_local_first():
    request = AgentRunRequest(
        user_question="Build a macro brief.",
    )

    assert request.source_visibility_mode == "public"
    assert request.confirm_external_search is False
    assert request.include_holdings is False


def test_agent_run_rejects_client_supplied_current_date(tmp_path):
    provider = MockProvider([ChatResponse(tool_calls=[finalize_call()], finish_reason="tool_calls")])
    _install_service(_service(tmp_path, provider))

    response = _client().post(
        "/api/agent/run",
        json={
            "session_id": "agent-session-current-date",
            "user_question": "Build a macro brief.",
            "current_date": "1999-01-01",
        },
    )

    assert response.status_code == 422
    assert not provider.calls


def test_agent_route_registered_without_forbidden_legacy_routes():
    paths = {route.path for route in app.routes}

    assert "/api/agent/run" in paths
    assert "/api/chat" not in paths
    assert "/api/ai/tavily" not in paths
