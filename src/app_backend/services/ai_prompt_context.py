"""Deterministic full-catalogue and prompt-context selection.

The full catalogue is an audit surface and never silently truncates cards.
The selected prompt context is a separate, mode-aware and budget-aware view:

- P1 is always retained in full.
- P2/P3 are selected by answer mode and stable financial reading order.
- P4 is represented by aggregate constraint distributions rather than raw
  excluded-card payloads.

No external tokenizer or model is called. Token counts are conservative local
estimates used only for budget control.
"""

from __future__ import annotations

import math
from collections import Counter
from dataclasses import asdict
from typing import Any

from app_backend.schemas.ai_preview import (
    AIConstraintSummary,
    AIContextCard,
    AIFullContextCatalogue,
    AIPromptBudgetSummary,
    AISelectedPromptContext,
    AnswerMode,
)
from app_backend.services.ai_evidence_cards import render_manifest_cards
from app_backend.services.ai_research_modes import (
    P2_MODULES_BY_MODE,
    P3_MODULES_BY_MODE,
)


DEFAULT_CARD_LIMIT = 96
DEFAULT_CHAR_LIMIT = 32_000
DEFAULT_ESTIMATED_TOKEN_LIMIT = 12_000

_MODULE_READING_ORDER = {
    "macro_regime_review": 0,
    "financial_stress_composite": 1,
    "credit_stress": 2,
    "liquidity_funding_stress": 3,
    "rate_pressure": 4,
    "real_yield_pressure": 5,
    "pullback_systemic_risk_checklist": 6,
    "inflation_energy_pressure": 10,
    "growth_inflation_macro_pack": 11,
    "equity_trend": 12,
    "market_stress_derived": 13,
    "historical_risk_percentile": 14,
    "valuation_equity_structure": 20,
    "breadth_concentration_proxy": 21,
    "scenario_stress": 22,
    "historical_validation": 23,
    "portfolio_exposure_overlay": 24,
    "portfolio_deviation": 25,
    "data_quality_diagnostics": 26,
}


def build_full_context_catalogue(manifest: dict[str, Any]) -> AIFullContextCatalogue:
    bundle = render_manifest_cards(manifest)
    evidence_cards = [_card_model(card) for card in bundle["evidence_cards"]]
    model_cards = [_card_model(card) for card in bundle["model_output_cards"]]
    excluded_cards = [
        _card_model(card) for card in bundle["excluded_constraint_cards"]
    ]
    all_cards = evidence_cards + model_cards + excluded_cards
    source_distribution = Counter(
        card.source_badge or "unknown"
        for card in evidence_cards + model_cards
    )
    excluded_distribution = Counter(
        card.excluded_reason or "excluded" for card in excluded_cards
    )
    priority_counts = Counter(f"P{card.priority}" for card in all_cards)
    return AIFullContextCatalogue(
        evidence_cards=evidence_cards,
        model_output_cards=model_cards,
        excluded_constraint_cards=excluded_cards,
        total_card_count=len(all_cards),
        priority_counts=dict(sorted(priority_counts.items())),
        source_badge_distribution=dict(sorted(source_distribution.items())),
        excluded_reason_distribution=dict(sorted(excluded_distribution.items())),
    )


def select_prompt_context(
    manifest: dict[str, Any],
    *,
    answer_mode: AnswerMode,
    card_limit: int = DEFAULT_CARD_LIMIT,
    char_limit: int = DEFAULT_CHAR_LIMIT,
    estimated_token_limit: int = DEFAULT_ESTIMATED_TOKEN_LIMIT,
) -> tuple[AISelectedPromptContext, AIPromptBudgetSummary]:
    bundle = render_manifest_cards(manifest)
    included_cards = sorted(
        bundle["evidence_cards"] + bundle["model_output_cards"],
        key=_card_sort_key,
    )
    constraint_summary = _constraint_summary(
        bundle["excluded_constraint_cards"]
    )
    constraint_text = _constraint_summary_text(constraint_summary)

    p1_cards = [card for card in included_cards if card.priority == 1]
    p2_cards = [card for card in included_cards if card.priority == 2]
    p3_cards = [card for card in included_cards if card.priority == 3]
    selected = list(p1_cards)
    selected_texts = [_prompt_card_text(card) for card in selected]

    omitted_by_priority: Counter[str] = Counter()
    omitted_by_reason: Counter[str] = Counter()
    ready = True
    status_reason = "selected_prompt_context_within_budget"

    base_text = _join_context(selected_texts, constraint_text)
    if not _within_budget(
        card_count=len(selected),
        text=base_text,
        card_limit=card_limit,
        char_limit=char_limit,
        estimated_token_limit=estimated_token_limit,
    ):
        ready = False
        status_reason = "p1_core_context_exceeds_budget_not_truncated"
        for card in p2_cards + p3_cards:
            omitted_by_priority[f"P{card.priority}"] += 1
            omitted_by_reason["p1_budget_guard"] += 1
    else:
        allowed_p2 = P2_MODULES_BY_MODE[answer_mode]
        allowed_p3 = P3_MODULES_BY_MODE[answer_mode]
        budget_stopped = False
        for card in p2_cards + p3_cards:
            allowed_modules = allowed_p2 if card.priority == 2 else allowed_p3
            if card.module not in allowed_modules:
                omitted_by_priority[f"P{card.priority}"] += 1
                omitted_by_reason["mode_filtered"] += 1
                continue
            if budget_stopped:
                omitted_by_priority[f"P{card.priority}"] += 1
                omitted_by_reason["budget_exceeded"] += 1
                continue
            candidate_texts = selected_texts + [_prompt_card_text(card)]
            candidate_text = _join_context(candidate_texts, constraint_text)
            if not _within_budget(
                card_count=len(selected) + 1,
                text=candidate_text,
                card_limit=card_limit,
                char_limit=char_limit,
                estimated_token_limit=estimated_token_limit,
            ):
                omitted_by_priority[f"P{card.priority}"] += 1
                omitted_by_reason["budget_exceeded"] += 1
                budget_stopped = True
                continue
            selected.append(card)
            selected_texts.append(_prompt_card_text(card))

    selected_text = _join_context(selected_texts, constraint_text)
    selected_models = [_card_model(card) for card in selected]
    omitted_count = sum(omitted_by_priority.values())
    selection_notes = [
        "P1 核心宏观状态完整保留。",
        "P2/P3 按回答模式、稳定金融阅读顺序和预算选择。",
        "P4 仅以排除原因、模块与新鲜度分布摘要进入 Prompt。",
    ]
    if omitted_count:
        selection_notes.append(
            f"共有 {omitted_count} 张 P2/P3 卡片未进入 Prompt；"
            "完整卡片仍保留在 Full Context Catalogue。"
        )
    if not ready:
        selection_notes.append(
            "P1 核心上下文本身超过预算，因此 Prompt 标记为 not_ready，"
            "核心证据未被静默截断。"
        )

    context = AISelectedPromptContext(
        selected_cards=selected_models,
        constraint_summary=constraint_summary,
        selected_context_text=selected_text,
        selection_notes=selection_notes,
    )
    budget = AIPromptBudgetSummary(
        card_limit=card_limit,
        char_limit=char_limit,
        estimated_token_limit=estimated_token_limit,
        selected_card_count=len(selected_models),
        selected_char_count=len(selected_text),
        estimated_token_count=estimate_tokens(selected_text),
        omitted_card_count=omitted_count,
        omitted_by_priority=dict(sorted(omitted_by_priority.items())),
        omitted_by_reason=dict(sorted(omitted_by_reason.items())),
        ready=ready,
        status_reason=status_reason,
    )
    return context, budget


def estimate_tokens(text: str) -> int:
    """Return a conservative local estimate, not a provider tokenizer result."""

    if not text:
        return 0
    return math.ceil(len(text) / 3)


def _constraint_summary(cards: list[Any]) -> AIConstraintSummary:
    reasons = Counter(
        str(getattr(card, "excluded_reason", None) or "excluded") for card in cards
    )
    modules = Counter(str(getattr(card, "module", None) or "unknown") for card in cards)
    freshness = Counter(
        str(getattr(card, "freshness_status", None) or "unknown") for card in cards
    )
    total = len(cards)
    summary = (
        f"共有 {total} 条排除约束。"
        f"排除原因分布：{_format_distribution(reasons)}；"
        f"模块分布：{_format_distribution(modules)}；"
        f"新鲜度分布：{_format_distribution(freshness)}。"
        "这些项目不能被升级为事实，也不能用于触发强结论。"
    )
    return AIConstraintSummary(
        total_count=total,
        excluded_reason_distribution=dict(sorted(reasons.items())),
        module_distribution=dict(sorted(modules.items())),
        freshness_distribution=dict(sorted(freshness.items())),
        summary_zh=summary,
    )


def _constraint_summary_text(summary: AIConstraintSummary) -> str:
    return "[P4 约束摘要]\n" + summary.summary_zh


def _format_distribution(counter: Counter[str]) -> str:
    if not counter:
        return "无"
    return "、".join(f"{key}={value}" for key, value in sorted(counter.items()))


def _join_context(card_texts: list[str], constraint_text: str) -> str:
    parts = list(card_texts)
    if constraint_text:
        parts.append(constraint_text)
    return "\n\n".join(parts)


def _prompt_card_text(card: Any) -> str:
    """Return a compact prompt representation without repeated policy copy."""

    card_type = str(getattr(card, "card_type", "context_card"))
    prefix = {
        "evidence_card": "EVIDENCE",
        "model_output_card": "MODEL",
    }.get(card_type, "CONTEXT")
    fields = [
        f"[{prefix} P{getattr(card, 'priority', 3)}]",
        f"id={getattr(card, 'module', 'unknown')}.{getattr(card, 'metric_key', 'unknown')}",
        f"name={getattr(card, 'display_name', 'context')}",
        f"value={getattr(card, 'value_text', '') or '—'}",
        f"status={getattr(card, 'status', '') or 'unknown'}",
        f"source={getattr(card, 'source_badge', '') or 'unknown'}",
        f"freshness={getattr(card, 'freshness_status', '') or 'unknown'}",
    ]
    observation_date = getattr(card, "observation_date", None)
    if observation_date:
        fields.append(f"date={observation_date}")
    trigger = getattr(card, "trigger_eligibility", None)
    if trigger:
        fields.append(f"trigger={trigger}")
    for field_name in (
        "support_band",
        "severity_band",
        "uncertainty_band",
        "evidence_quality_band",
        "conflict_band",
    ):
        value = getattr(card, field_name, None)
        if value:
            fields.append(f"{field_name}={value}")
    missing_count = getattr(card, "missing_input_count", None)
    if missing_count:
        fields.append(f"missing_inputs={missing_count}")
    return " | ".join(fields)


def _within_budget(
    *,
    card_count: int,
    text: str,
    card_limit: int,
    char_limit: int,
    estimated_token_limit: int,
) -> bool:
    return (
        card_count <= card_limit
        and len(text) <= char_limit
        and estimate_tokens(text) <= estimated_token_limit
    )


def _card_model(card: Any) -> AIContextCard:
    return AIContextCard(**asdict(card))


def _card_sort_key(card: Any) -> tuple[int, int, str, str, str]:
    module = str(getattr(card, "module", ""))
    return (
        int(getattr(card, "priority", 3)),
        _MODULE_READING_ORDER.get(module, 999),
        module,
        str(getattr(card, "metric_key", "")),
        str(getattr(card, "card_type", "")),
    )


__all__ = [
    "DEFAULT_CARD_LIMIT",
    "DEFAULT_CHAR_LIMIT",
    "DEFAULT_ESTIMATED_TOKEN_LIMIT",
    "build_full_context_catalogue",
    "estimate_tokens",
    "select_prompt_context",
]
