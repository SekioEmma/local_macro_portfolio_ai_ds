import json
from datetime import date, timedelta

import audit_credit_oas_history_coverage as audit
from data_providers import market_history_store


def test_local_only_default_does_not_probe_network(tmp_path, monkeypatch):
    db_path = tmp_path / "market_history.sqlite3"
    _insert_series(db_path, "high_yield_spread", date(2023, 1, 1), 10)

    def fail_probe(*args, **kwargs):
        raise AssertionError("local-only audit must not probe FRED")

    monkeypatch.setattr(audit, "audit_fred_provider_ranges", fail_probe)

    result = audit.run_audit(market_history_db=db_path)

    assert result["mode"] == "local_only"
    assert result["fred_provider_availability"] == {}
    assert result["safety"]["reads_local_market_history_only"] is True
    assert result["safety"]["writes_database"] is False


def test_probe_fred_range_does_not_write_database(tmp_path, monkeypatch):
    db_path = tmp_path / "market_history.sqlite3"
    _insert_series(db_path, "high_yield_spread", date(2023, 1, 1), 5)
    before = market_history_store.count_observations_by_metric(db_path=db_path)

    monkeypatch.setattr(
        audit,
        "audit_fred_provider_ranges",
        lambda timeout_seconds=20: {
            "BAMLH0A0HYM2": {
                "series_id": "BAMLH0A0HYM2",
                "provider": "FRED",
                "status": "ok",
                "provider_start_now": "2023-01-01",
                "provider_end_now": "2026-01-01",
                "provider_non_null_count": 700,
                "provider_coverage_years": 3.0,
                "latest_value": 3.4,
                "latest_date": "2026-01-01",
                "frequency_detected": "daily_market_or_business_day",
                "query_method": "fred_public_csv",
                "notes_detected_if_available": "limited",
            }
        },
    )

    result = audit.run_audit(
        market_history_db=db_path,
        include_provider_probe=True,
    )

    after = market_history_store.count_observations_by_metric(db_path=db_path)
    assert result["mode"] == "probe_fred_range"
    assert before == after
    assert result["safety"]["writes_database"] is False


def test_output_has_summary_not_raw_series_values(tmp_path):
    db_path = tmp_path / "market_history.sqlite3"
    _insert_series(db_path, "high_yield_spread", date(2020, 1, 1), 1900)

    result = audit.run_audit(market_history_db=db_path)
    serialized = json.dumps(result, sort_keys=True)

    assert '"data":' not in serialized.lower()
    assert '"values":' not in serialized.lower()
    assert '"series": [' not in serialized.lower()
    assert "raw_provider_response" not in serialized.lower()
    assert "raw_payload" not in serialized.lower()
    assert '"lineage_json":' not in serialized.lower()
    assert "1900.0" not in serialized


def test_output_does_not_include_api_key_or_private_external_path(tmp_path, monkeypatch):
    secret = "super-secret-fred-key"
    monkeypatch.setenv("FRED_API_KEY", secret)
    monkeypatch.setattr(
        audit,
        "_probe_fred_api",
        lambda series_id, api_key, timeout_seconds=20: audit._provider_error(
            series_id, "fred_api", "forced_error"
        ),
    )
    monkeypatch.setattr(
        audit,
        "_probe_fred_public_csv",
        lambda series_id, timeout_seconds=20: audit._provider_summary(
            series_id,
            "fred_public_csv",
            [("2023-01-01", 1.0), ("2026-01-01", 2.0)],
        ),
    )
    db_path = tmp_path / "external" / "market_history.sqlite3"

    result = audit.run_audit(market_history_db=db_path, include_provider_probe=True)
    serialized = json.dumps(result, sort_keys=True)

    assert secret not in serialized
    assert str(tmp_path) not in serialized
    assert result["local_market_history"]["db_path"] == "<external_market_history_db>"
    assert result["safety"]["reads_dotenv"] is False


def test_missing_fred_key_uses_public_endpoint_fail_soft(monkeypatch):
    monkeypatch.delenv("FRED_API_KEY", raising=False)
    calls = []

    def public_csv(series_id, timeout_seconds=20):
        calls.append(series_id)
        return audit._provider_summary(
            series_id,
            "fred_public_csv",
            [("2023-01-01", 1.0), ("2023-01-03", 1.1)],
        )

    monkeypatch.setattr(audit, "_probe_fred_public_csv", public_csv)

    result = audit.audit_fred_provider_ranges()

    assert set(calls) == set(audit.PROVIDER_SERIES)
    assert result["BAMLH0A0HYM2"]["query_method"] == "fred_public_csv"


def test_empty_local_db_reports_no_local_history(tmp_path):
    db_path = tmp_path / "market_history.sqlite3"
    market_history_store.initialize_market_history_db(db_path)

    result = audit.run_audit(market_history_db=db_path)

    assert result["local_market_history"]["schema"]["compatible"] is True
    assert result["local_market_history"]["metrics"]["high_yield_spread"]["coverage_status"] == "no_local_history"
    assert (
        result["d13_eligibility"]["metrics"]["investment_grade_spread"][
            "current_recommended_d13_status"
        ]
        == "no_local_history"
    )


def test_eligibility_calculates_3y_5y_and_long_history(tmp_path):
    db_path = tmp_path / "market_history.sqlite3"
    _insert_series(db_path, "high_yield_spread", date(2020, 1, 1), 1900)
    _insert_series(db_path, "investment_grade_spread", date(2023, 1, 1), 1100)

    result = audit.run_audit(market_history_db=db_path)

    hy = result["d13_eligibility"]["metrics"]["high_yield_spread"]
    ig = result["d13_eligibility"]["metrics"]["investment_grade_spread"]
    assert hy["can_compute_3y_rolling"] is True
    assert hy["can_compute_5y_rolling"] is True
    assert hy["can_compute_10y_reference"] is False
    assert hy["can_compute_long_history_reference"] is False
    assert hy["current_recommended_d13_status"] == "sufficient"
    assert ig["can_compute_3y_rolling"] is True
    assert ig["can_compute_5y_rolling"] is False
    assert ig["current_recommended_d13_status"] == "limited_history"


def _insert_series(
    db_path,
    metric_key,
    start_date,
    count,
    *,
    source_series=None,
):
    series_id = source_series or audit.TARGET_METRICS.get(metric_key, {}).get("series_id", metric_key.upper())
    observations = [
        {
            "metric_key": metric_key,
            "observation_date": (start_date + timedelta(days=index)).isoformat(),
            "value": float(index + 1),
            "status": "ok",
            "source": "FRED",
            "source_badge": "official",
            "provider": "FRED",
            "source_series": series_id,
            "generated_at": "2026-01-01T00:00:00+00:00",
            "fetched_at": "2026-01-01T00:00:00+00:00",
            "freshness_status": "historical",
            "ai_context_allowed": True,
            "metric_kind": "raw",
        }
        for index in range(count)
    ]
    market_history_store.upsert_market_observations(observations, db_path=db_path)
