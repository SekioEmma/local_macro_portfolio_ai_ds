from __future__ import annotations

import pytest

from app_backend.services.holdings_external_context_service import (
    HoldingsContextError,
    HoldingsExternalContextService,
)


def test_holdings_context_service_is_unwired_by_default():
    service = HoldingsExternalContextService()

    with pytest.raises(HoldingsContextError) as exc:
        service.load_snapshot(session_id="session-1")
    assert exc.value.code == "holdings_snapshot_backend_not_wired"


def test_holdings_context_service_returns_injected_snapshot_only():
    service = HoldingsExternalContextService(
        lambda session_id: {
            "session_id": session_id,
            "positions": [{"ticker": "SPY", "shares": 10}],
        }
    )

    assert service.load_snapshot(session_id="session-1") == {
        "session_id": "session-1",
        "positions": [{"ticker": "SPY", "shares": 10}],
    }


def test_holdings_context_service_rejects_forbidden_fields():
    service = HoldingsExternalContextService(
        lambda _session_id: {
            "positions": [{"ticker": "SPY"}],
            "raw_provider_payload": {"secret": "must not leave local boundary"},
        }
    )

    with pytest.raises(HoldingsContextError) as exc:
        service.load_snapshot(session_id="session-1")
    assert exc.value.code == "forbidden_holdings_field:raw_provider_payload"
