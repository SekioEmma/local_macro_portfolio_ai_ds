from __future__ import annotations

from app_backend.services.agent_runtime import ToolDisabled


def test_tool_disabled_exception_carries_tool_name():
    error = ToolDisabled("search_tavily")

    assert error.name == "search_tavily"
