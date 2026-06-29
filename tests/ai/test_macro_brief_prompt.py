from __future__ import annotations

from datetime import date

import pytest

from app_backend.schemas.macro_brief import (
    REQUIRED_BOUNDARY_KEYWORDS,
    REQUIRED_ETF_SYMBOLS,
    REQUIRED_MODULE_KEYS,
    REQUIRED_SCENARIO_KEYS,
)
from app_backend.services.agent_tool_registry import FINALIZE_TOOL_NAME
from app_backend.services.macro_brief_prompt import (
    ANTI_CONSERVATIVE_BIAS_RULES,
    ANTI_HALLUCINATION_RULES,
    MACRO_BRIEF_RESPONSE_FORMAT,
    build_macro_brief_prompt,
)


def test_build_macro_brief_prompt_contains_f3_1_system_scaffold():
    prompt = build_macro_brief_prompt(
        user_question=" 分析当前美国宏观环境 ",
        current_date=date(2026, 6, 29),
        tool_names=["rag_retrieve", "dashboard_query", FINALIZE_TOOL_NAME],
        instrument_context="Portfolio instruments: SPY, QQQ, SHY, GLD.",
    )

    assert "Today's date is 2026-06-29" in prompt.system_prompt
    assert "dashboard_query, finalize_macro_brief, rag_retrieve" in prompt.system_prompt
    assert "Instrument context:" in prompt.system_prompt
    assert "MacroBrief JSON schema summary" in prompt.system_prompt
    assert FINALIZE_TOOL_NAME in prompt.system_prompt
    assert prompt.user_prompt.startswith("Research question:\n分析当前美国宏观环境")
    assert prompt.response_format == MACRO_BRIEF_RESPONSE_FORMAT


def test_system_prompt_names_required_schema_sections():
    prompt = build_macro_brief_prompt(
        user_question="x",
        current_date=date(2026, 6, 29),
        tool_names=[FINALIZE_TOOL_NAME],
    )
    text = prompt.system_prompt

    for symbol in REQUIRED_ETF_SYMBOLS:
        assert symbol in text
    for module_key in REQUIRED_MODULE_KEYS:
        assert module_key in text
    for scenario_key in REQUIRED_SCENARIO_KEYS:
        assert scenario_key in text
    for keyword in REQUIRED_BOUNDARY_KEYWORDS:
        assert keyword in text


def test_system_prompt_contains_anti_hallucination_rules():
    prompt = build_macro_brief_prompt(
        user_question="x",
        current_date=date(2026, 6, 29),
        tool_names=[FINALIZE_TOOL_NAME],
    )

    text = prompt.system_prompt
    assert ANTI_HALLUCINATION_RULES in text
    assert "Every numerical claim must originate from a tool call result" in text
    assert "source_id in source_list" in text
    assert "Do not silently reconcile" in text
    assert "For any post-2025 data, never guess" in text


def test_system_prompt_contains_status_and_scenario_discipline():
    prompt = build_macro_brief_prompt(
        user_question="x",
        current_date=date(2026, 6, 29),
        tool_names=[FINALIZE_TOOL_NAME],
    )

    text = prompt.system_prompt
    assert ANTI_CONSERVATIVE_BIAS_RULES in text
    assert "Reserve watch for genuinely mixed evidence" in text
    assert "The base scenario should reflect the most evidence-supported path" in text
    assert "distinct, non-trivial trigger_conditions" in text


def test_system_prompt_stays_under_f3_budget():
    prompt = build_macro_brief_prompt(
        user_question="分析当前美国宏观环境，未来 3 个月组合该如何看待",
        current_date=date(2026, 6, 29),
        tool_names=[
            "dashboard_query",
            "evidence_lookup",
            "search_tavily",
            "rag_retrieve",
            "quote_etf",
            "treasury_curve",
            "quote_dxy",
            "commodity_quote",
            "calendar_lookup",
            "portfolio_overlay",
            FINALIZE_TOOL_NAME,
        ],
        instrument_context="SPY/QQQ/SHY/GLD fixed macro portfolio context.",
    )

    assert len(prompt.system_prompt.encode("utf-8")) < 8000


def test_messages_are_provider_style_system_then_user():
    prompt = build_macro_brief_prompt(
        user_question="What is the macro setup?",
        current_date=date(2026, 6, 29),
        tool_names=[FINALIZE_TOOL_NAME],
    )

    assert prompt.messages() == [
        {"role": "system", "content": prompt.system_prompt},
        {"role": "user", "content": prompt.user_prompt},
    ]


@pytest.mark.parametrize(
    "kwargs",
    [
        {"user_question": "", "tool_names": [FINALIZE_TOOL_NAME]},
        {"user_question": "x", "tool_names": []},
        {"user_question": "x", "tool_names": [" "]},
    ],
)
def test_build_macro_brief_prompt_rejects_empty_inputs(kwargs):
    with pytest.raises(ValueError):
        build_macro_brief_prompt(
            current_date=date(2026, 6, 29),
            **kwargs,
        )
