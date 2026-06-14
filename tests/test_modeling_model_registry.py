from modeling.model_registry import (
    D16_FORBIDDEN_TERMS,
    D17_FORBIDDEN_TERMS,
    D18_FORBIDDEN_TERMS,
    D19_FORBIDDEN_TERMS,
    FORBIDDEN_PUBLIC_OUTPUT_KEYS,
    ModelRegistry,
)
from modeling.model_output import ModelOutput
from audit_sections import module_audits


REQUIRED_MODEL_MODULES = {
    "financial_stress_composite",
    "pullback_systemic_risk_checklist",
    "historical_risk_percentile",
    "liquidity_funding_stress",
    "growth_inflation_macro_pack",
    "valuation_equity_structure",
    "macro_regime_review",
    "scenario_stress",
    "historical_validation",
}


def test_model_registry_registers_all_stage_models():
    registry = ModelRegistry()

    assert REQUIRED_MODEL_MODULES <= set(registry.module_keys())
    assert {
        "financial_stress_composite",
        "pullback_systemic_risk_checklist",
        "macro_regime_review",
        "scenario_stress",
        "historical_validation",
    } <= registry.model_output_module_keys()


def test_model_registry_public_keys_boundaries_and_policies_are_present():
    registry = ModelRegistry()

    for registration in registry.all():
        assert registration.public_output_keys
        assert registration.interpretation_boundary
        assert registration.forbidden_language_policy
        assert registration.audit_policy
        assert registration.frontend_registry_policy


def test_model_registry_d15_public_keys_exclude_forbidden_fields():
    registry = ModelRegistry()
    keys = set(registry.public_output_keys("macro_regime_review"))

    assert "macro_regime_label" in keys
    assert not (keys & set(FORBIDDEN_PUBLIC_OUTPUT_KEYS))
    assert "macro_regime_score" not in keys
    assert "support_score_internal" not in keys
    assert "group_score_internal" not in keys


def test_model_registry_d19_public_keys_exclude_forbidden_backtest_terms():
    registry = ModelRegistry()
    keys = set(registry.public_output_keys("historical_validation"))
    text = " ".join(sorted(keys)).lower()

    assert "historical_validation_status" in keys
    for term in D19_FORBIDDEN_TERMS:
        assert term not in text


def test_model_registry_d16_public_keys_exclude_forbidden_terms():
    registry = ModelRegistry()
    keys = set(registry.public_output_keys("scenario_stress"))
    text = " ".join(sorted(keys)).lower()

    assert "scenario_stress_status" in keys
    assert "scenario_stress_interpretation_boundary" in keys
    assert not (keys & set(FORBIDDEN_PUBLIC_OUTPUT_KEYS))
    for term in D16_FORBIDDEN_TERMS:
        assert term not in text


def test_model_registry_d17_public_keys_exclude_forbidden_terms():
    registry = ModelRegistry()
    keys = set(registry.public_output_keys("growth_inflation_macro_pack"))
    text = " ".join(sorted(keys)).lower()

    assert "growth_macro_status" in keys
    assert "stagflation_watch_status" in keys
    assert not (keys & set(FORBIDDEN_PUBLIC_OUTPUT_KEYS))
    for term in D17_FORBIDDEN_TERMS:
        assert term not in text


def test_model_registry_d18_public_keys_exclude_forbidden_terms():
    registry = ModelRegistry()
    keys = set(registry.public_output_keys("valuation_equity_structure"))
    text = " ".join(sorted(keys)).lower()

    assert "valuation_context_status" in keys
    assert "breadth_concentration_context_status" in keys
    assert not (keys & set(FORBIDDEN_PUBLIC_OUTPUT_KEYS))
    for term in D18_FORBIDDEN_TERMS:
        assert term not in text


def test_model_registry_and_audit_expected_keys_agree_for_d15_d16_d17_d19():
    registry = ModelRegistry()

    assert module_audits.MACRO_REGIME_REVIEW_METRIC_KEYS == set(
        registry.public_output_keys("macro_regime_review")
    )
    assert module_audits.HISTORICAL_VALIDATION_METRIC_KEYS == set(
        registry.public_output_keys("historical_validation")
    )
    assert module_audits.SCENARIO_STRESS_METRIC_KEYS == set(
        registry.public_output_keys("scenario_stress")
    )
    assert module_audits.GROWTH_INFLATION_MACRO_PACK_METRIC_KEYS == set(
        registry.public_output_keys("growth_inflation_macro_pack")
    )
    assert module_audits.VALUATION_EQUITY_STRUCTURE_METRIC_KEYS == set(
        registry.public_output_keys("valuation_equity_structure")
    )


def test_model_output_helper_builds_compatible_metric_payload():
    output = ModelOutput(
        model_key="test_model_v0",
        module_key="test_model",
        metric_key="test_metric",
        value="ok",
        value_text="ok",
        status="ok",
        source_badge="derived",
        freshness_status="historical",
        interpretation_boundary="Reference review only.",
        component_contributions={"source": "test"},
    )

    payload = output.to_metric_payload(display_name="Test metric")

    assert payload["metric_key"] == "test_metric"
    assert payload["display_name"] == "Test metric"
    assert payload["source_badge"] == "derived"
    assert payload["interpretation_boundary"] == "Reference review only."
    assert payload["ai_context_tier"] == "model_output"
