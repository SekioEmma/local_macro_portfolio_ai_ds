"""Stage 9.3-A internal builder from AI Context Manifest to ExternalAIRequest.

This module defines the ONLY safe path from sanitized manifest material to a
guard-checked `ExternalAIRequest`. Stage 9.3-A does not wire it to any HTTP
route. Stage 9.3-B (real DeepSeek) must reuse this builder so that future
integration cannot accidentally bypass the manifest, the guards, or the
boundary contract.

Boundary policy:
- Inputs are only sanitized manifest summaries, counts, boundary notices, and
  an optional caller-provided ``user_intent_summary``.
- Raw user question / raw prompt / holdings / account values / position
  weights / transaction history / raw provider payloads / API keys / env
  files / file paths are NOT accepted by this builder. The argument name
  ``user_intent_summary`` is deliberately not ``question``.
- Default mode is ``"fake"``. Network mode is rejected outright.
- The builder runs ``guard_request`` and raises ``BlockedAdapterError`` on
  any finding; callers cannot get an unchecked request from this module.
"""
from __future__ import annotations

import uuid
from typing import Any

from app_backend.schemas.ai_external import (
    AdapterMode,
    AdapterProvider,
    ExternalAIRequest,
)
from app_backend.schemas.responses import AIContextManifestResponse
from app_backend.services.ai_external_adapter import (
    BlockedAdapterError,
    guard_request,
)


DEFAULT_USER_INTENT_SUMMARY = (
    "Local fake-adapter request derived from AI Context Manifest preview; "
    "no raw user question is forwarded."
)


def build_external_ai_request_from_manifest(
    manifest: AIContextManifestResponse | dict[str, Any],
    *,
    provider: AdapterProvider = "deepseek",
    mode: AdapterMode = "fake",
    user_intent_summary: str | None = None,
    memo_type: str | None = None,
    preview_type: str | None = None,
    request_id: str | None = None,
) -> ExternalAIRequest:
    """Build a guarded ExternalAIRequest from a sanitized manifest.

    Stage 9.3-A: ``mode="network"`` is rejected before construction. Any
    forbidden token surfacing in the derived summaries triggers the guard.
    The caller never gets an unchecked request.
    """
    if mode == "network":
        raise BlockedAdapterError(
            ["builder_mode_network_blocked_in_stage_9_3_a"]
        )

    data = _manifest_to_dict(manifest)
    included_facts = _items(data, "included_facts")
    excluded_facts = _items(data, "excluded_facts")
    included_models = _items(data, "included_model_outputs")
    excluded_models = _items(data, "excluded_model_outputs")
    boundary_notices = _boundary_notices(data)

    request = ExternalAIRequest(
        request_id=request_id or f"local-fake-{uuid.uuid4().hex[:12]}",
        provider=provider,
        mode=mode,
        user_intent_summary=user_intent_summary or DEFAULT_USER_INTENT_SUMMARY,
        context_preview_summary=_context_preview_summary(
            included_facts, included_models
        ),
        included_fact_count=len(included_facts),
        included_model_output_count=len(included_models),
        excluded_context_summary=_excluded_context_summary(
            excluded_facts, excluded_models
        ),
        boundary_notices=boundary_notices,
        memo_type=memo_type,
        preview_type=preview_type,
        validator_required=True,
    )

    guard = guard_request(request)
    if not guard.passed:
        raise BlockedAdapterError(guard.findings)
    return request


# ---------------------------------------------------------------------------
# Helpers (manifest-only; no raw prompt, no holdings, no file I/O)
# ---------------------------------------------------------------------------


def _manifest_to_dict(
    manifest: AIContextManifestResponse | dict[str, Any]
) -> dict[str, Any]:
    if hasattr(manifest, "model_dump"):
        return manifest.model_dump()
    if hasattr(manifest, "dict"):
        return manifest.dict()
    if isinstance(manifest, dict):
        return dict(manifest)
    raise TypeError("manifest must be a Pydantic model or dict")


def _items(data: dict[str, Any], key: str) -> list[dict[str, Any]]:
    raw = data.get(key) or []
    return [item for item in raw if isinstance(item, dict)]


def _context_preview_summary(
    facts: list[dict[str, Any]],
    models: list[dict[str, Any]],
) -> str:
    fact_count = len(facts)
    model_count = len(models)
    return (
        f"Manifest preview summary: included_facts={fact_count}, "
        f"included_model_outputs={model_count}. "
        "Only sanitized manifest material is forwarded."
    )


def _excluded_context_summary(
    excluded_facts: list[dict[str, Any]],
    excluded_models: list[dict[str, Any]],
) -> str:
    if not excluded_facts and not excluded_models:
        return "No excluded context."
    return (
        f"Excluded context: facts={len(excluded_facts)}, "
        f"model_outputs={len(excluded_models)}. Excluded rows remain "
        "constraints only."
    )


def _boundary_notices(data: dict[str, Any]) -> list[str]:
    raw = data.get("risk_boundaries") or data.get("boundary_notices") or []
    notices = [str(item) for item in raw if isinstance(item, str) and item.strip()]
    if not notices:
        notices = [
            "Reference evidence only.",
            "Not an action directive.",
            "Human review is required.",
        ]
    return notices


__all__ = [
    "DEFAULT_USER_INTENT_SUMMARY",
    "build_external_ai_request_from_manifest",
]
