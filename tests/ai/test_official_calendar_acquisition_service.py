from __future__ import annotations

import json
from dataclasses import dataclass, fields as dc_fields
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from app_backend.services.economic_calendar_service import (
    EconomicCalendarMutationResult,
    EconomicCalendarService,
)
from app_backend.services.official_calendar_acquisition_service import (
    OfficialCalendarAcquisitionService,
    OfficialCalendarAcquisitionSummary,
)


_ET = ZoneInfo("America/New_York")
_NOW = "2026-06-24T10:00:00-04:00"


def _now_provider():
    return datetime.fromisoformat(_NOW)


def _minimal_bls_ics() -> str:
    return (
        "BEGIN:VCALENDAR\n"
        "BEGIN:VEVENT\nDTSTART:20260715T083000\nSUMMARY:Consumer Price Index\nEND:VEVENT\n"
        "BEGIN:VEVENT\nDTSTART:20260807T083000\nSUMMARY:Employment Situation\nEND:VEVENT\n"
        "END:VCALENDAR"
    )


def _minimal_bea_json() -> str:
    return json.dumps({
        "Personal Income and Outlays": {"release_dates": ["2026-07-31T08:30:00-04:00"]},
        "Gross Domestic Product": {"release_dates": ["2026-07-29T08:30:00-04:00"]},
    })


@dataclass(frozen=True)
class _FakePayload:
    body: str
    source: str
    content_type: str


class _FakeTransport:
    def __init__(self, responses: dict[str, str] | None = None, fail_sources: set[str] | None = None):
        self.responses = responses or {}
        self.fail_sources = fail_sources or set()
        self.call_log: list[str] = []

    def fetch(self, source):
        source_str = str(source.value) if hasattr(source, "value") else str(source)
        self.call_log.append(source_str)
        if source_str in self.fail_sources:
            raise RuntimeError("fetch failed")
        body = self.responses.get(source_str, "")
        ct = "text/calendar" if source_str == "bls" else "application/json"
        return _FakePayload(body=body, source=source_str, content_type=ct)


def _service(tmp_path: Path, transport: _FakeTransport | None = None) -> OfficialCalendarAcquisitionService:
    db_path = tmp_path / "cal.sqlite"
    cal_service = EconomicCalendarService(db_path=db_path, now_provider=_now_provider)
    t = transport or _FakeTransport()
    return OfficialCalendarAcquisitionService(
        transport_factory=lambda: t,
        calendar_service=cal_service,
        now_provider=_now_provider,
    )


# ---- no-live planned: zero transport / parser / writer ----

def test_no_live_returns_planned(tmp_path):
    transport = _FakeTransport()
    svc = _service(tmp_path, transport)
    result = svc.run(source_keys=("bls", "bea"))
    assert result.status == "planned"
    assert result.error_codes == ["live_disabled"]
    assert transport.call_log == []


def test_no_live_creates_no_db(tmp_path):
    svc = _service(tmp_path)
    svc.run(source_keys=("bls", "bea"))
    assert not (tmp_path / "cal.sqlite").exists()


# ---- write without live: zero calls ----

def test_write_without_live_blocked(tmp_path):
    transport = _FakeTransport()
    svc = _service(tmp_path, transport)
    result = svc.run(source_keys=("bls", "bea"), write=True)
    assert result.status == "blocked"
    assert result.error_codes == ["write_requires_live"]
    assert transport.call_log == []


def test_write_without_live_no_db(tmp_path):
    svc = _service(tmp_path)
    svc.run(source_keys=("bls", "bea"), write=True)
    assert not (tmp_path / "cal.sqlite").exists()


# ---- BLS-only dry-run ----

def test_bls_only_dry_run(tmp_path):
    transport = _FakeTransport(responses={"bls": _minimal_bls_ics()})
    svc = _service(tmp_path, transport)
    result = svc.run(source_keys=("bls",), live=True)
    assert result.status == "dry_run"
    assert result.event_count == 2
    assert "consumer_price_index" in result.event_key_counts
    assert not (tmp_path / "cal.sqlite").exists()


# ---- BEA-only dry-run ----

def test_bea_only_dry_run(tmp_path):
    transport = _FakeTransport(responses={"bea": _minimal_bea_json()})
    svc = _service(tmp_path, transport)
    result = svc.run(source_keys=("bea",), live=True)
    assert result.status == "dry_run"
    assert result.event_count == 2
    assert "gross_domestic_product" in result.event_key_counts


# ---- both-source dry-run ----

def test_both_source_dry_run(tmp_path):
    transport = _FakeTransport(responses={"bls": _minimal_bls_ics(), "bea": _minimal_bea_json()})
    svc = _service(tmp_path, transport)
    result = svc.run(source_keys=("bls", "bea"), live=True)
    assert result.status == "dry_run"
    assert result.event_count == 4


# ---- both-source live-write ----

def test_both_source_live_write(tmp_path):
    transport = _FakeTransport(responses={"bls": _minimal_bls_ics(), "bea": _minimal_bea_json()})
    svc = _service(tmp_path, transport)
    result = svc.run(source_keys=("bls", "bea"), live=True, write=True)
    assert result.status == "ok"
    assert result.event_count == 4
    assert result.created_count == 4
    assert result.updated_count == 0
    assert (tmp_path / "cal.sqlite").exists()


# ---- selected source failure zero writer ----

def test_fetch_failure_blocks_write(tmp_path):
    transport = _FakeTransport(
        responses={"bls": _minimal_bls_ics()},
        fail_sources={"bea"},
    )
    svc = _service(tmp_path, transport)
    result = svc.run(source_keys=("bls", "bea"), live=True, write=True)
    assert result.status == "blocked"
    assert "fetch_failed" in result.error_codes
    assert not (tmp_path / "cal.sqlite").exists()


# ---- parser failure zero writer ----

def test_parser_failure_blocks_write(tmp_path):
    transport = _FakeTransport(responses={"bls": "not valid ics", "bea": _minimal_bea_json()})
    svc = _service(tmp_path, transport)
    result = svc.run(source_keys=("bls", "bea"), live=True, write=True)
    assert result.status == "blocked"
    assert not (tmp_path / "cal.sqlite").exists()


# ---- required event missing zero writer ----

def test_missing_bls_required_key_blocks(tmp_path):
    ics_only_cpi = (
        "BEGIN:VCALENDAR\n"
        "BEGIN:VEVENT\nDTSTART:20260715T083000\nSUMMARY:Consumer Price Index\nEND:VEVENT\n"
        "END:VCALENDAR"
    )
    transport = _FakeTransport(responses={"bls": ics_only_cpi, "bea": _minimal_bea_json()})
    svc = _service(tmp_path, transport)
    result = svc.run(source_keys=("bls", "bea"), live=True, write=True)
    assert result.status == "blocked"
    assert not (tmp_path / "cal.sqlite").exists()


# ---- duplicate source key ----

def test_duplicate_source_key_raises(tmp_path):
    svc = _service(tmp_path)
    with pytest.raises(ValueError) as exc_info:
        svc.run(source_keys=("bls", "bls"))
    assert "duplicate_source_key" in str(exc_info.value)


# ---- unknown source key ----

def test_unknown_source_key_raises(tmp_path):
    svc = _service(tmp_path)
    with pytest.raises(ValueError) as exc_info:
        svc.run(source_keys=("fred",))
    assert "unknown_source_key" in str(exc_info.value)


# ---- empty source keys ----

def test_empty_source_keys_raises(tmp_path):
    svc = _service(tmp_path)
    with pytest.raises(ValueError) as exc_info:
        svc.run(source_keys=())
    assert "empty_source_keys" in str(exc_info.value)


# ---- invalid date range ----

def test_invalid_start_date_raises(tmp_path):
    svc = _service(tmp_path)
    with pytest.raises(ValueError) as exc_info:
        svc.run(source_keys=("bls",), start_date="bad-date")
    assert "invalid_date_range" in str(exc_info.value)


def test_invalid_end_date_raises(tmp_path):
    svc = _service(tmp_path)
    with pytest.raises(ValueError) as exc_info:
        svc.run(source_keys=("bls",), end_date="bad-date")
    assert "invalid_date_range" in str(exc_info.value)


def test_end_before_start_raises(tmp_path):
    svc = _service(tmp_path)
    with pytest.raises(ValueError) as exc_info:
        svc.run(source_keys=("bls",), start_date="2026-12-31", end_date="2026-01-01")
    assert "invalid_date_range" in str(exc_info.value)


def test_start_in_past_raises(tmp_path):
    svc = _service(tmp_path)
    with pytest.raises(ValueError) as exc_info:
        svc.run(source_keys=("bls",), start_date="2025-01-01")
    assert "invalid_date_range" in str(exc_info.value)


# ---- max 366 days ----

def test_window_over_366_days_raises(tmp_path):
    svc = _service(tmp_path)
    with pytest.raises(ValueError) as exc_info:
        svc.run(source_keys=("bls",), start_date="2026-06-24", end_date="2027-07-01")
    assert "invalid_date_range" in str(exc_info.value)


# ---- ET default date range ----

def test_default_date_range_is_today_et_plus_365(tmp_path):
    svc = _service(tmp_path)
    result = svc.run(source_keys=("bls",))
    assert result.start_date == "2026-06-24"
    assert result.end_date == "2027-06-24"


# ---- writer exception ----

def test_writer_exception_returns_write_failed(tmp_path, monkeypatch):
    transport = _FakeTransport(responses={"bls": _minimal_bls_ics(), "bea": _minimal_bea_json()})
    db_path = tmp_path / "cal.sqlite"
    cal_service = EconomicCalendarService(db_path=db_path, now_provider=_now_provider)
    monkeypatch.setattr(cal_service, "upsert_events", lambda events: (_ for _ in ()).throw(RuntimeError("db error")))
    svc = OfficialCalendarAcquisitionService(
        transport_factory=lambda: transport,
        calendar_service=cal_service,
        now_provider=_now_provider,
    )
    result = svc.run(source_keys=("bls", "bea"), live=True, write=True)
    assert result.status == "blocked"
    assert "write_failed" in result.error_codes


# ---- malformed writer summary (count mismatch) ----

def test_count_mismatch_returns_write_failed(tmp_path, monkeypatch):
    transport = _FakeTransport(responses={"bls": _minimal_bls_ics(), "bea": _minimal_bea_json()})
    db_path = tmp_path / "cal.sqlite"
    cal_service = EconomicCalendarService(db_path=db_path, now_provider=_now_provider)
    monkeypatch.setattr(
        cal_service, "upsert_events",
        lambda events: EconomicCalendarMutationResult(status="ok", created_count=1, updated_count=0, event_count=999),
    )
    svc = OfficialCalendarAcquisitionService(
        transport_factory=lambda: transport,
        calendar_service=cal_service,
        now_provider=_now_provider,
    )
    result = svc.run(source_keys=("bls", "bea"), live=True, write=True)
    assert result.status == "blocked"
    assert "write_failed" in result.error_codes


# ---- safe summary fields only ----

def test_summary_fields_are_safe():
    allowed = {
        "status", "live", "write", "selected_sources", "start_date", "end_date",
        "event_count", "event_key_counts", "created_count", "updated_count",
        "unavailable_event_keys", "error_codes",
    }
    actual = {f.name for f in dc_fields(OfficialCalendarAcquisitionSummary)}
    assert actual == allowed


def test_summary_has_no_url_or_payload(tmp_path):
    transport = _FakeTransport(responses={"bls": _minimal_bls_ics(), "bea": _minimal_bea_json()})
    svc = _service(tmp_path, transport)
    result = svc.run(source_keys=("bls", "bea"), live=True)
    serialized = repr(result)
    for token in ["https://", "bls.gov", "bea.gov", "payload", "header", "body"]:
        assert token not in serialized


# ---- unavailable event key fixed to fomc_statement ----

def test_unavailable_keys_include_fomc(tmp_path):
    svc = _service(tmp_path)
    result = svc.run(source_keys=("bls",))
    assert "fomc_statement" in result.unavailable_event_keys


def test_unavailable_keys_fixed(tmp_path):
    svc = _service(tmp_path)
    result = svc.run(source_keys=("bls",))
    assert result.unavailable_event_keys == ("fomc_statement",)


# ---- transport each source max once ----

def test_transport_called_once_per_source(tmp_path):
    transport = _FakeTransport(responses={"bls": _minimal_bls_ics(), "bea": _minimal_bea_json()})
    svc = _service(tmp_path, transport)
    svc.run(source_keys=("bls", "bea"), live=True)
    assert transport.call_log.count("bls") == 1
    assert transport.call_log.count("bea") == 1


# ---- no raw response / URL / exception leak ----

def test_fetch_error_no_url_leak(tmp_path):
    transport = _FakeTransport(fail_sources={"bls"})
    svc = _service(tmp_path, transport)
    result = svc.run(source_keys=("bls",), live=True)
    serialized = repr(result)
    assert "bls.gov" not in serialized
    assert "https://" not in serialized


# ---- no fixture auto-load ----

def test_no_fixture_autoload(tmp_path):
    svc = _service(tmp_path)
    result = svc.run(source_keys=("bls",))
    assert result.event_count == 0
    assert not (tmp_path / "cal.sqlite").exists()


# ---- no actual / forecast / score / probability fields ----

def test_no_financial_value_fields():
    forbidden = {"actual", "forecast", "previous", "surprise", "value", "probability", "score", "signal"}
    actual = {f.name for f in dc_fields(OfficialCalendarAcquisitionSummary)}
    assert not actual & forbidden


# ---- idempotent re-write ----

def test_rewrite_updates_existing(tmp_path):
    transport = _FakeTransport(responses={"bls": _minimal_bls_ics(), "bea": _minimal_bea_json()})
    svc = _service(tmp_path, transport)
    first = svc.run(source_keys=("bls", "bea"), live=True, write=True)
    second = svc.run(source_keys=("bls", "bea"), live=True, write=True)
    assert first.created_count == 4
    assert second.created_count == 0
    assert second.updated_count == 4
    assert second.status == "ok"


# ---- planned summary has zero counts ----

def test_planned_summary_zero_counts(tmp_path):
    svc = _service(tmp_path)
    result = svc.run(source_keys=("bls",))
    assert result.event_count == 0
    assert result.created_count == 0
    assert result.updated_count == 0
    assert result.event_key_counts == {}


# ---- dry run summary has event counts ----

def test_dry_run_has_counts(tmp_path):
    transport = _FakeTransport(responses={"bls": _minimal_bls_ics(), "bea": _minimal_bea_json()})
    svc = _service(tmp_path, transport)
    result = svc.run(source_keys=("bls", "bea"), live=True)
    assert result.event_count == 4
    assert result.event_key_counts != {}
    assert result.created_count == 0
    assert result.updated_count == 0


# ---- created + updated == event_count on success ----

def test_created_plus_updated_equals_event_count(tmp_path):
    transport = _FakeTransport(responses={"bls": _minimal_bls_ics(), "bea": _minimal_bea_json()})
    svc = _service(tmp_path, transport)
    result = svc.run(source_keys=("bls", "bea"), live=True, write=True)
    assert result.created_count + result.updated_count == result.event_count


# ---- single source bls write ----

def test_bls_only_write(tmp_path):
    transport = _FakeTransport(responses={"bls": _minimal_bls_ics()})
    svc = _service(tmp_path, transport)
    result = svc.run(source_keys=("bls",), live=True, write=True)
    assert result.status == "ok"
    assert result.event_count == 2
    keys = set(result.event_key_counts.keys())
    assert keys == {"consumer_price_index", "employment_situation"}


# ---- single source bea write ----

def test_bea_only_write(tmp_path):
    transport = _FakeTransport(responses={"bea": _minimal_bea_json()})
    svc = _service(tmp_path, transport)
    result = svc.run(source_keys=("bea",), live=True, write=True)
    assert result.status == "ok"
    assert result.event_count == 2
    keys = set(result.event_key_counts.keys())
    assert keys == {"personal_income_and_outlays", "gross_domestic_product"}


# ---- no transport call in non-live mode ----

def test_no_transport_in_planned_mode(tmp_path):
    transport = _FakeTransport()
    svc = _service(tmp_path, transport)
    svc.run(source_keys=("bls", "bea"))
    assert transport.call_log == []


def test_no_transport_in_write_without_live(tmp_path):
    transport = _FakeTransport()
    svc = _service(tmp_path, transport)
    svc.run(source_keys=("bls",), write=True)
    assert transport.call_log == []


# ---- partial source failure blocks entire batch ----

def test_second_source_failure_blocks_entire_batch(tmp_path):
    transport = _FakeTransport(
        responses={"bls": _minimal_bls_ics()},
        fail_sources={"bea"},
    )
    svc = _service(tmp_path, transport)
    result = svc.run(source_keys=("bls", "bea"), live=True, write=True)
    assert result.status == "blocked"
    assert not (tmp_path / "cal.sqlite").exists()
