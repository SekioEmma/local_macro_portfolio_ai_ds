from __future__ import annotations

from typing import Literal, Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field

from app_backend.services.tavily_provider_contract import TavilyProviderPayload


TransportErrorKind = Literal[
    "timeout",
    "http_error",
    "malformed",
    "missing_key",
    "provider_refusal",
]


class TavilyTransportResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    url: str
    title: str
    snippet: str


class TavilyTransportRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    query: str
    max_results: int
    include_domains: list[str] = Field(default_factory=list)


class TavilyTransportResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    results: list[TavilyTransportResult] = Field(default_factory=list)


class TavilyTransportError(RuntimeError):
    def __init__(self, kind: TransportErrorKind, detail: str = "") -> None:
        self.kind = kind
        self.detail = ""
        super().__init__(kind)


@runtime_checkable
class TavilyTransport(Protocol):
    def send(
        self,
        request: TavilyTransportRequest,
    ) -> TavilyTransportResponse:
        ...


def build_transport_request_from_provider_payload(
    payload: TavilyProviderPayload,
) -> TavilyTransportRequest:
    return TavilyTransportRequest(
        query=payload.query,
        max_results=payload.max_results,
        include_domains=list(payload.include_domains),
    )


__all__ = [
    "TavilyTransport",
    "TavilyTransportError",
    "TavilyTransportRequest",
    "TavilyTransportResponse",
    "TavilyTransportResult",
    "TransportErrorKind",
    "build_transport_request_from_provider_payload",
]
