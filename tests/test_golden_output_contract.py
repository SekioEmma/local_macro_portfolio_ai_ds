import json
import socket
from pathlib import Path

from fastapi.testclient import TestClient

import audit_data_pipeline_coverage as audit
from app_backend.main import app
from app_backend.services import dashboard_service
from modeling.model_registry import FORBIDDEN_PUBLIC_OUTPUT_KEYS, ModelRegistry


REQUIRED_EVIDENCE_ROW_FIELDS = {
    "metric_key",
    "display_name",
    "value",
    "value_text",
    "unit",
    "status",
    "source",
    "source_badge",
    "observation_date",
    "generated_at",
    "freshness_status",
    "missing_reason",
    "interpretation_hint",
    "ai_context_allowed",
    "module",
}
MODEL_REGISTRY = ModelRegistry()
MODEL_MODULES = set(MODEL_REGISTRY.module_keys())
D10_KEYS = {
    "financial_stress_score",
    "financial_stress_status",
    "financial_stress_dominant_pressure_source",
    "financial_stress_component_contributions",
    "financial_stress_missing_inputs",
    "financial_stress_interpretation_boundary",
}
D11_KEYS = {
    "pullback_classification",
    "pullback_checklist_items",
    "pullback_missing_critical_inputs",
    "pullback_supporting_evidence",
    "pullback_interpretation_boundary",
}
D15_PUBLIC_KEYS = set(MODEL_REGISTRY.public_output_keys("macro_regime_review"))
D15_FORBIDDEN_FIELDS = set(FORBIDDEN_PUBLIC_OUTPUT_KEYS)
D16_PUBLIC_KEYS = set(MODEL_REGISTRY.public_output_keys("scenario_stress"))
D17_PUBLIC_KEYS = set(MODEL_REGISTRY.public_output_keys("growth_inflation_macro_pack"))
D18_PUBLIC_KEYS = set(MODEL_REGISTRY.public_output_keys("valuation_equity_structure"))
D19_PUBLIC_KEYS = set(MODEL_REGISTRY.public_output_keys("historical_validation"))
PORTFOLIO_EXPOSURE_OVERLAY_PUBLIC_KEYS = set(
    MODEL_REGISTRY.public_output_keys("portfolio_exposure_overlay")
)
FORBIDDEN_PUBLIC_PHRASES = (
    "crash probability",
    "recession probability",
    "market direction probability",
    "buy",
    "sell",
    "add position",
    "reduce position",
    "clear position",
    "hedge",
    "rebalance",
    "target allocation",
    "expected return",
    "trade signal",
)
PRIVATE_TOKENS = (
    "raw_provider",
    "raw_holdings",
    "raw_prompt",
    "api_key",
    "sk-",
    "HOLDINGS_AMOUNT_MUST_NOT_LEAK",
    "RAW_FUND",
    "G:\\local_macro_portfolio_ai",
)


def test_golden_evidence_row_and_model_output_contract(monkeypatch, tmp_path):
    _block_network(monkeypatch)
    _write_fake_reports(tmp_path)
    monkeypatch.setattr(dashboard_service, "DEFAULT_REPORTS_DIR", tmp_path)

    data = TestClient(app).get("/api/dashboard/evidence-table").json()
    rows = data["rows"]
    rows_by_module = _rows_by_module(rows)
    keys_by_module = {
        module: {row["metric_key"] for row in module_rows}
        for module, module_rows in rows_by_module.items()
    }

    assert rows
    assert REQUIRED_EVIDENCE_ROW_FIELDS <= set(rows[0])
    assert MODEL_MODULES <= set(rows_by_module)
    assert D10_KEYS <= keys_by_module["financial_stress_composite"]
    assert D11_KEYS <= keys_by_module["pullback_systemic_risk_checklist"]
    assert D17_PUBLIC_KEYS <= keys_by_module["growth_inflation_macro_pack"]
    assert D18_PUBLIC_KEYS <= keys_by_module["valuation_equity_structure"]
    assert D15_PUBLIC_KEYS <= keys_by_module["macro_regime_review"]
    assert D16_PUBLIC_KEYS <= keys_by_module["scenario_stress"]
    assert D19_PUBLIC_KEYS <= keys_by_module["historical_validation"]
    assert PORTFOLIO_EXPOSURE_OVERLAY_PUBLIC_KEYS <= keys_by_module["portfolio_exposure_overlay"]

    stress = _row(rows, "financial_stress_composite", "financial_stress_score")
    assert isinstance(stress["value"], (int, float))
    assert "pressure temperature" in stress["interpretation_boundary"]
    assert "event-odds model" in stress["interpretation_boundary"]

    pullback = _row(rows, "pullback_systemic_risk_checklist", "pullback_classification")
    assert "current evidence review" in pullback["interpretation_boundary"]
    assert "reference review only" in pullback["interpretation_boundary"]

    percentile_rows = rows_by_module["historical_risk_percentile"]
    assert percentile_rows
    assert {row["status"] for row in percentile_rows} <= {
        "ok",
        "watch",
        "pressure",
        "stress",
        "missing",
        "insufficient_history",
    }
    assert any("percentile" in row for row in percentile_rows)
    assert any("zscore" in row for row in percentile_rows)
    assert any("robust_zscore" in row for row in percentile_rows)

    liquidity = _row(
        rows,
        "liquidity_funding_stress",
        "liquidity_funding_interpretation_boundary",
    )
    assert "reference evidence" in liquidity["interpretation_boundary"]
    assert "ON RRP usage alone is not a risk trigger" in liquidity["interpretation_boundary"]
    growth_context = _row(rows, "growth_inflation_macro_pack", "growth_macro_status")
    assert "current-evidence context" in growth_context["interpretation_boundary"]
    assert "forecast" in growth_context["interpretation_boundary"]
    valuation_context = _row(rows, "valuation_equity_structure", "valuation_context_status")
    assert "research/proxy context" in valuation_context["interpretation_boundary"]
    assert valuation_context["value"] in {
        "available",
        "research_needed",
        "limited_proxy_context",
        "unavailable",
        "insufficient_evidence",
    }

    regime_rows = rows_by_module["macro_regime_review"]
    regime_keys = {row["metric_key"] for row in regime_rows}
    assert regime_keys == D15_PUBLIC_KEYS
    assert not (regime_keys & D15_FORBIDDEN_FIELDS)
    regime_boundary = _row(rows, "macro_regime_review", "interpretation_boundary")
    assert "current evidence review" in regime_boundary["value"]
    assert "prediction model" in regime_boundary["value"]
    assert "market direction forecast" in regime_boundary["value"]
    assert "probability" not in regime_boundary["value"].lower()
    assert "allocation directive" in regime_boundary["value"]
    assert "return estimate" in regime_boundary["value"]
    scenario_boundary = _row(
        rows,
        "scenario_stress",
        "scenario_stress_interpretation_boundary",
    )
    assert "scenario matrix" in scenario_boundary["value"]
    assert "event-odds model" in scenario_boundary["value"]
    d19_boundary = _row(rows, "historical_validation", "historical_validation_validation_boundary")
    assert "historical replay" in d19_boundary["value"]
    assert "event-window consistency" in d19_boundary["value"]
    overlay_boundary = _row(
        rows,
        "portfolio_exposure_overlay",
        "portfolio_exposure_interpretation_boundary",
    )
    assert "privacy-preserving explanatory layer" in overlay_boundary["value"]
    assert "position-level output" in overlay_boundary["value"]

    _assert_no_forbidden_public_phrases(
        {
            "model_outputs": [
                row
                for row in rows
                if row["module"] in MODEL_MODULES or row["module"] == "portfolio_deviation"
            ]
        }
    )


def test_golden_ai_context_manifest_contract(monkeypatch, tmp_path):
    _block_network(monkeypatch)
    _write_fake_reports(tmp_path)
    monkeypatch.setattr(dashboard_service, "DEFAULT_REPORTS_DIR", tmp_path)

    data = TestClient(app).get("/api/ai/context-preview").json()

    assert {
        "included_facts",
        "excluded_facts",
        "included_model_outputs",
        "excluded_model_outputs",
        "portfolio_context_policy",
        "privacy_policy",
        "search_policy",
        "model_destination",
        "persistence_policy",
        "risk_boundaries",
    } <= set(data)
    assert data["privacy_policy"]["returns_holdings_line_items"] is False
    assert data["privacy_policy"]["returns_provider_payloads"] is False
    assert data["privacy_policy"]["returns_credentials"] is False
    assert data["search_policy"]["search_enabled"] is False
    assert data["model_destination"]["deepseek_enabled"] is False
    assert data["model_destination"]["tavily_enabled"] is False

    included_model_modules = {row["module"] for row in data["included_model_outputs"]}
    included_model_keys = {row["metric_key"] for row in data["included_model_outputs"]}
    assert included_model_modules <= MODEL_REGISTRY.model_output_module_keys()
    assert {"financial_stress_composite", "pullback_systemic_risk_checklist", "macro_regime_review"} <= included_model_modules
    assert "macro_regime_label" in included_model_keys
    assert "macro_regime_label" not in {row["metric_key"] for row in data["included_facts"]}

    blocked_statuses = {"missing", "research_needed", "insufficient_history", "stale"}
    assert all(row["status"] not in blocked_statuses for row in data["included_facts"])
    _assert_no_private_tokens(data)
    _assert_no_forbidden_public_phrases(
        {
            "included_model_outputs": data["included_model_outputs"],
            "risk_boundaries": data["risk_boundaries"],
        }
    )


def test_golden_audit_contract(tmp_path):
    _write_fake_reports(tmp_path)

    result = audit.build_coverage_audit(
        reports_dir=tmp_path,
        last_good_cache_dir=tmp_path / "last_good",
        market_history_db_path=tmp_path / "market_history.sqlite3",
    )

    assert MODEL_MODULES <= set(result)
    assert "ai_context_manifest" in result
    assert result["portfolio_compact"]["portfolio_has_raw_holdings_leak"] is False
    d15 = result["macro_regime_review"]
    assert d15["public_outputs_expose_macro_regime_score"] is False
    assert d15["public_outputs_expose_numeric_internal_scores"] is False
    assert d15["contains_crash_probability_language"] is False
    assert d15["contains_recession_probability_language"] is False
    assert d15["hard_gate_count"] >= 10
    assert result["ai_context_manifest"]["included_d15_model_output_count"] >= 1
    d19 = result["historical_validation"]
    assert d19["event_count"] >= 5
    assert d19["boundary_violation_count"] == 0
    assert d19["public_outputs_expose_probability_language"] is False
    assert d19["public_outputs_expose_trading_language"] is False
    assert d19["public_outputs_expose_backtest_language"] is False
    assert d19["public_outputs_expose_return_language"] is False
    assert d19["proxy_constraint_violation_count"] == 0
    assert d19["missing_data_violation_count"] == 0
    assert d19["reads_local_market_history_only"] is True
    assert d19["writes_sqlite"] is False
    assert d19["fetches_live_provider_data"] is False
    assert d19["returns_holdings_line_items"] is False
    assert d19["returns_provider_payloads"] is False
    assert d19["returns_credentials"] is False
    assert d19["D15_band_only_boundary_preserved"] is True
    assert d19["D16_scenario_matrix_boundary_preserved"] is True
    assert d19["D17_context_layer_boundary_preserved"] is True
    assert d19["D18_research_proxy_boundary_preserved"] is True
    d16 = result["scenario_stress"]
    assert d16["scenario_count"] == 7
    assert d16["public_outputs_expose_probability_language"] is False
    assert d16["public_outputs_expose_trading_language"] is False
    assert d16["uses_model_registry"] is True
    assert d16["uses_evidence_index"] is True
    d17 = result["growth_inflation_macro_pack"]
    assert d17["growth_inflation_macro_pack_metric_count"] == len(D17_PUBLIC_KEYS)
    assert d17["public_outputs_expose_probability_language"] is False
    assert d17["public_outputs_expose_trading_language"] is False
    d18 = result["valuation_equity_structure"]
    assert d18["valuation_equity_structure_metric_count"] == len(D18_PUBLIC_KEYS)
    assert d18["public_outputs_expose_probability_language"] is False
    assert d18["public_outputs_expose_trading_language"] is False
    assert d18["public_outputs_expose_return_language"] is False
    portfolio_overlay = result["portfolio_exposure_overlay"]
    assert portfolio_overlay["portfolio_exposure_overlay_metric_count"] == len(
        PORTFOLIO_EXPOSURE_OVERLAY_PUBLIC_KEYS
    )
    assert portfolio_overlay["public_outputs_expose_probability_language"] is False
    assert portfolio_overlay["public_outputs_expose_trading_language"] is False
    assert portfolio_overlay["public_outputs_expose_allocation_language"] is False
    assert portfolio_overlay["public_outputs_expose_return_language"] is False
    assert portfolio_overlay["reads_holdings_line_items"] is False
    assert portfolio_overlay["returns_holdings_line_items"] is False
    assert portfolio_overlay["returns_position_weights"] is False
    assert portfolio_overlay["returns_account_values"] is False
    assert portfolio_overlay["portfolio_overlay_cannot_trigger_macro_regime"] is True
    assert portfolio_overlay["portfolio_overlay_downstream_only"] is True

    _assert_no_private_tokens(result)
    _assert_no_forbidden_public_phrases(
        {
            "macro_regime_review": result["macro_regime_review"],
            "scenario_stress": result["scenario_stress"],
            "growth_inflation_macro_pack": result["growth_inflation_macro_pack"],
            "valuation_equity_structure": result["valuation_equity_structure"],
            "portfolio_exposure_overlay": result["portfolio_exposure_overlay"],
            "ai_context_manifest": result["ai_context_manifest"],
        }
    )


def test_golden_model_registry_contract():
    for registration in MODEL_REGISTRY.all():
        assert registration.interpretation_boundary
        assert registration.forbidden_language_policy
        assert registration.audit_policy
        assert registration.frontend_registry_policy
        assert registration.public_output_keys
        assert not (set(registration.public_output_keys) & D15_FORBIDDEN_FIELDS)


def test_golden_frontend_registry_contract():
    module_registry = Path("app_frontend/src/utils/moduleRegistry.ts").read_text(
        encoding="utf-8"
    )
    metric_registry = Path("app_frontend/src/utils/metricRegistry.ts").read_text(
        encoding="utf-8"
    )
    registry_text = f"{module_registry}\n{metric_registry}"

    for module_key in MODEL_REGISTRY.model_output_module_keys():
        assert f"{module_key}:" in module_registry
    assert 'macro_regime_review: "Macro regime review"' in module_registry
    assert 'growth_inflation_macro_pack: "Growth/inflation macro pack"' in module_registry
    assert 'valuation_equity_structure: "Valuation/equity structure"' in module_registry
    assert 'portfolio_exposure_overlay: "Portfolio exposure overlay"' in module_registry
    assert 'scenario_stress: "Scenario stress"' in module_registry
    assert 'historical_validation: "Historical validation"' in module_registry
    for metric_key in D15_PUBLIC_KEYS:
        assert f"{metric_key}:" in metric_registry
    for metric_key in D16_PUBLIC_KEYS:
        assert f"{metric_key}:" in metric_registry
    for metric_key in D17_PUBLIC_KEYS:
        assert f"{metric_key}:" in metric_registry
    for metric_key in D18_PUBLIC_KEYS:
        assert f"{metric_key}:" in metric_registry
    for metric_key in D19_PUBLIC_KEYS:
        assert f"{metric_key}:" in metric_registry
    for metric_key in PORTFOLIO_EXPOSURE_OVERLAY_PUBLIC_KEYS:
        assert f"{metric_key}:" in metric_registry
    assert "current evidence review" in module_registry
    assert "current-evidence context" in module_registry
    assert "research/proxy context" in module_registry
    assert "scenario matrix" in module_registry
    assert "historical replay" in module_registry
    assert "allocation directive" in module_registry
    assert "return estimate" in module_registry
    for token in D15_FORBIDDEN_FIELDS:
        assert token not in registry_text
    _assert_no_forbidden_public_phrases(registry_text)


def _rows_by_module(rows):
    grouped = {}
    for row in rows:
        grouped.setdefault(row["module"], []).append(row)
    return grouped


def _row(rows, module, metric_key):
    for row in rows:
        if row["module"] == module and row["metric_key"] == metric_key:
            return row
    raise AssertionError(f"missing row {module}.{metric_key}")


def _assert_no_private_tokens(payload):
    text = json.dumps(list(_string_values(payload)), sort_keys=True)
    for token in PRIVATE_TOKENS:
        assert token not in text


def _assert_no_forbidden_public_phrases(payload):
    text = json.dumps(payload, sort_keys=True).lower()
    for phrase in FORBIDDEN_PUBLIC_PHRASES:
        assert phrase not in text


def _string_values(value):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for item in value.values():
            yield from _string_values(item)
    elif isinstance(value, list):
        for item in value:
            yield from _string_values(item)


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
        json.dumps(
            {
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
                "raw_extra": "must_not_leak",
                "raw_" + "prompt": "must_not_leak",
                "raw_" + "provider_response": "must_not_leak",
            }
        ),
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
                "holdings_updated_at": {"value": "2026-01-01", "status": "ok"},
                "holdings": [
                    {
                        "ticker": "RAW_FUND",
                        "amount": "HOLDINGS_AMOUNT_MUST_NOT_LEAK",
                    }
                ],
                "raw_extra": "must_not_leak",
                "raw_" + "holdings": "must_not_leak",
            }
        ),
        encoding="utf-8",
    )


def _block_network(monkeypatch):
    def _raise_on_network(*args, **kwargs):
        raise AssertionError("Network access is not allowed in golden contract tests.")

    monkeypatch.setattr(socket, "create_connection", _raise_on_network)
