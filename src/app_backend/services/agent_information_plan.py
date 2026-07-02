"""Local-first information planning seam for the MacroBrief agent."""
from __future__ import annotations

from typing import Any, Literal

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


class AgentToolPlanStep(BaseModel):
    model_config = ConfigDict(extra="forbid")

    topic: str
    tool_name: str
    reason: str
    max_calls: int = Field(default=1, ge=1)
    required: bool = True
    args: list[dict[str, Any]] = Field(default_factory=list)


class AgentToolPlan(BaseModel):
    model_config = ConfigDict(extra="forbid")

    steps: list[AgentToolPlanStep] = Field(default_factory=list)

    @property
    def tool_names(self) -> list[str]:
        return [step.tool_name for step in self.steps]

    @property
    def topics(self) -> list[str]:
        return [step.topic for step in self.steps]


class AgentInformationPlan(BaseModel):
    model_config = ConfigDict(extra="forbid")

    local_first: bool = True
    needs: list[AgentInformationNeed]
    tool_plan: AgentToolPlan = Field(default_factory=AgentToolPlan)

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
    return AgentInformationPlan(
        needs=needs,
        tool_plan=build_agent_tool_plan(user_question=user_question, tool_names=tool_names),
    )


def build_agent_tool_plan(
    *,
    user_question: str,
    tool_names: list[str],
) -> AgentToolPlan:
    """Build a deterministic, bounded tool plan for autonomous agent runs.

    The planner is intentionally local and conservative: keyword detection
    decides which information slots matter, then the backend intersects those
    slots with the actually enabled tools. This lets callers expose fewer tools
    without relying on the model to respect unavailable capabilities.
    """
    available = set(tool_names)
    lowered = user_question.lower()
    steps: list[AgentToolPlanStep] = []

    def add(
        *,
        topic: str,
        tool_name: str,
        reason: str,
        max_calls: int = 1,
        required: bool = True,
        args: list[dict[str, Any]] | None = None,
    ) -> None:
        if tool_name not in available:
            return
        if any(step.topic == topic and step.tool_name == tool_name for step in steps):
            return
        steps.append(
            AgentToolPlanStep(
                topic=topic,
                tool_name=tool_name,
                reason=reason,
                max_calls=max_calls,
                required=required,
                args=list(args or [{}]),
            )
        )

    add(
        topic="dashboard_overview",
        tool_name="dashboard_query",
        reason="Baseline local macro dashboard context is useful for most MacroBrief questions.",
    )
    if _matches_any(lowered, _EQUITY_MARKERS):
        add(
            topic="equity_market",
            tool_name="quote_etf",
            reason="Question asks about equity or portfolio market exposure.",
            max_calls=4,
            args=[{"symbols": [symbol]} for symbol in ("SPY", "QQQ", "SHY", "GLD")],
        )
    if _matches_any(lowered, _RATE_MARKERS):
        add(
            topic="rates",
            tool_name="treasury_curve",
            reason="Question asks about rates, yield curve, Fed transmission, or duration pressure.",
        )
    if _matches_any(lowered, _CREDIT_MARKERS):
        add(
            topic="credit",
            tool_name="evidence_lookup",
            reason="Question asks about credit stress or spreads.",
            args=[{"module_key": "credit_stress"}],
        )
    if _matches_any(lowered, _INFLATION_MARKERS):
        add(
            topic="inflation",
            tool_name="evidence_lookup",
            reason="Question asks about CPI, PCE, inflation, or real-rate pressure.",
            args=[{"module_key": "inflation_energy_pressure"}],
        )
    if _matches_any(lowered, _LABOR_MARKERS):
        add(
            topic="labor",
            tool_name="calendar_lookup",
            reason="Question asks about employment or labor-market releases.",
            args=[{"event_name": "Nonfarm Payrolls"}],
        )
    if _matches_any(lowered, _ENERGY_MARKERS):
        add(
            topic="energy",
            tool_name="commodity_quote",
            reason="Question asks about oil, commodities, or energy risk.",
            required=False,
            args=[{"benchmark": "brent"}],
        )
    if _matches_any(lowered, _DOLLAR_MARKERS):
        add(
            topic="dollar",
            tool_name="quote_dxy",
            reason="Question asks about dollar or FX pressure.",
        )
    if _matches_any(lowered, _POLICY_MARKERS):
        add(
            topic="policy",
            tool_name="calendar_lookup",
            reason="Question asks about Fed, FOMC, or policy timing.",
            args=[{"event_name": "FOMC"}],
        )
    if _matches_any(lowered, _CALENDAR_MARKERS):
        add(
            topic="calendar",
            tool_name="calendar_lookup",
            reason="Question asks about upcoming releases or forward indicators.",
            args=[{"limit": 5}],
        )
    if _matches_any(lowered, _RAG_MARKERS):
        add(
            topic="local_rag_context",
            tool_name="rag_retrieve",
            reason="Question benefits from local historical or institutional context.",
            required=False,
            args=[{"query": _topic_query(lowered, topic="local_rag_context"), "top_k": 5}],
        )
    if _question_needs_current_public_news(lowered):
        add(
            topic="current_public_news",
            tool_name="search_tavily",
            reason="Question asks for current public market, policy, or geopolitical context.",
            max_calls=3,
            required=False,
            args=[{"query": _topic_query(lowered, topic="current_public_news"), "max_results": 5}],
        )

    return AgentToolPlan(steps=steps)


def information_plan_trace_event(plan: AgentInformationPlan) -> AgentRuntimeEvent:
    return AgentRuntimeEvent(
        type="information_gap",
        data={
            "local_first": plan.local_first,
            "missing_topics": plan.missing_topics,
            "search_topics": plan.search_topics,
            "needs": [need.model_dump(mode="json") for need in plan.needs],
            "tool_plan": plan.tool_plan.model_dump(mode="json"),
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


def _matches_any(lowered_question: str, markers: tuple[str, ...]) -> bool:
    return any(marker in lowered_question for marker in markers)


def _topic_query(lowered_question: str, *, topic: str) -> str:
    parts = ["US macro environment"]
    if _matches_any(lowered_question, _RATE_MARKERS):
        parts.append("Treasury yields Fed policy")
    if _matches_any(lowered_question, _INFLATION_MARKERS):
        parts.append("inflation CPI PCE")
    if _matches_any(lowered_question, _LABOR_MARKERS):
        parts.append("labor market payrolls")
    if _matches_any(lowered_question, _ENERGY_MARKERS):
        parts.append("energy oil risk")
    if _matches_any(lowered_question, _DOLLAR_MARKERS):
        parts.append("US dollar")
    if _matches_any(lowered_question, _CREDIT_MARKERS):
        parts.append("credit spreads")
    if topic == "local_rag_context":
        parts.append("historical context")
    return " ".join(parts)


_EQUITY_MARKERS = (
    "spy",
    "qqq",
    "shy",
    "gld",
    "equity",
    "stock",
    "portfolio",
    "risk asset",
    "组合",
    "权益",
    "股",
    "风险资产",
)
_RATE_MARKERS = (
    "rate",
    "rates",
    "yield",
    "treasury",
    "duration",
    "fed",
    "fomc",
    "利率",
    "收益率",
    "长端",
    "美债",
    "久期",
    "联储",
)
_CREDIT_MARKERS = (
    "credit",
    "spread",
    "hyg",
    "lqd",
    "信用",
    "利差",
    "高收益",
    "投资级",
)
_INFLATION_MARKERS = (
    "inflation",
    "cpi",
    "pce",
    "real rate",
    "price",
    "通胀",
    "物价",
    "实际利率",
)
_LABOR_MARKERS = (
    "labor",
    "labour",
    "employment",
    "payroll",
    "job",
    "unemployment",
    "就业",
    "非农",
    "失业",
)
_ENERGY_MARKERS = (
    "energy",
    "oil",
    "brent",
    "wti",
    "commodity",
    "能源",
    "油",
    "原油",
    "商品",
)
_DOLLAR_MARKERS = (
    "dollar",
    "usd",
    "dxy",
    "fx",
    "美元",
    "汇率",
)
_POLICY_MARKERS = (
    "fed",
    "fomc",
    "powell",
    "policy",
    "rate cut",
    "rate hike",
    "联储",
    "政策",
    "降息",
    "加息",
)
_CALENDAR_MARKERS = (
    "calendar",
    "release",
    "upcoming",
    "forward",
    "next",
    "日历",
    "发布",
    "前瞻",
    "后续",
)
_RAG_MARKERS = (
    "history",
    "historical",
    "memo",
    "institutional",
    "context",
    "历史",
    "复盘",
    "机构",
    "背景",
)


__all__ = [
    "AgentInformationNeed",
    "AgentInformationPlan",
    "AgentToolPlan",
    "AgentToolPlanStep",
    "build_agent_information_plan",
    "build_agent_tool_plan",
    "information_plan_trace_event",
]
