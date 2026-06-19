from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

from .gdelt_schema import GdeltEventSummaryBucket, GdeltStorySummaryBucket


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DB_PATH = (
    PROJECT_ROOT / "data" / "research_context" / "research_context.sqlite3"
)


def initialize_research_context_db(db_path: Path | str | None = None) -> Path:
    path = Path(db_path) if db_path is not None else DEFAULT_DB_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path) as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS gdelt_event_summary_buckets (
                provider TEXT NOT NULL,
                query_key TEXT NOT NULL,
                window_start TEXT NOT NULL,
                window_end TEXT NOT NULL,
                group_by_field TEXT NOT NULL,
                bucket_key TEXT NOT NULL,
                event_count INTEGER NOT NULL,
                conflict_event_count INTEGER NOT NULL,
                cameoplus_event_count INTEGER NOT NULL,
                fatality_event_count INTEGER NOT NULL,
                fatalities INTEGER NOT NULL,
                article_count INTEGER NOT NULL,
                avg_significance REAL,
                max_significance REAL,
                avg_goldstein_scale REAL,
                avg_market_sensitivity REAL,
                avg_confidence REAL,
                raw_payload_hash TEXT NOT NULL,
                ingested_at TEXT NOT NULL,
                source_badge TEXT NOT NULL,
                trigger_eligibility TEXT NOT NULL,
                ai_context_allowed INTEGER NOT NULL DEFAULT 0,
                interpretation_boundary TEXT NOT NULL,
                PRIMARY KEY (
                    provider, query_key, window_start, window_end,
                    group_by_field, bucket_key
                )
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS gdelt_story_summary_buckets (
                provider TEXT NOT NULL,
                query_key TEXT NOT NULL,
                window_start TEXT NOT NULL,
                window_end TEXT NOT NULL,
                group_by_field TEXT NOT NULL,
                bucket_key TEXT NOT NULL,
                story_count INTEGER NOT NULL,
                article_count INTEGER NOT NULL,
                linked_event_count INTEGER NOT NULL,
                avg_significance REAL,
                max_significance REAL,
                avg_linked_event_market_sensitivity REAL,
                avg_linked_event_goldstein_scale REAL,
                avg_confidence REAL,
                raw_payload_hash TEXT NOT NULL,
                ingested_at TEXT NOT NULL,
                source_badge TEXT NOT NULL,
                trigger_eligibility TEXT NOT NULL,
                ai_context_allowed INTEGER NOT NULL DEFAULT 0,
                interpretation_boundary TEXT NOT NULL,
                PRIMARY KEY (
                    provider, query_key, window_start, window_end,
                    group_by_field, bucket_key
                )
            )
            """
        )
        connection.commit()
    return path


def upsert_event_bucket(
    bucket: GdeltEventSummaryBucket, *, db_path: Path | str | None = None
) -> None:
    _upsert(bucket.to_record(), "gdelt_event_summary_buckets", db_path=db_path)


def upsert_story_bucket(
    bucket: GdeltStorySummaryBucket, *, db_path: Path | str | None = None
) -> None:
    _upsert(bucket.to_record(), "gdelt_story_summary_buckets", db_path=db_path)


def _upsert(record: dict[str, Any], table: str, *, db_path: Path | str | None) -> None:
    path = initialize_research_context_db(db_path)
    payload = dict(record)
    payload["group_by_field"] = payload.pop("group_by")
    payload["ai_context_allowed"] = 1 if payload["ai_context_allowed"] else 0
    columns = list(payload)
    placeholders = ",".join(f":{column}" for column in columns)
    update_columns = [
        column
        for column in columns
        if column
        not in {
            "provider",
            "query_key",
            "window_start",
            "window_end",
            "group_by_field",
            "bucket_key",
        }
    ]
    updates = ",".join(f"{column}=excluded.{column}" for column in update_columns)
    with sqlite3.connect(path) as connection:
        connection.execute(
            f"""
            INSERT INTO {table} ({','.join(columns)})
            VALUES ({placeholders})
            ON CONFLICT (
                provider, query_key, window_start, window_end,
                group_by_field, bucket_key
            ) DO UPDATE SET {updates}
            """,
            payload,
        )
        connection.commit()
