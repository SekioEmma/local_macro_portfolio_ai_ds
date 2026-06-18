"""Context priority ranking for AI Context Manifest consumption.

Assigns a 1-4 priority band to each manifest row so downstream renderers and
prompt builders can present evidence in a fixed financial reasoning order
(macro state -> credit/funding/rates -> inflation/growth/equity -> proxy/
explanation/portfolio -> excluded constraints).

This is a deterministic ranking layer. It does not modify rows, does not call
external models, does not consume holdings, and does not produce any
allocation, probability, or forecast output.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any


PRIORITY_CORE_MACRO_STATE = 1
PRIORITY_INFLATION_GROWTH_EQUITY = 2
PRIORITY_PROXY_EXPLANATION_PORTFOLIO = 3
PRIORITY_EXCLUDED_CONSTRAINT = 4

PRIORITY_LABELS_EN = {
    PRIORITY_CORE_MACRO_STATE: "P1 core macro state",
    PRIORITY_INFLATION_GROWTH_EQUITY: "P2 inflation / growth / equity",
    PRIORITY_PROXY_EXPLANATION_PORTFOLIO: "P3 proxy / explanation / portfolio overlay",
    PRIORITY_EXCLUDED_CONSTRAINT: "P4 excluded / missing constraint",
}

PRIORITY_LABELS_ZH = {
    PRIORITY_CORE_MACRO_STATE: "P1 核心宏观状态",
    PRIORITY_INFLATION_GROWTH_EQUITY: "P2 通胀 / 增长 / 权益",
    PRIORITY_PROXY_EXPLANATION_PORTFOLIO: "P3 代理 / 解释层 / 组合暴露",
    PRIORITY_EXCLUDED_CONSTRAINT: "P4 已排除 / 缺失约束",
}

_MODULE_PRIORITY: dict[str, int] = {
    # P1 - current core macro state
    "macro_regime_review": PRIORITY_CORE_MACRO_STATE,
    "financial_stress_composite": PRIORITY_CORE_MACRO_STATE,
    "pullback_systemic_risk_checklist": PRIORITY_CORE_MACRO_STATE,
    "credit_stress": PRIORITY_CORE_MACRO_STATE,
    "liquidity_funding_stress": PRIORITY_CORE_MACRO_STATE,
    "rate_pressure": PRIORITY_CORE_MACRO_STATE,
    "real_yield_pressure": PRIORITY_CORE_MACRO_STATE,
    # P2 - inflation, growth, equity trend, derived stress, historical bands
    "inflation_energy_pressure": PRIORITY_INFLATION_GROWTH_EQUITY,
    "growth_inflation_macro_pack": PRIORITY_INFLATION_GROWTH_EQUITY,
    "equity_trend": PRIORITY_INFLATION_GROWTH_EQUITY,
    "market_stress_derived": PRIORITY_INFLATION_GROWTH_EQUITY,
    "historical_risk_percentile": PRIORITY_INFLATION_GROWTH_EQUITY,
    # P3 - proxy / valuation / explanation / portfolio
    "breadth_concentration_proxy": PRIORITY_PROXY_EXPLANATION_PORTFOLIO,
    "valuation_equity_structure": PRIORITY_PROXY_EXPLANATION_PORTFOLIO,
    "scenario_stress": PRIORITY_PROXY_EXPLANATION_PORTFOLIO,
    "historical_validation": PRIORITY_PROXY_EXPLANATION_PORTFOLIO,
    "portfolio_exposure_overlay": PRIORITY_PROXY_EXPLANATION_PORTFOLIO,
    "portfolio_deviation": PRIORITY_PROXY_EXPLANATION_PORTFOLIO,
    "data_quality_diagnostics": PRIORITY_PROXY_EXPLANATION_PORTFOLIO,
}

# Reasoning order: which P1 sub-modules to read first within P1.
# Order matches the user-specified "credit -> funding -> rates -> real_yield ->
# regime -> stress composite -> pullback" reading flow.
_INTRA_P1_ORDER: dict[str, int] = {
    "macro_regime_review": 0,
    "financial_stress_composite": 1,
    "credit_stress": 2,
    "liquidity_funding_stress": 3,
    "rate_pressure": 4,
    "real_yield_pressure": 5,
    "pullback_systemic_risk_checklist": 6,
}

_INTRA_P2_ORDER: dict[str, int] = {
    "inflation_energy_pressure": 0,
    "growth_inflation_macro_pack": 1,
    "equity_trend": 2,
    "market_stress_derived": 3,
    "historical_risk_percentile": 4,
}

_INTRA_P3_ORDER: dict[str, int] = {
    "valuation_equity_structure": 0,
    "breadth_concentration_proxy": 1,
    "scenario_stress": 2,
    "historical_validation": 3,
    "portfolio_exposure_overlay": 4,
    "portfolio_deviation": 5,
    "data_quality_diagnostics": 6,
}


def assign_context_priority(
    row: Mapping[str, Any],
    *,
    excluded: bool = False,
) -> int:
    """Return the 1-4 priority band for a manifest row.

    Excluded rows always receive P4 regardless of module. Unknown modules
    default to P3 so they appear after core state but before excluded
    constraints; this is deliberately conservative.
    """

    if excluded:
        return PRIORITY_EXCLUDED_CONSTRAINT
    module = str(row.get("module") or "").strip()
    return _MODULE_PRIORITY.get(module, PRIORITY_PROXY_EXPLANATION_PORTFOLIO)


def priority_label(priority: int, *, language: str = "en") -> str:
    table = PRIORITY_LABELS_ZH if language == "zh" else PRIORITY_LABELS_EN
    return table.get(priority, f"P? unknown priority {priority}")


def sort_rows_by_priority(
    rows: list[Mapping[str, Any]],
    *,
    excluded: bool = False,
) -> list[Mapping[str, Any]]:
    """Return rows sorted by priority, then by intra-priority reading order,
    then by module name, then by metric_key, for deterministic output."""

    def sort_key(row: Mapping[str, Any]) -> tuple[int, int, str, str]:
        priority = assign_context_priority(row, excluded=excluded)
        module = str(row.get("module") or "")
        metric_key = str(row.get("metric_key") or "")
        intra = _intra_priority_index(priority, module)
        return (priority, intra, module, metric_key)

    return sorted(rows, key=sort_key)


def group_rows_by_priority(
    rows: list[Mapping[str, Any]],
    *,
    excluded: bool = False,
) -> dict[int, list[Mapping[str, Any]]]:
    """Bucket rows by their priority band."""

    buckets: dict[int, list[Mapping[str, Any]]] = {
        PRIORITY_CORE_MACRO_STATE: [],
        PRIORITY_INFLATION_GROWTH_EQUITY: [],
        PRIORITY_PROXY_EXPLANATION_PORTFOLIO: [],
        PRIORITY_EXCLUDED_CONSTRAINT: [],
    }
    for row in sort_rows_by_priority(rows, excluded=excluded):
        priority = assign_context_priority(row, excluded=excluded)
        buckets[priority].append(row)
    return buckets


def _intra_priority_index(priority: int, module: str) -> int:
    if priority == PRIORITY_CORE_MACRO_STATE:
        return _INTRA_P1_ORDER.get(module, len(_INTRA_P1_ORDER))
    if priority == PRIORITY_INFLATION_GROWTH_EQUITY:
        return _INTRA_P2_ORDER.get(module, len(_INTRA_P2_ORDER))
    if priority == PRIORITY_PROXY_EXPLANATION_PORTFOLIO:
        return _INTRA_P3_ORDER.get(module, len(_INTRA_P3_ORDER))
    return 0
