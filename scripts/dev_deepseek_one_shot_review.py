from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Callable


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from app_backend.schemas.ai_external import (  # noqa: E402
    DeepSeekTransportResponse,
    ExternalAIRuntimePolicy,
)
from app_backend.services import ai_context_service  # noqa: E402
from app_backend.services.ai_external_adapter import (  # noqa: E402
    BlockedAdapterError,
    guard_external_model_response,
    guard_request,
    validate_external_ai_response_content,
)
from app_backend.services.ai_external_request_builder import (  # noqa: E402
    build_external_ai_request_from_manifest,
)
from app_backend.services.ai_external_runtime_policy import (  # noqa: E402
    guard_external_ai_runtime_policy,
)
from app_backend.services.deepseek_adapter import (  # noqa: E402
    DeepSeekNetworkAdapter,
    network_config,
)
from app_backend.services.deepseek_provider_contract import (  # noqa: E402
    build_deepseek_provider_payload,
)
from app_backend.services.deepseek_real_transport import (  # noqa: E402
    DeepSeekRealTransport,
    load_deepseek_api_key_from_env,
)
from app_backend.services.deepseek_transport_contract import (  # noqa: E402
    DeepSeekTransport,
    DeepSeekTransportError,
    build_transport_request_from_provider_payload,
)


SANITIZED_CONTENT_PREVIEW_LIMIT = 800


class OneShotReviewBlocked(RuntimeError):
    def __init__(self, findings: list[str]) -> None:
        super().__init__("; ".join(findings) or "one_shot_review_blocked")
        self.findings = list(findings)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Local-only, manual-only DeepSeek one-shot review. Default mode "
            "is dry-run and never calls the provider."
        )
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--dry-run",
        action="store_true",
        help="Build and print sanitized summaries only. This is the default.",
    )
    mode.add_argument(
        "--live-call",
        action="store_true",
        help="Permit a real DeepSeek call only when all confirmation flags pass.",
    )
    parser.add_argument(
        "--i-understand-this-calls-deepseek",
        action="store_true",
        help="Required with --live-call.",
    )
    parser.add_argument(
        "--confirm-context-preview",
        action="store_true",
        help="Required with --live-call after reviewing the sanitized preview.",
    )
    return parser.parse_args(argv)


def run_one_shot_review(
    argv: list[str] | None = None,
    *,
    manifest_builder: Callable[[], Any] | None = None,
    transport_factory: Callable[[str], DeepSeekTransport] | None = None,
    key_loader: Callable[[], str] | None = None,
    emit: Callable[[dict[str, Any]], None] | None = None,
) -> dict[str, Any]:
    """Run the local one-shot review flow.

    The default path is dry-run and fails closed before any transport is
    constructed. Tests inject manifest, key, and transport callables; CLI live
    mode uses the existing process-env key loader and real transport.
    """
    args = parse_args(argv)
    manifest = (manifest_builder or ai_context_service.build_ai_context_manifest)()
    request = build_external_ai_request_from_manifest(manifest)
    request_guard = guard_request(request)
    preview_summary = _build_preview_summary(
        request=request,
        mode="live" if args.live_call else "dry_run",
        request_guard_passed=request_guard.passed,
    )
    _emit(emit, {"type": "sanitized_context_preview", "summary": preview_summary})

    if not request_guard.passed:
        return _blocked_result(
            "request_guard_failed",
            request_guard.findings,
            preview_summary,
            emit=emit,
        )

    if not args.live_call:
        return _blocked_result(
            "live_call_flag_required",
            ["live_call_not_requested"],
            preview_summary,
            emit=emit,
        )
    if not args.i_understand_this_calls_deepseek:
        return _blocked_result(
            "manual_deepseek_confirmation_required",
            ["missing_i_understand_this_calls_deepseek"],
            preview_summary,
            emit=emit,
        )
    if not args.confirm_context_preview:
        return _blocked_result(
            "context_preview_confirmation_required",
            ["missing_confirm_context_preview"],
            preview_summary,
            emit=emit,
        )

    policy = _approved_one_shot_runtime_policy()
    policy_guard = guard_external_ai_runtime_policy(policy)
    if not policy_guard.passed:
        return _blocked_result(
            "runtime_policy_failed",
            policy_guard.findings,
            preview_summary,
            emit=emit,
        )

    try:
        api_key = (key_loader or load_deepseek_api_key_from_env)()
    except DeepSeekTransportError as exc:
        return _blocked_result(
            f"transport_error_{exc.kind}",
            [f"transport_error_{exc.kind}"],
            preview_summary,
            emit=emit,
        )

    if not isinstance(api_key, str) or not api_key.strip():
        return _blocked_result(
            "missing_deepseek_api_key",
            ["transport_error_missing_key"],
            preview_summary,
            emit=emit,
        )

    try:
        response = _send_live_one_shot(
            request=request,
            policy=policy,
            transport=(transport_factory or _real_transport_factory)(api_key),
        )
    except DeepSeekTransportError as exc:
        return _blocked_result(
            f"transport_error_{exc.kind}",
            [f"transport_error_{exc.kind}"],
            preview_summary,
            emit=emit,
        )
    except BlockedAdapterError as exc:
        return _blocked_result(
            "external_response_blocked",
            exc.findings,
            preview_summary,
            emit=emit,
        )

    validator_result = validate_external_ai_response_content(response.content)
    external_guard = guard_external_model_response(response)
    if validator_result.passed is not True or not external_guard.passed:
        findings = list(validator_result.blocked_terms)
        findings.extend(validator_result.privacy_findings)
        findings.extend(external_guard.findings)
        summary = _build_result_summary(response=response, blocked=True)
        summary["findings"] = sorted(set(findings))
        result = {
            "status": "blocked",
            "reason": "external_guard_or_validator_failed",
            "preview_summary": preview_summary,
            "result_summary": summary,
        }
        _emit(emit, {"type": "sanitized_result_summary", "summary": summary})
        return result

    summary = _build_result_summary(response=response, blocked=False)
    result = {
        "status": "ok",
        "reason": "external_response_guarded",
        "preview_summary": preview_summary,
        "result_summary": summary,
    }
    _emit(emit, {"type": "sanitized_result_summary", "summary": summary})
    return result


def _send_live_one_shot(
    *,
    request: Any,
    policy: ExternalAIRuntimePolicy,
    transport: DeepSeekTransport,
) -> Any:
    payload = build_deepseek_provider_payload(request)
    transport_request = build_transport_request_from_provider_payload(payload)
    transport_response = transport.send(transport_request)
    if not isinstance(transport_response, DeepSeekTransportResponse):
        raise BlockedAdapterError(["transport_malformed_response"])

    adapter = DeepSeekNetworkAdapter(
        config=network_config(),
        transport=_FixedTransport(transport_response),
        runtime_policy=policy,
    )
    return adapter.generate_external_response(request)


def _approved_one_shot_runtime_policy() -> ExternalAIRuntimePolicy:
    return ExternalAIRuntimePolicy(
        external_ai_enabled=True,
        provider_network_enabled=True,
        user_controlled_switch_enabled=True,
        single_request_user_approved=True,
        context_preview_confirmed=True,
        request_built_from_manifest=True,
        request_guard_passed=True,
        response_guard_required=True,
        stage9_validator_required=True,
        human_review_required=True,
        save_raw_prompt=False,
        save_raw_response=False,
        persist_chat_by_default=False,
        allow_search=False,
        allow_tavily=False,
        allow_background_call=False,
        allow_app_start_call=False,
        allow_page_load_call=False,
        allow_holdings_line_items=False,
        allow_account_values=False,
        allow_position_weights=False,
        allow_transaction_history=False,
    )


def _build_preview_summary(
    *,
    request: Any,
    mode: str,
    request_guard_passed: bool,
) -> dict[str, Any]:
    return {
        "included_fact_count": request.included_fact_count,
        "included_model_output_count": request.included_model_output_count,
        "excluded_context_summary": request.excluded_context_summary,
        "boundary_notices": list(request.boundary_notices),
        "provider": request.provider,
        "mode": mode,
        "not_saved_by_default": True,
        "human_review_required": True,
        "request_guard_passed": request_guard_passed,
        "dangerous_permissions_summary": {
            "prompt_persistence": False,
            "response_persistence": False,
            "chat_persistence": False,
            "search": False,
            "tavily": False,
            "background_call": False,
            "app_start_call": False,
            "page_load_call": False,
            "private_portfolio_detail_exposure": False,
            "account_detail_exposure": False,
            "position_detail_exposure": False,
            "transaction_detail_exposure": False,
        },
    }


def _build_result_summary(*, response: Any, blocked: bool) -> dict[str, Any]:
    blocked_terms = list(response.validator_result.blocked_terms)
    privacy_findings = list(response.validator_result.privacy_findings)
    summary = {
        "provider": response.provider,
        "external_model_called": response.external_model_called,
        "fake_response": response.fake_response,
        "validator_passed": response.validator_result.passed,
        "blocked_terms_count": len(blocked_terms),
        "privacy_findings_count": len(privacy_findings),
        "content_character_count": len(response.content),
        "human_review_required": response.human_review_required,
        "not_saved_by_default": response.not_saved_by_default,
    }
    if blocked or blocked_terms or privacy_findings:
        summary["content_preview_blocked"] = True
        summary["content_preview"] = ""
    else:
        summary["content_preview_blocked"] = False
        summary["content_preview"] = response.content[:SANITIZED_CONTENT_PREVIEW_LIMIT]
    return summary


def _blocked_result(
    reason: str,
    findings: list[str],
    preview_summary: dict[str, Any],
    *,
    emit: Callable[[dict[str, Any]], None] | None,
) -> dict[str, Any]:
    summary = {
        "provider": "deepseek",
        "external_model_called": False,
        "fake_response": False,
        "validator_passed": False,
        "blocked_terms_count": 0,
        "privacy_findings_count": 0,
        "content_character_count": 0,
        "human_review_required": True,
        "not_saved_by_default": True,
        "content_preview_blocked": True,
        "content_preview": "",
        "findings": list(findings),
    }
    result = {
        "status": "blocked",
        "reason": reason,
        "preview_summary": preview_summary,
        "result_summary": summary,
    }
    _emit(emit, {"type": "sanitized_result_summary", "summary": summary})
    return result


def _emit(
    emit: Callable[[dict[str, Any]], None] | None,
    payload: dict[str, Any],
) -> None:
    if emit is None:
        print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
    else:
        emit(payload)


def _real_transport_factory(api_key: str) -> DeepSeekRealTransport:
    return DeepSeekRealTransport(api_key=api_key)


class _FixedTransport:
    def __init__(self, response: DeepSeekTransportResponse) -> None:
        self.response = response

    def send(self, request: Any) -> DeepSeekTransportResponse:
        return self.response


def main(argv: list[str] | None = None) -> int:
    result = run_one_shot_review(argv)
    return 0 if result["status"] in {"ok", "blocked"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
