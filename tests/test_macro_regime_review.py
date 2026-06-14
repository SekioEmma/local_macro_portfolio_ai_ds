from data_quality import macro_regime_review as d15


def test_d15_rates_pressure_requires_two_core_rates_inputs():
    rows = [
        _row("rate_pressure", "dgs10", 4.5),
        _row("rate_pressure", "dfii10", 2.1),
        _row("real_yield_pressure", "real_yield_pressure_status", "pressure", status="pressure"),
        _row("credit_stress", "high_yield_spread", 3.4),
        _row("inflation_energy_pressure", "core_cpi_yoy", 3.1),
        _row("labor_macro", "initial_jobless_claims", 230000),
        _row("labor_macro", "unemployment_rate", 4.0),
    ]

    result = _by_key(d15.build_macro_regime_review_rows(rows))

    assert result["macro_regime_label"]["value"] == "rates_pressure"
    assert result["support_band"]["value"] in {"moderate", "strong"}
    assert result["macro_regime_label"]["ai_context_allowed"] is True


def test_d15_vix_alone_cannot_trigger_credit_stress():
    rows = [
        _row("credit_stress", "vix", 35.0, status="pressure"),
        _row("rate_pressure", "dgs10", 4.5),
        _row("rate_pressure", "dfii10", 2.1),
        _row("inflation_energy_pressure", "core_cpi_yoy", 3.1),
        _row("labor_macro", "initial_jobless_claims", 230000),
        _row("labor_macro", "unemployment_rate", 4.0),
    ]

    result = _by_key(d15.build_macro_regime_review_rows(rows))

    assert result["macro_regime_label"]["value"] != "credit_stress"
    gates = result["macro_regime_label"]["component_contributions"]["hard_gates"]
    assert gates["vix_alone_cannot_trigger_credit_stress"] is True


def test_d15_d14_alone_cannot_trigger_liquidity_funding_pressure():
    rows = [
        _row(
            "liquidity_funding_stress",
            "liquidity_funding_stress_status",
            "pressure",
            status="pressure",
            source_badge="derived",
            freshness_status="historical",
        )
    ]

    result = _by_key(d15.build_macro_regime_review_rows(rows))

    assert result["macro_regime_label"]["value"] == "insufficient_evidence"
    assert result["macro_regime_label"]["ai_context_allowed"] is False
    gates = result["macro_regime_label"]["component_contributions"]["hard_gates"]
    assert gates["d14_alone_cannot_trigger_liquidity_or_systemic_regime"] is True


def test_d15_oil_alone_cannot_trigger_inflation_energy_pressure():
    rows = [
        _row("inflation_energy_pressure", "wti_30d_change", 12.0, status="pressure"),
        _row("inflation_energy_pressure", "brent_30d_change", 11.0, status="pressure"),
        _row("rate_pressure", "dgs10", 4.5),
        _row("rate_pressure", "dfii10", 2.1),
        _row("credit_stress", "high_yield_spread", 3.4),
        _row("labor_macro", "initial_jobless_claims", 230000),
        _row("labor_macro", "unemployment_rate", 4.0),
    ]

    result = _by_key(d15.build_macro_regime_review_rows(rows))

    assert result["macro_regime_label"]["value"] != "inflation_energy_pressure"
    assert "core_inflation_input" in result["macro_regime_label"]["missing_inputs"]


def test_d15_public_outputs_do_not_expose_scores_or_probability_language():
    rows = [
        _row("credit_stress", "high_yield_spread", 3.4),
        _row("rate_pressure", "dgs10", 4.5),
        _row("rate_pressure", "dfii10", 2.1),
        _row("inflation_energy_pressure", "core_cpi_yoy", 3.1),
        _row("labor_macro", "initial_jobless_claims", 230000),
        _row("labor_macro", "unemployment_rate", 4.0),
    ]

    result = d15.build_macro_regime_review_rows(rows)
    serialized = str(result).lower()

    assert "macro_regime_score" not in serialized
    assert "support_score_internal" not in serialized
    assert "group_score_internal" not in serialized
    assert "crash probability" not in serialized
    assert "recession probability" not in serialized


def _by_key(rows):
    return {row["metric_key"]: row for row in rows}


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
        "source": "test_source",
        "source_badge": source_badge,
        "source_series": metric_key.upper(),
        "observation_date": "2026-06-01",
        "generated_at": "2026-06-01T00:00:00+00:00",
        "freshness_status": freshness_status,
        "missing_reason": None,
        "interpretation_hint": "test evidence",
        "blocked_reason": None,
        "ai_context_allowed": True,
    }

