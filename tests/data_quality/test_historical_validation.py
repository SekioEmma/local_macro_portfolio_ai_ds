import json
import subprocess
import sys

from data_quality import historical_validation as d19
from data_providers import market_history_store
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]


def test_d19_event_window_registry_shape():
    registry = d19.get_event_window_registry()

    assert registry
    required = {
        "event_id",
        "event_type",
        "start_date",
        "end_date",
        "pre_window_start",
        "pre_window_end",
        "expected_regime_labels",
        "expected_primary_pressure_groups",
        "expected_pressure_groups",
        "expected_non_trigger_constraints",
        "required_metric_groups",
        "optional_metric_groups",
        "known_data_limitations",
        "ordinary_pullback_flag",
        "data_availability_constraints",
        "interpretation_boundary",
    }
    assert all(required <= set(event) for event in registry)
    required_base_windows = {
        "2018_q4_tightening_scare",
        "2020_covid_shock",
        "2022_inflation_rates_bear_market",
        "2023_svb_bank_stress",
        "2015_2016_oil_hy_energy_stress",
    }
    assert required_base_windows <= {event["event_id"] for event in registry}


def test_d19_expanded_optional_windows_are_well_formed():
    registry = d19.get_event_window_registry()
    optional_windows = {
        "2011_euro_debt_us_downgrade_stress",
        "2016_global_growth_oil_credit_stress",
        "2018_volmageddon_liquidity_shock",
        "2021_reopening_inflation_pressure",
        "2024_rates_concentration_watch",
        "2025_ai_concentration_rates_watch",
    }

    events = {event["event_id"]: event for event in registry}
    assert optional_windows <= set(events)
    for event in events.values():
        assert event["pre_window_start"] <= event["pre_window_end"]
        assert event["pre_window_end"] < event["start_date"]
        assert event["start_date"] <= event["end_date"]
        assert event["required_metric_groups"]
        assert event["interpretation_boundary"] == d19.VALIDATION_BOUNDARY


def test_d19_insufficient_local_history_is_graceful(tmp_path):
    db_path = tmp_path / "market_history.sqlite3"
    market_history_store.initialize_market_history_db(db_path)

    summary = d19.build_historical_validation_summary(db_path=str(db_path))
    rows = d19.build_historical_validation_rows(db_path=str(db_path))

    assert summary["event_count"] == len(d19.EVENT_WINDOWS)
    assert summary["available_event_count"] == 0
    assert summary["insufficient_history_event_count"] == len(d19.EVENT_WINDOWS)
    assert summary["status"] == "insufficient_history"
    assert rows
    assert {row["status"] for row in rows} == {"insufficient_history"}
    assert rows[0]["ai_context_allowed"] is False


def test_d19_stress_window_can_recognize_rates_inflation_pressure(tmp_path):
    db_path = tmp_path / "market_history.sqlite3"
    market_history_store.initialize_market_history_db(db_path)
    for metric_key, value, status in (
        ("high_yield_spread", 4.2, "ok"),
        ("investment_grade_spread", 1.4, "ok"),
        ("dgs10", 4.1, "ok"),
        ("dfii10", 1.6, "ok"),
        ("real_yield_pressure_status", 1.0, "pressure"),
        ("core_cpi_yoy", 6.3, "pressure"),
        ("core_pce_yoy", 5.1, "pressure"),
        ("initial_jobless_claims", 220000.0, "ok"),
        ("unemployment_rate", 3.7, "ok"),
    ):
        _write_observation(db_path, metric_key, value, status, "2022-06-15")

    summary = d19.build_historical_validation_summary(db_path=str(db_path))
    event = _event(summary, "2022_inflation_rates_bear_market")

    assert event["window_status"] == "ok"
    assert event["coverage_status"] == "available"
    assert event["available_day_count"] == 1
    assert set(event["dominant_primary_pressure_groups"]) & {
        "rates_real_yield",
        "inflation_energy",
    }
    assert event["under_escalation_flag"] is False
    assert event["boundary_checks"]["D17_not_recession_call"] is True


def test_d19_ordinary_pullback_is_not_automatically_systemic(tmp_path):
    db_path = tmp_path / "market_history.sqlite3"
    market_history_store.initialize_market_history_db(db_path)
    for metric_key, value, status in (
        ("high_yield_spread", 3.5, "ok"),
        ("investment_grade_spread", 1.2, "ok"),
        ("dgs10", 3.2, "ok"),
        ("dfii10", 1.2, "ok"),
        ("real_yield_pressure_status", 1.0, "pressure"),
        ("core_cpi_yoy", 2.4, "ok"),
        ("initial_jobless_claims", 210000.0, "ok"),
        ("unemployment_rate", 3.8, "ok"),
    ):
        _write_observation(db_path, metric_key, value, status, "2018-11-15")

    summary = d19.build_historical_validation_summary(db_path=str(db_path))
    event = _event(summary, "2018_q4_tightening_scare")

    assert event["window_status"] == "ok"
    assert event["coverage_status"] == "available"
    assert event["over_escalation_flag"] is False
    assert event["boundary_checks"]["proxy_only_not_triggering"] is True


def test_d19_limited_replay_keeps_missing_groups_visible(tmp_path):
    db_path = tmp_path / "market_history.sqlite3"
    market_history_store.initialize_market_history_db(db_path)
    _write_observation(db_path, "dgs10", 4.1, "ok", "2022-06-15")
    _write_observation(db_path, "dfii10", 1.6, "ok", "2022-06-15")

    summary = d19.build_historical_validation_summary(db_path=str(db_path))
    event = _event(summary, "2022_inflation_rates_bear_market")

    assert event["coverage_status"] == "limited_replay"
    assert "inflation_energy" in event["missing_inputs"]
    assert event["boundary_checks"]["missing_data_visible"] is True
    assert event["under_escalation_flag"] is False


def test_d19_expanded_boundaries_are_preserved(tmp_path):
    db_path = tmp_path / "market_history.sqlite3"
    market_history_store.initialize_market_history_db(db_path)

    summary = d19.build_historical_validation_summary(db_path=str(db_path))

    assert summary["proxy_constraint_violation_count"] == 0
    assert summary["missing_data_violation_count"] == 0
    assert summary["module_consistency_summary"]["D14_confirmation_only_boundary_preserved"] is True
    assert summary["module_consistency_summary"]["D15_band_only_boundary_preserved"] is True
    assert summary["module_consistency_summary"]["D16_scenario_matrix_boundary_preserved"] is True
    assert summary["module_consistency_summary"]["D17_context_layer_boundary_preserved"] is True
    assert summary["module_consistency_summary"]["D18_research_proxy_boundary_preserved"] is True
    assert summary["missing_data_summary"]["valuation_gap_visible"] is True
    assert summary["missing_data_summary"]["earnings_gap_visible"] is True
    assert summary["missing_data_summary"]["true_breadth_gap_visible"] is True


def test_d19_public_rows_keep_legacy_keys_and_add_compact_v1_keys(tmp_path):
    db_path = tmp_path / "market_history.sqlite3"
    market_history_store.initialize_market_history_db(db_path)

    rows = d19.build_historical_validation_rows(db_path=str(db_path))
    keys = {row["metric_key"] for row in rows}

    assert d19.HISTORICAL_VALIDATION_KEYS <= keys
    assert d19.OPTIONAL_HISTORICAL_VALIDATION_KEYS <= keys
    assert _row(rows, "historical_validation_model_version")["value"] == "historical_validation_v1"
    assert _row(rows, "historical_validation_formula_version")["value"] == (
        "d19_expanded_historical_validation_v1"
    )


def test_d19_public_rows_include_compact_registry_replay_metadata(tmp_path):
    db_path = tmp_path / "market_history.sqlite3"
    market_history_store.initialize_market_history_db(db_path)
    for metric_key, value, status in (
        ("high_yield_spread", 4.2, "ok"),
        ("investment_grade_spread", 1.4, "ok"),
        ("dgs10", 4.1, "ok"),
        ("dfii10", 1.6, "ok"),
        ("real_yield_pressure_status", 1.0, "pressure"),
        ("core_cpi_yoy", 6.3, "pressure"),
        ("core_pce_yoy", 5.1, "pressure"),
        ("initial_jobless_claims", 220000.0, "ok"),
        ("unemployment_rate", 3.7, "ok"),
    ):
        _write_observation(db_path, metric_key, value, status, "2022-06-15")

    rows = d19.build_historical_validation_rows(db_path=str(db_path))
    contributions = _row(rows, "historical_validation_status")[
        "component_contributions"
    ]
    replay_rows = contributions["d19_v1_replay_rows"]
    replay_summary = contributions["d19_v1_replay_summary"]
    inflation = _replay_event(replay_rows, "inflation_rates_pressure_2022")

    assert replay_summary["replay_row_count"] >= 9
    assert replay_summary["rows_with_summary_count"] >= 5
    assert replay_summary["boundary_violation_count"] == 0
    assert inflation["validation_status"] in {"available", "limited"}
    assert "2022_inflation_rates_bear_market" in inflation["source_summary_event_ids"]
    assert inflation["available_day_count"] >= 1
    assert {"rates_real_yield", "inflation_energy"} & set(
        inflation["available_model_outputs"]
    )
    assert "earnings_gap_visible" in contributions["missing_data_summary"]


def test_run_historical_validation_defaults_to_stdout_only_and_output_is_explicit(tmp_path):
    db_path = tmp_path / "market_history.sqlite3"
    out_path = tmp_path / "d19.json"
    market_history_store.initialize_market_history_db(db_path)

    completed = subprocess.run(
        [
            sys.executable,
            str(_REPO_ROOT / "scripts/run_historical_validation.py"),
            "--market-history-db",
            str(db_path),
            "--event-id",
            "2022_inflation_rates_bear_market",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    payload = json.loads(completed.stdout)
    assert payload["event_count"] == 1
    assert not out_path.exists()

    subprocess.run(
        [
            sys.executable,
            str(_REPO_ROOT / "scripts/run_historical_validation.py"),
            "--market-history-db",
            str(db_path),
            "--output",
            str(out_path),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    assert json.loads(out_path.read_text(encoding="utf-8"))["event_count"] == len(
        d19.EVENT_WINDOWS
    )


def test_d19_public_outputs_do_not_expose_forbidden_scoring_terms(tmp_path):
    db_path = tmp_path / "market_history.sqlite3"
    market_history_store.initialize_market_history_db(db_path)

    payload = {
        "summary": d19.build_historical_validation_summary(db_path=str(db_path)),
        "rows": d19.build_historical_validation_rows(db_path=str(db_path)),
        "registry": d19.get_event_window_registry(),
    }
    text = json.dumps(payload, sort_keys=True).lower()

    for token in (
        "roc",
        "auc",
        "precision",
        "recall",
        "f1",
        "probability calibration",
        "crash probability",
        "recession probability",
        "trade signal",
        "buy",
        "sell",
        "hedge",
        "target allocation",
        "expected return",
    ):
        assert token not in text


def _event(summary, event_id):
    for event in summary["events"]:
        if event["event_id"] == event_id:
            return event
    raise AssertionError(f"missing event {event_id}")


def _row(rows, metric_key):
    for row in rows:
        if row["metric_key"] == metric_key:
            return row
    raise AssertionError(f"missing row {metric_key}")


def _replay_event(rows, event_id):
    for row in rows:
        if row["event_id"] == event_id:
            return row
    raise AssertionError(f"missing replay event {event_id}")


def _write_observation(db_path, metric_key, value, status, observation_date):
    market_history_store.upsert_market_observation(
        {
            "metric_key": metric_key,
            "observation_date": observation_date,
            "value": value,
            "value_text": str(value),
            "unit": None,
            "status": status,
            "source": "test_source",
            "source_badge": "official",
            "provider": "test_provider",
            "source_series": metric_key.upper(),
            "generated_at": f"{observation_date}T00:00:00+00:00",
            "fetched_at": f"{observation_date}T00:00:00+00:00",
            "freshness_status": "historical",
            "ai_context_allowed": True,
            "metric_kind": "raw",
        },
        db_path=db_path,
    )
