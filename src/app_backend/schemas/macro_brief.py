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

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


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
    price: float
    change_pct: float
    as_of: str = Field(min_length=4, max_length=40)


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
    """§9 source_list — each source has either a url or a rag_doc_id.

    The 'either/or' constraint is enforced in F2-2.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str = Field(min_length=1, max_length=64)
    url: str | None = None
    rag_doc_id: str | None = None
    accessed_at: str = Field(min_length=4, max_length=40)
    title: str | None = Field(default=None, max_length=500)


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
]
