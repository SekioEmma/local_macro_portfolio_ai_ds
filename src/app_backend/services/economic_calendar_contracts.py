from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
from enum import StrEnum
import ipaddress
import re
from urllib.parse import SplitResult, urlsplit, urlunsplit


class EconomicCalendarAdmissionError(ValueError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class EconomicCalendarEventKey(StrEnum):
    CONSUMER_PRICE_INDEX = "consumer_price_index"
    EMPLOYMENT_SITUATION = "employment_situation"
    PERSONAL_INCOME_AND_OUTLAYS = "personal_income_and_outlays"
    GROSS_DOMESTIC_PRODUCT = "gross_domestic_product"
    FOMC_STATEMENT = "fomc_statement"


@dataclass(frozen=True)
class EconomicCalendarEventMetadata:
    event_key: EconomicCalendarEventKey
    event_name: str
    source: str
    source_domain: str


@dataclass(frozen=True)
class EconomicCalendarEventInput:
    event_key: str
    release_date: str
    release_time_et: str
    source_url: str
    ingested_at: str


@dataclass(frozen=True)
class AdmittedEconomicCalendarEvent:
    event_key: EconomicCalendarEventKey
    event_name: str
    source: str
    release_date: str
    release_time_et: str
    source_url: str
    source_domain: str
    ingested_at: str


_CATALOG: dict[EconomicCalendarEventKey, EconomicCalendarEventMetadata] = {
    EconomicCalendarEventKey.CONSUMER_PRICE_INDEX: EconomicCalendarEventMetadata(
        event_key=EconomicCalendarEventKey.CONSUMER_PRICE_INDEX,
        event_name="Consumer Price Index",
        source="BLS",
        source_domain="bls.gov",
    ),
    EconomicCalendarEventKey.EMPLOYMENT_SITUATION: EconomicCalendarEventMetadata(
        event_key=EconomicCalendarEventKey.EMPLOYMENT_SITUATION,
        event_name="Employment Situation",
        source="BLS",
        source_domain="bls.gov",
    ),
    EconomicCalendarEventKey.PERSONAL_INCOME_AND_OUTLAYS: EconomicCalendarEventMetadata(
        event_key=EconomicCalendarEventKey.PERSONAL_INCOME_AND_OUTLAYS,
        event_name="Personal Income and Outlays",
        source="BEA",
        source_domain="bea.gov",
    ),
    EconomicCalendarEventKey.GROSS_DOMESTIC_PRODUCT: EconomicCalendarEventMetadata(
        event_key=EconomicCalendarEventKey.GROSS_DOMESTIC_PRODUCT,
        event_name="Gross Domestic Product",
        source="BEA",
        source_domain="bea.gov",
    ),
    EconomicCalendarEventKey.FOMC_STATEMENT: EconomicCalendarEventMetadata(
        event_key=EconomicCalendarEventKey.FOMC_STATEMENT,
        event_name="FOMC Statement",
        source="Federal Reserve",
        source_domain="federalreserve.gov",
    ),
}
_TIME_RE = re.compile(r"^\d{2}:\d{2}$")


def resolve_calendar_event_key(event_key: str) -> EconomicCalendarEventMetadata:
    try:
        key = EconomicCalendarEventKey(event_key)
    except ValueError as exc:
        raise EconomicCalendarAdmissionError("unsupported_event_key") from exc
    return _CATALOG[key]


def canonicalize_calendar_source_url(
    source_url: str,
    source: str,
) -> tuple[str, str]:
    expected_domain = _source_domain(source)
    parsed = _parse_url(source_url)
    hostname = _validated_hostname(parsed)
    if not _domain_matches(hostname, expected_domain):
        raise EconomicCalendarAdmissionError("source_mismatch")
    path = parsed.path or ""
    if any(part == ".." for part in path.split("/")):
        raise EconomicCalendarAdmissionError("invalid_source_url")
    return urlunsplit(("https", hostname, path, "", "")), hostname


def admit_calendar_event(event: EconomicCalendarEventInput) -> AdmittedEconomicCalendarEvent:
    metadata = resolve_calendar_event_key(event.event_key)
    source_url, source_domain = canonicalize_calendar_source_url(
        event.source_url,
        metadata.source,
    )
    return AdmittedEconomicCalendarEvent(
        event_key=metadata.event_key,
        event_name=metadata.event_name,
        source=metadata.source,
        release_date=_validated_release_date(event.release_date),
        release_time_et=_validated_release_time(event.release_time_et),
        source_url=source_url,
        source_domain=source_domain,
        ingested_at=_validated_ingested_at(event.ingested_at),
    )


def _source_domain(source: str) -> str:
    if source == "BLS":
        return "bls.gov"
    if source == "BEA":
        return "bea.gov"
    if source == "Federal Reserve":
        return "federalreserve.gov"
    raise EconomicCalendarAdmissionError("source_mismatch")


def _parse_url(source_url: str) -> SplitResult:
    try:
        parsed = urlsplit(source_url)
        _ = parsed.port
    except ValueError as exc:
        raise EconomicCalendarAdmissionError("invalid_source_url") from exc
    if parsed.scheme.lower() != "https":
        raise EconomicCalendarAdmissionError("invalid_source_url")
    if parsed.username is not None or parsed.password is not None:
        raise EconomicCalendarAdmissionError("invalid_source_url")
    if parsed.port is not None:
        raise EconomicCalendarAdmissionError("invalid_source_url")
    if parsed.query or parsed.fragment:
        raise EconomicCalendarAdmissionError("invalid_source_url")
    return parsed


def _validated_hostname(parsed: SplitResult) -> str:
    hostname = (parsed.hostname or "").strip().lower().rstrip(".")
    if not hostname:
        raise EconomicCalendarAdmissionError("invalid_source_url")
    if hostname == "localhost" or hostname.endswith(".localhost"):
        raise EconomicCalendarAdmissionError("invalid_source_url")
    try:
        ipaddress.ip_address(hostname)
    except ValueError:
        return hostname
    raise EconomicCalendarAdmissionError("invalid_source_url")


def _domain_matches(hostname: str, expected_domain: str) -> bool:
    return hostname == expected_domain or hostname.endswith("." + expected_domain)


def _validated_release_date(value: str) -> str:
    try:
        parsed = date.fromisoformat(value)
    except ValueError as exc:
        raise EconomicCalendarAdmissionError("invalid_release_date") from exc
    return parsed.isoformat()


def _validated_release_time(value: str) -> str:
    if not _TIME_RE.match(value):
        raise EconomicCalendarAdmissionError("invalid_release_time_et")
    hour_text, minute_text = value.split(":")
    hour = int(hour_text)
    minute = int(minute_text)
    if not 0 <= hour <= 23 or not 0 <= minute <= 59:
        raise EconomicCalendarAdmissionError("invalid_release_time_et")
    return value


def _validated_ingested_at(value: str) -> str:
    normalized = value.strip()
    if normalized.endswith("Z"):
        normalized = normalized[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise EconomicCalendarAdmissionError("invalid_ingested_at") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise EconomicCalendarAdmissionError("invalid_ingested_at")
    return parsed.astimezone(timezone.utc).isoformat()


__all__ = [
    "AdmittedEconomicCalendarEvent",
    "EconomicCalendarAdmissionError",
    "EconomicCalendarEventInput",
    "EconomicCalendarEventKey",
    "admit_calendar_event",
    "canonicalize_calendar_source_url",
    "resolve_calendar_event_key",
]
