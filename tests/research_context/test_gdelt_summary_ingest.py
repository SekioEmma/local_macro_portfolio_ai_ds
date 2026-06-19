from __future__ import annotations

import importlib.util
import sqlite3
from pathlib import Path

import pytest

from research_context import gdelt_client


ROOT = Path(__file__).resolve().parents[2]


def _load_script(name):
    path = ROOT / "scripts" / name
    spec = importlib.util.spec_from_file_location(name.removesuffix(".py"), path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


event_ingest = _load_script("ingest_gdelt_event_summary.py")
story_ingest = _load_script("ingest_gdelt_story_summary.py")


def test_url_query_construction_uses_configured_preset():
    request = gdelt_client.build_summary_request(
        summary_kind="events",
        query_key="ukraine_energy_infrastructure",
        window_start="2026-06-01",
        window_end="2026-06-07",
    )
    assert request["url"] == "https://gdeltcloud.com/api/v2/events/summary"
    assert request["params"]["country"] == "Ukraine"
    assert request["params"]["search"] == "energy infrastructure"
    assert request["params"]["group_by"] == "date"


def test_bearer_key_loads_from_environment(monkeypatch):
    monkeypatch.setenv("GDELT_CLOUD_API_KEY", "gdelt_sk_test")
    assert gdelt_client.load_gdelt_api_key() == "gdelt_sk_test"


def test_explicit_window_guard():
    gdelt_client.validate_window("2026-06-01", "2026-06-30")
    with pytest.raises(ValueError, match="exceeds_30_days"):
        gdelt_client.validate_window("2026-05-01", "2026-06-02")


def test_event_response_normalization_hash_and_no_article_body():
    payload = {
        "success": True,
        "group_by": "region",
        "article_body": "must never persist",
        "data": [
            {
                "key": "Europe",
                "event_count": 12,
                "conflict_event_count": 8,
                "cameoplus_event_count": 4,
                "fatality_event_count": 2,
                "fatalities": 6,
                "article_count": 40,
                "avg_significance": 0.42,
                "max_significance": 0.91,
                "metrics": {
                    "goldstein_scale": {"avg": -3.8},
                    "cameoplus": {"market_sensitivity": {"avg": 0.31}},
                    "confidence": {"avg": 0.83},
                },
            }
        ],
    }
    buckets = gdelt_client.normalize_event_summary(
        payload,
        query_key="global_conflict_pressure",
        window_start="2026-06-01",
        window_end="2026-06-07",
        ingested_at="2026-06-19T00:00:00+00:00",
    )
    record = buckets[0].to_record()
    assert record["event_count"] == 12
    assert record["avg_market_sensitivity"] == 0.31
    assert len(record["raw_payload_hash"]) == 64
    assert "article_body" not in record
    assert record["source_badge"] == "research_context"


def test_story_ingest_writes_aggregate_bucket_only(tmp_path):
    def requester(**kwargs):
        return {
            "status": "ok",
            "retrieved_at": "2026-06-19T00:00:00+00:00",
            "raw_payload_hash": "c" * 64,
            "payload": {
                "success": True,
                "group_by": "category",
                "data": [
                    {
                        "key": "energy",
                        "story_count": 5,
                        "article_count": 20,
                        "linked_event_count": 3,
                        "avg_significance": 0.4,
                        "max_significance": 0.7,
                        "metrics": {
                            "linked_events": {
                                "goldstein_scale": {"avg": -1.2},
                                "cameoplus": {
                                    "market_sensitivity": {"avg": 0.25}
                                },
                                "confidence": {"avg": 0.8},
                            }
                        },
                    }
                ],
            },
        }

    db_path = tmp_path / "research.sqlite3"
    summary = story_ingest.build_ingest_summary(
        query_key="middle_east_energy_risk",
        window_start="2026-06-01",
        window_end="2026-06-07",
        db_path=db_path,
        dry_run=False,
        live=True,
        requester=requester,
    )
    assert summary["upserted_buckets"] == 1
    with sqlite3.connect(db_path) as connection:
        row = connection.execute(
            "SELECT source_badge, trigger_eligibility, ai_context_allowed "
            "FROM gdelt_story_summary_buckets"
        ).fetchone()
    assert row == ("research_context", "research_context_only", 0)


def test_event_ingest_reports_missing_key_without_network(monkeypatch):
    monkeypatch.delenv("GDELT_CLOUD_API_KEY", raising=False)
    summary = event_ingest.build_ingest_summary(
        query_key="global_conflict_pressure",
        window_start="2026-06-01",
        window_end="2026-06-07",
        live=True,
    )
    assert summary["status"] == "not_available"
    assert summary["normalized_buckets"] == 0
