"""Phase F3 MacroBrief prompt construction.

Pure prompt builders only: no provider calls, no file reads, no network,
and no persistence. The agent runtime will pass these strings to the
provider adapter in F5.
"""
from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
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
_LOCAL_TOOL_ORDER = (
    "dashboard_query",
    "evidence_lookup",
    "quote_etf",
    "treasury_curve",
    "quote_dxy",
    "calendar_lookup",
    "portfolio_overlay",
    "rag_retrieve",
)

SECTION_SCHEMA_GUIDE = f"""
MacroBrief JSON schema summary:
1. core_conclusion: string. No probability-win language.
2. market_state: exactly {len(REQUIRED_ETF_SYMBOLS)} cards for {", ".join(REQUIRED_ETF_SYMBOLS)}.
   Each card requires symbol, price, change_pct, as_of.
3. confirmed_facts: list of fact objects with id, statement, value, unit,
   source_id, evidence_ids, claim_status, as_of.
   evidence_ids must reference run evidence records. claim_status is one of
   observed, reported, unavailable.
4. judgments: list of judgment objects with claim, evidence_supports,
   evidence_ids, and temporal_scope.
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
2. Every numerical claim must be referenced by source_id in source_list and
   by evidence_ids in the current run evidence ledger.
3. Mark facts from official or directly observed tool outputs as observed.
   Mark facts from public reporting or institutional interpretation as
   reported. Use unavailable only when the value is absent.
4. If two tool outputs conflict, write both facts and flag the discrepancy
   in judgments. Do not silently reconcile.
5. Do not cite percentages, dates, prices, yields, spreads, or index levels
   unless they appear in a tool output.
6. Do not claim historical transmission patterns unless an enabled evidence
   retrieval tool returned evidence with specific dates.
7. For any post-2025 data, never guess from training knowledge.
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
    {"id": "f1", "statement": "示例工具返回利率仍在观察区间。", "value": "tool_value", "unit": null, "source_id": "s1", "evidence_ids": ["ev_example"], "claim_status": "observed", "as_of": "2026-01-02"}
  ],
  "judgments": [
    {"claim": "示例判断必须引用事实。", "evidence_supports": ["f1"], "evidence_ids": ["ev_example"], "claim_type": "direct_evidence", "temporal_scope": "current_run"}
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


REACT_GUIDANCE = f"""
ReAct operating rules:
1. Use only tools listed in this prompt; never request unavailable tools.
2. When information is insufficient, call search_tavily or rag_retrieve;
   宁可搜，不要猜.
3. Prefer local tools first: dashboard_query, evidence_lookup, quote_etf,
   treasury_curve, quote_dxy, calendar_lookup, portfolio_overlay, and
   rag_retrieve before external search.
4. Use search_tavily only for current public information not answered by
   local data or RAG.
5. Facts must come before judgments. Every judgment must cite
   confirmed_facts ids.
6. When the brief is complete, call {FINALIZE_TOOL_NAME}; do not finish
   with plain text.
""".strip()


HOLDINGS_NOT_INCLUDED_NOTICE = (
    "User holdings context: not included for this run. Do not infer "
    "account, position, transaction, or amount details."
)

_FORBIDDEN_HOLDINGS_KEYS = (
    "transaction",
    "order_book",
    "cost_basis",
    "p&l",
    "profit_loss",
    "raw_provider",
)


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
    include_holdings: bool = False,
    holdings_snapshot: Mapping[str, Any] | None = None,
) -> MacroBriefPrompt:
    """Build the F3-1 MacroBrief prompt package."""
    question = _normalize_user_question(user_question)
    tools = _format_tool_names(tool_names)
    context = _format_instrument_context(instrument_context)
    holdings_context = _format_holdings_context(
        include_holdings=include_holdings,
        holdings_snapshot=holdings_snapshot,
    )

    system_prompt = "\n\n".join(
        part
        for part in (
            "You are a senior macro strategist producing one structured MacroBrief.",
            f"Today's date is {current_date.isoformat()}; treat it as now for all analysis and tool-call date ranges.",
            f"You have access to these tools: {tools}.",
            context,
            holdings_context,
            SECTION_SCHEMA_GUIDE,
            ABSOLUTE_PROHIBITIONS,
            ANTI_HALLUCINATION_RULES,
            ANTI_CONSERVATIVE_BIAS_RULES,
            REFERENCE_BRIEF_EXAMPLE,
            _build_react_guidance(tool_names),
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
    return ", ".join(sorted(_normalized_tool_names(tool_names)))


def _build_react_guidance(tool_names: list[str]) -> str:
    enabled = set(_normalized_tool_names(tool_names))
    lines = [
        "ReAct operating rules:",
        "1. Use only tools listed in this prompt; never request unavailable tools.",
    ]
    index = 2
    information_tools = [
        name for name in ("search_tavily", "rag_retrieve") if name in enabled
    ]
    if information_tools:
        lines.append(
            f"{index}. When information is insufficient, call "
            f"{_format_english_list(information_tools)}; 宁可搜，不要猜."
        )
    else:
        lines.append(
            f"{index}. If enabled tools cannot support a value, mark it unavailable; "
            "do not guess or ask for disabled tools."
        )
    index += 1

    local_tools = [name for name in _LOCAL_TOOL_ORDER if name in enabled]
    if local_tools:
        lines.append(
            f"{index}. Prefer enabled local tools first: "
            f"{_format_english_list(local_tools)}."
        )
        index += 1
    if "search_tavily" in enabled:
        lines.append(
            f"{index}. Use search_tavily only for current public information not "
            "answered by local data or RAG."
        )
        index += 1
    lines.append(
        f"{index}. Facts must come before judgments. Every judgment must cite "
        "confirmed_facts ids."
    )
    index += 1
    lines.append(
        f"{index}. When the brief is complete, call {FINALIZE_TOOL_NAME}; "
        "do not finish with plain text."
    )
    return "\n".join(lines)


def _normalized_tool_names(tool_names: list[str]) -> list[str]:
    if not isinstance(tool_names, list) or not tool_names:
        raise ValueError("tool_names must be a non-empty list")
    normalized: list[str] = []
    for name in tool_names:
        if not isinstance(name, str) or not name.strip():
            raise ValueError("tool_names must contain non-empty strings")
        normalized.append(name.strip())
    return list(dict.fromkeys(normalized))


def _format_english_list(items: list[str]) -> str:
    if not items:
        return ""
    if len(items) == 1:
        return items[0]
    return ", ".join(items[:-1]) + f", and {items[-1]}"


def _format_instrument_context(instrument_context: str | None) -> str:
    if instrument_context is None or not instrument_context.strip():
        return ""
    return "Instrument context:\n" + instrument_context.strip()


def _format_holdings_context(
    *,
    include_holdings: bool,
    holdings_snapshot: Mapping[str, Any] | None,
) -> str:
    if not include_holdings:
        return HOLDINGS_NOT_INCLUDED_NOTICE
    if not isinstance(holdings_snapshot, Mapping) or not holdings_snapshot:
        raise ValueError("holdings_snapshot is required when include_holdings is true")
    _reject_forbidden_holdings_keys(holdings_snapshot)
    serialized = json.dumps(holdings_snapshot, ensure_ascii=False, sort_keys=True)
    return (
        "User holdings context (explicitly approved for this run only; "
        "server-side injection channel):\n"
        f"{serialized}"
    )


def _reject_forbidden_holdings_keys(value: Any) -> None:
    if isinstance(value, Mapping):
        for key, item in value.items():
            lowered = str(key).lower()
            if any(forbidden in lowered for forbidden in _FORBIDDEN_HOLDINGS_KEYS):
                raise ValueError(f"forbidden holdings field: {key}")
            _reject_forbidden_holdings_keys(item)
    elif isinstance(value, Sequence) and not isinstance(value, str | bytes | bytearray):
        for item in value:
            _reject_forbidden_holdings_keys(item)


__all__ = [
    "ABSOLUTE_PROHIBITIONS",
    "ANTI_CONSERVATIVE_BIAS_RULES",
    "ANTI_HALLUCINATION_RULES",
    "HOLDINGS_NOT_INCLUDED_NOTICE",
    "MACRO_BRIEF_RESPONSE_FORMAT",
    "MacroBriefPrompt",
    "REFERENCE_BRIEF_EXAMPLE",
    "REACT_GUIDANCE",
    "SECTION_SCHEMA_GUIDE",
    "build_macro_brief_prompt",
]
