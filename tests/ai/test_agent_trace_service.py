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
    TraceSizeExceeded,
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

    path = tmp_path / "session-1.jsonl"
    lines = path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 3
    assert "raw user macro question" not in path.read_text(encoding="utf-8")
    first = json.loads(lines[0])
    assert first["type"] == "session_start"
    assert first["data"]["user_question_sha256"] == sha256_text("raw user macro question")
    assert first["data"]["current_date"] == "2026-06-30"


def test_trace_service_rejects_unsafe_session_id(tmp_path):
    service = AgentTraceService(root_dir=tmp_path)

    with pytest.raises(InvalidTraceSessionId):
        service.write_event(AgentTraceEvent(type="session_start", session_id="../escape"))


def test_trace_service_enforces_session_size_limit(tmp_path):
    service = AgentTraceService(root_dir=tmp_path, max_session_bytes=40)

    with pytest.raises(TraceSizeExceeded):
        service.write_event(
            AgentTraceEvent(
                type="large",
                session_id="session-2",
                data={"payload": "x" * 80},
            )
        )


def test_run_agent_can_persist_trace_when_service_is_injected(tmp_path):
    provider = MockProvider([ChatResponse(tool_calls=[finalize_call()], finish_reason="tool_calls")])
    service = AgentTraceService(root_dir=tmp_path)
    holdings_snapshot = {"ticker": "SPY", "amount": 100}

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
    assert [event.type for event in events] == [
        "session_start",
        "llm_completion",
        "macro_brief_validation",
        "session_end",
    ]
    assert events[0].data["holdings_included"] is True
    assert events[0].data["holdings_snapshot_sha256"] == sha256_json(holdings_snapshot)
    trace_text = (tmp_path / "session-3.jsonl").read_text(encoding="utf-8")
    assert "Build a macro brief." not in trace_text
    assert "amount" not in trace_text
