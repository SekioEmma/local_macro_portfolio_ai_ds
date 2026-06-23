import json
from datetime import date
from pathlib import Path

from data_quality.historical_validation_event_registry import (
    ALLOWED_EVENT_TYPES,
    ALLOWED_PRESSURE_GROUPS,
    build_historical_validation_event_registry,
    get_historical_validation_event_registry,
    validate_historical_validation_event_registry,
)

_REPO_ROOT = Path(__file__).resolve().parents[2]


FORBIDDEN_OUTPUT_TERMS = (
    "crash probability",
    "recession probability",
    "market direction probability",
    "expected return",
    "predicted return",
    "future return",
    "buy",
    "sell",
    "hedge",
    "rebalance",
    "target allocation",
    "target weight",
    "trade signal",
    "guaranteed",
    "will rise",
    "will fall",
)


def test_d19_v0_event_registry_integrity():
    events = build_historical_validation_event_registry()

    assert len(events) >= 9
    assert len({event.event_id for event in events}) == len(events)
    validate_historical_validation_event_registry(events)

    for event in events:
        assert event.event_id == event.event_id.lower()
        assert " " not in event.event_id
        assert event.event_name
        start = date.fromisoformat(event.start_date)
        end = date.fromisoformat(event.end_date)
        pre_start = date.fromisoformat(event.pre_window_start)
        pre_end = date.fromisoformat(event.pre_window_end)
        assert start <= end
        assert pre_start <= pre_end
        assert pre_end < start
        assert event.event_type in ALLOWED_EVENT_TYPES
        assert set(event.expected_pressure_groups) <= ALLOWED_PRESSURE_GROUPS
        assert event.interpretation_boundary
        assert event.data_availability_constraints


def test_d19_v0_event_registry_contains_initial_stage_r1_windows():
    event_ids = {
        event.event_id for event in build_historical_validation_event_registry()
    }

    assert {
        "dot_com_equity_valuation_unwind_2000",
        "gfc_credit_funding_systemic_stress_2008",
        "debt_ceiling_eurozone_stress_2011",
        "oil_hy_energy_credit_stress_2015_2016",
        "q4_rates_liquidity_equity_stress_2018",
        "covid_liquidity_shock_2020",
        "inflation_rates_pressure_2022",
        "svb_regional_banking_liquidity_credit_stress_2023",
        "ai_concentration_valuation_structure_research_window_2024_2025",
    } <= event_ids


def test_d19_v0_registry_boundary_language_is_output_safe():
    text = json.dumps(
        get_historical_validation_event_registry(),
        sort_keys=True,
        ensure_ascii=False,
    ).lower()

    for token in FORBIDDEN_OUTPUT_TERMS:
        assert token not in text


def test_d19_v0_registry_code_has_no_production_clustering():
    source = Path(
        str(_REPO_ROOT / "src/data_quality/historical_validation_event_registry.py")
    ).read_text(encoding="utf-8")

    for token in (
        "KMeans(",
        "GaussianMixture",
        "cluster_probability",
        "cluster_to_action",
        "cluster_to_portfolio",
        "predict_proba",
    ):
        assert token not in source
