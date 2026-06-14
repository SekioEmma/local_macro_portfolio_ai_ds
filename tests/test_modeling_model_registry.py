from modeling.model_registry import (
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
    "macro_regime_review",
    "historical_validation",
}


def test_model_registry_registers_all_stage_models():
    registry = ModelRegistry()

    assert REQUIRED_MODEL_MODULES <= set(registry.module_keys())
    assert {
        "financial_stress_composite",
        "pullback_systemic_risk_checklist",
        "macro_regime_review",
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


def test_model_registry_and_audit_expected_keys_agree_for_d15_d19():
    registry = ModelRegistry()

    assert module_audits.MACRO_REGIME_REVIEW_METRIC_KEYS == set(
        registry.public_output_keys("macro_regime_review")
    )
    assert module_audits.HISTORICAL_VALIDATION_METRIC_KEYS == set(
        registry.public_output_keys("historical_validation")
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
