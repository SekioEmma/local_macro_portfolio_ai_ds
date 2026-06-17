"""
S2 Scenario Stress Matrix Explanation Contract / Golden Integration.

Locks explanation metadata contracts, forbidden output language, D13/D17/D18/D19
context boundaries, and golden/AI context/memo integration for Scenario Stress
Matrix (legacy: D16).

Does not change financial model semantics, support/severity/uncertainty
calculation, production code, frontend, endpoints, or external AI.
"""

import json
import socket
from types import SimpleNamespace

import pytest

from app_backend.schemas.responses import DashboardEvidenceRow
from app_backend.services import ai_context_service
from app_backend.services import dashboard_service
from app_backend.services.ai_memo_renderer import (
    render_ai_memo_preview,
    validate_ai_memo_preview,
)
from data_quality import scenario_stress as d16
from modeling.metric_lookup import D16_PUBLIC_OUTPUT_KEYS
from modeling.model_registry import ModelRegistry


MODEL_REGISTRY = ModelRegistry()

EXPECTED_PUBLIC_KEYS = set(D16_PUBLIC_OUTPUT_KEYS)

SCENARIO_NAMES = {
    "high_rates_stay_high",
    "inflation_rebound",
    "credit_spread_widening",
    "liquidity_funding_squeeze",
    "growth_slowdown",
    "stagflation_pressure",
    "ai_mega_cap_concentration_unwind",
}

S1_SCENARIO_METADATA_FIELDS = {
    "scenario_name": str,
    "scenario_status": str,
    "input_evidence_groups": list,
    "affected_evidence_groups": list,
    "transmission_channels": list,
    "support_band": str,
    "severity_band": str,
    "uncertainty_band": str,
    "supporting_evidence_keys": list,
    "missing_inputs": list,
    "blocked_inputs": list,
    "proxy_constraints": list,
    "scenario_uncertainty_drivers": list,
    "scenario_missing_constraints": list,
    "scenario_proxy_constraints": list,
    "scenario_source_gate_constraints": list,
    "scenario_d13_reliability_context": list,
    "scenario_d13_divergence_context": list,
    "scenario_d13_oas_coverage_context": list,
    "scenario_d17_d18_gap_context": list,
    "scenario_d19_reference_context": dict,
    "scenario_refinement_boundary": str,
    "interpretation_boundary": str,
}

FORBIDDEN_TERMS = {
    "scenario_probability",
    "forecast_path",
    "expected_return",
    "predicted_return",
    "future_return",
    "target_price",
    "portfolio_action",
    "trade_signal",
    "target_allocation",
    "crash_probability",
    "recession_probability",
    "market_direction_probability",
    "buy",
    "sell",
    "add position",
    "reduce position",
    "clear position",
    "hedge",
    "rebalance",
    "overweight",
    "underweight",
    "will rise",
    "will fall",
}


# ---------------------------------------------------------------------------
# 4.1 Public output keys locked
# ---------------------------------------------------------------------------

class TestPublicOutputContract:
    def test_public_output_keys_exact_set(self):
        rows = d16.build_scenario_stress_rows([])
        keys = {row["metric_key"] for row in rows}
        assert keys == EXPECTED_PUBLIC_KEYS

    def test_module_key_constants(self):
        assert d16.MODULE_KEY == "scenario_stress"

    def test_model_key_constants(self):
        assert d16.MODEL_KEY == "scenario_stress_v0"
        assert d16.MODEL_VERSION == "scenario_stress_v0"

    def test_source_badge_is_derived(self):
        rows = d16.build_scenario_stress_rows([])
        assert all(row["source_badge"] == "derived" for row in rows)

    def test_scenario_count_is_seven(self):
        summary = d16.build_scenario_stress_summary([])
        assert summary["scenario_count"] == 7
        assert len(summary["scenarios"]) == 7
        assert {s["scenario_name"] for s in summary["scenarios"]} == SCENARIO_NAMES

    def test_registry_matches_module(self):
        registration = MODEL_REGISTRY.get("scenario_stress")
        assert registration is not None
        assert set(registration.public_output_keys) == EXPECTED_PUBLIC_KEYS


# ---------------------------------------------------------------------------
# 4.2 Scenario explanation metadata shape locked
# ---------------------------------------------------------------------------

class TestScenarioMetadataShape:
    def test_all_s1_metadata_fields_present_with_correct_types(self):
        summary = d16.build_scenario_stress_summary(_pressure_rows())
        for scenario in summary["scenarios"]:
            for field, expected_type in S1_SCENARIO_METADATA_FIELDS.items():
                assert field in scenario, f"missing field: {field} in {scenario['scenario_name']}"
                assert isinstance(scenario[field], expected_type), (
                    f"{field} in {scenario['scenario_name']}: "
                    f"expected {expected_type.__name__}, got {type(scenario[field]).__name__}"
                )

    def test_summary_top_level_shape(self):
        summary = d16.build_scenario_stress_summary([])
        for key in (
            "status",
            "row_status",
            "scenario_count",
            "scenarios",
            "primary_scenario",
            "affected_groups",
            "transmission_channels",
            "severity_band",
            "uncertainty_band",
            "supporting_evidence",
            "missing_inputs",
            "input_evidence",
            "as_of_date",
            "uses_model_registry",
            "uses_evidence_index",
        ):
            assert key in summary, f"missing top-level key: {key}"

    def test_refinement_boundary_text_present(self):
        summary = d16.build_scenario_stress_summary(_pressure_rows())
        for scenario in summary["scenarios"]:
            boundary = scenario["scenario_refinement_boundary"]
            assert "S1 refinement" in boundary
            assert "explanation" in boundary
            assert "uncertainty context only" in boundary


# ---------------------------------------------------------------------------
# 4.3 Forbidden output language
# ---------------------------------------------------------------------------

class TestForbiddenOutputLanguage:
    def test_no_forbidden_terms_in_rows(self):
        rows = d16.build_scenario_stress_rows(_pressure_rows())
        serialized = json.dumps(rows, sort_keys=True).lower()
        for term in FORBIDDEN_TERMS:
            assert term not in serialized, f"forbidden term found: {term}"

    def test_no_forbidden_terms_in_summary(self):
        summary = d16.build_scenario_stress_summary(_pressure_rows())
        serialized = json.dumps(summary, sort_keys=True).lower()
        for term in FORBIDDEN_TERMS:
            assert term not in serialized, f"forbidden term found: {term}"

    def test_boundary_text_contains_required_disclaimers(self):
        boundary = d16.BOUNDARY.lower()
        assert "not a forecast" in boundary
        assert "event-odds model" in boundary
        assert "allocation directive" in boundary
        assert "return estimate" in boundary

    def test_no_forbidden_keys_in_output(self):
        rows = d16.build_scenario_stress_rows([])
        keys = {row["metric_key"] for row in rows}
        forbidden_keys = {
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
        assert not (keys & forbidden_keys)


# ---------------------------------------------------------------------------
# 4.4 D13 reliability/OAS coverage context is explanation-only
# ---------------------------------------------------------------------------

class TestD13ReliabilityContext:
    def test_d13_reliability_does_not_change_severity(self):
        base = [_row("credit_stress", "high_yield_spread", 550.0, status="pressure")]
        baseline = _scenario(base, "credit_spread_widening")
        refined = _scenario(
            [
                *base,
                _d13_row(
                    "high_yield_spread_percentile",
                    "high_yield_spread",
                    reliability_band="low",
                    divergence_band="material",
                ),
            ],
            "credit_spread_widening",
        )
        assert refined["severity_band"] == baseline["severity_band"]
        assert refined["support_band"] == baseline["support_band"]

    def test_d13_reliability_adds_uncertainty_drivers(self):
        scenario = _scenario(
            [
                _row("credit_stress", "high_yield_spread", 550.0, status="pressure"),
                _d13_row(
                    "high_yield_spread_percentile",
                    "high_yield_spread",
                    reliability_band="low",
                    divergence_band="material",
                ),
            ],
            "credit_spread_widening",
        )
        assert any("reliability_low" in d for d in scenario["scenario_uncertainty_drivers"])
        assert any("method_divergence_material" in d for d in scenario["scenario_uncertainty_drivers"])
        assert scenario["scenario_d13_reliability_context"]
        assert scenario["scenario_d13_divergence_context"]

    def test_d13_oas_below_gate_surfaces_coverage_context(self):
        scenario = _scenario(
            [
                _row("credit_stress", "high_yield_spread", 550.0, status="pressure"),
                _d13_row(
                    "high_yield_spread_percentile",
                    "high_yield_spread",
                    status="insufficient_history",
                    reliability_band="insufficient",
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
        assert scenario["scenario_d13_oas_coverage_context"]
        assert any(
            "current_level_only_without_normalization" in c
            for c in scenario["scenario_missing_constraints"]
        )
        assert "high_yield_spread_normalization_below_exact_gate" in scenario[
            "scenario_source_gate_constraints"
        ]
        assert "BAA10Y" not in json.dumps(scenario, sort_keys=True)

    def test_d13_percentile_row_does_not_enter_supporting_evidence(self):
        scenario = _scenario(
            [
                _row("credit_stress", "high_yield_spread", 550.0, status="pressure"),
                _d13_row(
                    "high_yield_spread_percentile",
                    "high_yield_spread",
                    reliability_band="high",
                ),
            ],
            "credit_spread_widening",
        )
        assert "high_yield_spread" in scenario["supporting_evidence_keys"]
        assert "high_yield_spread_percentile" not in scenario["supporting_evidence_keys"]


# ---------------------------------------------------------------------------
# 4.5 D17/D18 missing/gap context remains visible
# ---------------------------------------------------------------------------

class TestD17D18GapContext:
    def test_valuation_earnings_breadth_gaps_visible(self):
        scenario = _scenario(
            [
                _row("market_stress_derived", "nasdaq100_drawdown_3m", -12.0, status="pressure", source_badge="derived"),
                _row("valuation_equity_structure", "valuation_missing_inputs", "sp500_forward_pe_source_gate", status="research_needed", source_badge="derived"),
                _row("valuation_equity_structure", "earnings_missing_inputs", "earnings_revision, eps_growth", status="research_needed", source_badge="derived"),
                _row("valuation_equity_structure", "breadth_concentration_missing_inputs", "true_breadth", status="research_needed", source_badge="derived"),
            ],
            "ai_mega_cap_concentration_unwind",
        )
        assert scenario["uncertainty_band"] == "high"
        assert scenario["scenario_d17_d18_gap_context"]
        assert any("valuation_missing:" in c for c in scenario["scenario_missing_constraints"])
        assert any("earnings_missing:" in c for c in scenario["scenario_missing_constraints"])
        assert any("true_breadth_missing:" in c for c in scenario["scenario_missing_constraints"])

    def test_growth_macro_gaps_visible_when_relevant(self):
        scenario = _scenario(
            [
                _row("labor_macro", "initial_jobless_claims", 350000, status="pressure"),
                _row("labor_macro", "unemployment_rate", 5.5, status="pressure"),
                _row("growth_inflation_macro_pack", "growth_macro_missing_inputs", "gdp_quarterly, real_pce", status="research_needed", source_badge="derived"),
            ],
            "growth_slowdown",
        )
        assert scenario["scenario_d17_d18_gap_context"]
        assert any("growth_macro_missing:" in c for c in scenario["scenario_missing_constraints"])

    def test_proxy_limited_status_raises_uncertainty(self):
        scenario = _scenario(
            [
                _row("market_stress_derived", "nasdaq100_drawdown_3m", -12.0, status="pressure", source_badge="derived"),
                _row(
                    "valuation_equity_structure",
                    "breadth_concentration_context_status",
                    "limited_proxy_context",
                    status="limited_proxy_context",
                    source_badge="derived",
                    component_contributions={
                        "hard_gates": {"proxy_breadth_does_not_replace_true_breadth": True},
                    },
                ),
            ],
            "ai_mega_cap_concentration_unwind",
        )
        assert any("proxy_only_context" in d for d in scenario["scenario_uncertainty_drivers"])


# ---------------------------------------------------------------------------
# 4.6 D19 historical reference context is reference-only
# ---------------------------------------------------------------------------

class TestD19ReferenceContext:
    def test_d19_replay_is_reference_only(self):
        scenario = _scenario(
            [
                _row("credit_stress", "high_yield_spread", 550.0, status="pressure"),
                _row(
                    "historical_validation",
                    "historical_validation_status",
                    value="available",
                    status="ok",
                    source_badge="derived",
                    component_contributions={
                        "d19_v1_replay_summary": {
                            "available_event_count": 3,
                            "limited_replay_event_count": 2,
                        },
                        "d19_v1_replay_rows": [{"event_id": "test", "validation_status": "available"}],
                    },
                ),
            ],
            "credit_spread_widening",
        )
        ref = scenario["scenario_d19_reference_context"]
        assert ref["reference_note"] == "historical_replay_reference_available"
        serialized = json.dumps(scenario, sort_keys=True).lower()
        for term in ("prediction accuracy", "backtest", "strategy performance", "expected_return"):
            assert term not in serialized

    def test_d19_limited_replay_shows_limited_note(self):
        scenario = _scenario(
            [
                _row("credit_stress", "high_yield_spread", 550.0, status="pressure"),
                _row(
                    "historical_validation",
                    "historical_validation_status",
                    value="insufficient_history",
                    status="insufficient_history",
                    source_badge="derived",
                    component_contributions={},
                ),
            ],
            "credit_spread_widening",
        )
        ref = scenario["scenario_d19_reference_context"]
        assert ref["reference_note"] == "d19_reference_limited"

    def test_d19_does_not_change_severity_or_support(self):
        base = [_row("credit_stress", "high_yield_spread", 550.0, status="pressure")]
        baseline = _scenario(base, "credit_spread_widening")
        with_d19 = _scenario(
            [
                *base,
                _row(
                    "historical_validation",
                    "historical_validation_status",
                    value="available",
                    status="ok",
                    source_badge="derived",
                    component_contributions={
                        "d19_v1_replay_summary": {"available_event_count": 5},
                        "d19_v1_replay_rows": [],
                    },
                ),
            ],
            "credit_spread_widening",
        )
        assert with_d19["severity_band"] == baseline["severity_band"]
        assert with_d19["support_band"] == baseline["support_band"]
        assert with_d19["supporting_evidence_keys"] == baseline["supporting_evidence_keys"]


# ---------------------------------------------------------------------------
# 4.7 Portfolio overlay cannot drive scenario severity alone
# ---------------------------------------------------------------------------

class TestPortfolioOverlayBoundary:
    def test_portfolio_overlay_does_not_change_severity_or_support(self):
        base = [_row("credit_stress", "high_yield_spread", 550.0, status="pressure")]
        baseline = _scenario(base, "credit_spread_widening")
        with_overlay = _scenario(
            [
                *base,
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
        assert with_overlay["severity_band"] == baseline["severity_band"]
        assert with_overlay["supporting_evidence_keys"] == baseline["supporting_evidence_keys"]

    def test_portfolio_overlay_alone_does_not_create_support(self):
        scenario = _scenario(
            [
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
        assert scenario["support_band"] == "unsupported"
        assert scenario["severity_band"] == "mild"

    def test_no_portfolio_action_language_in_output(self):
        rows = d16.build_scenario_stress_rows(
            [
                _row("credit_stress", "high_yield_spread", 550.0, status="pressure"),
                _row(
                    "portfolio_exposure_overlay",
                    "portfolio_exposure_overlay_status",
                    value="pressure",
                    status="pressure",
                    source_badge="derived",
                ),
            ]
        )
        serialized = json.dumps(rows, sort_keys=True).lower()
        assert "portfolio_action" not in serialized
        assert "target_allocation" not in serialized


# ---------------------------------------------------------------------------
# 4.8 Golden contract integration
# ---------------------------------------------------------------------------

class TestGoldenContractIntegration:
    def test_golden_evidence_table_contains_d16_keys(self, monkeypatch, tmp_path):
        _block_network(monkeypatch)
        _write_fake_reports(tmp_path)
        monkeypatch.setattr(dashboard_service, "DEFAULT_REPORTS_DIR", tmp_path)

        from fastapi.testclient import TestClient
        from app_backend.main import app

        data = TestClient(app).get("/api/dashboard/evidence-table").json()
        d16_rows = [r for r in data["rows"] if r["module"] == "scenario_stress"]
        d16_keys = {r["metric_key"] for r in d16_rows}

        assert d16_keys == EXPECTED_PUBLIC_KEYS
        assert all(r["source_badge"] == "derived" for r in d16_rows)

    def test_golden_d16_boundary_text(self, monkeypatch, tmp_path):
        _block_network(monkeypatch)
        _write_fake_reports(tmp_path)
        monkeypatch.setattr(dashboard_service, "DEFAULT_REPORTS_DIR", tmp_path)

        from fastapi.testclient import TestClient
        from app_backend.main import app

        data = TestClient(app).get("/api/dashboard/evidence-table").json()
        boundary_row = next(
            r for r in data["rows"]
            if r["metric_key"] == "scenario_stress_interpretation_boundary"
        )
        boundary = boundary_row["value"].lower()
        assert "scenario matrix" in boundary
        assert "not a forecast" in boundary
        assert "event-odds model" in boundary

    def test_golden_d16_scenarios_carry_s1_metadata(self, monkeypatch, tmp_path):
        _block_network(monkeypatch)
        _write_fake_reports(tmp_path)
        monkeypatch.setattr(dashboard_service, "DEFAULT_REPORTS_DIR", tmp_path)

        from fastapi.testclient import TestClient
        from app_backend.main import app

        data = TestClient(app).get("/api/dashboard/evidence-table").json()
        status_row = next(
            r for r in data["rows"]
            if r["metric_key"] == "scenario_stress_status"
        )
        scenarios = status_row["component_contributions"]["scenarios"]
        assert len(scenarios) == 7
        for scenario in scenarios:
            for field in S1_SCENARIO_METADATA_FIELDS:
                assert field in scenario, f"missing {field} in golden scenario {scenario['scenario_name']}"


# ---------------------------------------------------------------------------
# 4.9 AI Context Manifest integration
# ---------------------------------------------------------------------------

class TestAIContextManifestIntegration:
    def test_d16_enters_manifest_as_model_output(self, monkeypatch):
        rows = [
            _evidence_row("scenario_stress", "scenario_stress_status", "available"),
            _evidence_row("credit_stress", "high_yield_spread", 3.4, source_badge="official"),
        ]
        monkeypatch.setattr(
            dashboard_service,
            "build_dashboard_evidence_table",
            lambda **kwargs: SimpleNamespace(generated_at="2026-06-01T00:00:00+00:00", rows=rows),
        )
        manifest = ai_context_service.build_ai_context_manifest()
        model_keys = {r["metric_key"] for r in manifest.included_model_outputs}
        excluded_model_keys = {r["metric_key"] for r in manifest.excluded_model_outputs}
        fact_keys = {r["metric_key"] for r in manifest.included_facts}

        assert "scenario_stress_status" in model_keys | excluded_model_keys
        assert "scenario_stress_status" not in fact_keys

    def test_d16_manifest_row_carries_s1_scenario_metadata(self, monkeypatch):
        rows = [
            _evidence_row(
                "scenario_stress",
                "scenario_stress_status",
                "available",
                component_contributions={
                    "scenarios": [
                        {
                            "scenario_name": "credit_spread_widening",
                            "scenario_uncertainty_drivers": ["d13_hy_reliability_low"],
                            "scenario_d13_reliability_context": [{"metric_key": "hy_pct"}],
                            "scenario_refinement_boundary": "S1 refinement...",
                        }
                    ],
                    "uses_model_registry": True,
                    "uses_evidence_index": True,
                },
            ),
        ]
        monkeypatch.setattr(
            dashboard_service,
            "build_dashboard_evidence_table",
            lambda **kwargs: SimpleNamespace(generated_at="2026-06-01T00:00:00+00:00", rows=rows),
        )
        manifest = ai_context_service.build_ai_context_manifest()
        d16_output = next(
            (r for r in manifest.included_model_outputs if r["metric_key"] == "scenario_stress_status"),
            next(
                (r for r in manifest.excluded_model_outputs if r["metric_key"] == "scenario_stress_status"),
                None,
            ),
        )
        assert d16_output is not None
        assert "scenarios" in d16_output["component_contributions"]

    def test_d16_manifest_no_forbidden_terms(self, monkeypatch):
        rows = [
            _evidence_row("scenario_stress", "scenario_stress_status", "available"),
        ]
        monkeypatch.setattr(
            dashboard_service,
            "build_dashboard_evidence_table",
            lambda **kwargs: SimpleNamespace(generated_at="2026-06-01T00:00:00+00:00", rows=rows),
        )
        manifest = ai_context_service.build_ai_context_manifest()
        serialized = json.dumps(
            {
                "included_model_outputs": manifest.included_model_outputs,
                "excluded_model_outputs": manifest.excluded_model_outputs,
            },
            sort_keys=True,
        ).lower()
        for term in FORBIDDEN_TERMS:
            assert term not in serialized, f"forbidden term in manifest: {term}"


# ---------------------------------------------------------------------------
# 4.10 AI memo contract integration
# ---------------------------------------------------------------------------

class TestAIMemoContractIntegration:
    def test_memo_with_d16_context_passes_validation(self):
        manifest = _manifest_with_d16_output()
        preview = render_ai_memo_preview("daily_review_memo", manifest)
        result = validate_ai_memo_preview(preview)
        assert result.passed is True

    def test_memo_d16_forbidden_content_blocked(self):
        manifest = _manifest_with_d16_output()
        preview = render_ai_memo_preview("daily_review_memo", manifest).as_dict()
        preview["sections"][0]["content"] = (
            "You should buy more equities and sell bonds for expected return of 5%"
        )
        result = validate_ai_memo_preview(preview)
        assert result.passed is False
        assert any(t in result.blocked_terms for t in ("buy", "sell", "expected return"))

    def test_memo_privacy_flags_remain_closed(self):
        manifest = _manifest_with_d16_output()
        preview = render_ai_memo_preview("daily_review_memo", manifest)
        assert preview.privacy_summary.external_model_called is False
        assert preview.privacy_summary.search_called is False
        assert preview.privacy_summary.saved_by_default is False
        assert preview.privacy_summary.uses_holdings_line_items is False


# ---------------------------------------------------------------------------
# 4.11 D15/D16 compliance audit reinforcement
# ---------------------------------------------------------------------------

class TestComplianceAuditReinforcement:
    def test_d16_audit_section_present_and_clean(self, tmp_path):
        import audit_data_pipeline_coverage as audit

        _write_fake_reports(tmp_path)
        result = audit.build_coverage_audit(
            reports_dir=tmp_path,
            last_good_cache_dir=tmp_path / "last_good",
            market_history_db_path=tmp_path / "market_history.sqlite3",
        )
        d16_audit = result["scenario_stress"]
        assert d16_audit["scenario_count"] == 7
        assert d16_audit["public_outputs_expose_probability_language"] is False
        assert d16_audit["public_outputs_expose_trading_language"] is False
        assert d16_audit["uses_model_registry"] is True
        assert d16_audit["uses_evidence_index"] is True

    def test_d16_production_files_contain_no_forbidden_surfaces(self):
        from pathlib import Path

        text = Path("src/data_quality/scenario_stress.py").read_text(encoding="utf-8")
        for token in (
            "/api/chat",
            "/api/search",
            "/api/ai/deepseek",
            "/api/ai/external",
            "DeepSeek",
            "Tavily",
            "external_llm.yaml",
            "crash_probability",
            "recession_probability",
            "scenario_probability",
            "expected_return",
            "trade_signal",
            "target_allocation",
        ):
            assert token not in text, f"forbidden surface in scenario_stress.py: {token}"

    def test_model_registry_boundary_and_forbidden_policy(self):
        registration = MODEL_REGISTRY.get("scenario_stress")
        assert registration is not None
        assert registration.interpretation_boundary
        assert registration.forbidden_language_policy
        assert "forecast" in registration.interpretation_boundary.lower() or "not a forecast" in registration.interpretation_boundary.lower()


# ---------------------------------------------------------------------------
# Shared fixtures and helpers
# ---------------------------------------------------------------------------

def _row(
    module,
    metric_key,
    value,
    *,
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
    divergence_band="none",
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
        "reliability_drivers": [],
        "divergence_band": divergence_band,
        "method_agreement": "all_available_aligned",
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
        "divergence_band": divergence_band,
        "history_coverage_status": history_coverage_status,
        "provider_rebuild_status": provider_rebuild_status,
        "normalization_availability": normalization,
        "substitution_policy": substitution_policy,
    }


def _pressure_rows():
    return [
        _row("credit_stress", "high_yield_spread", 550.0, status="pressure"),
        _row("rate_pressure", "dgs10", 5.5, status="pressure"),
        _row("real_yield_pressure", "dfii10", 3.0, status="pressure"),
        _row("inflation_energy_pressure", "core_cpi_yoy", 4.5, status="pressure"),
        _row("labor_macro", "initial_jobless_claims", 350000, status="pressure"),
        _row("labor_macro", "unemployment_rate", 5.5, status="pressure"),
    ]


def _scenario(rows, scenario_name):
    summary = d16.build_scenario_stress_summary(rows)
    return next(s for s in summary["scenarios"] if s["scenario_name"] == scenario_name)


def _evidence_row(
    module,
    metric_key,
    value,
    *,
    source_badge="derived",
    component_contributions=None,
):
    return DashboardEvidenceRow(
        row_id=f"{module}:{metric_key}",
        module=module,
        metric_key=metric_key,
        display_name=metric_key,
        value=value,
        value_text=str(value),
        unit=None,
        status="ok",
        source="local_rules",
        source_badge=source_badge,
        source_series=metric_key.upper(),
        observation_date="2026-06-01",
        generated_at="2026-06-01T00:00:00+00:00",
        freshness_status="historical",
        missing_reason=None,
        interpretation_hint="test",
        blocked_reason=None,
        ai_context_allowed=True,
        interpretation_boundary=(
            "Scenario stress is a hypothetical scenario matrix, not future market direction."
        ),
        ai_context_tier="model_output" if module == "scenario_stress" else None,
        trigger_eligibility="reference_review_only",
        component_contributions=component_contributions,
    )


def _manifest_with_d16_output():
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
        "included_model_outputs": [
            {
                "module": "scenario_stress",
                "metric_key": "scenario_stress_status",
                "display_name": "Scenario stress status",
                "status": "ok",
                "source_badge": "derived",
                "freshness_status": "historical",
                "interpretation_boundary": d16.BOUNDARY,
                "component_contributions": {
                    "scenarios": [],
                    "uses_model_registry": True,
                    "uses_evidence_index": True,
                },
            }
        ],
        "excluded_model_outputs": [],
        "risk_boundaries": ["Reference context only."],
        "privacy_policy": {"returns_sanitized_evidence_rows_only": True},
        "search_policy": {"search_enabled": False},
        "portfolio_context_policy": {"mode": "compact_summary_only"},
        "persistence_policy": {"saves_manifest": False},
        "source_summary": {"total_evidence_rows": 2},
    }


def _write_fake_reports(tmp_path):
    generated_at = "2026-01-01T00:00:00+00:00"

    def metric(value, source="FRED", badge="official", status="ok"):
        return {
            "value": value,
            "status": status,
            "source": source,
            "source_badge": badge,
            "observation_date": "2026-01-01",
            "freshness_status": "fresh",
        }

    (tmp_path / "market_snapshot.json").write_text(
        json.dumps({
            "generated_at": generated_at,
            "status": "ok",
            "risk_level": "watch",
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
            "hyg_vs_lqd_30d": metric(-1.2, source="yfinance", badge="proxy"),
        }),
        encoding="utf-8",
    )
    (tmp_path / "portfolio_snapshot.json").write_text(
        json.dumps({
            "generated_at": generated_at,
            "status": "ok",
            "max_deviation_asset": {"value": "equity", "status": "ok"},
            "max_deviation_pp": {"value": 2.3, "status": "ok"},
            "equity_total_deviation_pp": {"value": 1.4, "status": "ok"},
            "cash_reserve_status": {"value": "available", "status": "ok"},
            "holdings_updated_at": {"value": "2026-01-01", "status": "ok"},
            "holdings": [],
        }),
        encoding="utf-8",
    )


def _block_network(monkeypatch):
    def _raise_on_network(*args, **kwargs):
        raise AssertionError("Network access is not allowed in S2 contract tests.")

    monkeypatch.setattr(socket, "create_connection", _raise_on_network)
