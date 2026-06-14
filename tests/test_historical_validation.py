import json

from data_quality import historical_validation as d19
from data_quality import market_history_store


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
        "ordinary_pullback_flag",
        "data_availability_constraints",
        "interpretation_boundary",
    }
    assert all(required <= set(event) for event in registry)
    assert any(event["event_id"] == "2022_inflation_rates_bear_market" for event in registry)


def test_d19_insufficient_local_history_is_graceful(tmp_path):
    db_path = tmp_path / "market_history.sqlite3"
    market_history_store.initialize_market_history_db(db_path)

    summary = d19.build_historical_validation_summary(db_path=str(db_path))
    rows = d19.build_historical_validation_rows(db_path=str(db_path))

    assert summary["event_count"] == len(d19.EVENT_WINDOWS)
    assert summary["available_event_count"] == 0
    assert summary["insufficient_history_event_count"] == len(d19.EVENT_WINDOWS)
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

    assert event["window_status"] == "available"
    assert event["available_day_count"] == 1
    assert set(event["dominant_primary_pressure_groups"]) & {
        "rates_real_yield",
        "inflation_energy",
    }
    assert event["under_escalation_flag"] is False


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

    assert event["window_status"] == "available"
    assert event["over_escalation_flag"] is False


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
