"""Process-local registry for Phase F agent run cancellation seams."""
from __future__ import annotations

from dataclasses import dataclass, field
from threading import Lock


@dataclass
class AgentRunRegistry:
    _cancelled: set[str] = field(default_factory=set, init=False)
    _lock: Lock = field(default_factory=Lock, init=False)

    def request_cancel(self, session_id: str) -> bool:
        with self._lock:
            already_cancelled = session_id in self._cancelled
            self._cancelled.add(session_id)
            return not already_cancelled

    def is_cancelled(self, session_id: str) -> bool:
        with self._lock:
            return session_id in self._cancelled

    def clear(self, session_id: str) -> None:
        with self._lock:
            self._cancelled.discard(session_id)


__all__ = ["AgentRunRegistry"]
