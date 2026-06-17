import json
import socket

import audit_data_pipeline_coverage as audit
from data_quality import scenario_stress as d16
from modeling.model_registry import ModelRegistry


EXPECTED_SCENARIOS = {
    "high_rates_stay_high",
    "inflation_rebound",
    "credit_spread_widening",
    "liquidity_funding_squeeze",
    "growth_slowdown",
    "stagflation_pressure",
    "ai_mega_cap_concentration_unwind",
}
FORBIDDEN_EXACT_TERMS = {
    "scenario_probability",
    "crash_probability",
    "recession_probability",
    "market_direction_probability",
    "expected_return",
    "trade_signal",
    "target_allocation",
}


def test_scenario_registry_includes_all_seven_scenarios():
    names = {item.scenario_name for item in d16.get_scenario_registry()}

    assert names == EXPECTED_SCENARIOS


def test_scenario_result_fails_closed_when_required_evidence_is_missing():
    summary = d16.build_scenario_stress_summary([])

    assert summary["status"] == "insufficient_evidence"
    assert summary["primary_scenario"] == "none"
    assert all(
        item["scenario_status"] == "insufficient_evidence"
        for item in summary["scenarios"]
    )


def test_proxy_only_evidence_cannot_produce_strong_or_high_severity():
    scenario = _scenario(
        [
            _row("breadth_concentration_proxy", "qqq_vs_spy_30d", value=-5.0, status="pressure", source_badge="proxy"),
            _row("breadth_concentration_proxy", "spy_vs_rsp_30d", value=-3.0, status="pressure", source_badge="proxy"),
        ],
        "ai_mega_cap_concentration_unwind",
    )

    assert scenario["support_band"] != "strong"
    assert scenario["severity_band"] not in {"severe", "extreme"}
    assert scenario["uncertainty_band"] == "high"


def test_oil_alone_cannot_trigger_inflation_rebound_strong_support():
    scenario = _scenario(
        [_row("inflation_energy_pressure", "wti_30d_change", value=8.0, status="pressure")],
        "inflation_rebound",
    )

    assert scenario["support_band"] == "weak"
    assert scenario["severity_band"] == "mild"


def test_vix_alone_cannot_trigger_credit_spread_widening_strong_support():
    scenario = _scenario(
        [_row("credit_stress", "vix", value=31.0, status="pressure")],
        "credit_spread_widening",
    )

    assert scenario["support_band"] == "weak"
    assert scenario["severity_band"] == "mild"


def test_d14_liquidity_alone_cannot_trigger_strong_funding_squeeze():
    scenario = _scenario(
        [
            _row(
                "liquidity_funding_stress",
                "liquidity_funding_stress_status",
                value="pressure",
                status="pressure",
                source_badge="derived",
            )
        ],
        "liquidity_funding_squeeze",
    )

    assert scenario["support_band"] == "weak"
    assert scenario["severity_band"] == "mild"


def test_labor_watch_alone_avoids_cycle_call_language():
    rows = d16.build_scenario_stress_rows(
        [
            _row(
                "labor_macro",
                "labor_deterioration_status",
                value="watch",
                status="watch",
                source_badge="derived",
            )
        ]
    )
    serialized = json.dumps(rows, ensure_ascii=False).lower()

    assert "recession" not in serialized


def test_ai_mega_cap_concentration_keeps_missing_constraints_visible():
    scenario = _scenario(
        [
            _row("breadth_concentration_proxy", "qqq_vs_spy_30d", value=-4.0, status="pressure", source_badge="proxy"),
            _row("market_stress_derived", "nasdaq100_drawdown_3m", value=-11.0, status="pressure", source_badge="derived"),
        ],
        "ai_mega_cap_concentration_unwind",
    )

    assert {"valuation", "earnings", "true_breadth"} <= set(scenario["missing_inputs"])


def test_public_output_keys_exclude_forbidden_terms():
    keys = set(ModelRegistry().public_output_keys("scenario_stress"))
    text = " ".join(sorted(keys)).lower()

    assert not (keys & FORBIDDEN_EXACT_TERMS)
    for term in FORBIDDEN_EXACT_TERMS:
        assert term not in text


def test_d16_is_registered_in_model_registry():
    registration = ModelRegistry().require("scenario_stress")

    assert registration.model_key == "scenario_stress_v0"
    assert registration.category == "model_output"


def test_d16_audit_section_exists_and_leak_flags_are_false(monkeypatch, tmp_path):
    _block_network(monkeypatch)
    _write_json(
        tmp_path / "market_snapshot.json",
        {
            "generated_at": "2026-01-01T00:00:00+00:00",
            "status": "ok",
            "dgs10": {
                "value": 4.5,
                "status": "ok",
                "source": "FRED",
                "source_badge": "official",
                "observation_date": "2026-01-01",
                "freshness_status": "fresh",
            },
        },
    )

    result = audit.build_coverage_audit(reports_dir=tmp_path)
    d16_audit = result["scenario_stress"]

    assert d16_audit["scenario_count"] == 7
    assert d16_audit["public_outputs_expose_probability_language"] is False
    assert d16_audit["public_outputs_expose_trading_language"] is False
    assert d16_audit["uses_model_registry"] is True
    assert d16_audit["uses_evidence_index"] is True


def test_d16_compact_rows_have_stable_public_contract():
    rows = d16.build_scenario_stress_rows([])
    keys = {row["metric_key"] for row in rows}

    assert keys == set(ModelRegistry().public_output_keys("scenario_stress"))
    assert len(rows) == 14


def test_d16_works_with_fake_rows_without_live_data(monkeypatch):
    _block_network(monkeypatch)
    rows = d16.build_scenario_stress_rows(
        [
            _row("rate_pressure", "dgs10", value=4.8, status="pressure"),
            _row("real_yield_pressure", "dfii10", value=2.1, status="pressure"),
        ]
    )

    assert rows
    assert _by_key(rows, "scenario_stress_scenario_count")["value"] == 7


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


def _by_key(rows, metric_key):
    return {row["metric_key"]: row for row in rows}[metric_key]


def _write_json(path, payload):
    path.write_text(json.dumps(payload), encoding="utf-8")


def _block_network(monkeypatch):
    def _raise_on_network(*args, **kwargs):
        raise AssertionError("Network access is not allowed in D16 tests.")

    monkeypatch.setattr(socket, "create_connection", _raise_on_network)
