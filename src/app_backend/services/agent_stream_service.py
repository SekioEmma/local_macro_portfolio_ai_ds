"""SSE event bridge for Phase F MacroBrief agent runs."""
from __future__ import annotations

import json
import queue
import threading
import uuid
from collections.abc import Iterator
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app_backend.schemas.agent_api import AgentRunRequest
from app_backend.services.agent_api_service import AgentRunService
from app_backend.services.agent_run_registry import AgentRunRegistry
from app_backend.services.agent_runtime import AgentRuntimeEvent
from app_backend.services.agent_trace_service import sanitize_trace_payload


class AgentSseEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event_id: str
    session_id: str
    sequence: int = Field(ge=1)
    timestamp: str
    type: str
    payload: dict[str, Any] = Field(default_factory=dict)


class AgentStreamService:
    """Run the synchronous agent service behind a sanitized SSE stream."""

    def __init__(
        self,
        agent_run_service: AgentRunService,
        *,
        run_registry: AgentRunRegistry | None = None,
    ) -> None:
        self._agent_run_service = agent_run_service
        self._run_registry = run_registry

    def stream(self, request: AgentRunRequest) -> Iterator[str]:
        session_id = request.session_id or uuid.uuid4().hex
        stream_request = request.model_copy(update={"session_id": session_id})
        event_queue: queue.Queue[AgentRuntimeEvent | _ResultItem | _ErrorItem] = queue.Queue()
        if self._run_registry is not None:
            self._run_registry.clear(session_id)

        def _callback(event: AgentRuntimeEvent) -> None:
            event_queue.put(event)

        def _run() -> None:
            try:
                event_queue.put(
                    AgentRuntimeEvent(type="run_started", step=0, data={})
                )
                result = self._agent_run_service.run(
                    stream_request,
                    event_callback=_callback,
                    cancellation_requested=(
                        (lambda: self._run_registry.is_cancelled(session_id))
                        if self._run_registry is not None
                        else None
                    ),
                )
                event_queue.put(_ResultItem(response=result.model_dump(mode="json")))
            except Exception as exc:  # noqa: BLE001 - converted into sanitized SSE error
                event_queue.put(_ErrorItem(error_type=type(exc).__name__, detail=str(exc)))
            finally:
                if self._run_registry is not None:
                    self._run_registry.clear(session_id)

        worker = threading.Thread(target=_run, name=f"agent-stream-{session_id}", daemon=True)
        worker.start()

        sequence = 0
        while True:
            item = event_queue.get()
            if isinstance(item, _ResultItem):
                for event_type, payload in _brief_section_payloads(item.response):
                    sequence += 1
                    yield encode_sse_event(
                        _sse_event(
                            session_id=session_id,
                            sequence=sequence,
                            event_type=event_type,
                            payload=payload,
                        )
                    )
                sequence += 1
                yield encode_sse_event(
                    _sse_event(
                        session_id=session_id,
                        sequence=sequence,
                        event_type="complete",
                        payload={
                            "final_status": item.response.get("final_status"),
                            "steps": item.response.get("steps", 0),
                            "trace_session_id": item.response.get("trace_session_id"),
                        },
                    )
                )
                break
            if isinstance(item, _ErrorItem):
                sequence += 1
                yield encode_sse_event(
                    _sse_event(
                        session_id=session_id,
                        sequence=sequence,
                        event_type="error",
                        payload={"error_type": item.error_type, "detail": item.detail},
                    )
                )
                break
            sequence += 1
            event_type, payload = _runtime_event_payload(item)
            yield encode_sse_event(
                _sse_event(
                    session_id=session_id,
                    sequence=sequence,
                    event_type=event_type,
                    payload=payload,
                )
            )


def encode_sse_event(event: AgentSseEvent) -> str:
    data = json.dumps(event.model_dump(mode="json"), ensure_ascii=False, sort_keys=True)
    return f"id: {event.event_id}\nevent: {event.type}\ndata: {data}\n\n"


def _sse_event(
    *,
    session_id: str,
    sequence: int,
    event_type: str,
    payload: dict[str, Any],
) -> AgentSseEvent:
    return AgentSseEvent(
        event_id=f"{session_id}:{sequence}",
        session_id=session_id,
        sequence=sequence,
        timestamp=datetime.now(UTC).isoformat(),
        type=event_type,
        payload=sanitize_trace_payload(payload),
    )


def _runtime_event_payload(event: AgentRuntimeEvent) -> tuple[str, dict[str, Any]]:
    if event.type in {"information_plan", "information_gap"}:
        return "information_plan", {"step": event.step, **event.data}
    if event.type == "agent_phase":
        return "phase_changed", {"step": event.step, **event.data}
    if event.type == "llm_completion":
        return "provider_call_finished", {"step": event.step, **event.data}
    if event.type == "macro_brief_validation" and event.data.get("status") == "ok":
        return "brief_validated", {"step": event.step, **event.data}
    if event.type == "macro_brief_validation":
        return "warning", {"step": event.step, "kind": "macro_brief_validation", **event.data}
    if event.type == "run_cancelled":
        return "cancelled", {"step": event.step, **event.data}
    if event.type in {
        "run_started",
        "provider_call_started",
        "tool_result",
        "tool_disabled",
        "provider_error",
    }:
        return event.type, {"step": event.step, **event.data}
    return "warning", {"step": event.step, "kind": event.type, **event.data}


def _brief_section_payloads(response: dict[str, Any]) -> list[tuple[str, dict[str, Any]]]:
    brief = response.get("brief")
    if not isinstance(brief, dict):
        return []
    section_keys = [
        "core_conclusion",
        "market_state",
        "confirmed_facts",
        "judgments",
        "module_table",
        "risk_assessment",
        "forward_indicators",
        "scenarios",
        "source_list",
        "boundary_notice",
    ]
    return [
        ("brief_section", {"section": key, "content": brief[key]})
        for key in section_keys
        if key in brief
    ]


class _ResultItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    response: dict[str, Any]


class _ErrorItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    error_type: str
    detail: str = ""


__all__ = [
    "AgentSseEvent",
    "AgentStreamService",
    "encode_sse_event",
]
