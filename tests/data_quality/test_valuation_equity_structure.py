import json
import socket

import audit_data_pipeline_coverage as audit
from data_quality import macro_regime_review as d15
from data_quality import scenario_stress as d16
from data_quality import valuation_equity_structure as d18
from modeling.model_registry import ModelRegistry


FORBIDDEN_EXACT_TERMS = {
    "valuation_score",
    "expected_return",
    "market_direction_probability",
    "crash_probability",
    "recession_probability",
    "trade_signal",
    "target_allocation",
    "timing_signal",
}


def test_d18_builds_deterministic_rows_from_fake_evidence():
    rows = d18.build_valuation_equity_structure_rows(
        [
            _row("valuation_research", "sp500_trailing_pe", "pressure", status="pressure"),
            _row("valuation_research", "earnings_revision", "watch", status="watch"),
            _row("breadth_concentration_proxy", "qqq_vs_spy_30d", -4.0, status="pressure", source_badge="proxy"),
            _row("breadth_concentration_proxy", "spy_vs_rsp_30d", -3.0, status="pressure", source_badge="proxy"),
        ]
    )

    by_key = _by_key(rows)
    assert set(by_key) == set(ModelRegistry().public_output_keys("valuation_equity_structure"))
    assert by_key["valuation_context_status"]["value"] == "available"
    assert by_key["valuation_pressure_hint"]["value"] == "elevated"
    assert by_key["earnings_context_status"]["value"] == "limited_context"
    assert by_key["breadth_concentration_context_status"]["value"] == "pressure"


def test_missing_valuation_earnings_and_true_breadth_are_research_needed_not_fake_values():
    rows = d18.build_valuation_equity_structure_rows([])
    by_key = _by_key(rows)

    assert by_key["valuation_context_status"]["value"] == "research_needed"
    assert by_key["valuation_pressure_hint"]["value"] == "research_needed"
    assert by_key["valuation_missing_inputs"]["status"] == "research_needed"
    assert "sp500_forward_pe_source_gate" in by_key["valuation_missing_inputs"]["value"]
    assert "earnings_revision_source_gate" in by_key["earnings_missing_inputs"]["value"]
    assert "true_breadth_source_gate" in by_key["breadth_concentration_missing_inputs"]["value"]
    assert by_key["valuation_missing_inputs"]["ai_context_allowed"] is False


def test_research_needed_valuation_rows_are_not_ai_factual_support():
    rows = d18.build_valuation_equity_structure_rows([])
    research_rows = [row for row in rows if row["status"] == "research_needed"]

    assert research_rows
    assert all(row["ai_context_allowed"] is False for row in research_rows)


def test_missing_valuation_is_neither_low_nor_high():
    rows = d18.build_valuation_equity_structure_rows([])
    by_key = _by_key(rows)

    assert by_key["valuation_pressure_hint"]["value"] == "research_needed"
    assert by_key["valuation_pressure_hint"]["value"] not in {"none", "elevated"}


def test_valuation_high_alone_cannot_trigger_macro_regime_support():
    d18_rows = d18.build_valuation_equity_structure_rows(
        [_row("valuation_research", "sp500_trailing_pe", "pressure", status="pressure")]
    )
    regime = _by_key(d15.build_macro_regime_review_rows(d18_rows))

    assert regime["macro_regime_label"]["value"] == "insufficient_evidence"
    gates = regime["macro_regime_label"]["component_contributions"]["hard_gates"]
    assert gates["valuation_earnings_true_breadth_gaps_remain_explicit"] is True


def test_valuation_high_alone_cannot_trigger_systemic_review():
    rows = d18.build_valuation_equity_structure_rows(
        [_row("valuation_research", "sp500_trailing_pe", "pressure", status="pressure")]
    )
    contributions = _by_key(rows)["valuation_context_status"]["component_contributions"]

    assert contributions["hard_gates"]["valuation_cannot_trigger_systemic_review"] is True


def test_proxy_breadth_cannot_replace_true_breadth():
    rows = d18.build_valuation_equity_structure_rows(
        [_row("breadth_concentration_proxy", "spy_vs_rsp_30d", -3.0, status="pressure", source_badge="proxy")]
    )
    by_key = _by_key(rows)

    assert by_key["breadth_concentration_context_status"]["value"] == "limited_proxy_context"
    assert "true_breadth_source_gate" in by_key["breadth_concentration_missing_inputs"]["value"]
    gates = by_key["breadth_concentration_context_status"]["component_contributions"]["hard_gates"]
    assert gates["proxy_breadth_not_true_breadth"] is True


def test_qqq_spy_proxy_alone_cannot_create_strong_or_high_context():
    rows = d18.build_valuation_equity_structure_rows(
        [_row("breadth_concentration_proxy", "qqq_vs_spy_30d", -4.0, status="pressure", source_badge="proxy")]
    )
    by_key = _by_key(rows)

    assert by_key["equity_structure_status"]["value"] == "limited_proxy_context"
    assert by_key["equity_structure_status"]["value"] not in {"pressure", "strong", "high"}


def test_spy_rsp_proxy_alone_cannot_create_strong_or_high_context():
    rows = d18.build_valuation_equity_structure_rows(
        [_row("breadth_concentration_proxy", "spy_vs_rsp_30d", -4.0, status="pressure", source_badge="proxy")]
    )
    by_key = _by_key(rows)

    assert by_key["breadth_concentration_context_status"]["value"] == "limited_proxy_context"
    assert by_key["breadth_concentration_context_status"]["value"] not in {"pressure", "strong", "high"}


def test_ai_mega_cap_context_remains_limited_without_credit_funding_labor_confirmation():
    d18_rows = d18.build_valuation_equity_structure_rows(
        [
            _row("breadth_concentration_proxy", "qqq_vs_spy_30d", -4.0, status="pressure", source_badge="proxy"),
            _row("breadth_concentration_proxy", "spy_vs_rsp_30d", -3.0, status="pressure", source_badge="proxy"),
        ]
    )
    scenario = _scenario(d18_rows, "ai_mega_cap_concentration_unwind")

    assert scenario["support_band"] == "weak"
    assert scenario["severity_band"] == "mild"
    assert scenario["uncertainty_band"] == "high"


def test_d18_is_registered_in_model_registry_and_metric_lookup():
    registration = ModelRegistry().require("valuation_equity_structure")

    assert registration.model_key == "valuation_equity_structure_v0"
    assert registration.category == "research_context"
    assert set(registration.public_output_keys) == set(
        ModelRegistry().public_output_keys("valuation_equity_structure")
    )


def test_d18_audit_section_exists_and_leak_flags_are_false(monkeypatch, tmp_path):
    _block_network(monkeypatch)
    _write_json(
        tmp_path / "market_snapshot.json",
        {
            "generated_at": "2026-01-01T00:00:00+00:00",
            "status": "ok",
            "sp500_30d_return": {
                "value": 1.0,
                "status": "ok",
                "source": "test",
                "source_badge": "proxy",
                "observation_date": "2026-01-01",
                "freshness_status": "fresh",
            },
        },
    )

    result = audit.build_coverage_audit(reports_dir=tmp_path)
    d18_audit = result["valuation_equity_structure"]

    assert d18_audit["valuation_equity_structure_metric_count"] == 19
    assert d18_audit["public_outputs_expose_probability_language"] is False
    assert d18_audit["public_outputs_expose_trading_language"] is False
    assert d18_audit["public_outputs_expose_return_language"] is False
    assert d18_audit["valuation_cannot_trigger_macro_regime"] is True
    assert d18_audit["valuation_cannot_trigger_systemic_review"] is True
    assert d18_audit["proxy_breadth_not_true_breadth"] is True


def test_d18_public_keys_exclude_forbidden_terms():
    keys = set(ModelRegistry().public_output_keys("valuation_equity_structure"))
    text = " ".join(sorted(keys)).lower()

    assert not (keys & FORBIDDEN_EXACT_TERMS)
    for term in FORBIDDEN_EXACT_TERMS:
        assert term not in text


def test_d18_works_with_fake_rows_without_live_data(monkeypatch):
    _block_network(monkeypatch)
    rows = d18.build_valuation_equity_structure_rows(
        [_row("breadth_concentration_proxy", "qqq_vs_spy_30d", -1.0, source_badge="proxy")]
    )

    assert rows
    assert _by_key(rows)["valuation_equity_structure_model_version"]["value"] == "valuation_equity_structure_v0"


def _scenario(rows, scenario_name):
    summary = d16.build_scenario_stress_summary(rows)
    return next(
        item for item in summary["scenarios"] if item["scenario_name"] == scenario_name
    )


def _row(
    module,
    metric_key,
    value,
    *,
    status="ok",
    source_badge="official",
    freshness_status="fresh",
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
        "source": "test_source" if source_badge not in {"missing", "derived"} else "local_rules",
        "source_badge": source_badge,
        "source_series": metric_key.upper(),
        "observation_date": "2026-01-01",
        "generated_at": "2026-01-01T00:00:00+00:00",
        "freshness_status": freshness_status,
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


def _block_network(monkeypatch):
    def _raise_on_network(*args, **kwargs):
        raise AssertionError("Network access is not allowed in D18 tests.")

    monkeypatch.setattr(socket, "create_connection", _raise_on_network)
