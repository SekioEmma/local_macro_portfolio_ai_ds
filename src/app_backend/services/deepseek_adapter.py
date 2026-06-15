"""Stage 9.3-A DeepSeek adapter skeleton.

This module ships ONLY a disabled-by-default DeepSeek adapter shell and a
FakeDeepSeekAdapter that returns deterministic local text. There is no
HTTP client import, no environment variable read, no API key handling,
and no network attempt anywhere in this file.

Stage 9.3-B (real DeepSeek) is NOT implemented here. Bringing it in must:
- add an explicit user-controlled switch
- show context preview before send
- run the validator after response
- never persist raw prompts/responses by default
- reuse `ExternalAIRequest` / `ExternalAIResponse` and the guards in
  `ai_external_adapter.py` unchanged

Importing this module must not trigger any network or file I/O.
"""
from __future__ import annotations

from app_backend.schemas.ai_external import (
    DeepSeekTransportResponse,
    ExternalAIAdapterConfig,
    ExternalAIPrivacySummary,
    ExternalAIRequest,
    ExternalAIResponse,
    ExternalAIRuntimePolicy,
)
from app_backend.schemas.ai_memo import AIMemoValidatorResult
from app_backend.services.ai_external_adapter import (
    BlockedAdapterError,
    ExternalAIAdapter,
    guard_external_model_response,
    guard_request,
    guard_response,
    validate_external_ai_response_content,
)
from app_backend.services.ai_external_runtime_policy import (
    assert_external_ai_runtime_policy_allowed,
)
from app_backend.services.deepseek_provider_contract import (
    build_deepseek_provider_payload,
)
from app_backend.services.deepseek_transport_contract import (
    DeepSeekTransport,
    DeepSeekTransportError,
    build_transport_request_from_provider_payload,
)


FAKE_BOUNDARY_NOTICE = (
    "Fake adapter output only; not an action directive, not an "
    "event-odds model, not a return-estimation model, not a position-level "
    "output, and not external-model output."
)


def default_disabled_config() -> ExternalAIAdapterConfig:
    """Stage 9.3-A default: disabled, no network, no persistence."""
    return ExternalAIAdapterConfig(
        provider="deepseek",
        enabled=False,
        mode="disabled",
        allow_network=False,
        requires_user_switch=True,
        requires_context_preview=True,
        requires_validator=True,
        save_raw_prompt=False,
        save_raw_response=False,
    )


def fake_only_config() -> ExternalAIAdapterConfig:
    """Stage 9.3-A test/preview config: fake mode, no network."""
    return ExternalAIAdapterConfig(
        provider="deepseek",
        enabled=True,
        mode="fake",
        allow_network=False,
        requires_user_switch=True,
        requires_context_preview=True,
        requires_validator=True,
        save_raw_prompt=False,
        save_raw_response=False,
    )


class DeepSeekAdapter(ExternalAIAdapter):
    """Disabled-by-default DeepSeek adapter.

    Stage 9.3-A behavior:
    - `mode="disabled"` → `generate()` raises `BlockedAdapterError`
    - `mode="fake"` → returns deterministic local text via `FakeDeepSeekAdapter`
    - `mode="network"` → blocked at config guard, never reaches `generate()`
    """

    def generate(self, request: ExternalAIRequest) -> ExternalAIResponse:
        if self.config.mode == "disabled":
            raise BlockedAdapterError(["adapter_disabled_in_stage_9_3_a"])
        if self.config.mode == "network":
            # Defensive; config guard should have blocked this already.
            raise BlockedAdapterError(["network_mode_not_implemented_in_stage_9_3_a"])
        if self.config.mode != "fake":
            raise BlockedAdapterError([f"unsupported_mode_{self.config.mode}"])

        request_guard = guard_request(request)
        if not request_guard.passed:
            raise BlockedAdapterError(request_guard.findings)

        response = _build_fake_response(self.config, request)
        response_guard = guard_response(response)
        if not response_guard.passed:
            raise BlockedAdapterError(response_guard.findings)
        return response


class FakeDeepSeekAdapter(DeepSeekAdapter):
    """Convenience alias that defaults to fake mode.

    Useful in tests so they do not have to construct a config every time.
    """

    def __init__(self, config: ExternalAIAdapterConfig | None = None) -> None:
        super().__init__(config or fake_only_config())


def _build_fake_response(
    config: ExternalAIAdapterConfig,
    request: ExternalAIRequest,
) -> ExternalAIResponse:
    content = (
        "[fake-deepseek] Local fake adapter response. "
        f"included_facts={request.included_fact_count}, "
        f"included_models={request.included_model_output_count}. "
        f"{FAKE_BOUNDARY_NOTICE}"
    )
    return ExternalAIResponse(
        provider=config.provider,
        mode="fake",
        external_model_called=False,
        fake_response=True,
        content=content,
        validator_result=AIMemoValidatorResult(
            passed=True,
            blocked_terms=[],
            privacy_findings=[],
        ),
        privacy_summary=ExternalAIPrivacySummary(
            uses_ai_context_manifest_only=True,
            uses_holdings_line_items=False,
            uses_raw_provider_payloads=False,
            uses_raw_prompts=False,
            external_model_called=False,
            search_called=False,
            saved_by_default=False,
        ),
        not_saved_by_default=True,
        human_review_required=True,
    )


# ---------------------------------------------------------------------------
# Stage 9.3-B-2a: minimal adapter with injected mocked transport
# ---------------------------------------------------------------------------
#
# Stage 9.3-B-2a wires together the full safety chain end-to-end while still
# using a mocked transport: NO real HTTP, NO API key read, NO env read, NO
# new HTTP route. The `external_model_called` flag remains `False` because
# the transport is a mock. `guard_response` still blocks `external_model_called=True`
# and Stage 9.3-B-2a deliberately does not weaken that guard. The Stage
# 9.3-B-2b task is the one that may revisit that guard policy and introduce
# a real network transport behind a separate explicit approval.


def mocked_transport_only_config() -> ExternalAIAdapterConfig:
    """Stage 9.3-B-2a default config: disabled, no network.

    Tests may pass `fake_only_config()` explicitly to exercise the mocked
    transport path. The default remains fail-closed and never reaches
    transport.
    """
    return default_disabled_config()


class DeepSeekNetworkAdapter(ExternalAIAdapter):
    """Stage 9.3-B-2a minimal adapter with injected mocked transport.

    Fixed call order in `generate()`:

    1. `guard_request(request)`
    2. `assert_external_ai_runtime_policy_allowed(policy)`
    3. `build_deepseek_provider_payload(request)`
    4. `build_transport_request_from_provider_payload(payload)`
    5. `transport.send(transport_request)` (mocked in Stage 9.3-B-2a)
    6. construct `ExternalAIResponse` from the transport response
    7. `guard_response(response)`
    8. return response

    Fail-closed paths (all raise `BlockedAdapterError`):

    - default `mode="disabled"` config (no transport call attempted)
    - `mode="network"` (defensive; config guard already blocks)
    - missing runtime policy or policy guard fails
    - missing transport
    - `guard_request` fails
    - transport raises `DeepSeekTransportError` (timeout / http_error /
      malformed) or any other exception
    - transport returns a non-`DeepSeekTransportResponse` object
    - `guard_response` fails (forbidden output term / privacy token /
      validator_result not passed)

    Raw prompt / raw response are NEVER persisted; this adapter has no
    storage path. The response carries `not_saved_by_default=True` and
    `human_review_required=True`.
    """

    def __init__(
        self,
        config: ExternalAIAdapterConfig | None = None,
        *,
        transport: DeepSeekTransport | None = None,
        runtime_policy: ExternalAIRuntimePolicy | None = None,
    ) -> None:
        super().__init__(config or mocked_transport_only_config())
        self._transport = transport
        self._runtime_policy = runtime_policy

    @property
    def transport(self) -> DeepSeekTransport | None:
        return self._transport

    @property
    def runtime_policy(self) -> ExternalAIRuntimePolicy | None:
        return self._runtime_policy

    def generate(self, request: ExternalAIRequest) -> ExternalAIResponse:
        # 1. guard_request
        request_guard = guard_request(request)
        if not request_guard.passed:
            raise BlockedAdapterError(request_guard.findings)

        # Config-level mode gates do not attempt to involve transport.
        if self.config.mode == "disabled":
            raise BlockedAdapterError(["adapter_disabled_in_stage_9_3_a"])
        if self.config.mode == "network":
            raise BlockedAdapterError(
                ["network_mode_not_implemented_in_stage_9_3_b_2a"]
            )
        if self.config.mode != "fake":
            raise BlockedAdapterError([f"unsupported_mode_{self.config.mode}"])

        # 2. runtime policy
        if self._runtime_policy is None:
            raise BlockedAdapterError(["missing_runtime_policy"])
        assert_external_ai_runtime_policy_allowed(self._runtime_policy)

        # 3. provider payload (guard_request runs again inside, harmless)
        payload = build_deepseek_provider_payload(request)

        # 4. transport request
        transport_request = build_transport_request_from_provider_payload(payload)

        # 5. transport send (mocked in Stage 9.3-B-2a)
        if self._transport is None:
            raise BlockedAdapterError(["missing_transport"])
        try:
            transport_response = self._transport.send(transport_request)
        except DeepSeekTransportError as exc:
            raise BlockedAdapterError([f"transport_error_{exc.kind}"]) from exc
        except BlockedAdapterError:
            raise
        except Exception:
            # Any other exception is treated as fail-closed; the detail is
            # NOT leaked, only a categorical finding.
            raise BlockedAdapterError(["transport_unknown_error"])

        if not isinstance(transport_response, DeepSeekTransportResponse):
            raise BlockedAdapterError(["transport_malformed_response"])

        # 6. construct ExternalAIResponse. Stage 9.3-B-2a remains
        #    external_model_called=False because the transport is mocked.
        response = ExternalAIResponse(
            provider=self.config.provider,
            mode="fake",
            external_model_called=False,
            fake_response=True,
            content=transport_response.content_text,
            validator_result=AIMemoValidatorResult(
                passed=True,
                blocked_terms=[],
                privacy_findings=[],
            ),
            privacy_summary=ExternalAIPrivacySummary(
                uses_ai_context_manifest_only=True,
                uses_holdings_line_items=False,
                uses_raw_provider_payloads=False,
                uses_raw_prompts=False,
                external_model_called=False,
                search_called=False,
                saved_by_default=False,
            ),
            not_saved_by_default=True,
            human_review_required=True,
        )

        # 7. guard_response blocks forbidden output terms, privacy tokens,
        #    validator_result failure, and Stage 9.3-A invariants.
        response_guard = guard_response(response)
        if not response_guard.passed:
            raise BlockedAdapterError(response_guard.findings)

        return response

    def generate_external_response(
        self,
        request: ExternalAIRequest,
    ) -> ExternalAIResponse:
        """Generate a guarded real-external response from an injected transport.

        This Stage 9.3-B-2c path is explicit and internal. It is not wired to
        any HTTP endpoint and does not persist raw prompt or raw response data.
        """
        request_guard = guard_request(request)
        if not request_guard.passed:
            raise BlockedAdapterError(request_guard.findings)

        if self.config.mode == "disabled":
            raise BlockedAdapterError(["adapter_disabled_in_stage_9_3_a"])
        if self.config.mode == "network":
            raise BlockedAdapterError(
                ["network_mode_not_implemented_in_stage_9_3_b_2c"]
            )
        if self.config.mode != "fake":
            raise BlockedAdapterError([f"unsupported_mode_{self.config.mode}"])

        if self._runtime_policy is None:
            raise BlockedAdapterError(["missing_runtime_policy"])
        assert_external_ai_runtime_policy_allowed(self._runtime_policy)

        payload = build_deepseek_provider_payload(request)
        transport_request = build_transport_request_from_provider_payload(payload)

        if self._transport is None:
            raise BlockedAdapterError(["missing_transport"])
        try:
            transport_response = self._transport.send(transport_request)
        except DeepSeekTransportError as exc:
            raise BlockedAdapterError([f"transport_error_{exc.kind}"]) from exc
        except BlockedAdapterError:
            raise
        except Exception:
            raise BlockedAdapterError(["transport_unknown_error"])

        if not isinstance(transport_response, DeepSeekTransportResponse):
            raise BlockedAdapterError(["transport_malformed_response"])

        validator_result = validate_external_ai_response_content(
            transport_response.content_text
        )
        response = ExternalAIResponse(
            provider=self.config.provider,
            mode="network",
            external_model_called=True,
            fake_response=False,
            content=transport_response.content_text,
            validator_result=validator_result,
            privacy_summary=ExternalAIPrivacySummary(
                uses_ai_context_manifest_only=True,
                uses_holdings_line_items=False,
                uses_raw_provider_payloads=False,
                uses_raw_prompts=False,
                external_model_called=True,
                search_called=False,
                saved_by_default=False,
            ),
            not_saved_by_default=True,
            human_review_required=True,
        )

        response_guard = guard_external_model_response(response)
        if not response_guard.passed:
            raise BlockedAdapterError(response_guard.findings)

        return response


__all__ = [
    "DeepSeekAdapter",
    "FakeDeepSeekAdapter",
    "DeepSeekNetworkAdapter",
    "FAKE_BOUNDARY_NOTICE",
    "default_disabled_config",
    "fake_only_config",
    "mocked_transport_only_config",
]
