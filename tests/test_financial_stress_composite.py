from data_quality import financial_stress_composite as composite


def test_core_credit_missing_blocks_total_score():
    rows = [_row("credit_stress", "vix", 38.0, source="CBOE")]

    result = _by_key(composite.build_financial_stress_rows(rows))

    assert result["financial_stress_score"]["value"] is None
    assert result["financial_stress_score"]["status"] == "insufficient_evidence"
    assert result["financial_stress_score"]["ai_context_allowed"] is False
    assert "high_yield_spread" in result["financial_stress_score"]["missing_inputs"]
    assert "investment_grade_spread" in result["financial_stress_score"]["missing_inputs"]


def test_vix_alone_high_cannot_trigger_stress():
    rows = [
        _row("credit_stress", "high_yield_spread", 2.5),
        _row("credit_stress", "investment_grade_spread", 0.8),
        _row("credit_stress", "vix", 40.0, source="CBOE"),
    ]

    result = _by_key(composite.build_financial_stress_rows(rows))

    assert result["financial_stress_status"]["value"] == "watch"
    assert result["financial_stress_score"]["value"] <= 44.0


def test_equity_drawdown_alone_cannot_trigger_stress():
    rows = [
        _row("credit_stress", "high_yield_spread", 2.5),
        _row("credit_stress", "investment_grade_spread", 0.8),
        _row("market_stress_derived", "sp500_drawdown_3m", -25.0, badge="derived"),
        _row("market_stress_derived", "sp500_drawdown_6m", -24.0, badge="derived"),
        _row("market_stress_derived", "nasdaq100_drawdown_3m", -30.0, badge="derived"),
        _row("market_stress_derived", "nasdaq100_drawdown_6m", -28.0, badge="derived"),
    ]

    result = _by_key(composite.build_financial_stress_rows(rows))

    assert result["financial_stress_status"]["value"] != "stress"
    assert result["financial_stress_score"]["value"] <= 69.0


def test_credit_spreads_vix_and_drawdown_can_enter_pressure():
    rows = [
        _row("credit_stress", "high_yield_spread", 7.0),
        _row("credit_stress", "investment_grade_spread", 2.2),
        _row("credit_stress", "vix", 36.0, source="CBOE"),
        _row("market_stress_derived", "sp500_drawdown_3m", -22.0, badge="derived"),
        _row("market_stress_derived", "nasdaq100_drawdown_3m", -25.0, badge="derived"),
    ]

    result = _by_key(composite.build_financial_stress_rows(rows))

    assert result["financial_stress_status"]["value"] in {"pressure", "stress"}
    assert result["financial_stress_score"]["value"] >= 45.0
    assert result["financial_stress_dominant_pressure_source"]["value"] == "credit_conditions"


def test_proxy_only_evidence_cannot_trigger_stress():
    rows = [
        _row("credit_stress", "high_yield_spread", 8.0, badge="proxy"),
        _row("credit_stress", "investment_grade_spread", 3.0, badge="proxy"),
        _row("credit_stress", "vix", 45.0, badge="proxy", source="proxy"),
        _row("market_stress_derived", "sp500_drawdown_3m", -30.0, badge="proxy"),
        _row("labor_macro", "labor_deterioration_status", "pressure", badge="derived"),
    ]

    result = _by_key(composite.build_financial_stress_rows(rows))

    assert result["financial_stress_status"]["value"] != "stress"
    assert result["financial_stress_score"]["value"] <= 69.0


def test_no_contributions_means_no_total_score():
    result = _by_key(composite.build_financial_stress_rows([]))

    assert result["financial_stress_score"]["value"] is None
    assert result["financial_stress_score"]["status"] == "missing"
    assert result["financial_stress_score"]["component_contributions"][
        "credit_conditions"
    ]["inputs"] == []


def test_contributions_preserve_input_evidence_and_source_badge():
    rows = [
        _row("credit_stress", "high_yield_spread", 4.0),
        _row("credit_stress", "investment_grade_spread", 1.1),
        _row("labor_macro", "labor_deterioration_status", "watch", badge="derived"),
    ]

    result = _by_key(composite.build_financial_stress_rows(rows))
    contributions = result["financial_stress_score"]["component_contributions"]

    credit_input = contributions["credit_conditions"]["inputs"][0]
    labor_input = contributions["labor_deterioration"]["inputs"][0]
    assert credit_input["metric_key"] == "high_yield_spread"
    assert credit_input["source_badge"] == "official"
    assert labor_input["metric_key"] == "labor_deterioration_status"
    assert labor_input["source_badge"] == "derived"


def test_percentile_context_is_auxiliary_and_preserved():
    rows = [
        _row("credit_stress", "high_yield_spread", 2.5),
        _row("credit_stress", "investment_grade_spread", 0.8),
        _d13("vix_percentile", "extreme"),
        _d13("dgs30_percentile", "high"),
        _d13("high_yield_spread_percentile", None, status="insufficient_history"),
    ]

    result = _by_key(composite.build_financial_stress_rows(rows))
    context = result["financial_stress_score"]["component_contributions"]["percentile_context"]

    assert result["financial_stress_percentile_context"]["status"] == "ok"
    assert context["available_count"] == 2
    assert "high_yield_spread_percentile" in [
        item["metric_key"] for item in context["missing"]
    ]
    assert "not forecast probability" in context["normalization_boundary"]


def test_extreme_vix_percentile_alone_does_not_trigger_stress():
    rows = [
        _row("credit_stress", "high_yield_spread", 2.5),
        _row("credit_stress", "investment_grade_spread", 0.8),
        _d13("vix_percentile", "extreme"),
        _d13("vix_robust_zscore", "extreme", robust_band="extreme"),
    ]

    result = _by_key(composite.build_financial_stress_rows(rows))

    assert result["financial_stress_status"]["value"] == "ok"
    assert result["financial_stress_score"]["value"] < 25


def test_extreme_drawdown_percentile_alone_does_not_trigger_stress():
    rows = [
        _row("credit_stress", "high_yield_spread", 2.5),
        _row("credit_stress", "investment_grade_spread", 0.8),
        _d13("sp500_drawdown_3m_percentile", "extreme"),
        _d13("nasdaq100_drawdown_3m_percentile", "extreme"),
    ]

    result = _by_key(composite.build_financial_stress_rows(rows))

    assert result["financial_stress_status"]["value"] == "ok"
    assert result["financial_stress_score"]["value"] < 25


def test_missing_research_stale_and_insufficient_inputs_are_not_strong_evidence():
    rows = [
        _row("credit_stress", "high_yield_spread", 6.5, status="stale"),
        _row("credit_stress", "investment_grade_spread", 2.2, status="research_needed"),
        _row(
            "market_stress_derived",
            "sp500_drawdown_3m",
            -25.0,
            status="insufficient_history",
            badge="derived",
        ),
    ]

    result = _by_key(composite.build_financial_stress_rows(rows))

    assert result["financial_stress_status"]["value"] == "insufficient_evidence"
    assert result["financial_stress_score"]["value"] is None


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


def _d13(metric_key, percentile_band, *, status="ok", robust_band=None):
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
        "robust_zscore_band": robust_band,
        "percentile_direction": "higher_is_more_stress",
        "frequency_class": "daily_or_weekly_market",
        "ai_context_tier": "factual_band" if status == "ok" else "excluded",
        "trigger_eligibility": "hard_trigger_allowed" if status == "ok" else "not_eligible",
        "interpretation_boundary": "Historical percentile is relative to available local history, not a forecast.",
    }


def _by_key(rows):
    return {row["metric_key"]: row for row in rows}
