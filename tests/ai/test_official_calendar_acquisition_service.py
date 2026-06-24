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


# ===========================================================================
# C4c: Transport payload boundary
# ===========================================================================

class _SimplePayload:
    """Flexible payload for boundary tests — any attr can be set or omitted."""
    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)


class _PayloadTransport:
    """Transport that returns a fixed payload object regardless of source."""
    def __init__(self, payload):
        self._payload = payload
        self.call_log: list[str] = []

    def fetch(self, source):
        key = source.value if hasattr(source, "value") else str(source)
        self.call_log.append(key)
        return self._payload


def _svc_with_payload(tmp_path, payload):
    t = _PayloadTransport(payload)
    db_path = tmp_path / "cal.sqlite"
    cal_svc = EconomicCalendarService(db_path=db_path, now_provider=_now_provider)
    svc = OfficialCalendarAcquisitionService(
        transport_factory=lambda: t,
        calendar_service=cal_svc,
        now_provider=_now_provider,
    )
    return svc, t


# A1 – payload is None
def test_payload_none_blocked(tmp_path):
    svc, _ = _svc_with_payload(tmp_path, None)
    result = svc.run(source_keys=("bls",), live=True)
    assert result.status == "blocked"
    assert "invalid_response" in result.error_codes


# A2 – payload has no source attribute
def test_payload_no_source_attr_blocked(tmp_path):
    payload = _SimplePayload(content_type="text/calendar", body="BEGIN:VCALENDAR\nEND:VCALENDAR")
    svc, _ = _svc_with_payload(tmp_path, payload)
    result = svc.run(source_keys=("bls",), live=True)
    assert result.status == "blocked"
    assert "invalid_response" in result.error_codes


# A3 – payload.source is the wrong source key
def test_payload_wrong_source_blocked(tmp_path):
    payload = _SimplePayload(source="bea", content_type="text/calendar", body="BEGIN:VCALENDAR\nEND:VCALENDAR")
    svc, _ = _svc_with_payload(tmp_path, payload)
    result = svc.run(source_keys=("bls",), live=True)
    assert result.status == "blocked"
    assert "invalid_response" in result.error_codes


# A4 – payload.source is an enum whose .value matches → validation passes, parser runs
def test_payload_enum_source_accepted(tmp_path):
    class _FakeEnum:
        value = "bls"
    payload = _SimplePayload(source=_FakeEnum(), content_type="text/calendar", body=_minimal_bls_ics())
    svc, _ = _svc_with_payload(tmp_path, payload)
    result = svc.run(source_keys=("bls",), live=True)
    assert result.status == "dry_run"


# A5 – payload.source is a plain string → accepted
def test_payload_string_source_accepted(tmp_path):
    payload = _SimplePayload(source="bls", content_type="text/calendar", body=_minimal_bls_ics())
    svc, _ = _svc_with_payload(tmp_path, payload)
    result = svc.run(source_keys=("bls",), live=True)
    assert result.status == "dry_run"


# A6 – payload has no body attribute
def test_payload_no_body_attr_blocked(tmp_path):
    payload = _SimplePayload(source="bls", content_type="text/calendar")
    svc, _ = _svc_with_payload(tmp_path, payload)
    result = svc.run(source_keys=("bls",), live=True)
    assert result.status == "blocked"
    assert "invalid_response" in result.error_codes


# A7 – payload.body is bytes
def test_payload_body_bytes_blocked(tmp_path):
    payload = _SimplePayload(source="bls", content_type="text/calendar", body=b"BEGIN:VCALENDAR\nEND:VCALENDAR")
    svc, _ = _svc_with_payload(tmp_path, payload)
    result = svc.run(source_keys=("bls",), live=True)
    assert result.status == "blocked"
    assert "invalid_response" in result.error_codes


# A8 – payload.body is None
def test_payload_body_none_blocked(tmp_path):
    payload = _SimplePayload(source="bls", content_type="text/calendar", body=None)
    svc, _ = _svc_with_payload(tmp_path, payload)
    result = svc.run(source_keys=("bls",), live=True)
    assert result.status == "blocked"
    assert "invalid_response" in result.error_codes


# A9 – body contains NUL byte
def test_payload_body_nul_blocked(tmp_path):
    payload = _SimplePayload(source="bls", content_type="text/calendar", body="BEGIN\x00END")
    svc, _ = _svc_with_payload(tmp_path, payload)
    result = svc.run(source_keys=("bls",), live=True)
    assert result.status == "blocked"
    assert "invalid_response" in result.error_codes


# A10 – body UTF-8 encoded size exceeds 1 MiB
def test_payload_body_over_1mib_blocked(tmp_path):
    big_body = "x" * (1_048_576 + 1)
    payload = _SimplePayload(source="bls", content_type="text/calendar", body=big_body)
    svc, _ = _svc_with_payload(tmp_path, payload)
    result = svc.run(source_keys=("bls",), live=True)
    assert result.status == "blocked"
    assert "invalid_response" in result.error_codes


# A11 – body contains a lone surrogate that cannot be UTF-8 encoded
def test_payload_body_surrogate_blocked(tmp_path):
    body_with_surrogate = "prefix\ud800suffix"
    payload = _SimplePayload(source="bls", content_type="text/calendar", body=body_with_surrogate)
    svc, _ = _svc_with_payload(tmp_path, payload)
    result = svc.run(source_keys=("bls",), live=True)
    assert result.status == "blocked"
    assert "invalid_response" in result.error_codes


# A12 – payload has no content_type attribute
def test_payload_no_content_type_attr_blocked(tmp_path):
    payload = _SimplePayload(source="bls", body="BEGIN:VCALENDAR\nEND:VCALENDAR")
    svc, _ = _svc_with_payload(tmp_path, payload)
    result = svc.run(source_keys=("bls",), live=True)
    assert result.status == "blocked"
    assert "invalid_response" in result.error_codes


# A13 – content_type is not a string
def test_payload_content_type_nonstring_blocked(tmp_path):
    payload = _SimplePayload(source="bls", content_type=42, body="BEGIN:VCALENDAR\nEND:VCALENDAR")
    svc, _ = _svc_with_payload(tmp_path, payload)
    result = svc.run(source_keys=("bls",), live=True)
    assert result.status == "blocked"
    assert "invalid_response" in result.error_codes


# A14 – content_type is "text/html"
def test_payload_text_html_blocked(tmp_path):
    payload = _SimplePayload(source="bls", content_type="text/html", body="BEGIN:VCALENDAR\nEND:VCALENDAR")
    svc, _ = _svc_with_payload(tmp_path, payload)
    result = svc.run(source_keys=("bls",), live=True)
    assert result.status == "blocked"
    assert "invalid_response" in result.error_codes


# A15 – content_type is "text/calendarish"
def test_payload_text_calendarish_blocked(tmp_path):
    payload = _SimplePayload(source="bls", content_type="text/calendarish", body="BEGIN:VCALENDAR\nEND:VCALENDAR")
    svc, _ = _svc_with_payload(tmp_path, payload)
    result = svc.run(source_keys=("bls",), live=True)
    assert result.status == "blocked"
    assert "invalid_response" in result.error_codes


# A16 – content_type is "application/jsonish" for BEA
def test_payload_application_jsonish_blocked(tmp_path):
    payload = _SimplePayload(source="bea", content_type="application/jsonish", body=_minimal_bea_json())
    svc, _ = _svc_with_payload(tmp_path, payload)
    result = svc.run(source_keys=("bea",), live=True)
    assert result.status == "blocked"
    assert "invalid_response" in result.error_codes


# A17 – "text/calendar; charset=utf-8" is accepted for BLS
def test_payload_calendar_with_charset_accepted(tmp_path):
    payload = _SimplePayload(source="bls", content_type="text/calendar; charset=utf-8", body=_minimal_bls_ics())
    svc, _ = _svc_with_payload(tmp_path, payload)
    result = svc.run(source_keys=("bls",), live=True)
    assert result.status == "dry_run"


# A18 – "application/json; charset=utf-8" is accepted for BEA
def test_payload_json_with_charset_accepted(tmp_path):
    payload = _SimplePayload(source="bea", content_type="application/json; charset=utf-8", body=_minimal_bea_json())
    svc, _ = _svc_with_payload(tmp_path, payload)
    result = svc.run(source_keys=("bea",), live=True)
    assert result.status == "dry_run"


# A19 – BLS payload invalid → BEA fetch is never called, no write
def test_bls_invalid_payload_bea_not_called(tmp_path):
    bad_bls = _SimplePayload(source="bls", content_type="text/html", body="garbage")

    class _SelectiveTransport:
        def __init__(self):
            self.call_log: list[str] = []

        def fetch(self, source):
            key = source.value if hasattr(source, "value") else str(source)
            self.call_log.append(key)
            if key == "bls":
                return bad_bls
            return _SimplePayload(source="bea", content_type="application/json", body=_minimal_bea_json())

    t = _SelectiveTransport()
    db_path = tmp_path / "cal.sqlite"
    cal_svc = EconomicCalendarService(db_path=db_path, now_provider=_now_provider)
    svc = OfficialCalendarAcquisitionService(
        transport_factory=lambda: t,
        calendar_service=cal_svc,
        now_provider=_now_provider,
    )
    result = svc.run(source_keys=("bls", "bea"), live=True, write=True)
    assert result.status == "blocked"
    assert "bea" not in t.call_log
    assert not (tmp_path / "cal.sqlite").exists()


# A20 – BEA payload invalid → entire batch blocked, no SQLite
def test_bea_invalid_payload_batch_blocked(tmp_path):
    good_bls = _SimplePayload(source="bls", content_type="text/calendar", body=_minimal_bls_ics())
    bad_bea = _SimplePayload(source="bea", content_type="text/plain", body="{}")

    class _SelectiveTransport2:
        def fetch(self, source):
            key = source.value if hasattr(source, "value") else str(source)
            return good_bls if key == "bls" else bad_bea

    db_path = tmp_path / "cal.sqlite"
    cal_svc = EconomicCalendarService(db_path=db_path, now_provider=_now_provider)
    svc = OfficialCalendarAcquisitionService(
        transport_factory=_SelectiveTransport2,
        calendar_service=cal_svc,
        now_provider=_now_provider,
    )
    result = svc.run(source_keys=("bls", "bea"), live=True, write=True)
    assert result.status == "blocked"
    assert "invalid_response" in result.error_codes
    assert not (tmp_path / "cal.sqlite").exists()


# A21 – transport validation failure creates no SQLite
def test_transport_validation_failure_no_db(tmp_path):
    payload = _SimplePayload(source="bls", content_type="text/calendar", body=None)
    svc, _ = _svc_with_payload(tmp_path, payload)
    svc.run(source_keys=("bls",), live=True, write=True)
    assert not (tmp_path / "cal.sqlite").exists()


# A22 – raw body marker does not appear in summary repr
def test_raw_body_marker_not_in_summary_repr(tmp_path):
    marker = "SECRET_BODY_MARKER_XYZ"
    payload = _SimplePayload(source="bls", content_type="text/html", body=marker)
    svc, _ = _svc_with_payload(tmp_path, payload)
    result = svc.run(source_keys=("bls",), live=True)
    assert marker not in repr(result)


# A23 – parser raises RuntimeError → blocked, code is "invalid_response"
def test_parser_runtime_error_becomes_invalid_response(tmp_path, monkeypatch):
    payload = _SimplePayload(source="bls", content_type="text/calendar", body=_minimal_bls_ics())
    svc, _ = _svc_with_payload(tmp_path, payload)
    import app_backend.services.official_calendar_acquisition_service as svc_mod
    monkeypatch.setattr(
        svc_mod,
        "parse_bls_calendar_ics",
        lambda *a: (_ for _ in ()).throw(RuntimeError("secret parser failure")),
    )
    result = svc.run(source_keys=("bls",), live=True)
    assert result.status == "blocked"
    assert "invalid_response" in result.error_codes


# A24 – parser RuntimeError text does not appear in summary repr
def test_parser_runtime_error_no_leak(tmp_path, monkeypatch):
    payload = _SimplePayload(source="bls", content_type="text/calendar", body=_minimal_bls_ics())
    svc, _ = _svc_with_payload(tmp_path, payload)
    import app_backend.services.official_calendar_acquisition_service as svc_mod
    monkeypatch.setattr(
        svc_mod,
        "parse_bls_calendar_ics",
        lambda *a: (_ for _ in ()).throw(RuntimeError("secret parser failure")),
    )
    result = svc.run(source_keys=("bls",), live=True)
    assert "secret parser failure" not in repr(result)


# ===========================================================================
# C4c: Writer-result boundary
# ===========================================================================

def _write_svc(tmp_path):
    transport = _FakeTransport(responses={"bls": _minimal_bls_ics(), "bea": _minimal_bea_json()})
    db_path = tmp_path / "cal.sqlite"
    cal_svc = EconomicCalendarService(db_path=db_path, now_provider=_now_provider)
    return OfficialCalendarAcquisitionService(
        transport_factory=lambda: transport,
        calendar_service=cal_svc,
        now_provider=_now_provider,
    ), cal_svc


# B1 – writer returns None
def test_writer_returns_none_blocked(tmp_path, monkeypatch):
    svc, cal_svc = _write_svc(tmp_path)
    monkeypatch.setattr(cal_svc, "upsert_events", lambda events: None)
    result = svc.run(source_keys=("bls", "bea"), live=True, write=True)
    assert result.status == "blocked"
    assert "write_failed" in result.error_codes


# B2 – writer returns list
def test_writer_returns_list_blocked(tmp_path, monkeypatch):
    svc, cal_svc = _write_svc(tmp_path)
    monkeypatch.setattr(cal_svc, "upsert_events", lambda events: [])
    result = svc.run(source_keys=("bls", "bea"), live=True, write=True)
    assert result.status == "blocked"
    assert "write_failed" in result.error_codes


# B3 – writer returns dict
def test_writer_returns_dict_blocked(tmp_path, monkeypatch):
    svc, cal_svc = _write_svc(tmp_path)
    monkeypatch.setattr(cal_svc, "upsert_events", lambda events: {"status": "ok"})
    result = svc.run(source_keys=("bls", "bea"), live=True, write=True)
    assert result.status == "blocked"
    assert "write_failed" in result.error_codes


# B4 – writer returns arbitrary object that duck-types but is not EconomicCalendarMutationResult
def test_writer_returns_nonresult_object_blocked(tmp_path, monkeypatch):
    class _Imposter:
        status = "ok"
        event_count = 4
        created_count = 4
        updated_count = 0

    svc, cal_svc = _write_svc(tmp_path)
    monkeypatch.setattr(cal_svc, "upsert_events", lambda events: _Imposter())
    result = svc.run(source_keys=("bls", "bea"), live=True, write=True)
    assert result.status == "blocked"
    assert "write_failed" in result.error_codes


# B5 – writer result status is not "ok"
def test_writer_status_not_ok_blocked(tmp_path, monkeypatch):
    svc, cal_svc = _write_svc(tmp_path)
    monkeypatch.setattr(
        cal_svc, "upsert_events",
        lambda events: EconomicCalendarMutationResult(
            status="error", event_count=4, created_count=4, updated_count=0
        ),
    )
    result = svc.run(source_keys=("bls", "bea"), live=True, write=True)
    assert result.status == "blocked"
    assert "write_failed" in result.error_codes


# B6 – event_count=True (bool is subclass of int but must be rejected)
def test_writer_event_count_bool_blocked(tmp_path, monkeypatch):
    svc, cal_svc = _write_svc(tmp_path)
    monkeypatch.setattr(
        cal_svc, "upsert_events",
        lambda events: EconomicCalendarMutationResult(
            status="ok", event_count=True, created_count=1, updated_count=0
        ),
    )
    result = svc.run(source_keys=("bls", "bea"), live=True, write=True)
    assert result.status == "blocked"
    assert "write_failed" in result.error_codes


# B7 – created_count=True
def test_writer_created_count_bool_blocked(tmp_path, monkeypatch):
    svc, cal_svc = _write_svc(tmp_path)
    monkeypatch.setattr(
        cal_svc, "upsert_events",
        lambda events: EconomicCalendarMutationResult(
            status="ok", event_count=4, created_count=True, updated_count=3
        ),
    )
    result = svc.run(source_keys=("bls", "bea"), live=True, write=True)
    assert result.status == "blocked"
    assert "write_failed" in result.error_codes


# B8 – negative count
def test_writer_negative_count_blocked(tmp_path, monkeypatch):
    svc, cal_svc = _write_svc(tmp_path)
    monkeypatch.setattr(
        cal_svc, "upsert_events",
        lambda events: EconomicCalendarMutationResult(
            status="ok", event_count=-1, created_count=-1, updated_count=0
        ),
    )
    result = svc.run(source_keys=("bls", "bea"), live=True, write=True)
    assert result.status == "blocked"
    assert "write_failed" in result.error_codes


# B9 – subclass with string count: rejected by exact-type check
def test_validate_mutation_counts_rejects_subclass():
    from app_backend.services.official_calendar_acquisition_service import _validate_mutation_counts

    class _Bad(EconomicCalendarMutationResult):
        pass

    bad = object.__new__(_Bad)
    object.__setattr__(bad, "status", "ok")
    object.__setattr__(bad, "event_count", "4")
    object.__setattr__(bad, "created_count", 4)
    object.__setattr__(bad, "updated_count", 0)
    assert _validate_mutation_counts(bad, 4) is None


# B10 – event_count mismatch via _validate_mutation_counts
def test_validate_mutation_counts_rejects_count_mismatch():
    from app_backend.services.official_calendar_acquisition_service import _validate_mutation_counts

    result = EconomicCalendarMutationResult(status="ok", event_count=999, created_count=999, updated_count=0)
    assert _validate_mutation_counts(result, 4) is None


# B11 – created + updated != event_count via _validate_mutation_counts
def test_validate_mutation_counts_rejects_sum_mismatch():
    from app_backend.services.official_calendar_acquisition_service import _validate_mutation_counts

    result = EconomicCalendarMutationResult(status="ok", event_count=4, created_count=3, updated_count=0)
    assert _validate_mutation_counts(result, 4) is None


# B12 – valid EconomicCalendarMutationResult returns the count tuple
def test_validate_mutation_counts_accepts_valid():
    from app_backend.services.official_calendar_acquisition_service import _validate_mutation_counts

    result = EconomicCalendarMutationResult(status="ok", event_count=4, created_count=4, updated_count=0)
    assert _validate_mutation_counts(result, 4) == (4, 4, 0)


# B13 – several malformed writer returns never produce status="ok"
def test_malformed_writer_never_returns_ok_status(tmp_path, monkeypatch):
    svc, cal_svc = _write_svc(tmp_path)
    for bad_return in [None, [], {}, object(), False, 0, "ok"]:
        monkeypatch.setattr(cal_svc, "upsert_events", lambda events, r=bad_return: r)
        result = svc.run(source_keys=("bls", "bea"), live=True, write=True)
        assert result.status != "ok", f"Expected non-ok for writer returning {bad_return!r}"


# B14 – writer exception text does not appear in summary repr
def test_writer_exception_no_leak(tmp_path, monkeypatch):
    svc, cal_svc = _write_svc(tmp_path)
    monkeypatch.setattr(
        cal_svc,
        "upsert_events",
        lambda events: (_ for _ in ()).throw(RuntimeError("secret_db_error_xyzzy")),
    )
    result = svc.run(source_keys=("bls", "bea"), live=True, write=True)
    assert "secret_db_error_xyzzy" not in repr(result)
    assert result.status == "blocked"


# B15 – C4b success path still works after C4c changes
def test_c4b_bls_bea_write_still_succeeds_after_c4c(tmp_path):
    transport = _FakeTransport(responses={"bls": _minimal_bls_ics(), "bea": _minimal_bea_json()})
    svc = _service(tmp_path, transport)
    result = svc.run(source_keys=("bls", "bea"), live=True, write=True)
    assert result.status == "ok"
    assert result.event_count == 4
    assert result.created_count == 4
    assert result.updated_count == 0
    assert (tmp_path / "cal.sqlite").exists()


# ===========================================================================
# C4e: Exception-total payload and writer-result hardening
# ===========================================================================

_SECRET = "SECRET_LEAK_TOKEN_C4E"


class _SourcePropertyRaises:
    """Payload whose .source property raises RuntimeError."""

    content_type = "text/calendar"
    body = "BEGIN:VCALENDAR\nEND:VCALENDAR"

    @property
    def source(self):
        raise RuntimeError(_SECRET + "_source")


class _ContentTypePropertyRaises:
    """Payload whose .content_type property raises RuntimeError."""

    source = "bls"
    body = "BEGIN:VCALENDAR\nEND:VCALENDAR"

    @property
    def content_type(self):
        raise RuntimeError(_SECRET + "_ct")


class _BodyPropertyRaises:
    """Payload whose .body property raises RuntimeError."""

    source = "bls"
    content_type = "text/calendar"

    @property
    def body(self):
        raise RuntimeError(_SECRET + "_body")


class _GetattributeRaises:
    """Payload whose generic attribute access raises RuntimeError."""

    def __getattribute__(self, name):
        if name in {"source", "content_type", "body"}:
            raise RuntimeError(_SECRET + "_getattr_" + name)
        return object.__getattribute__(self, name)


class _EnumValueRaises:
    """An enum-like object whose .value property raises RuntimeError."""

    @property
    def value(self):
        raise RuntimeError(_SECRET + "_value")


class _RaisingContentTypeStr(str):
    """str subclass whose .split raises RuntimeError."""

    def split(self, *_args, **_kwargs):  # type: ignore[override]
        raise RuntimeError(_SECRET + "_split")


class _RaisingBodyStr(str):
    """str subclass whose .encode raises RuntimeError."""

    def encode(self, *_args, **_kwargs):  # type: ignore[override]
        raise RuntimeError(_SECRET + "_encode")


# ---- A. Payload property / dynamic-object failures ----

def test_c4e_source_property_raises_blocked(tmp_path):
    svc, transport = _svc_with_payload(tmp_path, _SourcePropertyRaises())
    result = svc.run(source_keys=("bls",), live=True, write=True)
    assert result.status == "blocked"
    assert result.error_codes == ["invalid_response"]
    assert _SECRET not in repr(result)
    assert not (tmp_path / "cal.sqlite").exists()


def test_c4e_content_type_property_raises_blocked(tmp_path):
    svc, transport = _svc_with_payload(tmp_path, _ContentTypePropertyRaises())
    result = svc.run(source_keys=("bls",), live=True, write=True)
    assert result.status == "blocked"
    assert result.error_codes == ["invalid_response"]
    assert _SECRET not in repr(result)
    assert not (tmp_path / "cal.sqlite").exists()


def test_c4e_body_property_raises_blocked(tmp_path):
    svc, transport = _svc_with_payload(tmp_path, _BodyPropertyRaises())
    result = svc.run(source_keys=("bls",), live=True, write=True)
    assert result.status == "blocked"
    assert result.error_codes == ["invalid_response"]
    assert _SECRET not in repr(result)
    assert not (tmp_path / "cal.sqlite").exists()


def test_c4e_getattribute_raises_blocked(tmp_path):
    svc, transport = _svc_with_payload(tmp_path, _GetattributeRaises())
    result = svc.run(source_keys=("bls",), live=True, write=True)
    assert result.status == "blocked"
    assert result.error_codes == ["invalid_response"]
    assert _SECRET not in repr(result)
    assert not (tmp_path / "cal.sqlite").exists()


def test_c4e_enum_value_property_raises_blocked(tmp_path):
    payload = _SimplePayload(
        source=_EnumValueRaises(),
        content_type="text/calendar",
        body=_minimal_bls_ics(),
    )
    svc, transport = _svc_with_payload(tmp_path, payload)
    result = svc.run(source_keys=("bls",), live=True, write=True)
    assert result.status == "blocked"
    assert result.error_codes == ["invalid_response"]
    assert _SECRET not in repr(result)
    assert not (tmp_path / "cal.sqlite").exists()


def test_c4e_content_type_str_subclass_split_raises_blocked(tmp_path):
    bad_ct = _RaisingContentTypeStr("text/calendar")
    payload = _SimplePayload(
        source="bls",
        content_type=bad_ct,
        body=_minimal_bls_ics(),
    )
    svc, transport = _svc_with_payload(tmp_path, payload)
    result = svc.run(source_keys=("bls",), live=True, write=True)
    assert result.status == "blocked"
    assert result.error_codes == ["invalid_response"]
    assert _SECRET not in repr(result)
    assert not (tmp_path / "cal.sqlite").exists()


def test_c4e_body_str_subclass_encode_raises_blocked(tmp_path):
    bad_body = _RaisingBodyStr(_minimal_bls_ics())
    payload = _SimplePayload(
        source="bls",
        content_type="text/calendar",
        body=bad_body,
    )
    svc, transport = _svc_with_payload(tmp_path, payload)
    result = svc.run(source_keys=("bls",), live=True, write=True)
    assert result.status == "blocked"
    assert result.error_codes == ["invalid_response"]
    assert _SECRET not in repr(result)
    assert not (tmp_path / "cal.sqlite").exists()


def test_c4e_payload_property_failures_writer_zero_calls(tmp_path, monkeypatch):
    """For every dynamic-object payload failure, the writer must remain uncalled."""
    db_path = tmp_path / "cal.sqlite"
    cal_svc = EconomicCalendarService(db_path=db_path, now_provider=_now_provider)
    writer_calls: list[object] = []
    monkeypatch.setattr(
        cal_svc,
        "upsert_events",
        lambda events: writer_calls.append(events) or EconomicCalendarMutationResult(
            status="ok", event_count=0, created_count=0, updated_count=0,
        ),
    )
    payloads = [
        _SourcePropertyRaises(),
        _ContentTypePropertyRaises(),
        _BodyPropertyRaises(),
        _GetattributeRaises(),
    ]
    for payload in payloads:
        t = _PayloadTransport(payload)
        svc = OfficialCalendarAcquisitionService(
            transport_factory=lambda transport=t: transport,
            calendar_service=cal_svc,
            now_provider=_now_provider,
        )
        result = svc.run(source_keys=("bls",), live=True, write=True)
        assert result.status == "blocked"
        assert result.error_codes == ["invalid_response"]
    assert writer_calls == []


# ---- B. Outer-call safety net ----

def test_c4e_outer_safety_net_when_helper_raises(tmp_path, monkeypatch):
    """Even if the payload helper itself is broken to raise, run() must fail closed."""
    payload = _SimplePayload(
        source="bls",
        content_type="text/calendar",
        body=_minimal_bls_ics(),
    )
    svc, transport = _svc_with_payload(tmp_path, payload)

    import app_backend.services.official_calendar_acquisition_service as svc_mod

    def _raise(*_args, **_kwargs):
        raise RuntimeError(_SECRET + "_helper")

    monkeypatch.setattr(svc_mod, "_validate_transport_payload", _raise)
    result = svc.run(source_keys=("bls",), live=True, write=True)
    assert result.status == "blocked"
    assert result.error_codes == ["invalid_response"]
    assert _SECRET not in repr(result)
    assert not (tmp_path / "cal.sqlite").exists()


def test_c4e_outer_safety_net_writer_helper_raises(tmp_path, monkeypatch):
    """If the mutation-count helper itself raises, run() falls back to blocked."""
    transport = _FakeTransport(
        responses={"bls": _minimal_bls_ics(), "bea": _minimal_bea_json()},
    )
    db_path = tmp_path / "cal.sqlite"
    cal_svc = EconomicCalendarService(db_path=db_path, now_provider=_now_provider)
    svc = OfficialCalendarAcquisitionService(
        transport_factory=lambda: transport,
        calendar_service=cal_svc,
        now_provider=_now_provider,
    )
    import app_backend.services.official_calendar_acquisition_service as svc_mod

    def _raise(*_args, **_kwargs):
        raise RuntimeError(_SECRET + "_count_helper")

    monkeypatch.setattr(svc_mod, "_validate_mutation_counts", _raise)
    result = svc.run(source_keys=("bls", "bea"), live=True, write=True)
    assert result.status == "blocked"
    assert result.error_codes == ["write_failed"]
    assert _SECRET not in repr(result)


# ---- C. Writer TOCTOU / subclass failures ----

def test_c4e_writer_subclass_rejected(tmp_path, monkeypatch):
    """Even a subclass with otherwise-valid counts must be rejected."""

    class _SubResult(EconomicCalendarMutationResult):
        pass

    sub = object.__new__(_SubResult)
    object.__setattr__(sub, "status", "ok")
    object.__setattr__(sub, "event_count", 4)
    object.__setattr__(sub, "created_count", 4)
    object.__setattr__(sub, "updated_count", 0)
    svc, cal_svc = _write_svc(tmp_path)
    monkeypatch.setattr(cal_svc, "upsert_events", lambda events: sub)
    result = svc.run(source_keys=("bls", "bea"), live=True, write=True)
    assert result.status == "blocked"
    assert result.error_codes == ["write_failed"]


def test_c4e_writer_subclass_getattribute_raises(tmp_path, monkeypatch):
    """Subclass whose __getattribute__ raises on count reads must be rejected."""

    class _RaisingResult(EconomicCalendarMutationResult):
        def __getattribute__(self, name):
            if name == "event_count":
                raise RuntimeError(_SECRET + "_getattribute_event_count")
            return object.__getattribute__(self, name)

    bad = object.__new__(_RaisingResult)
    object.__setattr__(bad, "status", "ok")
    object.__setattr__(bad, "event_count", 4)
    object.__setattr__(bad, "created_count", 4)
    object.__setattr__(bad, "updated_count", 0)
    svc, cal_svc = _write_svc(tmp_path)
    monkeypatch.setattr(cal_svc, "upsert_events", lambda events: bad)
    result = svc.run(source_keys=("bls", "bea"), live=True, write=True)
    assert result.status == "blocked"
    assert result.error_codes == ["write_failed"]
    assert _SECRET not in repr(result)


def test_c4e_writer_property_status_raises(tmp_path, monkeypatch):
    """Imposter object with a status property that raises must be rejected, not crash run()."""

    class _ImposterStatusRaises:
        event_count = 4
        created_count = 4
        updated_count = 0

        @property
        def status(self):
            raise RuntimeError(_SECRET + "_status_property")

    svc, cal_svc = _write_svc(tmp_path)
    monkeypatch.setattr(cal_svc, "upsert_events", lambda events: _ImposterStatusRaises())
    result = svc.run(source_keys=("bls", "bea"), live=True, write=True)
    assert result.status == "blocked"
    assert result.error_codes == ["write_failed"]
    assert _SECRET not in repr(result)


def test_c4e_writer_imposter_duck_typed_rejected(tmp_path, monkeypatch):
    """An imposter with matching field names but wrong exact type is rejected."""

    class _DuckImposter:
        status = "ok"
        event_count = 4
        created_count = 4
        updated_count = 0

    svc, cal_svc = _write_svc(tmp_path)
    monkeypatch.setattr(cal_svc, "upsert_events", lambda events: _DuckImposter())
    result = svc.run(source_keys=("bls", "bea"), live=True, write=True)
    assert result.status == "blocked"
    assert result.error_codes == ["write_failed"]


def test_c4e_writer_toctou_subclass_flipping_counts(tmp_path, monkeypatch):
    """A subclass that flips its count attribute between reads must not influence the summary.

    Because the helper now returns captured primitive counts and the success
    summary uses only those primitives, even if the writer object mutates its
    underlying attributes between reads, no malformed value can reach the
    summary — the helper rejects subclasses outright.
    """

    class _FlippingSub(EconomicCalendarMutationResult):
        _reads: list[int] = []

        def __getattribute__(self, name):
            if name == "event_count":
                reads = object.__getattribute__(type(self), "_reads")
                reads.append(len(reads))
                if len(reads) == 1:
                    return 4
                return 999
            return object.__getattribute__(self, name)

    flipping = object.__new__(_FlippingSub)
    object.__setattr__(flipping, "status", "ok")
    object.__setattr__(flipping, "event_count", 4)
    object.__setattr__(flipping, "created_count", 4)
    object.__setattr__(flipping, "updated_count", 0)
    svc, cal_svc = _write_svc(tmp_path)
    monkeypatch.setattr(cal_svc, "upsert_events", lambda events: flipping)
    result = svc.run(source_keys=("bls", "bea"), live=True, write=True)
    # Subclass rejected, so write_failed and counts are 0, not 999.
    assert result.status == "blocked"
    assert result.error_codes == ["write_failed"]
    assert result.event_count == 0
    assert result.updated_count == 0
    assert result.created_count == 0


# ---- D. Regression: legitimate paths still pass ----

def test_c4e_regression_bls_bea_dry_run_succeeds(tmp_path):
    transport = _FakeTransport(
        responses={"bls": _minimal_bls_ics(), "bea": _minimal_bea_json()},
    )
    svc = _service(tmp_path, transport)
    result = svc.run(source_keys=("bls", "bea"), live=True)
    assert result.status == "dry_run"
    assert result.event_count == 4
    assert not (tmp_path / "cal.sqlite").exists()


def test_c4e_regression_bls_bea_live_write_succeeds(tmp_path):
    transport = _FakeTransport(
        responses={"bls": _minimal_bls_ics(), "bea": _minimal_bea_json()},
    )
    svc = _service(tmp_path, transport)
    result = svc.run(source_keys=("bls", "bea"), live=True, write=True)
    assert result.status == "ok"
    assert result.event_count == 4
    assert result.created_count == 4
    assert result.updated_count == 0
    assert (tmp_path / "cal.sqlite").exists()


def test_c4e_regression_fomc_still_unavailable(tmp_path):
    svc = _service(tmp_path)
    result = svc.run(source_keys=("bls",))
    assert result.unavailable_event_keys == ("fomc_statement",)


def test_c4e_regression_no_live_writes_zero_db(tmp_path):
    transport = _FakeTransport()
    svc = _service(tmp_path, transport)
    svc.run(source_keys=("bls", "bea"))
    svc.run(source_keys=("bls", "bea"), write=True)
    assert transport.call_log == []
    assert not (tmp_path / "cal.sqlite").exists()
