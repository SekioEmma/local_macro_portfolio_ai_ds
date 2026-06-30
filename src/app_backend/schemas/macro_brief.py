"""Phase F2 MacroBrief 10-section output schema.

The MacroBrief is the strongly-typed contract between the Phase F agent
runtime and the frontend. Each of the 10 sections has a fixed shape that
the LLM MUST emit to terminate the agent loop (via
``finalize_macro_brief``).

This module ships F2-1: the Pydantic models with Literal-type constraints
ONLY. Custom cross-section validators (exactly 6 module rows, exactly 4
scenario keys, 5 boundary keywords, judgment-fact cross-reference, etc.)
are added in F2-2. The runtime parser wrapper is F2-3.

All models are frozen + extra="forbid" so the LLM cannot smuggle extra
fields and downstream consumers cannot mutate a parsed brief.
"""
from __future__ import annotations

import json
import re
from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


# ---------------------------------------------------------------------------
# Literal enumerations (LLM must use exactly these tokens)
# ---------------------------------------------------------------------------

ETFSymbol = Literal["SPY", "QQQ", "SHY", "GLD"]

# Six fixed module keys; cross-section validator in F2-2 will enforce all six
# present in module_table exactly once.
ModuleKey = Literal[
    "equity_trend",
    "rate_pressure",
    "real_yield_pressure",
    "inflation_energy",
    "credit_pressure",
    "geopolitical_risk",
]

ModuleStatus = Literal["benign", "watch", "pressure", "stress", "crisis"]

# Four fixed scenario keys; cross-section validator in F2-2 will enforce all
# four present in `scenarios` exactly once.
ScenarioKey = Literal["base", "bullish", "bearish", "systemic"]

# Optional metadata on each judgment indicating its evidentiary grade. The
# F3 prompt forces the LLM to tag every judgment; F2 keeps it optional so
# preliminary briefs (e.g. partial-fill retries) can still serialize.
ClaimType = Literal[
    "direct_evidence",
    "cross_evidence_inference",
    "interpretive",
    "watchlist",
]

# Optional metadata on numeric thresholds inside `risk_assessment` triggers
# and `forward_indicators[*].relevance`. F3 prompt will require LLMs to tag
# any numeric threshold; F2 keeps it optional.
ThresholdSource = Literal[
    "project_band",
    "historical_percentile",
    "heuristic_watchlist",
]


# Constants referenced by F2-2 validators (kept here so both the schema and
# the parser can import a single source of truth).
REQUIRED_BOUNDARY_KEYWORDS: tuple[str, ...] = (
    "非个股操作",
    "非概率胜率",
    "非收益预测",
    "非动态择时",
    "非黑盒最优化",
)

REQUIRED_MODULE_KEYS: tuple[str, ...] = (
    "equity_trend",
    "rate_pressure",
    "real_yield_pressure",
    "inflation_energy",
    "credit_pressure",
    "geopolitical_risk",
)

REQUIRED_SCENARIO_KEYS: tuple[str, ...] = (
    "base",
    "bullish",
    "bearish",
    "systemic",
)

REQUIRED_ETF_SYMBOLS: tuple[str, ...] = ("SPY", "QQQ", "SHY", "GLD")

FORWARD_INDICATOR_COUNT: int = 5


# ---------------------------------------------------------------------------
# Section models
# ---------------------------------------------------------------------------


class ETFStateCard(BaseModel):
    """§2 market_state — one card per ETF in REQUIRED_ETF_SYMBOLS."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    symbol: ETFSymbol
    price: float | None = None
    change_pct: float | None = None
    as_of: str | None = Field(default=None, min_length=4, max_length=40)


class ConfirmedFact(BaseModel):
    """§3 confirmed_facts — each fact must carry an id and a source_id.

    The id is referenced by Judgment.evidence_supports.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str = Field(min_length=1, max_length=64)
    statement: str = Field(min_length=1, max_length=1000)
    value: str | float | int | None = None
    unit: str | None = None
    source_id: str = Field(min_length=1, max_length=64)
    as_of: str | None = None


class Judgment(BaseModel):
    """§4 judgments — each claim references one or more confirmed_fact ids."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    claim: str = Field(min_length=1, max_length=2000)
    evidence_supports: list[str] = Field(min_length=1)
    claim_type: ClaimType | None = None


class ModuleRow(BaseModel):
    """§5 module_table — one row per module_key in REQUIRED_MODULE_KEYS."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    module_key: ModuleKey
    module_name_zh: str = Field(min_length=1, max_length=64)
    status: ModuleStatus
    note: str | None = Field(default=None, max_length=1000)


class RiskAssessment(BaseModel):
    """§6 risk_assessment — current label plus upgrade/downgrade triggers.

    Decision 5 (2026-06-29) added `upgrade_triggers` / `downgrade_triggers`
    so the brief explains what would push risk to a different label, not
    just what the current label is.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    current_label: str = Field(min_length=1, max_length=64)
    summary: str = Field(min_length=1, max_length=2000)
    upgrade_triggers: list[str] = Field(min_length=1)
    downgrade_triggers: list[str] = Field(min_length=1)


class ForwardIndicator(BaseModel):
    """§7 forward_indicators — exactly FORWARD_INDICATOR_COUNT entries.

    release_date format and the section length are enforced in F2-2.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str = Field(min_length=1, max_length=128)
    release_date: str = Field(min_length=8, max_length=20)
    relevance: str = Field(min_length=1, max_length=1000)


class ScenarioBlock(BaseModel):
    """§8 scenarios — one block per key in REQUIRED_SCENARIO_KEYS."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    trigger_conditions: list[str] = Field(min_length=1)
    transmission_path: str = Field(min_length=1, max_length=2000)
    note: str | None = Field(default=None, max_length=1000)


class SourceItem(BaseModel):
    """§9 source_list — each source has a url, rag_doc_id, or local title.

    The 'either/or' constraint is enforced by ``MacroBrief`` in F2-2.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str = Field(min_length=1, max_length=64)
    url: str | None = None
    rag_doc_id: str | None = None
    accessed_at: str = Field(min_length=4, max_length=40)
    title: str | None = Field(default=None, max_length=500)


# Probability-language fragments forbidden in §1 core_conclusion. The plan
# §5 row 1 disallows "X% 概率" patterns; we also reject the wider English
# equivalents so the agent cannot smuggle probability talk in either lang.
_PROBABILITY_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\d+\s*%\s*的?\s*概率"),
    re.compile(r"概率\s*[:：是为]\s*\d+\s*%"),
    re.compile(r"(?i)\d+\s*%\s*probability"),
    re.compile(r"(?i)probability\s+of\s+\d+\s*%"),
)

# Sentinel that lets the F2-3 parser distinguish a multi-finding payload
# raised by the cross-section validator from an unrelated ValueError msg.
_FINDINGS_SENTINEL = "macro_brief_findings_v1::"


def _encode_findings(findings: list[str]) -> str:
    return _FINDINGS_SENTINEL + json.dumps(findings, ensure_ascii=False)


def decode_findings(message: str) -> list[str] | None:
    """Extract the F2-2 findings list from a ValueError / ValidationError msg.

    Returns ``None`` if the message was not produced by ``MacroBrief``'s
    cross-section validator. Used by macro_brief_parser (F2-3).
    """
    if not isinstance(message, str):
        return None
    idx = message.find(_FINDINGS_SENTINEL)
    if idx < 0:
        return None
    tail = message[idx + len(_FINDINGS_SENTINEL):]
    try:
        decoded = json.loads(tail)
    except json.JSONDecodeError:
        return None
    if not isinstance(decoded, list):
        return None
    return [str(item) for item in decoded]


class MacroBrief(BaseModel):
    """The 10-section MacroBrief contract.

    F2-1 ships the bare structural schema; F2-2 adds cross-section
    validators (counts, key sets, keyword presence, evidence cross-ref).
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    # §1 core_conclusion
    core_conclusion: str = Field(min_length=1, max_length=4000)
    # §2 market_state
    market_state: list[ETFStateCard]
    # §3 confirmed_facts
    confirmed_facts: list[ConfirmedFact]
    # §4 judgments
    judgments: list[Judgment]
    # §5 module_table
    module_table: list[ModuleRow]
    # §6 risk_assessment
    risk_assessment: RiskAssessment
    # §7 forward_indicators
    forward_indicators: list[ForwardIndicator]
    # §8 scenarios
    scenarios: dict[ScenarioKey, ScenarioBlock]
    # §9 source_list
    source_list: list[SourceItem]
    # §10 boundary_notice
    boundary_notice: str = Field(min_length=1, max_length=4000)

    @model_validator(mode="after")
    def _validate_cross_section(self) -> "MacroBrief":
        findings: list[str] = []
        findings.extend(_check_market_state(self.market_state))
        findings.extend(_check_module_table(self.module_table))
        findings.extend(_check_scenarios(self.scenarios))
        findings.extend(_check_forward_indicators(self.forward_indicators))
        findings.extend(_check_boundary_notice(self.boundary_notice))
        findings.extend(_check_core_conclusion(self.core_conclusion))
        findings.extend(_check_facts_and_sources(self.confirmed_facts, self.source_list))
        findings.extend(_check_judgment_evidence(self.judgments, self.confirmed_facts))
        if findings:
            raise ValueError(_encode_findings(findings))
        return self


# ---------------------------------------------------------------------------
# Cross-section validators (each returns a list of finding codes; empty
# list means the section is valid in isolation)
# ---------------------------------------------------------------------------


def _check_market_state(cards: list[ETFStateCard]) -> list[str]:
    seen: set[str] = set()
    findings: list[str] = []
    for card in cards:
        if card.symbol in seen:
            findings.append(f"market_state.duplicate_etf:{card.symbol}")
        seen.add(card.symbol)
    missing = [s for s in REQUIRED_ETF_SYMBOLS if s not in seen]
    if missing:
        findings.append(
            f"market_state.missing_etfs:{','.join(missing)}"
        )
    if len(cards) != len(REQUIRED_ETF_SYMBOLS):
        findings.append(
            f"market_state.expected_{len(REQUIRED_ETF_SYMBOLS)}_cards_got_{len(cards)}"
        )
    return findings


def _check_module_table(rows: list[ModuleRow]) -> list[str]:
    if len(rows) != len(REQUIRED_MODULE_KEYS):
        # We still want to report missing keys below for actionable feedback.
        pass
    seen: set[str] = set()
    findings: list[str] = []
    for row in rows:
        if row.module_key in seen:
            findings.append(f"module_table.duplicate_module_key:{row.module_key}")
        seen.add(row.module_key)
    missing = [k for k in REQUIRED_MODULE_KEYS if k not in seen]
    if missing:
        findings.append(f"module_table.missing_module_keys:{','.join(missing)}")
    if len(rows) != len(REQUIRED_MODULE_KEYS):
        findings.append(
            f"module_table.expected_{len(REQUIRED_MODULE_KEYS)}_rows_got_{len(rows)}"
        )
    return findings


def _check_scenarios(scenarios: dict[str, ScenarioBlock]) -> list[str]:
    findings: list[str] = []
    present = set(scenarios.keys())
    missing = [k for k in REQUIRED_SCENARIO_KEYS if k not in present]
    if missing:
        findings.append(f"scenarios.missing_keys:{','.join(missing)}")
    if len(scenarios) != len(REQUIRED_SCENARIO_KEYS):
        findings.append(
            f"scenarios.expected_{len(REQUIRED_SCENARIO_KEYS)}_keys_got_{len(scenarios)}"
        )
    return findings


def _check_forward_indicators(indicators: list[ForwardIndicator]) -> list[str]:
    findings: list[str] = []
    if len(indicators) != FORWARD_INDICATOR_COUNT:
        findings.append(
            f"forward_indicators.expected_{FORWARD_INDICATOR_COUNT}_got_{len(indicators)}"
        )
    for i, indicator in enumerate(indicators):
        if not _is_iso_date(indicator.release_date):
            findings.append(
                f"forward_indicators[{i}].release_date_not_iso_date:{indicator.release_date}"
            )
    return findings


def _is_iso_date(value: str) -> bool:
    try:
        date.fromisoformat(value)
        return True
    except ValueError:
        return False


def _check_boundary_notice(text: str) -> list[str]:
    missing = [kw for kw in REQUIRED_BOUNDARY_KEYWORDS if kw not in text]
    if missing:
        return [f"boundary_notice.missing_keywords:{','.join(missing)}"]
    return []


def _check_core_conclusion(text: str) -> list[str]:
    for pattern in _PROBABILITY_PATTERNS:
        match = pattern.search(text)
        if match:
            return [f"core_conclusion.contains_probability_language:{match.group(0)}"]
    return []


def _check_facts_and_sources(
    facts: list[ConfirmedFact],
    sources: list[SourceItem],
) -> list[str]:
    findings: list[str] = []
    # Source id uniqueness and url/rag_doc_id presence
    source_ids: set[str] = set()
    for source in sources:
        if source.id in source_ids:
            findings.append(f"source_list.duplicate_source_id:{source.id}")
        source_ids.add(source.id)
        has_url = bool(source.url and source.url.strip())
        has_rag = bool(source.rag_doc_id and source.rag_doc_id.strip())
        has_title = bool(source.title and source.title.strip())
        if not (has_url or has_rag or has_title):
            findings.append(f"source_list[{source.id}].missing_url_or_rag_doc_id")
    # Fact id uniqueness
    fact_ids: set[str] = set()
    for fact in facts:
        if fact.id in fact_ids:
            findings.append(f"confirmed_facts.duplicate_id:{fact.id}")
        fact_ids.add(fact.id)
        if fact.source_id not in source_ids:
            findings.append(
                f"confirmed_facts[{fact.id}].unknown_source_id:{fact.source_id}"
            )
    return findings


def _check_judgment_evidence(
    judgments: list[Judgment],
    facts: list[ConfirmedFact],
) -> list[str]:
    fact_ids = {fact.id for fact in facts}
    findings: list[str] = []
    for i, judgment in enumerate(judgments):
        unknown = [fid for fid in judgment.evidence_supports if fid not in fact_ids]
        if unknown:
            findings.append(
                f"judgments[{i}].unknown_evidence_ids:{','.join(unknown)}"
            )
    return findings


__all__ = [
    "ClaimType",
    "ConfirmedFact",
    "ETFStateCard",
    "ETFSymbol",
    "FORWARD_INDICATOR_COUNT",
    "ForwardIndicator",
    "Judgment",
    "MacroBrief",
    "ModuleKey",
    "ModuleRow",
    "ModuleStatus",
    "REQUIRED_BOUNDARY_KEYWORDS",
    "REQUIRED_ETF_SYMBOLS",
    "REQUIRED_MODULE_KEYS",
    "REQUIRED_SCENARIO_KEYS",
    "RiskAssessment",
    "ScenarioBlock",
    "ScenarioKey",
    "SourceItem",
    "ThresholdSource",
    "decode_findings",
]
