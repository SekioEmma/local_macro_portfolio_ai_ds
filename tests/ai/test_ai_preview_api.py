
from fastapi.testclient import TestClient

from app_backend.main import app
from app_backend.services import ai_context_service


def test_context_preview_api_returns_local_preview_flags(monkeypatch):
    monkeypatch.setattr(ai_context_service, "build_ai_context_manifest", _manifest_fixture)

    response = TestClient(app).get("/api/ai/context-preview")

    assert response.status_code == 200
    data = response.json()
    assert data["mode"] == "local_preview"
    assert data["model_destination"]["destination"] == "local_preview_only"
    assert data["search_enabled"] is False
    assert data["external_model_called"] is False
    assert data["search_called"] is False
    assert data["saved_by_default"] is False
    assert data["included_fact_count"] == 1
    assert data["included_model_output_count"] == 1
    assert data["privacy_policy"]["returns_holdings_line_items"] is False


def test_context_preview_api_does_not_leak_private_payloads(monkeypatch):
    monkeypatch.setattr(ai_context_service, "build_ai_context_manifest", _manifest_fixture)

    body = TestClient(app).get("/api/ai/context-preview").text

    assert "RAW_FUND" not in body
    assert "HOLDINGS_AMOUNT_MUST_NOT_LEAK" not in body
    assert "raw_provider_payload" not in body
    assert "current_holdings.csv" not in body


def test_preview_chat_api_returns_deterministic_local_output(monkeypatch):
    monkeypatch.setattr(ai_context_service, "build_ai_context_manifest", _manifest_fixture)
    client = TestClient(app)
    request = {
        "question": "Please review the current context.",
        "style": "structured",
        "context_mode": "full_sanitized",
    }

    first = client.post("/api/ai/preview-chat", json=request)
    second = client.post("/api/ai/preview-chat", json=request)

    assert first.status_code == 200
    assert first.json() == second.json()
    data = first.json()
    assert data["mode"] == "local_preview"
    assert data["not_sent_to_external_model"] is True
    assert data["privacy_summary"]["external_model_called"] is False
    assert data["privacy_summary"]["search_called"] is False
    assert data["privacy_summary"]["saved_by_default"] is False
    assert data["validator_result"]["passed"] is True
    assert "Please review" not in first.text


def test_preview_chat_api_context_modes_do_not_upgrade_non_selected_context(monkeypatch):
    monkeypatch.setattr(ai_context_service, "build_ai_context_manifest", _manifest_fixture)
    client = TestClient(app)

    facts_only = client.post(
        "/api/ai/preview-chat",
        json={
            "question": "facts",
            "style": "structured",
            "context_mode": "facts_only",
        },
    ).json()
    models_only = client.post(
        "/api/ai/preview-chat",
        json={
            "question": "models",
            "style": "structured",
            "context_mode": "model_outputs_only",
        },
    ).json()

    assert "Financial stress status" not in _section(facts_only, "model_output_summary")["content"]
    assert "High yield spread" not in _section(models_only, "evidence_summary")["content"]


def test_preview_memo_and_report_api_use_local_renderer(monkeypatch):
    monkeypatch.setattr(ai_context_service, "build_ai_context_manifest", _manifest_fixture)
    client = TestClient(app)

    memo = client.post(
        "/api/ai/preview-memo",
        json={"memo_type": "daily_review_memo", "style": "concise"},
    )
    report = client.post(
        "/api/ai/preview-report",
        json={"report_type": "evidence_audit_report", "style": "outline"},
    )

    assert memo.status_code == 200
    assert memo.json()["mode"] == "local_preview"
    assert memo.json()["not_sent_to_external_model"] is True
    assert memo.json()["human_review_required"] is True
    assert memo.json()["validator_result"]["passed"] is True
    assert report.status_code == 200
    assert report.json()["mode"] == "local_preview"
    assert report.json()["not_sent_to_external_model"] is True
    assert report.json()["human_review_required"] is True
    assert report.json()["validator_result"]["passed"] is True


def test_stage_9_2_does_not_add_forbidden_preview_routes():
    route_paths = {route.path for route in app.routes}

    assert "/api/chat" not in route_paths
    assert "/api/search" not in route_paths
    assert "/api/ai/preview-save" not in route_paths
    assert "/api/ai/preview-favorite" not in route_paths
    assert "/api/ai/report-save" not in route_paths


def test_preview_endpoints_do_not_return_raw_prompt(monkeypatch):
    monkeypatch.setattr(ai_context_service, "build_ai_context_manifest", _manifest_fixture)

    response = TestClient(app).post(
        "/api/ai/preview-chat",
        json={
            "question": "RAW_PROMPT_MUST_NOT_RETURN",
            "style": "natural",
            "context_mode": "full_sanitized",
        },
    )

    assert response.status_code == 200
    assert "RAW_PROMPT_MUST_NOT_RETURN" not in response.text
    assert response.json()["privacy_summary"]["uses_raw_prompts"] is False


def _section(payload, section_key):
    for section in payload["sections"]:
        if section["key"] == section_key:
            return section
    raise AssertionError(f"missing section {section_key}")


def _manifest_fixture():
    return {
        "generated_at": "2026-06-15T00:00:00+00:00",
        "included_facts": [
            _row(
                "credit_stress",
                "high_yield_spread",
                "High yield spread",
                source_badge="official",
            )
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
                interpretation_boundary="Financial stress score is pressure temperature, not prediction.",
            )
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
        "source_summary": {"total_evidence_rows": 3},
    }


def _row(
    module,
    metric_key,
    display_name,
    *,
    status="ok",
    source_badge="derived",
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
        "freshness_status": "fresh",
        "missing_reason": None,
        "interpretation_hint": "fixture context",
        "interpretation_boundary": interpretation_boundary,
        "ai_context_allowed": status == "ok",
    }
