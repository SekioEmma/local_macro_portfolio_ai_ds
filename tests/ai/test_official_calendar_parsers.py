from __future__ import annotations

import json
import socket
from pathlib import Path

import pytest

from app_backend.services.official_calendar_parsers import (
    OfficialCalendarParseError,
    parse_bea_release_dates_json,
    parse_bls_calendar_ics,
)
from app_backend.services.economic_calendar_contracts import (
    EconomicCalendarEventInput,
)


_INGESTED = "2026-06-01T00:00:00+00:00"
_START = "2026-01-01"
_END = "2026-12-31"


def _ics_event(summary: str, dtstart: str, dtstart_params: str = "") -> str:
    dtstart_line = f"DTSTART{dtstart_params}:{dtstart}" if dtstart_params else f"DTSTART:{dtstart}"
    return f"BEGIN:VEVENT\n{dtstart_line}\nSUMMARY:{summary}\nEND:VEVENT"


def _ics_wrap(*events: str) -> str:
    body = "\n".join(events)
    return f"BEGIN:VCALENDAR\n{body}\nEND:VCALENDAR"


def _bea_json(**releases: list[str]) -> str:
    data: dict = {}
    for name, dates in releases.items():
        data[name] = {"release_dates": dates}
    return json.dumps(data)


def _minimal_bls_ics() -> str:
    return _ics_wrap(
        _ics_event("Consumer Price Index", "20260115T083000"),
        _ics_event("Employment Situation", "20260207T083000"),
    )


def _minimal_bea_json() -> str:
    return _bea_json(
        **{
            "Personal Income and Outlays": ["2026-01-31T08:30:00-05:00"],
            "Gross Domestic Product": ["2026-02-28T08:30:00-05:00"],
        }
    )


# ---- BLS folded lines ----

def test_bls_folded_lines_parsed_correctly():
    ics = _ics_wrap(
        "BEGIN:VEVENT\nDTSTART:20260115T083000\nSUMMARY:Consumer Price\n  Index\nEND:VEVENT",
        _ics_event("Employment Situation", "20260207T083000"),
    )
    result = parse_bls_calendar_ics(ics, _START, _END, _INGESTED)
    keys = {e.event_key for e in result}
    assert "consumer_price_index" in keys


def test_bls_folded_with_tab():
    ics = _ics_wrap(
        "BEGIN:VEVENT\nDTSTART:20260115T083000\nSUMMARY:Consumer Price\n\t Index\nEND:VEVENT",
        _ics_event("Employment Situation", "20260207T083000"),
    )
    result = parse_bls_calendar_ics(ics, _START, _END, _INGESTED)
    keys = {e.event_key for e in result}
    assert "consumer_price_index" in keys


# ---- BLS UTC datetime ----

def test_bls_utc_dtstart():
    ics = _ics_wrap(
        _ics_event("Consumer Price Index", "20260115T133000Z"),
        _ics_event("Employment Situation", "20260207T133000Z"),
    )
    result = parse_bls_calendar_ics(ics, _START, _END, _INGESTED)
    cpi = [e for e in result if e.event_key == "consumer_price_index"][0]
    assert cpi.release_time_et == "08:30"


# ---- BLS TZID=America/New_York ----

def test_bls_tzid_et():
    ics = _ics_wrap(
        _ics_event("Consumer Price Index", "20260115T083000", ";TZID=America/New_York"),
        _ics_event("Employment Situation", "20260207T083000", ";TZID=America/New_York"),
    )
    result = parse_bls_calendar_ics(ics, _START, _END, _INGESTED)
    cpi = [e for e in result if e.event_key == "consumer_price_index"][0]
    assert cpi.release_date == "2026-01-15"
    assert cpi.release_time_et == "08:30"


# ---- BLS floating datetime (ET assumed) ----

def test_bls_floating_et():
    result = parse_bls_calendar_ics(_minimal_bls_ics(), _START, _END, _INGESTED)
    cpi = [e for e in result if e.event_key == "consumer_price_index"][0]
    assert cpi.release_time_et == "08:30"
    assert cpi.release_date == "2026-01-15"


# ---- BLS CPI detection ----

def test_bls_cpi_detected():
    result = parse_bls_calendar_ics(_minimal_bls_ics(), _START, _END, _INGESTED)
    assert any(e.event_key == "consumer_price_index" for e in result)


# ---- BLS Employment Situation detection ----

def test_bls_employment_detected():
    result = parse_bls_calendar_ics(_minimal_bls_ics(), _START, _END, _INGESTED)
    assert any(e.event_key == "employment_situation" for e in result)


# ---- BLS non-target events ignored ----

def test_bls_non_target_ignored():
    ics = _ics_wrap(
        _ics_event("Consumer Price Index", "20260115T083000"),
        _ics_event("Employment Situation", "20260207T083000"),
        _ics_event("Producer Price Index", "20260310T083000"),
        _ics_event("Job Openings and Labor Turnover Survey", "20260410T100000"),
    )
    result = parse_bls_calendar_ics(ics, _START, _END, _INGESTED)
    keys = {e.event_key for e in result}
    assert keys == {"consumer_price_index", "employment_situation"}


# ---- BLS malformed relevant event fail-closed ----

def test_bls_malformed_cpi_dtstart_fails():
    ics = _ics_wrap(
        _ics_event("Consumer Price Index", "BADDATE"),
        _ics_event("Employment Situation", "20260207T083000"),
    )
    with pytest.raises(OfficialCalendarParseError) as exc_info:
        parse_bls_calendar_ics(ics, _START, _END, _INGESTED)
    assert exc_info.value.code == "malformed_source_payload"


def test_bls_missing_dtstart_fails():
    ics = _ics_wrap(
        "BEGIN:VEVENT\nSUMMARY:Consumer Price Index\nEND:VEVENT",
        _ics_event("Employment Situation", "20260207T083000"),
    )
    with pytest.raises(OfficialCalendarParseError) as exc_info:
        parse_bls_calendar_ics(ics, _START, _END, _INGESTED)
    assert exc_info.value.code == "malformed_source_payload"


# ---- BLS missing required category ----

def test_bls_missing_cpi_fails():
    ics = _ics_wrap(
        _ics_event("Employment Situation", "20260207T083000"),
    )
    with pytest.raises(OfficialCalendarParseError) as exc_info:
        parse_bls_calendar_ics(ics, _START, _END, _INGESTED)
    assert exc_info.value.code == "missing_required_event_key"


def test_bls_missing_employment_fails():
    ics = _ics_wrap(
        _ics_event("Consumer Price Index", "20260115T083000"),
    )
    with pytest.raises(OfficialCalendarParseError) as exc_info:
        parse_bls_calendar_ics(ics, _START, _END, _INGESTED)
    assert exc_info.value.code == "missing_required_event_key"


# ---- BLS date filtering ----

def test_bls_events_outside_range_excluded():
    ics = _ics_wrap(
        _ics_event("Consumer Price Index", "20260115T083000"),
        _ics_event("Consumer Price Index", "20250115T083000"),
        _ics_event("Employment Situation", "20260207T083000"),
    )
    result = parse_bls_calendar_ics(ics, _START, _END, _INGESTED)
    dates = [e.release_date for e in result if e.event_key == "consumer_price_index"]
    assert "2025-01-15" not in dates


def test_bls_date_range_edge_start_inclusive():
    ics = _ics_wrap(
        _ics_event("Consumer Price Index", "20260101T083000"),
        _ics_event("Employment Situation", "20260207T083000"),
    )
    result = parse_bls_calendar_ics(ics, _START, _END, _INGESTED)
    assert any(e.release_date == "2026-01-01" for e in result)


def test_bls_date_range_edge_end_inclusive():
    ics = _ics_wrap(
        _ics_event("Consumer Price Index", "20260115T083000"),
        _ics_event("Employment Situation", "20261231T083000"),
    )
    result = parse_bls_calendar_ics(ics, _START, _END, _INGESTED)
    assert any(e.release_date == "2026-12-31" for e in result)


# ---- BLS duplicate events ----

def test_bls_duplicate_deduped():
    ics = _ics_wrap(
        _ics_event("Consumer Price Index", "20260115T083000"),
        _ics_event("Consumer Price Index", "20260115T083000"),
        _ics_event("Employment Situation", "20260207T083000"),
    )
    result = parse_bls_calendar_ics(ics, _START, _END, _INGESTED)
    cpi = [e for e in result if e.event_key == "consumer_price_index"]
    assert len(cpi) == 1


# ---- BLS source URL fixed ----

def test_bls_source_url_fixed():
    result = parse_bls_calendar_ics(_minimal_bls_ics(), _START, _END, _INGESTED)
    for event in result:
        assert event.source_url == "https://www.bls.gov/schedule/news_release/bls.ics"


# ---- BLS output valid EconomicCalendarEventInput ----

def test_bls_output_types():
    result = parse_bls_calendar_ics(_minimal_bls_ics(), _START, _END, _INGESTED)
    for event in result:
        assert isinstance(event, EconomicCalendarEventInput)


# ---- BEA JSON two required keys ----

def test_bea_both_keys_present():
    result = parse_bea_release_dates_json(_minimal_bea_json(), _START, _END, _INGESTED)
    keys = {e.event_key for e in result}
    assert keys == {"personal_income_and_outlays", "gross_domestic_product"}


# ---- BEA offset conversion ----

def test_bea_utc_offset_converted_to_et():
    payload = _bea_json(
        **{
            "Personal Income and Outlays": ["2026-01-31T13:30:00+00:00"],
            "Gross Domestic Product": ["2026-02-28T13:30:00+00:00"],
        }
    )
    result = parse_bea_release_dates_json(payload, _START, _END, _INGESTED)
    pce = [e for e in result if e.event_key == "personal_income_and_outlays"][0]
    assert pce.release_time_et == "08:30"


# ---- BEA DST conversion ----

def test_bea_dst_conversion():
    payload = _bea_json(
        **{
            "Personal Income and Outlays": ["2026-07-31T12:30:00+00:00"],
            "Gross Domestic Product": ["2026-07-29T12:30:00+00:00"],
        }
    )
    result = parse_bea_release_dates_json(payload, "2026-07-01", "2026-08-31", _INGESTED)
    pce = [e for e in result if e.event_key == "personal_income_and_outlays"][0]
    assert pce.release_time_et == "08:30"


def test_bea_winter_offset():
    payload = _bea_json(
        **{
            "Personal Income and Outlays": ["2026-01-15T08:30:00-05:00"],
            "Gross Domestic Product": ["2026-01-29T08:30:00-05:00"],
        }
    )
    result = parse_bea_release_dates_json(payload, _START, _END, _INGESTED)
    pce = [e for e in result if e.event_key == "personal_income_and_outlays"][0]
    assert pce.release_time_et == "08:30"
    assert pce.release_date == "2026-01-15"


# ---- BEA malformed JSON ----

def test_bea_malformed_json_raises():
    with pytest.raises(OfficialCalendarParseError) as exc_info:
        parse_bea_release_dates_json("not json", _START, _END, _INGESTED)
    assert exc_info.value.code == "malformed_source_payload"


def test_bea_json_array_raises():
    with pytest.raises(OfficialCalendarParseError) as exc_info:
        parse_bea_release_dates_json("[]", _START, _END, _INGESTED)
    assert exc_info.value.code == "malformed_source_payload"


# ---- BEA missing key ----

def test_bea_missing_pce_key_raises():
    payload = _bea_json(
        **{"Gross Domestic Product": ["2026-02-28T08:30:00-05:00"]}
    )
    with pytest.raises(OfficialCalendarParseError) as exc_info:
        parse_bea_release_dates_json(payload, _START, _END, _INGESTED)
    assert exc_info.value.code == "missing_required_event_key"


def test_bea_missing_gdp_key_raises():
    payload = _bea_json(
        **{"Personal Income and Outlays": ["2026-01-31T08:30:00-05:00"]}
    )
    with pytest.raises(OfficialCalendarParseError) as exc_info:
        parse_bea_release_dates_json(payload, _START, _END, _INGESTED)
    assert exc_info.value.code == "missing_required_event_key"


# ---- BEA malformed datetime ----

def test_bea_malformed_timestamp_raises():
    payload = _bea_json(
        **{
            "Personal Income and Outlays": ["not-a-date"],
            "Gross Domestic Product": ["2026-02-28T08:30:00-05:00"],
        }
    )
    with pytest.raises(OfficialCalendarParseError) as exc_info:
        parse_bea_release_dates_json(payload, _START, _END, _INGESTED)
    assert exc_info.value.code == "malformed_source_payload"


# ---- BEA missing offset ----

def test_bea_naive_timestamp_raises():
    payload = _bea_json(
        **{
            "Personal Income and Outlays": ["2026-01-31T08:30:00"],
            "Gross Domestic Product": ["2026-02-28T08:30:00-05:00"],
        }
    )
    with pytest.raises(OfficialCalendarParseError) as exc_info:
        parse_bea_release_dates_json(payload, _START, _END, _INGESTED)
    assert exc_info.value.code == "malformed_source_payload"


# ---- BEA date range empty ----

def test_bea_all_out_of_range_raises():
    payload = _bea_json(
        **{
            "Personal Income and Outlays": ["2025-01-31T08:30:00-05:00"],
            "Gross Domestic Product": ["2025-02-28T08:30:00-05:00"],
        }
    )
    with pytest.raises(OfficialCalendarParseError) as exc_info:
        parse_bea_release_dates_json(payload, _START, _END, _INGESTED)
    assert exc_info.value.code == "missing_required_event_key"


# ---- BEA duplicate timestamps ----

def test_bea_duplicates_deduped():
    payload = _bea_json(
        **{
            "Personal Income and Outlays": [
                "2026-01-31T08:30:00-05:00",
                "2026-01-31T08:30:00-05:00",
            ],
            "Gross Domestic Product": ["2026-02-28T08:30:00-05:00"],
        }
    )
    result = parse_bea_release_dates_json(payload, _START, _END, _INGESTED)
    pce = [e for e in result if e.event_key == "personal_income_and_outlays"]
    assert len(pce) == 1


# ---- BEA source URL fixed ----

def test_bea_source_url_fixed():
    result = parse_bea_release_dates_json(_minimal_bea_json(), _START, _END, _INGESTED)
    for event in result:
        assert event.source_url == "https://apps.bea.gov/API/signup/release_dates.json"


# ---- BEA output types ----

def test_bea_output_types():
    result = parse_bea_release_dates_json(_minimal_bea_json(), _START, _END, _INGESTED)
    for event in result:
        assert isinstance(event, EconomicCalendarEventInput)


# ---- No FOMC in output ----

def test_bls_no_fomc_output():
    ics = _ics_wrap(
        _ics_event("Consumer Price Index", "20260115T083000"),
        _ics_event("Employment Situation", "20260207T083000"),
        _ics_event("FOMC Statement", "20260318T140000"),
    )
    result = parse_bls_calendar_ics(ics, _START, _END, _INGESTED)
    assert not any(e.event_key == "fomc_statement" for e in result)


def test_bea_no_fomc_key():
    payload = _bea_json(
        **{
            "Personal Income and Outlays": ["2026-01-31T08:30:00-05:00"],
            "Gross Domestic Product": ["2026-02-28T08:30:00-05:00"],
            "FOMC Statement": ["2026-03-18T14:00:00-04:00"],
        }
    )
    result = parse_bea_release_dates_json(payload, _START, _END, _INGESTED)
    assert not any(e.event_key == "fomc_statement" for e in result)


# ---- No network / SQLite / filesystem side effect ----

def test_parsers_no_network_side_effect(monkeypatch):
    def block(*a, **kw):
        raise AssertionError("parsers must not touch network")

    monkeypatch.setattr(socket, "create_connection", block)
    parse_bls_calendar_ics(_minimal_bls_ics(), _START, _END, _INGESTED)
    parse_bea_release_dates_json(_minimal_bea_json(), _START, _END, _INGESTED)


def test_parsers_no_filesystem_side_effect(tmp_path):
    before = set(tmp_path.iterdir())
    parse_bls_calendar_ics(_minimal_bls_ics(), _START, _END, _INGESTED)
    parse_bea_release_dates_json(_minimal_bea_json(), _START, _END, _INGESTED)
    assert set(tmp_path.iterdir()) == before


# ---- Parser source has no network or SQLite imports ----

def test_parser_source_no_forbidden_imports():
    source_path = Path(__file__).parents[2] / "src" / "app_backend" / "services" / "official_calendar_parsers.py"
    source = source_path.read_text(encoding="utf-8")
    for token in ["httpx", "requests", "aiohttp", "sqlite3", "FastAPI", "pathlib", "os.environ", "os.getenv"]:
        assert token not in source


# ---- BEA non-list release_dates ----

def test_bea_release_dates_not_list_raises():
    payload = json.dumps({
        "Personal Income and Outlays": {"release_dates": "2026-01-31T08:30:00-05:00"},
        "Gross Domestic Product": {"release_dates": ["2026-02-28T08:30:00-05:00"]},
    })
    with pytest.raises(OfficialCalendarParseError) as exc_info:
        parse_bea_release_dates_json(payload, _START, _END, _INGESTED)
    assert exc_info.value.code == "malformed_source_payload"


# ---- BEA non-dict entry ----

def test_bea_non_dict_entry_raises():
    payload = json.dumps({
        "Personal Income and Outlays": ["2026-01-31T08:30:00-05:00"],
        "Gross Domestic Product": {"release_dates": ["2026-02-28T08:30:00-05:00"]},
    })
    with pytest.raises(OfficialCalendarParseError) as exc_info:
        parse_bea_release_dates_json(payload, _START, _END, _INGESTED)
    assert exc_info.value.code == "malformed_source_payload"


# ---- BEA non-string timestamp ----

def test_bea_non_string_timestamp_raises():
    payload = json.dumps({
        "Personal Income and Outlays": {"release_dates": [12345]},
        "Gross Domestic Product": {"release_dates": ["2026-02-28T08:30:00-05:00"]},
    })
    with pytest.raises(OfficialCalendarParseError) as exc_info:
        parse_bea_release_dates_json(payload, _START, _END, _INGESTED)
    assert exc_info.value.code == "malformed_source_payload"


# ---- BEA Z suffix handled ----

def test_bea_z_suffix_handled():
    payload = _bea_json(
        **{
            "Personal Income and Outlays": ["2026-01-31T13:30:00Z"],
            "Gross Domestic Product": ["2026-02-28T13:30:00Z"],
        }
    )
    result = parse_bea_release_dates_json(payload, _START, _END, _INGESTED)
    pce = [e for e in result if e.event_key == "personal_income_and_outlays"][0]
    assert pce.release_time_et == "08:30"


# ---- BLS multiple events same key different dates ----

def test_bls_multiple_cpi_dates():
    ics = _ics_wrap(
        _ics_event("Consumer Price Index", "20260115T083000"),
        _ics_event("Consumer Price Index", "20260212T083000"),
        _ics_event("Consumer Price Index", "20260312T083000"),
        _ics_event("Employment Situation", "20260207T083000"),
    )
    result = parse_bls_calendar_ics(ics, _START, _END, _INGESTED)
    cpi = [e for e in result if e.event_key == "consumer_price_index"]
    assert len(cpi) == 3


# ---- BEA multiple releases ----

def test_bea_multiple_gdp_releases():
    payload = _bea_json(
        **{
            "Personal Income and Outlays": ["2026-01-31T08:30:00-05:00"],
            "Gross Domestic Product": [
                "2026-01-29T08:30:00-05:00",
                "2026-02-26T08:30:00-05:00",
                "2026-03-26T08:30:00-05:00",
            ],
        }
    )
    result = parse_bea_release_dates_json(payload, _START, _END, _INGESTED)
    gdp = [e for e in result if e.event_key == "gross_domestic_product"]
    assert len(gdp) == 3


# ---- BLS ingested_at passthrough ----

def test_bls_ingested_at_passthrough():
    result = parse_bls_calendar_ics(_minimal_bls_ics(), _START, _END, _INGESTED)
    for event in result:
        assert event.ingested_at == _INGESTED


# ---- BEA ingested_at passthrough ----

def test_bea_ingested_at_passthrough():
    result = parse_bea_release_dates_json(_minimal_bea_json(), _START, _END, _INGESTED)
    for event in result:
        assert event.ingested_at == _INGESTED


# ---- BLS case-insensitive summary matching ----

def test_bls_case_insensitive_summary():
    ics = _ics_wrap(
        _ics_event("CONSUMER PRICE INDEX", "20260115T083000"),
        _ics_event("employment situation", "20260207T083000"),
    )
    result = parse_bls_calendar_ics(ics, _START, _END, _INGESTED)
    keys = {e.event_key for e in result}
    assert keys == {"consumer_price_index", "employment_situation"}


# ---- BLS empty VEVENT list (both required missing) ----

def test_bls_empty_ics_fails():
    ics = "BEGIN:VCALENDAR\nEND:VCALENDAR"
    with pytest.raises(OfficialCalendarParseError) as exc_info:
        parse_bls_calendar_ics(ics, _START, _END, _INGESTED)
    assert exc_info.value.code == "missing_required_event_key"
