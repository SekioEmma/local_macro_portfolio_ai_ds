from __future__ import annotations

from dataclasses import dataclass
from threading import RLock
from typing import TypeVar

from app_backend.schemas.responses import (
    DashboardEvidenceTableResponse,
    DashboardSummaryResponse,
)


T = TypeVar("T")


@dataclass(frozen=True)
class CachedDashboardContext:
    key_digest: str
    summary: DashboardSummaryResponse
    unfiltered_evidence_table: DashboardEvidenceTableResponse


class SharedDashboardContextCache:
    def __init__(self) -> None:
        self._lock = RLock()
        self._cached: CachedDashboardContext | None = None

    def get(self, key_digest: str) -> CachedDashboardContext | None:
        with self._lock:
            if self._cached is None or self._cached.key_digest != key_digest:
                return None
            return _copy_cached_context(self._cached)

    def set(self, item: CachedDashboardContext) -> None:
        with self._lock:
            self._cached = _copy_cached_context(item)

    def clear(self) -> None:
        with self._lock:
            self._cached = None


def _copy_model(value: T) -> T:
    if hasattr(value, "model_copy"):
        return value.model_copy(deep=True)
    return value.copy(deep=True)


def _copy_cached_context(item: CachedDashboardContext) -> CachedDashboardContext:
    return CachedDashboardContext(
        key_digest=item.key_digest,
        summary=_copy_model(item.summary),
        unfiltered_evidence_table=_copy_model(item.unfiltered_evidence_table),
    )
