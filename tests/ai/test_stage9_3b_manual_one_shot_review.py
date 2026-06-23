from __future__ import annotations

from pathlib import Path

import pytest

import dev_deepseek_one_shot_review as review
from app_backend.main import app
from app_backend.schemas.ai_external import DeepSeekTransportResponse
from app_backend.services.deepseek_transport_contract import DeepSeekTransportError

_REPO_ROOT = Path(__file__).resolve().parents[2]


STAGE_9_2_SURFACE_FILES = (
    str(_REPO_ROOT / "src/app_backend/main.py"),
    str(_REPO_ROOT / "src/app_backend/services/ai_preview_service.py"),
    str(_REPO_ROOT / "src/app_backend/services/ai_memo_renderer.py"),
    str(_REPO_ROOT / "src/app_backend/services/ai_context_service.py"),
)

FORBIDDEN_ROUTES = {
    "/api/chat",
    "/api/search",
    "/api/ai/deepseek",
    "/api/ai/external",
    "/api/ai/tavily",
}

FORBIDDEN_OUTPUT_TOKENS = (
    "test-secret-key",
    "raw_prompt",
    "raw_response",
    "raw_provider_payload",
    "api_key",
    "holdings line items",
    "account values",
    "position weights",
    "transaction history",
    "g:\\local_macro_portfolio_ai",
    ".env",
    "external_llm.yaml",
)


class SpyTransport:
    def __init__(
        self,
        *,
        content: str = "Reference evidence only. Human review is required.",
        error_kind: str | None = None,
        malformed: bool = False,
    ) -> None:
        self.calls = []
        self.content = content
        self.error_kind = error_kind
        self.malformed = malformed

    def send(self, request):
        self.calls.append(request)
        if self.error_kind is not None:
            raise DeepSeekTransportError(kind=self.error_kind)
        if self.malformed:
            return {"content_text": self.content}
        return DeepSeekTransportResponse(
            request_id=request.request_id,
            provider=request.provider,
            mode=request.mode,
            content_text=self.content,
            finish_reason="stop",
        )


def test_default_run_fails_closed_and_does_not_touch_transport():
    transport = SpyTransport()
    emitted = []

    result = review.run_one_shot_review(
        [],
        manifest_builder=_manifest_fixture,
        key_loader=_key_loader,
        transport_factory=lambda _key: transport,
        emit=emitted.append,
    )

    assert result["status"] == "blocked"
    assert result["reason"] == "live_call_flag_required"
    assert transport.calls == []
    assert emitted[0]["type"] == "sanitized_context_preview"
    assert emitted[1]["type"] == "sanitized_result_summary"


@pytest.mark.parametrize(
    ("argv", "reason"),
    [
        (["--dry-run"], "live_call_flag_required"),
        (["--i-understand-this-calls-deepseek", "--confirm-context-preview"], "live_call_flag_required"),
        (["--live-call", "--confirm-context-preview"], "manual_deepseek_confirmation_required"),
        (["--live-call", "--i-understand-this-calls-deepseek"], "context_preview_confirmation_required"),
    ],
)
def test_missing_live_flags_fail_closed(argv, reason):
    transport = SpyTransport()

    result = review.run_one_shot_review(
        argv,
        manifest_builder=_manifest_fixture,
        key_loader=_key_loader,
        transport_factory=lambda _key: transport,
        emit=lambda _payload: None,
    )

    assert result["status"] == "blocked"
    assert result["reason"] == reason
    assert transport.calls == []


def test_full_live_flags_without_key_fail_closed_and_do_not_read_dotenv_or_yaml(monkeypatch):
    transport = SpyTransport()

    def _missing_key():
        raise DeepSeekTransportError(kind="missing_key", detail="missing")

    forbidden_reads = []

    def _blocked_read_text(self, *args, **kwargs):
        text = str(self).lower()
        if text.endswith(".env") or text.endswith("external_llm.yaml"):
            forbidden_reads.append(text)
            raise AssertionError(f"forbidden config read: {self}")
        return original_read_text(self, *args, **kwargs)

    original_read_text = Path.read_text
    monkeypatch.setattr(Path, "read_text", _blocked_read_text)

    result = review.run_one_shot_review(
        [
            "--live-call",
            "--i-understand-this-calls-deepseek",
            "--confirm-context-preview",
        ],
        manifest_builder=_manifest_fixture,
        key_loader=_missing_key,
        transport_factory=lambda _key: transport,
        emit=lambda _payload: None,
    )

    assert result["status"] == "blocked"
    assert result["reason"] == "transport_error_missing_key"
    assert transport.calls == []
    assert forbidden_reads == []
    assert "test-secret-key" not in str(result).lower()


def test_mock_success_path_runs_full_sanitized_chain(monkeypatch):
    calls = {
        "manifest": 0,
        "request_guard": 0,
        "runtime_policy": 0,
        "provider_payload": 0,
        "validator": 0,
        "external_guard": 0,
    }
    transport = SpyTransport()

    def _manifest():
        calls["manifest"] += 1
        return _manifest_fixture()

    original_guard_request = review.guard_request
    original_runtime_guard = review.guard_external_ai_runtime_policy
    original_provider_builder = review.build_deepseek_provider_payload
    original_validator = review.validate_external_ai_response_content
    original_external_guard = review.guard_external_model_response

    def _guard_request(request, *args, **kwargs):
        calls["request_guard"] += 1
        return original_guard_request(request, *args, **kwargs)

    def _runtime_guard(policy):
        calls["runtime_policy"] += 1
        return original_runtime_guard(policy)

    def _provider_builder(request_obj):
        calls["provider_payload"] += 1
        return original_provider_builder(request_obj)

    def _validator(content):
        calls["validator"] += 1
        return original_validator(content)

    def _external_guard(response):
        calls["external_guard"] += 1
        return original_external_guard(response)

    monkeypatch.setattr(review, "guard_request", _guard_request)
    monkeypatch.setattr(review, "guard_external_ai_runtime_policy", _runtime_guard)
    monkeypatch.setattr(review, "build_deepseek_provider_payload", _provider_builder)
    monkeypatch.setattr(review, "validate_external_ai_response_content", _validator)
    monkeypatch.setattr(review, "guard_external_model_response", _external_guard)

    result = review.run_one_shot_review(
        [
            "--live-call",
            "--i-understand-this-calls-deepseek",
            "--confirm-context-preview",
        ],
        manifest_builder=_manifest,
        key_loader=_key_loader,
        transport_factory=lambda _key: transport,
        emit=lambda _payload: None,
    )

    assert result["status"] == "ok"
    assert calls["manifest"] == 1
    assert calls["request_guard"] >= 1
    assert calls["runtime_policy"] == 1
    assert calls["provider_payload"] == 1
    assert len(transport.calls) == 1
    assert calls["validator"] >= 1
    assert calls["external_guard"] >= 1
    summary = result["result_summary"]
    assert summary["external_model_called"] is True
    assert summary["fake_response"] is False
    assert summary["validator_passed"] is True
    assert summary["not_saved_by_default"] is True
    assert summary["human_review_required"] is True
    _assert_sanitized(result)


def test_request_guard_failure_prevents_transport(monkeypatch):
    transport = SpyTransport()

    def _blocked_guard(_request, *args, **kwargs):
        return _guard_result(False, ["blocked_by_test"])

    monkeypatch.setattr(review, "guard_request", _blocked_guard)

    result = review.run_one_shot_review(
        [
            "--live-call",
            "--i-understand-this-calls-deepseek",
            "--confirm-context-preview",
        ],
        manifest_builder=_manifest_fixture,
        key_loader=_key_loader,
        transport_factory=lambda _key: transport,
        emit=lambda _payload: None,
    )

    assert result["status"] == "blocked"
    assert result["reason"] == "request_guard_failed"
    assert transport.calls == []


def test_runtime_policy_failure_prevents_transport(monkeypatch):
    transport = SpyTransport()

    monkeypatch.setattr(
        review,
        "guard_external_ai_runtime_policy",
        lambda _policy: _guard_result(False, ["runtime_blocked_by_test"]),
    )

    result = review.run_one_shot_review(
        [
            "--live-call",
            "--i-understand-this-calls-deepseek",
            "--confirm-context-preview",
        ],
        manifest_builder=_manifest_fixture,
        key_loader=_key_loader,
        transport_factory=lambda _key: transport,
        emit=lambda _payload: None,
    )

    assert result["status"] == "blocked"
    assert result["reason"] == "runtime_policy_failed"
    assert transport.calls == []


@pytest.mark.parametrize("kind", ["timeout", "http_error", "malformed", "provider_refusal"])
def test_transport_error_paths_fail_closed(kind):
    transport = SpyTransport(error_kind=kind)

    result = review.run_one_shot_review(
        [
            "--live-call",
            "--i-understand-this-calls-deepseek",
            "--confirm-context-preview",
        ],
        manifest_builder=_manifest_fixture,
        key_loader=_key_loader,
        transport_factory=lambda _key: transport,
        emit=lambda _payload: None,
    )

    assert result["status"] == "blocked"
    assert result["reason"] == f"transport_error_{kind}"
    assert result["result_summary"]["content_preview"] == ""


def test_malformed_transport_response_fails_closed():
    transport = SpyTransport(malformed=True)

    result = review.run_one_shot_review(
        [
            "--live-call",
            "--i-understand-this-calls-deepseek",
            "--confirm-context-preview",
        ],
        manifest_builder=_manifest_fixture,
        key_loader=_key_loader,
        transport_factory=lambda _key: transport,
        emit=lambda _payload: None,
    )

    assert result["status"] == "blocked"
    assert result["reason"] == "external_response_blocked"
    assert result["result_summary"]["content_preview"] == ""


@pytest.mark.parametrize(
    "content",
    [
        "This says buy now. Human review is required.",
        "This leaks api_key. Human review is required.",
    ],
)
def test_validator_and_external_guard_block_preview(content):
    transport = SpyTransport(content=content)

    result = review.run_one_shot_review(
        [
            "--live-call",
            "--i-understand-this-calls-deepseek",
            "--confirm-context-preview",
        ],
        manifest_builder=_manifest_fixture,
        key_loader=_key_loader,
        transport_factory=lambda _key: transport,
        emit=lambda _payload: None,
    )

    assert result["status"] == "blocked"
    assert result["result_summary"]["content_preview_blocked"] is True
    assert result["result_summary"]["content_preview"] == ""


def test_route_and_stage92_import_isolation():
    route_paths = {route.path for route in app.routes}
    assert route_paths.isdisjoint(FORBIDDEN_ROUTES)

    for file_path in STAGE_9_2_SURFACE_FILES:
        source = Path(file_path).read_text(encoding="utf-8")
        for forbidden in (
            "dev_deepseek_one_shot_review",
            "DeepSeekNetworkAdapter",
            "DeepSeekRealTransport",
            "ai_external_runtime_policy",
            "build_deepseek_provider_payload",
            "load_deepseek_api_key_from_env",
        ):
            assert forbidden not in source

    main_source = (_REPO_ROOT / "src/app_backend/main.py").read_text(encoding="utf-8")
    assert "dev_deepseek_one_shot_review" not in main_source


def test_default_run_does_not_write_files(tmp_path, monkeypatch):
    writes = []

    def _blocked_write_text(self, *args, **kwargs):
        writes.append(str(self))
        raise AssertionError("default one-shot review must not write files")

    monkeypatch.setattr(Path, "write_text", _blocked_write_text)

    result = review.run_one_shot_review(
        [],
        manifest_builder=_manifest_fixture,
        key_loader=_key_loader,
        transport_factory=lambda _key: SpyTransport(),
        emit=lambda _payload: None,
    )

    assert result["status"] == "blocked"
    assert writes == []
    assert "--save-sanitized-summary" not in Path(
        str(_REPO_ROOT / "scripts/dev_deepseek_one_shot_review.py")
    ).read_text(encoding="utf-8")


def _manifest_fixture():
    return {
        "included_facts": [
            {"metric_key": "macro_fact", "value_text": "available"},
            {"metric_key": "liquidity_fact", "value_text": "available"},
        ],
        "excluded_facts": [{"metric_key": "stale_fact", "status": "stale"}],
        "included_model_outputs": [
            {"metric_key": "stress_score", "value_text": "reference only"}
        ],
        "excluded_model_outputs": [
            {"metric_key": "missing_model", "status": "missing"}
        ],
        "risk_boundaries": [
            "Reference evidence only.",
            "Human review is required.",
            "Not an action directive.",
        ],
    }


def _key_loader() -> str:
    return "test-secret-key"


def _guard_result(passed: bool, findings: list[str]):
    from app_backend.schemas.ai_external import ExternalAIGuardResult

    return ExternalAIGuardResult(passed=passed, findings=findings)


def _assert_sanitized(result) -> None:
    text = str(result).lower()
    for token in FORBIDDEN_OUTPUT_TOKENS:
        assert token not in text
