from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

from data_providers.source_registry import prefer_source


SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "ingest_official_bls_cpi_history.py"
SPEC = importlib.util.spec_from_file_location("ingest_official_bls_cpi_history", SCRIPT)
assert SPEC and SPEC.loader
ingest = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(ingest)


def test_bls_v1_post_payload_and_chunks():
    assert ingest.split_year_chunks(2000, 2026) == [
        (2000, 2009),
        (2010, 2019),
        (2020, 2026),
    ]
    payload = ingest.build_bls_v1_post_payload(
        ["CUSR0000SA0", "CUSR0000SA0L1E"], 2020, 2026
    )
    assert payload == {
        "seriesid": ["CUSR0000SA0", "CUSR0000SA0L1E"],
        "startyear": "2020",
        "endyear": "2026",
        "catalog": True,
    }
    with pytest.raises(ValueError, match="exceeds"):
        ingest.build_bls_v1_post_payload(["CUSR0000SA0"], 2000, 2010)


def test_response_normalization_and_title_validation():
    rows = ingest.normalize_bls_series(
        {
            "seriesID": "CUSR0000SA0",
            "seriesTitle": "CPI-U All items in U.S. city average, seasonally adjusted",
            "data": [
                {"year": "2025", "period": "M02", "value": "320.1"},
                {"year": "2025", "period": "M13", "value": "999"},
                {"year": "2025", "period": "M01", "value": "-"},
            ],
        },
        ingested_at="2026-06-19T00:00:00+00:00",
    )
    assert rows == [
        {
            "series_id": "CUSR0000SA0",
            "metric_key": "headline_cpi_index",
            "observation_date": "2025-02-01",
            "value": 320.1,
            "title_validation": "response_title_confirmed",
            "ingested_at": "2026-06-19T00:00:00+00:00",
        }
    ]
    with pytest.raises(ValueError, match="title_mismatch"):
        ingest.normalize_bls_series(
            {
                "seriesID": "CUSR0000SA0L1E",
                "seriesTitle": "Wrong title",
                "data": [],
            },
            ingested_at="now",
        )


def test_yoy_calculation_and_official_observation():
    records = [
        {
            "series_id": "CUSR0000SA0",
            "metric_key": "headline_cpi_index",
            "observation_date": "2024-01-01",
            "value": 300.0,
            "title_validation": "series_registry_confirmed_response_id",
            "ingested_at": "now",
        },
        {
            "series_id": "CUSR0000SA0",
            "metric_key": "headline_cpi_index",
            "observation_date": "2025-01-01",
            "value": 309.0,
            "title_validation": "series_registry_confirmed_response_id",
            "ingested_at": "now",
        },
    ]
    yoy = ingest.calculate_yoy(records)
    assert len(yoy) == 1
    assert yoy[0]["value"] == pytest.approx(3.0)
    observation = ingest.build_market_observation(yoy[0], derived=True)
    assert observation["metric_key"] == "headline_cpi_yoy"
    assert observation["provider"] == "bls"
    assert observation["source_badge"] == "official"
    assert observation["lineage"]["trigger_eligibility"] == "eligible"


def test_bls_official_priority_over_fred_fallback():
    assert prefer_source("official", "official_fallback") is True
    assert prefer_source("official_fallback", "official") is False


def test_ingest_uses_chunked_fetcher_and_writes(tmp_path):
    calls = []

    def fake_fetch(series_ids, start_year, end_year):
        calls.append((start_year, end_year))
        return {
            "status": "ok",
            "retrieved_at": "2026-06-19T00:00:00+00:00",
            "series": [
                {
                    "seriesID": series_id,
                    "data": [
                        {"year": str(start_year), "period": "M01", "value": "100"},
                        {"year": str(end_year), "period": "M01", "value": "110"},
                    ],
                }
                for series_id in series_ids
            ],
        }

    summary = ingest.build_ingest_summary(
        start_year=2000,
        end_year=2020,
        db_path=tmp_path / "market.sqlite3",
        dry_run=False,
        live=True,
        fetcher=fake_fetch,
    )
    assert calls == [(2000, 2009), (2010, 2019), (2020, 2020)]
    assert summary["inserted_count"] >= 8
    assert summary["errors"] == []
