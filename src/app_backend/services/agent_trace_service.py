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
TRACE_SCHEMA_VERSION = 1
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

    schema_version: int = TRACE_SCHEMA_VERSION
    ts: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())
    type: str
    session_id: str
    step: int | None = None
    data: dict[str, Any] = Field(default_factory=dict)
    event_sequence: int | None = None
    previous_event_hash: str | None = None
    event_hash: str | None = None


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
        indexed = self._indexed_trace_path(session_id)
        if indexed is not None:
            return indexed
        legacy = self.root_dir / f"{session_id}.jsonl"
        if legacy.exists():
            return legacy
        now = datetime.now(UTC)
        return self.root_dir / f"{now:%Y}" / f"{now:%m}" / f"{now:%d}" / f"{session_id}.jsonl"

    def summary_path(self, session_id: str) -> Path:
        path = self.trace_path(session_id)
        return path.with_name(f"{path.stem}.summary.json")

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
        self._ensure_index_entry(event.session_id, path)
        if _trace_has_overflow(path):
            if event.type == "session_end":
                self._write_summary(
                    session_id=event.session_id,
                    final_status=str(event.data.get("final_status", "")),
                    steps=_int_or_none(event.data.get("steps")),
                    overflowed=True,
                )
            return

        safe_event = self._prepare_hashed_event(
            event.model_copy(update={"data": sanitize_trace_payload(event.data)}),
            path=path,
        )
        line = _event_line(safe_event)
        encoded_size = len((line + "\n").encode("utf-8"))
        current_size = path.stat().st_size if path.exists() else 0
        if current_size + encoded_size > self.max_session_bytes and event.type != "trace_overflow":
            self._write_overflow_event(path, event.session_id)
            self._write_summary(session_id=event.session_id, overflowed=True)
            return

        with path.open("a", encoding="utf-8", newline="\n") as handle:
            handle.write(line)
            handle.write("\n")
        if event.type == "session_end":
            self._write_summary(
                session_id=event.session_id,
                final_status=str(event.data.get("final_status", "")),
                steps=_int_or_none(event.data.get("steps")),
                overflowed=False,
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

    def _indexed_trace_path(self, session_id: str) -> Path | None:
        index_path = self.root_dir / "index.jsonl"
        if not index_path.exists():
            return None
        matched: Path | None = None
        with index_path.open("r", encoding="utf-8") as handle:
            for line in handle:
                if not line.strip():
                    continue
                try:
                    item = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if item.get("session_id") != session_id:
                    continue
                relpath = item.get("trace_relpath")
                if isinstance(relpath, str) and relpath:
                    matched = (self.root_dir / relpath).resolve()
        if matched is None:
            return None
        root = self.root_dir.resolve()
        try:
            matched.relative_to(root)
        except ValueError:
            return None
        return matched

    def _ensure_index_entry(self, session_id: str, path: Path) -> None:
        if path.exists():
            return
        index_path = self.root_dir / "index.jsonl"
        index_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "schema_version": TRACE_SCHEMA_VERSION,
            "session_id": session_id,
            "trace_relpath": path.relative_to(self.root_dir).as_posix(),
            "summary_relpath": self.summary_path(session_id).relative_to(self.root_dir).as_posix(),
            "created_at": datetime.now(UTC).isoformat(),
        }
        with index_path.open("a", encoding="utf-8", newline="\n") as handle:
            handle.write(json.dumps(payload, ensure_ascii=False, sort_keys=True))
            handle.write("\n")

    def _prepare_hashed_event(
        self,
        event: AgentTraceEvent,
        *,
        path: Path,
    ) -> AgentTraceEvent:
        sequence, previous_hash = _next_sequence_and_previous_hash(path)
        event = event.model_copy(
            update={
                "schema_version": TRACE_SCHEMA_VERSION,
                "event_sequence": sequence,
                "previous_event_hash": previous_hash,
                "event_hash": None,
            }
        )
        event_hash = sha256_text(_event_line(event))
        return event.model_copy(update={"event_hash": event_hash})

    def _write_overflow_event(self, path: Path, session_id: str) -> None:
        overflow = self._prepare_hashed_event(
            AgentTraceEvent(
                type="trace_overflow",
                session_id=session_id,
                data={
                    "max_session_bytes": self.max_session_bytes,
                    "overflowed_at_bytes": path.stat().st_size if path.exists() else 0,
                },
            ),
            path=path,
        )
        with path.open("a", encoding="utf-8", newline="\n") as handle:
            handle.write(_event_line(overflow))
            handle.write("\n")

    def _write_summary(
        self,
        *,
        session_id: str,
        final_status: str | None = None,
        steps: int | None = None,
        overflowed: bool,
    ) -> None:
        events = self.read_events(session_id)
        payload = {
            "schema_version": TRACE_SCHEMA_VERSION,
            "session_id": session_id,
            "event_count": len(events),
            "first_event_ts": events[0].ts if events else None,
            "last_event_ts": events[-1].ts if events else None,
            "last_event_hash": events[-1].event_hash if events else None,
            "overflowed": overflowed or any(event.type == "trace_overflow" for event in events),
            "final_status": final_status,
            "steps": steps,
        }
        path = self.summary_path(session_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _event_line(event: AgentTraceEvent) -> str:
    return json.dumps(event.model_dump(mode="json"), ensure_ascii=False, sort_keys=True)


def _next_sequence_and_previous_hash(path: Path) -> tuple[int, str | None]:
    if not path.exists():
        return 1, None
    sequence = 0
    previous_hash: str | None = None
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            try:
                item = json.loads(line)
            except json.JSONDecodeError:
                continue
            event_sequence = item.get("event_sequence")
            if isinstance(event_sequence, int):
                sequence = max(sequence, event_sequence)
            event_hash = item.get("event_hash")
            if isinstance(event_hash, str) and event_hash:
                previous_hash = event_hash
    return sequence + 1, previous_hash


def _trace_has_overflow(path: Path) -> bool:
    if not path.exists():
        return False
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if '"type": "trace_overflow"' in line:
                return True
    return False


def _int_or_none(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    return None


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
