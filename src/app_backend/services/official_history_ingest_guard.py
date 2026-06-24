from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date
from types import MappingProxyType
from typing import Any


class OfficialHistoryAdmissionError(ValueError):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


@dataclass(frozen=True)
class ApprovedHistorySeries:
    metric_key: str
    source_series: str
    provider: str
    source: str
    source_badge: str
    metric_kind: str
    freshness_status: str
    ai_context_allowed: bool


@dataclass(frozen=True)
class ApprovedHistoryRoute:
    route_key: str
    series: tuple[ApprovedHistorySeries, ...]

    @property
    def metric_keys(self) -> tuple[str, ...]:
        return tuple(item.metric_key for item in self.series)


_FRED_RATE_SERIES = (
    ("DGS2", "dgs2"),
    ("DGS10", "dgs10"),
    ("DGS30", "dgs30"),
    ("T10Y2Y", "t10y2y"),
    ("T10YIE", "t10yie"),
    ("DFII10", "dfii10"),
)

_BLS_CPI_SERIES = (
    ("CUSR0000SA0", "headline_cpi_index", "raw"),
    ("CUSR0000SA0", "headline_cpi_yoy", "derived"),
    ("CUSR0000SA0L1E", "core_cpi_index", "raw"),
    ("CUSR0000SA0L1E", "core_cpi_yoy", "derived"),
)

_APPROVED_ROUTES = MappingProxyType(
    {
        "fred_rates": ApprovedHistoryRoute(
            route_key="fred_rates",
            series=tuple(
                ApprovedHistorySeries(
                    metric_key=metric_key,
                    source_series=source_series,
                    provider="fred",
                    source="FRED",
                    source_badge="official_fallback",
                    metric_kind="raw",
                    freshness_status="historical",
                    ai_context_allowed=True,
                )
                for source_series, metric_key in _FRED_RATE_SERIES
            ),
        ),
        "bls_cpi": ApprovedHistoryRoute(
            route_key="bls_cpi",
            series=tuple(
                ApprovedHistorySeries(
                    metric_key=metric_key,
                    source_series=source_series,
                    provider="bls",
                    source="BLS",
                    source_badge="official",
                    metric_kind=metric_kind,
                    freshness_status="historical",
                    ai_context_allowed=True,
                )
                for source_series, metric_key, metric_kind in _BLS_CPI_SERIES
            ),
        ),
    }
)

_URL_KEYS = frozenset(
    {
        "url",
        "source_url",
        "source_link",
        "web_url",
        "search_url",
        "provider_url",
    }
)

_SENSITIVE_TERMS = (
    "holdings",
    "account",
    "position",
    "transaction",
    "api_key",
    "apikey",
    "raw_provider_payload",
    "raw_payload",
    "raw_prompt",
    "raw_output",
    "secret",
)

_BLOCKED_SOURCE_BADGES = frozenset(
    {
        "search-derived",
        "proxy",
        "unofficial_fallback",
        "commercial_api_fallback",
        "derived",
    }
)


def list_approved_history_routes() -> tuple[ApprovedHistoryRoute, ...]:
    return tuple(_APPROVED_ROUTES.values())


def resolve_approved_history_route(route_key: str) -> ApprovedHistoryRoute:
    route = _APPROVED_ROUTES.get(route_key)
    if route is None:
        raise OfficialHistoryAdmissionError("unsupported_route")
    return route


def validate_history_observation(
    route_key: str,
    observation: dict[str, Any],
) -> dict[str, Any]:
    route = resolve_approved_history_route(route_key)
    _reject_unsafe_payload(observation)

    metric_key = str(observation.get("metric_key") or "")
    catalog_item = _series_by_metric(route).get(metric_key)
    if catalog_item is None:
        raise OfficialHistoryAdmissionError("unsupported_metric_key")

    _require_equal(observation.get("provider"), catalog_item.provider, "provider_mismatch")
    _require_equal(observation.get("source"), catalog_item.source, "source_mismatch")
    _require_equal(
        observation.get("source_series"),
        catalog_item.source_series,
        "source_series_mismatch",
    )

    source_badge = str(observation.get("source_badge") or "")
    if source_badge in _BLOCKED_SOURCE_BADGES:
        raise OfficialHistoryAdmissionError("source_badge_mismatch")
    _require_equal(source_badge, catalog_item.source_badge, "source_badge_mismatch")

    _require_equal(observation.get("status"), "ok", "status_not_ok")
    _require_equal(
        observation.get("freshness_status"),
        catalog_item.freshness_status,
        "freshness_status_mismatch",
    )
    if observation.get("ai_context_allowed") is not catalog_item.ai_context_allowed:
        raise OfficialHistoryAdmissionError("ai_context_not_allowed")

    _validate_iso_date(observation.get("observation_date"), "invalid_observation_date")
    _validate_numeric_value(observation.get("value"))

    if not str(observation.get("source_series") or "").strip():
        raise OfficialHistoryAdmissionError("source_series_mismatch")

    metric_kind = str(observation.get("metric_kind") or "raw")
    if metric_kind != catalog_item.metric_kind:
        raise OfficialHistoryAdmissionError("invalid_metric_kind")

    lineage = observation.get("lineage")
    if metric_kind == "derived":
        if not isinstance(lineage, dict) or not lineage:
            raise OfficialHistoryAdmissionError("missing_derived_lineage")
        if route_key == "bls_cpi":
            _validate_iso_date(
                lineage.get("prior_observation_date"),
                "missing_derived_lineage",
            )

    return dict(observation)


def validate_history_batch(
    route_key: str,
    observations: list[dict[str, Any]] | tuple[dict[str, Any], ...],
) -> tuple[dict[str, Any], ...]:
    return tuple(validate_history_observation(route_key, item) for item in observations)


def _series_by_metric(route: ApprovedHistoryRoute) -> dict[str, ApprovedHistorySeries]:
    return {item.metric_key: item for item in route.series}


def _require_equal(actual: Any, expected: str, code: str) -> None:
    if actual != expected:
        raise OfficialHistoryAdmissionError(code)


def _validate_iso_date(value: Any, code: str) -> None:
    if not isinstance(value, str):
        raise OfficialHistoryAdmissionError(code)
    try:
        date.fromisoformat(value)
    except ValueError as exc:
        raise OfficialHistoryAdmissionError(code) from exc


def _validate_numeric_value(value: Any) -> None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise OfficialHistoryAdmissionError("invalid_numeric_value")
    if not math.isfinite(float(value)):
        raise OfficialHistoryAdmissionError("invalid_numeric_value")


def _reject_unsafe_payload(value: Any) -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            lowered_key = str(key).lower()
            if lowered_key in _URL_KEYS:
                raise OfficialHistoryAdmissionError("url_input_not_allowed")
            if any(term in lowered_key for term in _SENSITIVE_TERMS):
                raise OfficialHistoryAdmissionError("sensitive_content_rejected")
            _reject_unsafe_payload(item)
        return
    if isinstance(value, (list, tuple, set)):
        for item in value:
            _reject_unsafe_payload(item)
        return
    if isinstance(value, str):
        lowered_value = value.lower()
        if "http://" in lowered_value or "https://" in lowered_value:
            raise OfficialHistoryAdmissionError("url_input_not_allowed")
        if any(term in lowered_value for term in _SENSITIVE_TERMS):
            raise OfficialHistoryAdmissionError("sensitive_content_rejected")


__all__ = [
    "ApprovedHistoryRoute",
    "ApprovedHistorySeries",
    "OfficialHistoryAdmissionError",
    "list_approved_history_routes",
    "resolve_approved_history_route",
    "validate_history_batch",
    "validate_history_observation",
]
