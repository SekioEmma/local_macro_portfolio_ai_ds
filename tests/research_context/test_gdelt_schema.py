from __future__ import annotations

import sqlite3

import pytest

from research_context.gdelt_schema import (
    GdeltEventSummaryBucket,
    GdeltStorySummaryBucket,
)
from research_context.research_context_store import (
    initialize_research_context_db,
    upsert_event_bucket,
)


def _event(**overrides):
    payload = {
        "provider": "gdelt_cloud",
        "query_key": "global_conflict_pressure",
        "window_start": "2026-06-01",
        "window_end": "2026-06-07",
        "group_by": "region",
        "bucket_key": "Europe",
        "event_count": 10,
        "conflict_event_count": 8,
        "cameoplus_event_count": 2,
        "fatality_event_count": 3,
        "fatalities": 7,
        "article_count": 40,
        "avg_significance": 0.5,
        "max_significance": 0.9,
        "avg_goldstein_scale": -3.0,
        "avg_market_sensitivity": 0.4,
        "avg_confidence": 0.8,
        "raw_payload_hash": "a" * 64,
        "ingested_at": "2026-06-19T00:00:00+00:00",
    }
    payload.update(overrides)
    return GdeltEventSummaryBucket(**payload)


def test_event_and_story_schema_default_to_research_only():
    event = _event()
    story = GdeltStorySummaryBucket(
        provider="gdelt_cloud",
        query_key="middle_east_energy_risk",
        window_start="2026-06-01",
        window_end="2026-06-07",
        group_by="date",
        bucket_key="2026-06-01",
        story_count=5,
        article_count=20,
        linked_event_count=3,
        avg_significance=0.4,
        max_significance=0.7,
        avg_linked_event_market_sensitivity=0.2,
        avg_linked_event_goldstein_scale=-1.0,
        avg_confidence=0.8,
        raw_payload_hash="b" * 64,
        ingested_at="2026-06-19T00:00:00+00:00",
    )
    for bucket in (event, story):
        assert bucket.source_badge == "research_context"
        assert bucket.trigger_eligibility == "research_context_only"
        assert bucket.ai_context_allowed is False
        assert "not probability" in bucket.interpretation_boundary


def test_schema_rejects_trigger_or_ai_upgrade():
    with pytest.raises(ValueError, match="trigger"):
        _event(trigger_eligibility="eligible")
    with pytest.raises(ValueError, match="default_false"):
        _event(ai_context_allowed=True)


def test_research_context_store_has_no_article_body_columns(tmp_path):
    db_path = initialize_research_context_db(tmp_path / "research.sqlite3")
    upsert_event_bucket(_event(), db_path=db_path)
    with sqlite3.connect(db_path) as connection:
        columns = {
            row[1]
            for row in connection.execute(
                "PRAGMA table_info(gdelt_event_summary_buckets)"
            )
        }
        count = connection.execute(
            "SELECT COUNT(*) FROM gdelt_event_summary_buckets"
        ).fetchone()[0]
    assert count == 1
    assert not {"article_body", "full_text", "raw_payload"} & columns
