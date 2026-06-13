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
        _d14("liquidity_funding_stress_status", "pressure"),
        _d14("short_term_funding_pressure_status", "pressure"),
        _d14("official_stress_reference_status", "pressure"),
        _d14("cp_effr_spread", 1.2),
        _d14("stl_fsi", 1.1, badge="official_fallback"),
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


def test_liquidity_missing_removed_when_d14_usable():
    rows = [
        _row("credit_stress", "high_yield_spread", 2.8),
        _row("credit_stress", "investment_grade_spread", 0.8),
        _d14("liquidity_funding_stress_status", "ok"),
        _d14("short_term_funding_pressure_status", "ok"),
        _d14("official_stress_reference_status", "ok"),
    ]

    result = _by_key(checklist.build_pullback_checklist_rows(rows))
    missing = result["pullback_missing_critical_inputs"]["missing_inputs"]
    context = result["pullback_classification"]["component_contributions"][
        "pullback_liquidity_funding_context"
    ]

    assert "liquidity" not in missing
    assert {"valuation", "earnings", "true_breadth"} <= set(missing)
    assert context["liquidity_available"] is True
    assert result["pullback_liquidity_funding_context"]["status"] == "ok"


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


def test_checklist_items_include_percentile_evidence_and_rarity_note():
    rows = [
        _row("credit_stress", "high_yield_spread", 2.8),
        _row("credit_stress", "investment_grade_spread", 0.8),
        _row("market_stress_derived", "sp500_drawdown_3m", -10.0, badge="derived"),
        _d13("sp500_drawdown_3m_percentile", "high"),
        _d13("vix_percentile", "extreme"),
    ]

    result = _by_key(checklist.build_pullback_checklist_rows(rows))
    items = result["pullback_checklist_items"]["component_contributions"]["checklist_items"]
    equity_item = _item(items, "equity_damage")

    assert result["pullback_percentile_context"]["status"] == "ok"
    assert equity_item["percentile_evidence"]
    assert "D13 auxiliary rarity bands" in equity_item["rarity_note"]


def test_percentile_only_cannot_trigger_systemic_and_liquidity_gap_remains():
    rows = [
        _row("credit_stress", "high_yield_spread", 2.8),
        _row("credit_stress", "investment_grade_spread", 0.8),
        _d13("sp500_drawdown_3m_percentile", "extreme"),
        _d13("vix_percentile", "extreme"),
        _d13("dgs30_percentile", "extreme"),
    ]

    result = _by_key(checklist.build_pullback_checklist_rows(rows))
    context = result["pullback_classification"]["component_contributions"][
        "pullback_percentile_context"
    ]
    missing = result["pullback_missing_critical_inputs"]["missing_inputs"]

    assert result["pullback_classification"]["value"] != "systemic_risk_review"
    assert {"liquidity", "valuation", "earnings", "true_breadth"} <= set(missing)
    assert context["systemic_not_triggered_by_percentile_only"] is True
    assert context["liquidity_still_missing_until_d14"] is False


def test_d14_only_cannot_trigger_systemic():
    rows = [
        _row("credit_stress", "high_yield_spread", 2.8),
        _row("credit_stress", "investment_grade_spread", 0.8),
        _d14("liquidity_funding_stress_status", "stress"),
        _d14("short_term_funding_pressure_status", "stress"),
        _d14("official_stress_reference_status", "stress"),
    ]

    result = _by_key(checklist.build_pullback_checklist_rows(rows))

    assert result["pullback_classification"]["value"] != "systemic_risk_review"


def test_cp_only_and_official_reference_only_cannot_trigger_systemic():
    cp_only = [
        _row("financial_stress_composite", "financial_stress_status", "pressure", badge="derived"),
        _row("credit_stress", "high_yield_spread", 6.8),
        _row("credit_stress", "investment_grade_spread", 2.2),
        _d14("short_term_funding_pressure_status", "pressure"),
        _d14("cp_effr_spread", 1.5),
    ]
    reference_only = [
        _row("financial_stress_composite", "financial_stress_status", "pressure", badge="derived"),
        _row("credit_stress", "high_yield_spread", 6.8),
        _row("credit_stress", "investment_grade_spread", 2.2),
        _d14("official_stress_reference_status", "stress"),
        _d14("stl_fsi", 2.5, badge="official_fallback"),
    ]

    assert _by_key(checklist.build_pullback_checklist_rows(cp_only))[
        "pullback_classification"
    ]["value"] != "systemic_risk_review"
    assert _by_key(checklist.build_pullback_checklist_rows(reference_only))[
        "pullback_classification"
    ]["value"] != "systemic_risk_review"


def test_boundary_does_not_contain_recession_probability_or_trading_advice_claim():
    rows = [
        _row("credit_stress", "high_yield_spread", 2.8),
        _row("credit_stress", "investment_grade_spread", 0.8),
    ]

    result = _by_key(checklist.build_pullback_checklist_rows(rows))
    boundary = result["pullback_interpretation_boundary"]["value"]

    assert "This checklist is not crash probability." in boundary
    assert "D14 does not produce recession probability." in boundary
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


def _d13(metric_key, percentile_band, *, status="ok"):
    return {
        "module": "historical_risk_percentile",
        "metric_key": metric_key,
        "display_name": metric_key,
        "value": 95.0 if status == "ok" else None,
        "value_text": "95 percentile" if status == "ok" else "insufficient history",
        "unit": "percentile",
        "status": status,
        "source": "local_market_history",
        "source_badge": "derived",
        "source_series": metric_key.upper(),
        "observation_date": "2026-06-01",
        "generated_at": "2026-06-01T00:00:00+00:00",
        "freshness_status": "historical" if status == "ok" else "insufficient_history",
        "missing_reason": None if status == "ok" else "insufficient_history_for_percentile",
        "interpretation_hint": "D13 auxiliary context",
        "blocked_reason": None if status == "ok" else "status_insufficient_history",
        "ai_context_allowed": status == "ok",
        "lookback_window": "5Y rolling",
        "lookback_start": "2021-06-01",
        "lookback_end": "2026-06-01",
        "observation_count": 1200 if status == "ok" else 20,
        "minimum_observation_count": 60,
        "history_quality_status": "sufficient" if status == "ok" else "insufficient_history",
        "percentile": 95.0 if percentile_band else None,
        "percentile_band": percentile_band,
        "zscore_band": None,
        "robust_zscore_band": None,
        "percentile_direction": "higher_is_more_stress",
        "frequency_class": "daily_or_weekly_market",
        "ai_context_tier": "factual_band" if status == "ok" else "excluded",
        "trigger_eligibility": "hard_trigger_allowed" if status == "ok" else "not_eligible",
        "interpretation_boundary": "Historical percentile is relative to available local history, not a forecast.",
    }


def _d14(metric_key, value, *, status="ok", badge="derived"):
    return {
        "module": "liquidity_funding_stress",
        "metric_key": metric_key,
        "display_name": metric_key,
        "value": value if status == "ok" else None,
        "value_text": str(value) if status == "ok" else status,
        "unit": None,
        "status": status,
        "source": "market_history" if badge == "derived" else "FRED",
        "source_badge": badge,
        "source_series": metric_key.upper(),
        "observation_date": "2026-06-01",
        "generated_at": "2026-06-01T00:00:00+00:00",
        "freshness_status": "historical" if status == "ok" else status,
        "missing_reason": None if status == "ok" else "status_inputs_missing",
        "interpretation_hint": "D14 funding confirmation context",
        "blocked_reason": None if status == "ok" else f"status_{status}",
        "ai_context_allowed": status == "ok",
        "input_evidence": [],
        "missing_inputs": [] if status == "ok" else [metric_key],
        "interpretation_boundary": "Liquidity/funding stress rows are reference evidence, not trading signals.",
    }


def _by_key(rows):
    return {row["metric_key"]: row for row in rows}


def _item(items, key):
    for item in items:
        if item["key"] == key:
            return item
    raise AssertionError(f"missing checklist item {key}")
