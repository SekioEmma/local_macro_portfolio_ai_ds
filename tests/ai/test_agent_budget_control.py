from __future__ import annotations

from app_backend.services.agent_runtime import AgentBudget


def test_agent_budget_tracks_steps_and_tokens():
    budget = AgentBudget(max_steps=2)

    assert budget.has_step()
    budget.record_step()
    budget.record_step()

    assert not budget.has_step()
