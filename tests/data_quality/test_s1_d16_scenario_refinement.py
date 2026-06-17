import json

from data_quality import scenario_stress as d16
from modeling.metric_lookup import D16_PUBLIC_OUTPUT_KEYS


FORBIDDEN_OUTPUT_KEYS = {
    "scenario_probability",
    "forecast_path",
    "expected_return",
    "predicted_return",
    "future_return",
    "target_price",
    "portfolio_action",
    "trade_signal",
    "target_allocation",
}


def test_s1_public_contract_remains_unchanged_and_non_predictive():
    rows = d16.build_scenario_stress_rows([])
    keys = {row["metric_key"] for row in rows}
    serialized = json.dumps(rows, sort_keys=True).lower()

    assert keys == set(D16_PUBLIC_OUTPUT_KEYS)
    assert not (keys & FORBIDDEN_OUTPUT_KEYS)
    for term in FORBIDDEN_OUTPUT_KEYS:
        assert term not in serialized
    boundary = _by_key(rows, "scenario_stress_interpretation_boundary")["value"].lower()
    assert "hypothetical scenario matrix" in boundary
    assert "not a forecast" in boundary
    assert "event-odds" in boundary
    assert "allocation directive" in boundary
    assert "return estimate" in boundary


def test_s1_d13_reliability_and_divergence_affect_explanation_only():
    base = [
        _row("credit_stress", "high_yield_spread", value=550.0, status="pressure"),
    ]
    baseline = _scenario(base, "credit_spread_widening")
    refined = _scenario(
        [
            *base,
            _d13_row(
                "high_yield_spread_percentile",
                "high_yield_spread",
                reliability_band="low",
                reliability_drivers=["method_divergence"],
                divergence_band="material",
                method_agreement="mixed",
            ),
        ],
        "credit_spread_widening",
    )

    assert refined["severity_band"] == baseline["severity_band"]
    assert "high_yield_spread" in refined["supporting_evidence_keys"]
    assert "high_yield_spread_percentile" not in refined["supporting_evidence_keys"]
    assert any(
        "reliability_low" in driver
        for driver in refined["scenario_uncertainty_drivers"]
    )
    assert any(
        "method_divergence_material" in driver
        for driver in refined["scenario_uncertainty_drivers"]
    )
    assert refined["scenario_d13_reliability_context"]
    assert refined["scenario_d13_divergence_context"]
    assert "scenario_probability" not in json.dumps(refined, sort_keys=True).lower()


def test_s1_oas_below_gate_is_current_level_only_caveat_not_normalized_support():
    scenario = _scenario(
        [
            _row("credit_stress", "high_yield_spread", value=550.0, status="pressure"),
            _d13_row(
                "high_yield_spread_percentile",
                "high_yield_spread",
                status="insufficient_history",
                reliability_band="insufficient",
                divergence_band="not_available",
                history_coverage_status="below_exact_gate",
                provider_rebuild_status="provider_rebuild_limited",
                normalization_availability={
                    "current_level_available": True,
                    "percentile_available": False,
                    "zscore_available": False,
                    "robust_zscore_available": False,
                },
                substitution_policy="no_substitution",
                trigger_eligibility="not_eligible",
            ),
        ],
        "credit_spread_widening",
    )
    serialized = json.dumps(scenario, sort_keys=True)

    assert "high_yield_spread_percentile" not in scenario["supporting_evidence_keys"]
    assert any(
        "current_level_only_without_normalization" in item
        for item in scenario["scenario_missing_constraints"]
    )
    assert "high_yield_spread_normalization_below_exact_gate" in scenario[
        "scenario_source_gate_constraints"
    ]
    assert "high_yield_spread_provider_rebuild_limited" in scenario[
        "scenario_source_gate_constraints"
    ]
    assert scenario["scenario_d13_oas_coverage_context"]
    assert "BAA10Y" not in serialized


def test_s1_d17_d18_missing_gaps_remain_visible_and_do_not_reduce_uncertainty():
    scenario = _scenario(
        [
            _row(
                "market_stress_derived",
                "nasdaq100_drawdown_3m",
                value=-12.0,
                status="pressure",
                source_badge="derived",
            ),
            _row(
                "valuation_equity_structure",
                "valuation_missing_inputs",
                value="sp500_forward_pe_source_gate, sp500_erp_source_gate",
                status="research_needed",
                source_badge="derived",
            ),
            _row(
                "valuation_equity_structure",
                "earnings_missing_inputs",
                value="earnings_revision, eps_growth",
                status="research_needed",
                source_badge="derived",
            ),
            _row(
                "valuation_equity_structure",
                "breadth_concentration_missing_inputs",
                value="true_breadth, true_breadth_source_gate",
                status="research_needed",
                source_badge="derived",
            ),
        ],
        "ai_mega_cap_concentration_unwind",
    )

    assert scenario["uncertainty_band"] == "high"
    assert any(
        item.startswith("valuation_missing:sp500_forward_pe_source_gate")
        for item in scenario["scenario_missing_constraints"]
    )
    assert any(
        item.startswith("earnings_missing:earnings_revision")
        for item in scenario["scenario_missing_constraints"]
    )
    assert any(
        item.startswith("true_breadth_missing:true_breadth")
        for item in scenario["scenario_missing_constraints"]
    )
    assert "valuation_source_gate_missing" in scenario["scenario_source_gate_constraints"]
    assert scenario["scenario_d17_d18_gap_context"]


def test_s1_proxy_only_evidence_cannot_create_high_severity():
    scenario = _scenario(
        [
            _row(
                "breadth_concentration_proxy",
                "qqq_vs_spy_30d",
                value=-5.0,
                status="pressure",
                source_badge="proxy",
                trigger_eligibility="proxy_auxiliary_only",
            ),
            _row(
                "breadth_concentration_proxy",
                "spy_vs_rsp_30d",
                value=-3.0,
                status="pressure",
                source_badge="proxy",
                trigger_eligibility="proxy_auxiliary_only",
            ),
        ],
        "ai_mega_cap_concentration_unwind",
    )

    assert scenario["support_band"] != "strong"
    assert scenario["severity_band"] not in {"severe", "extreme"}
    assert scenario["uncertainty_band"] == "high"
    assert "qqq_vs_spy_30d_proxy_only" in scenario["scenario_proxy_constraints"]
    assert "valuation_earnings_true_breadth_gaps_explicit" in scenario[
        "scenario_proxy_constraints"
    ]


def test_s1_d19_replay_metadata_is_reference_only():
    scenario = _scenario(
        [
            _row("credit_stress", "high_yield_spread", value=550.0, status="pressure"),
            _row(
                "historical_validation",
                "historical_validation_status",
                value="limited_replay",
                status="ok",
                source_badge="derived",
                component_contributions={
                    "d19_v1_replay_summary": {
                        "available_event_count": 1,
                        "limited_replay_event_count": 2,
                        "insufficient_history_event_count": 3,
                        "boundary_violation_count": 0,
                    },
                    "d19_v1_replay_rows": [
                        {"event_id": "sample", "validation_status": "limited"}
                    ],
                },
            ),
        ],
        "credit_spread_widening",
    )
    serialized = json.dumps(scenario, sort_keys=True).lower()

    assert scenario["scenario_d19_reference_context"]["reference_note"] == (
        "historical_replay_reference_available"
    )
    for term in (
        "prediction accuracy",
        "backtest",
        "strategy performance",
        "scenario_probability",
        "expected_return",
    ):
        assert term not in serialized


def test_s1_portfolio_overlay_cannot_change_scenario_severity_or_create_support():
    base_rows = [
        _row("credit_stress", "high_yield_spread", value=550.0, status="pressure"),
    ]
    baseline = _scenario(base_rows, "credit_spread_widening")
    refined = _scenario(
        [
            *base_rows,
            _row(
                "portfolio_exposure_overlay",
                "portfolio_exposure_overlay_status",
                value="pressure",
                status="pressure",
                source_badge="derived",
            ),
        ],
        "credit_spread_widening",
    )
    serialized = json.dumps(refined, sort_keys=True).lower()

    assert refined["severity_band"] == baseline["severity_band"]
    assert refined["supporting_evidence_keys"] == baseline["supporting_evidence_keys"]
    assert "portfolio_action" not in serialized


def test_s1_ai_context_rows_remain_model_output_with_refined_metadata():
    rows = d16.build_scenario_stress_rows(
        [
            _row("credit_stress", "high_yield_spread", value=550.0, status="pressure"),
            _d13_row(
                "high_yield_spread_percentile",
                "high_yield_spread",
                reliability_band="low",
                divergence_band="material",
            ),
        ]
    )

    status = _by_key(rows, "scenario_stress_status")
    scenario = status["component_contributions"]["scenarios"][2]
    assert status["metric_key"] == "scenario_stress_status"
    assert status["ai_context_tier"] == "model_output"
    assert "scenario_uncertainty_drivers" in scenario
    assert status["source_badge"] == "derived"


def _scenario(rows, scenario_name):
    summary = d16.build_scenario_stress_summary(rows)
    return next(
        item for item in summary["scenarios"] if item["scenario_name"] == scenario_name
    )


def _row(
    module,
    metric_key,
    *,
    value,
    status="ok",
    source_badge="official",
    trigger_eligibility="reference_review_only",
    component_contributions=None,
):
    return {
        "row_id": f"{module}:{metric_key}",
        "module": module,
        "metric_key": metric_key,
        "display_name": metric_key,
        "value": value,
        "value_text": str(value),
        "unit": None,
        "status": status,
        "source": "local_rules" if source_badge == "derived" else "test_source",
        "source_badge": source_badge,
        "source_series": metric_key.upper(),
        "observation_date": "2026-01-01",
        "generated_at": "2026-01-01T00:00:00+00:00",
        "freshness_status": "historical",
        "missing_reason": None,
        "interpretation_hint": "Reference review only.",
        "interpretation_boundary": "Reference review only.",
        "ai_context_allowed": True,
        "trigger_eligibility": trigger_eligibility,
        "component_contributions": component_contributions or {},
    }


def _d13_row(
    metric_key,
    source_metric_key,
    *,
    status="ok",
    reliability_band="high",
    reliability_drivers=None,
    divergence_band="none",
    method_agreement="all_available_aligned",
    history_coverage_status="sufficient",
    provider_rebuild_status="not_needed",
    normalization_availability=None,
    substitution_policy="not_applicable",
    trigger_eligibility="hard_trigger_allowed",
):
    normalization = normalization_availability or {
        "current_level_available": True,
        "percentile_available": True,
        "zscore_available": True,
        "robust_zscore_available": True,
    }
    component_contributions = {
        "reliability_band": reliability_band,
        "reliability_drivers": reliability_drivers or [],
        "divergence_band": divergence_band,
        "method_agreement": method_agreement,
        "history_coverage_status": history_coverage_status,
        "provider_rebuild_status": provider_rebuild_status,
        "normalization_availability": normalization,
        "substitution_policy": substitution_policy,
        "trigger_eligibility": trigger_eligibility,
    }
    return {
        **_row(
            "historical_risk_percentile",
            metric_key,
            value=1.0 if status == "ok" else None,
            status=status,
            source_badge="derived",
            trigger_eligibility=trigger_eligibility,
            component_contributions=component_contributions,
        ),
        "source_metric_key": source_metric_key,
        "reliability_band": reliability_band,
        "reliability_drivers": reliability_drivers or [],
        "divergence_band": divergence_band,
        "method_agreement": method_agreement,
        "history_coverage_status": history_coverage_status,
        "provider_rebuild_status": provider_rebuild_status,
        "normalization_availability": normalization,
        "substitution_policy": substitution_policy,
    }


def _by_key(rows, metric_key):
    return {row["metric_key"]: row for row in rows}[metric_key]
