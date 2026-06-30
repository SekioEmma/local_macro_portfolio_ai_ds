from __future__ import annotations

from app_backend.services.agent_information_plan import (
    build_agent_information_plan,
    information_plan_trace_event,
)


def test_information_plan_prefers_local_tools_before_search():
    plan = build_agent_information_plan(
        user_question="当前美国宏观环境如何，油价和地缘有什么影响？",
        tool_names=[
            "dashboard_query",
            "quote_etf",
            "treasury_curve",
            "rag_retrieve",
            "search_tavily",
        ],
    )

    needs = {need.topic: need for need in plan.needs}
    assert needs["market_state"].status == "local_available"
    assert needs["rates_and_credit"].status == "local_available"
    assert needs["local_rag_context"].status == "local_available"
    assert needs["current_public_news"].status == "search_required"
    assert needs["current_public_news"].preferred_public_sources


def test_information_plan_marks_public_news_missing_when_search_unavailable():
    plan = build_agent_information_plan(
        user_question="latest geopolitical oil news",
        tool_names=["dashboard_query", "rag_retrieve"],
    )

    assert "current_public_news" in plan.missing_topics
    assert plan.search_topics == []


def test_information_plan_trace_event_is_structured_without_raw_question():
    plan = build_agent_information_plan(
        user_question="latest geopolitical oil news with private wording",
        tool_names=["dashboard_query", "search_tavily"],
    )

    event = information_plan_trace_event(plan)

    assert event.type == "information_gap"
    assert event.data["local_first"] is True
    assert "current_public_news" in event.data["search_topics"]
    assert "private wording" not in str(event.data)
