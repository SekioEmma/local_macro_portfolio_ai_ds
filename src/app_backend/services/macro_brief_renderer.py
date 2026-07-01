"""Deterministic Chinese Markdown renderer for validated MacroBrief objects."""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict

from app_backend.schemas.macro_brief import MacroBrief
from app_backend.services.agent_runtime import AgentRuntimeEvent
from app_backend.services.macro_brief_sources import (
    SourceVisibilityMode,
    build_macro_brief_source_references,
    render_macro_brief_sources_markdown,
)


class MacroBriefRenderResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    visibility_mode: SourceVisibilityMode
    markdown: str
    source_markdown: str


MACRO_BRIEF_PRODUCT_STATUS_LABELS = (
    "研究辅助输出",
    "非自动投资决策",
    "需要用户审阅",
)


def render_macro_brief_markdown(
    brief: MacroBrief,
    *,
    visibility_mode: SourceVisibilityMode = "public",
    runtime_events: list[AgentRuntimeEvent] | None = None,
) -> MacroBriefRenderResult:
    """Render a parsed MacroBrief without introducing new facts or numbers."""
    references = build_macro_brief_source_references(
        brief,
        runtime_events=runtime_events,
    )
    source_markdown = render_macro_brief_sources_markdown(
        references,
        visibility_mode=visibility_mode,
    )
    sections = [
        _product_status_notice(),
        _core_conclusion(brief),
        _temporal_envelope(brief),
        _market_state(brief),
        _confirmed_facts(brief),
        _judgments(brief),
        _module_table(brief),
        _risk_assessment(brief),
        _forward_indicators(brief),
        _scenarios(brief),
        "## 信息来源\n\n" + source_markdown,
        "## 边界提示\n\n" + brief.boundary_notice,
    ]
    return MacroBriefRenderResult(
        visibility_mode=visibility_mode,
        markdown="\n\n".join(sections),
        source_markdown=source_markdown,
    )


def _product_status_notice() -> str:
    return "## 输出定位\n\n" + " / ".join(MACRO_BRIEF_PRODUCT_STATUS_LABELS)


def _core_conclusion(brief: MacroBrief) -> str:
    return "## 核心结论\n\n" + brief.core_conclusion


def macro_brief_temporal_envelope_payload(brief: MacroBrief) -> dict[str, Any]:
    return {
        "report_generated_at": brief.report_generated_at,
        "market_data_cutoff": brief.market_data_cutoff,
        "policy_data_cutoff": brief.policy_data_cutoff,
        "macro_data_cutoff": brief.macro_data_cutoff,
        "public_news_cutoff": brief.public_news_cutoff,
        "max_market_data_age_working_days_approx": brief.max_market_data_age_trading_days,
        "asynchronous_inputs": brief.asynchronous_inputs,
        "temporal_alignment_note": brief.temporal_alignment_note,
    }


def _temporal_envelope(brief: MacroBrief) -> str:
    payload = macro_brief_temporal_envelope_payload(brief)
    labels = {
        "report_generated_at": "报告生成时间",
        "market_data_cutoff": "市场数据截止",
        "policy_data_cutoff": "政策数据截止",
        "macro_data_cutoff": "宏观数据截止",
        "public_news_cutoff": "公开新闻截止",
        "max_market_data_age_working_days_approx": "市场数据工作日跨度近似值",
        "asynchronous_inputs": "输入时间错配",
        "temporal_alignment_note": "时间对齐提示",
    }
    lines = [
        "## 时间对齐",
        "",
        "| 字段 | 值 |",
        "| --- | --- |",
    ]
    for key, label in labels.items():
        value = payload[key]
        if value is None:
            rendered = "unavailable"
        elif isinstance(value, bool):
            rendered = "true" if value else "false"
        else:
            rendered = str(value)
        lines.append(f"| {label} | {rendered} |")
    return "\n".join(lines)


def _market_state(brief: MacroBrief) -> str:
    lines = [
        "## 市场快照",
        "",
        "| 资产 | 最新价 | 变化 | 日期 |",
        "| --- | ---: | ---: | --- |",
    ]
    for card in brief.market_state:
        price = "unavailable" if card.price is None else f"{card.price:.2f}"
        change = "unavailable" if card.change_pct is None else f"{card.change_pct:+.2f}%"
        as_of = "unavailable" if card.as_of is None else card.as_of
        lines.append(f"| {card.symbol} | {price} | {change} | {as_of} |")
    return "\n".join(lines)


def _confirmed_facts(brief: MacroBrief) -> str:
    lines = ["## 已确认事实", ""]
    for fact in brief.confirmed_facts:
        value = "" if fact.value is None else f"；值={fact.value}"
        unit = "" if fact.unit is None else f"{fact.unit}"
        as_of = "" if fact.as_of is None else f"；截至={fact.as_of}"
        lines.append(f"- [{fact.id}] {fact.statement}{value}{unit}{as_of}；来源={fact.source_id}")
    return "\n".join(lines)


def _judgments(brief: MacroBrief) -> str:
    lines = ["## 判断", ""]
    for judgment in brief.judgments:
        claim_type = "" if judgment.claim_type is None else f"；claim_type={judgment.claim_type}"
        lines.append(
            f"- {judgment.claim}（证据：{', '.join(judgment.evidence_supports)}{claim_type}）"
        )
    return "\n".join(lines)


def _module_table(brief: MacroBrief) -> str:
    lines = [
        "## 当前市场状态表",
        "",
        "| 模块 | 状态 | 依据 |",
        "| --- | --- | --- |",
    ]
    for row in brief.module_table:
        note = row.note or ""
        lines.append(f"| {row.module_name_zh} | `{row.status}` | {note} |")
    return "\n".join(lines)


def _risk_assessment(brief: MacroBrief) -> str:
    risk = brief.risk_assessment
    return "\n".join(
        [
            "## 风险评估",
            "",
            f"当前标签：`{risk.current_label}`",
            "",
            risk.summary,
            "",
            "升级触发：",
            *[f"- {item}" for item in risk.upgrade_triggers],
            "",
            "降级触发：",
            *[f"- {item}" for item in risk.downgrade_triggers],
        ]
    )


def _forward_indicators(brief: MacroBrief) -> str:
    lines = [
        "## 后续验证点",
        "",
        "| 指标 | 发布日期 | 相关性 |",
        "| --- | --- | --- |",
    ]
    for indicator in brief.forward_indicators:
        lines.append(
            f"| {indicator.name} | {indicator.release_date} | {indicator.relevance} |"
        )
    return "\n".join(lines)


def _scenarios(brief: MacroBrief) -> str:
    lines = ["## 情景路径", ""]
    for name, scenario in brief.scenarios.items():
        lines.extend(
            [
                f"### {name}",
                "",
                f"- 触发条件：{'; '.join(scenario.trigger_conditions)}",
                f"- 传导路径：{scenario.transmission_path}",
            ]
        )
        if scenario.note:
            lines.append(f"- 备注：{scenario.note}")
        lines.append("")
    return "\n".join(lines).strip()


__all__ = [
    "MACRO_BRIEF_PRODUCT_STATUS_LABELS",
    "MacroBriefRenderResult",
    "macro_brief_temporal_envelope_payload",
    "render_macro_brief_markdown",
]
