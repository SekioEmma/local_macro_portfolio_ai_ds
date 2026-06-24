from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time, timedelta
from pathlib import Path
import sqlite3
from typing import Any, Callable
from zoneinfo import ZoneInfo

from app_backend.services.economic_calendar_contracts import (
    EconomicCalendarAdmissionError,
    EconomicCalendarEventInput,
    admit_calendar_event,
    resolve_calendar_event_key,
)


PROJECT_ROOT = Path(__file__).resolve().parents[3]
_DEFAULT_DB_PATH = PROJECT_ROOT / "data" / "economic_calendar.sqlite"
_SCHEMA_PATH = Path(__file__).with_name("economic_calendar_schema.sql")
_ET = ZoneInfo("America/New_York")

NowProvider = Callable[[], datetime]


@dataclass(frozen=True)
class EconomicCalendarEventRecord:
    id: int
    event_key: str
    event_name: str
    release_date: str
    release_time_et: str
    source: str
    source_domain: str
    ingested_at: str
    created_at: str
    updated_at: str


@dataclass(frozen=True)
class EconomicCalendarMutationResult:
    status: str
    created_count: int
    updated_count: int
    event_count: int


class EconomicCalendarService:
    def __init__(
        self,
        db_path: Path = _DEFAULT_DB_PATH,
        now_provider: NowProvider | None = None,
    ) -> None:
        self._db_path = db_path
        self._now_provider = now_provider or _default_now_et

    def upsert_events(
        self,
        events: list[EconomicCalendarEventInput],
    ) -> EconomicCalendarMutationResult:
        if not events:
            raise EconomicCalendarAdmissionError("empty_event_batch")
        admitted_events = [admit_calendar_event(event) for event in events]
        self._validate_calendar_root()

        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        created_count = 0
        updated_count = 0
        now = _utc_now()
        with self._connect_existing_or_new() as connection:
            self._initialize_schema(connection)
            for event in admitted_events:
                existing_id = self._existing_id(
                    connection,
                    event.event_key.value,
                    event.release_date,
                    event.release_time_et,
                )
                if existing_id is None:
                    created_count += 1
                    connection.execute(
                        """
                        INSERT INTO economic_calendar (
                            event_key, event_name, release_date, release_time_et,
                            source, source_url, source_domain, ingested_at,
                            created_at, updated_at
                        )
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            event.event_key.value,
                            event.event_name,
                            event.release_date,
                            event.release_time_et,
                            event.source,
                            event.source_url,
                            event.source_domain,
                            event.ingested_at,
                            now,
                            now,
                        ),
                    )
                else:
                    updated_count += 1
                    connection.execute(
                        """
                        UPDATE economic_calendar
                        SET event_name = ?,
                            source = ?,
                            source_url = ?,
                            source_domain = ?,
                            ingested_at = ?,
                            updated_at = ?
                        WHERE id = ?
                        """,
                        (
                            event.event_name,
                            event.source,
                            event.source_url,
                            event.source_domain,
                            event.ingested_at,
                            now,
                            existing_id,
                        ),
                    )
        return EconomicCalendarMutationResult(
            status="ok",
            created_count=created_count,
            updated_count=updated_count,
            event_count=len(admitted_events),
        )

    def next_releases(self, window_days: int = 30) -> list[EconomicCalendarEventRecord]:
        if isinstance(window_days, bool) or not isinstance(window_days, int) or not 1 <= window_days <= 365:
            raise EconomicCalendarAdmissionError("invalid_window_days")
        self._validate_calendar_root()
        if not self._db_path.exists():
            return []
        now_et = _coerce_et(self._now_provider())
        horizon = now_et + timedelta(days=window_days)
        with self._connect_existing() as connection:
            rows = connection.execute(
                """
                SELECT id, event_key, event_name, release_date, release_time_et,
                       source, source_domain, ingested_at, created_at, updated_at
                FROM economic_calendar
                ORDER BY release_date ASC, release_time_et ASC, id ASC
                """
            ).fetchall()
        records = [_record_from_row(row) for row in rows]
        return [
            record
            for record in records
            if now_et <= _release_at_et(record) <= horizon
        ]

    def events_by_name(
        self,
        name: str,
        limit: int = 5,
    ) -> list[EconomicCalendarEventRecord]:
        if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 100:
            raise EconomicCalendarAdmissionError("invalid_limit")
        event_name = _resolve_event_name(name)
        self._validate_calendar_root()
        if not self._db_path.exists():
            return []
        with self._connect_existing() as connection:
            rows = connection.execute(
                """
                SELECT id, event_key, event_name, release_date, release_time_et,
                       source, source_domain, ingested_at, created_at, updated_at
                FROM economic_calendar
                WHERE event_name = ?
                ORDER BY release_date DESC, release_time_et DESC, id DESC
                LIMIT ?
                """,
                (event_name, limit),
            ).fetchall()
            return [_record_from_row(row) for row in rows]

    def _validate_calendar_root(self) -> None:
        cursor = self._db_path
        while True:
            try:
                if cursor.is_symlink():
                    raise EconomicCalendarAdmissionError("invalid_calendar_root")
            except OSError as exc:
                raise EconomicCalendarAdmissionError("invalid_calendar_root") from exc
            if cursor == cursor.parent:
                return
            cursor = cursor.parent

    def _connect_existing_or_new(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self._db_path)
        connection.execute("PRAGMA foreign_keys=ON")
        return connection

    def _connect_existing(self) -> sqlite3.Connection:
        connection = sqlite3.connect(f"file:{self._db_path}?mode=rw", uri=True)
        connection.execute("PRAGMA foreign_keys=ON")
        return connection

    def _initialize_schema(self, connection: sqlite3.Connection) -> None:
        connection.executescript(_SCHEMA_PATH.read_text(encoding="utf-8"))

    def _existing_id(
        self,
        connection: sqlite3.Connection,
        event_key: str,
        release_date: str,
        release_time_et: str,
    ) -> int | None:
        row = connection.execute(
            """
            SELECT id
            FROM economic_calendar
            WHERE event_key = ? AND release_date = ? AND release_time_et = ?
            """,
            (event_key, release_date, release_time_et),
        ).fetchone()
        return int(row[0]) if row is not None else None


def build_default_economic_calendar_service() -> EconomicCalendarService:
    return EconomicCalendarService()


def _resolve_event_name(name: str) -> str:
    normalized = " ".join(name.split()).casefold()
    for event_key in [
        "consumer_price_index",
        "employment_situation",
        "personal_income_and_outlays",
        "gross_domestic_product",
        "fomc_statement",
    ]:
        metadata = resolve_calendar_event_key(event_key)
        if metadata.event_name.casefold() == normalized:
            return metadata.event_name
    raise EconomicCalendarAdmissionError("unsupported_event_key")


def _record_from_row(row: Any) -> EconomicCalendarEventRecord:
    return EconomicCalendarEventRecord(
        id=int(row[0]),
        event_key=str(row[1]),
        event_name=str(row[2]),
        release_date=str(row[3]),
        release_time_et=str(row[4]),
        source=str(row[5]),
        source_domain=str(row[6]),
        ingested_at=str(row[7]),
        created_at=str(row[8]),
        updated_at=str(row[9]),
    )


def _release_at_et(record: EconomicCalendarEventRecord) -> datetime:
    release_date = datetime.fromisoformat(record.release_date).date()
    hour, minute = (int(part) for part in record.release_time_et.split(":"))
    return datetime.combine(release_date, time(hour=hour, minute=minute), tzinfo=_ET)


def _coerce_et(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=_ET)
    return value.astimezone(_ET)


def _default_now_et() -> datetime:
    return datetime.now(_ET)


def _utc_now() -> str:
    return datetime.now(ZoneInfo("UTC")).isoformat()


__all__ = [
    "EconomicCalendarEventRecord",
    "EconomicCalendarMutationResult",
    "EconomicCalendarService",
    "build_default_economic_calendar_service",
]
