from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
import httpx


class OfficialCalendarSource(StrEnum):
    BLS = "bls"
    BEA = "bea"


class OfficialCalendarTransportError(Exception):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass(frozen=True)
class FetchedOfficialCalendarPayload:
    source: OfficialCalendarSource
    body: str
    content_type: str


_FIXED_URLS: dict[OfficialCalendarSource, str] = {
    OfficialCalendarSource.BLS: "https://www.bls.gov/schedule/news_release/bls.ics",
    OfficialCalendarSource.BEA: "https://apps.bea.gov/API/signup/release_dates.json",
}

_EXPECTED_CONTENT_TYPES: dict[OfficialCalendarSource, str] = {
    OfficialCalendarSource.BLS: "text/calendar",
    OfficialCalendarSource.BEA: "application/json",
}

_MAX_BODY_BYTES = 1_048_576
_TIMEOUT_SECONDS = 15


class OfficialCalendarRealTransport:

    def fetch(self, source: OfficialCalendarSource) -> FetchedOfficialCalendarPayload:
        if source not in _FIXED_URLS:
            raise OfficialCalendarTransportError("unsupported_source")
        url = _FIXED_URLS[source]
        expected_ct = _EXPECTED_CONTENT_TYPES[source]
        try:
            with httpx.Client(
                timeout=_TIMEOUT_SECONDS,
                follow_redirects=False,
            ) as client:
                with client.stream("GET", url) as response:
                    if response.status_code != 200:
                        raise OfficialCalendarTransportError("fetch_failed")
                    ct = response.headers.get("content-type", "")
                    if expected_ct not in ct:
                        raise OfficialCalendarTransportError("invalid_response")
                    chunks: list[bytes] = []
                    total = 0
                    for chunk in response.iter_bytes(chunk_size=8192):
                        total += len(chunk)
                        if total > _MAX_BODY_BYTES:
                            raise OfficialCalendarTransportError("response_too_large")
                        chunks.append(chunk)
            raw = b"".join(chunks)
            try:
                body = raw.decode("utf-8")
            except UnicodeDecodeError:
                raise OfficialCalendarTransportError("invalid_response")
        except OfficialCalendarTransportError:
            raise
        except Exception:
            raise OfficialCalendarTransportError("fetch_failed")
        return FetchedOfficialCalendarPayload(
            source=source,
            body=body,
            content_type=expected_ct,
        )


def get_fixed_url(source: OfficialCalendarSource) -> str:
    return _FIXED_URLS[source]


__all__ = [
    "FetchedOfficialCalendarPayload",
    "OfficialCalendarRealTransport",
    "OfficialCalendarSource",
    "OfficialCalendarTransportError",
    "get_fixed_url",
]
