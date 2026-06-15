import json

from data_quality import portfolio_exposure_overlay as overlay
from data_quality import macro_regime_review as d15
from data_quality import scenario_stress as d16
from modeling.model_registry import ModelRegistry


def _row(
    metric_key,
    value,
    *,
    module="test",
    status="ok",
    source_badge="derived",
    ai_context_allowed=True,
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
        "source": "local_rules",
        "source_badge": source_badge,
        "source_series": "TEST",
        "observation_date": "2026-06-01",
        "generated_at": "2026-06-01T00:00:00+00:00",
        "freshness_status": "current",
        "missing_reason": None,
        "interpretation_hint": "test",
        "ai_context_allowed": ai_context_allowed,
        "trigger_eligibility": "overlay_only",
    }


def _by_key(rows):
    return {row["metric_key"]: row for row in rows}


def _fake_sanitized_rows():
    return [
        _row("max_deviation_asset", "equity_bucket", module="portfolio_deviation", source_badge="local"),
        _row("max_deviation_pp", 4.0, module="portfolio_deviation", source_badge="local"),
        _row("equity_total_deviation_pp", 1.2, module="portfolio_deviation", source_badge="local"),
        _row(
            "cash_reserve_status",
            "cash_excluded_from_target_allocation",
            module="portfolio_deviation",
            source_badge="local",
        ),
        _row("financial_stress_status", "watch", module="financial_stress_composite"),
        _row("liquidity_funding_stress_status", "ok", module="liquidity_funding_stress"),
        _row("inflation_macro_status", "pressure", module="growth_inflation_macro_pack"),
        _row("growth_macro_status", "limited_context", module="growth_inflation_macro_pack"),
        _row("valuation_context_status", "research_needed", module="valuation_equity_structure", status="research_needed"),
        _row("equity_structure_status", "watch", module="valuation_equity_structure"),
        _row("scenario_stress_status", "available", module="scenario_stress"),
        _row("scenario_stress_scenarios", "inflation_rebound", module="scenario_stress"),
        _row("historical_validation_status", "available", module="historical_validation"),
        _row(
            "historical_validation_coverage_summary",
            "available=2",
            module="historical_validation",
        ),
    ]


def test_stage8_overlay_builds_deterministic_rows_from_fake_sanitized_evidence():
    rows = overlay.build_portfolio_exposure_overlay_rows(_fake_sanitized_rows())
    by_key = _by_key(rows)

    assert set(by_key) == set(ModelRegistry().public_output_keys("portfolio_exposure_overlay"))
    assert by_key["portfolio_exposure_overlay_status"]["value"] == "available"
    assert "inflation_energy" in by_key["portfolio_exposure_primary_channels"]["value"]
    assert by_key["portfolio_exposure_inflation_energy_context"]["value"] == "pressure"
    assert by_key["portfolio_exposure_equity_beta_context"]["value"] == "watch"
    assert by_key["portfolio_exposure_interpretation_boundary"]["ai_context_allowed"] is True

    repeated = overlay.build_portfolio_exposure_overlay_rows(_fake_sanitized_rows())
    comparable = [
        (row["metric_key"], row["value"], row["status"], row["source_badge"])
        for row in rows
    ]
    repeated_comparable = [
        (row["metric_key"], row["value"], row["status"], row["source_badge"])
        for row in repeated
    ]
    assert comparable == repeated_comparable


def test_missing_sanitized_portfolio_context_is_not_low_or_high_exposure():
    rows = overlay.build_portfolio_exposure_overlay_rows(
        [_row("financial_stress_status", "pressure", module="financial_stress_composite")]
    )
    by_key = _by_key(rows)
    contributions = by_key["portfolio_exposure_overlay_status"]["component_contributions"]

    assert by_key["portfolio_exposure_overlay_status"]["value"] == "private_inputs_excluded"
    assert by_key["portfolio_exposure_overlay_status"]["status"] == "insufficient_evidence"
    assert "sanitized_portfolio_context" in by_key["portfolio_exposure_missing_inputs"]["value"]
    assert contributions["channels"]["equity_beta"]["status"] == "private_input_excluded"
    assert contributions["channels"]["equity_beta"]["hard_gates"][
        "missing_sanitized_context_not_low_or_high"
    ] is True


def test_overlay_does_not_expose_private_or_position_level_details():
    raw_like_rows = _fake_sanitized_rows() + [
        _row("holdings", [{"ticker": "RAW_FUND", "amount": 999}], module="portfolio_deviation"),
        _row("account_value", 999999, module="portfolio_deviation"),
        _row("position_weight", 0.5, module="portfolio_deviation"),
    ]
    output = overlay.build_portfolio_exposure_overlay_rows(raw_like_rows)
    body = json.dumps(output, sort_keys=True).lower()

    assert "raw_fund" not in body
    assert "999999" not in body
    assert '"position_weight"' not in body
    assert '"account_value"' not in body
    assert "ticker" not in body


def test_overlay_boundary_flags_preserve_downstream_only_contracts():
    rows = overlay.build_portfolio_exposure_overlay_rows(_fake_sanitized_rows())
    contributions = _by_key(rows)["portfolio_exposure_overlay_status"]["component_contributions"]
    hard_gates = contributions["hard_gates"]

    assert hard_gates["portfolio_overlay_cannot_trigger_macro_regime"] is True
    assert hard_gates["portfolio_overlay_cannot_trigger_systemic_stress"] is True
    assert hard_gates["portfolio_overlay_cannot_change_scenario_severity"] is True
    assert hard_gates["portfolio_overlay_downstream_only"] is True
    assert hard_gates["reads_holdings_line_items"] is False
    assert hard_gates["returns_holdings_line_items"] is False
    assert hard_gates["returns_position_weights"] is False
    assert hard_gates["returns_account_values"] is False


def test_channel_contexts_do_not_become_action_instructions():
    rows = overlay.build_portfolio_exposure_overlay_rows(_fake_sanitized_rows())
    body = json.dumps(rows, sort_keys=True).lower()

    for phrase in (
        "trade signal",
        "buy",
        "sell",
        "hedge",
        "rebalance",
        "target weight",
        "ideal allocation",
        "add position",
        "reduce position",
        "clear position",
        "de-risk",
        "rotate into",
        "overweight",
        "underweight",
    ):
        assert phrase not in body


def test_overlay_rows_do_not_change_d15_or_d16_outputs():
    base = _fake_sanitized_rows()
    overlay_rows = overlay.build_portfolio_exposure_overlay_rows(base)

    d15_base = _by_key(d15.build_macro_regime_review_rows(base))
    d15_with_overlay = _by_key(d15.build_macro_regime_review_rows(base + overlay_rows))
    assert d15_base["macro_regime_label"]["value"] == d15_with_overlay[
        "macro_regime_label"
    ]["value"]
    assert d15_base["primary_pressure_ranking"]["value"] == d15_with_overlay[
        "primary_pressure_ranking"
    ]["value"]

    d16_base = d16.build_scenario_stress_summary(base)
    d16_with_overlay = d16.build_scenario_stress_summary(base + overlay_rows)
    assert d16_base["status"] == d16_with_overlay["status"]
    assert d16_base["severity_band"] == d16_with_overlay["severity_band"]
    assert d16_base["primary_scenario"] == d16_with_overlay["primary_scenario"]
