from modeling.metric_lookup import (
    D15_FORBIDDEN_PUBLIC_KEYS,
    D15_PUBLIC_OUTPUT_KEYS,
    D16_PUBLIC_OUTPUT_KEYS,
    D17_PUBLIC_OUTPUT_KEYS,
    D18_PUBLIC_OUTPUT_KEYS,
    D19_PUBLIC_OUTPUT_KEYS,
    D20_PUBLIC_OUTPUT_KEYS,
    MetricLookup,
)


def test_metric_lookup_registers_d15_public_fields_without_internal_scores():
    lookup = MetricLookup()
    public_keys = set(lookup.public_output_keys("macro_regime_review"))

    assert set(D15_PUBLIC_OUTPUT_KEYS) <= public_keys
    assert not (public_keys & set(D15_FORBIDDEN_PUBLIC_KEYS))
    assert lookup.require("macro_regime_label").role == "model_output"
    assert lookup.require("interpretation_boundary").interpretation_boundary_required is True


def test_metric_lookup_registers_d19_public_fields():
    lookup = MetricLookup()
    public_keys = set(lookup.public_output_keys("historical_validation"))

    assert set(D19_PUBLIC_OUTPUT_KEYS) <= public_keys
    assert lookup.require("historical_validation_status").evidence_group == "historical_validation"
    assert (
        lookup.require("historical_validation_validation_boundary")
        .interpretation_boundary_required
        is True
    )


def test_metric_lookup_registers_stage8_portfolio_exposure_public_fields():
    lookup = MetricLookup()
    public_keys = set(lookup.public_output_keys("portfolio_exposure_overlay"))

    assert set(D20_PUBLIC_OUTPUT_KEYS) <= public_keys
    assert lookup.require("portfolio_exposure_overlay_status").evidence_group == "portfolio_overlay"
    assert lookup.require("portfolio_exposure_overlay_status").trigger_policy == "cannot_trigger"
    assert lookup.require("portfolio_exposure_overlay_status").ai_context_policy == "compact_safe_only"
    assert (
        lookup.require("portfolio_exposure_interpretation_boundary")
        .interpretation_boundary_required
        is True
    )


def test_metric_lookup_registers_d16_public_fields():
    lookup = MetricLookup()
    public_keys = set(lookup.public_output_keys("scenario_stress"))

    assert set(D16_PUBLIC_OUTPUT_KEYS) <= public_keys
    assert lookup.require("scenario_stress_status").evidence_group == "scenario_stress"
    assert (
        lookup.require("scenario_stress_interpretation_boundary")
        .interpretation_boundary_required
        is True
    )


def test_metric_lookup_registers_d17_public_fields():
    lookup = MetricLookup()
    public_keys = set(lookup.public_output_keys("growth_inflation_macro_pack"))

    assert set(D17_PUBLIC_OUTPUT_KEYS) <= public_keys
    assert lookup.require("growth_macro_status").evidence_group == "growth_macro"
    assert lookup.require("growth_macro_status").trigger_policy == "confirmation_only"
    assert (
        lookup.require("stagflation_watch_interpretation_boundary")
        .interpretation_boundary_required
        is True
    )


def test_metric_lookup_registers_d18_public_fields_as_auxiliary_context():
    lookup = MetricLookup()
    public_keys = set(lookup.public_output_keys("valuation_equity_structure"))

    assert set(D18_PUBLIC_OUTPUT_KEYS) <= public_keys
    assert lookup.require("valuation_context_status").evidence_group == "valuation_earnings_breadth"
    assert lookup.require("valuation_context_status").trigger_policy == "cannot_trigger"
    assert lookup.require("equity_structure_status").status_policy == "auxiliary_only"
    assert (
        lookup.require("breadth_concentration_interpretation_boundary")
        .interpretation_boundary_required
        is True
    )


def test_metric_lookup_proxy_metrics_cannot_be_strong_triggers():
    lookup = MetricLookup()

    assert lookup.require("hyg_vs_lqd_30d").trigger_policy == "proxy_never_strong_trigger"
    assert lookup.require("spy_vs_rsp_30d").source_policy == "proxy_auxiliary_only"
    assert lookup.can_strong_trigger("hyg_vs_lqd_30d") is False
    assert lookup.can_strong_trigger("spy_vs_rsp_30d") is False


def test_metric_lookup_research_needed_and_insufficient_history_do_not_support_label():
    lookup = MetricLookup()

    assert lookup.require("earnings_revision").status_policy == "research_needed"
    assert lookup.require("eps_growth").trigger_policy == "cannot_trigger"
    assert lookup.can_support_label("earnings_revision") is False
    assert lookup.can_support_label("eps_growth") is False
    assert lookup.require("ism_manufacturing_pmi").status_policy == "research_needed"
    assert lookup.can_support_label("ism_manufacturing_pmi") is False
    assert lookup.get("unknown_insufficient_history_metric") is None
    assert lookup.can_support_label("unknown_insufficient_history_metric") is False


def test_metric_lookup_portfolio_overlay_cannot_determine_macro_regime():
    lookup = MetricLookup()
    portfolio_metrics = lookup.metrics_by_group("portfolio_overlay")

    assert {metric.metric_key for metric in portfolio_metrics} >= {
        "max_deviation_asset",
        "max_deviation_pp",
        "equity_total_deviation_pp",
    }
    assert all(metric.trigger_policy == "cannot_trigger" for metric in portfolio_metrics)
    assert all(lookup.can_support_label(metric.metric_key) is False for metric in portfolio_metrics)
