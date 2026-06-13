"""M2 batch market history read tests.

Covers:
- list_market_observations_batch API semantics
- Schema version 2 index migration
- D13 row equivalence between single-query and batch paths
- D14 row equivalence between single-query and batch paths
- Benchmark M2 output fields
"""
from __future__ import annotations

import socket
from datetime import date, timedelta

import pytest

from data_quality import historical_percentile_metrics as percentile
from data_quality import liquidity_funding_stress as d14
from data_quality import market_history_store as store


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _block_network(monkeypatch):
    def _raise(*args, **kwargs):
        raise AssertionError("Network access is not allowed in M2 tests.")

    monkeypatch.setattr(socket, "create_connection", _raise)


def _insert(db_path, metric_key, observation_date, value, *, source_badge="official", source_series=None):
    store.upsert_market_observation(
        {
            "metric_key": metric_key,
            "observation_date": observation_date,
            "value": value,
            "value_text": str(value),
            "unit": "percent",
            "status": "ok",
            "source": "FRED",
            "source_badge": source_badge,
            "provider": "FRED",
            "source_series": source_series or metric_key.upper(),
            "generated_at": f"{observation_date}T00:00:00+00:00",
            "fetched_at": f"{observation_date}T00:00:00+00:00",
            "freshness_status": "historical",
            "ai_context_allowed": True,
            "metric_kind": "raw",
            "lineage": {"source_series": source_series or metric_key.upper()},
        },
        db_path=db_path,
    )


def _insert_series(
    db_path,
    metric_key,
    start_date,
    count,
    *,
    source_badge="official",
    source_series=None,
    step_days=1,
):
    for i in range(count):
        obs_date = (start_date + timedelta(days=i * step_days)).isoformat()
        _insert(db_path, metric_key, obs_date, float(i + 1), source_badge=source_badge, source_series=source_series)


def _without_generated_at(value):
    if isinstance(value, dict):
        return {
            key: _without_generated_at(item)
            for key, item in value.items()
            if key != "generated_at"
        }
    if isinstance(value, list):
        return [_without_generated_at(item) for item in value]
    return value


def _stable_d13(row):
    return _without_generated_at(row)


def _stable_d14(row):
    return _without_generated_at(row)


def _db_with_d14_observations(tmp_path, *, sofr=None, effr=None, iorb=None, cp=None, stl=None, nfci=None, anfci=None):
    db_path = tmp_path / "market_history.sqlite3"
    params = {
        "sofr": (sofr, "SOFR", "official", "percent", "2026-06-01"),
        "effr": (effr, "EFFR", "official", "percent", "2026-06-01"),
        "iorb": (iorb, "IORB", "official", "percent", "2026-06-01"),
        "commercial_paper_rate": (cp, "DCPF3M", "official_fallback", "percent", "2026-06-01"),
        "stl_fsi": (stl, "STLFSI4", "official_fallback", "index", "2026-05-29"),
        "nfci": (nfci, "NFCI", "official_fallback", "index", "2026-05-29"),
        "anfci": (anfci, "ANFCI", "official_fallback", "index", "2026-05-29"),
    }
    for metric_key, (value, series, badge, unit, obs_date) in params.items():
        if value is None:
            continue
        store.upsert_market_observation(
            {
                "metric_key": metric_key,
                "observation_date": obs_date,
                "value": value,
                "value_text": str(value),
                "unit": unit,
                "status": "ok",
                "source": "FRED",
                "source_badge": badge,
                "provider": "FRED",
                "source_series": series,
                "generated_at": f"{obs_date}T00:00:00+00:00",
                "fetched_at": f"{obs_date}T00:00:00+00:00",
                "freshness_status": "historical",
                "ai_context_allowed": True,
                "metric_kind": "raw",
                "lineage": {"provider": "FRED", "source_series": series},
            },
            db_path=db_path,
        )
    return db_path


# ---------------------------------------------------------------------------
# Part A: list_market_observations_batch API
# ---------------------------------------------------------------------------

def test_batch_empty_keys_returns_empty_dict(tmp_path):
    db_path = tmp_path / "mh.sqlite3"
    store.initialize_market_history_db(db_path)
    result = store.list_market_observations_batch([], db_path=db_path)
    assert result == {}


def test_batch_empty_keys_does_not_fail_without_db(tmp_path):
    result = store.list_market_observations_batch([], db_path=tmp_path / "absent.sqlite3")
    assert result == {}


def test_batch_missing_db_returns_empty_lists(tmp_path):
    result = store.list_market_observations_batch(["vix", "dgs10"], db_path=tmp_path / "absent.sqlite3")
    assert result == {"vix": [], "dgs10": []}


def test_batch_returns_same_observations_as_single_list(tmp_path):
    db_path = tmp_path / "mh.sqlite3"
    start = date(2024, 1, 1)
    for i in range(5):
        _insert(db_path, "vix", (start + timedelta(days=i)).isoformat(), float(i + 10))
    for i in range(3):
        _insert(db_path, "dgs10", (start + timedelta(days=i)).isoformat(), float(i + 4))

    single_vix = store.list_market_observations(metric_key="vix", db_path=db_path)
    single_dgs10 = store.list_market_observations(metric_key="dgs10", db_path=db_path)
    batch = store.list_market_observations_batch(["vix", "dgs10"], db_path=db_path)

    assert len(batch["vix"]) == len(single_vix)
    assert len(batch["dgs10"]) == len(single_dgs10)
    assert [r["observation_date"] for r in batch["vix"]] == [r["observation_date"] for r in single_vix]
    assert [r["observation_date"] for r in batch["dgs10"]] == [r["observation_date"] for r in single_dgs10]


def test_batch_limit_per_key_applies_per_metric(tmp_path):
    db_path = tmp_path / "mh.sqlite3"
    start = date(2024, 1, 1)
    for i in range(10):
        _insert(db_path, "vix", (start + timedelta(days=i)).isoformat(), float(i + 1))
    for i in range(10):
        _insert(db_path, "dgs30", (start + timedelta(days=i)).isoformat(), float(i + 4))

    result = store.list_market_observations_batch(["vix", "dgs30"], limit_per_key=3, db_path=db_path)

    assert len(result["vix"]) == 3
    assert len(result["dgs30"]) == 3


def test_batch_missing_metric_returns_empty_list(tmp_path):
    db_path = tmp_path / "mh.sqlite3"
    _insert(db_path, "vix", "2026-01-01", 20.0)

    result = store.list_market_observations_batch(["vix", "nonexistent_metric"], db_path=db_path)

    assert len(result["vix"]) == 1
    assert result["nonexistent_metric"] == []


def test_batch_observations_sorted_desc_per_metric(tmp_path):
    db_path = tmp_path / "mh.sqlite3"
    for obs_date in ["2024-01-01", "2024-03-15", "2024-06-01", "2024-12-31"]:
        _insert(db_path, "vix", obs_date, 20.0)

    result = store.list_market_observations_batch(["vix"], db_path=db_path)
    dates = [r["observation_date"] for r in result["vix"]]

    assert dates == sorted(dates, reverse=True)


def test_batch_set_input_accepted(tmp_path):
    db_path = tmp_path / "mh.sqlite3"
    _insert(db_path, "vix", "2026-01-01", 20.0)

    result = store.list_market_observations_batch({"vix"}, db_path=db_path)
    assert len(result["vix"]) == 1


def test_batch_tuple_input_accepted(tmp_path):
    db_path = tmp_path / "mh.sqlite3"
    _insert(db_path, "dgs10", "2026-01-01", 4.5)

    result = store.list_market_observations_batch(("dgs10",), db_path=db_path)
    assert len(result["dgs10"]) == 1


# ---------------------------------------------------------------------------
# Part B: SQLite index migration (schema version 2)
# ---------------------------------------------------------------------------

def test_migration_creates_metric_date_index_on_fresh_db(tmp_path):
    db_path = tmp_path / "mh.sqlite3"
    store.initialize_market_history_db(db_path)

    with store.connect_market_history_db(db_path) as conn:
        idx = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index' AND name='idx_market_observations_metric_date'"
        ).fetchone()
    assert idx is not None, "idx_market_observations_metric_date index must exist after migration"


def test_migration_schema_version_is_2(tmp_path):
    db_path = tmp_path / "mh.sqlite3"
    store.initialize_market_history_db(db_path)
    assert store.get_market_history_schema_version(db_path=db_path) == 2


def test_migration_is_idempotent(tmp_path):
    db_path = tmp_path / "mh.sqlite3"
    store.initialize_market_history_db(db_path)
    store.initialize_market_history_db(db_path)
    store.initialize_market_history_db(db_path)

    assert store.get_market_history_schema_version(db_path=db_path) == 2
    with store.connect_market_history_db(db_path) as conn:
        rows = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index' AND name='idx_market_observations_metric_date'"
        ).fetchall()
    assert len(rows) == 1, "Idempotent migration must not create duplicate index"


def test_migration_does_not_change_existing_data(tmp_path):
    db_path = tmp_path / "mh.sqlite3"
    _insert(db_path, "vix", "2026-01-01", 22.5)
    _insert(db_path, "dgs10", "2026-01-01", 4.2)

    store.initialize_market_history_db(db_path)

    rows_vix = store.list_market_observations(metric_key="vix", db_path=db_path)
    rows_dgs10 = store.list_market_observations(metric_key="dgs10", db_path=db_path)
    assert rows_vix[0]["value_numeric"] == 22.5
    assert rows_dgs10[0]["value_numeric"] == 4.2


# ---------------------------------------------------------------------------
# Part C: D13 row equivalence â€?batch path produces identical results
# ---------------------------------------------------------------------------

def test_d13_batch_rows_identical_to_single_query_rows(tmp_path):
    """build_historical_percentile_rows must return the same values whether it
    uses batch or per-metric queries (they are now always batch; this test
    verifies the result is still identical to the pre-batch single-query path).
    """
    db_path = tmp_path / "mh.sqlite3"
    start = date(2020, 1, 1)
    # Insert enough history for 5Y window
    _insert_series(db_path, "high_yield_spread", start, 370, source_series="BAMLH0A0HYM2EY", step_days=5)
    _insert_series(db_path, "vix", start, 370, source_series="VIXCLS", step_days=5)
    _insert_series(db_path, "dgs30", start, 370, source_series="DGS30", step_days=5)
    _insert_series(db_path, "dfii10", start, 370, source_series="DFII10", step_days=5)

    expected = [
        percentile.build_metric_payload(spec, db_path=str(db_path))
        for spec in percentile.PERCENTILE_METRIC_SPECS
    ]
    rows = percentile.build_historical_percentile_rows(db_path=str(db_path))

    assert [_stable_d13(row) for row in rows] == [_stable_d13(row) for row in expected]


def test_d13_hy_ig_insufficient_history_gates_unchanged(tmp_path):
    """HY and IG spread percentile blocks when history < minimum_observation_count.
    This gate must not be bypassed by M2 batch optimization.
    """
    db_path = tmp_path / "mh.sqlite3"
    # Insert only 10 observations â€?far below minimum of 60
    start = date(2026, 1, 1)
    for i in range(10):
        _insert(db_path, "high_yield_spread", (start + timedelta(days=i)).isoformat(), float(4 + i * 0.1))
    for i in range(10):
        _insert(db_path, "investment_grade_spread", (start + timedelta(days=i)).isoformat(), float(1 + i * 0.05))

    rows = percentile.build_historical_percentile_rows(db_path=str(db_path))
    by_key = {r["metric_key"]: r for r in rows}

    assert by_key["high_yield_spread_percentile"]["status"] == "insufficient_history"
    assert by_key["high_yield_spread_percentile"]["ai_context_allowed"] is False
    assert by_key["investment_grade_spread_percentile"]["status"] == "insufficient_history"
    assert by_key["investment_grade_spread_percentile"]["ai_context_allowed"] is False


def test_d13_ai_context_allowed_counts_unchanged(tmp_path):
    """With 5Y of official data for the main metrics, ai_context_allowed=True
    count must match expectations. Gate logic must not change under M2.
    """
    db_path = tmp_path / "mh.sqlite3"
    start = date(2020, 1, 1)
    for metric_key, series in [
        ("high_yield_spread", "BAMLH0A0HYM2EY"),
        ("investment_grade_spread", "BAMLC0A0CMEY"),
        ("vix", "VIXCLS"),
        ("dgs30", "DGS30"),
        ("dfii10", "DFII10"),
        ("sp500_drawdown_3m", "SP500"),
        ("nasdaq100_drawdown_3m", "NDX"),
        ("initial_claims_4w_avg", "ICSA"),
        ("continuing_claims_4w_avg", "CCSA"),
    ]:
        _insert_series(db_path, metric_key, start, 370, source_series=series, step_days=5)

    rows = percentile.build_historical_percentile_rows(db_path=str(db_path))
    allowed = [r for r in rows if r.get("ai_context_allowed")]
    # At least the specs with 5Y official data should have ai_context_allowed=True
    assert len(allowed) >= 10


def test_d13_spec_count_unchanged():
    assert len(percentile.PERCENTILE_METRIC_SPECS) == 23


# ---------------------------------------------------------------------------
# Part D: D14 row equivalence â€?batch path produces identical results
# ---------------------------------------------------------------------------

def test_d14_batch_rows_count_unchanged(tmp_path):
    db_path = _db_with_d14_observations(tmp_path, sofr=4.32, effr=4.30, iorb=4.30, cp=4.8, stl=0.2, nfci=0.1, anfci=0.05)

    rows = d14.build_liquidity_funding_rows(db_path=db_path)

    assert len(rows) == len(d14.ALL_METRIC_KEYS)


def test_d14_batch_rows_identical_to_single_query_path(monkeypatch, tmp_path):
    db_path = _db_with_d14_observations(
        tmp_path,
        sofr=4.32,
        effr=4.30,
        iorb=4.30,
        cp=4.8,
        stl=0.2,
        nfci=0.1,
        anfci=0.05,
    )
    original_batch = store.list_market_observations_batch
    monkeypatch.setattr(store, "list_market_observations_batch", lambda *args, **kwargs: None)
    expected = d14.build_liquidity_funding_rows(db_path=db_path)
    monkeypatch.setattr(store, "list_market_observations_batch", original_batch)

    rows = d14.build_liquidity_funding_rows(db_path=db_path)

    assert [_stable_d14(row) for row in rows] == [_stable_d14(row) for row in expected]


def test_d14_ofr_fsi_remains_research_needed(tmp_path):
    """ofr_fsi has no source mapping; must remain research_needed regardless of M2."""
    db_path = _db_with_d14_observations(tmp_path, sofr=4.32, effr=4.30)

    rows = {r["metric_key"]: r for r in d14.build_liquidity_funding_rows(db_path=db_path)}

    assert rows["ofr_fsi"]["status"] == "research_needed"
    assert rows["ofr_fsi"]["source_badge"] == "research_needed"
    assert rows["ofr_fsi"]["ai_context_allowed"] is False


def test_d14_liquidity_funding_status_unchanged_after_batch(tmp_path):
    db_path = _db_with_d14_observations(tmp_path, sofr=4.0, effr=4.0, iorb=4.0, cp=5.2, stl=-0.2, nfci=-0.1, anfci=-0.1)

    rows = {r["metric_key"]: r for r in d14.build_liquidity_funding_rows(db_path=db_path)}

    assert rows["short_term_funding_pressure_status"]["status"] == "pressure"
    assert rows["liquidity_funding_stress_status"]["value"] == "watch"


def test_d14_source_badge_series_date_preserved_after_batch(tmp_path):
    db_path = _db_with_d14_observations(tmp_path, sofr=4.32)

    rows = {r["metric_key"]: r for r in d14.build_liquidity_funding_rows(db_path=db_path)}

    assert rows["sofr"]["source_badge"] == "official"
    assert rows["sofr"]["source_series"] == "SOFR"
    assert rows["sofr"]["observation_date"] == "2026-06-01"


def test_d14_batch_produces_same_spread_values_as_individual_queries(tmp_path):
    db_path = _db_with_d14_observations(tmp_path, sofr=4.35, effr=4.30)

    rows = {r["metric_key"]: r for r in d14.build_liquidity_funding_rows(db_path=db_path)}

    assert rows["sofr_effr_spread"]["value"] == pytest.approx(0.05, abs=1e-5)
    assert rows["sofr_effr_spread"]["source_badge"] == "derived"


def test_d14_missing_db_still_returns_all_rows(tmp_path):
    rows = d14.build_liquidity_funding_rows(db_path=tmp_path / "absent.sqlite3")
    assert len(rows) == len(d14.ALL_METRIC_KEYS)


# ---------------------------------------------------------------------------
# benchmark M2 output fields
# ---------------------------------------------------------------------------

def test_benchmark_output_contains_m2_fields(monkeypatch, tmp_path):
    import json

    _block_network(monkeypatch)

    (tmp_path / "market_snapshot.json").write_text(
        json.dumps({"generated_at": "2026-01-01T00:00:00+00:00", "status": "ok"}),
        encoding="utf-8",
    )

    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
    import benchmark_dashboard_pipeline as bench

    result = bench.run_benchmark(
        reports_dir=tmp_path,
        market_history_db_path=tmp_path / "absent.sqlite3",
    )

    assert result["d13_query_strategy"] == "batch"
    assert result["d14_query_strategy"] == "batch"
    assert result["market_history_batch_api_available"] is True


def test_benchmark_index_available_after_migration(tmp_path):
    """After initialize_market_history_db, idx_market_observations_metric_date exists
    and the benchmark reports market_history_index_metric_date_available=True.
    """
    import json
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
    import benchmark_dashboard_pipeline as bench

    (tmp_path / "market_snapshot.json").write_text(
        json.dumps({"generated_at": "2026-01-01T00:00:00+00:00", "status": "ok"}),
        encoding="utf-8",
    )
    db_path = tmp_path / "mh.sqlite3"
    store.initialize_market_history_db(db_path)

    result = bench.run_benchmark(reports_dir=tmp_path, market_history_db_path=db_path)

    assert result["market_history_index_metric_date_available"] is True
