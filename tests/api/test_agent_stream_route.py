from __future__ import annotations

import json
import threading
import time
from datetime import date
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app_backend.schemas.agent_api import AgentRunRequest
from app_backend.main import app, get_agent_run_registry, get_agent_run_service
from app_backend.services.agent_api_service import AgentRunService
from app_backend.services.agent_run_registry import AgentRunRegistry
from app_backend.services.agent_runtime import AgentRuntimeEvent
from app_backend.services.agent_stream_service import AgentStreamService
from app_backend.services.agent_tool_registry import FINALIZE_TOOL_NAME, ToolSpec
from app_backend.services.agent_trace_service import AgentTraceService
from app_backend.services.holdings_consent_service import HoldingsConsentService
from app_backend.services.holdings_external_context_service import (
    HoldingsExternalContextService,
)
from app_backend.services.llm_provider_adapter import ChatResponse, ToolCall
from tests.ai.test_agent_runtime_mocked import MockProvider, brief_payload, finalize_call, make_registry


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
        enable_evidence_ledger=False,
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
    assert any(
        event["type"] == "brief_section"
        and event["payload"]["section"] == "temporal_envelope"
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


def test_agent_stream_route_rejects_client_supplied_current_date(tmp_path):
    provider = MockProvider([ChatResponse(tool_calls=[finalize_call()], finish_reason="tool_calls")])
    _install_service(tmp_path, provider)

    try:
        response = _client().post(
            "/api/agent/run/stream",
            json={
                "session_id": "agent-stream-current-date",
                "user_question": "Build a macro brief.",
                "current_date": "1999-01-01",
            },
            headers={"accept": "text/event-stream"},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 422
    assert not provider.calls


def test_default_agent_stream_rejects_holdings_activation_when_snapshot_provider_is_unwired():
    try:
        response = _client().post(
            "/api/agent/run/stream",
            json={
                "session_id": "agent-stream-default-unwired",
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
    assert events[-1]["payload"]["detail"] == "holdings_snapshot_backend_not_wired"


def test_agent_stream_with_consent_injects_holdings_without_sse_leak(tmp_path):
    provider = MockProvider([ChatResponse(tool_calls=[finalize_call()], finish_reason="tool_calls")])
    consent_service = HoldingsConsentService()
    token = consent_service.issue(session_id="agent-stream-holdings").token
    context_service = HoldingsExternalContextService(
        lambda _session_id: {
            "positions": [{"ticker": "SPY", "quantity": 10, "market_value": 5000}],
            "asset_class_breakdown": {"equity": 1.0},
        }
    )
    service = AgentRunService(
        provider_factory=lambda: provider,
        registry_factory=lambda _confirm_external_search: make_registry(),
        trace_factory=lambda: AgentTraceService(root_dir=tmp_path),
        current_date_provider=lambda: date(2026, 6, 30),
        holdings_consent_service=consent_service,
        holdings_context_service=context_service,
        enable_evidence_ledger=False,
    )
    app.dependency_overrides[get_agent_run_service] = lambda: service

    try:
        response = _client().post(
            "/api/agent/run/stream",
            json={
                "session_id": "agent-stream-holdings",
                "user_question": "Build a macro brief.",
                "include_holdings": True,
                "holdings_consent_token": token,
            },
            headers={"accept": "text/event-stream"},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    system_prompt = provider.calls[0]["messages"][0].content
    assert "explicitly approved for this run only" in system_prompt
    assert '"ticker": "SPY"' in system_prompt
    assert "market_value" not in response.text
    assert "5000" not in response.text
    with pytest.raises(Exception):
        consent_service.validate(token, session_id="agent-stream-holdings")


def test_agent_stream_blocks_model_holdings_output_disclosure(tmp_path):
    leaking_payload = brief_payload()
    leaking_payload["core_conclusion"] = "SPY market value is 5000."
    provider = MockProvider([ChatResponse(tool_calls=[finalize_call("stream-leak-final", leaking_payload)], finish_reason="tool_calls")])
    consent_service = HoldingsConsentService()
    token = consent_service.issue(session_id="agent-stream-holdings-leak").token
    context_service = HoldingsExternalContextService(
        lambda _session_id: {
            "positions": [{"ticker": "SPY", "quantity": 10, "market_value": 5000}],
            "asset_class_breakdown": {"equity": 1.0},
        }
    )
    service = AgentRunService(
        provider_factory=lambda: provider,
        registry_factory=lambda _confirm_external_search: make_registry(),
        trace_factory=lambda: AgentTraceService(root_dir=tmp_path),
        current_date_provider=lambda: date(2026, 6, 30),
        holdings_consent_service=consent_service,
        holdings_context_service=context_service,
        enable_evidence_ledger=False,
    )
    app.dependency_overrides[get_agent_run_service] = lambda: service

    try:
        response = _client().post(
            "/api/agent/run/stream",
            json={
                "session_id": "agent-stream-holdings-leak",
                "user_question": "Build a macro brief.",
                "include_holdings": True,
                "holdings_consent_token": token,
            },
            headers={"accept": "text/event-stream"},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    events = _events_from_sse(response.text)
    assert not any(event["type"] == "brief_section" for event in events)
    assert events[-1]["type"] == "complete"
    assert events[-1]["payload"]["final_status"] == "validation_failed"
    assert "5000" not in response.text


def test_agent_stream_route_propagates_cancel_before_tool_dispatch(tmp_path):
    registry = AgentRunRegistry()
    session_id = "agent-stream-cancel"
    dispatches: list[dict[str, Any]] = []

    class CancellingProvider:
        name = "deepseek"

        def __init__(self) -> None:
            self.calls: list[dict[str, Any]] = []

        def chat(self, **kwargs):  # noqa: ANN003, ANN201
            self.calls.append(kwargs)
            registry.request_cancel(session_id)
            return ChatResponse(
                tool_calls=[
                    ToolCall(
                        id="call-1",
                        name="dashboard_query",
                        arguments={"series": "DGS10"},
                    )
                ],
                finish_reason="tool_calls",
            )

    provider = CancellingProvider()

    def registry_factory(_confirm_external_search: bool):
        local_registry = make_registry(on_dashboard=dispatches)
        return local_registry

    service = AgentRunService(
        provider_factory=lambda: provider,
        registry_factory=registry_factory,
        trace_factory=lambda: AgentTraceService(root_dir=tmp_path),
        current_date_provider=lambda: date(2026, 6, 30),
        enable_evidence_ledger=False,
    )
    app.dependency_overrides[get_agent_run_service] = lambda: service
    app.dependency_overrides[get_agent_run_registry] = lambda: registry

    try:
        response = _client().post(
            "/api/agent/run/stream",
            json={
                "session_id": session_id,
                "user_question": "Build a cancellable macro brief.",
            },
            headers={"accept": "text/event-stream"},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    events = _events_from_sse(response.text)
    event_types = [event["type"] for event in events]
    assert "cancelled" in event_types
    assert "tool_result" not in event_types
    assert "brief_section" not in event_types
    assert events[-1]["type"] == "complete"
    assert events[-1]["payload"]["final_status"] == "cancelled"
    assert dispatches == []
    assert registry.is_cancelled(session_id) is False


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


def test_agent_stream_service_enforces_queue_size_limit():
    class FloodService:
        def run(self, request, *, event_callback=None, cancellation_requested=None):  # noqa: ANN001, ANN201
            del request, cancellation_requested
            assert event_callback is not None
            for index in range(2000):
                event_callback(
                    AgentRuntimeEvent(
                        type="provider_call_started",
                        step=index,
                        data={"phase": "research"},
                    )
                )
            return _MinimalResponse()

    class _MinimalResponse:
        def model_dump(self, *, mode: str):  # noqa: ANN201
            del mode
            return {
                "final_status": "ok",
                "steps": 0,
                "trace_session_id": "queue-overflow",
                "brief": None,
            }

    stream = AgentStreamService(FloodService(), max_queue_size=1).stream(
        AgentRunRequest(
            session_id="queue-overflow",
            user_question="Build a macro brief.",
        )
    )
    events = _events_from_sse("".join(stream))

    assert events[-1]["type"] == "error"
    assert events[-1]["payload"]["detail"] == "agent_stream_queue_overflow"


def test_agent_stream_service_sanitizes_unhandled_exception_detail():
    class ExplodingService:
        def run(self, request, *, event_callback=None, cancellation_requested=None):  # noqa: ANN001, ANN201
            del request, event_callback, cancellation_requested
            raise RuntimeError(
                r"raw_prompt=secret question sk-live-secret C:\Users\Alice\holdings.csv"
            )

    stream = AgentStreamService(ExplodingService()).stream(
        AgentRunRequest(
            session_id="stream-explosion",
            user_question="Build a macro brief.",
        )
    )
    text = "".join(stream)
    events = _events_from_sse(text)

    assert events[-1]["type"] == "error"
    assert events[-1]["payload"]["error_type"] == "RuntimeError"
    assert events[-1]["payload"]["detail"] == "agent_stream_internal_error"
    assert "raw_prompt" not in text
    assert "sk-live-secret" not in text
    assert "holdings.csv" not in text


def test_agent_stream_service_emits_heartbeat_while_worker_is_running():
    class SlowService:
        def run(self, request, *, event_callback=None, cancellation_requested=None):  # noqa: ANN001, ANN201
            del request, event_callback, cancellation_requested
            time.sleep(0.05)
            return _MinimalResponse(final_status="ok")

    stream = AgentStreamService(
        SlowService(),
        heartbeat_interval_seconds=0.01,
    ).stream(
        AgentRunRequest(
            session_id="stream-heartbeat",
            user_question="Build a macro brief.",
        )
    )

    text = "".join(stream)
    events = _events_from_sse(text)
    heartbeats = [event for event in events if event["type"] == "heartbeat"]

    assert heartbeats
    assert heartbeats[0]["payload"] == {"status": "running"}
    assert events[-1]["type"] == "complete"


def test_agent_stream_service_requests_cancel_when_client_disconnects():
    registry = AgentRunRegistry()
    session_id = "stream-disconnect-cancel"
    cancellation_seen = threading.Event()

    class DisconnectAwareService:
        def run(self, request, *, event_callback=None, cancellation_requested=None):  # noqa: ANN001, ANN201
            del request, event_callback
            assert cancellation_requested is not None
            deadline = time.monotonic() + 1.0
            while time.monotonic() < deadline:
                if cancellation_requested():
                    cancellation_seen.set()
                    return _MinimalResponse(final_status="cancelled")
                time.sleep(0.005)
            return _MinimalResponse(final_status="ok")

    probes = 0

    def client_disconnected() -> bool:
        nonlocal probes
        probes += 1
        return probes >= 2

    stream = AgentStreamService(
        DisconnectAwareService(),
        run_registry=registry,
        heartbeat_interval_seconds=0.01,
    ).stream(
        AgentRunRequest(
            session_id=session_id,
            user_question="Build a macro brief.",
        ),
        client_disconnected=client_disconnected,
    )

    first = next(stream)
    with pytest.raises(StopIteration):
        next(stream)

    events = _events_from_sse(first)
    assert events[0]["type"] in {"run_started", "heartbeat"}
    assert cancellation_seen.wait(timeout=1.0)
    assert probes >= 2


class _MinimalResponse:
    def __init__(self, *, final_status: str) -> None:
        self._final_status = final_status

    def model_dump(self, *, mode: str):  # noqa: ANN201
        del mode
        return {
            "final_status": self._final_status,
            "steps": 0,
            "trace_session_id": "minimal-stream-response",
            "brief": None,
        }
