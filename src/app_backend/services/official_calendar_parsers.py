from __future__ import annotations

import json
import re
from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

from app_backend.services.economic_calendar_contracts import (
    EconomicCalendarEventInput,
)

_ET = ZoneInfo("America/New_York")

_BLS_SOURCE_URL = "https://www.bls.gov/schedule/news_release/bls.ics"
_BEA_SOURCE_URL = "https://apps.bea.gov/API/signup/release_dates.json"

_BLS_EVENT_MAP: dict[str, str] = {
    "consumer price index": "consumer_price_index",
    "employment situation": "employment_situation",
}

_BEA_EVENT_MAP: dict[str, str] = {
    "Personal Income and Outlays": "personal_income_and_outlays",
    "Gross Domestic Product": "gross_domestic_product",
}


class OfficialCalendarParseError(ValueError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def parse_bls_calendar_ics(
    payload: str,
    start_date: str,
    end_date: str,
    ingested_at: str,
) -> list[EconomicCalendarEventInput]:
    start = date.fromisoformat(start_date)
    end = date.fromisoformat(end_date)
    events = _extract_vevents(payload)
    results: list[EconomicCalendarEventInput] = []
    for vevent in events:
        summary = _vevent_field(vevent, "SUMMARY")
        if summary is None:
            continue
        event_key = _match_bls_summary(summary)
        if event_key is None:
            continue
        dtstart = _vevent_field(vevent, "DTSTART")
        if dtstart is None:
            raise OfficialCalendarParseError("malformed_source_payload")
        et_dt = _parse_bls_dtstart(dtstart, vevent)
        if et_dt is None:
            raise OfficialCalendarParseError("malformed_source_payload")
        release_date_val = et_dt.date()
        if not (start <= release_date_val <= end):
            continue
        release_time_str = f"{et_dt.hour:02d}:{et_dt.minute:02d}"
        results.append(
            EconomicCalendarEventInput(
                event_key=event_key,
                release_date=release_date_val.isoformat(),
                release_time_et=release_time_str,
                source_url=_BLS_SOURCE_URL,
                ingested_at=ingested_at,
            )
        )
    seen: set[tuple[str, str, str]] = set()
    deduped: list[EconomicCalendarEventInput] = []
    for item in results:
        key = (item.event_key, item.release_date, item.release_time_et)
        if key not in seen:
            seen.add(key)
            deduped.append(item)
    results = deduped
    found_keys = {item.event_key for item in results}
    for required_key in _BLS_EVENT_MAP.values():
        if required_key not in found_keys:
            raise OfficialCalendarParseError("missing_required_event_key")
    return results


def parse_bea_release_dates_json(
    payload: str,
    start_date: str,
    end_date: str,
    ingested_at: str,
) -> list[EconomicCalendarEventInput]:
    start = date.fromisoformat(start_date)
    end = date.fromisoformat(end_date)
    try:
        data = json.loads(payload)
    except (json.JSONDecodeError, ValueError):
        raise OfficialCalendarParseError("malformed_source_payload")
    if not isinstance(data, dict):
        raise OfficialCalendarParseError("malformed_source_payload")
    results: list[EconomicCalendarEventInput] = []
    for bea_name, event_key in _BEA_EVENT_MAP.items():
        if bea_name not in data:
            raise OfficialCalendarParseError("missing_required_event_key")
        entry = data[bea_name]
        if not isinstance(entry, dict):
            raise OfficialCalendarParseError("malformed_source_payload")
        release_dates_raw = entry.get("release_dates")
        if not isinstance(release_dates_raw, list):
            raise OfficialCalendarParseError("malformed_source_payload")
        seen_dates: set[tuple[str, str]] = set()
        for raw_ts in release_dates_raw:
            if not isinstance(raw_ts, str):
                raise OfficialCalendarParseError("malformed_source_payload")
            et_dt = _parse_bea_timestamp(raw_ts)
            release_date_val = et_dt.date()
            if not (start <= release_date_val <= end):
                continue
            release_time_str = f"{et_dt.hour:02d}:{et_dt.minute:02d}"
            dedup_key = (release_date_val.isoformat(), release_time_str)
            if dedup_key in seen_dates:
                continue
            seen_dates.add(dedup_key)
            results.append(
                EconomicCalendarEventInput(
                    event_key=event_key,
                    release_date=release_date_val.isoformat(),
                    release_time_et=release_time_str,
                    source_url=_BEA_SOURCE_URL,
                    ingested_at=ingested_at,
                )
            )
        has_in_range = any(item.event_key == event_key for item in results)
        if not has_in_range:
            raise OfficialCalendarParseError("missing_required_event_key")
    return results


def _extract_vevents(ics_text: str) -> list[str]:
    unfolded = re.sub(r"\r?\n[ \t]", "", ics_text)
    events: list[str] = []
    in_event = False
    current: list[str] = []
    for line in unfolded.split("\n"):
        stripped = line.rstrip("\r")
        if stripped == "BEGIN:VEVENT":
            in_event = True
            current = []
        elif stripped == "END:VEVENT":
            if in_event:
                events.append("\n".join(current))
            in_event = False
        elif in_event:
            current.append(stripped)
    return events


def _vevent_field(vevent: str, field: str) -> str | None:
    for line in vevent.split("\n"):
        if line.startswith(field + ":") or line.startswith(field + ";"):
            _, _, value = line.partition(":")
            return value.strip()
    return None


def _match_bls_summary(summary: str) -> str | None:
    normalized = summary.strip().lower()
    for pattern, event_key in _BLS_EVENT_MAP.items():
        if pattern in normalized:
            return event_key
    return None


def _parse_bls_dtstart(dtstart_value: str, vevent: str) -> datetime | None:
    for line in vevent.split("\n"):
        if line.startswith("DTSTART;") or line.startswith("DTSTART:"):
            pass
        else:
            continue
        if "TZID=" in line:
            tzid_match = re.search(r"TZID=([^:;]+)", line)
            if tzid_match:
                tzid = tzid_match.group(1)
                try:
                    tz = ZoneInfo(tzid)
                except (KeyError, ValueError):
                    return None
                try:
                    naive = datetime.strptime(dtstart_value, "%Y%m%dT%H%M%S")
                except ValueError:
                    return None
                aware = naive.replace(tzinfo=tz)
                return aware.astimezone(_ET)
    if dtstart_value.endswith("Z"):
        try:
            utc_dt = datetime.strptime(dtstart_value, "%Y%m%dT%H%M%SZ")
        except ValueError:
            return None
        return utc_dt.replace(tzinfo=timezone.utc).astimezone(_ET)
    try:
        naive = datetime.strptime(dtstart_value, "%Y%m%dT%H%M%S")
    except ValueError:
        return None
    return naive.replace(tzinfo=_ET)


def _parse_bea_timestamp(raw: str) -> datetime:
    normalized = raw.strip()
    if normalized.endswith("Z"):
        normalized = normalized[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        raise OfficialCalendarParseError("malformed_source_payload")
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise OfficialCalendarParseError("malformed_source_payload")
    return parsed.astimezone(_ET)


__all__ = [
    "OfficialCalendarParseError",
    "parse_bea_release_dates_json",
    "parse_bls_calendar_ics",
]
