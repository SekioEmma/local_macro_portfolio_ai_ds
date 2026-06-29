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
    "MACRO_BRIEF_RESPONSE_FORMAT",
    "MacroBriefPrompt",
    "SECTION_SCHEMA_GUIDE",
    "build_macro_brief_prompt",
]
