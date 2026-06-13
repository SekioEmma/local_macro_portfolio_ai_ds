from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_MARKET_HISTORY_DB_PATH = PROJECT_ROOT / "data" / "market_history" / "market_history.sqlite3"
CURRENT_SCHEMA_VERSION = 1
MAX_LIMIT = 5000
BLOCKED_SOURCE_BADGES = {"missing", "research_needed", "search-derived"}
BLOCKED_STATUSES = {
    "missing",
    "research_needed",
    "not_available",
    "insufficient_history",
    "stale",
}
SECRET_PATTERNS = (
    re.compile(r"sk-[A-Za-z0-9_-]{20,}"),
    re.compile(r"[A-Z_]*API_KEY", re.IGNORECASE),
)
HOLDINGS_TOKENS = {
    "holding",
    "holdings",
    "ticker",
    "fund_code",
    "amount",
    "current_value",
    "market_value",
    "cost_basis",
}


class MarketHistoryValidationError(ValueError):
    pass


@dataclass(frozen=True)
class MarketObservation:
    metric_key: str
    observation_date: str
    value: float | str | bool
    value_text: str | None = None
    unit: str | None = None
    status: str = "ok"
    source: str | None = None
    source_badge: str = "missing"
    provider: str | None = None
    source_series: str | None = None
    generated_at: str | None = None
    fetched_at: str | None = None
    freshness_status: str | None = None
    ai_context_allowed: bool = False
    metric_kind: str = "raw"
    lineage: dict[str, Any] | None = None
    raw_hash: str | None = None


def get_default_market_history_db_path() -> Path:
    return DEFAULT_MARKET_HISTORY_DB_PATH


def connect_market_history_db(db_path: Path | str | None = None) -> sqlite3.Connection:
    path = Path(db_path) if db_path is not None else get_default_market_history_db_path()
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    return connection


def initialize_market_history_db(db_path: Path | str | None = None) -> Path:
    path = Path(db_path) if db_path is not None else get_default_market_history_db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with connect_market_history_db(path) as connection:
        _run_migrations(connection)
    return path


def get_market_history_schema_version(
    db_path: Path | str | None = None,
    connection: sqlite3.Connection | None = None,
) -> int:
    if connection is not None:
        return _schema_version(connection)
    path = Path(db_path) if db_path is not None else get_default_market_history_db_path()
    if not path.exists():
        return 0
    with connect_market_history_db(path) as active:
        return _schema_version(active)


def upsert_market_observation(
    observation: MarketObservation | dict[str, Any],
    *,
    db_path: Path | str | None = None,
    connection: sqlite3.Connection | None = None,
) -> dict[str, Any]:
    payload = _validated_observation_payload(observation)
    close_connection = False
    active = connection
    if active is None:
        path = initialize_market_history_db(db_path)
        active = connect_market_history_db(path)
        close_connection = True
    try:
        existing = active.execute(
            """
            SELECT id FROM market_observations
            WHERE metric_key = ?
              AND observation_date = ?
              AND source_badge = ?
              AND IFNULL(source_series, '') = IFNULL(?, '')
            """,
            (
                payload["metric_key"],
                payload["observation_date"],
                payload["source_badge"],
                payload["source_series"],
            ),
        ).fetchone()
        active.execute(
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
            payload,
        )
        active.commit()
        return {
            "status": "updated" if existing else "inserted",
            "metric_key": payload["metric_key"],
        }
    finally:
        if close_connection and active is not None:
            active.close()


def list_market_observations(
    *,
    metric_key: str | None = None,
    limit: int = 100,
    db_path: Path | str | None = None,
) -> list[dict[str, Any]]:
    path = Path(db_path) if db_path is not None else get_default_market_history_db_path()
    if not path.exists():
        return []
    bounded_limit = _bounded_limit(limit)
    with connect_market_history_db(path) as connection:
        if metric_key:
            rows = connection.execute(
                """
                SELECT * FROM market_observations
                WHERE metric_key = ?
                ORDER BY observation_date DESC, id DESC
                LIMIT ?
                """,
                (metric_key, bounded_limit),
            ).fetchall()
        else:
            rows = connection.execute(
                """
                SELECT * FROM market_observations
                ORDER BY observation_date DESC, id DESC
                LIMIT ?
                """,
                (bounded_limit,),
            ).fetchall()
    return [_row_to_observation(row) for row in rows]


def get_latest_observation(
    metric_key: str,
    *,
    db_path: Path | str | None = None,
) -> dict[str, Any] | None:
    rows = list_market_observations(metric_key=metric_key, limit=1, db_path=db_path)
    return rows[0] if rows else None


def count_observations_by_metric(
    *,
    db_path: Path | str | None = None,
) -> dict[str, int]:
    path = Path(db_path) if db_path is not None else get_default_market_history_db_path()
    if not path.exists():
        return {}
    with connect_market_history_db(path) as connection:
        rows = connection.execute(
            """
            SELECT metric_key, COUNT(*) AS count
            FROM market_observations
            GROUP BY metric_key
            ORDER BY metric_key
            """
        ).fetchall()
    return {row["metric_key"]: int(row["count"]) for row in rows}


def get_market_history_summary(
    *,
    db_path: Path | str | None = None,
) -> dict[str, Any]:
    path = Path(db_path) if db_path is not None else get_default_market_history_db_path()
    if not path.exists():
        return {
            "market_history_db_exists": False,
            "market_history_schema_version": 0,
            "market_history_metric_count": 0,
            "market_history_observation_count": 0,
            "observations_by_metric": {},
            "latest_observation_by_metric": {},
        }
    counts = count_observations_by_metric(db_path=path)
    latest = {
        metric_key: item["observation_date"]
        for metric_key in counts
        for item in [get_latest_observation(metric_key, db_path=path)]
        if item is not None
    }
    return {
        "market_history_db_exists": True,
        "market_history_schema_version": get_market_history_schema_version(db_path=path),
        "market_history_metric_count": len(counts),
        "market_history_observation_count": sum(counts.values()),
        "observations_by_metric": counts,
        "latest_observation_by_metric": latest,
    }


def _run_migrations(connection: sqlite3.Connection) -> None:
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_migrations (
            version INTEGER PRIMARY KEY,
            applied_at TEXT NOT NULL
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS market_observations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            metric_key TEXT NOT NULL,
            observation_date TEXT NOT NULL,
            value_numeric REAL,
            value_text TEXT,
            value_type TEXT NOT NULL,
            unit TEXT,
            status TEXT NOT NULL,
            source TEXT,
            source_badge TEXT NOT NULL,
            provider TEXT,
            source_series TEXT NOT NULL DEFAULT '',
            generated_at TEXT,
            fetched_at TEXT NOT NULL,
            freshness_status TEXT,
            ai_context_allowed INTEGER NOT NULL DEFAULT 0,
            metric_kind TEXT NOT NULL DEFAULT 'raw',
            lineage_json TEXT NOT NULL DEFAULT '{}',
            raw_hash TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            UNIQUE(metric_key, observation_date, source_badge, source_series)
        )
        """
    )
    connection.execute(
        """
        INSERT OR IGNORE INTO schema_migrations (version, applied_at)
        VALUES (?, ?)
        """,
        (CURRENT_SCHEMA_VERSION, _utc_now()),
    )
    connection.commit()


def _schema_version(connection: sqlite3.Connection) -> int:
    row = connection.execute("SELECT MAX(version) AS version FROM schema_migrations").fetchone()
    if row is None or row["version"] is None:
        return 0
    return int(row["version"])


def _validated_observation_payload(observation: MarketObservation | dict[str, Any]) -> dict[str, Any]:
    raw = observation.__dict__ if isinstance(observation, MarketObservation) else dict(observation)
    _assert_safe(raw)
    metric_key = _required_text(raw.get("metric_key"), "metric_key")
    if metric_key in {"holdings_updated_at"}:
        raise MarketHistoryValidationError("portfolio local rows are not market observations")
    observation_date = _required_text(raw.get("observation_date"), "observation_date")
    value = raw.get("value")
    if value is None:
        raise MarketHistoryValidationError("value is required")
    source_badge = _required_text(raw.get("source_badge"), "source_badge")
    if source_badge in BLOCKED_SOURCE_BADGES:
        raise MarketHistoryValidationError(f"source_badge_{source_badge}")
    status = _required_text(raw.get("status"), "status")
    if status in BLOCKED_STATUSES:
        raise MarketHistoryValidationError(f"status_{status}")
    metric_kind = _text_or_default(raw.get("metric_kind"), "raw")
    lineage = raw.get("lineage") if isinstance(raw.get("lineage"), dict) else {}
    if (metric_kind == "derived" or source_badge == "derived") and not lineage:
        raise MarketHistoryValidationError("derived observations require lineage")
    value_numeric, value_type = _value_fields(value)
    source_series = _text_or_default(raw.get("source_series"), "")
    now = _utc_now()
    payload = {
        "metric_key": metric_key,
        "observation_date": observation_date,
        "value_numeric": value_numeric,
        "value_text": _text_or_none(raw.get("value_text")) or str(value),
        "value_type": value_type,
        "unit": _text_or_none(raw.get("unit")),
        "status": status,
        "source": _text_or_none(raw.get("source")),
        "source_badge": source_badge,
        "provider": _text_or_none(raw.get("provider")) or _text_or_none(raw.get("source")),
        "source_series": source_series,
        "generated_at": _text_or_none(raw.get("generated_at")),
        "fetched_at": _text_or_none(raw.get("fetched_at")) or now,
        "freshness_status": _text_or_none(raw.get("freshness_status")),
        "ai_context_allowed": 1 if bool(raw.get("ai_context_allowed")) else 0,
        "metric_kind": metric_kind,
        "lineage_json": json.dumps(lineage, ensure_ascii=True, sort_keys=True),
        "raw_hash": _text_or_none(raw.get("raw_hash")),
        "created_at": now,
        "updated_at": now,
    }
    payload["raw_hash"] = payload["raw_hash"] or _payload_hash(payload)
    return payload


def _row_to_observation(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": row["id"],
        "metric_key": row["metric_key"],
        "observation_date": row["observation_date"],
        "value_numeric": row["value_numeric"],
        "value_text": row["value_text"],
        "value_type": row["value_type"],
        "unit": row["unit"],
        "status": row["status"],
        "source": row["source"],
        "source_badge": row["source_badge"],
        "provider": row["provider"],
        "source_series": row["source_series"] or None,
        "generated_at": row["generated_at"],
        "fetched_at": row["fetched_at"],
        "freshness_status": row["freshness_status"],
        "ai_context_allowed": bool(row["ai_context_allowed"]),
        "metric_kind": row["metric_kind"],
        "lineage": json.loads(row["lineage_json"] or "{}"),
        "raw_hash": row["raw_hash"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def _value_fields(value: Any) -> tuple[float | None, str]:
    if isinstance(value, bool):
        return (1.0 if value else 0.0), "bool"
    if isinstance(value, (int, float)):
        return float(value), "number"
    return None, "text"


def _assert_safe(value: Any) -> None:
    text = json.dumps(value, ensure_ascii=False, default=str).lower()
    if any(pattern.search(text) for pattern in SECRET_PATTERNS):
        raise MarketHistoryValidationError("observation contains secret-like content")
    if any(token in text for token in HOLDINGS_TOKENS):
        raise MarketHistoryValidationError("observation contains holdings-like content")
    forbidden_raw_keys = ("raw_provider_response", "raw_prompt", "raw_output", "raw_holdings")
    if any(key in text for key in forbidden_raw_keys):
        raise MarketHistoryValidationError("observation contains raw payload content")


def _required_text(value: Any, field_name: str) -> str:
    text = _text_or_none(value)
    if not text:
        raise MarketHistoryValidationError(f"{field_name} is required")
    return text


def _text_or_default(value: Any, default: str) -> str:
    text = _text_or_none(value)
    return text if text is not None else default


def _text_or_none(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _bounded_limit(limit: int) -> int:
    try:
        parsed = int(limit)
    except (TypeError, ValueError):
        return 100
    return max(1, min(parsed, MAX_LIMIT))


def _payload_hash(payload: dict[str, Any]) -> str:
    data = json.dumps(
        {key: value for key, value in payload.items() if key not in {"raw_hash", "created_at", "updated_at"}},
        ensure_ascii=True,
        sort_keys=True,
        default=str,
    )
    return hashlib.sha256(data.encode("utf-8")).hexdigest()


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()
