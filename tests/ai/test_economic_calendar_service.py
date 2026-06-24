from __future__ import annotations

from dataclasses import fields, is_dataclass
from datetime import datetime
import inspect
import json
from pathlib import Path
import re
import sqlite3
from zoneinfo import ZoneInfo

import pytest

from app_backend.services import economic_calendar_service as service_module
from app_backend.services.economic_calendar_contracts import (
    EconomicCalendarAdmissionError,
    EconomicCalendarEventInput,
)
from app_backend.services.economic_calendar_service import (
    EconomicCalendarEventRecord,
    EconomicCalendarMutationResult,
    EconomicCalendarService,
    build_default_economic_calendar_service,
)


ROOT = Path(__file__).parents[2]
SERVICE_SOURCE = ROOT / "src" / "app_backend" / "services" / "economic_calendar_service.py"
SEED_PATH = ROOT / "data" / "economic_calendar_seed.json"
ET = ZoneInfo("America/New_York")


def _paths(tmp_path: Path) -> tuple[Path, Path]:
    return tmp_path / "economic_calendar.sqlite", tmp_path / "calendar_db"


def _now(value: str = "2001-01-15T08:00:00-05:00"):
    parsed = datetime.fromisoformat(value)
    return lambda: parsed


def _service(tmp_path: Path, now: str = "2001-01-15T08:00:00-05:00") -> EconomicCalendarService:
    db_path, _db_parent = _paths(tmp_path)
    return EconomicCalendarService(db_path=db_path, now_provider=_now(now))


def _event(**overrides: str) -> EconomicCalendarEventInput:
    values = {
        "event_key": "consumer_price_index",
        "release_date": "2001-01-15",
        "release_time_et": "08:30",
        "source_url": "https://www.bls.gov/cpi/",
        "ingested_at": "2001-01-01T00:00:00+00:00",
    }
    values.update(overrides)
    return EconomicCalendarEventInput(**values)


def _fixture_inputs() -> list[EconomicCalendarEventInput]:
    fixture = json.loads(SEED_PATH.read_text(encoding="utf-8"))
    return [EconomicCalendarEventInput(**event) for event in fixture["events"]]


def _connect(db_path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(db_path)
    connection.execute("PRAGMA foreign_keys=ON")
    return connection


def _make_file_symlink(link_path: Path, target_path: Path) -> None:
    try:
        link_path.symlink_to(target_path)
    except NotImplementedError as exc:
        pytest.skip(f"file symlink creation is unavailable: {exc.__class__.__name__}")
    except OSError as exc:
        if isinstance(exc, PermissionError) or getattr(exc, "winerror", None) == 1314:
            pytest.skip(f"file symlink creation is unavailable: {exc.__class__.__name__}")
        raise


def _make_dir_symlink(link_path: Path, target_path: Path) -> None:
    target_path.mkdir(parents=True, exist_ok=True)
    try:
        link_path.symlink_to(target_path, target_is_directory=True)
    except NotImplementedError as exc:
        pytest.skip(f"directory symlink creation is unavailable: {exc.__class__.__name__}")
    except OSError as exc:
        if isinstance(exc, PermissionError) or getattr(exc, "winerror", None) == 1314:
            pytest.skip(f"directory symlink creation is unavailable: {exc.__class__.__name__}")
        raise


def test_import_construction_and_default_factory_create_no_tmp_files(tmp_path: Path) -> None:
    db_path, db_parent = _paths(tmp_path)
    service = EconomicCalendarService(db_path=db_path)
    default_service = build_default_economic_calendar_service()
    assert isinstance(service, EconomicCalendarService)
    assert isinstance(default_service, EconomicCalendarService)
    assert not db_path.exists()
    assert not db_parent.exists()


def test_default_factory_is_repo_root_anchored_not_cwd(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    service = build_default_economic_calendar_service()
    assert service._db_path == service_module.PROJECT_ROOT / "data" / "economic_calendar.sqlite"
    assert service._db_path != tmp_path / "data" / "economic_calendar.sqlite"
    assert not (tmp_path / "data").exists()


def test_queries_missing_db_return_empty_and_create_no_files(tmp_path: Path) -> None:
    db_path, db_parent = _paths(tmp_path)
    service = _service(tmp_path)
    assert service.next_releases() == []
    assert service.events_by_name("Consumer Price Index") == []
    assert not db_path.exists()
    assert not db_parent.exists()


def test_custom_tmp_path_service_supports_upsert_and_queries(tmp_path: Path) -> None:
    service = _service(tmp_path)
    result = service.upsert_events([_event()])
    assert result == EconomicCalendarMutationResult(status="ok", created_count=1, updated_count=0, event_count=1)
    assert [item.event_key for item in service.next_releases(window_days=1)] == ["consumer_price_index"]
    assert [item.event_key for item in service.events_by_name("Consumer Price Index")] == ["consumer_price_index"]


def test_explicit_fixture_inputs_can_be_upserted(tmp_path: Path) -> None:
    result = _service(tmp_path).upsert_events(_fixture_inputs())
    assert result.status == "ok"
    assert result.created_count == 5
    assert result.updated_count == 0
    assert result.event_count == 5


def test_fixture_upsert_writes_all_five_event_types(tmp_path: Path) -> None:
    db_path, _db_parent = _paths(tmp_path)
    _service(tmp_path).upsert_events(_fixture_inputs())
    with _connect(db_path) as connection:
        keys = {row[0] for row in connection.execute("SELECT event_key FROM economic_calendar").fetchall()}
    assert keys == {
        "consumer_price_index",
        "employment_situation",
        "personal_income_and_outlays",
        "gross_domestic_product",
        "fomc_statement",
    }


@pytest.mark.parametrize(
    ("event_name", "event_key", "source", "source_domain"),
    [
        ("Consumer Price Index", "consumer_price_index", "BLS", "www.bls.gov"),
        ("Employment Situation", "employment_situation", "BLS", "www.bls.gov"),
        ("Personal Income and Outlays", "personal_income_and_outlays", "BEA", "www.bea.gov"),
        ("Gross Domestic Product", "gross_domestic_product", "BEA", "www.bea.gov"),
        ("FOMC Statement", "fomc_statement", "Federal Reserve", "www.federalreserve.gov"),
    ],
)
def test_fixture_records_preserve_catalog_metadata(
    tmp_path: Path,
    event_name: str,
    event_key: str,
    source: str,
    source_domain: str,
) -> None:
    service = _service(tmp_path, now="2001-01-01T00:00:00-05:00")
    service.upsert_events(_fixture_inputs())
    record = service.events_by_name(event_name)[0]
    assert record.event_key == event_key
    assert record.source == source
    assert record.source_domain == source_domain


def test_schema_version_unique_and_indexes_exist_after_upsert(tmp_path: Path) -> None:
    db_path, _db_parent = _paths(tmp_path)
    _service(tmp_path).upsert_events([_event()])
    with _connect(db_path) as connection:
        version = connection.execute("SELECT version FROM schema_migrations").fetchone()[0]
        indexes = {
            row[1]
            for row in connection.execute("PRAGMA index_list(economic_calendar)").fetchall()
        }
    assert version == 1
    assert "idx_economic_calendar_release_time" in indexes
    assert "idx_economic_calendar_event_key_release" in indexes
    assert "idx_economic_calendar_source_release" in indexes
    assert any("autoindex" in item for item in indexes)


def test_same_key_date_time_update_preserves_id_and_counts_updated(tmp_path: Path) -> None:
    service = _service(tmp_path)
    created = service.upsert_events([_event()])
    updated = service.upsert_events(
        [
            _event(
                source_url="https://calendar.bls.gov/",
                ingested_at="2001-01-02T00:00:00+00:00",
            )
        ]
    )
    records = service.events_by_name("Consumer Price Index")
    assert created.created_count == 1
    assert updated.created_count == 0
    assert updated.updated_count == 1
    assert len(records) == 1
    assert records[0].id == 1
    assert records[0].source_domain == "calendar.bls.gov"


def test_new_event_creates_new_row(tmp_path: Path) -> None:
    service = _service(tmp_path)
    service.upsert_events([_event()])
    result = service.upsert_events([_event(release_date="2001-01-16")])
    assert result.created_count == 1
    assert len(service.events_by_name("Consumer Price Index", limit=10)) == 2


@pytest.mark.parametrize(
    "bad_event",
    [
        _event(event_key="unknown"),
        _event(release_date="2001-99-01"),
        _event(release_time_et="08:30:00"),
        _event(ingested_at="2001-01-01T00:00:00"),
        _event(source_url="https://bea.gov/data/"),
        _event(source_url="https://bls.gov.evil.example/cpi/"),
        _event(source_url="https://www.bls.gov/cpi/?x=1"),
        _event(source_url="https://www.bls.gov/cpi/#frag"),
        _event(source_url="https://user@www.bls.gov/cpi/"),
        _event(source_url="https://www.bls.gov:443/cpi/"),
    ],
)
def test_invalid_batch_creates_no_db_or_directory(tmp_path: Path, bad_event: EconomicCalendarEventInput) -> None:
    db_path, db_parent = _paths(tmp_path)
    service = _service(tmp_path)
    with pytest.raises(EconomicCalendarAdmissionError):
        service.upsert_events([_event(), bad_event])
    assert not db_path.exists()
    assert not db_parent.exists()


def test_empty_batch_rejected_without_creating_db(tmp_path: Path) -> None:
    db_path, db_parent = _paths(tmp_path)
    with pytest.raises(EconomicCalendarAdmissionError) as exc_info:
        _service(tmp_path).upsert_events([])
    assert exc_info.value.code == "empty_event_batch"
    assert not db_path.exists()
    assert not db_parent.exists()


def test_upsert_result_does_not_expose_url_input_or_db_path(tmp_path: Path) -> None:
    result = _service(tmp_path).upsert_events([_event()])
    serialized = repr(result)
    assert "https://" not in serialized
    assert "economic_calendar.sqlite" not in serialized
    assert "source_url" not in serialized


def test_next_releases_uses_injected_et_now_and_excludes_past(tmp_path: Path) -> None:
    service = _service(tmp_path, now="2001-01-15T08:30:00-05:00")
    service.upsert_events(
        [
            _event(release_date="2001-01-15", release_time_et="08:29"),
            _event(release_date="2001-01-15", release_time_et="08:30"),
            _event(release_date="2001-01-16", release_time_et="08:30"),
        ]
    )
    assert [record.release_time_et for record in service.next_releases(window_days=1)] == ["08:30", "08:30"]


def test_next_releases_horizon_boundary_is_inclusive(tmp_path: Path) -> None:
    service = _service(tmp_path, now="2001-01-15T08:30:00-05:00")
    service.upsert_events(
        [
            _event(release_date="2001-01-16", release_time_et="08:30"),
            _event(release_date="2001-01-16", release_time_et="08:31"),
        ]
    )
    assert [record.release_time_et for record in service.next_releases(window_days=1)] == ["08:30"]


def test_next_releases_sort_order(tmp_path: Path) -> None:
    service = _service(tmp_path, now="2001-01-01T00:00:00-05:00")
    service.upsert_events(
        [
            _event(release_date="2001-01-17", release_time_et="09:00"),
            _event(release_date="2001-01-16", release_time_et="10:00"),
            _event(release_date="2001-01-16", release_time_et="08:00"),
        ]
    )
    assert [(item.release_date, item.release_time_et) for item in service.next_releases(window_days=30)] == [
        ("2001-01-16", "08:00"),
        ("2001-01-16", "10:00"),
        ("2001-01-17", "09:00"),
    ]


@pytest.mark.parametrize("window_days", [0, -1, 366, True, "30", 1.5])
def test_next_releases_rejects_invalid_window_days(tmp_path: Path, window_days) -> None:
    with pytest.raises(EconomicCalendarAdmissionError) as exc_info:
        _service(tmp_path).next_releases(window_days=window_days)
    assert exc_info.value.code == "invalid_window_days"


def test_events_by_name_exact_match_with_casefold_and_whitespace(tmp_path: Path) -> None:
    service = _service(tmp_path)
    service.upsert_events(_fixture_inputs())
    assert [item.event_key for item in service.events_by_name("  consumer   price index  ")] == [
        "consumer_price_index"
    ]


@pytest.mark.parametrize(
    ("query_name", "expected_key"),
    [
        ("Consumer Price Index", "consumer_price_index"),
        ("Employment Situation", "employment_situation"),
        ("Personal Income and Outlays", "personal_income_and_outlays"),
        ("Gross Domestic Product", "gross_domestic_product"),
        ("FOMC Statement", "fomc_statement"),
    ],
)
def test_events_by_name_matches_each_catalog_name(
    tmp_path: Path,
    query_name: str,
    expected_key: str,
) -> None:
    service = _service(tmp_path)
    service.upsert_events(_fixture_inputs())
    assert [item.event_key for item in service.events_by_name(query_name)] == [expected_key]


def test_events_by_name_rejects_unknown_name(tmp_path: Path) -> None:
    with pytest.raises(EconomicCalendarAdmissionError) as exc_info:
        _service(tmp_path).events_by_name("Consumer")
    assert exc_info.value.code == "unsupported_event_key"


def test_events_by_name_descending_history_sort(tmp_path: Path) -> None:
    service = _service(tmp_path)
    service.upsert_events(
        [
            _event(release_date="2001-01-15", release_time_et="08:30"),
            _event(release_date="2001-01-17", release_time_et="08:30"),
            _event(release_date="2001-01-17", release_time_et="09:00"),
        ]
    )
    assert [(item.release_date, item.release_time_et) for item in service.events_by_name("Consumer Price Index")] == [
        ("2001-01-17", "09:00"),
        ("2001-01-17", "08:30"),
        ("2001-01-15", "08:30"),
    ]


def test_events_by_name_limit_caps_results(tmp_path: Path) -> None:
    service = _service(tmp_path)
    service.upsert_events(
        [
            _event(release_date="2001-01-15"),
            _event(release_date="2001-01-16"),
        ]
    )
    assert len(service.events_by_name("Consumer Price Index", limit=1)) == 1


@pytest.mark.parametrize("limit", [0, -1, 101, True, "5", 1.5])
def test_events_by_name_rejects_invalid_limit(tmp_path: Path, limit) -> None:
    with pytest.raises(EconomicCalendarAdmissionError) as exc_info:
        _service(tmp_path).events_by_name("Consumer Price Index", limit=limit)
    assert exc_info.value.code == "invalid_limit"


def test_invalid_query_limits_do_not_create_missing_db(tmp_path: Path) -> None:
    db_path, db_parent = _paths(tmp_path)
    service = _service(tmp_path)
    with pytest.raises(EconomicCalendarAdmissionError):
        service.next_releases(window_days=0)
    with pytest.raises(EconomicCalendarAdmissionError):
        service.events_by_name("Consumer Price Index", limit=0)
    assert not db_path.exists()
    assert not db_parent.exists()


def test_unknown_name_with_missing_db_does_not_create_files(tmp_path: Path) -> None:
    db_path, db_parent = _paths(tmp_path)
    with pytest.raises(EconomicCalendarAdmissionError):
        _service(tmp_path).events_by_name("Unknown Event")
    assert not db_path.exists()
    assert not db_parent.exists()


def test_public_record_exposes_metadata_only(tmp_path: Path) -> None:
    service = _service(tmp_path)
    service.upsert_events([_event()])
    record = service.events_by_name("Consumer Price Index")[0]
    serialized = repr(record)
    assert "https://" not in serialized
    assert "economic_calendar.sqlite" not in serialized
    forbidden_fields = {
        "source_url",
        "actual",
        "forecast",
        "previous",
        "value",
        "surprise",
        "probability",
        "score",
        "signal",
        "embedding",
        "chunk",
    }
    assert not ({field.name for field in fields(EconomicCalendarEventRecord)} & forbidden_fields)


def test_default_db_file_symlink_rejected_before_sqlite_initialization(tmp_path: Path) -> None:
    db_path = tmp_path / "economic_calendar.sqlite"
    target_path = tmp_path / "outside.sqlite"
    _make_file_symlink(db_path, target_path)
    service = EconomicCalendarService(db_path=db_path)
    with pytest.raises(EconomicCalendarAdmissionError) as exc_info:
        service.upsert_events([_event()])
    assert exc_info.value.code == "invalid_calendar_root"
    assert str(exc_info.value) == "invalid_calendar_root"
    assert not target_path.exists()


def test_default_db_parent_symlink_rejected_before_sqlite_initialization(tmp_path: Path) -> None:
    link_parent = tmp_path / "calendar_parent"
    target_parent = tmp_path / "outside_parent"
    _make_dir_symlink(link_parent, target_parent)
    service = EconomicCalendarService(db_path=link_parent / "economic_calendar.sqlite")
    with pytest.raises(EconomicCalendarAdmissionError) as exc_info:
        service.upsert_events([_event()])
    assert exc_info.value.code == "invalid_calendar_root"
    assert str(exc_info.value) == "invalid_calendar_root"
    assert not (target_parent / "economic_calendar.sqlite").exists()


def test_next_releases_rejects_db_file_symlink(tmp_path: Path) -> None:
    db_path = tmp_path / "economic_calendar.sqlite"
    target_path = tmp_path / "target.sqlite"
    _make_file_symlink(db_path, target_path)
    service = EconomicCalendarService(db_path=db_path)
    with pytest.raises(EconomicCalendarAdmissionError) as exc_info:
        service.next_releases()
    assert exc_info.value.code == "invalid_calendar_root"
    assert not target_path.exists()


def test_next_releases_rejects_immediate_parent_symlink(tmp_path: Path) -> None:
    link_parent = tmp_path / "link_dir"
    target_parent = tmp_path / "real_dir"
    _make_dir_symlink(link_parent, target_parent)
    service = EconomicCalendarService(db_path=link_parent / "cal.sqlite")
    with pytest.raises(EconomicCalendarAdmissionError) as exc_info:
        service.next_releases()
    assert exc_info.value.code == "invalid_calendar_root"
    assert not (target_parent / "cal.sqlite").exists()


def test_next_releases_rejects_non_immediate_ancestor_symlink(tmp_path: Path) -> None:
    target_grandparent = tmp_path / "real_gp"
    link_grandparent = tmp_path / "link_gp"
    _make_dir_symlink(link_grandparent, target_grandparent)
    db_path = link_grandparent / "child" / "cal.sqlite"
    service = EconomicCalendarService(db_path=db_path)
    with pytest.raises(EconomicCalendarAdmissionError) as exc_info:
        service.next_releases()
    assert exc_info.value.code == "invalid_calendar_root"
    assert not (target_grandparent / "child" / "cal.sqlite").exists()


def test_events_by_name_rejects_db_file_symlink(tmp_path: Path) -> None:
    db_path = tmp_path / "economic_calendar.sqlite"
    target_path = tmp_path / "target.sqlite"
    _make_file_symlink(db_path, target_path)
    service = EconomicCalendarService(db_path=db_path)
    with pytest.raises(EconomicCalendarAdmissionError) as exc_info:
        service.events_by_name("Consumer Price Index")
    assert exc_info.value.code == "invalid_calendar_root"
    assert not target_path.exists()


def test_events_by_name_rejects_immediate_parent_symlink(tmp_path: Path) -> None:
    link_parent = tmp_path / "link_dir"
    target_parent = tmp_path / "real_dir"
    _make_dir_symlink(link_parent, target_parent)
    service = EconomicCalendarService(db_path=link_parent / "cal.sqlite")
    with pytest.raises(EconomicCalendarAdmissionError) as exc_info:
        service.events_by_name("Consumer Price Index")
    assert exc_info.value.code == "invalid_calendar_root"
    assert not (target_parent / "cal.sqlite").exists()


def test_events_by_name_rejects_non_immediate_ancestor_symlink(tmp_path: Path) -> None:
    target_grandparent = tmp_path / "real_gp"
    link_grandparent = tmp_path / "link_gp"
    _make_dir_symlink(link_grandparent, target_grandparent)
    db_path = link_grandparent / "child" / "cal.sqlite"
    service = EconomicCalendarService(db_path=db_path)
    with pytest.raises(EconomicCalendarAdmissionError) as exc_info:
        service.events_by_name("Consumer Price Index")
    assert exc_info.value.code == "invalid_calendar_root"
    assert not (target_grandparent / "child" / "cal.sqlite").exists()


def test_upsert_rejects_non_immediate_ancestor_symlink(tmp_path: Path) -> None:
    target_grandparent = tmp_path / "real_gp"
    link_grandparent = tmp_path / "link_gp"
    _make_dir_symlink(link_grandparent, target_grandparent)
    db_path = link_grandparent / "child" / "cal.sqlite"
    service = EconomicCalendarService(db_path=db_path)
    with pytest.raises(EconomicCalendarAdmissionError) as exc_info:
        service.upsert_events([_event()])
    assert exc_info.value.code == "invalid_calendar_root"
    assert not (target_grandparent / "child" / "cal.sqlite").exists()


def test_read_path_guard_runs_before_connect_existing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    db_path = tmp_path / "economic_calendar.sqlite"
    target = tmp_path / "target.sqlite"
    _make_file_symlink(db_path, target)
    service = EconomicCalendarService(db_path=db_path)
    connect_calls: list[str] = []
    monkeypatch.setattr(
        service,
        "_connect_existing",
        lambda: connect_calls.append("connect") or (_ for _ in ()).throw(AssertionError("should not reach")),
    )
    with pytest.raises(EconomicCalendarAdmissionError) as exc_info:
        service.next_releases()
    assert exc_info.value.code == "invalid_calendar_root"
    assert connect_calls == []


def test_upsert_guard_runs_before_connect_existing_or_new(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    db_path = tmp_path / "economic_calendar.sqlite"
    target = tmp_path / "target.sqlite"
    _make_file_symlink(db_path, target)
    service = EconomicCalendarService(db_path=db_path)
    connect_calls: list[str] = []
    monkeypatch.setattr(
        service,
        "_connect_existing_or_new",
        lambda: connect_calls.append("connect") or (_ for _ in ()).throw(AssertionError("should not reach")),
    )
    with pytest.raises(EconomicCalendarAdmissionError) as exc_info:
        service.upsert_events([_event()])
    assert exc_info.value.code == "invalid_calendar_root"
    assert connect_calls == []


def test_symlink_guard_does_not_return_empty_list(tmp_path: Path) -> None:
    db_path = tmp_path / "economic_calendar.sqlite"
    target = tmp_path / "target.sqlite"
    _make_file_symlink(db_path, target)
    service = EconomicCalendarService(db_path=db_path)
    with pytest.raises(EconomicCalendarAdmissionError):
        service.next_releases()
    with pytest.raises(EconomicCalendarAdmissionError):
        service.events_by_name("Consumer Price Index")


def test_valid_tmp_path_service_still_works_after_guard_hardening(tmp_path: Path) -> None:
    service = _service(tmp_path)
    result = service.upsert_events([_event()])
    assert result.status == "ok"
    assert service.next_releases(window_days=1) != []
    assert service.events_by_name("Consumer Price Index") != []


def test_schema_rejects_duplicate_key_date_time_direct_insert(tmp_path: Path) -> None:
    db_path, _db_parent = _paths(tmp_path)
    _service(tmp_path).upsert_events([_event()])
    with _connect(db_path) as connection, pytest.raises(sqlite3.IntegrityError):
        connection.execute(
            """
            INSERT INTO economic_calendar (
                event_key, event_name, release_date, release_time_et, source,
                source_url, source_domain, ingested_at, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "consumer_price_index",
                "Consumer Price Index",
                "2001-01-15",
                "08:30",
                "BLS",
                "https://www.bls.gov/cpi/",
                "www.bls.gov",
                "2001-01-01T00:00:00+00:00",
                "2001-01-01T00:00:00+00:00",
                "2001-01-01T00:00:00+00:00",
            ),
        )


def test_schema_rejects_invalid_event_key_and_source_direct_write(tmp_path: Path) -> None:
    db_path, _db_parent = _paths(tmp_path)
    _service(tmp_path).upsert_events([_event()])
    with _connect(db_path) as connection:
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute("UPDATE economic_calendar SET event_key = 'bad'")
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute("UPDATE economic_calendar SET source = 'Reuters'")


def test_public_dataclasses_are_metadata_only() -> None:
    for klass in [EconomicCalendarEventRecord, EconomicCalendarMutationResult]:
        assert is_dataclass(klass)
    assert {field.name for field in fields(EconomicCalendarMutationResult)} == {
        "status",
        "created_count",
        "updated_count",
        "event_count",
    }


def test_service_public_methods_are_strictly_limited() -> None:
    methods = {
        name
        for name, value in inspect.getmembers(EconomicCalendarService, predicate=inspect.isfunction)
        if not name.startswith("_")
    }
    assert methods == {"upsert_events", "next_releases", "events_by_name"}


def test_service_source_has_no_forbidden_runtime_boundaries() -> None:
    source = SERVICE_SOURCE.read_text(encoding="utf-8")
    forbidden = [
        "httpx",
        "requests",
        "aiohttp",
        "os.environ",
        "os.getenv",
        "FastAPI",
        "main.py",
        "Tavily",
        "DeepSeek",
        "embedding",
        "vector",
        "data_providers",
        "economic_calendar_seed",
        "load_seed",
        "seed_default",
        "download",
        "crawl",
        "scrape",
        "refresh",
        "get_actual",
        "get_forecast",
        "get_surprise",
    ]
    assert not any(token in source for token in forbidden)
    assert re.search(r"\bRAG\b", source) is None
