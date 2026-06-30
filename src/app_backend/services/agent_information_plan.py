"""Local-first information planning seam for the MacroBrief agent."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app_backend.services.agent_runtime import AgentRuntimeEvent


NeedStatus = Literal["local_available", "search_required", "missing"]


class AgentInformationNeed(BaseModel):
    model_config = ConfigDict(extra="forbid")

    topic: str
    status: NeedStatus
    reason: str
    local_tools: list[str] = Field(default_factory=list)
    preferred_public_sources: list[str] = Field(default_factory=list)


class AgentInformationPlan(BaseModel):
    model_config = ConfigDict(extra="forbid")

    local_first: bool = True
    needs: list[AgentInformationNeed]

    @property
    def missing_topics(self) -> list[str]:
        return [need.topic for need in self.needs if need.status == "missing"]

    @property
    def search_topics(self) -> list[str]:
        return [need.topic for need in self.needs if need.status == "search_required"]


def build_agent_information_plan(
    *,
    user_question: str,
    tool_names: list[str],
) -> AgentInformationPlan:
    """Plan local coverage and public-search gaps without calling tools."""
    available = set(tool_names)
    lowered = user_question.lower()
    needs = [
        _need(
            topic="market_state",
            local_tools=_available_tools(available, ["quote_etf", "dashboard_query"]),
            fallback_reason="ETF market state needs quote_etf or dashboard_query.",
        ),
        _need(
            topic="rates_and_credit",
            local_tools=_available_tools(available, ["treasury_curve", "dashboard_query", "evidence_lookup"]),
            fallback_reason="Rates and credit need treasury_curve, dashboard_query, or evidence_lookup.",
        ),
        _need(
            topic="local_rag_context",
            local_tools=_available_tools(available, ["rag_retrieve"]),
            fallback_reason="Local historical/institutional context needs rag_retrieve.",
        ),
    ]
    if _question_needs_current_public_news(lowered):
        needs.append(
            _public_news_need(
                search_available="search_tavily" in available,
                reason="Question asks for current public market/geopolitical context.",
            )
        )
    return AgentInformationPlan(needs=needs)


def information_plan_trace_event(plan: AgentInformationPlan) -> AgentRuntimeEvent:
    return AgentRuntimeEvent(
        type="information_gap",
        data={
            "local_first": plan.local_first,
            "missing_topics": plan.missing_topics,
            "search_topics": plan.search_topics,
            "needs": [need.model_dump(mode="json") for need in plan.needs],
        },
    )


def _need(
    *,
    topic: str,
    local_tools: list[str],
    fallback_reason: str,
) -> AgentInformationNeed:
    if local_tools:
        return AgentInformationNeed(
            topic=topic,
            status="local_available",
            reason="Local project tools can provide this information.",
            local_tools=local_tools,
        )
    return AgentInformationNeed(
        topic=topic,
        status="missing",
        reason=fallback_reason,
    )


def _public_news_need(*, search_available: bool, reason: str) -> AgentInformationNeed:
    if search_available:
        return AgentInformationNeed(
            topic="current_public_news",
            status="search_required",
            reason=reason,
            local_tools=["search_tavily"],
            preferred_public_sources=[
                "official agencies",
                "central banks",
                "FRED",
                "BEA",
                "BLS",
                "Reuters",
            ],
        )
    return AgentInformationNeed(
        topic="current_public_news",
        status="missing",
        reason="Current public-news gap requires search_tavily, but it is unavailable.",
        preferred_public_sources=[
            "official agencies",
            "central banks",
            "Reuters",
        ],
    )


def _available_tools(available: set[str], candidates: list[str]) -> list[str]:
    return [name for name in candidates if name in available]


def _question_needs_current_public_news(lowered_question: str) -> bool:
    markers = (
        "current",
        "latest",
        "today",
        "now",
        "geopolitical",
        "oil",
        "energy",
        "reuters",
        "news",
        "当前",
        "最新",
        "今天",
        "地缘",
        "油价",
        "能源",
        "新闻",
    )
    return any(marker in lowered_question for marker in markers)


__all__ = [
    "AgentInformationNeed",
    "AgentInformationPlan",
    "build_agent_information_plan",
    "information_plan_trace_event",
]
