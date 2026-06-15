import json

import pytest

from app_backend.services.ai_memo_renderer import (
    MEMO_SECTION_KEYS,
    NO_ELIGIBLE_CONTEXT,
    render_ai_memo_preview,
    render_all_ai_memo_previews,
    validate_ai_memo_preview,
)


def test_renderer_returns_deterministic_daily_review_memo():
    manifest = _manifest_fixture()

    first = render_ai_memo_preview("daily_review_memo", manifest).as_dict()
    second = render_ai_memo_preview("daily_review_memo", manifest).as_dict()

    assert first == second
    assert first["memo_type"] == "daily_review_memo"
    assert first["mode"] == "local_deterministic_template"
    assert first["validator_result"]["passed"] is True
    assert first["human_review_required"] is True
    assert first["context_used_summary"] == {
        "included_fact_count": 2,
        "excluded_fact_count": 1,
        "included_model_output_count": 7,
        "excluded_model_output_count": 1,
    }


def test_renderer_returns_required_sections_for_each_memo_type():
    previews = render_all_ai_memo_previews(_manifest_fixture())

    assert {preview.memo_type for preview in previews} == set(MEMO_SECTION_KEYS)
    for preview in previews:
        assert [section.key for section in preview.sections] == MEMO_SECTION_KEYS[preview.memo_type]
        assert preview.human_review_required is True
        assert preview.validator_result.passed is True


def test_renderer_uses_included_facts_as_evidence_summary():
    preview = render_ai_memo_preview("daily_review_memo", _manifest_fixture())
    section = _section(preview, "evidence_summary")

    assert "High yield spread" in section.content
    assert "source=official" in section.content
    assert "freshness=fresh" in section.content
    assert "credit_stress.high_yield_spread" in section.source_context


def test_renderer_uses_excluded_context_only_as_constraints():
    preview = render_ai_memo_preview("daily_review_memo", _manifest_fixture())
    section = _section(preview, "missing_or_excluded_constraints")

    assert "Excluded context constraints" in section.content
    assert "constraint=status_research_needed" in section.content
    assert "valuation_equity_structure.valuation_missing_inputs" in section.source_context


def test_renderer_uses_included_model_outputs_as_model_context():
    preview = render_ai_memo_preview("risk_review_memo", _manifest_fixture())
    section = _section(preview, "financial_stress_context")

    assert "D10 financial stress" in section.content
    assert "financial_stress_composite.financial_stress_status" in section.source_context


def test_renderer_uses_excluded_model_outputs_only_as_constraints():
    preview = render_ai_memo_preview("macro_risk_report", _manifest_fixture())
    section = _section(preview, "missing_data_and_research_needed")

    assert "scenario_stress.scenario_stress_status" in section.source_context
    assert "constraint=status_limited_evidence" in section.content


@pytest.mark.parametrize(
    ("memo_type", "section_key", "expected"),
    [
        ("daily_review_memo", "interpretation_boundaries", "Macro regime review is current evidence review"),
        ("scenario_review_memo", "not_a_forecast_notice", "D16 remains a scenario matrix"),
        ("risk_review_memo", "current_macro_state", "D17 growth/inflation context"),
        ("macro_risk_report", "D10_D19_model_summary", "D18 valuation/equity structure"),
        ("macro_risk_report", "D10_D19_model_summary", "D19 historical validation"),
        ("portfolio_overlay_review", "exposure_channel_summary", "Stage 8 portfolio exposure overlay"),
    ],
)
def test_renderer_preserves_model_boundary_notices(memo_type, section_key, expected):
    preview = render_ai_memo_preview(memo_type, _manifest_fixture())

    assert expected in _section(preview, section_key).content


def test_portfolio_overlay_review_contains_no_private_portfolio_details():
    preview = render_ai_memo_preview("portfolio_overlay_review", _manifest_fixture())
    text = _preview_text(preview)

    assert "HOLDINGS_AMOUNT_MUST_NOT_LEAK" not in text
    assert "RAW_FUND" not in text
    assert "account values" not in text.lower()
    assert "position weights" not in text.lower()
    assert "target allocation" not in text.lower()
    assert "position-level output" in text
    assert preview.privacy_summary.external_model_called is False
    assert preview.privacy_summary.search_called is False
    assert preview.privacy_summary.saved_by_default is False


def test_generated_memo_fixture_passes_validator():
    preview = render_ai_memo_preview("macro_risk_report", _manifest_fixture())

    result = validate_ai_memo_preview(preview)

    assert result.passed is True
    assert result.blocked_terms == []
    assert result.privacy_findings == []


def test_missing_eligible_context_uses_explicit_no_context_wording():
    manifest = {
        "generated_at": "2026-06-15T00:00:00+00:00",
        "included_facts": [],
        "excluded_facts": [],
        "included_model_outputs": [],
        "excluded_model_outputs": [],
        "risk_boundaries": [],
        "privacy_policy": {},
        "search_policy": {},
        "portfolio_context_policy": {},
        "persistence_policy": {},
        "source_summary": {},
    }

    preview = render_ai_memo_preview("risk_review_memo", manifest)

    assert NO_ELIGIBLE_CONTEXT in _section(preview, "financial_stress_context").content
    assert NO_ELIGIBLE_CONTEXT in _section(preview, "missing_constraints").content
    assert preview.validator_result.passed is True


def test_d15_public_numeric_macro_regime_score_is_not_emitted():
    manifest = _manifest_fixture()
    manifest["included_model_outputs"].append(
        _row(
            "macro_regime_review",
            "macro_regime_score",
            "internal numeric score",
            interpretation_boundary="private internal score should remain excluded",
        )
    )

    preview = render_ai_memo_preview("daily_review_memo", manifest)

    assert "macro_regime_score" not in _preview_text(preview)


def _section(preview, section_key):
    for section in preview.sections:
        if section.key == section_key:
            return section
    raise AssertionError(f"missing section {section_key}")


def _preview_text(preview) -> str:
    return json.dumps(preview.as_dict(), sort_keys=True)


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
                interpretation_boundary="Reference evidence only, not allocation guidance.",
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
                "pullback_systemic_risk_checklist",
                "pullback_classification",
                "Pullback classification",
                interpretation_boundary="Pullback checklist is risk review, not forecast.",
            ),
            _row(
                "macro_regime_review",
                "macro_regime_label",
                "Macro regime label",
                interpretation_boundary="Macro regime review is current evidence review, not future market direction.",
            ),
            _row(
                "growth_inflation_macro_pack",
                "growth_macro_status",
                "Growth macro status",
                interpretation_boundary="D17 is growth/inflation context, not a recession call.",
            ),
            _row(
                "valuation_equity_structure",
                "valuation_context_status",
                "Valuation context status",
                interpretation_boundary="D18 is research/proxy context, not timing model phrasing.",
            ),
            _row(
                "historical_validation",
                "historical_validation_status",
                "Historical validation status",
                interpretation_boundary="D19 is historical replay and boundary validation.",
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
                    interpretation_boundary="D16 remains a scenario matrix.",
                ),
                "excluded_reason": "status_limited_evidence",
            }
        ],
        "portfolio_context_policy": {"mode": "compact_summary_only"},
        "privacy_policy": {"returns_sanitized_evidence_rows_only": True},
        "search_policy": {"search_enabled": False},
        "persistence_policy": {"saves_manifest": False},
        "risk_boundaries": [
            "Macro regime review is current evidence review, not future market direction.",
            "Scenario stress is a hypothetical scenario matrix, not future market direction.",
            "Growth/inflation context is not a recession call.",
            "Valuation/equity structure is research/proxy context.",
            "Historical validation is event-window replay.",
            "Portfolio exposure overlay uses sanitized compact context only.",
        ],
        "source_summary": {
            "total_evidence_rows": 10,
            "source_badge_distribution": {"derived": 7, "official": 3},
        },
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
