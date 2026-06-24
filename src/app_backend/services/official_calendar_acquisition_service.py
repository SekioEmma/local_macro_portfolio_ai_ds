from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Callable, Protocol
from zoneinfo import ZoneInfo

from app_backend.services.economic_calendar_contracts import (
    EconomicCalendarEventInput,
)
from app_backend.services.economic_calendar_service import (
    EconomicCalendarMutationResult,
    EconomicCalendarService,
)
from app_backend.services.official_calendar_parsers import (
    OfficialCalendarParseError,
    parse_bea_release_dates_json,
    parse_bls_calendar_ics,
)

_ET = ZoneInfo("America/New_York")
_ALLOWED_SOURCES = frozenset(("bls", "bea"))
_MAX_WINDOW_DAYS = 366
_UNAVAILABLE_EVENT_KEYS = ("fomc_statement",)
_MAX_PAYLOAD_BYTES = 1_048_576  # 1 MiB

_EXPECTED_CONTENT_TYPES: dict[str, str] = {
    "bls": "text/calendar",
    "bea": "application/json",
}


class _TransportProtocol(Protocol):
    def fetch(self, source: object) -> object: ...


@dataclass(frozen=True)
class OfficialCalendarAcquisitionSummary:
    status: str
    live: bool
    write: bool
    selected_sources: tuple[str, ...]
    start_date: str
    end_date: str
    event_count: int = 0
    event_key_counts: dict[str, int] = field(default_factory=dict)
    created_count: int = 0
    updated_count: int = 0
    unavailable_event_keys: tuple[str, ...] = _UNAVAILABLE_EVENT_KEYS
    error_codes: list[str] = field(default_factory=list)


NowProvider = Callable[[], datetime]


class OfficialCalendarAcquisitionService:
    def __init__(
        self,
        transport_factory: Callable[[], _TransportProtocol],
        calendar_service: EconomicCalendarService,
        now_provider: NowProvider | None = None,
    ) -> None:
        self._transport_factory = transport_factory
        self._calendar_service = calendar_service
        self._now_provider = now_provider or _default_now_et

    def run(
        self,
        *,
        source_keys: tuple[str, ...],
        start_date: str | None = None,
        end_date: str | None = None,
        live: bool = False,
        write: bool = False,
    ) -> OfficialCalendarAcquisitionSummary:
        validated_sources = self._validate_sources(source_keys)
        resolved_start, resolved_end = self._resolve_date_window(start_date, end_date)

        if write and not live:
            return OfficialCalendarAcquisitionSummary(
                status="blocked",
                live=live,
                write=write,
                selected_sources=validated_sources,
                start_date=resolved_start,
                end_date=resolved_end,
                error_codes=["write_requires_live"],
            )

        if not live:
            return OfficialCalendarAcquisitionSummary(
                status="planned",
                live=live,
                write=write,
                selected_sources=validated_sources,
                start_date=resolved_start,
                end_date=resolved_end,
                error_codes=["live_disabled"],
            )

        transport = self._transport_factory()
        ingested_at = datetime.now(ZoneInfo("UTC")).isoformat()
        all_events: list[EconomicCalendarEventInput] = []
        error_codes: list[str] = []

        for source_key in validated_sources:
            try:
                raw_payload = transport.fetch(_source_enum(source_key))
            except Exception:
                error_codes.append("fetch_failed")
                break
            body = _validate_transport_payload(raw_payload, source_key)
            if body is None:
                error_codes.append("invalid_response")
                break
            try:
                if source_key == "bls":
                    events = parse_bls_calendar_ics(
                        body,
                        resolved_start,
                        resolved_end,
                        ingested_at,
                    )
                else:
                    events = parse_bea_release_dates_json(
                        body,
                        resolved_start,
                        resolved_end,
                        ingested_at,
                    )
            except OfficialCalendarParseError as exc:
                error_codes.append(exc.code)
                break
            except Exception:
                error_codes.append("invalid_response")
                break
            all_events.extend(events)
        else:
            pass

        if error_codes:
            return OfficialCalendarAcquisitionSummary(
                status="blocked",
                live=live,
                write=write,
                selected_sources=validated_sources,
                start_date=resolved_start,
                end_date=resolved_end,
                error_codes=error_codes,
            )

        key_counts = _event_key_counts(all_events)

        if not write:
            return OfficialCalendarAcquisitionSummary(
                status="dry_run",
                live=live,
                write=write,
                selected_sources=validated_sources,
                start_date=resolved_start,
                end_date=resolved_end,
                event_count=len(all_events),
                event_key_counts=key_counts,
            )

        try:
            mutation = self._calendar_service.upsert_events(all_events)
        except Exception:
            return OfficialCalendarAcquisitionSummary(
                status="blocked",
                live=live,
                write=write,
                selected_sources=validated_sources,
                start_date=resolved_start,
                end_date=resolved_end,
                error_codes=["write_failed"],
            )

        if not _validate_mutation_result(mutation, len(all_events)):
            return OfficialCalendarAcquisitionSummary(
                status="blocked",
                live=live,
                write=write,
                selected_sources=validated_sources,
                start_date=resolved_start,
                end_date=resolved_end,
                error_codes=["write_failed"],
            )

        return OfficialCalendarAcquisitionSummary(
            status="ok",
            live=live,
            write=write,
            selected_sources=validated_sources,
            start_date=resolved_start,
            end_date=resolved_end,
            event_count=mutation.event_count,
            event_key_counts=key_counts,
            created_count=mutation.created_count,
            updated_count=mutation.updated_count,
        )

    def _validate_sources(self, source_keys: tuple[str, ...]) -> tuple[str, ...]:
        if not source_keys:
            raise ValueError("empty_source_keys")
        seen: set[str] = set()
        for key in source_keys:
            if key not in _ALLOWED_SOURCES:
                raise ValueError("unknown_source_key")
            if key in seen:
                raise ValueError("duplicate_source_key")
            seen.add(key)
        return source_keys

    def _resolve_date_window(
        self,
        start_date: str | None,
        end_date: str | None,
    ) -> tuple[str, str]:
        now_et = _coerce_et(self._now_provider())
        today = now_et.date()
        if start_date is not None:
            try:
                start = date.fromisoformat(start_date)
            except ValueError:
                raise ValueError("invalid_date_range")
        else:
            start = today
        if end_date is not None:
            try:
                end = date.fromisoformat(end_date)
            except ValueError:
                raise ValueError("invalid_date_range")
        else:
            end = start + timedelta(days=365)
        if end < start:
            raise ValueError("invalid_date_range")
        if (end - start).days > _MAX_WINDOW_DAYS:
            raise ValueError("invalid_date_range")
        if start < today:
            raise ValueError("invalid_date_range")
        return start.isoformat(), end.isoformat()


def build_default_official_calendar_acquisition_service() -> OfficialCalendarAcquisitionService:
    from data_providers.official_calendar_real_transport import (
        OfficialCalendarRealTransport,
    )

    return OfficialCalendarAcquisitionService(
        transport_factory=OfficialCalendarRealTransport,
        calendar_service=EconomicCalendarService(),
    )


def _validate_transport_payload(payload: object, expected_source: str) -> str | None:
    """Return body string if payload passes all boundary checks, None otherwise. Never raises."""
    if payload is None:
        return None
    try:
        raw_source = payload.source  # type: ignore[union-attr]
        content_type = payload.content_type  # type: ignore[union-attr]
        body = payload.body  # type: ignore[union-attr]
    except AttributeError:
        return None
    # Normalise source: accept enum (.value) or plain string
    source_str = raw_source.value if hasattr(raw_source, "value") else raw_source
    if not isinstance(source_str, str) or source_str != expected_source:
        return None
    # Validate content type: strip MIME params, lowercase exact match
    if not isinstance(content_type, str):
        return None
    ct_base = content_type.split(";")[0].strip().lower()
    if ct_base != _EXPECTED_CONTENT_TYPES.get(expected_source):
        return None
    # Validate body
    if not isinstance(body, str):
        return None
    if "\x00" in body:
        return None
    try:
        encoded = body.encode("utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return None
    if len(encoded) > _MAX_PAYLOAD_BYTES:
        return None
    return body


def _validate_mutation_result(result: object, expected_count: int) -> bool:
    """Return True only when result is a fully-valid EconomicCalendarMutationResult."""
    if not isinstance(result, EconomicCalendarMutationResult):
        return False
    if result.status != "ok":
        return False
    for attr in ("event_count", "created_count", "updated_count"):
        val = getattr(result, attr)
        if isinstance(val, bool):
            return False
        if not isinstance(val, int):
            return False
        if val < 0:
            return False
    if result.event_count != expected_count:
        return False
    if result.created_count + result.updated_count != result.event_count:
        return False
    return True


def _event_key_counts(events: list[EconomicCalendarEventInput]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for event in events:
        counts[event.event_key] = counts.get(event.event_key, 0) + 1
    return counts


def _source_enum(key: str) -> object:
    from data_providers.official_calendar_real_transport import (
        OfficialCalendarSource,
    )

    return OfficialCalendarSource(key)


def _coerce_et(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=_ET)
    return value.astimezone(_ET)


def _default_now_et() -> datetime:
    return datetime.now(_ET)


__all__ = [
    "OfficialCalendarAcquisitionService",
    "OfficialCalendarAcquisitionSummary",
    "build_default_official_calendar_acquisition_service",
]
