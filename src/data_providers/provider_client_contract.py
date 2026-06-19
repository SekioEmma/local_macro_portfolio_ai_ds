from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class HistoricalProviderClient(Protocol):
    provider_key: str

    def fetch_history(self, identifier: str, **kwargs: Any) -> dict[str, Any]:
        """Return a normalized envelope without persisting a raw provider payload."""


def validate_provider_response(payload: dict[str, Any]) -> None:
    required = {"status", "provider", "source_series", "data", "retrieved_at"}
    missing = sorted(required - set(payload))
    if missing:
        raise ValueError(f"provider_response_missing:{','.join(missing)}")
    if payload["status"] not in {"ok", "error", "not_available"}:
        raise ValueError("provider_response_invalid_status")
    if not isinstance(payload["data"], list):
        raise ValueError("provider_response_data_must_be_list")
    forbidden = {
        "raw_provider_payload",
        "raw_response",
        "credentials",
        "api_key",
        "authorization",
    }
    if forbidden & set(payload):
        raise ValueError("provider_response_contains_forbidden_raw_or_secret_field")
