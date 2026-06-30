from __future__ import annotations

from app_backend.services.macro_brief_parser import parse_macro_brief
from app_backend.services.macro_brief_renderer import render_macro_brief_markdown
from tests.ai.test_agent_runtime_mocked import brief_payload


def test_public_renderer_outputs_chinese_markdown_and_public_sources_only():
    brief = parse_macro_brief(brief_payload())

    result = render_macro_brief_markdown(brief, visibility_mode="public")

    assert result.visibility_mode == "public"
    assert "## 核心结论" in result.markdown
    assert "| SPY | 400.00 | +0.10% | 2026-06-28 |" in result.markdown
    assert "https://fred.stlouisfed.org/series/DGS10" in result.markdown
    assert "credit_snapshot" not in result.markdown
    assert "origin=" not in result.markdown


def test_debug_renderer_includes_internal_source_provenance():
    brief = parse_macro_brief(brief_payload())

    result = render_macro_brief_markdown(brief, visibility_mode="debug")

    assert "origin=search" in result.markdown
    assert "origin=rag" in result.markdown
    assert "rag_doc_id=credit_snapshot" in result.markdown
    assert "facts=f1" in result.markdown


def test_renderer_shows_unavailable_market_state_without_fabricating_numbers():
    payload = brief_payload()
    payload["market_state"][0]["price"] = None
    payload["market_state"][0]["change_pct"] = None
    payload["market_state"][0]["as_of"] = None
    brief = parse_macro_brief(payload)

    result = render_macro_brief_markdown(brief, visibility_mode="public")

    assert "| SPY | unavailable | unavailable | unavailable |" in result.markdown


def test_renderer_does_not_create_new_numeric_claims():
    brief = parse_macro_brief(brief_payload())

    result = render_macro_brief_markdown(brief, visibility_mode="public")

    assert "400.00" in result.markdown
    assert "4.3%" in result.markdown
    assert "70%" not in result.markdown
