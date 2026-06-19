from __future__ import annotations

import importlib.util
from pathlib import Path

from data_providers import fred_provider, market_history_store


SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "ingest_official_rates_history.py"
SPEC = importlib.util.spec_from_file_location("ingest_official_rates_history", SCRIPT)
assert SPEC and SPEC.loader
ingest = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(ingest)


def test_fred_response_normalization_and_missing_value_handling():
    payload = {
        "status": "ok",
        "series_id": "DGS10",
        "timestamp": "2026-06-19T00:00:00+00:00",
        "data": [
            {"date": "2026-06-18", "value": "4.25"},
            {"date": "2026-06-17", "value": "."},
            {"date": "", "value": "4.20"},
        ],
    }
    rows = ingest.normalize_fred_series(
        payload,
        series_id="DGS10",
        ingested_at="2026-06-19T01:00:00+00:00",
    )
    assert len(rows) == 1
    assert rows[0]["metric_key"] == "dgs10"
    assert rows[0]["value"] == 4.25
    assert rows[0]["source_badge"] == "official_fallback"
    assert rows[0]["lineage"]["trigger_eligibility"] == "eligible"
    assert fred_provider._parse_observation_value(".") is None


def test_duplicate_observation_upserts(tmp_path):
    db_path = tmp_path / "market.sqlite3"
    row = ingest.normalize_fred_series(
        {
            "status": "ok",
            "series_id": "T10YIE",
            "data": [{"date": "2026-06-18", "value": 2.31}],
        },
        series_id="T10YIE",
        ingested_at="2026-06-19T01:00:00+00:00",
    )[0]
    first = market_history_store.upsert_market_observation(row, db_path=db_path)
    row["value"] = 2.32
    second = market_history_store.upsert_market_observation(row, db_path=db_path)
    assert first["status"] == "inserted"
    assert second["status"] == "updated"
    assert market_history_store.count_observations_by_metric(db_path=db_path) == {
        "t10yie": 1
    }


def test_all_required_series_are_supported():
    assert ingest.RATE_SERIES == {
        "DGS2": {
            "metric_key": "dgs2",
            "unit": "percent",
            "freshness_policy": "business_daily",
        },
        "DGS10": {
            "metric_key": "dgs10",
            "unit": "percent",
            "freshness_policy": "business_daily",
        },
        "DGS30": {
            "metric_key": "dgs30",
            "unit": "percent",
            "freshness_policy": "business_daily",
        },
        "T10Y2Y": {
            "metric_key": "t10y2y",
            "unit": "percentage_points",
            "freshness_policy": "business_daily",
        },
        "T10YIE": {
            "metric_key": "t10yie",
            "unit": "percent",
            "freshness_policy": "business_daily",
        },
        "DFII10": {
            "metric_key": "dfii10",
            "unit": "percent",
            "freshness_policy": "business_daily",
        },
    }


def test_summary_fetches_without_network_and_writes(tmp_path):
    def fake_fetch(series_id: str, limit: int):
        assert limit == 10
        return {
            "status": "ok",
            "series_id": series_id,
            "data": [{"date": "2026-06-18", "value": 1.0}],
        }

    summary = ingest.build_ingest_summary(
        db_path=tmp_path / "market.sqlite3",
        limit=10,
        dry_run=False,
        live=True,
        fetcher=fake_fetch,
    )
    assert summary["inserted_count"] == 6
    assert summary["normalized_observations"] == 6
    assert summary["errors"] == []
