import json
import subprocess
import sys
from pathlib import Path

from data_quality.historical_validation_event_registry import (
    build_historical_validation_event_registry,
)
from data_quality.historical_validation_replay import (
    ALLOWED_VALIDATION_STATUSES,
    build_historical_validation_replay_rows,
    get_historical_validation_replay_rows,
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


def test_d19_v0_replay_rows_have_required_structure():
    rows = build_historical_validation_replay_rows()

    assert rows
    assert len(rows) >= 9
    for row in rows:
        assert row.event_id
        assert row.event_name
        assert row.expected_pressure_groups
        assert row.validation_status in ALLOWED_VALIDATION_STATUSES
        assert row.interpretation_boundary
        assert row.window["start"] <= row.window["end"]
        assert row.pre_window["start"] <= row.pre_window["end"]
        assert row.missing_or_limited_inputs


def test_d19_v0_replay_defaults_to_reference_only_without_local_summary():
    rows = build_historical_validation_replay_rows()

    assert {row.validation_status for row in rows} == {"reference_only"}
    assert all(row.available_model_outputs == () for row in rows)
    assert all(
        "not low-risk labels" in " ".join(row.validation_notes)
        for row in rows
        if row.validation_status in {"reference_only", "limited"}
    )


def test_d19_v0_replay_can_consume_existing_summary_without_reading_data():
    events = build_historical_validation_event_registry()
    target = events[0]
    rows = build_historical_validation_replay_rows(
        events=[target],
        existing_summary={
            "events": [
                {
                    "event_id": target.event_id,
                    "coverage_status": "limited_replay",
                    "dominant_primary_pressure_groups": ["credit"],
                    "missing_inputs": ["liquidity_funding"],
                }
            ]
        },
    )

    assert len(rows) == 1
    assert rows[0].validation_status == "limited"
    assert rows[0].available_model_outputs == ("credit",)
    assert rows[0].missing_or_limited_inputs == ("liquidity_funding",)
    assert rows[0].source_summary_event_ids == (target.event_id,)
    assert rows[0].coverage_statuses == ("limited_replay",)


def test_d19_v1_replay_maps_existing_summary_aliases_to_registry_windows():
    events = [
        event
        for event in build_historical_validation_event_registry()
        if event.event_id == "inflation_rates_pressure_2022"
    ]
    rows = build_historical_validation_replay_rows(
        events=events,
        existing_summary={
            "events": [
                {
                    "event_id": "2022_inflation_rates_bear_market",
                    "coverage_status": "available",
                    "window_status": "ok",
                    "available_day_count": 3,
                    "insufficient_history_day_count": 0,
                    "dominant_primary_pressure_groups": [
                        "rates_real_yield",
                        "inflation_energy",
                    ],
                    "dominant_labels": ["rates_pressure"],
                    "missing_inputs": [],
                    "blocked_inputs": ["true_breadth"],
                    "boundary_violation_flags": [],
                    "proxy_constraints": {"proxy_metric_keys": ["sp500_drawdown_3m"]},
                    "missing_data_summary": {"earnings_revision": 3},
                }
            ]
        },
    )

    assert len(rows) == 1
    row = rows[0]
    assert row.validation_status == "available"
    assert row.source_summary_event_ids == ("2022_inflation_rates_bear_market",)
    assert row.coverage_statuses == ("available",)
    assert row.window_statuses == ("ok",)
    assert row.available_day_count == 3
    assert row.available_model_outputs == ("rates_real_yield", "inflation_energy")
    assert row.blocked_inputs == ("true_breadth",)
    assert row.proxy_constraints["proxy_metric_keys"] == ("sp500_drawdown_3m",)
    assert row.missing_data_summary == {"earnings_revision": 3}
    assert row.compact_validation_metadata["has_summary"] is True


def test_d19_v1_replay_keeps_boundary_violations_visible_without_unsafe_language():
    events = [
        event
        for event in build_historical_validation_event_registry()
        if event.event_id == "q4_rates_liquidity_equity_stress_2018"
    ]
    rows = build_historical_validation_replay_rows(
        events=events,
        existing_summary={
            "events": [
                {
                    "event_id": "2018_q4_tightening_scare",
                    "coverage_status": "limited_replay",
                    "window_status": "limited_evidence",
                    "available_day_count": 1,
                    "insufficient_history_day_count": 2,
                    "dominant_primary_pressure_groups": ["rates_real_yield"],
                    "missing_inputs": ["liquidity_funding"],
                    "boundary_violation_flags": ["test_boundary_flag"],
                    "missing_data_summary": {"liquidity_funding": 2},
                }
            ]
        },
    )

    row = rows[0]
    assert row.validation_status == "limited"
    assert row.boundary_violation_flags == ("test_boundary_flag",)
    assert row.boundary_violation_count == 1
    assert "liquidity_funding" in row.missing_or_limited_inputs
    assert "boundary items" in " ".join(row.validation_notes)


def test_d19_v0_ordinary_pullback_is_not_systemic_stress_event():
    rows = build_historical_validation_replay_rows()
    ordinary_rows = [row for row in rows if row.ordinary_pullback_flag]

    assert ordinary_rows
    assert all(row.event_type != "systemic_stress_event" for row in ordinary_rows)
    assert all(
        "Ordinary pullback windows require confirmation"
        in " ".join(row.validation_notes)
        for row in ordinary_rows
    )


def test_d19_v0_replay_boundary_language_is_output_safe():
    text = json.dumps(
        get_historical_validation_replay_rows(),
        sort_keys=True,
        ensure_ascii=False,
    ).lower()

    for token in FORBIDDEN_OUTPUT_TERMS:
        assert token not in text


def test_d19_v1_replay_with_summary_boundary_language_is_output_safe():
    text = json.dumps(
        get_historical_validation_replay_rows(
            existing_summary={
                "events": [
                    {
                        "event_id": "2023_svb_bank_stress",
                        "coverage_status": "insufficient_history",
                        "window_status": "insufficient_history",
                        "available_day_count": 0,
                        "insufficient_history_day_count": 1,
                        "missing_inputs": ["liquidity_funding"],
                        "boundary_violation_flags": [],
                    }
                ]
            }
        ),
        sort_keys=True,
        ensure_ascii=False,
    ).lower()

    for token in FORBIDDEN_OUTPUT_TERMS:
        assert token not in text


def test_d19_v0_replay_code_has_no_production_clustering_or_forbidden_surfaces():
    service_sources = "\n".join(
        Path(path).read_text(encoding="utf-8")
        for path in (
            str(_REPO_ROOT / "src/data_quality/historical_validation_event_registry.py"),
            str(_REPO_ROOT / "src/data_quality/historical_validation_replay.py"),
        )
    )

    for token in (
        "KMeans(",
        "GaussianMixture",
        "cluster_probability",
        "cluster_to_action",
        "cluster_to_portfolio",
        "predict_proba",
        "DeepSeek",
        "Tavily",
        "external_llm.yaml",
        ".env",
        "@app.get",
        "@router.get",
        "/api/chat",
        "/api/search",
        "/api/ai/deepseek",
        "/api/ai/external",
    ):
        assert token not in service_sources


def test_run_historical_validation_show_events_is_read_only_and_import_safe():
    completed = subprocess.run(
        [
            sys.executable,
            str(_REPO_ROOT / "scripts/run_historical_validation.py"),
            "--show-events",
            "--format",
            "text",
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    assert "d19_v0_event_registry_count:" in completed.stdout
    assert "dot_com_equity_valuation_unwind_2000" in completed.stdout
