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
            try:
                body = _validate_transport_payload(raw_payload, source_key)
            except Exception:
                body = None
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

        try:
            counts = _validate_mutation_counts(mutation, len(all_events))
        except Exception:
            counts = None
        if counts is None:
            return OfficialCalendarAcquisitionSummary(
                status="blocked",
                live=live,
                write=write,
                selected_sources=validated_sources,
                start_date=resolved_start,
                end_date=resolved_end,
                error_codes=["write_failed"],
            )

        event_count, created_count, updated_count = counts
        return OfficialCalendarAcquisitionSummary(
            status="ok",
            live=live,
            write=write,
            selected_sources=validated_sources,
            start_date=resolved_start,
            end_date=resolved_end,
            event_count=event_count,
            event_key_counts=key_counts,
            created_count=created_count,
            updated_count=updated_count,
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
    """Return body string if payload passes all boundary checks, None otherwise.

    Exception-total: any failure raised while reading attributes, normalising the
    source, inspecting MIME parts, or encoding the body is swallowed and treated
    as an invalid payload. Never raises ``Exception``. System-level exits propagate.
    """
    if payload is None:
        return None
    try:
        raw_source = payload.source  # type: ignore[union-attr]
        content_type = payload.content_type  # type: ignore[union-attr]
        body = payload.body  # type: ignore[union-attr]

        # Normalise source: accept enum (.value) or plain built-in str.
        source_str = raw_source.value if hasattr(raw_source, "value") else raw_source
        if type(source_str) is not str:
            return None
        if source_str != expected_source:
            return None

        # Validate content type: must be exact built-in str so .split / .strip /
        # .lower cannot be overridden by a subclass.
        if type(content_type) is not str:
            return None
        ct_base = content_type.split(";")[0].strip().lower()
        if ct_base != _EXPECTED_CONTENT_TYPES.get(expected_source):
            return None

        # Validate body: must be exact built-in str so .encode cannot be
        # overridden by a subclass.
        if type(body) is not str:
            return None
        if "\x00" in body:
            return None
        encoded = body.encode("utf-8")
        if len(encoded) > _MAX_PAYLOAD_BYTES:
            return None
        return body
    except Exception:
        return None


def _validate_mutation_counts(
    result: object,
    expected_count: int,
) -> tuple[int, int, int] | None:
    """Return ``(event_count, created_count, updated_count)`` on success.

    Exception-total: any failure raised while reading attributes from a
    malicious or broken result object is swallowed and treated as a write
    failure. Returns ``None`` for any validation failure. Never raises
    ``Exception``. System-level exits propagate.

    Only an exact ``EconomicCalendarMutationResult`` instance is accepted —
    subclasses that could override attribute access are rejected.
    """
    if type(result) is not EconomicCalendarMutationResult:
        return None
    try:
        status = result.status  # type: ignore[union-attr]
        event_count = result.event_count  # type: ignore[union-attr]
        created_count = result.created_count  # type: ignore[union-attr]
        updated_count = result.updated_count  # type: ignore[union-attr]

        if status != "ok":
            return None
        for val in (event_count, created_count, updated_count):
            if type(val) is bool:
                return None
            if type(val) is not int:
                return None
            if val < 0:
                return None
        if event_count != expected_count:
            return None
        if created_count + updated_count != event_count:
            return None
        return (event_count, created_count, updated_count)
    except Exception:
        return None


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
