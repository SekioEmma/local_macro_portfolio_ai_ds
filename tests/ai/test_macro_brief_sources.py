from __future__ import annotations

from app_backend.services.agent_runtime import AgentRuntimeEvent
from app_backend.services.macro_brief_parser import parse_macro_brief
from app_backend.services.macro_brief_sources import (
    build_macro_brief_source_references,
    filter_macro_brief_sources,
    render_macro_brief_sources_markdown,
)
from tests.ai.test_agent_runtime_mocked import brief_payload


def test_debug_source_mode_keeps_search_rag_and_tool_provenance():
    brief = parse_macro_brief(brief_payload())
    events = [
        AgentRuntimeEvent(
            type="tool_result",
            step=1,
            data={"tool_name": "dashboard_query", "status": "ok"},
        ),
        AgentRuntimeEvent(
            type="tool_result",
            step=2,
            data={"tool_name": "rag_retrieve", "status": "ok"},
        ),
    ]

    references = build_macro_brief_source_references(brief, runtime_events=events)
    debug_references = filter_macro_brief_sources(references, visibility_mode="debug")

    assert {reference.origin for reference in debug_references} == {
        "search",
        "rag",
        "data_foundation",
    }
    rag_reference = next(reference for reference in debug_references if reference.origin == "rag")
    assert rag_reference.rag_doc_id == "credit_snapshot"
    assert rag_reference.tool_names == ["rag_retrieve"]
    data_reference = next(reference for reference in debug_references if reference.origin == "data_foundation")
    assert data_reference.tool_names == ["dashboard_query"]


def test_public_source_mode_only_keeps_url_backed_search_sources():
    brief = parse_macro_brief(brief_payload())

    references = build_macro_brief_source_references(brief)
    public_references = filter_macro_brief_sources(references, visibility_mode="public")

    assert len(public_references) == 1
    assert public_references[0].origin == "search"
    assert public_references[0].url == "https://fred.stlouisfed.org/series/DGS10"
    assert public_references[0].rag_doc_id is None


def test_debug_source_markdown_includes_internal_provenance():
    brief = parse_macro_brief(brief_payload())
    references = build_macro_brief_source_references(brief)

    markdown = render_macro_brief_sources_markdown(references, visibility_mode="debug")

    assert "origin=search" in markdown
    assert "origin=rag" in markdown
    assert "facts=f1" in markdown
    assert "rag_doc_id=credit_snapshot" in markdown


def test_public_source_markdown_hides_rag_doc_ids():
    brief = parse_macro_brief(brief_payload())
    references = build_macro_brief_source_references(brief)

    markdown = render_macro_brief_sources_markdown(references, visibility_mode="public")

    assert "https://fred.stlouisfed.org/series/DGS10" in markdown
    assert "credit_snapshot" not in markdown
    assert "origin=" not in markdown
