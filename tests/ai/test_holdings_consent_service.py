from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from app_backend.services.holdings_consent_service import (
    HoldingsConsentError,
    HoldingsConsentService,
)


def test_consent_token_validates_then_consumes_once():
    now = datetime(2026, 6, 30, 12, tzinfo=UTC)
    service = HoldingsConsentService(
        now_provider=lambda: now,
        token_factory=lambda: "token_1234567890123456",
    )
    grant = service.issue(session_id="session-1")

    assert grant.session_id == "session-1"
    assert service.validate(grant.token, session_id="session-1").token == grant.token
    assert service.consume(grant.token, session_id="session-1").used_at is not None

    with pytest.raises(HoldingsConsentError) as exc:
        service.consume(grant.token, session_id="session-1")
    assert exc.value.code == "holdings_consent_token_already_used"


def test_consent_token_expires_after_ttl():
    current = {"now": datetime(2026, 6, 30, 12, tzinfo=UTC)}
    service = HoldingsConsentService(
        ttl=timedelta(minutes=10),
        now_provider=lambda: current["now"],
        token_factory=lambda: "token_1234567890123456",
    )
    grant = service.issue()
    current["now"] = datetime(2026, 6, 30, 12, 11, tzinfo=UTC)

    with pytest.raises(HoldingsConsentError) as exc:
        service.validate(grant.token, session_id="session-1")
    assert exc.value.code == "holdings_consent_token_expired"


def test_consent_token_binds_to_declared_session():
    service = HoldingsConsentService(token_factory=lambda: "token_1234567890123456")
    grant = service.issue(session_id="session-1")

    with pytest.raises(HoldingsConsentError) as exc:
        service.validate(grant.token, session_id="session-2")
    assert exc.value.code == "holdings_consent_token_session_mismatch"
