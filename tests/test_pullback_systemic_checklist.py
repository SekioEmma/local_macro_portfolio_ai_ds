from data_quality import pullback_systemic_checklist as checklist


def test_equity_drawdown_alone_is_not_systemic_risk_review():
    rows = [
        _row("credit_stress", "high_yield_spread", 2.6),
        _row("credit_stress", "investment_grade_spread", 0.8),
        _row("market_stress_derived", "sp500_drawdown_3m", -18.0, badge="derived"),
    ]

    result = _by_key(checklist.build_pullback_checklist_rows(rows))

    assert result["pullback_classification"]["value"] in {
        "ordinary_pullback",
        "valuation_drawdown",
    }
    assert result["pullback_classification"]["value"] != "systemic_risk_review"


def test_vix_alone_is_not_systemic_risk_review():
    rows = [
        _row("credit_stress", "high_yield_spread", 2.6),
        _row("credit_stress", "investment_grade_spread", 0.8),
        _row("credit_stress", "vix", 40.0, source="CBOE"),
    ]

    result = _by_key(checklist.build_pullback_checklist_rows(rows))

    assert result["pullback_classification"]["value"] == "ordinary_pullback"
    assert result["pullback_classification"]["value"] != "systemic_risk_review"


def test_credit_stable_and_drawdown_classifies_as_pullback_or_valuation_drawdown():
    rows = [
        _row("credit_stress", "high_yield_spread", 2.7),
        _row("credit_stress", "investment_grade_spread", 0.7),
        _row("market_stress_derived", "nasdaq100_drawdown_6m", -13.0, badge="derived"),
    ]

    result = _by_key(checklist.build_pullback_checklist_rows(rows))

    assert result["pullback_classification"]["value"] in {
        "ordinary_pullback",
        "valuation_drawdown",
    }


def test_credit_worsening_vix_and_drawdown_classifies_as_credit_warning():
    rows = [
        _row("credit_stress", "high_yield_spread", 5.2),
        _row("credit_stress", "investment_grade_spread", 1.7),
        _row("credit_stress", "vix", 31.0, source="CBOE"),
        _row("market_stress_derived", "sp500_drawdown_3m", -14.0, badge="derived"),
    ]

    result = _by_key(checklist.build_pullback_checklist_rows(rows))

    assert result["pullback_classification"]["value"] in {
        "credit_warning",
        "macro_pressure",
    }


def test_financial_stress_credit_and_labor_pressure_can_trigger_systemic_review():
    rows = [
        _row("financial_stress_composite", "financial_stress_status", "pressure", badge="derived"),
        _row("credit_stress", "high_yield_spread", 6.8),
        _row("credit_stress", "investment_grade_spread", 2.2),
        _row("credit_stress", "vix", 38.0, source="CBOE"),
        _row("market_stress_derived", "sp500_drawdown_3m", -22.0, badge="derived"),
        _row("labor_macro", "labor_deterioration_status", "pressure", badge="derived"),
    ]

    result = _by_key(checklist.build_pullback_checklist_rows(rows))

    assert result["pullback_classification"]["value"] == "systemic_risk_review"
    assert result["pullback_classification"]["status"] == "stress"


def test_missing_credit_inputs_returns_insufficient_evidence():
    rows = [
        _row("credit_stress", "vix", 38.0, source="CBOE"),
        _row("market_stress_derived", "sp500_drawdown_3m", -22.0, badge="derived"),
    ]

    result = _by_key(checklist.build_pullback_checklist_rows(rows))

    assert result["pullback_classification"]["value"] == "insufficient_evidence"
    assert result["pullback_classification"]["ai_context_allowed"] is False
    assert "high_yield_spread" in result["pullback_classification"]["missing_inputs"]


def test_proxy_only_evidence_does_not_trigger_systemic_review():
    rows = [
        _row("credit_stress", "high_yield_spread", 7.0, badge="proxy", source="proxy"),
        _row("credit_stress", "investment_grade_spread", 2.5, badge="proxy", source="proxy"),
        _row("credit_stress", "vix", 40.0, badge="proxy", source="proxy"),
        _row("market_stress_derived", "sp500_drawdown_3m", -25.0, badge="proxy", source="proxy"),
        _row("labor_macro", "labor_deterioration_status", "pressure", badge="derived"),
    ]

    result = _by_key(checklist.build_pullback_checklist_rows(rows))

    assert result["pullback_classification"]["value"] != "systemic_risk_review"


def test_missing_critical_inputs_are_always_reported():
    rows = [
        _row("credit_stress", "high_yield_spread", 2.8),
        _row("credit_stress", "investment_grade_spread", 0.8),
    ]

    result = _by_key(checklist.build_pullback_checklist_rows(rows))
    missing = result["pullback_missing_critical_inputs"]["missing_inputs"]

    assert {"valuation", "earnings", "true_breadth", "liquidity"} <= set(missing)


def test_checklist_rows_preserve_input_evidence_and_source_badge():
    rows = [
        _row("credit_stress", "high_yield_spread", 4.0),
        _row("credit_stress", "investment_grade_spread", 1.1),
        _row("market_stress_derived", "hyg_vs_lqd_30d", -3.0, badge="proxy"),
    ]

    result = _by_key(checklist.build_pullback_checklist_rows(rows))
    items = result["pullback_checklist_items"]["component_contributions"][
        "checklist_items"
    ]
    credit_item = _item(items, "credit_spread_confirmation")
    proxy_item = _item(items, "cross_asset_proxy_confirmation")

    assert credit_item["evidence"][0]["metric_key"] == "high_yield_spread"
    assert credit_item["evidence"][0]["source_badge"] == "official"
    assert proxy_item["evidence"][0]["source_badge"] == "proxy"


def test_boundary_does_not_contain_recession_probability_or_trading_advice_claim():
    rows = [
        _row("credit_stress", "high_yield_spread", 2.8),
        _row("credit_stress", "investment_grade_spread", 0.8),
    ]

    result = _by_key(checklist.build_pullback_checklist_rows(rows))
    boundary = result["pullback_interpretation_boundary"]["value"]

    assert "recession probability" not in boundary.lower()
    assert "This checklist is not crash probability." in boundary
    assert "It does not produce buy/sell/hedge instructions." in boundary


def _row(
    module,
    metric_key,
    value,
    *,
    status="ok",
    badge="official",
    source="FRED",
):
    return {
        "module": module,
        "metric_key": metric_key,
        "display_name": metric_key,
        "value": value,
        "value_text": str(value),
        "unit": None,
        "status": status,
        "source": source,
        "source_badge": badge,
        "source_series": metric_key.upper(),
        "observation_date": "2026-06-01",
        "generated_at": "2026-06-01T00:00:00+00:00",
        "freshness_status": "fresh",
        "missing_reason": None,
        "interpretation_hint": "test input",
        "blocked_reason": None,
        "ai_context_allowed": status == "ok",
    }


def _by_key(rows):
    return {row["metric_key"]: row for row in rows}


def _item(items, key):
    for item in items:
        if item["key"] == key:
            return item
    raise AssertionError(f"missing checklist item {key}")
