import json

import audit_data_pipeline_coverage as audit
from data_quality import growth_inflation_macro_pack as d17
from modeling.model_registry import ModelRegistry

from tests.helpers.dashboard_fixtures import block_network_calls


FORBIDDEN_EXACT_TERMS = {
    "crash_probability",
    "recession_probability",
    "market_direction_probability",
    "expected_return",
    "trade_signal",
    "target_allocation",
}


def test_d17_builds_deterministic_rows_from_fake_evidence():
    rows = d17.build_growth_inflation_macro_pack_rows(
        [
            _row("inflation_energy_pressure", "core_cpi_yoy", "pressure"),
            _row("inflation_energy_pressure", "core_pce_yoy", "pressure"),
            _row("rate_pressure", "dgs10", 4.8, status="pressure"),
            _row("real_yield_pressure", "real_yield_pressure_status", "pressure"),
            _row("labor_macro", "labor_deterioration_status", "watch", status="watch"),
        ]
    )

    by_key = _by_key(rows)
    assert set(by_key) == set(ModelRegistry().public_output_keys("growth_inflation_macro_pack"))
    assert by_key["inflation_macro_status"]["value"] == "pressure"
    assert by_key["policy_constraint_status"]["value"] in {"constrained", "highly_constrained"}
    assert by_key["stagflation_watch_status"]["value"] in {"watch", "pressure"}


def test_missing_inputs_become_research_needed_rows_not_fake_values():
    rows = d17.build_growth_inflation_macro_pack_rows([])
    by_key = _by_key(rows)

    assert by_key["growth_macro_status"]["status"] == "research_needed"
    assert by_key["growth_macro_missing_inputs"]["status"] == "research_needed"
    assert "ism_manufacturing_pmi" in by_key["growth_macro_missing_inputs"]["value"]
    assert by_key["growth_macro_missing_inputs"]["ai_context_allowed"] is False


def test_research_needed_rows_are_not_ai_factual_support():
    rows = d17.build_growth_inflation_macro_pack_rows([])

    research_rows = [row for row in rows if row["status"] == "research_needed"]
    assert research_rows
    assert all(row["ai_context_allowed"] is False for row in research_rows)


def test_oil_alone_cannot_trigger_inflation_pressure():
    summary = d17.build_growth_inflation_macro_pack_summary(
        [_row("inflation_energy_pressure", "wti_30d_change", 8.0, status="pressure")]
    )

    assert summary["inflation"]["status"] != "pressure"
    assert summary["inflation"]["hard_gates"]["oil_alone_cannot_trigger_inflation_pressure"] is True


def test_cpi_alone_cannot_trigger_stagflation_pressure():
    summary = d17.build_growth_inflation_macro_pack_summary(
        [_row("inflation_energy_pressure", "core_cpi_yoy", "pressure", status="pressure")]
    )

    assert summary["stagflation"]["status"] != "pressure"
    assert summary["stagflation"]["hard_gates"]["cpi_alone_cannot_trigger_stagflation_watch_pressure"] is True


def test_labor_watch_alone_avoids_cycle_language():
    rows = d17.build_growth_inflation_macro_pack_rows(
        [_row("labor_macro", "labor_deterioration_status", "watch", status="watch")]
    )
    serialized = json.dumps(rows, ensure_ascii=False).lower()

    assert "recession" not in serialized


def test_inflation_growth_labor_and_policy_constraint_can_produce_stagflation_watch():
    summary = d17.build_growth_inflation_macro_pack_summary(
        [
            _row("inflation_energy_pressure", "core_cpi_yoy", "pressure", status="pressure"),
            _row("inflation_energy_pressure", "core_pce_yoy", "pressure", status="pressure"),
            _row("labor_macro", "labor_deterioration_status", "watch", status="watch"),
            _row("labor_macro", "initial_jobless_claims", 260000, status="watch"),
            _row("rate_pressure", "dgs10", 4.8, status="pressure"),
            _row("real_yield_pressure", "real_yield_pressure_status", "pressure", status="pressure"),
        ]
    )

    assert summary["stagflation"]["status"] in {"watch", "pressure"}


def test_d17_rows_preserve_low_frequency_interpretation_boundaries():
    rows = d17.build_growth_inflation_macro_pack_rows(
        [_row("inflation_energy_pressure", "core_cpi_yoy", 3.5)]
    )
    boundary = _by_key(rows)["inflation_macro_interpretation_boundary"]["value"]

    assert "CPI/PCE/PPI are low-frequency data" in boundary
    assert "forecast" in boundary
    assert "return estimate" in boundary


def test_d17_is_registered_in_model_registry():
    registration = ModelRegistry().require("growth_inflation_macro_pack")

    assert registration.model_key == "growth_inflation_macro_pack_v0"
    assert registration.category == "derived_context"


def test_d17_audit_section_exists_and_leak_flags_are_false(monkeypatch, tmp_path):
    block_network_calls(monkeypatch)
    _write_json(
        tmp_path / "market_snapshot.json",
        {
            "generated_at": "2026-01-01T00:00:00+00:00",
            "status": "ok",
            "core_cpi_yoy": {
                "value": 3.1,
                "status": "ok",
                "source": "FRED",
                "source_badge": "official",
                "observation_date": "2026-01-01",
                "freshness_status": "fresh",
            },
        },
    )

    result = audit.build_coverage_audit(reports_dir=tmp_path)
    d17_audit = result["growth_inflation_macro_pack"]

    assert d17_audit["growth_inflation_macro_pack_metric_count"] == 19
    assert d17_audit["public_outputs_expose_probability_language"] is False
    assert d17_audit["public_outputs_expose_trading_language"] is False
    assert d17_audit["boundary_available"] is True


def test_d17_public_keys_exclude_forbidden_terms():
    keys = set(ModelRegistry().public_output_keys("growth_inflation_macro_pack"))
    text = " ".join(sorted(keys)).lower()

    assert not (keys & FORBIDDEN_EXACT_TERMS)
    for term in FORBIDDEN_EXACT_TERMS:
        assert term not in text


def test_d17_works_with_fake_rows_without_live_data(monkeypatch):
    block_network_calls(monkeypatch)
    rows = d17.build_growth_inflation_macro_pack_rows(
        [_row("labor_macro", "unemployment_rate", 4.1)]
    )

    assert rows
    assert _by_key(rows)["growth_inflation_macro_pack_model_version"]["value"] == "growth_inflation_macro_pack_v0"


def _row(module, metric_key, value, *, status="ok", source_badge="official"):
    return {
        "row_id": f"{module}:{metric_key}",
        "module": module,
        "metric_key": metric_key,
        "display_name": metric_key,
        "value": value,
        "value_text": str(value),
        "unit": None,
        "status": status,
        "source": "test_source" if source_badge != "derived" else "local_rules",
        "source_badge": source_badge,
        "source_series": metric_key.upper(),
        "observation_date": "2026-01-01",
        "generated_at": "2026-01-01T00:00:00+00:00",
        "freshness_status": "fresh",
        "missing_reason": None,
        "interpretation_hint": "Derived local evidence row.",
        "interpretation_boundary": "Reference review only.",
        "ai_context_allowed": True,
        "trigger_eligibility": "reference_review_only",
    }


def _by_key(rows):
    return {row["metric_key"]: row for row in rows}


def _write_json(path, payload):
    path.write_text(json.dumps(payload), encoding="utf-8")


