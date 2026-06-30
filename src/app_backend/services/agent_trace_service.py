"""Phase F6 JSONL trace service for the MacroBrief agent.

The trace service records structured observability events without raw prompts,
raw LLM responses, raw search queries, or raw holdings snapshots. It is
service-only: callers inject it into the runtime when persistence is desired.
"""
from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


DEFAULT_TRACE_DIR = Path("outputs/agent_traces")
DEFAULT_MAX_TRACE_BYTES = 100_000
_SESSION_ID_PATTERN = re.compile(r"^[A-Za-z0-9_.-]{1,128}$")


class AgentTraceError(RuntimeError):
    """Base error for trace persistence problems."""


class InvalidTraceSessionId(AgentTraceError):
    """Raised when a session id would escape the trace directory."""


class TraceSizeExceeded(AgentTraceError):
    """Raised when a trace file grows beyond the configured cap."""


class AgentTraceEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ts: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())
    type: str
    session_id: str
    step: int | None = None
    data: dict[str, Any] = Field(default_factory=dict)


class AgentTraceService:
    """Append-only JSONL trace writer.

    Tests should pass a temporary ``root_dir``. Production/API wiring may use
    the default ``outputs/agent_traces`` directory, which is git-ignored.
    """

    def __init__(
        self,
        *,
        root_dir: Path | str = DEFAULT_TRACE_DIR,
        max_session_bytes: int = DEFAULT_MAX_TRACE_BYTES,
    ) -> None:
        self.root_dir = Path(root_dir)
        self.max_session_bytes = max_session_bytes

    def trace_path(self, session_id: str) -> Path:
        if not _SESSION_ID_PATTERN.fullmatch(session_id):
            raise InvalidTraceSessionId(f"invalid trace session id: {session_id!r}")
        return self.root_dir / f"{session_id}.jsonl"

    def start_session(
        self,
        *,
        session_id: str,
        user_question: str,
        holdings_included: bool,
        holdings_snapshot_sha256: str | None = None,
        current_date: str | None = None,
    ) -> None:
        self.write_event(
            AgentTraceEvent(
                type="session_start",
                session_id=session_id,
                data={
                    "user_question_sha256": sha256_text(user_question),
                    "holdings_included": holdings_included,
                    "holdings_snapshot_sha256": holdings_snapshot_sha256,
                    "current_date": current_date,
                },
            )
        )

    def write_runtime_events(
        self,
        *,
        session_id: str,
        events: list[Any],
    ) -> None:
        for event in events:
            self.write_event(
                AgentTraceEvent(
                    type=str(event.type),
                    session_id=session_id,
                    step=event.step,
                    data=dict(event.data),
                )
            )

    def end_session(
        self,
        *,
        session_id: str,
        final_status: str,
        steps: int,
        warnings: list[Any],
    ) -> None:
        self.write_event(
            AgentTraceEvent(
                type="session_end",
                session_id=session_id,
                data={
                    "final_status": final_status,
                    "steps": steps,
                    "warnings": [_dump_warning(warning) for warning in warnings],
                },
            )
        )

    def write_event(self, event: AgentTraceEvent) -> None:
        path = self.trace_path(event.session_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        line = json.dumps(event.model_dump(mode="json"), ensure_ascii=False, sort_keys=True)
        with path.open("a", encoding="utf-8", newline="\n") as handle:
            handle.write(line)
            handle.write("\n")
        if path.stat().st_size > self.max_session_bytes:
            raise TraceSizeExceeded(
                f"trace exceeds {self.max_session_bytes} bytes: {path.name}"
            )

    def read_events(self, session_id: str) -> list[AgentTraceEvent]:
        path = self.trace_path(session_id)
        if not path.exists():
            return []
        events: list[AgentTraceEvent] = []
        with path.open("r", encoding="utf-8") as handle:
            for line in handle:
                text = line.strip()
                if text:
                    events.append(AgentTraceEvent.model_validate_json(text))
        return events


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def sha256_json(value: Mapping[str, Any] | None) -> str | None:
    if value is None:
        return None
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)
    return sha256_text(payload)


def _dump_warning(warning: Any) -> dict[str, Any]:
    if hasattr(warning, "model_dump"):
        dumped = warning.model_dump(mode="json")
        return dict(dumped)
    if isinstance(warning, Mapping):
        return dict(warning)
    return {"code": str(warning), "message": ""}


__all__ = [
    "AgentTraceError",
    "AgentTraceEvent",
    "AgentTraceService",
    "InvalidTraceSessionId",
    "TraceSizeExceeded",
    "sha256_json",
    "sha256_text",
]
