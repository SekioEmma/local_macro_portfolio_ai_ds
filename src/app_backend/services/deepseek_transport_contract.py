"""Stage 9.3-B-2 DeepSeek transport contract.

This module defines the abstract transport interface and a deterministic
mock implementation. Real transport code lives in
``deepseek_real_transport.py`` and must implement the Protocol here without
expanding its surface beyond ``DeepSeekTransportRequest`` /
``DeepSeekTransportResponse``.

Boundary policy:

- This contract module does NOT import network client libraries. There is no
  real HTTP client anywhere here.
- It does NOT read environment variables, files, sockets, or the network.
  The adapter is allowed to fail closed by deciding it has no injected
  transport; without one, no `send` is ever attempted.
- The transport request and response carry no API key, base URL, endpoint
  path, or model name. Stage 9.3-B-2b applies key / URL / model internally
  but MUST NOT expose them through these schemas.
- A `DeepSeekTransportError` is the ONLY exception subclass a transport is
  allowed to raise. It carries a categorical ``kind`` plus an optional
  sanitized detail string. Never include a raw provider payload, raw prompt,
  or sensitive header.
"""
from __future__ import annotations

from typing import Literal, Protocol, runtime_checkable

from app_backend.schemas.ai_external import (
    DeepSeekProviderPayload,
    DeepSeekTransportRequest,
    DeepSeekTransportResponse,
)


TransportErrorKind = Literal[
    "timeout",
    "http_error",
    "malformed",
    "missing_key",
    "provider_refusal",
]


class DeepSeekTransportError(RuntimeError):
    """Categorical, sanitized transport-layer error.

    Carries only a kind and a short sanitized detail string. Stage 9.3-B
    adapter code is expected to convert this into a fail-closed
    `BlockedAdapterError`; do not surface the raw detail to users.
    """

    def __init__(self, kind: TransportErrorKind, detail: str = "") -> None:
        super().__init__(f"{kind}: {detail}" if detail else kind)
        self.kind = kind
        self.detail = detail


@runtime_checkable
class DeepSeekTransport(Protocol):
    """Stage 9.3-B transport Protocol.

    Implementations MUST take a `DeepSeekTransportRequest` and return a
    `DeepSeekTransportResponse`. Failure modes MUST be expressed via
    `DeepSeekTransportError`; any other exception leaking out of `send`
    is a bug and the adapter will fail closed regardless.
    """

    def send(self, request: DeepSeekTransportRequest) -> DeepSeekTransportResponse:
        ...


def build_transport_request_from_provider_payload(
    payload: DeepSeekProviderPayload,
) -> DeepSeekTransportRequest:
    """Derive a transport request from the sanitized provider payload.

    Pure conversion. No new content is invented; nothing forbidden by the
    payload schema can be smuggled in here.
    """
    return DeepSeekTransportRequest(
        request_id=payload.request_id,
        provider=payload.provider,
        mode=payload.mode,
        messages=list(payload.messages),
        boundary_notices=list(payload.boundary_notices),
        validator_required=payload.validator_required,
    )


class MockDeepSeekTransport:
    """Deterministic mock transport.

    Stage 9.3-B-2a uses this transport in tests and in any local-only
    sanity-check path. It returns a deterministic sanitized response
    derived from the request. ``external_model_called`` is the responsibility
    of the adapter; this transport's responses carry no API-key material,
    no raw provider envelope, and no boundary-violating text.

    The mock can be configured to raise `DeepSeekTransportError` with a
    given kind, used by tests to exercise fail-closed paths without ever
    touching the network.
    """

    def __init__(
        self,
        *,
        forced_error_kind: TransportErrorKind | None = None,
        forced_error_detail: str = "",
        content_text: str | None = None,
    ) -> None:
        self._forced_error_kind = forced_error_kind
        self._forced_error_detail = forced_error_detail
        self._content_text = content_text

    def send(self, request: DeepSeekTransportRequest) -> DeepSeekTransportResponse:
        if self._forced_error_kind is not None:
            raise DeepSeekTransportError(
                kind=self._forced_error_kind,
                detail=self._forced_error_detail,
            )
        text = self._content_text
        if text is None:
            text = (
                "Mocked transport reply. Local fake adapter response only. "
                "Not an action directive. Human review is required."
            )
        return DeepSeekTransportResponse(
            request_id=request.request_id,
            provider=request.provider,
            mode=request.mode,
            content_text=text,
            finish_reason="stop",
        )


FakeDeepSeekTransport = MockDeepSeekTransport


__all__ = [
    "DeepSeekTransport",
    "DeepSeekTransportError",
    "MockDeepSeekTransport",
    "FakeDeepSeekTransport",
    "TransportErrorKind",
    "build_transport_request_from_provider_payload",
]
