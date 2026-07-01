from __future__ import annotations

from fastapi.testclient import TestClient

from app_backend.main import app, get_agent_trace_debug_enabled, get_agent_trace_service
from app_backend.services.agent_trace_service import AgentTraceEvent, AgentTraceService


def _client() -> TestClient:
    return TestClient(app)


def test_agent_trace_endpoint_replays_sanitized_debug_history(tmp_path):
    service = AgentTraceService(root_dir=tmp_path)
    service.start_session(
        session_id="trace-route-1",
        user_question="private macro question",
        holdings_included=False,
        current_date="2026-06-30",
    )
    service.write_event(
        AgentTraceEvent(
            type="llm_completion",
            session_id="trace-route-1",
            step=1,
            data={"finish_reason": "tool_calls", "tokens": 44},
        )
    )
    service.write_event(
        AgentTraceEvent(
            type="tool_result",
            session_id="trace-route-1",
            step=1,
            data={"tool_name": "dashboard_query", "status": "ok"},
        )
    )
    app.dependency_overrides[get_agent_trace_service] = lambda: service
    app.dependency_overrides[get_agent_trace_debug_enabled] = lambda: True

    try:
        response = _client().get("/api/agent/trace/trace-route-1")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert body["session_id"] == "trace-route-1"
    assert body["event_count"] == 3
    assert body["sensitive_findings"] == []
    assert [message["role"] for message in body["message_history"]] == [
        "system",
        "assistant",
        "tool",
    ]
    assert "private macro question" not in response.text
    assert "question_sha256=" in response.text


def test_agent_trace_endpoint_returns_empty_replay_for_missing_trace(tmp_path):
    service = AgentTraceService(root_dir=tmp_path)
    app.dependency_overrides[get_agent_trace_service] = lambda: service
    app.dependency_overrides[get_agent_trace_debug_enabled] = lambda: True

    try:
        response = _client().get("/api/agent/trace/missing-session")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json() == {
        "session_id": "missing-session",
        "event_count": 0,
        "sensitive_findings": [],
        "message_history": [],
        "events": [],
    }


def test_agent_trace_endpoint_is_disabled_by_default(tmp_path):
    service = AgentTraceService(root_dir=tmp_path)
    app.dependency_overrides[get_agent_trace_service] = lambda: service

    try:
        response = _client().get("/api/agent/trace/trace-route-disabled")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 404
    assert response.json()["detail"] == "agent_trace_debug_disabled"


def test_agent_trace_route_registered():
    paths = {route.path for route in app.routes}

    assert "/api/agent/trace/{session_id}" in paths
