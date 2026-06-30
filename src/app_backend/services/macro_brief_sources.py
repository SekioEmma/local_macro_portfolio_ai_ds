"""Source visibility helpers for Phase F MacroBrief output.

Internal provenance is kept structured for debugging, while public rendering
can hide local RAG/data-foundation/tool details and show only URL-backed
public sources.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app_backend.schemas.macro_brief import MacroBrief, SourceItem
from app_backend.services.agent_runtime import AgentRuntimeEvent


SourceVisibilityMode = Literal["debug", "public"]
SourceOrigin = Literal["search", "rag", "data_foundation", "tool", "unknown"]

_DATA_FOUNDATION_TOOLS = {
    "dashboard_query",
    "evidence_lookup",
    "quote_etf",
    "treasury_curve",
    "calendar_lookup",
    "quote_dxy",
    "commodity_quote",
    "portfolio_overlay",
}


class MacroBriefSourceReference(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_id: str
    origin: SourceOrigin
    label: str
    url: str | None = None
    rag_doc_id: str | None = None
    accessed_at: str | None = None
    cited_by_fact_ids: list[str] = Field(default_factory=list)
    tool_names: list[str] = Field(default_factory=list)
    public_visible: bool = False


def build_macro_brief_source_references(
    brief: MacroBrief,
    *,
    runtime_events: list[AgentRuntimeEvent] | None = None,
) -> list[MacroBriefSourceReference]:
    fact_ids_by_source = _fact_ids_by_source(brief)
    tool_names = _tool_names_by_origin(runtime_events or [])
    references = [
        _source_reference(
            source,
            cited_by_fact_ids=fact_ids_by_source.get(source.id, []),
            tool_names=tool_names.get(_infer_origin(source), []),
        )
        for source in brief.source_list
    ]

    if runtime_events:
        references.extend(_event_only_references(references, runtime_events))
    return references


def filter_macro_brief_sources(
    references: list[MacroBriefSourceReference],
    *,
    visibility_mode: SourceVisibilityMode,
) -> list[MacroBriefSourceReference]:
    if visibility_mode == "debug":
        return references
    return [reference for reference in references if reference.public_visible]


def render_macro_brief_sources_markdown(
    references: list[MacroBriefSourceReference],
    *,
    visibility_mode: SourceVisibilityMode,
) -> str:
    visible = filter_macro_brief_sources(
        references,
        visibility_mode=visibility_mode,
    )
    if not visible:
        return "未列出公开搜索信源。" if visibility_mode == "public" else "未记录信源。"
    lines: list[str] = []
    for reference in visible:
        suffix = _reference_suffix(reference, visibility_mode)
        if reference.url:
            lines.append(f"- [{reference.label}]({reference.url}){suffix}")
        else:
            lines.append(f"- {reference.label}{suffix}")
    return "\n".join(lines)


def _source_reference(
    source: SourceItem,
    *,
    cited_by_fact_ids: list[str],
    tool_names: list[str],
) -> MacroBriefSourceReference:
    origin = _infer_origin(source)
    label = source.title or source.url or source.rag_doc_id or source.id
    return MacroBriefSourceReference(
        source_id=source.id,
        origin=origin,
        label=label,
        url=source.url,
        rag_doc_id=source.rag_doc_id,
        accessed_at=source.accessed_at,
        cited_by_fact_ids=cited_by_fact_ids,
        tool_names=tool_names,
        public_visible=origin == "search" and bool(source.url),
    )


def _infer_origin(source: SourceItem) -> SourceOrigin:
    if source.rag_doc_id:
        return "rag"
    if source.url:
        return "search"
    return "unknown"


def _fact_ids_by_source(brief: MacroBrief) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for fact in brief.confirmed_facts:
        out.setdefault(fact.source_id, []).append(fact.id)
    return {source_id: sorted(fact_ids) for source_id, fact_ids in out.items()}


def _tool_names_by_origin(events: list[AgentRuntimeEvent]) -> dict[SourceOrigin, list[str]]:
    out: dict[SourceOrigin, set[str]] = {}
    for event in events:
        if event.type != "tool_result":
            continue
        tool_name = event.data.get("tool_name")
        if not isinstance(tool_name, str) or not tool_name:
            continue
        out.setdefault(_origin_for_tool(tool_name), set()).add(tool_name)
    return {origin: sorted(names) for origin, names in out.items()}


def _origin_for_tool(tool_name: str) -> SourceOrigin:
    if tool_name == "search_tavily":
        return "search"
    if tool_name == "rag_retrieve":
        return "rag"
    if tool_name in _DATA_FOUNDATION_TOOLS:
        return "data_foundation"
    return "tool"


def _event_only_references(
    existing: list[MacroBriefSourceReference],
    events: list[AgentRuntimeEvent],
) -> list[MacroBriefSourceReference]:
    existing_origins = {reference.origin for reference in existing}
    references: list[MacroBriefSourceReference] = []
    for origin, names in _tool_names_by_origin(events).items():
        if origin in existing_origins:
            continue
        references.append(
            MacroBriefSourceReference(
                source_id=f"runtime:{origin}",
                origin=origin,
                label=_origin_label(origin),
                tool_names=names,
                public_visible=False,
            )
        )
    return references


def _reference_suffix(
    reference: MacroBriefSourceReference,
    visibility_mode: SourceVisibilityMode,
) -> str:
    if visibility_mode == "public":
        return ""
    details: list[str] = [f"origin={reference.origin}"]
    if reference.rag_doc_id:
        details.append(f"rag_doc_id={reference.rag_doc_id}")
    if reference.cited_by_fact_ids:
        details.append(f"facts={','.join(reference.cited_by_fact_ids)}")
    if reference.tool_names:
        details.append(f"tools={','.join(reference.tool_names)}")
    return f" ({'; '.join(details)})"


def _origin_label(origin: SourceOrigin) -> str:
    labels: dict[SourceOrigin, str] = {
        "search": "联网搜索",
        "rag": "本地 RAG",
        "data_foundation": "本地数据底座",
        "tool": "运行时工具",
        "unknown": "未知来源",
    }
    return labels[origin]


__all__ = [
    "MacroBriefSourceReference",
    "SourceOrigin",
    "SourceVisibilityMode",
    "build_macro_brief_source_references",
    "filter_macro_brief_sources",
    "render_macro_brief_sources_markdown",
]
