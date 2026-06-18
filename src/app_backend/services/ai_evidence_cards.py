"""Structured evidence-card rendering for the AI Context Manifest.

Converts manifest rows into fixed-shape Chinese-readable cards so downstream
prompt builders and UI surfaces can present evidence as discrete units rather
than dumping raw JSON. The cards never expose holdings line items, raw
provider payloads, raw prompt text, credentials, or any other privacy-marked
content.

Cards are bounded explanatory context only. They do not produce any action
directive, allocation directive, probability, return path, or forecast.

Three card types are produced:

- EvidenceCard:           a sanitized factual row (P1-P3 by module)
- ModelOutputCard:        a sanitized model-output row (D10-D19 / Stage 8)
- ExcludedConstraintCard: an excluded / missing / stale row (P4)
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from app_backend.services.ai_context_priority import (
    PRIORITY_EXCLUDED_CONSTRAINT,
    assign_context_priority,
    priority_label,
    sort_rows_by_priority,
)


MODULE_DISPLAY_ZH: dict[str, str] = {
    "credit_stress": "信用利差与压力",
    "rate_pressure": "名义利率压力",
    "real_yield_pressure": "实际收益率压力",
    "inflation_energy_pressure": "通胀与能源压力",
    "equity_trend": "权益趋势",
    "breadth_concentration_proxy": "广度与集中度代理",
    "market_stress_derived": "市场压力派生指标",
    "portfolio_deviation": "组合偏离",
    "data_quality_diagnostics": "数据质量诊断",
    "financial_stress_composite": "金融压力综合 (D10)",
    "pullback_systemic_risk_checklist": "回调与系统性风险复核 (D11)",
    "historical_risk_percentile": "历史风险归一化 (D13)",
    "liquidity_funding_stress": "流动性与短期融资压力 (D14)",
    "growth_inflation_macro_pack": "增长与通胀宏观包 (D17)",
    "valuation_equity_structure": "估值与权益结构 (D18)",
    "macro_regime_review": "宏观状态复核 (D15)",
    "scenario_stress": "情景压力矩阵 (D16)",
    "historical_validation": "历史验证复盘 (D19)",
    "portfolio_exposure_overlay": "组合暴露解释 (Stage 8)",
}

STATUS_DISPLAY_ZH: dict[str, str] = {
    "ok": "正常",
    "watch": "观察",
    "pressure": "压力",
    "stale": "陈旧",
    "missing": "缺失",
    "research_needed": "需要研究",
    "insufficient_history": "历史不足",
    "insufficient_evidence": "证据不足",
    "limited_evidence": "证据有限",
    "not_available": "不可用",
}

SOURCE_BADGE_DISPLAY_ZH: dict[str, str] = {
    "official": "官方",
    "official_fallback": "官方备份",
    "unofficial_fallback": "非官方备份",
    "proxy": "代理",
    "derived": "派生",
    "local": "本地",
    "search-derived": "搜索派生（已排除）",
    "missing": "缺失",
    "research_needed": "需要研究",
}

FRESHNESS_DISPLAY_ZH: dict[str, str] = {
    "fresh": "新鲜",
    "stale": "陈旧",
    "unknown": "未知",
    "missing": "缺失",
    "insufficient_history": "历史不足",
}

TRIGGER_DISPLAY_ZH: dict[str, str] = {
    "eligible": "可触发",
    "ineligible": "不可触发",
    "not_eligible_for_trigger": "不可触发",
    "support_only": "仅作为支撑证据",
    "reference_only": "仅作参考",
}

# Card boundary notices. Always included so semantic validator and existing
# memo validator both pass.
EVIDENCE_CARD_BOUNDARY_ZH = (
    "证据卡片仅为本地确定性解释上下文；不构成预测、不构成事件概率、"
    "不构成收益估计、不构成仓位指令。"
)
MODEL_OUTPUT_CARD_BOUNDARY_ZH = (
    "模型输出卡片仅为本地解释层上下文：金融压力评分是压力温度而非概率，"
    "宏观状态复核是当前证据复核而非未来方向，情景压力矩阵是假设传导矩阵"
    "而非预测；不构成事件概率、不构成收益估计、不构成仓位指令。"
)
EXCLUDED_CONSTRAINT_CARD_BOUNDARY_ZH = (
    "约束卡片说明哪些证据因 missing / research_needed / insufficient_history "
    "/ stale / proxy / not_available 等原因不能进入 AI 事实层；"
    "不能被升级为事实，不能用作触发结论的依据。"
)


@dataclass
class EvidenceCard:
    """Structured factual evidence card.

    Mirrors the manifest row shape but only carries fields safe for AI
    consumption. Includes Chinese display strings for direct UI use and a
    plain `as_text_block` rendering for prompt building.
    """

    module: str
    module_display_zh: str
    metric_key: str
    display_name: str
    value_text: str
    status: str
    status_display_zh: str
    source_badge: str
    source_badge_display_zh: str
    freshness_status: str
    freshness_display_zh: str
    observation_date: str | None
    interpretation_hint: str | None
    interpretation_boundary: str | None
    trigger_eligibility: str | None
    trigger_eligibility_display_zh: str | None
    priority: int
    priority_label_zh: str
    boundary_notice_zh: str = EVIDENCE_CARD_BOUNDARY_ZH
    card_type: str = "evidence_card"

    def as_text_block(self) -> str:
        return _format_card_block(
            heading=f"[证据卡片] {self.module_display_zh} · {self.display_name}",
            lines=[
                f"  module: {self.module}",
                f"  metric: {self.metric_key}",
                f"  value: {self.value_text or '—'}",
                f"  status: {self.status} ({self.status_display_zh})",
                f"  source: {self.source_badge} ({self.source_badge_display_zh})",
                f"  freshness: {self.freshness_status} ({self.freshness_display_zh})",
                f"  observation_date: {self.observation_date or '—'}",
                f"  interpretation_hint: {self.interpretation_hint or '—'}",
                f"  trigger_eligibility: {_display_or_dash(self.trigger_eligibility, self.trigger_eligibility_display_zh)}",
                f"  priority: {self.priority_label_zh}",
                f"  boundary: {self.interpretation_boundary or self.boundary_notice_zh}",
            ],
        )


@dataclass
class ModelOutputCard:
    """Structured model-output card (D10-D19 / Stage 8)."""

    module: str
    module_display_zh: str
    metric_key: str
    display_name: str
    value_text: str
    status: str
    status_display_zh: str
    source_badge: str
    source_badge_display_zh: str
    freshness_status: str
    freshness_display_zh: str
    observation_date: str | None
    interpretation_hint: str | None
    interpretation_boundary: str | None
    support_band: str | None
    severity_band: str | None
    uncertainty_band: str | None
    evidence_quality_band: str | None
    conflict_band: str | None
    missing_input_count: int
    priority: int
    priority_label_zh: str
    boundary_notice_zh: str = MODEL_OUTPUT_CARD_BOUNDARY_ZH
    card_type: str = "model_output_card"

    def as_text_block(self) -> str:
        lines = [
            f"  module: {self.module}",
            f"  metric: {self.metric_key}",
            f"  value: {self.value_text or '—'}",
            f"  status: {self.status} ({self.status_display_zh})",
            f"  source: {self.source_badge} ({self.source_badge_display_zh})",
            f"  freshness: {self.freshness_status} ({self.freshness_display_zh})",
            f"  observation_date: {self.observation_date or '—'}",
        ]
        for label, value in (
            ("support_band", self.support_band),
            ("severity_band", self.severity_band),
            ("uncertainty_band", self.uncertainty_band),
            ("evidence_quality_band", self.evidence_quality_band),
            ("conflict_band", self.conflict_band),
        ):
            if value:
                lines.append(f"  {label}: {value}")
        lines.append(f"  missing_input_count: {self.missing_input_count}")
        lines.append(f"  priority: {self.priority_label_zh}")
        lines.append(
            f"  boundary: {self.interpretation_boundary or self.boundary_notice_zh}"
        )
        return _format_card_block(
            heading=f"[模型输出卡片] {self.module_display_zh} · {self.display_name}",
            lines=lines,
        )


@dataclass
class ExcludedConstraintCard:
    """Structured excluded / missing constraint card."""

    module: str
    module_display_zh: str
    metric_key: str
    display_name: str
    excluded_reason: str
    excluded_reason_display_zh: str
    status: str
    status_display_zh: str
    source_badge: str
    source_badge_display_zh: str
    freshness_status: str
    freshness_display_zh: str
    effect_zh: str
    priority: int = PRIORITY_EXCLUDED_CONSTRAINT
    priority_label_zh: str = field(default="")
    boundary_notice_zh: str = EXCLUDED_CONSTRAINT_CARD_BOUNDARY_ZH
    card_type: str = "excluded_constraint_card"

    def __post_init__(self) -> None:
        if not self.priority_label_zh:
            self.priority_label_zh = priority_label(self.priority, language="zh")

    def as_text_block(self) -> str:
        return _format_card_block(
            heading=f"[约束卡片] {self.module_display_zh} · {self.display_name}",
            lines=[
                f"  module: {self.module}",
                f"  metric: {self.metric_key}",
                f"  excluded_reason: {self.excluded_reason} ({self.excluded_reason_display_zh})",
                f"  status: {self.status} ({self.status_display_zh})",
                f"  source: {self.source_badge} ({self.source_badge_display_zh})",
                f"  freshness: {self.freshness_status} ({self.freshness_display_zh})",
                f"  effect: {self.effect_zh}",
                f"  priority: {self.priority_label_zh}",
                f"  boundary: {self.boundary_notice_zh}",
            ],
        )


def render_evidence_card(row: Mapping[str, Any]) -> EvidenceCard:
    """Render a single factual row into an EvidenceCard.

    Raises ValueError if the row is missing both module and metric_key, since
    a card with no identity is meaningless.
    """

    module, metric_key = _require_identity(row)
    priority = assign_context_priority(row, excluded=False)
    trigger = _str_or_none(row.get("trigger_eligibility"))
    return EvidenceCard(
        module=module,
        module_display_zh=_module_display(module),
        metric_key=metric_key,
        display_name=_str(row.get("display_name") or metric_key),
        value_text=_str(row.get("value_text") or _format_value(row.get("value"))),
        status=_str(row.get("status") or "unknown"),
        status_display_zh=_status_display(row.get("status")),
        source_badge=_str(row.get("source_badge") or "unknown"),
        source_badge_display_zh=_source_badge_display(row.get("source_badge")),
        freshness_status=_str(row.get("freshness_status") or "unknown"),
        freshness_display_zh=_freshness_display(row.get("freshness_status")),
        observation_date=_str_or_none(row.get("observation_date")),
        interpretation_hint=_str_or_none(row.get("interpretation_hint")),
        interpretation_boundary=_str_or_none(row.get("interpretation_boundary")),
        trigger_eligibility=trigger,
        trigger_eligibility_display_zh=_trigger_display(trigger),
        priority=priority,
        priority_label_zh=priority_label(priority, language="zh"),
    )


def render_model_output_card(row: Mapping[str, Any]) -> ModelOutputCard:
    """Render a model-output row into a ModelOutputCard."""

    module, metric_key = _require_identity(row)
    priority = assign_context_priority(row, excluded=False)
    contributions = row.get("component_contributions")
    bands = _extract_bands(contributions)
    missing_inputs = row.get("missing_inputs")
    missing_input_count = len(missing_inputs) if isinstance(missing_inputs, list) else 0
    return ModelOutputCard(
        module=module,
        module_display_zh=_module_display(module),
        metric_key=metric_key,
        display_name=_str(row.get("display_name") or metric_key),
        value_text=_str(row.get("value_text") or _format_value(row.get("value"))),
        status=_str(row.get("status") or "unknown"),
        status_display_zh=_status_display(row.get("status")),
        source_badge=_str(row.get("source_badge") or "unknown"),
        source_badge_display_zh=_source_badge_display(row.get("source_badge")),
        freshness_status=_str(row.get("freshness_status") or "unknown"),
        freshness_display_zh=_freshness_display(row.get("freshness_status")),
        observation_date=_str_or_none(row.get("observation_date")),
        interpretation_hint=_str_or_none(row.get("interpretation_hint")),
        interpretation_boundary=_str_or_none(row.get("interpretation_boundary")),
        support_band=bands.get("support_band"),
        severity_band=bands.get("severity_band"),
        uncertainty_band=bands.get("uncertainty_band"),
        evidence_quality_band=bands.get("evidence_quality_band"),
        conflict_band=bands.get("conflict_band"),
        missing_input_count=missing_input_count,
        priority=priority,
        priority_label_zh=priority_label(priority, language="zh"),
    )


def render_excluded_constraint_card(row: Mapping[str, Any]) -> ExcludedConstraintCard:
    """Render an excluded row into an ExcludedConstraintCard."""

    module, metric_key = _require_identity(row)
    reason = _str(
        row.get("excluded_reason")
        or row.get("missing_reason")
        or row.get("blocked_reason")
        or "excluded"
    )
    return ExcludedConstraintCard(
        module=module,
        module_display_zh=_module_display(module),
        metric_key=metric_key,
        display_name=_str(row.get("display_name") or metric_key),
        excluded_reason=reason,
        excluded_reason_display_zh=_excluded_reason_display(reason),
        status=_str(row.get("status") or "unknown"),
        status_display_zh=_status_display(row.get("status")),
        source_badge=_str(row.get("source_badge") or "unknown"),
        source_badge_display_zh=_source_badge_display(row.get("source_badge")),
        freshness_status=_str(row.get("freshness_status") or "unknown"),
        freshness_display_zh=_freshness_display(row.get("freshness_status")),
        effect_zh=_effect_for_reason(reason),
    )


def render_manifest_cards(manifest: Mapping[str, Any]) -> dict[str, list[Any]]:
    """Render all four card buckets from a manifest dict.

    Returns a dict with keys:
      - evidence_cards: list[EvidenceCard]
      - model_output_cards: list[ModelOutputCard]
      - excluded_constraint_cards: list[ExcludedConstraintCard]

    All buckets are sorted by priority then module/metric for deterministic
    output.
    """

    included_facts = _items(manifest, "included_facts")
    included_models = _items(manifest, "included_model_outputs")
    excluded_facts = _items(manifest, "excluded_facts")
    excluded_models = _items(manifest, "excluded_model_outputs")

    evidence_cards = [
        render_evidence_card(row)
        for row in sort_rows_by_priority(included_facts, excluded=False)
    ]
    model_output_cards = [
        render_model_output_card(row)
        for row in sort_rows_by_priority(included_models, excluded=False)
    ]
    excluded_cards = [
        render_excluded_constraint_card(row)
        for row in sort_rows_by_priority(
            excluded_facts + excluded_models, excluded=True
        )
    ]

    return {
        "evidence_cards": evidence_cards,
        "model_output_cards": model_output_cards,
        "excluded_constraint_cards": excluded_cards,
    }


def cards_as_text_blocks(cards: list[Any]) -> str:
    """Join card text blocks into a single string suitable for prompt context.

    Returns "" when the list is empty (callers can substitute a fallback).
    """

    return "\n\n".join(card.as_text_block() for card in cards if hasattr(card, "as_text_block"))


# ----------------------------------------------------------------------
# Internal helpers
# ----------------------------------------------------------------------


def _items(manifest: Mapping[str, Any], key: str) -> list[Mapping[str, Any]]:
    raw = manifest.get(key) or []
    return [item for item in raw if isinstance(item, Mapping)]


def _require_identity(row: Mapping[str, Any]) -> tuple[str, str]:
    module = _str(row.get("module"))
    metric_key = _str(row.get("metric_key"))
    if not module and not metric_key:
        raise ValueError("manifest row must have at least module or metric_key")
    return module or "unknown_module", metric_key or "unknown_metric"


def _str(value: Any) -> str:
    if value is None:
        return ""
    text = str(value)
    return text.strip()


def _str_or_none(value: Any) -> str | None:
    text = _str(value)
    return text or None


def _format_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    return str(value).strip()


def _module_display(module: str) -> str:
    return MODULE_DISPLAY_ZH.get(module, module or "未识别模块")


def _status_display(status: Any) -> str:
    key = _str(status)
    return STATUS_DISPLAY_ZH.get(key, key or "未知")


def _source_badge_display(badge: Any) -> str:
    key = _str(badge)
    return SOURCE_BADGE_DISPLAY_ZH.get(key, key or "未知")


def _freshness_display(freshness: Any) -> str:
    key = _str(freshness)
    return FRESHNESS_DISPLAY_ZH.get(key, key or "未知")


def _trigger_display(trigger: str | None) -> str | None:
    if not trigger:
        return None
    return TRIGGER_DISPLAY_ZH.get(trigger, trigger)


def _excluded_reason_display(reason: str) -> str:
    reason_lower = reason.lower()
    if reason_lower.startswith("status_"):
        return f"状态 {STATUS_DISPLAY_ZH.get(reason_lower.removeprefix('status_'), reason_lower.removeprefix('status_'))}"
    if reason_lower.startswith("freshness_"):
        return f"新鲜度 {FRESHNESS_DISPLAY_ZH.get(reason_lower.removeprefix('freshness_'), reason_lower.removeprefix('freshness_'))}"
    if reason_lower.startswith("source_badge_"):
        return f"来源 {SOURCE_BADGE_DISPLAY_ZH.get(reason_lower.removeprefix('source_badge_'), reason_lower.removeprefix('source_badge_'))}"
    if reason_lower == "ai_context_not_allowed":
        return "未通过 AI 上下文准入"
    return reason


def _effect_for_reason(reason: str) -> str:
    reason_lower = reason.lower()
    if "research_needed" in reason_lower:
        return "缺少官方/可信来源映射，不能作为事实进入 AI 上下文。"
    if "insufficient_history" in reason_lower:
        return "历史窗口不足以触发归一化或回看判断；不能作为支撑证据。"
    if "insufficient_evidence" in reason_lower or "limited_evidence" in reason_lower:
        return "证据不足以支撑该结论；不能作为触发依据。"
    if "missing" in reason_lower:
        return "数据缺失；不能作为事实纳入分析。"
    if "stale" in reason_lower:
        return "数据陈旧；不能作为当前事实。"
    if "not_available" in reason_lower:
        return "该指标本地不可用；保留为研究项。"
    if "proxy" in reason_lower:
        return "仅为代理值，不能升级为官方事实。"
    if "search" in reason_lower:
        return "搜索派生数据已禁用，不能进入 AI 上下文。"
    return "已从 AI 事实层中排除，不能作为触发依据。"


def _extract_bands(contributions: Any) -> dict[str, str | None]:
    """Pull canonical band names from component_contributions if present.

    Bands are explanatory metadata; they describe model output quality
    (support / severity / uncertainty / evidence_quality / conflict) without
    leaking raw payloads, holdings, or probabilities.
    """

    bands: dict[str, str | None] = {
        "support_band": None,
        "severity_band": None,
        "uncertainty_band": None,
        "evidence_quality_band": None,
        "conflict_band": None,
    }
    if not isinstance(contributions, Mapping):
        return bands
    for key in bands:
        value = contributions.get(key)
        if isinstance(value, str) and value.strip():
            bands[key] = value.strip()
    # Scenario stress nests scenarios inside contributions["scenarios"]; pull
    # bands from the first scenario when top-level fields are absent.
    if not any(bands.values()):
        scenarios = contributions.get("scenarios")
        if isinstance(scenarios, list) and scenarios:
            scenario = scenarios[0]
            if isinstance(scenario, Mapping):
                for key in bands:
                    value = scenario.get(key)
                    if isinstance(value, str) and value.strip():
                        bands[key] = value.strip()
    return bands


def _display_or_dash(raw: str | None, display: str | None) -> str:
    if not raw:
        return "—"
    if not display or display == raw:
        return raw
    return f"{raw} ({display})"


def _format_card_block(*, heading: str, lines: list[str]) -> str:
    return heading + "\n" + "\n".join(lines)
