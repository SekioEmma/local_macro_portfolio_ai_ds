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
_REDACTED = "[REDACTED_TRACE_FIELD]"
_HASHED_FIELD = "[HASHED_TRACE_FIELD]"
_FORBIDDEN_TRACE_KEYS = frozenset(
    {
        "api_key",
        "api_key_env",
        "authorization",
        "deepseek_api_key",
        "tavily_api_key",
        "raw_prompt",
        "raw_response",
        "raw_body",
        "raw_payload",
        "raw_provider",
        "raw_search_query",
        "raw_holdings",
        "holdings_snapshot",
        "user_question",
        "prompt",
        "response",
    }
)
_HASH_ONLY_KEYS = frozenset({"query", "search_query", "question", "args"})
_SENSITIVE_VALUE_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"(?i)\btvly-[A-Za-z0-9_-]{8,128}"),
    re.compile(r"(?i)\bsk-[A-Za-z0-9_-]{16,128}"),
    re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._\-/+=]{8,512}"),
    re.compile(r"(?i)\bAuthorization\s*:\s*[A-Za-z0-9._\-/+=\s]{8,512}"),
    re.compile(r"(?i)\bapi[_-]?key\s*[:=]\s*[A-Za-z0-9._\-/+=]{8,256}"),
    re.compile(r"\b[A-Z]:[\\/][^\s\"'<>]+"),
    re.compile(r"/Users/[^\s\"'<>]+"),
    re.compile(r"/home/[^\s\"'<>]+"),
    re.compile(r"/mnt/data[^\s\"'<>]*"),
)
_SENSITIVE_SCAN_MARKERS = (
    "raw_prompt",
    "raw_response",
    "raw_search_query",
    "raw_holdings",
    "api_key",
    "deepseek_api_key",
    "tavily_api_key",
    "Bearer ",
    "Authorization:",
)


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


class AgentTraceReplay(BaseModel):
    model_config = ConfigDict(extra="forbid")

    session_id: str
    events: list[AgentTraceEvent]
    message_history: list[dict[str, str]]


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
        safe_event = event.model_copy(
            update={"data": sanitize_trace_payload(event.data)}
        )
        line = json.dumps(safe_event.model_dump(mode="json"), ensure_ascii=False, sort_keys=True)
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

    def replay(self, session_id: str) -> AgentTraceReplay:
        events = self.read_events(session_id)
        return AgentTraceReplay(
            session_id=session_id,
            events=events,
            message_history=[_event_to_replay_message(event) for event in events],
        )

    def scan_for_sensitive_markers(self, session_id: str) -> list[str]:
        path = self.trace_path(session_id)
        if not path.exists():
            return []
        return scan_trace_text_for_sensitive_markers(path.read_text(encoding="utf-8"))


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def sha256_json(value: Mapping[str, Any] | None) -> str | None:
    if value is None:
        return None
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)
    return sha256_text(payload)


def sanitize_trace_payload(value: Any, *, parent_key: str | None = None) -> Any:
    if isinstance(value, Mapping):
        safe: dict[str, Any] = {}
        for key, item in value.items():
            key_text = str(key)
            normalized = key_text.lower()
            if normalized in _FORBIDDEN_TRACE_KEYS:
                safe[f"redacted_field_{len(safe)}"] = {
                    "field_name_sha256": sha256_text(key_text),
                    "value": _REDACTED,
                }
            elif normalized in _HASH_ONLY_KEYS:
                safe[f"{key_text}_sha256"] = _hash_any(item)
            else:
                safe[key_text] = sanitize_trace_payload(item, parent_key=key_text)
        return safe
    if isinstance(value, list):
        return [sanitize_trace_payload(item, parent_key=parent_key) for item in value]
    if isinstance(value, tuple):
        return [sanitize_trace_payload(item, parent_key=parent_key) for item in value]
    if isinstance(value, str):
        return _sanitize_trace_string(value)
    return value


def scan_trace_text_for_sensitive_markers(text: str) -> list[str]:
    findings = [marker for marker in _SENSITIVE_SCAN_MARKERS if marker in text]
    for pattern in _SENSITIVE_VALUE_PATTERNS:
        if pattern.search(text):
            findings.append(f"pattern:{pattern.pattern}")
    return sorted(set(findings))


def _dump_warning(warning: Any) -> dict[str, Any]:
    if hasattr(warning, "model_dump"):
        dumped = warning.model_dump(mode="json")
        return dict(dumped)
    if isinstance(warning, Mapping):
        return dict(warning)
    return {"code": str(warning), "message": ""}


def _hash_any(value: Any) -> str:
    if isinstance(value, str):
        return sha256_text(value)
    return sha256_text(json.dumps(value, ensure_ascii=False, sort_keys=True, default=str))


def _sanitize_trace_string(value: str) -> str:
    out = value
    for pattern in _SENSITIVE_VALUE_PATTERNS:
        out = pattern.sub(_REDACTED, out)
    return out


def _event_to_replay_message(event: AgentTraceEvent) -> dict[str, str]:
    if event.type == "session_start":
        return {
            "role": "system",
            "content": (
                "session_start "
                f"question_sha256={event.data.get('user_question_sha256', '')} "
                f"holdings_included={event.data.get('holdings_included', False)}"
            ),
        }
    if event.type == "llm_completion":
        return {
            "role": "assistant",
            "content": (
                "llm_completion "
                f"step={event.step} "
                f"finish_reason={event.data.get('finish_reason', '')} "
                f"tokens={event.data.get('tokens', 0)}"
            ),
        }
    if event.type == "tool_result":
        return {
            "role": "tool",
            "content": (
                "tool_result "
                f"step={event.step} "
                f"tool={event.data.get('tool_name', '')} "
                f"status={event.data.get('status', '')} "
                f"error_code={event.data.get('error_code', '')}"
            ),
        }
    if event.type == "macro_brief_validation":
        return {
            "role": "user",
            "content": (
                "macro_brief_validation "
                f"step={event.step} "
                f"status={event.data.get('status', '')}"
            ),
        }
    return {
        "role": "system",
        "content": f"{event.type} step={event.step}",
    }


__all__ = [
    "AgentTraceError",
    "AgentTraceEvent",
    "AgentTraceReplay",
    "AgentTraceService",
    "InvalidTraceSessionId",
    "TraceSizeExceeded",
    "sanitize_trace_payload",
    "scan_trace_text_for_sensitive_markers",
    "sha256_json",
    "sha256_text",
]
