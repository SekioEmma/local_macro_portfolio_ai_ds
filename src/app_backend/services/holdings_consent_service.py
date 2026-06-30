"""Run-scoped one-time consent tokens for detailed holdings context."""
from __future__ import annotations

import secrets
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from threading import Lock

from pydantic import BaseModel, ConfigDict, Field


NowProvider = Callable[[], datetime]
TokenFactory = Callable[[], str]


class HoldingsConsentError(ValueError):
    """Raised when a holdings consent token is missing, stale, or invalid."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


class HoldingsConsentGrant(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    token: str = Field(min_length=16, max_length=256)
    session_id: str | None = Field(default=None, min_length=1, max_length=128)
    issued_at: str
    expires_at: str
    used_at: str | None = None


@dataclass
class HoldingsConsentService:
    """In-memory fail-closed consent token store.

    Tokens are process-local by design. They authorize one explicitly
    requested agent run and never contain holdings content.
    """

    ttl: timedelta = timedelta(minutes=10)
    now_provider: NowProvider = lambda: datetime.now(UTC)
    token_factory: TokenFactory = lambda: secrets.token_urlsafe(32)
    _tokens: dict[str, HoldingsConsentGrant] = field(default_factory=dict, init=False)
    _lock: Lock = field(default_factory=Lock, init=False)

    def issue(self, *, session_id: str | None = None) -> HoldingsConsentGrant:
        now = self._now()
        expires_at = now + self.ttl
        grant = HoldingsConsentGrant(
            token=self.token_factory(),
            session_id=session_id,
            issued_at=now.isoformat(),
            expires_at=expires_at.isoformat(),
        )
        with self._lock:
            self._tokens[grant.token] = grant
            self._drop_expired_locked(now)
        return grant

    def validate(self, token: str | None, *, session_id: str) -> HoldingsConsentGrant:
        if not token:
            raise HoldingsConsentError("holdings_consent_token_required")
        now = self._now()
        with self._lock:
            grant = self._tokens.get(token)
            self._validate_grant(grant, session_id=session_id, now=now)
            return grant

    def consume(self, token: str | None, *, session_id: str) -> HoldingsConsentGrant:
        if not token:
            raise HoldingsConsentError("holdings_consent_token_required")
        now = self._now()
        with self._lock:
            grant = self._tokens.get(token)
            self._validate_grant(grant, session_id=session_id, now=now)
            consumed = grant.model_copy(update={"used_at": now.isoformat()})
            self._tokens[token] = consumed
            return consumed

    def _validate_grant(
        self,
        grant: HoldingsConsentGrant | None,
        *,
        session_id: str,
        now: datetime,
    ) -> None:
        if grant is None:
            raise HoldingsConsentError("holdings_consent_token_invalid")
        if grant.used_at is not None:
            raise HoldingsConsentError("holdings_consent_token_already_used")
        if datetime.fromisoformat(grant.expires_at) <= now:
            raise HoldingsConsentError("holdings_consent_token_expired")
        if grant.session_id is not None and grant.session_id != session_id:
            raise HoldingsConsentError("holdings_consent_token_session_mismatch")

    def _drop_expired_locked(self, now: datetime) -> None:
        expired = [
            token
            for token, grant in self._tokens.items()
            if datetime.fromisoformat(grant.expires_at) <= now
        ]
        for token in expired:
            self._tokens.pop(token, None)

    def _now(self) -> datetime:
        value = self.now_provider()
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)


__all__ = [
    "HoldingsConsentError",
    "HoldingsConsentGrant",
    "HoldingsConsentService",
]
