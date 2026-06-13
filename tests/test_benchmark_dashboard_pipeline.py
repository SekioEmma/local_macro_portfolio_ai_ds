"""Tests for scripts/benchmark_dashboard_pipeline.py.

Validates read-only behaviour, expected output shape, and privacy guards.
All tests block network to confirm no external connections are made.
"""
import json
import socket

import benchmark_dashboard_pipeline as bench
from data_quality import market_history_store


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _block_network(monkeypatch):
    def _raise(*args, **kwargs):
        raise AssertionError("Network access is not allowed in benchmark tests.")

    monkeypatch.setattr(socket, "create_connection", _raise)


def _write_json(path, payload):
    path.write_text(json.dumps(payload), encoding="utf-8")


def _insert_observation(db_path, metric_key, observation_date, value, *, source_series=None):
    market_history_store.upsert_market_observation(
        {
            "metric_key": metric_key,
            "observation_date": observation_date,
            "value": value,
            "value_text": str(value),
            "unit": "percent",
            "status": "ok",
            "source": "test_source",
            "source_badge": "official",
            "provider": "test_source",
            "source_series": source_series or metric_key.upper(),
            "generated_at": f"{observation_date}T00:00:00+00:00",
            "fetched_at": f"{observation_date}T00:00:00+00:00",
            "freshness_status": "fresh",
            "ai_context_allowed": True,
            "metric_kind": "raw",
            "lineage": {},
        },
        db_path=db_path,
    )


def _minimal_reports_dir(tmp_path):
    _write_json(
        tmp_path / "market_snapshot.json",
        {
            "generated_at": "2026-01-01T00:00:00+00:00",
            "status": "ok",
            "dgs10": {
                "value": 4.5,
                "status": "ok",
                "source": "FRED",
                "source_badge": "official",
                "observation_date": "2026-01-01",
                "freshness_status": "fresh",
            },
        },
    )
    return tmp_path


EXPECTED_KEYS = {
    "generated_at",
    "market_history_observation_count",
    "market_history_metric_count",
    "dashboard_summary_ms",
    "dashboard_evidence_table_ms",
    "ai_context_manifest_ms",
    "d10_build_ms",
    "d11_build_ms",
    "d13_build_ms",
    "d13_query_strategy",
    "d14_build_ms",
    "d14_query_strategy",
    "audit_total_ms",
    "evidence_row_count",
    "included_facts_count",
    "included_model_outputs_count",
    "market_history_batch_api_available",
    "market_history_index_metric_date_available",
    "slowest_sections",
    "notes",
    "call_path_audit",
    "db_index_audit",
}


# ---------------------------------------------------------------------------
# test 1: runs without network
# ---------------------------------------------------------------------------

def test_benchmark_runs_without_network(monkeypatch, tmp_path):
    _block_network(monkeypatch)
    reports_dir = _minimal_reports_dir(tmp_path)
    result = bench.run_benchmark(
        reports_dir=reports_dir,
        market_history_db_path=tmp_path / "empty.sqlite3",
    )
    assert isinstance(result, dict)


# ---------------------------------------------------------------------------
# test 2: does not write DB / cache / outputs
# ---------------------------------------------------------------------------

def test_benchmark_does_not_write_db(monkeypatch, tmp_path):
    _block_network(monkeypatch)
    reports_dir = _minimal_reports_dir(tmp_path)
    db_path = tmp_path / "test_no_write.sqlite3"

    bench.run_benchmark(reports_dir=reports_dir, market_history_db_path=db_path)

    # DB should not have been created (benchmark does not initialise or write to DB)
    assert not db_path.exists(), "Benchmark must not create or write to the market history DB"


def test_benchmark_does_not_write_output_files(monkeypatch, tmp_path):
    _block_network(monkeypatch)
    reports_dir = _minimal_reports_dir(tmp_path)

    bench.run_benchmark(
        reports_dir=reports_dir,
        market_history_db_path=tmp_path / "absent.sqlite3",
    )

    written = [p for p in tmp_path.rglob("*") if p.is_file() and p.suffix != ".json"]
    # Only the .json report file we wrote ourselves should exist
    assert not written, f"Unexpected files written by benchmark: {written}"


# ---------------------------------------------------------------------------
# test 3: output includes all expected keys
# ---------------------------------------------------------------------------

def test_benchmark_output_has_expected_keys(monkeypatch, tmp_path):
    _block_network(monkeypatch)
    reports_dir = _minimal_reports_dir(tmp_path)
    result = bench.run_benchmark(
        reports_dir=reports_dir,
        market_history_db_path=tmp_path / "absent.sqlite3",
    )
    missing = EXPECTED_KEYS - result.keys()
    assert not missing, f"Benchmark output missing keys: {missing}"


def test_benchmark_slowest_sections_is_list(monkeypatch, tmp_path):
    _block_network(monkeypatch)
    result = bench.run_benchmark(
        reports_dir=_minimal_reports_dir(tmp_path),
        market_history_db_path=tmp_path / "absent.sqlite3",
    )
    assert isinstance(result["slowest_sections"], list)
    assert len(result["slowest_sections"]) <= 3
    for entry in result["slowest_sections"]:
        assert "section" in entry
        assert "ms" in entry


def test_benchmark_timings_are_non_negative(monkeypatch, tmp_path):
    _block_network(monkeypatch)
    result = bench.run_benchmark(
        reports_dir=_minimal_reports_dir(tmp_path),
        market_history_db_path=tmp_path / "absent.sqlite3",
    )
    for key in (
        "dashboard_summary_ms",
        "dashboard_evidence_table_ms",
        "ai_context_manifest_ms",
        "d10_build_ms",
        "d11_build_ms",
        "d13_build_ms",
        "d14_build_ms",
        "audit_total_ms",
    ):
        assert result[key] >= 0, f"{key} must be non-negative"


# ---------------------------------------------------------------------------
# test 4: does not expose raw holdings
# ---------------------------------------------------------------------------

def test_benchmark_does_not_expose_raw_holdings(monkeypatch, tmp_path):
    _block_network(monkeypatch)
    _write_json(
        tmp_path / "portfolio_snapshot.json",
        {
            "generated_at": "2026-01-01T00:00:00+00:00",
            "status": "ok",
            "holdings": [{"ticker": "SENSITIVE_FUND", "amount": 999999}],
        },
    )
    _write_json(
        tmp_path / "market_snapshot.json",
        {
            "generated_at": "2026-01-01T00:00:00+00:00",
            "status": "ok",
        },
    )
    result = bench.run_benchmark(
        reports_dir=tmp_path,
        market_history_db_path=tmp_path / "absent.sqlite3",
    )
    serialized = json.dumps(result)
    assert "SENSITIVE_FUND" not in serialized
    assert "raw_holdings" not in serialized


# ---------------------------------------------------------------------------
# test 5: does not expose raw provider payload
# ---------------------------------------------------------------------------

def test_benchmark_does_not_expose_raw_provider_payload(monkeypatch, tmp_path):
    _block_network(monkeypatch)
    result = bench.run_benchmark(
        reports_dir=_minimal_reports_dir(tmp_path),
        market_history_db_path=tmp_path / "absent.sqlite3",
    )
    serialized = json.dumps(result)
    assert "raw_provider" not in serialized


# ---------------------------------------------------------------------------
# test 6: does not include API keys
# ---------------------------------------------------------------------------

def test_benchmark_does_not_include_api_keys(monkeypatch, tmp_path):
    _block_network(monkeypatch)
    result = bench.run_benchmark(
        reports_dir=_minimal_reports_dir(tmp_path),
        market_history_db_path=tmp_path / "absent.sqlite3",
    )
    serialized = json.dumps(result)
    import re
    assert not re.search(r"sk-[A-Za-z0-9_-]{20,}", serialized), "API key pattern found in output"
    assert "DEEPSEEK_API_KEY" not in serialized
    assert "FRED_API_KEY" not in serialized
    assert "TAVILY_API_KEY" not in serialized


# ---------------------------------------------------------------------------
# test 7: can run when market_history DB exists with data
# ---------------------------------------------------------------------------

def test_benchmark_runs_with_populated_db(monkeypatch, tmp_path):
    _block_network(monkeypatch)
    reports_dir = _minimal_reports_dir(tmp_path)
    db_path = tmp_path / "market_history.sqlite3"
    market_history_store.initialize_market_history_db(db_path=db_path)

    for i in range(3):
        _insert_observation(
            db_path,
            "high_yield_spread",
            f"2026-01-{i + 1:02d}",
            4.5 + i * 0.1,
            source_series="BAMLH0A0HYM2EY",
        )
        _insert_observation(
            db_path,
            "vix",
            f"2026-01-{i + 1:02d}",
            18.0 + i,
            source_series="VIXCLS",
        )

    result = bench.run_benchmark(reports_dir=reports_dir, market_history_db_path=db_path)

    assert result["db_index_audit"]["db_exists"] is True
    assert result["market_history_observation_count"] >= 6
    assert result["market_history_metric_count"] >= 2
    assert result["dashboard_summary_ms"] >= 0


# ---------------------------------------------------------------------------
# test 8: can run when market_history DB missing or empty
# ---------------------------------------------------------------------------

def test_benchmark_runs_with_missing_db(monkeypatch, tmp_path):
    _block_network(monkeypatch)
    reports_dir = _minimal_reports_dir(tmp_path)
    result = bench.run_benchmark(
        reports_dir=reports_dir,
        market_history_db_path=tmp_path / "nonexistent.sqlite3",
    )
    assert isinstance(result, dict)
    assert result["market_history_observation_count"] == 0
    assert result["db_index_audit"]["db_exists"] is False


def test_benchmark_runs_with_empty_db(monkeypatch, tmp_path):
    _block_network(monkeypatch)
    reports_dir = _minimal_reports_dir(tmp_path)
    db_path = tmp_path / "empty_market_history.sqlite3"
    market_history_store.initialize_market_history_db(db_path=db_path)

    result = bench.run_benchmark(reports_dir=reports_dir, market_history_db_path=db_path)

    assert isinstance(result, dict)
    assert result["market_history_observation_count"] == 0
    assert result["db_index_audit"]["db_exists"] is True


# ---------------------------------------------------------------------------
# test: call_path_audit structure
# ---------------------------------------------------------------------------

def test_benchmark_call_path_audit_structure(monkeypatch, tmp_path):
    _block_network(monkeypatch)
    result = bench.run_benchmark(
        reports_dir=_minimal_reports_dir(tmp_path),
        market_history_db_path=tmp_path / "absent.sqlite3",
    )
    audit = result["call_path_audit"]
    assert "confirmed_facts" in audit
    assert "resolved_hotspots" in audit
    assert "remaining_hotspots_for_m3" in audit
    assert isinstance(audit["confirmed_facts"], list)
    assert isinstance(audit["resolved_hotspots"], list)
    assert isinstance(audit["remaining_hotspots_for_m3"], list)
    assert len(audit["confirmed_facts"]) > 0
    assert len(audit["resolved_hotspots"]) > 0
    assert len(audit["remaining_hotspots_for_m3"]) > 0


# ---------------------------------------------------------------------------
# test: guard_output rejects prohibited patterns
# ---------------------------------------------------------------------------

def test_guard_output_rejects_raw_holdings():
    import pytest
    with pytest.raises(ValueError, match="raw_holdings"):
        bench._guard_output({"data": "raw_holdings leak"})


def test_guard_output_rejects_raw_provider():
    import pytest
    with pytest.raises(ValueError, match="raw_provider"):
        bench._guard_output({"data": "raw_provider payload"})


def test_guard_output_accepts_clean_data():
    result = bench._guard_output({"timing_ms": 12.3, "row_count": 42})
    assert result["timing_ms"] == 12.3


# ---------------------------------------------------------------------------
# test: db_index_audit structure
# ---------------------------------------------------------------------------

def test_db_index_audit_keys_present_when_db_missing(monkeypatch, tmp_path):
    _block_network(monkeypatch)
    result = bench.run_benchmark(
        reports_dir=_minimal_reports_dir(tmp_path),
        market_history_db_path=tmp_path / "absent.sqlite3",
    )
    idx = result["db_index_audit"]
    assert "db_exists" in idx
    assert "explicit_index_names" in idx
    assert "has_explicit_metric_key_index" in idx
    assert "unique_constraint_covers_metric_key_observation_date" in idx
    assert "note" in idx
