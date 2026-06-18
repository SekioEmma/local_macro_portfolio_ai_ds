from __future__ import annotations

import pytest

from app_backend.services.ai_context_priority import (
    PRIORITY_CORE_MACRO_STATE,
    PRIORITY_EXCLUDED_CONSTRAINT,
    PRIORITY_INFLATION_GROWTH_EQUITY,
    PRIORITY_PROXY_EXPLANATION_PORTFOLIO,
    assign_context_priority,
    group_rows_by_priority,
    priority_label,
    sort_rows_by_priority,
)


@pytest.mark.parametrize(
    "module",
    [
        "macro_regime_review",
        "financial_stress_composite",
        "pullback_systemic_risk_checklist",
        "credit_stress",
        "liquidity_funding_stress",
        "rate_pressure",
        "real_yield_pressure",
    ],
)
def test_p1_modules_are_core_macro_state(module):
    assert assign_context_priority({"module": module}) == PRIORITY_CORE_MACRO_STATE


@pytest.mark.parametrize(
    "module",
    [
        "inflation_energy_pressure",
        "growth_inflation_macro_pack",
        "equity_trend",
        "market_stress_derived",
        "historical_risk_percentile",
    ],
)
def test_p2_modules_are_inflation_growth_equity(module):
    assert (
        assign_context_priority({"module": module})
        == PRIORITY_INFLATION_GROWTH_EQUITY
    )


@pytest.mark.parametrize(
    "module",
    [
        "breadth_concentration_proxy",
        "valuation_equity_structure",
        "scenario_stress",
        "historical_validation",
        "portfolio_exposure_overlay",
        "portfolio_deviation",
        "data_quality_diagnostics",
    ],
)
def test_p3_modules_are_proxy_explanation_portfolio(module):
    assert (
        assign_context_priority({"module": module})
        == PRIORITY_PROXY_EXPLANATION_PORTFOLIO
    )


def test_excluded_rows_are_always_p4_regardless_of_module():
    row = {"module": "macro_regime_review"}
    assert assign_context_priority(row, excluded=True) == PRIORITY_EXCLUDED_CONSTRAINT


def test_unknown_module_falls_back_to_p3_not_p1():
    assert (
        assign_context_priority({"module": "unknown_future_module"})
        == PRIORITY_PROXY_EXPLANATION_PORTFOLIO
    )


def test_sort_orders_p1_then_p2_then_p3():
    rows = [
        {"module": "valuation_equity_structure", "metric_key": "fwd_pe"},
        {"module": "macro_regime_review", "metric_key": "macro_regime_label"},
        {"module": "equity_trend", "metric_key": "sp500_drawdown"},
        {"module": "credit_stress", "metric_key": "high_yield_spread"},
    ]
    sorted_rows = sort_rows_by_priority(rows)
    modules = [row["module"] for row in sorted_rows]
    # macro_regime_review and credit_stress are P1; equity_trend is P2;
    # valuation_equity_structure is P3.
    assert modules.index("macro_regime_review") < modules.index("equity_trend")
    assert modules.index("credit_stress") < modules.index("equity_trend")
    assert modules.index("equity_trend") < modules.index("valuation_equity_structure")


def test_sort_intra_p1_follows_reasoning_order():
    rows = [
        {"module": "pullback_systemic_risk_checklist", "metric_key": "x"},
        {"module": "credit_stress", "metric_key": "x"},
        {"module": "macro_regime_review", "metric_key": "x"},
        {"module": "financial_stress_composite", "metric_key": "x"},
    ]
    sorted_rows = sort_rows_by_priority(rows)
    modules = [row["module"] for row in sorted_rows]
    # Macro regime first, then financial stress composite, then credit,
    # then pullback (per the user-specified P1 reading order).
    assert modules == [
        "macro_regime_review",
        "financial_stress_composite",
        "credit_stress",
        "pullback_systemic_risk_checklist",
    ]


def test_group_by_priority_buckets_all_four_bands():
    rows = [
        {"module": "macro_regime_review", "metric_key": "a"},
        {"module": "equity_trend", "metric_key": "b"},
        {"module": "valuation_equity_structure", "metric_key": "c"},
    ]
    buckets = group_rows_by_priority(rows)
    assert len(buckets[PRIORITY_CORE_MACRO_STATE]) == 1
    assert len(buckets[PRIORITY_INFLATION_GROWTH_EQUITY]) == 1
    assert len(buckets[PRIORITY_PROXY_EXPLANATION_PORTFOLIO]) == 1
    assert len(buckets[PRIORITY_EXCLUDED_CONSTRAINT]) == 0


def test_priority_label_chinese_and_english_both_available():
    assert "核心" in priority_label(PRIORITY_CORE_MACRO_STATE, language="zh")
    assert "P1" in priority_label(PRIORITY_CORE_MACRO_STATE, language="en")
