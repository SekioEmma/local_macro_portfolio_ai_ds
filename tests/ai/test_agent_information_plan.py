from __future__ import annotations

from app_backend.services.agent_information_plan import (
    build_agent_tool_plan,
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


def test_tool_plan_maps_macro_question_to_bounded_tools():
    plan = build_agent_tool_plan(
        user_question=(
            "当前美国宏观环境综合评估，结合长端利率、美元、信用利差、通胀、"
            "就业、能源风险和未来三个月 SPY/QQQ/SHY/GLD 组合风险暴露。"
        ),
        tool_names=[
            "dashboard_query",
            "evidence_lookup",
            "quote_etf",
            "treasury_curve",
            "calendar_lookup",
            "rag_retrieve",
            "search_tavily",
            "commodity_quote",
            "quote_dxy",
            "finalize_macro_brief",
        ],
    )

    by_topic = {step.topic: step for step in plan.steps}

    assert by_topic["dashboard_overview"].tool_name == "dashboard_query"
    assert by_topic["equity_market"].tool_name == "quote_etf"
    assert by_topic["rates"].tool_name == "treasury_curve"
    assert by_topic["credit"].tool_name == "evidence_lookup"
    assert by_topic["inflation"].tool_name == "evidence_lookup"
    assert by_topic["labor"].tool_name == "calendar_lookup"
    assert by_topic["energy"].tool_name == "commodity_quote"
    assert by_topic["dollar"].tool_name == "quote_dxy"
    assert by_topic["current_public_news"].tool_name == "search_tavily"
    assert by_topic["current_public_news"].max_calls == 3
    assert by_topic["equity_market"].args == [
        {"symbol": "SPY"},
        {"symbol": "QQQ"},
        {"symbol": "SHY"},
        {"symbol": "GLD"},
    ]


def test_tool_plan_respects_enabled_tools_and_search_confirmation_boundary():
    plan = build_agent_tool_plan(
        user_question="最新地缘和油价如何影响美元与利率？",
        tool_names=["dashboard_query", "treasury_curve", "quote_dxy"],
    )

    assert plan.tool_names == ["dashboard_query", "treasury_curve", "quote_dxy"]
    assert "search_tavily" not in plan.tool_names
    assert "commodity_quote" not in plan.tool_names


def test_information_plan_embeds_tool_plan_without_raw_question():
    plan = build_agent_information_plan(
        user_question="latest geopolitical oil news with private wording",
        tool_names=["dashboard_query", "search_tavily", "commodity_quote"],
    )

    event = information_plan_trace_event(plan)

    assert "tool_plan" in event.data
    assert any(
        step["tool_name"] == "commodity_quote"
        for step in event.data["tool_plan"]["steps"]
    )
    assert "private wording" not in str(event.data)
