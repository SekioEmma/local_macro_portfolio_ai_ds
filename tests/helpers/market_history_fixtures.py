from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path
from typing import Any, Iterable

from data_quality import market_history_store


def seed_market_history_series_for_tests(
    db_path: Path | str,
    metric_key: str,
    start_date: date,
    count: int,
    *,
    constant: float | None = None,
    source: str = "FRED",
    source_badge: str = "official",
    source_series: str | None = None,
    status: str = "ok",
    freshness_status: str = "historical",
) -> None:
    rows = []
    for index in range(count):
        value = constant if constant is not None else float(index + 1)
        rows.append(
            market_history_observation_for_tests(
                metric_key,
                (start_date + timedelta(days=index)).isoformat(),
                value,
                source=source,
                source_badge=source_badge,
                source_series=source_series,
                status=status,
                freshness_status=freshness_status,
            )
        )
    insert_market_observations_many_for_tests(db_path, rows)


def market_history_observation_for_tests(
    metric_key: str,
    observation_date: str,
    value: Any,
    *,
    source: str = "FRED",
    source_badge: str = "official",
    source_series: str | None = None,
    status: str = "ok",
    freshness_status: str = "historical",
) -> dict[str, Any]:
    return {
        "metric_key": metric_key,
        "observation_date": observation_date,
        "value": value,
        "status": status,
        "source": source,
        "source_badge": source_badge,
        "provider": source,
        "source_series": source_series or metric_key.upper(),
        "generated_at": "2026-01-01T00:00:00+00:00",
        "fetched_at": "2026-01-01T00:00:00+00:00",
        "freshness_status": freshness_status,
        "ai_context_allowed": status == "ok",
        "metric_kind": "raw",
    }


def insert_market_observations_many_for_tests(
    db_path: Path | str,
    rows: Iterable[dict[str, Any] | market_history_store.MarketObservation],
) -> None:
    payloads = [
        market_history_store._validated_observation_payload(row)  # noqa: SLF001
        for row in rows
    ]
    if not payloads:
        return
    path = market_history_store.initialize_market_history_db(db_path=db_path)
    with market_history_store.connect_market_history_db(path) as connection:
        connection.executemany(
            """
            INSERT INTO market_observations (
                metric_key, observation_date, value_numeric, value_text,
                value_type, unit, status, source, source_badge, provider,
                source_series, generated_at, fetched_at, freshness_status,
                ai_context_allowed, metric_kind, lineage_json, raw_hash,
                created_at, updated_at
            )
            VALUES (
                :metric_key, :observation_date, :value_numeric, :value_text,
                :value_type, :unit, :status, :source, :source_badge, :provider,
                :source_series, :generated_at, :fetched_at, :freshness_status,
                :ai_context_allowed, :metric_kind, :lineage_json, :raw_hash,
                :created_at, :updated_at
            )
            ON CONFLICT(metric_key, observation_date, source_badge, source_series)
            DO UPDATE SET
                value_numeric = excluded.value_numeric,
                value_text = excluded.value_text,
                value_type = excluded.value_type,
                unit = excluded.unit,
                status = excluded.status,
                source = excluded.source,
                provider = excluded.provider,
                generated_at = excluded.generated_at,
                fetched_at = excluded.fetched_at,
                freshness_status = excluded.freshness_status,
                ai_context_allowed = excluded.ai_context_allowed,
                metric_kind = excluded.metric_kind,
                lineage_json = excluded.lineage_json,
                raw_hash = excluded.raw_hash,
                updated_at = excluded.updated_at
            """,
            payloads,
        )
        connection.commit()
