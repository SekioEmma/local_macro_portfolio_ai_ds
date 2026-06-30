from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

from app_backend.main import app, get_agent_run_registry, get_agent_run_service
from app_backend.services.agent_api_service import AgentRunService
from app_backend.services.agent_run_registry import AgentRunRegistry
from app_backend.services.agent_tool_registry import FINALIZE_TOOL_NAME, ToolSpec
from app_backend.services.agent_trace_service import AgentTraceService
from app_backend.services.llm_provider_adapter import ChatResponse, ToolCall
from tests.ai.test_agent_runtime_mocked import MockProvider, finalize_call, make_registry


def _client() -> TestClient:
    return TestClient(app)


def _install_service(tmp_path: Path, provider: MockProvider) -> None:
    def registry_factory(_confirm_external_search: bool):
        registry = make_registry()
        registry.register(
            ToolSpec(
                name="rag_retrieve",
                description="Mock RAG retrieve.",
                parameters_schema={
                    "type": "object",
                    "properties": {"query": {"type": "string"}},
                    "required": ["query"],
                    "additionalProperties": False,
                },
                handler=lambda args: {"chunks": [], "query": args["query"]},
            )
        )
        return registry

    service = AgentRunService(
        provider_factory=lambda: provider,
        registry_factory=registry_factory,
        trace_factory=lambda: AgentTraceService(root_dir=tmp_path),
        current_date_provider=lambda: date(2026, 6, 30),
    )
    app.dependency_overrides[get_agent_run_service] = lambda: service


def _events_from_sse(text: str) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for block in text.strip().split("\n\n"):
        data_line = next(
            (line for line in block.splitlines() if line.startswith("data: ")),
            None,
        )
        if data_line:
            events.append(json.loads(data_line.removeprefix("data: ")))
    return events


def test_agent_stream_route_emits_sanitized_lifecycle_and_sections(tmp_path):
    provider = MockProvider(
        [
            ChatResponse(
                tool_calls=[
                    ToolCall(
                        id="call-1",
                        name="dashboard_query",
                        arguments={"series": "DGS10"},
                    )
                ],
                finish_reason="tool_calls",
            ),
            ChatResponse(tool_calls=[finalize_call()], finish_reason="tool_calls"),
        ]
    )
    _install_service(tmp_path, provider)

    try:
        response = _client().post(
            "/api/agent/run/stream",
            json={
                "session_id": "agent-stream-1",
                "user_question": "Build a private macro brief.",
            },
            headers={"accept": "text/event-stream"},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert "Build a private macro brief." not in response.text
    events = _events_from_sse(response.text)
    event_types = [event["type"] for event in events]

    assert event_types[0] == "run_started"
    assert "information_plan" in event_types
    assert "provider_call_started" in event_types
    assert "provider_call_finished" in event_types
    assert "tool_result" in event_types
    assert "brief_validated" in event_types
    assert "brief_section" in event_types
    assert event_types[-1] == "complete"
    assert [event["sequence"] for event in events] == list(range(1, len(events) + 1))
    assert all(event["session_id"] == "agent-stream-1" for event in events)
    assert all({"event_id", "timestamp", "payload"}.issubset(event) for event in events)
    assert any(
        event["type"] == "brief_section"
        and event["payload"]["section"] == "core_conclusion"
        for event in events
    )


def test_agent_stream_route_converts_input_errors_to_sse_error(tmp_path):
    provider = MockProvider([ChatResponse(tool_calls=[finalize_call()], finish_reason="tool_calls")])
    _install_service(tmp_path, provider)

    try:
        response = _client().post(
            "/api/agent/run/stream",
            json={
                "session_id": "agent-stream-error",
                "user_question": "Build a macro brief.",
                "include_holdings": True,
            },
            headers={"accept": "text/event-stream"},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    events = _events_from_sse(response.text)
    assert events[-1]["type"] == "error"
    assert events[-1]["payload"]["detail"] == "holdings_consent_service_not_wired"
    assert not provider.calls


def test_agent_cancel_route_is_idempotent():
    registry = AgentRunRegistry()
    app.dependency_overrides[get_agent_run_registry] = lambda: registry

    try:
        first = _client().post("/api/agent/run/cancel-me/cancel")
        second = _client().post("/api/agent/run/cancel-me/cancel")
    finally:
        app.dependency_overrides.clear()

    assert first.status_code == 200
    assert first.json() == {
        "session_id": "cancel-me",
        "cancelled": True,
        "already_cancelled": False,
    }
    assert second.status_code == 200
    assert second.json()["already_cancelled"] is True
    assert registry.is_cancelled("cancel-me") is True


def test_agent_stream_and_cancel_routes_registered():
    paths = {route.path for route in app.routes}

    assert "/api/agent/run/stream" in paths
    assert "/api/agent/run/{session_id}/cancel" in paths
    assert FINALIZE_TOOL_NAME == "finalize_macro_brief"
