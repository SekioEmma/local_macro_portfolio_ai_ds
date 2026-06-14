from __future__ import annotations

from typing import Any, Iterable


BLOCKING_STATUSES = {
    "missing",
    "stale",
    "research_needed",
    "insufficient_history",
    "not_available",
    "insufficient_evidence",
}
BLOCKING_FRESHNESS = {"missing", "stale", "unknown", "insufficient_history"}
BLOCKING_SOURCE_BADGES = {"missing", "research_needed", "search-derived"}
PROXY_ONLY_BADGES = {"proxy"}
PROXY_ONLY_TRIGGER_POLICIES = {
    "auxiliary_only",
    "proxy_auxiliary_only",
    "context_only",
}
PUBLIC_PAYLOAD_FIELDS = (
    "row_id",
    "module",
    "metric_key",
    "display_name",
    "value",
    "value_text",
    "unit",
    "status",
    "source",
    "source_badge",
    "source_series",
    "observation_date",
    "generated_at",
    "freshness_status",
    "missing_reason",
    "interpretation_hint",
    "interpretation_boundary",
    "ai_context_allowed",
    "ai_context_tier",
    "trigger_eligibility",
)


class MissingEvidenceError(KeyError):
    def __init__(self, metric_key: str) -> None:
        super().__init__(f"missing evidence metric: {metric_key}")
        self.metric_key = metric_key


class EvidenceIndex:
    def __init__(self, rows: Iterable[Any]) -> None:
        self._rows = tuple(rows)
        self._by_metric_key: dict[str, Any] = {}
        for row in self._rows:
            metric_key = _row_value(row, "metric_key")
            if metric_key is not None and str(metric_key) not in self._by_metric_key:
                self._by_metric_key[str(metric_key)] = row

    def rows(self) -> list[Any]:
        return list(self._rows)

    def by_metric_key(self, metric_key: str) -> Any | None:
        return self._by_metric_key.get(metric_key)

    def require_metric(self, metric_key: str) -> Any:
        row = self.by_metric_key(metric_key)
        if row is None:
            raise MissingEvidenceError(metric_key)
        return row

    def rows_by_module(self, module_key: str) -> list[Any]:
        return [row for row in self._rows if _row_value(row, "module") == module_key]

    def rows_by_source_badge(self, source_badge: str) -> list[Any]:
        return [
            row for row in self._rows if _row_value(row, "source_badge") == source_badge
        ]

    def rows_by_status(self, status: str) -> list[Any]:
        return [row for row in self._rows if _row_value(row, "status") == status]

    def rows_allowed_for_ai_context(self) -> list[Any]:
        return [row for row in self._rows if self._row_allowed_for_ai_context(row)]

    def rows_blocked_from_ai_context(self) -> list[Any]:
        return [row for row in self._rows if not self._row_allowed_for_ai_context(row)]

    def has_valid_value(self, metric_key: str) -> bool:
        row = self.by_metric_key(metric_key)
        return bool(row is not None and _row_value(row, "value") not in (None, ""))

    def is_usable_for_support(
        self,
        metric_key: str,
        *,
        require_ai_context_allowed: bool = True,
        require_core_trigger: bool = False,
    ) -> bool:
        row = self.by_metric_key(metric_key)
        if row is None:
            return False
        if self.blocked_reason(
            metric_key,
            require_ai_context_allowed=require_ai_context_allowed,
            require_core_trigger=require_core_trigger,
        ):
            return False
        return self.has_valid_value(metric_key)

    def blocked_reason(
        self,
        metric_key: str,
        *,
        require_ai_context_allowed: bool = True,
        require_core_trigger: bool = False,
    ) -> str | None:
        row = self.by_metric_key(metric_key)
        if row is None:
            return "missing_metric"
        value = _row_value(row, "value")
        if value in (None, ""):
            return "value_missing"
        status = _row_text(row, "status")
        if status in BLOCKING_STATUSES:
            return f"status_{status}"
        freshness = _row_text(row, "freshness_status")
        if freshness in BLOCKING_FRESHNESS:
            return f"freshness_{freshness}"
        source_badge = _row_text(row, "source_badge")
        if source_badge in BLOCKING_SOURCE_BADGES:
            return f"source_badge_{source_badge}"
        if require_ai_context_allowed and _row_value(row, "ai_context_allowed") is False:
            return _row_text(row, "blocked_reason") or "ai_context_not_allowed"
        if require_core_trigger and self._row_is_proxy_only(row):
            return "proxy_only_cannot_trigger"
        return None

    def missing_or_blocked_inputs(
        self,
        metric_keys: Iterable[str],
        *,
        require_ai_context_allowed: bool = True,
        require_core_trigger: bool = False,
    ) -> list[str]:
        blocked = []
        for metric_key in metric_keys:
            if self.blocked_reason(
                metric_key,
                require_ai_context_allowed=require_ai_context_allowed,
                require_core_trigger=require_core_trigger,
            ):
                blocked.append(metric_key)
        return blocked

    def public_payload(self, metric_key: str) -> dict[str, Any]:
        row = self.require_metric(metric_key)
        return {
            field: _row_value(row, field)
            for field in PUBLIC_PAYLOAD_FIELDS
            if _row_value(row, field) is not None
        }

    def _row_allowed_for_ai_context(self, row: Any) -> bool:
        metric_key = _row_text(row, "metric_key")
        if metric_key is None:
            return False
        return self.blocked_reason(metric_key, require_ai_context_allowed=True) is None

    def _row_is_proxy_only(self, row: Any) -> bool:
        source_badge = _row_text(row, "source_badge")
        trigger = _row_text(row, "trigger_eligibility")
        return source_badge in PROXY_ONLY_BADGES or trigger in PROXY_ONLY_TRIGGER_POLICIES


def _row_value(row: Any, field: str) -> Any:
    if isinstance(row, dict):
        return row.get(field)
    return getattr(row, field, None)


def _row_text(row: Any, field: str) -> str | None:
    value = _row_value(row, field)
    if value is None:
        return None
    return str(value)
