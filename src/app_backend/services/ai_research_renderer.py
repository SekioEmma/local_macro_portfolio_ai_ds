"""Chinese deterministic renderer for the local controlled research preview."""

from __future__ import annotations

from collections import Counter
from typing import Any

from app_backend.schemas.ai_memo import (
    AIMemoContextUsedSummary,
    AIMemoPrivacySummary,
)
from app_backend.schemas.ai_preview import (
    AIPromptPreviewResponse,
    AIResearchPreviewResponse,
    AIResearchSection,
    AnswerMode,
    DetailLevel,
)
from app_backend.services.ai_prompt_context import select_prompt_context
from app_backend.services.ai_research_modes import (
    ANSWER_MODE_TASKS_ZH,
    ANSWER_MODE_TITLES_ZH,
    ANSWER_MODE_TO_MEMO_TYPE,
)
from app_backend.services.ai_research_validator import validate_research_domains


MODE = "local_controlled_research_preview"
INTERPRETATION_BOUNDARY_ZH = (
    "本内容是基于 AI Context Manifest 的本地确定性证据复核；"
    "不是预测、事件概率、收益路径、交易动作、配置建议或仓位指令。"
)
SYSTEM_BOUNDARY_ZH = (
    "你是本地宏观金融风险研究助手，只能使用下方选中的 AI Context Manifest "
    "证据卡片、模型输出卡片与约束摘要。必须区分事实、模型输出、代理、缺失和"
    "排除约束。不得输出买入、卖出、加仓、减仓、清仓、抄底、对冲、再平衡、"
    "目标配置、预期收益、价格路径、危机概率、衰退概率或市场方向概率。"
    "证据不足时必须明确写明证据不足，并要求人工复核。"
)
OUTPUT_CONTRACT_ZH = [
    "使用中文金融研究语言，先陈述当前证据支持什么以及不支持什么。",
    "每个实质结论必须引用对应的 evidence/model context id。",
    "反向证据与 missing/stale/proxy 约束必须分开表达。",
    "代理证据不能触发系统性风险、真实广度或宏观状态强结论。",
    "情景不是预测，历史验证不是回测，金融压力评分不是概率。",
    "组合内容仅限本地清洗后的紧凑风险通道解释。",
    "不得输出交易动作、目标配置、概率或收益预测。",
]
PREFLIGHT_CHECKLIST_ZH = [
    "上下文仅来自 AI Context Manifest。",
    "P1 核心证据完整保留，P2/P3 按模式和预算选择。",
    "P4 仅以缺失、代理、陈旧和来源门禁分布摘要进入 Prompt。",
    "未调用 DeepSeek、Tavily、外部搜索或 live provider。",
    "未保存问题、Prompt、回答或聊天历史。",
    "输出必须通过语言、隐私和金融语义检查并接受人工复核。",
]

_DETAIL_CARD_COUNTS: dict[DetailLevel, int] = {
    "brief": 3,
    "standard": 5,
    "deep": 8,
}
_NORMAL_STATUSES = {"ok", "normal", "stable", "low", "neutral", "not_confirmed"}


def render_research_preview(
    manifest: dict[str, Any],
    *,
    answer_mode: AnswerMode,
    detail_level: DetailLevel,
) -> AIResearchPreviewResponse:
    selected_context, budget = select_prompt_context(
        manifest,
        answer_mode=answer_mode,
    )
    sections = _render_sections(
        answer_mode=answer_mode,
        detail_level=detail_level,
        selected_cards=selected_context.selected_cards,
        constraint_summary=selected_context.constraint_summary.summary_zh,
    )
    answer_preview = "\n\n".join(
        f"{section.title}\n{section.content}" for section in sections
    )
    validator_result, semantic_result = validate_research_domains(
        system_boundary=SYSTEM_BOUNDARY_ZH,
        task_instruction=_task_instruction(answer_mode),
        selected_context=selected_context.selected_context_text,
        model_answer=answer_preview,
        validator_explanation="本地预览仅 blocker 阻断，其余 finding 进入人工复核。",
        sections=sections,
        selected_cards=selected_context.selected_cards,
        prompt_ready=budget.ready,
    )
    response_sections = [] if semantic_result.blocked else sections
    response_answer = "" if semantic_result.blocked else answer_preview
    response_context = (
        _blocked_prompt_context(selected_context)
        if semantic_result.blocked
        else selected_context
    )
    return AIResearchPreviewResponse(
        mode=MODE,
        answer_mode=answer_mode,
        legacy_memo_type=ANSWER_MODE_TO_MEMO_TYPE[answer_mode],
        detail_level=detail_level,
        title=ANSWER_MODE_TITLES_ZH[answer_mode],
        answer_preview=response_answer,
        research_sections=response_sections,
        selected_prompt_context=response_context,
        prompt_budget=budget,
        context_used_summary=_context_summary(manifest),
        privacy_summary=_privacy_summary(),
        validator_result=validator_result,
        semantic_validator_result=semantic_result,
        not_sent_to_external_model=True,
        human_review_required=True,
        interpretation_boundary=INTERPRETATION_BOUNDARY_ZH,
    )


def render_prompt_preview(
    manifest: dict[str, Any],
    *,
    answer_mode: AnswerMode,
    detail_level: DetailLevel,
) -> AIPromptPreviewResponse:
    selected_context, budget = select_prompt_context(
        manifest,
        answer_mode=answer_mode,
    )
    task_instruction = _task_instruction(answer_mode)
    prompt_text = (
        "[SYSTEM BOUNDARY]\n"
        f"{SYSTEM_BOUNDARY_ZH}\n\n"
        "[TASK INSTRUCTION]\n"
        f"{task_instruction}\n\n"
        "[SELECTED PROMPT CONTEXT]\n"
        f"{selected_context.selected_context_text}\n\n"
        "[OUTPUT CONTRACT]\n"
        + "\n".join(f"- {item}" for item in OUTPUT_CONTRACT_ZH)
    )
    _, semantic_result = validate_research_domains(
        system_boundary=SYSTEM_BOUNDARY_ZH,
        task_instruction=task_instruction,
        selected_context=selected_context.selected_context_text,
        model_answer="",
        validator_explanation="Prompt Preview 只检查选中上下文隐私和预算。",
        sections=[],
        selected_cards=selected_context.selected_cards,
        prompt_ready=budget.ready,
    )
    response_context = (
        _blocked_prompt_context(selected_context)
        if semantic_result.blocked
        else selected_context
    )
    return AIPromptPreviewResponse(
        mode="local_prompt_preview",
        status="ready" if budget.ready and not semantic_result.blocked else "not_ready",
        answer_mode=answer_mode,
        legacy_memo_type=ANSWER_MODE_TO_MEMO_TYPE[answer_mode],
        detail_level=detail_level,
        system_boundary=SYSTEM_BOUNDARY_ZH,
        task_instruction=task_instruction,
        selected_prompt_context=response_context,
        output_contract=OUTPUT_CONTRACT_ZH,
        preflight_checklist=PREFLIGHT_CHECKLIST_ZH,
        prompt_budget=budget,
        prompt_text="" if semantic_result.blocked else prompt_text,
        semantic_validator_result=semantic_result,
        not_sent_to_external_model=True,
        search_called=False,
        saved_by_default=False,
    )


def _render_sections(
    *,
    answer_mode: AnswerMode,
    detail_level: DetailLevel,
    selected_cards: list[Any],
    constraint_summary: str,
) -> list[AIResearchSection]:
    card_limit = _DETAIL_CARD_COUNTS[detail_level]
    p1_cards = [card for card in selected_cards if card.priority == 1]
    p2_cards = [card for card in selected_cards if card.priority == 2]
    p3_cards = [card for card in selected_cards if card.priority == 3]
    normal_cards = [
        card
        for card in selected_cards
        if str(card.status or "").lower() in _NORMAL_STATUSES
    ]

    conclusion_cards = _prefer_modules(
        p1_cards,
        [
            "macro_regime_review",
            "financial_stress_composite",
            "pullback_systemic_risk_checklist",
            "credit_stress",
            "liquidity_funding_stress",
        ],
        limit=3,
    )
    supporting_cards = (p1_cards + p2_cards + p3_cards)[:card_limit]
    used_context_ids = set(
        _context_ids(conclusion_cards) + _context_ids(supporting_cards)
    )
    counter_cards = [
        card
        for card in normal_cards
        if f"{card.module}.{card.metric_key}" not in used_context_ids
    ][: min(4, card_limit)]
    macro_cards = _macro_cards(
        answer_mode,
        p1_cards=p1_cards,
        p2_cards=p2_cards,
        p3_cards=p3_cards,
        limit=card_limit,
    )
    portfolio_cards = [
        card
        for card in selected_cards
        if card.module in {"portfolio_exposure_overlay", "portfolio_deviation"}
    ][:card_limit]
    watch_cards = _watch_cards(selected_cards, card_limit)

    conclusion_tags = ["evidence_review", "macro_state"]
    conclusion_modules = {card.module for card in conclusion_cards}
    if {
        "pullback_systemic_risk_checklist",
        "credit_stress",
        "liquidity_funding_stress",
    }.issubset(conclusion_modules):
        conclusion_tags.append("systemic_risk_review")
    if any(card.module == "financial_stress_composite" for card in conclusion_cards):
        conclusion_tags.extend(
            ["financial_stress_score", "stress_pressure_temperature"]
        )

    macro_tags = ["macro_explanation"]
    if any(card.module == "scenario_stress" for card in macro_cards):
        macro_tags.extend(["scenario_context", "scenario_not_forecast"])
    if any(card.module == "historical_validation" for card in macro_cards):
        macro_tags.extend(["historical_context", "historical_not_backtest"])

    return [
        AIResearchSection(
            key="current_conclusion",
            title="一、当前结论",
            content=_conclusion_text(answer_mode, conclusion_cards),
            source_context=_context_ids(conclusion_cards),
            claim_tags=conclusion_tags,
        ),
        AIResearchSection(
            key="supporting_evidence",
            title="二、支撑证据",
            content=_card_narrative(
                supporting_cards,
                prefix="当前可用事实与模型复核层显示",
                empty="当前没有足够的可用证据形成支撑组。",
            ),
            source_context=_context_ids(supporting_cards),
            claim_tags=["evidence_support"],
        ),
        AIResearchSection(
            key="counter_evidence",
            title="三、反向证据",
            content=_card_narrative(
                counter_cards,
                prefix="可用证据中，以下通道尚未显示风险升级共振",
                empty=(
                    "当前可用事实中没有清晰的反向确认项；"
                    "这不等于风险已确认，只表示需要更多可用证据。"
                ),
            ),
            source_context=_context_ids(counter_cards),
            claim_tags=["counter_evidence"],
        ),
        AIResearchSection(
            key="data_constraints",
            title="四、数据质量与缺失约束",
            content=constraint_summary,
            source_context=["manifest.excluded_context_summary"],
            claim_tags=["data_constraints"],
        ),
        AIResearchSection(
            key="macro_explanation",
            title="五、宏观金融解释",
            content=_macro_text(answer_mode, macro_cards),
            source_context=_context_ids(macro_cards),
            claim_tags=macro_tags,
        ),
        AIResearchSection(
            key="portfolio_channels",
            title="六、组合风险通道",
            content=_portfolio_text(portfolio_cards),
            source_context=(
                _context_ids(portfolio_cards)
                + ["manifest.portfolio_context_policy"]
            ),
            claim_tags=["portfolio_context", "portfolio_local_only"],
        ),
        AIResearchSection(
            key="watchlist_and_boundaries",
            title="七、观察指标与边界声明",
            content=_watchlist_text(watch_cards),
            source_context=_context_ids(watch_cards) + ["manifest.risk_boundaries"],
            claim_tags=["watchlist", "boundary_notice"],
        ),
    ]


def _conclusion_text(answer_mode: AnswerMode, cards: list[Any]) -> str:
    if not cards:
        return (
            "当前证据不足以形成稳定判断，应维持 evidence review，"
            "不能把单一市场指标升级为宏观或系统性风险结论。"
        )
    readings = "；".join(_reading(card) for card in cards)
    mode_clause = {
        "daily_brief": "当前市场状态应先从核心宏观压力与数据质量理解",
        "risk_review": "当前判断属于风险证据复核，而不是危机概率判断",
        "scenario_review": "当前情景内容只描述假设传导，不代表未来会发生",
        "portfolio_overlay": "当前仅解释本地组合暴露的风险通道",
        "evidence_audit": "当前重点是区分可用事实与被排除约束",
        "research_memo": "当前报告结论只代表本期 Manifest 的证据状态",
    }[answer_mode]
    stress_boundary = ""
    if any(card.module == "financial_stress_composite" for card in cards):
        stress_boundary = " 金融压力评分仅表示压力温度，不是概率或预测。"
    return f"{mode_clause}。核心读数包括：{readings}。{stress_boundary}"


def _macro_text(answer_mode: AnswerMode, cards: list[Any]) -> str:
    if not cards:
        return "宏观解释层缺少足够的可用证据，不能扩展叙事。"
    readings = "；".join(_reading(card) for card in cards)
    extra = ""
    modules = {card.module for card in cards}
    if "scenario_stress" in modules:
        extra = " 情景矩阵仅用于解释假设冲击如何传导，不是预测或事件概率。"
    if "historical_validation" in modules:
        extra += " 历史验证是事件窗口复盘，不是回测或预测准确率。"
    if answer_mode == "evidence_audit":
        extra = " 审计结论优先说明来源、状态与新鲜度，不替代金融判断。"
    return f"宏观解释应沿信用、融资、利率、实际利率、通胀和权益顺序展开：{readings}。{extra}"


def _blocked_prompt_context(selected_context: Any) -> Any:
    return selected_context.model_copy(
        update={
            "selected_cards": [],
            "selected_context_text": "",
            "selection_notes": [
                *selected_context.selection_notes,
                "检测到 blocker，选中上下文与生成正文已从响应中隐藏。",
            ],
        }
    )


def _portfolio_text(cards: list[Any]) -> str:
    if not cards:
        return (
            "组合部分仅使用本地清洗后的 compact summary。"
            "当前没有足够的组合 overlay 卡片，因此只能保留通道级说明；"
            "不读取持仓行项目，也不构成配置建议或仓位指令。"
        )
    return (
        "组合暴露解释仅使用本地清洗后的紧凑上下文："
        + "；".join(_reading(card) for card in cards)
        + "。这些内容只说明宏观压力可能通过久期、信用、权益 beta 或流动性通道传导，"
        "不读取持仓行项目，也不构成配置建议或仓位指令。"
    )


def _watchlist_text(cards: list[Any]) -> str:
    if cards:
        watchlist = "、".join(
            f"{card.display_name}（{card.metric_key}）" for card in cards
        )
    else:
        watchlist = "信用、融资、长端利率、实际利率和核心通胀"
    return (
        f"后续应继续观察：{watchlist}。{INTERPRETATION_BOUNDARY_ZH}"
        "任何 error 级语义问题都需要人工确认，blocker 则阻断本地显示。"
    )


def _card_narrative(cards: list[Any], *, prefix: str, empty: str) -> str:
    if not cards:
        return empty
    return f"{prefix}：" + "；".join(_reading(card) for card in cards) + "。"


def _reading(card: Any) -> str:
    return (
        f"{card.module_display_zh}的{card.display_name}为"
        f"{card.value_text or '不可用'}，状态为{card.status_display_zh or card.status or '未知'}"
    )


def _context_ids(cards: list[Any]) -> list[str]:
    return [f"{card.module}.{card.metric_key}" for card in cards]


def _prefer_modules(cards: list[Any], modules: list[str], *, limit: int) -> list[Any]:
    result: list[Any] = []
    for module in modules:
        for card in cards:
            if card.module == module and card not in result:
                result.append(card)
                if len(result) >= limit:
                    return result
    return (result + [card for card in cards if card not in result])[:limit]


def _watch_cards(cards: list[Any], limit: int) -> list[Any]:
    preferred = [
        card
        for card in cards
        if card.module
        in {
            "credit_stress",
            "liquidity_funding_stress",
            "rate_pressure",
            "real_yield_pressure",
            "inflation_energy_pressure",
        }
    ]
    return preferred[:limit]


def _macro_cards(
    answer_mode: AnswerMode,
    *,
    p1_cards: list[Any],
    p2_cards: list[Any],
    p3_cards: list[Any],
    limit: int,
) -> list[Any]:
    if answer_mode == "scenario_review":
        scenario = [card for card in p3_cards if card.module == "scenario_stress"]
        return (scenario + p1_cards + p2_cards + p3_cards)[:limit]
    if answer_mode == "research_memo":
        historical = [
            card for card in p3_cards if card.module == "historical_validation"
        ]
        return (historical + p1_cards + p2_cards + p3_cards)[:limit]
    return (p2_cards + p1_cards + p3_cards)[:limit]


def _task_instruction(answer_mode: AnswerMode) -> str:
    return (
        f"任务模式：{ANSWER_MODE_TITLES_ZH[answer_mode]}。"
        f"{ANSWER_MODE_TASKS_ZH[answer_mode]}"
        "请按当前结论、支撑证据、反向证据、数据质量与缺失约束、"
        "宏观金融解释、组合风险通道、观察指标与边界声明七段输出。"
    )


def _context_summary(manifest: dict[str, Any]) -> AIMemoContextUsedSummary:
    return AIMemoContextUsedSummary(
        included_fact_count=len(manifest.get("included_facts") or []),
        excluded_fact_count=len(manifest.get("excluded_facts") or []),
        included_model_output_count=len(manifest.get("included_model_outputs") or []),
        excluded_model_output_count=len(manifest.get("excluded_model_outputs") or []),
    )


def _privacy_summary() -> AIMemoPrivacySummary:
    return AIMemoPrivacySummary(
        uses_ai_context_manifest_only=True,
        uses_holdings_line_items=False,
        uses_raw_provider_payloads=False,
        uses_raw_prompts=False,
        external_model_called=False,
        search_called=False,
        saved_by_default=False,
    )


def constraint_reason_counts(manifest: dict[str, Any]) -> dict[str, int]:
    reasons = Counter(
        str(row.get("excluded_reason") or "excluded")
        for row in (
            list(manifest.get("excluded_facts") or [])
            + list(manifest.get("excluded_model_outputs") or [])
        )
        if isinstance(row, dict)
    )
    return dict(sorted(reasons.items()))


__all__ = [
    "INTERPRETATION_BOUNDARY_ZH",
    "MODE",
    "OUTPUT_CONTRACT_ZH",
    "PREFLIGHT_CHECKLIST_ZH",
    "SYSTEM_BOUNDARY_ZH",
    "constraint_reason_counts",
    "render_prompt_preview",
    "render_research_preview",
]
