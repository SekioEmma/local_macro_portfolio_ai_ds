"""Phase F3 MacroBrief prompt construction.

Pure prompt builders only: no provider calls, no file reads, no network,
and no persistence. The agent runtime will pass these strings to the
provider adapter in F5.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any

from app_backend.schemas.macro_brief import (
    REQUIRED_BOUNDARY_KEYWORDS,
    REQUIRED_ETF_SYMBOLS,
    REQUIRED_MODULE_KEYS,
    REQUIRED_SCENARIO_KEYS,
)
from app_backend.services.agent_tool_registry import FINALIZE_TOOL_NAME


MACRO_BRIEF_RESPONSE_FORMAT: dict[str, str] = {
    "type": "json_object",
}

SECTION_SCHEMA_GUIDE = f"""
MacroBrief JSON schema summary:
1. core_conclusion: string. No probability-win language.
2. market_state: exactly {len(REQUIRED_ETF_SYMBOLS)} cards for {", ".join(REQUIRED_ETF_SYMBOLS)}.
   Each card requires symbol, price, change_pct, as_of.
3. confirmed_facts: list of fact objects with id, statement, value, unit,
   source_id, as_of.
4. judgments: list of judgment objects with claim and evidence_supports.
   Every evidence_supports id must exist in confirmed_facts.
5. module_table: exactly {len(REQUIRED_MODULE_KEYS)} rows for:
   {", ".join(REQUIRED_MODULE_KEYS)}.
   Each row requires module_key, module_name_zh, status, note.
6. risk_assessment: current_label, summary, upgrade_triggers,
   downgrade_triggers.
7. forward_indicators: exactly 5 entries. Each entry requires name,
   release_date as ISO date, relevance.
8. scenarios: exactly {len(REQUIRED_SCENARIO_KEYS)} keys:
   {", ".join(REQUIRED_SCENARIO_KEYS)}. Each scenario requires
   trigger_conditions and transmission_path.
9. source_list: each source requires id, accessed_at, and either url or
   rag_doc_id.
10. boundary_notice: must include these exact phrases:
   {", ".join(REQUIRED_BOUNDARY_KEYWORDS)}.
""".strip()


ABSOLUTE_PROHIBITIONS = """
Absolute prohibitions:
1. 禁止个股操作建议.
2. 禁止概率胜率, including any "X% probability" framing.
3. 禁止收益预测.
4. 禁止动态择时.
5. 禁止黑盒最优化.
""".strip()


ANTI_HALLUCINATION_RULES = """
Evidence and anti-hallucination rules:
1. Every numerical claim must originate from a tool call result.
2. Every numerical claim must be referenced by source_id in source_list.
3. If two tool outputs conflict, write both facts and flag the discrepancy
   in judgments. Do not silently reconcile.
4. Do not cite percentages, dates, prices, yields, spreads, or index levels
   unless they appear in a tool output.
5. Do not claim historical transmission patterns unless rag_retrieve
   returned evidence with specific dates.
6. For any post-2025 data, never guess from training knowledge.
""".strip()


ANTI_CONSERVATIVE_BIAS_RULES = """
Status and scenario discipline:
1. For every module_table row, choose the clearest status supported by
   evidence.
2. Reserve watch for genuinely mixed evidence; do not use watch as a safe
   middle by default.
3. Reserve crisis for documented systemic events only.
4. The base scenario should reflect the most evidence-supported path, not
   the middle between bullish and bearish.
5. Each scenario must have distinct, non-trivial trigger_conditions.
""".strip()


REFERENCE_BRIEF_EXAMPLE = """
Reference brief example (format only; do not reuse these synthetic facts):
{
  "core_conclusion": "示例：宏观环境处于数据敏感的观察状态。",
  "market_state": [
    {"symbol": "SPY", "price": 100.0, "change_pct": 0.1, "as_of": "2026-01-02"},
    {"symbol": "QQQ", "price": 100.0, "change_pct": 0.1, "as_of": "2026-01-02"},
    {"symbol": "SHY", "price": 100.0, "change_pct": 0.0, "as_of": "2026-01-02"},
    {"symbol": "GLD", "price": 100.0, "change_pct": -0.1, "as_of": "2026-01-02"}
  ],
  "confirmed_facts": [
    {"id": "f1", "statement": "示例工具返回利率仍在观察区间。", "value": "tool_value", "unit": null, "source_id": "s1", "as_of": "2026-01-02"}
  ],
  "judgments": [
    {"claim": "示例判断必须引用事实。", "evidence_supports": ["f1"], "claim_type": "direct_evidence"}
  ],
  "module_table": [
    {"module_key": "equity_trend", "module_name_zh": "权益趋势", "status": "watch", "note": "示例"},
    {"module_key": "rate_pressure", "module_name_zh": "利率压力", "status": "pressure", "note": "示例"},
    {"module_key": "real_yield_pressure", "module_name_zh": "真实利率压力", "status": "watch", "note": "示例"},
    {"module_key": "inflation_energy", "module_name_zh": "通胀能源", "status": "watch", "note": "示例"},
    {"module_key": "credit_pressure", "module_name_zh": "信用压力", "status": "benign", "note": "示例"},
    {"module_key": "geopolitical_risk", "module_name_zh": "地缘风险", "status": "watch", "note": "示例"}
  ],
  "risk_assessment": {"current_label": "watch", "summary": "示例", "upgrade_triggers": ["示例上行触发"], "downgrade_triggers": ["示例下行触发"]},
  "forward_indicators": [
    {"name": "CPI", "release_date": "2026-01-15", "relevance": "示例"},
    {"name": "FOMC", "release_date": "2026-01-29", "relevance": "示例"},
    {"name": "Payrolls", "release_date": "2026-02-06", "relevance": "示例"},
    {"name": "PCE", "release_date": "2026-02-27", "relevance": "示例"},
    {"name": "ISM", "release_date": "2026-02-02", "relevance": "示例"}
  ],
  "scenarios": {
    "base": {"trigger_conditions": ["示例 base"], "transmission_path": "示例", "note": null},
    "bullish": {"trigger_conditions": ["示例 bullish"], "transmission_path": "示例", "note": null},
    "bearish": {"trigger_conditions": ["示例 bearish"], "transmission_path": "示例", "note": null},
    "systemic": {"trigger_conditions": ["示例 systemic"], "transmission_path": "示例", "note": null}
  },
  "source_list": [
    {"id": "s1", "url": "https://fred.stlouisfed.org/series/example", "rag_doc_id": null, "accessed_at": "2026-01-02", "title": "Synthetic example"}
  ],
  "boundary_notice": "非个股操作 / 非概率胜率 / 非收益预测 / 非动态择时 / 非黑盒最优化"
}
""".strip()


@dataclass(frozen=True)
class MacroBriefPrompt:
    """Prompt package consumed by the future agent/provider layer."""

    system_prompt: str
    user_prompt: str
    response_format: dict[str, str]

    def messages(self) -> list[dict[str, str]]:
        return [
            {"role": "system", "content": self.system_prompt},
            {"role": "user", "content": self.user_prompt},
        ]


def build_macro_brief_prompt(
    *,
    user_question: str,
    current_date: date,
    tool_names: list[str],
    instrument_context: str | None = None,
) -> MacroBriefPrompt:
    """Build the F3-1 MacroBrief prompt package."""
    question = _normalize_user_question(user_question)
    tools = _format_tool_names(tool_names)
    context = _format_instrument_context(instrument_context)

    system_prompt = "\n\n".join(
        part
        for part in (
            "You are a senior macro strategist producing one structured MacroBrief.",
            f"Today's date is {current_date.isoformat()}; treat it as now for all analysis and tool-call date ranges.",
            f"You have access to these tools: {tools}.",
            context,
            SECTION_SCHEMA_GUIDE,
            ABSOLUTE_PROHIBITIONS,
            ANTI_HALLUCINATION_RULES,
            ANTI_CONSERVATIVE_BIAS_RULES,
            REFERENCE_BRIEF_EXAMPLE,
            (
                f"Your output must be valid JSON matching the MacroBrief schema. "
                f"You must call {FINALIZE_TOOL_NAME} to terminate; this is the only exit."
            ),
        )
        if part
    )
    user_prompt = "\n".join(
        [
            "Research question:",
            question,
            "",
            "Produce the MacroBrief only after the available tools provide enough evidence.",
        ]
    )
    return MacroBriefPrompt(
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        response_format=dict(MACRO_BRIEF_RESPONSE_FORMAT),
    )


def _normalize_user_question(user_question: str) -> str:
    if not isinstance(user_question, str) or not user_question.strip():
        raise ValueError("user_question must be a non-empty string")
    return " ".join(user_question.strip().split())


def _format_tool_names(tool_names: list[str]) -> str:
    if not isinstance(tool_names, list) or not tool_names:
        raise ValueError("tool_names must be a non-empty list")
    normalized: list[str] = []
    for name in tool_names:
        if not isinstance(name, str) or not name.strip():
            raise ValueError("tool_names must contain non-empty strings")
        normalized.append(name.strip())
    return ", ".join(sorted(dict.fromkeys(normalized)))


def _format_instrument_context(instrument_context: str | None) -> str:
    if instrument_context is None or not instrument_context.strip():
        return ""
    return "Instrument context:\n" + instrument_context.strip()


__all__ = [
    "ABSOLUTE_PROHIBITIONS",
    "ANTI_CONSERVATIVE_BIAS_RULES",
    "ANTI_HALLUCINATION_RULES",
    "MACRO_BRIEF_RESPONSE_FORMAT",
    "MacroBriefPrompt",
    "REFERENCE_BRIEF_EXAMPLE",
    "SECTION_SCHEMA_GUIDE",
    "build_macro_brief_prompt",
]
