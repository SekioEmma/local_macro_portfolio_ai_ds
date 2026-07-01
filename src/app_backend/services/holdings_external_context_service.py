"""Server-side detailed holdings context loader for consented agent runs."""
from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from typing import Any


HoldingsSnapshotProvider = Callable[[str], Mapping[str, Any] | None]

_FORBIDDEN_KEY_FRAGMENTS = (
    "account_number",
    "broker_login",
    "phone",
    "email",
    "identity",
    "id_card",
    "bank_card",
    "api_key",
    "access_token",
    "cookie",
    "password",
    "otp",
    "verification",
    "raw_provider",
    "order",
    "trade_history",
    "transaction",
    "deposit",
    "withdrawal",
    "device_id",
    "local_path",
    "database_path",
    "env",
)


class HoldingsContextError(ValueError):
    """Raised when holdings context is unavailable or violates policy."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


class HoldingsExternalContextService:
    """Loads only caller-injected snapshots; never reads holdings from disk."""

    def __init__(self, snapshot_provider: HoldingsSnapshotProvider | None = None) -> None:
        self._snapshot_provider = snapshot_provider

    @property
    def is_wired(self) -> bool:
        return self._snapshot_provider is not None

    def load_snapshot(self, *, session_id: str) -> dict[str, Any]:
        if self._snapshot_provider is None:
            raise HoldingsContextError("holdings_snapshot_backend_not_wired")
        snapshot = self._snapshot_provider(session_id)
        if not isinstance(snapshot, Mapping) or not snapshot:
            raise HoldingsContextError("holdings_snapshot_unavailable")
        sanitized = _sanitize(snapshot)
        if not isinstance(sanitized, dict) or not sanitized:
            raise HoldingsContextError("holdings_snapshot_unavailable")
        return sanitized


def _sanitize(value: Any) -> Any:
    if isinstance(value, Mapping):
        sanitized: dict[str, Any] = {}
        for key, item in value.items():
            key_text = str(key)
            lowered = key_text.lower()
            if any(fragment in lowered for fragment in _FORBIDDEN_KEY_FRAGMENTS):
                raise HoldingsContextError(f"forbidden_holdings_field:{key_text}")
            sanitized[key_text] = _sanitize(item)
        return sanitized
    if isinstance(value, Sequence) and not isinstance(value, str | bytes | bytearray):
        return [_sanitize(item) for item in value]
    return value


__all__ = [
    "HoldingsContextError",
    "HoldingsExternalContextService",
    "HoldingsSnapshotProvider",
]
