import math

from data_quality import historical_derived_metrics as derived
from data_providers import market_history_store

from tests.helpers.dashboard_fixtures import block_network_calls


def test_period_return_with_sufficient_history(tmp_path):
    db_path = tmp_path / "market_history.sqlite3"
    _insert(db_path, "sp500", "2026-01-01", 100.0)
    _insert(db_path, "sp500", "2026-02-01", 110.0)

    result = derived.calculate_period_return("sp500", 30, db_path=db_path)

    assert result.status == "ok"
    assert math.isclose(result.value, 0.10)
    assert result.source_badge == "derived"
    assert "sp500" in result.dependency_keys
    assert "period_return" in result.calculation
    assert "sp500" in result.interpretation_hint


def test_period_return_with_insufficient_history(tmp_path):
    db_path = tmp_path / "market_history.sqlite3"
    _insert(db_path, "sp500", "2026-02-01", 110.0)

    result = derived.calculate_period_return("sp500", 30, db_path=db_path)

    assert result.status == "insufficient_history"
    assert result.ai_context_allowed is False
    assert result.history_points_used == 1


def test_rolling_average_with_sufficient_points(tmp_path):
    db_path = tmp_path / "market_history.sqlite3"
    for day, value in enumerate([1, 2, 3, 4, 5], start=1):
        _insert(db_path, "dgs10", f"2026-01-0{day}", float(value))

    result = derived.calculate_rolling_average("dgs10", 5, db_path=db_path)

    assert result.status == "ok"
    assert result.value == 3.0
    assert result.history_points_used == 5
    assert result.history_points_required == 5


def test_rolling_average_with_insufficient_points(tmp_path):
    db_path = tmp_path / "market_history.sqlite3"
    _insert(db_path, "dgs10", "2026-01-01", 1.0)

    result = derived.calculate_rolling_average("dgs10", 5, db_path=db_path)

    assert result.status == "insufficient_history"
    assert result.ai_context_allowed is False
    assert result.missing_reason == "history_points_insufficient"


def test_relative_return_with_sufficient_history(tmp_path):
    db_path = tmp_path / "market_history.sqlite3"
    _insert(db_path, "nasdaq100", "2026-01-01", 100.0)
    _insert(db_path, "nasdaq100", "2026-02-01", 130.0)
    _insert(db_path, "sp500", "2026-01-01", 100.0)
    _insert(db_path, "sp500", "2026-02-01", 110.0)

    result = derived.calculate_relative_return("nasdaq100", "sp500", 30, db_path=db_path)

    assert result.status == "ok"
    assert math.isclose(result.value, 0.20)
    assert result.dependency_keys == ["nasdaq100", "sp500"]
    assert "minus" in result.interpretation_hint


def test_relative_return_with_one_dependency_insufficient(tmp_path):
    db_path = tmp_path / "market_history.sqlite3"
    _insert(db_path, "nasdaq100", "2026-01-01", 100.0)
    _insert(db_path, "nasdaq100", "2026-02-01", 130.0)
    _insert(db_path, "sp500", "2026-02-01", 110.0)

    result = derived.calculate_relative_return("nasdaq100", "sp500", 30, db_path=db_path)

    assert result.status == "insufficient_history"
    assert result.ai_context_allowed is False
    assert "sp500" in result.missing_reason


def test_oil_period_return_preserves_official_dependency_metadata(tmp_path):
    db_path = tmp_path / "market_history.sqlite3"
    _insert(db_path, "wti", "2026-01-31", 70.0, source_series="DCOILWTICO")
    _insert(db_path, "wti", "2026-03-02", 77.0, source_series="DCOILWTICO")

    result = derived.calculate_period_return(
        "wti",
        30,
        db_path=db_path,
        output_metric_key="wti_30d_change",
    )

    assert result.status == "ok"
    assert result.ai_context_allowed is True
    assert result.dependency_source_badges == ["official"]
    assert result.dependency_source_series == ["DCOILWTICO"]


def test_proxy_breadth_metrics_calculate_from_proxy_history(tmp_path):
    db_path = tmp_path / "market_history.sqlite3"
    _insert_proxy_series(db_path)

    by_module = derived.build_historical_dashboard_candidates(db_path=db_path)
    proxy = {
        item.metric_key: item
        for item in by_module["breadth_concentration_proxy"]
    }

    assert proxy["spy_proxy_30d_return"].status == "ok"
    assert math.isclose(proxy["spy_proxy_30d_return"].value, 120 / 110 - 1)
    assert math.isclose(proxy["rsp_proxy_60d_return"].value, 0.10)
    assert math.isclose(
        proxy["spy_vs_rsp_30d"].value,
        (120 / 110 - 1) - (110 / 105 - 1),
    )
    assert math.isclose(
        proxy["qqq_vs_spy_30d"].value,
        (140 / 115 - 1) - (120 / 110 - 1),
    )
    assert math.isclose(
        proxy["hyg_vs_lqd_30d"].value,
        (104 / 102 - 1) - (102 / 101 - 1),
    )
    for metric in proxy.values():
        assert metric.source_badge == "derived"
        assert metric.ai_context_allowed is True
        assert metric.dependency_source_badges == ["proxy"]
        assert "yfinance ETF proxy" in metric.interpretation_hint
        assert "not official market breadth" in metric.interpretation_hint
        assert "not valuation data" in metric.interpretation_hint
        assert "not a crash confirmation signal" in metric.interpretation_hint


def test_proxy_breadth_metrics_block_without_sufficient_history(tmp_path):
    db_path = tmp_path / "market_history.sqlite3"
    _insert_proxy(db_path, "spy_proxy", "2026-03-02", 120.0, source_series="SPY")

    result = derived.build_historical_dashboard_candidates(db_path=db_path)[
        "breadth_concentration_proxy"
    ]
    spy = next(item for item in result if item.metric_key == "spy_proxy_30d_return")

    assert spy.status == "insufficient_history"
    assert spy.ai_context_allowed is False
    assert spy.missing_reason == "history_points_insufficient"


def test_drawdown_metrics_calculate_from_local_history(tmp_path):
    db_path = tmp_path / "market_history.sqlite3"
    _insert(db_path, "sp500", "2025-11-01", 100.0, source_series="^GSPC")
    _insert(db_path, "sp500", "2026-01-01", 120.0, source_series="^GSPC")
    _insert(db_path, "sp500", "2026-02-01", 90.0, source_series="^GSPC")
    _insert(db_path, "sp500", "2026-03-02", 96.0, source_series="^GSPC")

    result = derived.calculate_drawdown(
        "sp500",
        90,
        db_path=db_path,
        output_metric_key="sp500_drawdown_3m",
    )

    assert result.status == "ok"
    assert math.isclose(result.value, 96.0 / 120.0 - 1.0)
    assert result.dependency_source_badges == ["official"]
    assert "market outcome" in result.interpretation_hint
    assert "trading signal" in result.interpretation_hint


def test_drawdown_metrics_block_without_sufficient_history(tmp_path):
    db_path = tmp_path / "market_history.sqlite3"
    _insert(db_path, "sp500", "2026-03-02", 96.0, source_series="^GSPC")

    result = derived.calculate_drawdown("sp500", 90, db_path=db_path)

    assert result.status == "insufficient_history"
    assert result.ai_context_allowed is False
    assert result.missing_reason == "history_points_insufficient"


def test_curve_slope_calculates_from_latest_dgs_history(tmp_path):
    db_path = tmp_path / "market_history.sqlite3"
    _insert(db_path, "dgs2", "2026-03-02", 4.25, source_series="DGS2")
    _insert(db_path, "dgs10", "2026-03-02", 4.75, source_series="DGS10")

    result = derived.calculate_latest_spread(
        "dgs10",
        "dgs2",
        db_path=db_path,
        output_metric_key="dgs10_dgs2_curve_slope",
    )

    assert result.status == "ok"
    assert math.isclose(result.value, 0.50)
    assert result.value_text == "0.50pp"
    assert result.dependency_source_badges == ["official"]
    assert result.dependency_source_series == ["DGS10", "DGS2"]
    assert "macro context" in result.interpretation_hint
    assert "not a trading signal" in result.interpretation_hint


def test_curve_slope_blocks_when_dependency_missing(tmp_path):
    db_path = tmp_path / "market_history.sqlite3"
    _insert(db_path, "dgs10", "2026-03-02", 4.75, source_series="DGS10")

    result = derived.calculate_latest_spread(
        "dgs10",
        "dgs2",
        db_path=db_path,
        output_metric_key="dgs10_dgs2_curve_slope",
    )

    assert result.status == "insufficient_history"
    assert result.ai_context_allowed is False
    assert "dgs2" in result.missing_reason


def test_curve_slope_uses_compact_official_fallback_when_history_missing(tmp_path):
    db_path = tmp_path / "market_history.sqlite3"
    fallback = {
        "dgs2": _compact_dgs_observation("dgs2", 4.25, "DGS2"),
        "dgs10": _compact_dgs_observation("dgs10", 4.75, "DGS10"),
        "dgs30": _compact_dgs_observation("dgs30", 5.10, "DGS30"),
    }

    result = derived.calculate_latest_spread(
        "dgs30",
        "dgs10",
        db_path=db_path,
        fallback_observations=fallback,
        output_metric_key="dgs30_dgs10_curve_slope",
    )

    assert result.status == "ok"
    assert math.isclose(result.value, 0.35)
    assert result.source_badge == "derived"
    assert result.dependency_source_badges == ["official"]
    assert set(result.dependency_source_series) == {"DGS30", "DGS10"}
    assert result.dependency_observation_dates == ["2026-03-02"]
    assert result.dependency_generated_ats == ["2026-03-02T00:00:00+00:00"]
    assert result.dependency_freshness_statuses == ["fresh"]
    assert result.ai_context_allowed is True
    assert "compact/dashboard official DGS fallback" in result.interpretation_hint
    assert "not a trading signal" in result.interpretation_hint


def test_curve_slope_compact_fallback_blocks_when_value_missing(tmp_path):
    db_path = tmp_path / "market_history.sqlite3"
    fallback = {
        "dgs2": _compact_dgs_observation("dgs2", 4.25, "DGS2"),
        "dgs10": _compact_dgs_observation("dgs10", None, "DGS10"),
    }

    result = derived.calculate_latest_spread(
        "dgs10",
        "dgs2",
        db_path=db_path,
        fallback_observations=fallback,
        output_metric_key="dgs10_dgs2_curve_slope",
    )

    assert result.status == "insufficient_history"
    assert result.ai_context_allowed is False
    assert "dgs10:latest_observation_missing" in result.missing_reason


def test_curve_slope_compact_fallback_blocks_when_metadata_missing(tmp_path):
    db_path = tmp_path / "market_history.sqlite3"
    fallback = {
        "dgs2": _compact_dgs_observation("dgs2", 4.25, "DGS2"),
        "dgs10": _compact_dgs_observation("dgs10", 4.75, None),
    }

    result = derived.calculate_latest_spread(
        "dgs10",
        "dgs2",
        db_path=db_path,
        fallback_observations=fallback,
        output_metric_key="dgs10_dgs2_curve_slope",
    )

    assert result.status == "insufficient_history"
    assert result.ai_context_allowed is False
    assert "dgs10:latest_observation_missing" in result.missing_reason


def test_curve_slope_uses_compact_fallback_when_history_metadata_incomplete(tmp_path):
    db_path = tmp_path / "market_history.sqlite3"
    _insert_incomplete_history(db_path, "dgs10", "2026-03-02", 4.70)
    _insert_incomplete_history(db_path, "dgs2", "2026-03-02", 4.10)
    fallback = {
        "dgs2": _compact_dgs_observation("dgs2", 4.25, "DGS2"),
        "dgs10": _compact_dgs_observation("dgs10", 4.75, "DGS10"),
    }

    result = derived.calculate_latest_spread(
        "dgs10",
        "dgs2",
        db_path=db_path,
        fallback_observations=fallback,
        output_metric_key="dgs10_dgs2_curve_slope",
    )

    assert result.status == "ok"
    assert math.isclose(result.value, 0.50)
    assert result.dependency_source_series == ["DGS10", "DGS2"]
    assert result.ai_context_allowed is True


def test_cross_asset_proxy_metrics_preserve_proxy_dependency_metadata(tmp_path):
    db_path = tmp_path / "market_history.sqlite3"
    _insert_cross_asset_proxy_series(db_path)

    stress = {
        item.metric_key: item
        for item in derived.build_historical_dashboard_candidates(db_path=db_path)[
            "market_stress_derived"
        ]
    }

    assert math.isclose(stress["tlt_proxy_30d_return"].value, 105.0 / 100.0 - 1.0)
    assert math.isclose(stress["gld_proxy_30d_return"].value, 102.0 / 100.0 - 1.0)
    assert math.isclose(stress["shy_proxy_30d_return"].value, 100.5 / 100.0 - 1.0)
    assert math.isclose(
        stress["tlt_vs_shy_30d"].value,
        (105.0 / 100.0 - 1.0) - (100.5 / 100.0 - 1.0),
    )
    for key in ("tlt_proxy_30d_return", "gld_proxy_30d_return", "shy_proxy_30d_return", "tlt_vs_shy_30d"):
        assert stress[key].source_badge == "derived"
        assert stress[key].dependency_source_badges == ["proxy"]
        assert stress[key].ai_context_allowed is True
        assert "ETF proxy" in stress[key].interpretation_hint
    assert "relative return proxy" in stress["tlt_vs_shy_30d"].interpretation_hint
    assert "not an official bond-risk indicator" in stress["tlt_vs_shy_30d"].interpretation_hint


def test_ppi_final_demand_yoy_requires_official_history(tmp_path):
    db_path = tmp_path / "market_history.sqlite3"
    dates = [
        "2025-01-01",
        "2025-02-01",
        "2025-03-01",
        "2025-04-01",
        "2025-05-01",
        "2025-06-01",
        "2025-07-01",
        "2025-08-01",
        "2025-09-01",
        "2025-10-01",
        "2025-11-01",
        "2025-12-01",
        "2026-01-01",
    ]
    for observation_date, value in zip(dates, [150.0, 151.0, 152.0, 153.0, 154.0, 155.0, 156.0, 157.0, 158.0, 159.0, 160.0, 161.0, 162.0]):
        _insert(db_path, "ppi_final_demand", observation_date, value, source_series="PPIFIS")

    result = derived.calculate_observation_yoy(
        "ppi_final_demand",
        13,
        db_path=db_path,
        output_metric_key="ppi_final_demand_yoy",
    )

    assert result.status == "ok"
    assert math.isclose(result.value, 162.0 / 150.0 - 1.0)
    assert result.dependency_source_badges == ["official"]
    assert result.dependency_source_series == ["PPIFIS"]
    assert "PPI Final Demand" in result.interpretation_hint


def test_distance_to_threshold_with_latest_observation(tmp_path):
    db_path = tmp_path / "market_history.sqlite3"
    _insert(db_path, "dgs30", "2026-01-01", 4.8)

    result = derived.calculate_distance_to_threshold("dgs30", 5.0, db_path=db_path)

    assert result.status == "ok"
    assert math.isclose(result.value, -0.2)
    assert result.unit == "pp"
    assert "threshold" in result.interpretation_hint


def test_distance_to_threshold_without_latest_observation(tmp_path):
    result = derived.calculate_distance_to_threshold(
        "dgs30",
        5.0,
        db_path=tmp_path / "missing.sqlite3",
    )

    assert result.status == "insufficient_history"
    assert result.ai_context_allowed is False
    assert result.missing_reason == "latest_observation_missing"


def test_build_historical_dashboard_candidates_groups_supported_metrics(tmp_path):
    db_path = tmp_path / "market_history.sqlite3"
    for day, value in enumerate([1, 2, 3, 4, 5], start=1):
        _insert(db_path, "dgs10", f"2026-01-0{day}", float(value))
    _insert(db_path, "dgs30", "2026-01-05", 4.8)

    by_module = derived.build_historical_dashboard_candidates(db_path=db_path)
    rate_metrics = {item.metric_key: item for item in by_module["rate_pressure"]}

    assert set(by_module) == {
        "breadth_concentration_proxy",
        "equity_trend",
        "inflation_energy_pressure",
        "labor_macro",
        "market_stress_derived",
        "rate_pressure",
    }
    assert rate_metrics["dgs10_5d_avg"].status == "ok"
    assert rate_metrics["dgs30_distance_to_5pct"].status == "ok"
    assert rate_metrics["dgs10_10d_avg"].status == "insufficient_history"


def test_flattened_metrics_are_compact_and_safe(tmp_path):
    metrics = derived.flatten_historical_dashboard_candidates(db_path=tmp_path / "missing.sqlite3")
    payloads = [derived.metric_to_dict(item) for item in metrics]
    text = str(payloads)

    assert len(payloads) == 39
    assert all(item["source_badge"] == "derived" for item in payloads)
    assert "raw_provider_response" not in text
    assert "api_key" not in text.lower()
    assert "holding" not in text.lower()


def test_labor_unemployment_derived_metrics_calculate_from_official_history(tmp_path):
    db_path = tmp_path / "market_history.sqlite3"
    values = [4.0, 3.9, 3.8, 3.8, 3.9, 4.0, 4.1, 4.2, 4.3, 4.3, 4.4, 4.5]
    for month, value in enumerate(values, start=1):
        _insert(db_path, "unemployment_rate", f"2025-{month:02d}-01", value, source_series="UNRATE")

    average = derived.calculate_rolling_average(
        "unemployment_rate",
        3,
        db_path=db_path,
        output_metric_key="unemployment_rate_3m_avg",
        unit="raw_percent",
    )
    gap = derived.calculate_low_gap(
        "unemployment_rate",
        12,
        db_path=db_path,
        output_metric_key="unemployment_rate_12m_low_gap",
    )

    assert average.status == "ok"
    assert math.isclose(average.value, (4.3 + 4.4 + 4.5) / 3)
    assert average.value_text == "4.40%"
    assert average.dependency_source_series == ["UNRATE"]
    assert gap.status == "ok"
    assert math.isclose(gap.value, 0.7)
    assert gap.value_text == "0.70pp"


def test_labor_claims_averages_calculate_from_official_history(tmp_path):
    db_path = tmp_path / "market_history.sqlite3"
    for week, value in enumerate([200000, 205000, 210000, 215000], start=1):
        _insert(db_path, "initial_jobless_claims", f"2026-01-{week:02d}", value, source_series="ICSA")
    for week, value in enumerate([1700000, 1710000, 1720000, 1730000], start=1):
        _insert(db_path, "continuing_claims", f"2026-01-{week:02d}", value, source_series="CCSA")

    initial = derived.calculate_rolling_average(
        "initial_jobless_claims",
        4,
        db_path=db_path,
        output_metric_key="initial_claims_4w_avg",
        unit="claims",
    )
    continuing = derived.calculate_rolling_average(
        "continuing_claims",
        4,
        db_path=db_path,
        output_metric_key="continuing_claims_4w_avg",
        unit="claims",
    )

    assert initial.status == "ok"
    assert initial.value == 207500
    assert initial.value_text == "207,500"
    assert initial.dependency_source_series == ["ICSA"]
    assert continuing.status == "ok"
    assert continuing.value == 1715000
    assert continuing.value_text == "1,715,000"
    assert continuing.dependency_source_series == ["CCSA"]


def test_labor_derived_metrics_block_with_insufficient_history(tmp_path):
    db_path = tmp_path / "market_history.sqlite3"
    _insert(db_path, "continuing_claims", "2026-01-01", 1700000, source_series="CCSA")

    result = derived.calculate_rolling_average(
        "continuing_claims",
        4,
        db_path=db_path,
        output_metric_key="continuing_claims_4w_avg",
    )

    assert result.status == "insufficient_history"
    assert result.ai_context_allowed is False
    assert result.missing_reason == "history_points_insufficient"


def test_sahm_rule_proxy_is_not_official_recession_fact(tmp_path):
    db_path = tmp_path / "market_history.sqlite3"
    values = [3.8, 3.8, 3.8, 3.9, 4.0, 4.0, 4.1, 4.2, 4.4, 4.5, 4.6, 4.7]
    for month, value in enumerate(values, start=1):
        _insert(db_path, "unemployment_rate", f"2025-{month:02d}-01", value, source_series="UNRATE")

    result = derived.calculate_sahm_rule_proxy_status(db_path=db_path)

    assert result.status == "watch"
    assert result.source_badge == "derived"
    assert result.dependency_source_series == ["UNRATE"]
    assert "recession-warning proxy" in result.interpretation_hint
    assert "not an official recession fact" in result.interpretation_hint
    assert "trading signal" in result.interpretation_hint


def test_labor_deterioration_status_preserves_inputs_and_missing_inputs(tmp_path):
    missing = derived.calculate_labor_deterioration_status(db_path=tmp_path / "missing.sqlite3")

    assert missing.status == "missing"
    assert missing.ai_context_allowed is False
    assert set(missing.missing_inputs) == {
        "unemployment_rate",
        "initial_jobless_claims",
        "continuing_claims",
        "nonfarm_payrolls",
    }

    db_path = tmp_path / "market_history.sqlite3"
    for month, value in enumerate([3.8, 3.8, 3.8, 3.9, 4.0, 4.0, 4.1, 4.2, 4.4, 4.5, 4.6, 4.7], start=1):
        _insert(db_path, "unemployment_rate", f"2025-{month:02d}-01", value, source_series="UNRATE")
    for week, value in enumerate([200000, 202000, 204000, 206000, 230000, 232000, 234000, 236000], start=1):
        _insert(db_path, "initial_jobless_claims", f"2026-01-{week:02d}", value, source_series="ICSA")
    for week, value in enumerate([1700000, 1705000, 1710000, 1715000, 1730000, 1735000, 1740000, 1745000], start=1):
        _insert(db_path, "continuing_claims", f"2026-01-{week:02d}", value, source_series="CCSA")
    _insert(db_path, "nonfarm_payrolls", "2025-11-01", 160000, source_series="PAYEMS")
    _insert(db_path, "nonfarm_payrolls", "2025-12-01", 159900, source_series="PAYEMS")

    result = derived.calculate_labor_deterioration_status(db_path=db_path)

    assert result.status == "pressure"
    assert result.source_badge == "derived"
    assert result.missing_inputs == []
    assert {item["metric_key"] for item in result.input_evidence} == {
        "unemployment_rate_12m_low_gap",
        "initial_claims_4w_avg",
        "continuing_claims_4w_avg",
        "nonfarm_payrolls_monthly_change",
    }
    assert result.dependency_source_series == ["UNRATE", "ICSA", "CCSA", "PAYEMS"]
    assert "Single-month unemployment increases do not determine recession" in result.interpretation_hint
    assert "not crisis confirmation" in result.interpretation_hint


def test_no_network_access(monkeypatch, tmp_path):
    block_network_calls(monkeypatch)

    result = derived.calculate_rolling_average("dgs10", 5, db_path=tmp_path / "missing.sqlite3")

    assert result.status == "insufficient_history"


def _insert(db_path, metric_key, observation_date, value, *, source_series=None):
    market_history_store.upsert_market_observation(
        {
            "metric_key": metric_key,
            "observation_date": observation_date,
            "value": value,
            "value_text": str(value),
            "unit": "index",
            "status": "ok",
            "source": "test_source",
            "source_badge": "official",
            "provider": "test_source",
            "source_series": source_series or metric_key.upper(),
            "generated_at": f"{observation_date}T00:00:00+00:00",
            "fetched_at": f"{observation_date}T00:00:00+00:00",
            "freshness_status": "fresh",
            "ai_context_allowed": True,
            "metric_kind": "raw",
            "lineage": {},
        },
        db_path=db_path,
    )


def _compact_dgs_observation(metric_key, value, source_series):
    return {
        "metric_key": metric_key,
        "value": value,
        "source": f"FRED:{source_series}" if source_series else "FRED",
        "source_badge": "official",
        "source_series": source_series,
        "observation_date": "2026-03-02",
        "generated_at": "2026-03-02T00:00:00+00:00",
        "freshness_status": "fresh",
        "ai_context_allowed": True,
    }


def _insert_incomplete_history(db_path, metric_key, observation_date, value):
    market_history_store.upsert_market_observation(
        {
            "metric_key": metric_key,
            "observation_date": observation_date,
            "value": value,
            "value_text": str(value),
            "unit": "percent",
            "status": "ok",
            "source": "test_source",
            "source_badge": "official",
            "provider": "test_source",
            "source_series": None,
            "generated_at": f"{observation_date}T00:00:00+00:00",
            "fetched_at": f"{observation_date}T00:00:00+00:00",
            "freshness_status": "fresh",
            "ai_context_allowed": True,
            "metric_kind": "raw",
            "lineage": {},
        },
        db_path=db_path,
    )


def _insert_proxy_series(db_path):
    values_by_metric = {
        "spy_proxy": [100.0, 110.0, 120.0],
        "rsp_proxy": [100.0, 105.0, 110.0],
        "qqq_proxy": [100.0, 115.0, 140.0],
        "hyg_proxy": [100.0, 102.0, 104.0],
        "lqd_proxy": [100.0, 101.0, 102.0],
    }
    series_by_metric = {
        "spy_proxy": "SPY",
        "rsp_proxy": "RSP",
        "qqq_proxy": "QQQ",
        "hyg_proxy": "HYG",
        "lqd_proxy": "LQD",
    }
    for metric_key, values in values_by_metric.items():
        for observation_date, value in zip(
            ["2026-01-01", "2026-01-31", "2026-03-02"],
            values,
        ):
            _insert_proxy(
                db_path,
                metric_key,
                observation_date,
                value,
                source_series=series_by_metric[metric_key],
            )


def _insert_proxy(db_path, metric_key, observation_date, value, *, source_series):
    market_history_store.upsert_market_observation(
        {
            "metric_key": metric_key,
            "observation_date": observation_date,
            "value": value,
            "value_text": str(value),
            "unit": "price",
            "status": "ok",
            "source": "Yahoo Finance via yfinance",
            "source_badge": "proxy",
            "provider": "yfinance",
            "source_series": source_series,
            "generated_at": f"{observation_date}T00:00:00+00:00",
            "fetched_at": f"{observation_date}T00:00:00+00:00",
            "freshness_status": "historical",
            "ai_context_allowed": False,
            "metric_kind": "proxy",
            "lineage": {"source_badge": "proxy"},
        },
        db_path=db_path,
    )


def _insert_cross_asset_proxy_series(db_path):
    for metric_key, source_series, start, end in (
        ("tlt_proxy", "TLT", 100.0, 105.0),
        ("gld_proxy", "GLD", 100.0, 102.0),
        ("shy_proxy", "SHY", 100.0, 100.5),
    ):
        _insert_proxy(db_path, metric_key, "2026-01-31", start, source_series=source_series)
        _insert_proxy(db_path, metric_key, "2026-03-02", end, source_series=source_series)
