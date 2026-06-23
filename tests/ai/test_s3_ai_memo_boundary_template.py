from __future__ import annotations

import json
from pathlib import Path

from app_backend.services.ai_memo_renderer import (
    FORBIDDEN_GENERATED_OUTPUT_TERMS,
    MODEL_MODULE_LABELS,
    PRIVACY_FORBIDDEN_TERMS,
    render_ai_memo_preview,
    validate_ai_memo_preview,
)

_REPO_ROOT = Path(__file__).resolve().parents[2]


FORBIDDEN_SCENARIO_TOKENS = (
    "scenario_probability",
    "forecast_path",
    "expected_return",
    "portfolio_action",
    "trade_signal",
    "target_allocation",
)


def test_scenario_memo_uses_scenario_stress_matrix_label():
    preview = render_ai_memo_preview("scenario_review_memo", _scenario_manifest())

    body = _serialized(preview)
    assert preview.validator_result.passed is True
    assert "Scenario Stress Matrix" in body
    assert "D16 scenario stress" not in body
    assert any(
        "scenario_stress.scenario_stress_status" in section.source_context
        for section in preview.sections
    )


def test_scenario_metadata_appears_as_explanatory_context_only():
    preview = render_ai_memo_preview("scenario_review_memo", _scenario_manifest())
    body = _serialized(preview)

    assert preview.validator_result.passed is True
    for expected in (
        "credit_spread_widening",
        "support_band=elevated",
        "severity_band=moderate",
        "uncertainty_band=high",
        "oas_coverage_limited",
        "valuation_source_gate",
        "credit_conditions",
        "credit_spread_channel",
    ):
        assert expected in body
    for token in FORBIDDEN_SCENARIO_TOKENS:
        assert token not in body


def test_not_a_forecast_boundary_is_explicit_and_validator_safe():
    preview = render_ai_memo_preview("scenario_review_memo", _scenario_manifest())
    notice = _section(preview, "not_a_forecast_notice").content

    assert preview.validator_result.passed is True
    assert "not a forecast" in notice
    assert "not an event-odds model" in notice
    assert "not an action directive" in notice
    assert "return-estimation model" in notice


def test_excluded_scenario_rows_are_not_promoted():
    preview = render_ai_memo_preview(
        "scenario_review_memo",
        _scenario_manifest(included=False, excluded=True),
    )
    selected = _section(preview, "selected_scenario").content

    assert preview.validator_result.passed is True
    assert "selected scenario is not rendered" in selected
    assert "constraint=status_limited_evidence" in selected
    assert "scenario_name=credit_spread_widening" not in selected


def test_risk_review_memo_includes_scenario_boundary():
    preview = render_ai_memo_preview("risk_review_memo", _scenario_manifest())
    notes = _section(preview, "scenario_stress_notes").content

    assert preview.validator_result.passed is True
    assert "Scenario Stress Matrix" in notes
    assert "model-output scenario context only" in notes
    for token in FORBIDDEN_SCENARIO_TOKENS:
        assert token not in _serialized(preview)


def test_macro_risk_report_treats_scenario_stress_as_model_output():
    preview = render_ai_memo_preview("macro_risk_report", _scenario_manifest())
    model_summary = _section(preview, "D10_D19_model_summary").content
    evidence_summary = _section(preview, "evidence_table_snapshot_summary").content

    assert preview.validator_result.passed is True
    assert "Scenario Stress Matrix" in model_summary
    assert "Scenario Stress Matrix" not in evidence_summary


def test_forbidden_terms_and_privacy_flags_remain_blocked():
    preview = render_ai_memo_preview("scenario_review_memo", _scenario_manifest()).as_dict()
    preview["sections"][0]["content"] = "expected return"
    result = validate_ai_memo_preview(preview)
    assert result.passed is False
    assert "expected return" in result.blocked_terms

    preview = render_ai_memo_preview("scenario_review_memo", _scenario_manifest()).as_dict()
    preview["sections"][0]["content"] = "raw prompt"
    result = validate_ai_memo_preview(preview)
    assert result.passed is False
    assert "raw prompt" in result.privacy_findings

    preview = render_ai_memo_preview("scenario_review_memo", _scenario_manifest()).as_dict()
    preview["privacy_summary"]["external_model_called"] = True
    preview["privacy_summary"]["search_called"] = True
    preview["privacy_summary"]["saved_by_default"] = True
    result = validate_ai_memo_preview(preview)
    assert result.passed is False
    assert "external_model_called" in result.privacy_findings
    assert "search_called" in result.privacy_findings
    assert "saved_by_default" in result.privacy_findings


def test_no_endpoint_or_external_ai_surface_added():
    main_text = (_REPO_ROOT / "src/app_backend/main.py").read_text(encoding="utf-8")
    renderer_text = (_REPO_ROOT / "src/app_backend/services/ai_memo_renderer.py").read_text(
        encoding="utf-8"
    )

    assert "/api/chat" not in main_text
    assert "/api/ai/memo" not in main_text
    assert "/api/memo" not in main_text
    for token in (
        "deepseek",
        "tavily",
        "requests",
        "httpx",
        "live_fetch",
        "provider_live",
    ):
        assert token not in renderer_text.lower()


def test_human_readable_scenario_label_is_primary():
    assert MODEL_MODULE_LABELS["scenario_stress"] == "Scenario Stress Matrix (legacy: D16)"
    assert MODEL_MODULE_LABELS["scenario_stress"] != "D16 scenario stress"
    assert "target allocation" in FORBIDDEN_GENERATED_OUTPUT_TERMS
    assert "raw prompt" in PRIVACY_FORBIDDEN_TERMS


def _scenario_manifest(*, included: bool = True, excluded: bool = False):
    included_model_outputs = [_scenario_row()] if included else []
    excluded_model_outputs = [
        {
            **_scenario_row(),
            "status": "limited_evidence",
            "excluded_reason": "status_limited_evidence",
            "component_contributions": {"scenarios": []},
        }
    ] if excluded else []
    return {
        "generated_at": "2026-06-15T00:00:00+00:00",
        "included_facts": [
            {
                "module": "credit_stress",
                "metric_key": "high_yield_spread",
                "display_name": "High yield spread",
                "status": "ok",
                "source_badge": "official",
                "freshness_status": "fresh",
                "interpretation_boundary": "Reference context only.",
            }
        ],
        "excluded_facts": [],
        "included_model_outputs": included_model_outputs,
        "excluded_model_outputs": excluded_model_outputs,
        "risk_boundaries": ["Reference context only."],
        "privacy_policy": {"returns_sanitized_evidence_rows_only": True},
        "search_policy": {"search_enabled": False},
        "portfolio_context_policy": {"mode": "compact_summary_only"},
        "persistence_policy": {"saves_manifest": False},
        "source_summary": {"total_evidence_rows": 2},
    }


def _scenario_row():
    return {
        "module": "scenario_stress",
        "metric_key": "scenario_stress_status",
        "display_name": "Scenario stress status",
        "status": "ok",
        "source_badge": "derived",
        "freshness_status": "historical",
        "interpretation_boundary": (
            "Scenario stress is a hypothetical scenario matrix, not future market direction."
        ),
        "component_contributions": {
            "scenarios": [
                {
                    "scenario_name": "credit_spread_widening",
                    "scenario_status": "watch",
                    "support_band": "elevated",
                    "severity_band": "moderate",
                    "uncertainty_band": "high",
                    "affected_evidence_groups": ["credit_conditions", "funding_liquidity"],
                    "transmission_channels": ["credit_spread_channel", "funding_channel"],
                    "scenario_uncertainty_drivers": ["oas_coverage_limited"],
                    "scenario_missing_constraints": ["valuation_context_missing"],
                    "scenario_proxy_constraints": ["proxy_breadth_limited"],
                    "scenario_source_gate_constraints": ["valuation_source_gate"],
                    "scenario_refinement_boundary": "Explanation and uncertainty context only.",
                }
            ],
            "uses_model_registry": True,
            "uses_evidence_index": True,
        },
    }


def _section(preview, key):
    for section in preview.sections:
        if section.key == key:
            return section
    raise AssertionError(f"missing section {key!r}")


def _serialized(preview) -> str:
    return json.dumps(preview.as_dict(), sort_keys=True)
