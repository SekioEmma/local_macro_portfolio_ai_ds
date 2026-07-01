from __future__ import annotations

import json
from datetime import date

import pytest

from app_backend.services.agent_runtime import run_agent
from app_backend.services.agent_tool_registry import FINALIZE_TOOL_NAME
from app_backend.services.agent_trace_service import (
    AgentTraceEvent,
    AgentTraceService,
    InvalidTraceSessionId,
    sanitize_trace_payload,
    scan_trace_text_for_sensitive_markers,
    sha256_json,
    sha256_text,
)
from app_backend.services.llm_provider_adapter import ChatResponse
from tests.ai.test_agent_runtime_mocked import MockProvider, finalize_call, make_registry


def test_trace_service_writes_jsonl_without_raw_question(tmp_path):
    service = AgentTraceService(root_dir=tmp_path)

    service.start_session(
        session_id="session-1",
        user_question="raw user macro question",
        holdings_included=False,
        current_date="2026-06-30",
    )
    service.write_event(
        AgentTraceEvent(
            type="tool_call",
            session_id="session-1",
            step=1,
            data={"tool": "dashboard_query", "args_summary": {"series": "DGS10"}},
        )
    )
    service.end_session(session_id="session-1", final_status="ok", steps=1, warnings=[])

    path = service.trace_path("session-1")
    lines = path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 3
    assert "raw user macro question" not in path.read_text(encoding="utf-8")
    first = json.loads(lines[0])
    assert first["type"] == "session_start"
    assert first["schema_version"] == 1
    assert first["event_sequence"] == 1
    assert first["previous_event_hash"] is None
    assert first["event_hash"]
    assert first["data"]["user_question_sha256"] == sha256_text("raw user macro question")
    assert first["data"]["current_date"] == "2026-06-30"
    second = json.loads(lines[1])
    assert second["event_sequence"] == 2
    assert second["previous_event_hash"] == first["event_hash"]
    assert (tmp_path / "index.jsonl").exists()
    assert service.summary_path("session-1").exists()


def test_trace_service_rejects_unsafe_session_id(tmp_path):
    service = AgentTraceService(root_dir=tmp_path)

    with pytest.raises(InvalidTraceSessionId):
        service.write_event(AgentTraceEvent(type="session_start", session_id="../escape"))


def test_trace_service_overflow_writes_summary_without_raising(tmp_path):
    service = AgentTraceService(root_dir=tmp_path, max_session_bytes=400)

    service.write_event(AgentTraceEvent(type="small", session_id="session-2"))
    service.write_event(
        AgentTraceEvent(
            type="large",
            session_id="session-2",
            data={"payload": "x" * 800},
        )
    )
    service.write_event(
        AgentTraceEvent(
            type="ignored_after_overflow",
            session_id="session-2",
            data={"payload": "y" * 10},
        )
    )

    events = service.read_events("session-2")
    assert [event.type for event in events] == ["small", "trace_overflow"]
    assert events[1].previous_event_hash == events[0].event_hash
    summary = json.loads(service.summary_path("session-2").read_text(encoding="utf-8"))
    assert summary["overflowed"] is True
    assert summary["event_count"] == 2


def test_run_agent_can_persist_trace_when_service_is_injected(tmp_path):
    provider = MockProvider([ChatResponse(tool_calls=[finalize_call()], finish_reason="tool_calls")])
    service = AgentTraceService(root_dir=tmp_path)
    holdings_snapshot = {"positions": [{"ticker": "SPY", "quantity": 100}]}

    result = run_agent(
        session_id="session-3",
        user_question="Build a macro brief.",
        provider=provider,
        tool_registry=make_registry(),
        current_date=date(2026, 6, 30),
        tool_names=["dashboard_query", FINALIZE_TOOL_NAME],
        include_holdings=True,
        holdings_snapshot=holdings_snapshot,
        trace_service=service,
    )

    assert result.final_status == "ok"
    events = service.read_events("session-3")
    event_types = [event.type for event in events]
    assert event_types[0] == "session_start"
    assert "provider_call_started" in event_types
    assert "llm_completion" in event_types
    assert "macro_brief_validation" in event_types
    assert event_types[-1] == "session_end"
    assert events[0].data["holdings_included"] is True
    assert events[0].data["holdings_snapshot_sha256"] == sha256_json(holdings_snapshot)
    trace_text = service.trace_path("session-3").read_text(encoding="utf-8")
    assert "Build a macro brief." not in trace_text
    assert "quantity" not in trace_text


def test_trace_sanitizes_sensitive_payload_fields(tmp_path):
    service = AgentTraceService(root_dir=tmp_path)

    service.write_event(
        AgentTraceEvent(
            type="tool_call",
            session_id="session-4",
            data={
                "tool": "search_tavily",
                "query": "raw query about CPI",
                "api_key": "tvly-Secret1234567890",
                "raw_prompt": "full prompt text",
                "path": "C:\\Users\\someone\\secret.txt",
            },
        )
    )

    trace_text = service.trace_path("session-4").read_text(encoding="utf-8")
    assert "raw query about CPI" not in trace_text
    assert "tvly-Secret1234567890" not in trace_text
    assert "full prompt text" not in trace_text
    assert "C:\\Users\\someone\\secret.txt" not in trace_text
    assert "query_sha256" in trace_text
    assert "redacted_field_2" in trace_text
    assert service.scan_for_sensitive_markers("session-4") == []


def test_sanitize_trace_payload_hashes_args_without_raw_query():
    payload = sanitize_trace_payload(
        {
            "args": {"query": "private search query", "limit": 3},
            "nested": {"search_query": "another query"},
        }
    )

    assert "args_sha256" in payload
    assert "private search query" not in str(payload)
    assert payload["nested"]["search_query_sha256"] == sha256_text("another query")


def test_trace_scan_detects_contaminated_text():
    findings = scan_trace_text_for_sensitive_markers(
        '{"raw_prompt":"x","secret":"sk-abcdefghijklmnopqrstuvwxyz123456"}'
    )

    assert "raw_prompt" in findings
    assert any(finding.startswith("pattern:") for finding in findings)


def test_trace_replay_returns_debug_summary_without_raw_content(tmp_path):
    service = AgentTraceService(root_dir=tmp_path)
    service.start_session(
        session_id="session-5",
        user_question="private user question",
        holdings_included=False,
    )
    service.write_event(
        AgentTraceEvent(
            type="llm_completion",
            session_id="session-5",
            step=1,
            data={"finish_reason": "tool_calls", "tokens": 12},
        )
    )
    service.write_event(
        AgentTraceEvent(
            type="tool_result",
            session_id="session-5",
            step=1,
            data={"tool_name": "dashboard_query", "status": "ok"},
        )
    )

    replay = service.replay("session-5")

    assert [message["role"] for message in replay.message_history] == [
        "system",
        "assistant",
        "tool",
    ]
    joined = "\n".join(message["content"] for message in replay.message_history)
    assert "private user question" not in joined
    assert "question_sha256=" in joined
