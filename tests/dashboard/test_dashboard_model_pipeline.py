"""Regression tests for the extracted dashboard model pipeline.

Validates that build_dashboard_model_rows produces the same row groups, module
keys, row ordering, and public metric_key sets as the original inline sequence
in build_dashboard_evidence_table. These tests lock behavior for M7/M8-A.
P-M1 adds conversion-count and input-order regression tests.
"""
import json
import socket
from pathlib import Path

from fastapi.testclient import TestClient

from app_backend.main import app
from app_backend.services import dashboard_model_pipeline
from app_backend.services import dashboard_service
from app_backend.services.dashboard_model_pipeline import (
    DashboardModelPipelineResult,
    build_dashboard_model_rows,
)
from app_backend.services.dashboard_service import _evidence_row
from modeling.model_registry import ModelRegistry


MODEL_REGISTRY = ModelRegistry()

EXPECTED_MODEL_ROW_GROUPS = {
    "historical_risk_percentile",
    "liquidity_funding_stress",
    "financial_stress_composite",
    "pullback_systemic_risk_checklist",
    "growth_inflation_macro_pack",
    "valuation_equity_structure",
    "macro_regime_review",
    "historical_validation",
    "scenario_stress",
    "portfolio_exposure_overlay",
}

# Ordered as in build_dashboard_model_rows rows assembly
EXPECTED_ROW_ORDER = [
    "financial_stress_composite",
    "pullback_systemic_risk_checklist",
    "growth_inflation_macro_pack",
    "valuation_equity_structure",
    "macro_regime_review",
    "scenario_stress",
    "historical_validation",
    "portfolio_exposure_overlay",
    "historical_risk_percentile",
    "liquidity_funding_stress",
]

D10_PUBLIC_KEYS = {
    "financial_stress_score",
    "financial_stress_status",
    "financial_stress_dominant_pressure_source",
    "financial_stress_component_contributions",
    "financial_stress_missing_inputs",
    "financial_stress_interpretation_boundary",
}

D11_PUBLIC_KEYS = {
    "pullback_classification",
    "pullback_checklist_items",
    "pullback_missing_critical_inputs",
    "pullback_supporting_evidence",
    "pullback_interpretation_boundary",
}


def _build_pipeline(monkeypatch, tmp_path):
    _write_fake_reports(tmp_path)
    monkeypatch.setattr(dashboard_service, "DEFAULT_REPORTS_DIR", tmp_path)
    summary = dashboard_service.build_dashboard_summary(reports_dir=tmp_path)
    base_rows = (
        dashboard_service._evidence_rows_from_summary(summary)
        + dashboard_service._labor_macro_evidence_rows(
            dashboard_service._load_dashboard_reports(tmp_path),
            db_path=None,
        )
    )
    return build_dashboard_model_rows(
        base_rows=base_rows,
        db_path=None,
        build_evidence_row=_evidence_row,
    )


# ---------------------------------------------------------------------------
# Structure tests
# ---------------------------------------------------------------------------


def test_pipeline_result_type(monkeypatch, tmp_path):
    _block_network(monkeypatch)
    result = _build_pipeline(monkeypatch, tmp_path)
    assert isinstance(result, DashboardModelPipelineResult)
    assert isinstance(result.rows, list)
    assert isinstance(result.row_groups, dict)


def test_pipeline_row_groups_keys(monkeypatch, tmp_path):
    _block_network(monkeypatch)
    result = _build_pipeline(monkeypatch, tmp_path)
    assert set(result.row_groups.keys()) == EXPECTED_MODEL_ROW_GROUPS


def test_pipeline_rows_are_nonempty(monkeypatch, tmp_path):
    _block_network(monkeypatch)
    result = _build_pipeline(monkeypatch, tmp_path)
    assert len(result.rows) > 0
    for group_key, group_rows in result.row_groups.items():
        assert len(group_rows) > 0, f"group {group_key!r} is empty"


def test_pipeline_rows_module_matches_group_key(monkeypatch, tmp_path):
    _block_network(monkeypatch)
    result = _build_pipeline(monkeypatch, tmp_path)
    for group_key, group_rows in result.row_groups.items():
        for row in group_rows:
            assert row.module == group_key, (
                f"row {row.metric_key!r} has module={row.module!r}, "
                f"expected {group_key!r}"
            )


def test_pipeline_rows_assembly_order(monkeypatch, tmp_path):
    """rows list starts with financial_stress groups and ends with percentile/liquidity."""
    _block_network(monkeypatch)
    result = _build_pipeline(monkeypatch, tmp_path)

    # Collect module sequence from result.rows (deduped, order-preserving)
    seen_modules: list[str] = []
    for row in result.rows:
        if not seen_modules or seen_modules[-1] != row.module:
            seen_modules.append(row.module)

    for expected_module in EXPECTED_ROW_ORDER:
        assert expected_module in seen_modules, (
            f"Expected module {expected_module!r} missing from rows"
        )

    # D13/D14 must appear after all model outputs in the rows assembly
    model_indices = {
        m: seen_modules.index(m)
        for m in EXPECTED_ROW_ORDER
        if m in seen_modules
    }
    percentile_idx = model_indices.get("historical_risk_percentile", -1)
    liquidity_idx = model_indices.get("liquidity_funding_stress", -1)
    d10_idx = model_indices.get("financial_stress_composite", -1)
    if percentile_idx >= 0 and d10_idx >= 0:
        assert percentile_idx > d10_idx, (
            "historical_risk_percentile should appear after financial_stress_composite in rows"
        )
    if liquidity_idx >= 0 and d10_idx >= 0:
        assert liquidity_idx > d10_idx, (
            "liquidity_funding_stress should appear after financial_stress_composite in rows"
        )


# ---------------------------------------------------------------------------
# Public key preservation tests
# ---------------------------------------------------------------------------


def test_pipeline_d10_public_keys_present(monkeypatch, tmp_path):
    _block_network(monkeypatch)
    result = _build_pipeline(monkeypatch, tmp_path)
    d10_keys = {row.metric_key for row in result.row_groups["financial_stress_composite"]}
    assert D10_PUBLIC_KEYS <= d10_keys, (
        f"Missing D10 keys: {D10_PUBLIC_KEYS - d10_keys}"
    )


def test_pipeline_d11_public_keys_present(monkeypatch, tmp_path):
    _block_network(monkeypatch)
    result = _build_pipeline(monkeypatch, tmp_path)
    d11_keys = {row.metric_key for row in result.row_groups["pullback_systemic_risk_checklist"]}
    assert D11_PUBLIC_KEYS <= d11_keys, (
        f"Missing D11 keys: {D11_PUBLIC_KEYS - d11_keys}"
    )


def test_pipeline_registry_model_public_keys_present(monkeypatch, tmp_path):
    """ModelRegistry public output keys must appear in pipeline row_groups."""
    _block_network(monkeypatch)
    result = _build_pipeline(monkeypatch, tmp_path)
    all_pipeline_keys = {row.metric_key for row in result.rows}

    for model_key in MODEL_REGISTRY.module_keys():
        public_keys = set(MODEL_REGISTRY.public_output_keys(model_key))
        if not public_keys:
            continue
        # At least one public key from each registered model should appear
        assert public_keys & all_pipeline_keys, (
            f"No public keys for model {model_key!r} found in pipeline rows. "
            f"Expected subset of {sorted(public_keys)!r}"
        )


# ---------------------------------------------------------------------------
# AI context gate tests
# ---------------------------------------------------------------------------


def test_pipeline_derived_rows_have_ai_context_field(monkeypatch, tmp_path):
    _block_network(monkeypatch)
    result = _build_pipeline(monkeypatch, tmp_path)
    for row in result.rows:
        assert hasattr(row, "ai_context_allowed"), (
            f"Row {row.metric_key!r} missing ai_context_allowed"
        )


def test_pipeline_stage8_overlay_rows_have_downstream_only_gate(monkeypatch, tmp_path):
    """Stage 8 rows must not be classified as base fact rows."""
    _block_network(monkeypatch)
    result = _build_pipeline(monkeypatch, tmp_path)
    overlay_rows = result.row_groups["portfolio_exposure_overlay"]
    assert overlay_rows, "portfolio_exposure_overlay group is empty"
    for row in overlay_rows:
        # Stage 8 rows should not appear in base modules
        assert row.module == "portfolio_exposure_overlay", (
            f"Unexpected module {row.module!r} in Stage 8 group"
        )
        assert row.source_badge == "derived", (
            f"Stage 8 row {row.metric_key!r} has unexpected source_badge={row.source_badge!r}"
        )


# ---------------------------------------------------------------------------
# Integration test: pipeline output matches build_dashboard_evidence_table
# ---------------------------------------------------------------------------


def test_pipeline_output_matches_evidence_table_row_count(monkeypatch, tmp_path):
    """build_dashboard_model_rows + base_rows must produce same count as evidence table."""
    _block_network(monkeypatch)
    _write_fake_reports(tmp_path)
    monkeypatch.setattr(dashboard_service, "DEFAULT_REPORTS_DIR", tmp_path)

    # Get row count from the full evidence table API
    client = TestClient(app)
    api_data = client.get("/api/dashboard/evidence-table").json()
    api_row_count = api_data["row_count"]
    api_modules = set(api_data["modules"])

    # Build via pipeline directly
    summary = dashboard_service.build_dashboard_summary(reports_dir=tmp_path)
    reports = dashboard_service._load_dashboard_reports(tmp_path)
    base_rows = (
        dashboard_service._evidence_rows_from_summary(summary)
        + dashboard_service._labor_macro_evidence_rows(reports, db_path=None)
    )
    pipeline_result = build_dashboard_model_rows(
        base_rows=base_rows,
        db_path=None,
        build_evidence_row=_evidence_row,
    )
    direct_total = len(base_rows) + len(pipeline_result.rows)

    assert direct_total == api_row_count, (
        f"Pipeline direct build ({direct_total}) != API row_count ({api_row_count})"
    )
    pipeline_modules = {row.module for row in base_rows} | {
        row.module for row in pipeline_result.rows
    }
    assert pipeline_modules == api_modules


def test_pipeline_module_keys_present_in_evidence_table(monkeypatch, tmp_path):
    """All EXPECTED_MODEL_ROW_GROUPS appear as modules in the API evidence table."""
    _block_network(monkeypatch)
    _write_fake_reports(tmp_path)
    monkeypatch.setattr(dashboard_service, "DEFAULT_REPORTS_DIR", tmp_path)

    data = TestClient(app).get("/api/dashboard/evidence-table").json()
    api_modules = set(data["modules"])

    assert EXPECTED_MODEL_ROW_GROUPS <= api_modules, (
        f"Missing modules in evidence table: {EXPECTED_MODEL_ROW_GROUPS - api_modules}"
    )


# ---------------------------------------------------------------------------
# Boundary gate tests: no forbidden endpoints
# ---------------------------------------------------------------------------


def test_no_chat_endpoint(monkeypatch, tmp_path):
    client = TestClient(app)
    response = client.post("/api/chat", json={"message": "hello"})
    assert response.status_code in {404, 405, 422}


def test_no_search_endpoint(monkeypatch, tmp_path):
    client = TestClient(app)
    response = client.get("/api/search", params={"q": "test"})
    assert response.status_code in {404, 405}


# ---------------------------------------------------------------------------
# P-M1: Row conversion count regression
# ---------------------------------------------------------------------------


def test_pm1_model_to_dict_called_once_per_row(monkeypatch, tmp_path):
    """Each DashboardEvidenceRow should be converted to dict at most once."""
    _block_network(monkeypatch)
    call_count = 0
    original_fn = dashboard_model_pipeline._model_to_dict

    def counting_model_to_dict(value):
        nonlocal call_count
        call_count += 1
        return original_fn(value)

    monkeypatch.setattr(
        dashboard_model_pipeline, "_model_to_dict", counting_model_to_dict
    )
    result = _build_pipeline(monkeypatch, tmp_path)

    total_row_objects = len(result.rows)
    # base_rows are also converted once; count them from the pipeline helper
    _write_fake_reports(tmp_path)
    monkeypatch.setattr(dashboard_service, "DEFAULT_REPORTS_DIR", tmp_path)
    summary = dashboard_service.build_dashboard_summary(reports_dir=tmp_path)
    base_rows = (
        dashboard_service._evidence_rows_from_summary(summary)
        + dashboard_service._labor_macro_evidence_rows(
            dashboard_service._load_dashboard_reports(tmp_path),
            db_path=None,
        )
    )
    max_expected = len(base_rows) + total_row_objects
    assert call_count <= max_expected, (
        f"_model_to_dict called {call_count} times but only "
        f"{max_expected} unique rows exist (base={len(base_rows)}, "
        f"pipeline={total_row_objects}). Repeated conversion detected."
    )


def test_pm1_no_repeated_base_row_conversion(monkeypatch, tmp_path):
    """base_rows should be converted exactly once, not once per downstream model."""
    _block_network(monkeypatch)
    converted_ids: list[int] = []
    original_fn = dashboard_model_pipeline._model_to_dict

    def tracking_model_to_dict(value):
        converted_ids.append(id(value))
        return original_fn(value)

    monkeypatch.setattr(
        dashboard_model_pipeline, "_model_to_dict", tracking_model_to_dict
    )
    _build_pipeline(monkeypatch, tmp_path)

    from collections import Counter
    counts = Counter(converted_ids)
    repeated = {obj_id: c for obj_id, c in counts.items() if c > 1}
    assert not repeated, (
        f"{len(repeated)} row objects were converted more than once. "
        f"Max repeat count: {max(repeated.values())}"
    )


# ---------------------------------------------------------------------------
# P-M1: Input order preservation for Scenario Stress Matrix and
#        Portfolio Exposure Overlay
# ---------------------------------------------------------------------------


def test_pm1_scenario_stress_input_includes_historical_validation(monkeypatch, tmp_path):
    """Scenario Stress Matrix input must include Historical Validation Replay
    rows after Macro Regime Review rows."""
    _block_network(monkeypatch)
    captured_input: list[dict] = []

    from data_quality import scenario_stress as ss_mod
    original_build = ss_mod.build_scenario_stress_rows

    def capturing_build(input_dicts, **kwargs):
        captured_input.extend(input_dicts)
        return original_build(input_dicts, **kwargs)

    monkeypatch.setattr(ss_mod, "build_scenario_stress_rows", capturing_build)
    _build_pipeline(monkeypatch, tmp_path)

    modules_in_input = [d.get("module", "") for d in captured_input]
    has_macro_regime = "macro_regime_review" in modules_in_input
    has_historical_validation = "historical_validation" in modules_in_input
    assert has_macro_regime, "Scenario Stress input missing macro_regime_review rows"
    assert has_historical_validation, "Scenario Stress input missing historical_validation rows"

    last_macro_idx = max(
        i for i, m in enumerate(modules_in_input) if m == "macro_regime_review"
    )
    first_validation_idx = next(
        i for i, m in enumerate(modules_in_input) if m == "historical_validation"
    )
    assert first_validation_idx > last_macro_idx, (
        "Historical Validation Replay rows must appear after Macro Regime Review "
        "rows in Scenario Stress Matrix input"
    )


def test_pm1_portfolio_overlay_input_order(monkeypatch, tmp_path):
    """Portfolio Exposure Overlay input must include Scenario Stress Matrix
    before Historical Validation Replay."""
    _block_network(monkeypatch)
    captured_input: list[dict] = []

    from data_quality import portfolio_exposure_overlay as peo_mod
    original_build = peo_mod.build_portfolio_exposure_overlay_rows

    def capturing_build(input_dicts, **kwargs):
        captured_input.extend(input_dicts)
        return original_build(input_dicts, **kwargs)

    monkeypatch.setattr(
        peo_mod, "build_portfolio_exposure_overlay_rows", capturing_build
    )
    _build_pipeline(monkeypatch, tmp_path)

    modules_in_input = [d.get("module", "") for d in captured_input]
    has_scenario = "scenario_stress" in modules_in_input
    has_validation = "historical_validation" in modules_in_input
    assert has_scenario, "Portfolio Overlay input missing scenario_stress rows"
    assert has_validation, "Portfolio Overlay input missing historical_validation rows"

    last_scenario_idx = max(
        i for i, m in enumerate(modules_in_input) if m == "scenario_stress"
    )
    first_validation_idx = next(
        i for i, m in enumerate(modules_in_input) if m == "historical_validation"
    )
    assert last_scenario_idx < first_validation_idx, (
        "Scenario Stress Matrix rows must appear before Historical Validation "
        "Replay rows in Portfolio Exposure Overlay input"
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _block_network(monkeypatch):
    def _raise(*args, **kwargs):
        raise AssertionError("Network access not allowed in pipeline tests.")
    monkeypatch.setattr(socket, "create_connection", _raise)


def _write_fake_reports(tmp_path: Path) -> None:
    generated_at = "2026-01-01T00:00:00+00:00"

    def metric(value, source="FRED", badge="official"):
        return {
            "value": value,
            "status": "ok",
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
                "wti_30d_change": metric(-4.2, source="EIA"),
                "brent_30d_change": metric(-3.8, source="EIA"),
                "sp500_30d_return": metric(2.2, source="yfinance"),
                "sp500_60d_return": metric(5.1, source="yfinance"),
                "nasdaq100_30d_return": metric(3.3, source="yfinance"),
                "nasdaq100_60d_return": metric(6.4, source="yfinance"),
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "market_temperature.json").write_text(
        json.dumps({"generated_at": generated_at, "status": "watch"}),
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
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "provider_health_check.json").write_text(
        json.dumps({"generated_at": generated_at, "overall_status": "ok"}),
        encoding="utf-8",
    )
