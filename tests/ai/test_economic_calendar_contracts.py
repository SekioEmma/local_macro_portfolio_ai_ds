from __future__ import annotations

from dataclasses import FrozenInstanceError, fields
import json
from pathlib import Path
import re

import pytest

from app_backend.services.economic_calendar_contracts import (
    EconomicCalendarAdmissionError,
    EconomicCalendarEventInput,
    EconomicCalendarEventKey,
    admit_calendar_event,
    canonicalize_calendar_source_url,
    resolve_calendar_event_key,
)


ROOT = Path(__file__).parents[2]
SERVICE_ROOT = ROOT / "src" / "app_backend" / "services"
CONTRACT_SOURCE = SERVICE_ROOT / "economic_calendar_contracts.py"
SCHEMA_PATH = SERVICE_ROOT / "economic_calendar_schema.sql"
SEED_PATH = ROOT / "data" / "economic_calendar_seed.json"


def _input(**overrides: str) -> EconomicCalendarEventInput:
    values = {
        "event_key": "consumer_price_index",
        "release_date": "2001-01-15",
        "release_time_et": "08:30",
        "source_url": "https://www.bls.gov/cpi/",
        "ingested_at": "2001-01-01T08:00:00-05:00",
    }
    values.update(overrides)
    return EconomicCalendarEventInput(**values)


def _admit(**overrides: str):
    return admit_calendar_event(_input(**overrides))


def _assert_rejected(code: str, **overrides: str) -> None:
    with pytest.raises(EconomicCalendarAdmissionError) as exc_info:
        _admit(**overrides)
    assert exc_info.value.code == code
    assert str(exc_info.value) == code


@pytest.mark.parametrize(
    ("event_key", "event_name", "source", "source_url"),
    [
        ("consumer_price_index", "Consumer Price Index", "BLS", "https://www.bls.gov/cpi/"),
        ("employment_situation", "Employment Situation", "BLS", "https://calendar.bls.gov/"),
        (
            "personal_income_and_outlays",
            "Personal Income and Outlays",
            "BEA",
            "https://www.bea.gov/data/income-saving/personal-income",
        ),
        (
            "gross_domestic_product",
            "Gross Domestic Product",
            "BEA",
            "https://apps.bea.gov/newsreleases/",
        ),
        (
            "fomc_statement",
            "FOMC Statement",
            "Federal Reserve",
            "https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm",
        ),
    ],
)
def test_accepts_fixed_event_catalog_and_derives_metadata(
    event_key: str,
    event_name: str,
    source: str,
    source_url: str,
) -> None:
    admitted = _admit(event_key=event_key, source_url=source_url)
    assert admitted.event_key == EconomicCalendarEventKey(event_key)
    assert admitted.event_name == event_name
    assert admitted.source == source


@pytest.mark.parametrize("event_key", ["", "unknown", "consumer_sentiment", "research_needed"])
def test_rejects_unknown_event_key(event_key: str) -> None:
    _assert_rejected("unsupported_event_key", event_key=event_key)


def test_resolve_calendar_event_key_returns_catalog_metadata() -> None:
    metadata = resolve_calendar_event_key("gross_domestic_product")
    assert metadata.event_name == "Gross Domestic Product"
    assert metadata.source == "BEA"


@pytest.mark.parametrize("release_date", ["2001-01-15", "2026-02-28", "1999-12-31"])
def test_accepts_iso_release_dates(release_date: str) -> None:
    assert _admit(release_date=release_date).release_date == release_date


@pytest.mark.parametrize("release_date", ["", "2001-1-15", "2001-02-29", "not-a-date", "2001-01-15T00:00:00"])
def test_rejects_invalid_release_dates(release_date: str) -> None:
    _assert_rejected("invalid_release_date", release_date=release_date)


@pytest.mark.parametrize("release_time_et", ["00:00", "08:30", "14:00", "23:59"])
def test_accepts_strict_hhmm_release_time(release_time_et: str) -> None:
    assert _admit(release_time_et=release_time_et).release_time_et == release_time_et


@pytest.mark.parametrize("release_time_et", ["", "8:30", "08:30:00", "24:00", "12:60", "TBD", "08:30.000"])
def test_rejects_invalid_release_time(release_time_et: str) -> None:
    _assert_rejected("invalid_release_time_et", release_time_et=release_time_et)


@pytest.mark.parametrize("ingested_at", ["2001-01-01T08:00:00", "not-a-time", "2001-99-01T00:00:00Z"])
def test_rejects_invalid_or_naive_ingested_at(ingested_at: str) -> None:
    _assert_rejected("invalid_ingested_at", ingested_at=ingested_at)


def test_normalizes_ingested_at_to_utc() -> None:
    assert _admit(ingested_at="2001-01-01T08:00:00-05:00").ingested_at == "2001-01-01T13:00:00+00:00"
    assert _admit(ingested_at="2001-01-01T13:00:00Z").ingested_at == "2001-01-01T13:00:00+00:00"


@pytest.mark.parametrize(
    ("event_key", "source_url"),
    [
        ("consumer_price_index", "https://bls.gov/cpi/"),
        ("consumer_price_index", "https://www.bls.gov/cpi/"),
        ("employment_situation", "https://calendar.bls.gov/"),
        ("personal_income_and_outlays", "https://bea.gov/data/"),
        ("gross_domestic_product", "https://apps.bea.gov/newsreleases/"),
        ("fomc_statement", "https://federalreserve.gov/monetarypolicy/"),
        ("fomc_statement", "https://www.federalreserve.gov/monetarypolicy/"),
    ],
)
def test_accepts_official_source_domains_and_subdomains(event_key: str, source_url: str) -> None:
    admitted = _admit(event_key=event_key, source_url=source_url)
    assert admitted.source_url.startswith("https://")


@pytest.mark.parametrize(
    ("event_key", "source_url"),
    [
        ("consumer_price_index", "https://bea.gov/data/"),
        ("personal_income_and_outlays", "https://bls.gov/cpi/"),
        ("fomc_statement", "https://bea.gov/data/"),
        ("consumer_price_index", "https://reuters.com/markets/"),
        ("consumer_price_index", "https://bloomberg.com/news/"),
        ("consumer_price_index", "https://fred.stlouisfed.org/series/CPIAUCSL"),
        ("fomc_statement", "https://imf.org/en/"),
        ("fomc_statement", "https://worldbank.org/en/"),
        ("consumer_price_index", "https://bls.gov.evil.example/cpi/"),
        ("fomc_statement", "https://federalreserve.gov.evil/"),
    ],
)
def test_rejects_source_domain_mismatch_and_suffix_attacks(event_key: str, source_url: str) -> None:
    _assert_rejected("source_mismatch", event_key=event_key, source_url=source_url)


@pytest.mark.parametrize(
    "source_url",
    [
        "https://www.bls.gov/cpi/?x=1",
        "https://www.bls.gov/cpi/#frag",
        "https://user@www.bls.gov/cpi/",
        "https://www.bls.gov:443/cpi/",
        "http://www.bls.gov/cpi/",
        "file:///tmp/calendar",
        "javascript:alert(1)",
        "data:text/plain,calendar",
        "https://localhost/cpi/",
        "https://127.0.0.1/cpi/",
        "https://[::1]/cpi/",
        "https://www.bls.gov/a/../cpi/",
        "https:///missing-host",
    ],
)
def test_rejects_unsafe_source_urls(source_url: str) -> None:
    _assert_rejected("invalid_source_url", source_url=source_url)


def test_canonicalize_source_url_lowercases_hostname_and_preserves_path() -> None:
    canonical, domain = canonicalize_calendar_source_url("https://WWW.BLS.GOV/cpi/", "BLS")
    assert canonical == "https://www.bls.gov/cpi/"
    assert domain == "www.bls.gov"


def test_admission_error_does_not_echo_input_or_secret() -> None:
    bad_url = "https://user:secret@www.bls.gov/cpi/"
    with pytest.raises(EconomicCalendarAdmissionError) as exc_info:
        _admit(source_url=bad_url)
    assert str(exc_info.value) == "invalid_source_url"
    assert "secret" not in str(exc_info.value)
    assert bad_url not in str(exc_info.value)


def test_event_input_and_admitted_output_do_not_accept_caller_metadata() -> None:
    input_fields = {field.name for field in fields(EconomicCalendarEventInput)}
    assert input_fields == {"event_key", "release_date", "release_time_et", "source_url", "ingested_at"}
    admitted_fields = {field.name for field in fields(_admit())}
    assert "event_name" not in input_fields
    assert "source" not in input_fields
    assert "source_domain" not in input_fields
    assert {"event_name", "source", "source_domain"} <= admitted_fields


def test_calendar_dataclasses_are_frozen() -> None:
    event = _input()
    admitted = _admit()
    with pytest.raises(FrozenInstanceError):
        event.event_key = "changed"
    with pytest.raises(FrozenInstanceError):
        admitted.event_name = "Changed"


def test_seed_fixture_top_level_metadata_and_notice() -> None:
    fixture = json.loads(SEED_PATH.read_text(encoding="utf-8"))
    assert fixture["fixture_only"] is True
    assert fixture["schema_version"] == 1
    assert "Offline synthetic fixture only" in fixture["fixture_notice"]
    assert "Service does not auto-load" in fixture["fixture_notice"]


def test_seed_fixture_contains_all_fixed_event_keys() -> None:
    fixture = json.loads(SEED_PATH.read_text(encoding="utf-8"))
    keys = {event["event_key"] for event in fixture["events"]}
    assert keys == {item.value for item in EconomicCalendarEventKey}
    assert len(fixture["events"]) == 5


def test_seed_fixture_events_are_admissible_and_synthetic_dated() -> None:
    fixture = json.loads(SEED_PATH.read_text(encoding="utf-8"))
    for event in fixture["events"]:
        admitted = admit_calendar_event(EconomicCalendarEventInput(**event))
        assert admitted.release_date.startswith("2001-01-")
        assert admitted.source_url.startswith("https://")


def test_seed_fixture_has_no_forbidden_calendar_value_fields() -> None:
    serialized = SEED_PATH.read_text(encoding="utf-8").lower()
    forbidden = [
        "actual",
        "forecast",
        "previous",
        "value",
        "surprise",
        "probability",
        "importance",
        "score",
        "trading",
    ]
    assert not any(token in serialized for token in forbidden)


def test_schema_defines_migration_and_calendar_table() -> None:
    schema = SCHEMA_PATH.read_text(encoding="utf-8")
    assert "CREATE TABLE IF NOT EXISTS schema_migrations" in schema
    assert "INSERT OR IGNORE INTO schema_migrations (version) VALUES (1)" in schema
    assert "CREATE TABLE IF NOT EXISTS economic_calendar" in schema


def test_schema_has_required_columns_unique_and_checks() -> None:
    schema = SCHEMA_PATH.read_text(encoding="utf-8")
    for column in [
        "id INTEGER PRIMARY KEY",
        "event_key TEXT NOT NULL CHECK",
        "event_name TEXT NOT NULL",
        "release_date TEXT NOT NULL",
        "release_time_et TEXT NOT NULL",
        "source TEXT NOT NULL CHECK",
        "source_url TEXT NOT NULL",
        "source_domain TEXT NOT NULL",
        "ingested_at TEXT NOT NULL",
        "created_at TEXT NOT NULL",
        "updated_at TEXT NOT NULL",
        "UNIQUE (event_key, release_date, release_time_et)",
    ]:
        assert column in schema
    for event_key in [item.value for item in EconomicCalendarEventKey]:
        assert event_key in schema


def test_schema_has_required_indexes() -> None:
    schema = SCHEMA_PATH.read_text(encoding="utf-8")
    assert "economic_calendar(release_date, release_time_et)" in schema
    assert "economic_calendar(event_key, release_date DESC)" in schema
    assert "economic_calendar(source, release_date)" in schema


def test_schema_has_no_forbidden_financial_or_sensitive_columns() -> None:
    schema = SCHEMA_PATH.read_text(encoding="utf-8").lower()
    table_match = re.search(
        r"create table if not exists economic_calendar \((.*?)\);\n\ncreate index",
        schema,
        re.DOTALL,
    )
    assert table_match is not None
    table_body = table_match.group(1)
    forbidden = [
        "actual",
        "forecast",
        "previous",
        "value",
        "surprise",
        "score",
        "probability",
        "raw html",
        "raw_provider",
        "api_key",
        "account",
        "holdings",
        "position",
        "transaction",
    ]
    assert not any(token in table_body for token in forbidden)


def test_contract_source_has_no_filesystem_sqlite_env_or_network_imports() -> None:
    source = CONTRACT_SOURCE.read_text(encoding="utf-8")
    forbidden = [
        "pathlib",
        "sqlite3",
        "httpx",
        "requests",
        "aiohttp",
        "os.environ",
        "os.getenv",
        "FastAPI",
        "main.py",
        "data_providers",
        "app_backend.services.",
    ]
    assert not any(token in source for token in forbidden)
