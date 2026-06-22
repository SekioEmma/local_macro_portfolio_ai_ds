"""Stage 9.3-B-1 DeepSeek provider payload contract.

This module defines the ONLY safe path from a guarded ``ExternalAIRequest``
to a sanitized ``DeepSeekProviderPayload``. Stage 9.3-B-1 does NOT
implement a real network adapter, does NOT read API keys, does NOT read
configuration files, and does NOT touch the network. The payload here is
the contract a future Stage 9.3-B-2 real adapter must consume verbatim;
Stage 9.3-B-2 is not allowed to extend the payload with API key, base
URL, endpoint path, or any field not already in the schema.

Boundary policy:

- The payload may carry only sanitized AI Context Manifest-derived
  summaries already validated by ``guard_request``.
- Provider messages are restricted to roles ``system`` / ``context`` /
  ``summary`` so that the future adapter cannot wrap raw user-question
  transcripts as a ``user`` chat message.
- No raw question / raw prompt / holdings / account values / position
  weights / transaction history / raw provider payload / search results /
  local file path / API key / env var name / endpoint string may appear
  in the payload. ``guard_request`` enforces this on the input side;
  ``extra="forbid"`` on the Pydantic models enforces it on the schema
  side.
"""
from __future__ import annotations

from app_backend.schemas.ai_external import (
    DeepSeekProviderMessage,
    DeepSeekProviderPayload,
    ExternalAIRequest,
)
from app_backend.services.ai_external_adapter import (
    BlockedAdapterError,
    guard_request,
)


_SYSTEM_BOUNDARY_PREFIX = (
    "Local-first macro risk research workbench. Sanitized AI Context "
    "Manifest material only. Not an action directive, not a forecast, not "
    "an event-odds model. Human review is required."
)


def build_deepseek_provider_payload(
    request: ExternalAIRequest,
) -> DeepSeekProviderPayload:
    """Construct a sanitized ``DeepSeekProviderPayload`` from an
    ``ExternalAIRequest``.

    Stage 9.3-B-1 contract:

    - ``guard_request`` runs FIRST. Any finding raises
      ``BlockedAdapterError``; no payload is returned.
    - Only the sanitized fields already present on the request are
      forwarded. No new content is invented here; in particular this
      builder does not echo any "user" chat message.
    - The ``messages`` list mirrors the request summaries but with
      restricted roles (``system`` / ``context`` / ``summary``). Stage
      9.3-B-2 may later decide model name and endpoint, but the message
      structure here is the maximum the adapter is allowed to send.
    """
    guard = guard_request(request)
    if not guard.passed:
        raise BlockedAdapterError(guard.findings)

    messages = [
        DeepSeekProviderMessage(role="system", content=_SYSTEM_BOUNDARY_PREFIX),
        DeepSeekProviderMessage(
            role="context",
            content=request.context_preview_summary,
        ),
        DeepSeekProviderMessage(
            role="context",
            content=request.excluded_context_summary,
        ),
        # Keep the user's intent as the final non-system message so a large
        # context package cannot push the actual question out of attention.
        DeepSeekProviderMessage(
            role="summary",
            content=request.user_intent_summary,
        ),
        DeepSeekProviderMessage(
            role="system",
            content="Boundary notices: " + " | ".join(request.boundary_notices),
        ),
    ]

    return DeepSeekProviderPayload(
        request_id=request.request_id,
        provider=request.provider,
        mode=request.mode,
        user_intent_summary=request.user_intent_summary,
        context_preview_summary=request.context_preview_summary,
        included_fact_count=request.included_fact_count,
        included_model_output_count=request.included_model_output_count,
        excluded_context_summary=request.excluded_context_summary,
        boundary_notices=list(request.boundary_notices),
        memo_type=request.memo_type,
        preview_type=request.preview_type,
        validator_required=request.validator_required,
        messages=messages,
    )


__all__ = [
    "build_deepseek_provider_payload",
]
