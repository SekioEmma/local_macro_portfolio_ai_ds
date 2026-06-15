import json
from pathlib import Path

import pytest

from app_backend.schemas.ai_preview import (
    AIPreviewChatRequest,
    AIPreviewMemoRequest,
    AIPreviewReportRequest,
)
from app_backend.services import ai_context_service, ai_preview_service


def test_context_preview_returns_local_flags_and_counts(monkeypatch):
    monkeypatch.setattr(ai_context_service, "build_ai_context_manifest", _manifest_fixture)

    preview = ai_preview_service.build_context_preview()

    assert preview.mode == "local_preview"
    assert preview.model_destination["destination"] == "local_preview_only"
    assert preview.search_enabled is False
    assert preview.external_model_called is False
    assert preview.search_called is False
    assert preview.saved_by_default is False
    assert preview.included_fact_count == 2
    assert preview.excluded_fact_count == 1
    assert preview.included_model_output_count == 2
    assert preview.excluded_model_output_count == 1
    assert preview.context_stats["source_summary"]["total_evidence_rows"] == 6
    assert preview.last_generated_at == "2026-06-15T00:00:00+00:00"


def test_context_preview_does_not_return_private_payloads(monkeypatch):
    monkeypatch.setattr(ai_context_service, "build_ai_context_manifest", _manifest_fixture)

    body = preview_text(ai_preview_service.build_context_preview())

    assert "RAW_FUND" not in body
    assert "HOLDINGS_AMOUNT_MUST_NOT_LEAK" not in body
    assert "raw_provider_payload" not in body
    assert "sk-" not in body


def test_preview_chat_is_deterministic_and_fail_closed(monkeypatch):
    monkeypatch.setattr(ai_context_service, "build_ai_context_manifest", _manifest_fixture)
    request = AIPreviewChatRequest(
        question="Can you review the current macro context?",
        style="natural",
        context_mode="full_sanitized",
    )

    first = ai_preview_service.render_chat_preview(request)
    second = ai_preview_service.render_chat_preview(request)

    assert first == second
    assert first.mode == "local_preview"
    assert first.not_sent_to_external_model is True
    assert first.privacy_summary.external_model_called is False
    assert first.privacy_summary.search_called is False
    assert first.privacy_summary.saved_by_default is False
    assert first.human_review_required is True
    assert first.validator_result.passed is True
    assert "Can you review" not in preview_text(first)


def test_preview_chat_context_modes_limit_support(monkeypatch):
    monkeypatch.setattr(ai_context_service, "build_ai_context_manifest", _manifest_fixture)

    facts_only = ai_preview_service.render_chat_preview(
        AIPreviewChatRequest(
            question="facts",
            style="structured",
            context_mode="facts_only",
        )
    )
    model_outputs_only = ai_preview_service.render_chat_preview(
        AIPreviewChatRequest(
            question="models",
            style="structured",
            context_mode="model_outputs_only",
        )
    )

    facts_text = _section(facts_only, "model_output_summary").content
    model_text = _section(model_outputs_only, "evidence_summary").content

    assert "Not used as support" in facts_text
    assert "Financial stress status" not in facts_text
    assert "Not used as support" in model_text
    assert "High yield spread" not in model_text


def test_preview_chat_excluded_context_is_constraints_only(monkeypatch):
    monkeypatch.setattr(ai_context_service, "build_ai_context_manifest", _manifest_fixture)

    preview = ai_preview_service.render_chat_preview(
        AIPreviewChatRequest(question="constraints")
    )
    section = _section(preview, "missing_or_excluded_constraints")

    assert "Excluded context constraints" in section.content
    assert "constraint=status_research_needed" in section.content
    assert "Valuation missing inputs" in section.content
    assert "valuation_equity_structure.valuation_missing_inputs" in section.source_context


def test_preview_memo_and_report_use_stage_9_1_renderer(monkeypatch):
    monkeypatch.setattr(ai_context_service, "build_ai_context_manifest", _manifest_fixture)

    memo = ai_preview_service.render_memo_preview(
        AIPreviewMemoRequest(memo_type="risk_review_memo")
    )
    report = ai_preview_service.render_report_preview(
        AIPreviewReportRequest(report_type="macro_risk_report")
    )

    assert memo.mode == "local_preview"
    assert memo.memo_type == "risk_review_memo"
    assert memo.not_sent_to_external_model is True
    assert memo.human_review_required is True
    assert memo.validator_result.passed is True
    assert report.mode == "local_preview"
    assert report.memo_type == "macro_risk_report"
    assert report.not_sent_to_external_model is True
    assert report.human_review_required is True
    assert report.validator_result.passed is True


@pytest.mark.parametrize(
    "blocked_term",
    [
        "buy",
        "sell",
        "add position",
        "reduce position",
        "clear position",
        "hedge",
        "rebalance",
        "target allocation",
        "target weight",
        "ideal allocation",
        "expected return",
        "predicted return",
        "future return",
        "market direction probability",
        "crash probability",
        "recession probability",
        "trade signal",
        "strategy return",
        "trading performance",
        "Sharpe",
        "de-risk",
        "rotate into",
        "overweight",
        "underweight",
        "guaranteed",
        "will rise",
        "will fall",
    ],
)
def test_preview_validator_blocks_forbidden_action_allocation_return_probability_fixtures(blocked_term):
    payload = _valid_preview_payload()
    payload["sections"][0]["content"] = blocked_term

    result = ai_preview_service.validate_ai_preview_payload(payload)

    assert result.passed is False
    assert blocked_term.lower() in result.blocked_terms


@pytest.mark.parametrize(
    "privacy_term",
    [
        "holdings line items",
        "account values",
        "position weights",
        "raw provider payload",
        "raw prompt",
        "API key",
        ".env",
        "data/private",
        "current_holdings.csv",
        "transaction history",
        "credentials",
    ],
)
def test_preview_validator_blocks_privacy_leakage_fixtures(privacy_term):
    payload = _valid_preview_payload()
    payload["sections"][0]["content"] = privacy_term

    result = ai_preview_service.validate_ai_preview_payload(payload)

    assert result.passed is False
    assert privacy_term.lower() in result.privacy_findings


def test_preview_service_does_not_import_external_adapters():
    source = Path("src/app_backend/services/ai_preview_service.py").read_text(
        encoding="utf-8"
    )

    assert "analyst_memo_provider" not in source
    assert "deepseek_client" not in source
    assert "tavily" not in source.lower()
    assert "storage_service" not in source


def preview_text(value) -> str:
    if hasattr(value, "model_dump"):
        payload = value.model_dump()
    elif hasattr(value, "dict"):
        payload = value.dict()
    else:
        payload = value
    return json.dumps(payload, sort_keys=True)


def _section(preview, section_key):
    for section in preview.sections:
        if section.key == section_key:
            return section
    raise AssertionError(f"missing section {section_key}")


def _valid_preview_payload():
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
        "validator_result": {"passed": True, "blocked_terms": [], "privacy_findings": []},
        "not_sent_to_external_model": True,
        "human_review_required": True,
        "interpretation_boundary": ai_preview_service.BOUNDARY_NOTICE,
    }


def _manifest_fixture():
    return {
        "generated_at": "2026-06-15T00:00:00+00:00",
        "included_facts": [
            _row(
                "credit_stress",
                "high_yield_spread",
                "High yield spread",
                source_badge="official",
                freshness_status="fresh",
            ),
            _row(
                "liquidity_funding_stress",
                "liquidity_funding_stress_status",
                "Liquidity funding stress status",
            ),
        ],
        "excluded_facts": [
            {
                **_row(
                    "valuation_equity_structure",
                    "valuation_missing_inputs",
                    "Valuation missing inputs",
                    status="research_needed",
                    freshness_status="missing",
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
            ),
            _row(
                "portfolio_exposure_overlay",
                "portfolio_exposure_overlay_status",
                "Portfolio exposure overlay status",
                interpretation_boundary="Stage 8 is a privacy-preserving explanatory layer.",
            ),
        ],
        "excluded_model_outputs": [
            {
                **_row(
                    "scenario_stress",
                    "scenario_stress_status",
                    "Scenario stress status",
                    status="limited_evidence",
                ),
                "excluded_reason": "status_limited_evidence",
            }
        ],
        "portfolio_context_policy": {
            "mode": "compact_summary_only",
            "holdings_line_items_allowed": False,
        },
        "privacy_policy": {
            "returns_sanitized_evidence_rows_only": True,
            "returns_holdings_line_items": False,
            "returns_provider_payloads": False,
        },
        "search_policy": {"search_enabled": False},
        "model_destination": {
            "chat_enabled": False,
            "deepseek_enabled": False,
            "tavily_enabled": False,
            "destination": "local_preview_only",
        },
        "persistence_policy": {"saves_manifest": False, "writes_chat_history": False},
        "risk_boundaries": ["Reference evidence only."],
        "source_summary": {"total_evidence_rows": 6},
    }


def _row(
    module,
    metric_key,
    display_name,
    *,
    status="ok",
    source_badge="derived",
    freshness_status="historical",
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
