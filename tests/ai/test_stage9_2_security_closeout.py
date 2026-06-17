"""Stage 9.2 closeout / security review regression tests.

Locks the AI preview endpoint surface, validator gate behavior, request
handling edge cases, and M7/M8-A pipeline coexistence after the dashboard
model pipeline extraction. These tests do not touch production code; they
exist to fail-closed on any regression in:

- preview endpoint surface (no chat/search/save endpoints added)
- validator flag gates (external_model_called / search_called / saved_by_default /
  not_sent_to_external_model / human_review_required / interpretation_boundary /
  boundary notice)
- request handling (empty/whitespace/very long question; question never echoed,
  determinism preserved)
- M7/M8-A regression (preview endpoints work end-to-end after the pipeline
  extraction; preview module does not import the pipeline directly)
"""
from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient

from app_backend.main import app
from app_backend.schemas.ai_preview import (
    AIPreviewChatRequest,
    AIPreviewMemoRequest,
    AIPreviewReportRequest,
)
from app_backend.services import ai_context_service, ai_preview_service


# ---------------------------------------------------------------------------
# 1. Endpoint surface audit (positive + negative)
# ---------------------------------------------------------------------------


REQUIRED_PREVIEW_ROUTES = {
    "/api/ai/context-preview",
    "/api/ai/preview-chat",
    "/api/ai/preview-memo",
    "/api/ai/preview-report",
}

FORBIDDEN_ROUTES = {
    "/api/chat",
    "/api/search",
    "/api/ai/chat",
    "/api/ai/search",
    "/api/ai/deepseek",
    "/api/ai/tavily",
    "/api/ai/preview-save",
    "/api/ai/preview-favorite",
    "/api/ai/report-save",
    "/api/ai/report-export",
}


def test_required_preview_routes_exist():
    route_paths = {route.path for route in app.routes}
    missing = REQUIRED_PREVIEW_ROUTES - route_paths
    assert not missing, f"Required preview routes missing: {missing}"


def test_no_forbidden_routes_present():
    route_paths = {route.path for route in app.routes}
    present = FORBIDDEN_ROUTES & route_paths
    assert not present, f"Forbidden routes present: {present}"


def test_no_endpoint_name_implies_real_external_ai():
    route_paths = {route.path for route in app.routes}
    for path in route_paths:
        lowered = path.lower()
        assert "deepseek" not in lowered, f"deepseek in route: {path}"
        assert "tavily" not in lowered, f"tavily in route: {path}"
        assert "external" not in lowered, f"external in route: {path}"


# ---------------------------------------------------------------------------
# 2. Context source audit — preview services depend only on manifest
# ---------------------------------------------------------------------------


def test_ai_preview_service_does_not_import_dashboard_model_pipeline():
    """Preview must consume AI Context Manifest, not call the pipeline directly."""
    source = Path("src/app_backend/services/ai_preview_service.py").read_text(
        encoding="utf-8"
    )
    assert "dashboard_model_pipeline" not in source
    assert "build_dashboard_model_rows" not in source


def test_ai_memo_renderer_does_not_import_dashboard_model_pipeline():
    source = Path("src/app_backend/services/ai_memo_renderer.py").read_text(
        encoding="utf-8"
    )
    assert "dashboard_model_pipeline" not in source
    assert "build_dashboard_model_rows" not in source


def test_ai_preview_service_does_not_open_private_files():
    source = Path("src/app_backend/services/ai_preview_service.py").read_text(
        encoding="utf-8"
    )
    # No raw file I/O or private path references in preview service.
    # (uses_holdings_line_items is a legitimate privacy advertisement flag
    # on the privacy summary; it does not read holdings.)
    assert "open(" not in source
    assert "current_holdings.csv" not in source
    assert "data/private" not in source
    assert "sqlite" not in source.lower()
    assert "holdings_line_items" in source  # advertises the boundary
    assert "uses_holdings_line_items=False" in source


# ---------------------------------------------------------------------------
# 3. Validator flag-gate audit
# ---------------------------------------------------------------------------


def _valid_payload():
    return {
        "mode": "local_preview",
        "answer_preview": "Local preview only. " + ai_preview_service.BOUNDARY_NOTICE,
        "sections": [
            {
                "key": "boundary_notice",
                "title": "Boundary Notice",
                "content": ai_preview_service.BOUNDARY_NOTICE,
                "source_context": ["stage9.boundary"],
            }
        ],
        "context_used_summary": {
            "included_fact_count": 0,
            "excluded_fact_count": 0,
            "included_model_output_count": 0,
            "excluded_model_output_count": 0,
        },
        "privacy_summary": {
            "uses_ai_context_manifest_only": True,
            "uses_holdings_line_items": False,
            "uses_raw_provider_payloads": False,
            "uses_raw_prompts": False,
            "external_model_called": False,
            "search_called": False,
            "saved_by_default": False,
        },
        "validator_result": {
            "passed": True,
            "blocked_terms": [],
            "privacy_findings": [],
        },
        "not_sent_to_external_model": True,
        "human_review_required": True,
        "interpretation_boundary": ai_preview_service.BOUNDARY_NOTICE,
    }


def test_validator_blocks_external_model_called_true():
    payload = _valid_payload()
    payload["privacy_summary"]["external_model_called"] = True
    result = ai_preview_service.validate_ai_preview_payload(payload)
    assert result.passed is False
    assert "external_model_called" in result.privacy_findings


def test_validator_blocks_search_called_true():
    payload = _valid_payload()
    payload["privacy_summary"]["search_called"] = True
    result = ai_preview_service.validate_ai_preview_payload(payload)
    assert result.passed is False
    assert "search_called" in result.privacy_findings


def test_validator_blocks_saved_by_default_true():
    payload = _valid_payload()
    payload["privacy_summary"]["saved_by_default"] = True
    result = ai_preview_service.validate_ai_preview_payload(payload)
    assert result.passed is False
    assert "saved_by_default" in result.privacy_findings


def test_validator_blocks_not_sent_to_external_model_missing():
    payload = _valid_payload()
    payload["not_sent_to_external_model"] = False
    result = ai_preview_service.validate_ai_preview_payload(payload)
    assert result.passed is False
    assert "not_sent_to_external_model_missing" in result.privacy_findings


def test_validator_blocks_human_review_required_missing():
    payload = _valid_payload()
    payload["human_review_required"] = False
    result = ai_preview_service.validate_ai_preview_payload(payload)
    assert result.passed is False
    assert "human_review_required_missing" in result.privacy_findings


def test_validator_blocks_interpretation_boundary_missing():
    payload = _valid_payload()
    payload["interpretation_boundary"] = ""
    result = ai_preview_service.validate_ai_preview_payload(payload)
    assert result.passed is False
    assert "interpretation_boundary_missing" in result.privacy_findings


def test_validator_blocks_boundary_notice_missing_from_sections():
    """When neither sections nor interpretation_boundary carry the boundary
    phrases, the validator must flag boundary_notice_missing."""
    payload = _valid_payload()
    payload["sections"] = [
        {
            "key": "evidence_summary",
            "title": "Evidence Summary",
            "content": "Some unrelated content without any boundary phrasing.",
            "source_context": [],
        }
    ]
    # Use a boundary string that is non-empty but does NOT contain the
    # canonical "not an action directive" / "human review is required" phrases.
    payload["interpretation_boundary"] = "Reference only."
    result = ai_preview_service.validate_ai_preview_payload(payload)
    assert result.passed is False
    assert "boundary_notice_missing" in result.privacy_findings


# ---------------------------------------------------------------------------
# 4. Request handling audit — edge cases for question
# ---------------------------------------------------------------------------


def test_preview_chat_handles_empty_question_safely(monkeypatch):
    monkeypatch.setattr(ai_context_service, "build_ai_context_manifest", _manifest_fixture)
    response = TestClient(app).post(
        "/api/ai/preview-chat",
        json={"question": "", "style": "natural", "context_mode": "full_sanitized"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["mode"] == "local_preview"
    assert data["validator_result"]["passed"] is True
    assert data["not_sent_to_external_model"] is True


def test_preview_chat_handles_whitespace_question_safely(monkeypatch):
    monkeypatch.setattr(ai_context_service, "build_ai_context_manifest", _manifest_fixture)
    response = TestClient(app).post(
        "/api/ai/preview-chat",
        json={"question": "   \n\t   ", "style": "natural", "context_mode": "full_sanitized"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["mode"] == "local_preview"
    assert data["validator_result"]["passed"] is True
    # Whitespace must not appear meaningfully in answer (since question is ignored)
    assert "   \n\t   " not in response.text


def test_preview_chat_handles_very_long_question_safely(monkeypatch):
    monkeypatch.setattr(ai_context_service, "build_ai_context_manifest", _manifest_fixture)
    long_marker = "VERY_LONG_QUESTION_MUST_NOT_LEAK_" + ("X" * 5000)
    response = TestClient(app).post(
        "/api/ai/preview-chat",
        json={
            "question": long_marker,
            "style": "natural",
            "context_mode": "full_sanitized",
        },
    )
    assert response.status_code == 200
    assert long_marker not in response.text
    assert "VERY_LONG_QUESTION_MUST_NOT_LEAK" not in response.text
    assert response.json()["validator_result"]["passed"] is True


def test_preview_chat_rejects_unsupported_style():
    # Pydantic Literal validation must fail-closed on unsupported style.
    response = TestClient(app).post(
        "/api/ai/preview-chat",
        json={"question": "x", "style": "freeform_creative", "context_mode": "full_sanitized"},
    )
    assert response.status_code == 422


def test_preview_chat_rejects_unsupported_context_mode():
    response = TestClient(app).post(
        "/api/ai/preview-chat",
        json={"question": "x", "style": "natural", "context_mode": "include_raw_holdings"},
    )
    assert response.status_code == 422


def test_preview_chat_deterministic_repeated_request(monkeypatch):
    monkeypatch.setattr(ai_context_service, "build_ai_context_manifest", _manifest_fixture)
    request_body = {
        "question": "What is the current macro context?",
        "style": "structured",
        "context_mode": "full_sanitized",
    }
    first = TestClient(app).post("/api/ai/preview-chat", json=request_body)
    second = TestClient(app).post("/api/ai/preview-chat", json=request_body)
    third = TestClient(app).post("/api/ai/preview-chat", json=request_body)
    assert first.json() == second.json() == third.json()


# ---------------------------------------------------------------------------
# 5. Context-mode audit — excluded rows remain constraints only
# ---------------------------------------------------------------------------


def test_excluded_facts_appear_only_in_constraints_section(monkeypatch):
    monkeypatch.setattr(ai_context_service, "build_ai_context_manifest", _manifest_fixture)
    request = AIPreviewChatRequest(
        question="x", style="structured", context_mode="full_sanitized"
    )
    preview = ai_preview_service.render_chat_preview(request)

    constraints_section = _section(preview, "missing_or_excluded_constraints")
    evidence_section = _section(preview, "evidence_summary")
    model_output_section = _section(preview, "model_output_summary")

    # Excluded fact label should appear ONLY in constraints section
    excluded_label = "Valuation missing inputs"
    assert excluded_label in constraints_section.content
    assert excluded_label not in evidence_section.content
    assert excluded_label not in model_output_section.content


def test_stage8_overlay_remains_downstream_only_in_chat(monkeypatch):
    monkeypatch.setattr(ai_context_service, "build_ai_context_manifest", _manifest_fixture)
    request = AIPreviewChatRequest(
        question="x", style="natural", context_mode="full_sanitized"
    )
    preview = ai_preview_service.render_chat_preview(request)
    overlay_section = _section(preview, "portfolio_overlay_summary")
    # Must reference the policy mode, not raw holdings
    assert "compact_summary_only" in overlay_section.content
    assert "holdings" not in overlay_section.content.lower()


# ---------------------------------------------------------------------------
# 6. M7/M8-A regression coexistence — preview endpoints still work after extraction
# ---------------------------------------------------------------------------


def test_dashboard_model_pipeline_module_exists():
    """Sanity check: M7/M8-A extraction is in place."""
    from app_backend.services import dashboard_model_pipeline  # noqa: F401
    from app_backend.services.dashboard_model_pipeline import (  # noqa: F401
        DashboardModelPipelineResult,
        build_dashboard_model_rows,
    )


def test_preview_endpoints_work_with_real_manifest_path(monkeypatch, tmp_path):
    """Full integration: preview chat works when manifest is built through the
    real dashboard_service path (which now uses dashboard_model_pipeline)."""
    from app_backend.services import dashboard_service

    _write_minimal_reports(tmp_path)
    monkeypatch.setattr(dashboard_service, "DEFAULT_REPORTS_DIR", tmp_path)

    response = TestClient(app).post(
        "/api/ai/preview-chat",
        json={
            "question": "test",
            "style": "natural",
            "context_mode": "full_sanitized",
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["mode"] == "local_preview"
    assert data["validator_result"]["passed"] is True


def test_context_preview_endpoint_works_with_real_manifest_path(monkeypatch, tmp_path):
    from app_backend.services import dashboard_service

    _write_minimal_reports(tmp_path)
    monkeypatch.setattr(dashboard_service, "DEFAULT_REPORTS_DIR", tmp_path)

    response = TestClient(app).get("/api/ai/context-preview")
    assert response.status_code == 200
    data = response.json()
    assert data["mode"] == "local_preview"
    assert data["external_model_called"] is False
    assert data["search_called"] is False
    assert data["saved_by_default"] is False


# ---------------------------------------------------------------------------
# 7. Privacy leak audit — concrete strings absent from preview response bodies
# ---------------------------------------------------------------------------


# Tokens that, if present in response BODIES, would indicate a real privacy
# leak. We deliberately exclude legitimate advertisement field-name substrings
# such as "uses_raw_provider_payloads" / "uses_raw_prompts" / "holdings_line_items",
# which describe the privacy boundary rather than leak data.
PRIVACY_LEAK_TOKENS = (
    "current_holdings.csv",
    "data/private",
    "G:\\local_macro_portfolio_ai",
    "/mnt/data",
    "C:\\Users\\",
    "HOLDINGS_AMOUNT_MUST_NOT_LEAK",
    "RAW_FUND",
    "DEEPSEEK_API_KEY",
    "TAVILY_API_KEY",
    # Concrete content tokens (not field names):
    "sk_live_",
    "sk_test_",
)


def test_preview_chat_body_contains_no_privacy_tokens(monkeypatch):
    monkeypatch.setattr(ai_context_service, "build_ai_context_manifest", _manifest_fixture)
    body = TestClient(app).post(
        "/api/ai/preview-chat",
        json={"question": "x", "style": "natural", "context_mode": "full_sanitized"},
    ).text
    for token in PRIVACY_LEAK_TOKENS:
        assert token not in body, f"privacy token {token!r} leaked in preview-chat body"


def test_preview_memo_body_contains_no_privacy_tokens(monkeypatch):
    monkeypatch.setattr(ai_context_service, "build_ai_context_manifest", _manifest_fixture)
    body = TestClient(app).post(
        "/api/ai/preview-memo",
        json={"memo_type": "daily_review_memo", "style": "concise"},
    ).text
    for token in PRIVACY_LEAK_TOKENS:
        assert token not in body, f"privacy token {token!r} leaked in preview-memo body"


def test_preview_report_body_contains_no_privacy_tokens(monkeypatch):
    monkeypatch.setattr(ai_context_service, "build_ai_context_manifest", _manifest_fixture)
    body = TestClient(app).post(
        "/api/ai/preview-report",
        json={"report_type": "macro_risk_report", "style": "outline"},
    ).text
    for token in PRIVACY_LEAK_TOKENS:
        assert token not in body, f"privacy token {token!r} leaked in preview-report body"


def test_context_preview_body_contains_no_privacy_tokens(monkeypatch):
    monkeypatch.setattr(ai_context_service, "build_ai_context_manifest", _manifest_fixture)
    body = TestClient(app).get("/api/ai/context-preview").text
    for token in PRIVACY_LEAK_TOKENS:
        assert token not in body, f"privacy token {token!r} leaked in context-preview body"


# ---------------------------------------------------------------------------
# 8. Forbidden output audit — no action / probability / return language
# ---------------------------------------------------------------------------


FORBIDDEN_OUTPUT_TOKENS = (
    "buy ",
    "sell ",
    "add position",
    "reduce position",
    "clear position",
    "rebalance",
    "target allocation",
    "target weight",
    "expected return",
    "predicted return",
    "future return",
    "market direction probability",
    "crash probability",
    "recession probability",
    "trade signal",
    "guaranteed",
    "will rise",
    "will fall",
)


def test_preview_memo_body_contains_no_forbidden_action_or_return_terms(monkeypatch):
    monkeypatch.setattr(ai_context_service, "build_ai_context_manifest", _manifest_fixture)
    for memo_type in (
        "daily_review_memo",
        "risk_review_memo",
        "scenario_review_memo",
        "portfolio_overlay_review",
    ):
        body = TestClient(app).post(
            "/api/ai/preview-memo",
            json={"memo_type": memo_type, "style": "concise"},
        ).text.lower()
        for token in FORBIDDEN_OUTPUT_TOKENS:
            assert token not in body, (
                f"forbidden term {token!r} present in {memo_type} body"
            )


def test_preview_report_body_contains_no_forbidden_action_or_return_terms(monkeypatch):
    monkeypatch.setattr(ai_context_service, "build_ai_context_manifest", _manifest_fixture)
    for report_type in ("macro_risk_report", "evidence_audit_report"):
        body = TestClient(app).post(
            "/api/ai/preview-report",
            json={"report_type": report_type, "style": "outline"},
        ).text.lower()
        for token in FORBIDDEN_OUTPUT_TOKENS:
            assert token not in body, (
                f"forbidden term {token!r} present in {report_type} body"
            )


# ---------------------------------------------------------------------------
# 9. Flag audit — every preview endpoint advertises local-only flags
# ---------------------------------------------------------------------------


def test_preview_chat_advertises_local_only_flags(monkeypatch):
    monkeypatch.setattr(ai_context_service, "build_ai_context_manifest", _manifest_fixture)
    data = TestClient(app).post(
        "/api/ai/preview-chat",
        json={"question": "x", "style": "natural", "context_mode": "full_sanitized"},
    ).json()
    assert data["mode"] == "local_preview"
    assert data["not_sent_to_external_model"] is True
    assert data["human_review_required"] is True
    assert data["interpretation_boundary"]
    assert data["privacy_summary"]["external_model_called"] is False
    assert data["privacy_summary"]["search_called"] is False
    assert data["privacy_summary"]["saved_by_default"] is False
    assert data["validator_result"]["passed"] is True


def test_preview_memo_advertises_local_only_flags(monkeypatch):
    monkeypatch.setattr(ai_context_service, "build_ai_context_manifest", _manifest_fixture)
    data = TestClient(app).post(
        "/api/ai/preview-memo",
        json={"memo_type": "daily_review_memo", "style": "concise"},
    ).json()
    assert data["mode"] == "local_preview"
    assert data["not_sent_to_external_model"] is True
    assert data["human_review_required"] is True
    assert data["interpretation_boundary"]
    assert data["validator_result"]["passed"] is True


def test_preview_report_advertises_local_only_flags(monkeypatch):
    monkeypatch.setattr(ai_context_service, "build_ai_context_manifest", _manifest_fixture)
    data = TestClient(app).post(
        "/api/ai/preview-report",
        json={"report_type": "macro_risk_report", "style": "outline"},
    ).json()
    assert data["mode"] == "local_preview"
    assert data["not_sent_to_external_model"] is True
    assert data["human_review_required"] is True
    assert data["interpretation_boundary"]
    assert data["validator_result"]["passed"] is True


def test_context_preview_advertises_local_only_flags(monkeypatch):
    monkeypatch.setattr(ai_context_service, "build_ai_context_manifest", _manifest_fixture)
    data = TestClient(app).get("/api/ai/context-preview").json()
    assert data["mode"] == "local_preview"
    assert data["external_model_called"] is False
    assert data["search_called"] is False
    assert data["saved_by_default"] is False
    assert data["search_enabled"] is False
    assert data["model_destination"]["destination"] == "local_preview_only"
    assert data["model_destination"]["deepseek_enabled"] is False
    assert data["model_destination"]["tavily_enabled"] is False


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _section(preview, section_key):
    for section in preview.sections:
        if section.key == section_key:
            return section
    raise AssertionError(f"missing section {section_key}")


def _manifest_fixture():
    return {
        "generated_at": "2026-06-15T00:00:00+00:00",
        "included_facts": [
            _row("credit_stress", "high_yield_spread", "High yield spread", source_badge="official"),
        ],
        "excluded_facts": [
            {
                **_row(
                    "valuation_equity_structure",
                    "valuation_missing_inputs",
                    "Valuation missing inputs",
                    status="research_needed",
                ),
                "excluded_reason": "status_research_needed",
            }
        ],
        "included_model_outputs": [
            _row(
                "financial_stress_composite",
                "financial_stress_status",
                "Financial stress status",
                interpretation_boundary="Financial stress score is pressure temperature.",
            ),
        ],
        "excluded_model_outputs": [],
        "portfolio_context_policy": {
            "mode": "compact_summary_only",
            "holdings_line_items_allowed": False,
        },
        "privacy_policy": {
            "returns_sanitized_evidence_rows_only": True,
            "returns_holdings_line_items": False,
            "returns_provider_payloads": False,
            "returns_credentials": False,
        },
        "search_policy": {"search_enabled": False},
        "model_destination": {
            "chat_enabled": False,
            "deepseek_enabled": False,
            "tavily_enabled": False,
            "destination": "local_preview_only",
        },
        "persistence_policy": {
            "saves_manifest": False,
            "saves_prompt_text": False,
            "writes_chat_history": False,
        },
        "risk_boundaries": ["Reference evidence only."],
        "source_summary": {"total_evidence_rows": 2},
    }


def _row(
    module,
    metric_key,
    display_name,
    *,
    status="ok",
    source_badge="derived",
    freshness_status="fresh",
    interpretation_boundary="Reference context only.",
):
    return {
        "row_id": f"{module}:{metric_key}",
        "module": module,
        "metric_key": metric_key,
        "display_name": display_name,
        "value": display_name,
        "value_text": display_name,
        "unit": None,
        "status": status,
        "source": "fixture",
        "source_badge": source_badge,
        "source_series": metric_key.upper(),
        "observation_date": "2026-06-15",
        "generated_at": "2026-06-15T00:00:00+00:00",
        "freshness_status": freshness_status,
        "missing_reason": None,
        "interpretation_hint": "fixture context",
        "interpretation_boundary": interpretation_boundary,
        "ai_context_allowed": status == "ok",
    }


def _write_minimal_reports(tmp_path: Path) -> None:
    generated_at = "2026-06-15T00:00:00+00:00"

    def metric(value, source="FRED", badge="official"):
        return {
            "value": value,
            "status": "ok",
            "source": source,
            "source_badge": badge,
            "observation_date": "2026-06-15",
            "freshness_status": "fresh",
        }

    (tmp_path / "market_snapshot.json").write_text(
        json.dumps(
            {
                "generated_at": generated_at,
                "status": "ok",
                "high_yield_spread": metric(3.4),
                "investment_grade_spread": metric(1.2),
                "vix": metric(18.2, source="CBOE"),
                "credit_stress_status": metric("watch"),
                "dgs10": metric(4.52),
                "dgs30": metric(4.83),
                "dfii10": metric(2.1),
                "t10yie": metric(2.35),
                "real_yield_pressure_status": metric("pressure"),
                "core_cpi_yoy": metric(3.1),
                "core_pce_yoy": metric(2.8),
                "ppiaco_yoy": metric(1.7),
                "unemployment_rate": metric(4.0),
                "initial_jobless_claims": metric(230000),
                "wti_30d_change": metric(-4.2, source="EIA"),
                "brent_30d_change": metric(-3.8, source="EIA"),
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "market_temperature.json").write_text(
        json.dumps({"generated_at": generated_at, "status": "watch"}),
        encoding="utf-8",
    )
    (tmp_path / "portfolio_snapshot.json").write_text(
        json.dumps(
            {
                "generated_at": generated_at,
                "status": "ok",
                "max_deviation_asset": {"value": "equity", "status": "ok"},
                "max_deviation_pp": {"value": 2.3, "status": "ok"},
                "equity_total_deviation_pp": {"value": 1.4, "status": "ok"},
                "cash_reserve_status": {"value": "available", "status": "ok"},
                "holdings_updated_at": {"value": "2026-06-15", "status": "ok"},
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "provider_health_check.json").write_text(
        json.dumps({"generated_at": generated_at, "overall_status": "ok"}),
        encoding="utf-8",
    )
