from __future__ import annotations

from app_backend.services.agent_run_registry import AgentRunRegistry


def test_registry_acquire_rejects_duplicate_active_session():
    registry = AgentRunRegistry()

    assert registry.acquire("session-1") is True
    assert registry.is_active("session-1") is True
    assert registry.acquire("session-1") is False


def test_registry_release_clears_active_session_and_cancellation():
    registry = AgentRunRegistry()
    registry.acquire("session-1")
    registry.request_cancel("session-1")

    registry.release("session-1")

    assert registry.is_active("session-1") is False
    assert registry.is_cancelled("session-1") is False


def test_registry_acquire_clears_stale_cancellation():
    registry = AgentRunRegistry()
    registry.request_cancel("session-1")

    assert registry.acquire("session-1") is True
    assert registry.is_cancelled("session-1") is False


def test_registry_cancel_request_remains_idempotent():
    registry = AgentRunRegistry()

    assert registry.request_cancel("session-1") is True
    assert registry.request_cancel("session-1") is False
    assert registry.is_cancelled("session-1") is True
