import json
import socket

from app_backend.schemas.responses import DashboardEvidenceRow, DashboardMetric, DashboardModule
import audit_data_pipeline_coverage as audit
from data_quality import market_history_store


def test_audit_script_runs_against_fake_reports(monkeypatch, tmp_path):
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

    assert result["coverage_summary"]["total_rows"] > 0
    assert "rows_with_value_and_complete_metadata" in result["coverage_summary"]
    assert "rows_with_value_but_blocked" in result["coverage_summary"]
    assert "provenance_missing_count" in result["coverage_summary"]
    assert "blocked_reason_counts" in result
    assert "source_badge_distribution" in result
    assert "ai_context_allowed_by_module" in result
    assert "module_coverage_summary" in result
    assert "usable_row_count_by_module" in result["module_coverage_summary"]
    assert "top_missing_metrics" in result
    assert "top_research_needed_metrics" in result
    assert "top_insufficient_history_metrics" in result
    assert "dashboard_overall_degraded_reasons" in result
    assert "data_sufficiency_assessment" in result
    assert "portfolio_compact" in result
    assert "portfolio_compact_available" in result["portfolio_compact"]
    assert "energy_history" in result
    assert "energy_history_available" in result["energy_history"]
    assert "real_yield_pressure_status_status" in result["energy_history"]
    assert "proxy_breadth" in result
    assert "breadth_proxy_available" in result["proxy_breadth"]
    assert "valuation_research" in result
    assert result["valuation_research"]["valuation_available"] is False
    assert result["module_coverage"]
    assert "recommendations" in result


def test_audit_reports_portfolio_compact_coverage(monkeypatch, tmp_path):
    _block_network(monkeypatch)
    _write_json(
        tmp_path / "portfolio_snapshot.json",
        {
            "generated_at": "2026-06-10T00:00:00+00:00",
            "status": "ok",
            "holdings_updated_at": "2026-06-01",
            "weights_ex_cash": {
                "sp500": 0.54,
                "nasdaq100": 0.17,
                "short_bond": 0.19,
                "gold": 0.10,
            },
            "target_allocation": {
                "sp500": 0.50,
                "nasdaq100": 0.20,
                "short_bond": 0.20,
                "gold": 0.10,
            },
            "cash_reserve_value": 1234567,
            "holdings": [{"ticker": "RAW_FUND", "amount": 999999}],
        },
    )

    result = audit.build_coverage_audit(reports_dir=tmp_path)
    portfolio = result["portfolio_compact"]

    assert portfolio["portfolio_compact_available"] is True
    assert portfolio["portfolio_deviation_value_count"] == 5
    assert portfolio["portfolio_deviation_missing_count"] == 0
    assert portfolio["portfolio_deviation_ai_context_allowed_count"] == 5
    assert portfolio["portfolio_has_raw_holdings_leak"] is False
    assert portfolio["portfolio_cash_excluded_from_target"] is True
    assert portfolio["portfolio_stale_status"] == "fresh"
    assert "fill_portfolio_deviation_compact" not in result["recommendations"]


def test_audit_reports_last_good_cache_status(monkeypatch, tmp_path):
    _block_network(monkeypatch)
    reports_dir = tmp_path / "reports"
    cache_dir = tmp_path / "cache"
    reports_dir.mkdir()
    cache_dir.mkdir()
    _write_json(
        reports_dir / "market_snapshot.json",
        {
            "generated_at": "2026-01-01T00:00:00+00:00",
            "status": "ok",
        },
    )
    _write_json(
        cache_dir / "dgs10.json",
        {
            "metric_key": "dgs10",
            "value": 4.52,
            "value_text": "4.52%",
            "unit": "percent",
            "status": "ok",
            "source": "FRED",
            "source_badge": "official",
            "provider": "FRED",
            "source_series": "DGS10",
            "observation_date": "2026-01-01",
            "generated_at": "2026-01-01T00:00:00+00:00",
            "fetched_at": "2026-01-01T00:00:00+00:00",
            "freshness_status": "fresh",
            "ttl_policy": "daily",
            "ttl_days": 7,
            "stale_after": "2026-01-08T00:00:00+00:00",
            "last_live_status": "ok",
            "last_error": None,
            "raw_hash": "safe-hash",
        },
    )

    result = audit.build_coverage_audit(
        reports_dir=reports_dir,
        last_good_cache_dir=cache_dir,
    )

    assert result["coverage_summary"]["last_good_metric_count"] == 1
    assert result["last_good_cache"]["last_good_metric_count"] == 1
    assert result["last_good_cache"]["metrics_with_last_good"] == ["dgs10"]
    assert result["last_good_cache"]["metrics_missing_but_last_good_available"] == ["dgs10"]
    assert result["last_good_cache"]["last_good_not_used_count"] == 1
    rate_pressure = next(
        item for item in result["module_coverage"] if item["module"] == "rate_pressure"
    )
    assert rate_pressure["last_good_available_count"] == 1
    assert rate_pressure["missing_but_last_good_available_count"] == 1


def test_audit_reports_missing_market_history_store(monkeypatch, tmp_path):
    _block_network(monkeypatch)
    _write_json(
        tmp_path / "market_snapshot.json",
        {
            "generated_at": "2026-01-01T00:00:00+00:00",
            "status": "ok",
        },
    )

    result = audit.build_coverage_audit(
        reports_dir=tmp_path,
        market_history_db_path=tmp_path / "missing" / "market_history.sqlite3",
    )
    historical = result["historical_store"]

    assert historical["market_history_available"] is False
    assert historical["market_history_db_exists"] is False
    assert historical["market_history_schema_version"] == 0
    assert "initialize_market_history_store" in historical["recommended_history_actions"]
    assert "ingest_market_history_from_dashboard" in historical["recommended_history_actions"]


def test_audit_reports_existing_market_history_store(monkeypatch, tmp_path):
    _block_network(monkeypatch)
    reports_dir = tmp_path / "reports"
    reports_dir.mkdir()
    db_path = tmp_path / "market_history.sqlite3"
    _write_json(
        reports_dir / "market_snapshot.json",
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
    market_history_store.upsert_market_observation(
        {
            "metric_key": "dgs10",
            "observation_date": "2026-01-01",
            "value": 4.5,
            "value_text": "4.5%",
            "unit": "percent",
            "status": "ok",
            "source": "FRED",
            "source_badge": "official",
            "provider": "FRED",
            "source_series": "DGS10",
            "generated_at": "2026-01-01T00:00:00+00:00",
            "fetched_at": "2026-01-01T00:00:00+00:00",
            "freshness_status": "fresh",
            "ai_context_allowed": True,
            "metric_kind": "raw",
            "lineage": {},
        },
        db_path=db_path,
    )

    result = audit.build_coverage_audit(
        reports_dir=reports_dir,
        market_history_db_path=db_path,
    )
    historical = result["historical_store"]

    assert historical["market_history_available"] is True
    assert historical["market_history_db_exists"] is True
    assert historical["market_history_schema_version"] == market_history_store.CURRENT_SCHEMA_VERSION
    assert historical["market_history_metric_count"] == 1
    assert historical["market_history_observation_count"] == 1
    assert historical["observations_by_metric"] == {"dgs10": 1}
    assert historical["latest_observation_by_metric"] == {"dgs10": "2026-01-01"}
    assert historical["dashboard_metrics_with_history_count"] == 1


def test_audit_reports_historical_derived_block_when_db_missing(monkeypatch, tmp_path):
    _block_network(monkeypatch)
    _write_json(
        tmp_path / "market_snapshot.json",
        {
            "generated_at": "2026-01-01T00:00:00+00:00",
            "status": "ok",
        },
    )

    result = audit.build_coverage_audit(
        reports_dir=tmp_path,
        market_history_db_path=tmp_path / "missing" / "market_history.sqlite3",
    )
    historical_derived = result["historical_derived"]

    assert historical_derived["historical_derived_available"] is False
    assert historical_derived["derived_metric_count"] == 39
    assert historical_derived["derived_metric_ok_count"] == 0
    assert historical_derived["derived_metric_insufficient_history_count"] == 38
    assert historical_derived["derived_metric_missing_dependency_count"] >= 1
    assert "initialize_and_ingest_market_history" in historical_derived["recommended_history_actions"]


def test_audit_reports_historical_derived_ok_and_blocked_counts(monkeypatch, tmp_path):
    _block_network(monkeypatch)
    reports_dir = tmp_path / "reports"
    reports_dir.mkdir()
    db_path = tmp_path / "market_history.sqlite3"
    _write_json(
        reports_dir / "market_snapshot.json",
        {
            "generated_at": "2026-01-01T00:00:00+00:00",
            "status": "ok",
        },
    )
    for day, value in enumerate([1, 2, 3, 4, 5], start=1):
        _insert_market_observation(db_path, "dgs10", f"2026-01-0{day}", float(value))
    _insert_market_observation(db_path, "dgs30", "2026-01-05", 4.8)

    result = audit.build_coverage_audit(
        reports_dir=reports_dir,
        market_history_db_path=db_path,
    )
    historical_derived = result["historical_derived"]
    rate = historical_derived["derived_metrics_by_module"]["rate_pressure"]

    assert historical_derived["historical_derived_available"] is True
    assert historical_derived["derived_metric_ok_count"] == 3
    assert rate["ok_count"] == 2
    assert historical_derived["derived_metrics_by_module"]["market_stress_derived"]["ok_count"] == 1
    assert historical_derived["dashboard_insufficient_history_still_blocked_count"] >= 1
    assert any(
        item["metric_key"] == "dgs10_5d_avg" and item["status"] == "ok"
        for item in historical_derived["derived_metric_details"]
    )


def test_audit_reports_yfinance_history_block_when_db_missing(monkeypatch, tmp_path):
    _block_network(monkeypatch)
    _write_json(
        tmp_path / "market_snapshot.json",
        {
            "generated_at": "2026-01-01T00:00:00+00:00",
            "status": "ok",
        },
    )

    result = audit.build_coverage_audit(
        reports_dir=tmp_path,
        market_history_db_path=tmp_path / "missing" / "market_history.sqlite3",
    )
    yfinance_history = result["yfinance_history"]

    assert yfinance_history["yfinance_history_configured"] is True
    assert yfinance_history["yfinance_enabled_symbol_count"] == 11
    assert yfinance_history["yfinance_observation_count"] == 0
    assert yfinance_history["yfinance_proxy_metric_count"] == 8
    assert yfinance_history["yfinance_unofficial_fallback_metric_count"] == 3
    assert "run_yfinance_history_ingest_live" in yfinance_history["recommendations"]
    assert "keep_proxy_out_of_official_layer" in yfinance_history["recommendations"]


def test_audit_reports_yfinance_history_observation_counts(monkeypatch, tmp_path):
    _block_network(monkeypatch)
    reports_dir = tmp_path / "reports"
    reports_dir.mkdir()
    db_path = tmp_path / "market_history.sqlite3"
    _write_json(
        reports_dir / "market_snapshot.json",
        {
            "generated_at": "2026-01-01T00:00:00+00:00",
            "status": "ok",
        },
    )
    _insert_market_observation(
        db_path,
        "sp500",
        "2026-01-01",
        100.0,
        source_badge="unofficial_fallback",
        provider="yfinance",
        source_series="^GSPC",
        metric_kind="index",
        ai_context_allowed=False,
    )
    _insert_market_observation(
        db_path,
        "spy_proxy",
        "2026-01-02",
        101.0,
        source_badge="proxy",
        provider="yfinance",
        source_series="SPY",
        metric_kind="proxy",
        ai_context_allowed=False,
    )

    result = audit.build_coverage_audit(
        reports_dir=reports_dir,
        market_history_db_path=db_path,
    )
    yfinance_history = result["yfinance_history"]

    assert yfinance_history["yfinance_observation_count"] == 2
    assert yfinance_history["yfinance_observations_by_metric"] == {
        "sp500": 1,
        "spy_proxy": 1,
    }
    assert yfinance_history["yfinance_latest_observation_by_metric"] == {
        "sp500": "2026-01-01",
        "spy_proxy": "2026-01-02",
    }
    assert yfinance_history["historical_store_proxy_observation_count"] == 1
    assert yfinance_history["historical_store_unofficial_observation_count"] == 1
    assert "run_yfinance_history_ingest_live" not in yfinance_history["recommendations"]


def test_audit_reports_dashboard_derived_integration(monkeypatch, tmp_path):
    _block_network(monkeypatch)
    reports_dir = tmp_path / "reports"
    reports_dir.mkdir()
    db_path = tmp_path / "market_history.sqlite3"
    _write_json(
        reports_dir / "market_snapshot.json",
        {
            "generated_at": "2026-03-02T00:00:00+00:00",
            "status": "ok",
        },
    )
    for metric_key, source_series, end_value in (
        ("sp500", "^GSPC", 110.0),
        ("nasdaq100", "^NDX", 130.0),
    ):
        _insert_market_observation(
            db_path,
            metric_key,
            "2026-01-01",
            100.0,
            source_badge="unofficial_fallback",
            provider="yfinance",
            source_series=source_series,
            metric_kind="index",
            ai_context_allowed=False,
        )
        _insert_market_observation(
            db_path,
            metric_key,
            "2026-03-02",
            end_value,
            source_badge="unofficial_fallback",
            provider="yfinance",
            source_series=source_series,
            metric_kind="index",
            ai_context_allowed=False,
        )

    result = audit.build_coverage_audit(
        reports_dir=reports_dir,
        market_history_db_path=db_path,
    )
    integration = result["dashboard_derived_integration"]

    assert integration["equity_derived_integrated_count"] == 5
    assert integration["equity_derived_still_insufficient_count"] == 0
    assert integration["historical_derived_used_in_dashboard_count"] == 5
    assert integration["dashboard_equity_trend_value_count"] == 5
    assert integration["integrated_metric_keys"] == [
        "nasdaq100_30d_return",
        "nasdaq100_60d_return",
        "nasdaq_vs_sp500_30d",
        "sp500_30d_return",
        "sp500_60d_return",
    ]


def test_audit_reports_proxy_breadth_coverage(monkeypatch, tmp_path):
    _block_network(monkeypatch)
    reports_dir = tmp_path / "reports"
    reports_dir.mkdir()
    db_path = tmp_path / "market_history.sqlite3"
    _write_json(
        reports_dir / "market_snapshot.json",
        {
            "generated_at": "2026-03-02T00:00:00+00:00",
            "status": "ok",
        },
    )
    _insert_proxy_series(db_path)

    result = audit.build_coverage_audit(
        reports_dir=reports_dir,
        market_history_db_path=db_path,
    )
    proxy = result["proxy_breadth"]

    assert proxy["breadth_proxy_available"] is True
    assert proxy["breadth_proxy_metric_count"] == 12
    assert proxy["breadth_proxy_ok_count"] == 12
    assert proxy["breadth_proxy_insufficient_history_count"] == 0
    assert proxy["concentration_proxy_available"] is True
    assert proxy["credit_proxy_available"] is True
    assert proxy["proxy_metrics_ai_context_allowed_count"] == 12
    assert proxy["proxy_insufficient_history_metric_keys"] == []
    assert "spy_vs_rsp_30d" in proxy["proxy_metric_keys"]
    assert "hyg_vs_lqd_60d" in proxy["proxy_metric_keys"]


def test_audit_reports_market_stress_derived_coverage(monkeypatch, tmp_path):
    _block_network(monkeypatch)
    reports_dir = tmp_path / "reports"
    reports_dir.mkdir()
    db_path = tmp_path / "market_history.sqlite3"
    _write_json(
        reports_dir / "market_snapshot.json",
        {
            "generated_at": "2026-03-02T00:00:00+00:00",
            "status": "ok",
        },
    )
    for metric_key, source_series, values in (
        ("sp500", "^GSPC", [95.0, 100.0, 120.0, 96.0]),
        ("nasdaq100", "^NDX", [90.0, 100.0, 150.0, 120.0]),
    ):
        for observation_date, value in zip(
            ["2025-08-01", "2025-11-01", "2026-01-01", "2026-03-02"],
            values,
        ):
            _insert_market_observation(
                db_path,
                metric_key,
                observation_date,
                value,
                source_badge="unofficial_fallback",
                provider="yfinance",
                source_series=source_series,
                metric_kind="index",
                ai_context_allowed=False,
            )
    for metric_key, source_series, value in (
        ("dgs2", "DGS2", 4.25),
        ("dgs10", "DGS10", 4.75),
        ("dgs30", "DGS30", 5.10),
    ):
        _insert_market_observation(
            db_path,
            metric_key,
            "2026-03-02",
            value,
            source_badge="official",
            provider="FRED",
            source_series=source_series,
        )
    for metric_key, source_series, start, end in (
        ("tlt_proxy", "TLT", 100.0, 105.0),
        ("gld_proxy", "GLD", 100.0, 102.0),
        ("shy_proxy", "SHY", 100.0, 100.5),
    ):
        _insert_market_observation(
            db_path,
            metric_key,
            "2026-01-31",
            start,
            source_badge="proxy",
            provider="yfinance",
            source_series=source_series,
            metric_kind="proxy",
            ai_context_allowed=False,
        )
        _insert_market_observation(
            db_path,
            metric_key,
            "2026-03-02",
            end,
            source_badge="proxy",
            provider="yfinance",
            source_series=source_series,
            metric_kind="proxy",
            ai_context_allowed=False,
        )

    result = audit.build_coverage_audit(
        reports_dir=reports_dir,
        market_history_db_path=db_path,
    )
    stress = result["market_stress_derived"]

    assert stress["market_stress_derived_available"] is True
    assert stress["market_stress_derived_metric_count"] == 10
    assert stress["market_stress_derived_ok_count"] == 10
    assert stress["market_stress_derived_insufficient_history_count"] == 0
    assert stress["drawdown_available"] is True
    assert stress["curve_slope_available"] is True
    assert stress["cross_asset_proxy_available"] is True
    assert stress["market_stress_ai_context_allowed_count"] == 10
    assert "tlt_vs_shy_30d" in stress["market_stress_metric_keys"]


def test_audit_reports_curve_slope_available_from_compact_dgs_fallback(monkeypatch, tmp_path):
    _block_network(monkeypatch)
    reports_dir = tmp_path / "reports"
    reports_dir.mkdir()
    db_path = tmp_path / "market_history.sqlite3"
    _write_json(
        reports_dir / "market_snapshot.json",
        {
            "generated_at": "2026-03-02T00:00:00+00:00",
            "status": "ok",
            "dgs2": _compact_dgs_metric(4.25, "DGS2"),
            "dgs10": _compact_dgs_metric(4.75, "DGS10"),
            "dgs30": _compact_dgs_metric(5.10, "DGS30"),
        },
    )

    result = audit.build_coverage_audit(
        reports_dir=reports_dir,
        market_history_db_path=db_path,
    )
    stress = result["market_stress_derived"]
    slope_details = {
        item["metric_key"]: item
        for item in result["historical_derived"]["derived_metric_details"]
        if item["metric_key"] in {"dgs10_dgs2_curve_slope", "dgs30_dgs10_curve_slope"}
    }

    assert stress["curve_slope_available"] is True
    assert "dgs10_dgs2_curve_slope" not in stress["market_stress_insufficient_history_metric_keys"]
    assert slope_details["dgs10_dgs2_curve_slope"]["status"] == "ok"
    assert slope_details["dgs10_dgs2_curve_slope"]["dependency_source_series"] == ["DGS10", "DGS2"]
    assert slope_details["dgs30_dgs10_curve_slope"]["dependency_source_series"] == ["DGS30", "DGS10"]


def test_audit_reports_energy_history_and_real_yield_status(monkeypatch, tmp_path):
    _block_network(monkeypatch)
    reports_dir = tmp_path / "reports"
    reports_dir.mkdir()
    db_path = tmp_path / "market_history.sqlite3"
    _write_json(
        reports_dir / "market_snapshot.json",
        {
            "generated_at": "2026-03-02T00:00:00+00:00",
            "status": "ok",
            "dfii10": {
                "value": 2.05,
                "status": "ok",
                "source": "FRED:DFII10",
                "source_badge": "official",
                "observation_date": "2026-03-02",
                "freshness_status": "fresh",
            },
            "t10yie": {
                "value": 2.35,
                "status": "ok",
                "source": "FRED:T10YIE",
                "source_badge": "official",
                "observation_date": "2026-03-02",
                "freshness_status": "fresh",
            },
        },
    )
    for metric_key, series, start_value, end_value in (
        ("wti", "DCOILWTICO", 70.0, 77.0),
        ("brent", "DCOILBRENTEU", 75.0, 72.0),
    ):
        _insert_market_observation(
            db_path,
            metric_key,
            "2026-01-31",
            start_value,
            source_badge="official",
            provider="FRED",
            source_series=series,
            metric_kind="raw",
            ai_context_allowed=True,
        )
        _insert_market_observation(
            db_path,
            metric_key,
            "2026-03-02",
            end_value,
            source_badge="official",
            provider="FRED",
            source_series=series,
            metric_kind="raw",
            ai_context_allowed=True,
        )

    result = audit.build_coverage_audit(
        reports_dir=reports_dir,
        market_history_db_path=db_path,
    )
    energy = result["energy_history"]

    assert energy["energy_history_available"] is True
    assert energy["wti_history_observation_count"] == 2
    assert energy["brent_history_observation_count"] == 2
    assert energy["wti_30d_change_status"] == "ok"
    assert energy["brent_30d_change_status"] == "ok"
    assert energy["real_yield_pressure_status_status"] == "pressure"
    assert energy["dgs30_breakout_confirmed_status"] == "research_needed"
    assert energy["ppi_final_demand_status"] == "missing"


def test_audit_reports_official_macro_pack(monkeypatch, tmp_path):
    _block_network(monkeypatch)
    _write_json(
        tmp_path / "market_snapshot.json",
        {
            "generated_at": "2026-01-01T00:00:00+00:00",
            "status": "ok",
            "dfii10": {
                "value": 2.0,
                "status": "ok",
                "source": "FRED",
                "source_badge": "official",
                "observation_date": "2026-01-01",
                "freshness_status": "fresh",
            },
            "t10yie": {
                "value": 2.3,
                "status": "ok",
                "source": "FRED",
                "source_badge": "official",
                "observation_date": "2026-01-01",
                "freshness_status": "fresh",
            },
            "core_cpi_yoy": {
                "value": 3.1,
                "status": "ok",
                "source": "FRED",
                "source_badge": "official",
                "observation_date": "2026-01-01",
                "freshness_status": "fresh",
            },
            "core_pce_yoy": {
                "value": 2.7,
                "status": "ok",
                "source": "FRED",
                "source_badge": "official",
                "observation_date": "2026-01-01",
                "freshness_status": "fresh",
            },
            "ppiaco_yoy": {
                "value": 1.7,
                "status": "ok",
                "source": "FRED:PPIACO",
                "source_badge": "official",
                "observation_date": "2026-01-01",
                "freshness_status": "fresh",
            },
        },
    )

    result = audit.build_coverage_audit(reports_dir=tmp_path)
    official = result["official_macro_pack"]

    assert official["official_macro_configured_count"] == 13
    assert official["real_yield_available"] is True
    assert official["inflation_core_available"] is True
    assert official["labor_available"] is False
    assert official["rate_macro_available_count"] == 0
    assert official["dfii10_status"] == "ok"
    assert official["t10yie_status"] == "ok"
    assert official["core_cpi_yoy_status"] == "ok"
    assert official["core_pce_yoy_status"] == "ok"
    assert official["ppiaco_yoy_status"] == "ok"
    assert official["ppi_final_demand_available"] is False
    assert official["ppi_final_demand_status"] == "missing"
    assert official["ppi_final_demand_yoy_status"] == "insufficient_history"
    assert official["ppi_final_demand_ai_context_allowed"] is False
    assert official["unemployment_rate_status"] == "missing"
    assert official["initial_jobless_claims_status"] == "missing"
    assert official["nonfarm_payrolls_status"] == "missing"
    assert official["continuing_claims_status"] == "missing"
    assert official["suspicious_yoy_count"] == 0
    assert official["blocked_due_to_index_level_count"] == 0
    assert "ppi_final_demand" in official["missing_metric_keys"]
    assert "official_macro_pack" in result
    assert "add_official_macro_pack" not in result["recommendations"]


def test_audit_reports_ppi_final_demand_and_valuation_gates(monkeypatch, tmp_path):
    _block_network(monkeypatch)
    reports_dir = tmp_path / "reports"
    reports_dir.mkdir()
    db_path = tmp_path / "market_history.sqlite3"
    _write_json(
        reports_dir / "market_snapshot.json",
        {
            "generated_at": "2026-03-02T00:00:00+00:00",
            "status": "ok",
            "market_data_package": {
                "inflation_indicators": {
                    "ppi_final_demand": {
                        "value": 157.659,
                        "status": "ok",
                        "source": "FRED:PPIFIS",
                        "source_tier": "official_or_public_data_api",
                        "observation_date": "2026-01-01",
                        "freshness": "normal_lag",
                    }
                }
            },
        },
    )
    _insert_proxy_series(db_path)

    result = audit.build_coverage_audit(
        reports_dir=reports_dir,
        market_history_db_path=db_path,
    )
    valuation = result["valuation_research"]
    official = result["official_macro_pack"]

    assert valuation["ppi_final_demand_available"] is True
    assert valuation["ppi_final_demand_ai_context_allowed"] is True
    assert valuation["valuation_available"] is False
    assert valuation["valuation_proxy_available"] is False
    assert valuation["valuation_public_research_candidate_available"] is True
    assert "sp500_forward_pe" in valuation["valuation_blocked_metric_keys"]
    assert "spy_vs_rsp_30d" in valuation["price_only_proxy_metric_keys_seen"]
    assert official["ppi_final_demand_available"] is True
    assert official["ppi_final_demand_status"] == "ok"


def test_audit_reports_labor_and_provider_health_followup(monkeypatch, tmp_path):
    _block_network(monkeypatch)
    db_path = tmp_path / "market_history.sqlite3"
    for index in range(12):
        _insert_market_observation(db_path, "unemployment_rate", f"2025-{index + 1:02d}-01", 4.0, source_series="UNRATE")
    for index in range(8):
        _insert_market_observation(db_path, "initial_jobless_claims", f"2026-01-{index + 1:02d}", 230000, source_series="ICSA")
        _insert_market_observation(db_path, "continuing_claims", f"2026-01-{index + 1:02d}", 1700000, source_series="CCSA")
    for index in range(2):
        _insert_market_observation(db_path, "nonfarm_payrolls", f"2025-{index + 11:02d}-01", 160000, source_series="PAYEMS")
    _write_json(
        tmp_path / "market_snapshot.json",
        {
            "generated_at": "2026-01-01T00:00:00+00:00",
            "status": "ok",
            "market_data_package": {
                "labor_indicators": {
                    "unemployment_rate": {
                        "value": 4.0,
                        "status": "ok",
                        "source": "FRED:UNRATE",
                        "source_tier": "official_or_public_data_api",
                        "observation_date": "2026-01-01",
                        "freshness": "normal_lag",
                    },
                    "initial_jobless_claims": {
                        "value": 230000,
                        "status": "ok",
                        "source": "FRED:ICSA",
                        "source_tier": "official_or_public_data_api",
                        "observation_date": "2026-01-04",
                        "freshness": "fresh",
                    },
                    "nonfarm_payrolls": {
                        "value": 160000,
                        "status": "ok",
                        "source": "FRED:PAYEMS",
                        "source_tier": "official_or_public_data_api",
                        "observation_date": "2025-12-01",
                        "freshness": "normal_lag",
                    },
                    "continuing_claims": {
                        "value": 1700000,
                        "status": "ok",
                        "source": "FRED:CCSA",
                        "source_tier": "official_or_public_data_api",
                        "observation_date": "2026-01-04",
                        "freshness": "fresh",
                    },
                }
            },
        },
    )
    _write_json(
        tmp_path / "provider_health_check.json",
        {
            "generated_at": "2026-01-01T00:00:00+00:00",
            "overall_status": "degraded",
            "summary": {"ok": 4, "transient_error": 1, "official_fallback_ok": 4},
            "checks": [
                {
                    "key": "fred_dgs10",
                    "provider": "FRED",
                    "status": "transient_error",
                    "source": "FRED",
                    "value_present": False,
                    "error_type": "transient_network",
                    "error_summary": "SSL EOF",
                },
                {
                    "key": "treasury_10y",
                    "provider": "U.S. Treasury",
                    "status": "ok",
                    "source": "U.S. Treasury",
                    "value_present": True,
                },
            ],
        },
    )

    result = audit.build_coverage_audit(reports_dir=tmp_path, market_history_db_path=db_path)
    official = result["official_macro_pack"]
    provider = result["provider_health"]

    assert official["labor_available"] is True
    assert official["labor_missing_count"] == 0
    assert official["unemployment_rate_status"] == "ok"
    assert official["initial_jobless_claims_status"] == "ok"
    assert official["nonfarm_payrolls_status"] == "ok"
    assert official["continuing_claims_status"] == "ok"
    assert official["labor_history_observation_counts"] == {
        "unemployment_rate": 12,
        "initial_jobless_claims": 8,
        "nonfarm_payrolls": 2,
        "continuing_claims": 8,
    }
    assert official["unemployment_rate_history_observation_count"] == 12
    assert official["initial_jobless_claims_history_observation_count"] == 8
    assert official["nonfarm_payrolls_history_observation_count"] == 2
    assert official["continuing_claims_history_observation_count"] == 8
    assert official["labor_history_sufficient_for_derived"] is True
    assert provider["overall_status"] == "degraded"
    assert provider["provider_health_transient_error_count"] == 1
    assert provider["official_fallback_ok_count"] == 1
    assert provider["official_fallback_ok_providers"] == ["U.S. Treasury"]


def test_audit_reports_module_coverage_summary_and_degraded_reasons(monkeypatch, tmp_path):
    _block_network(monkeypatch)
    _write_json(
        tmp_path / "market_snapshot.json",
        {
            "generated_at": "2026-01-01T00:00:00+00:00",
            "status": "ok",
            "financial_conditions": {"label": "partial"},
            "high_yield_spread": {
                "value": 3.1,
                "status": "ok",
                "source": "FRED:BAMLH0A0HYM2",
                "source_badge": "official",
                "observation_date": "2026-01-01",
                "freshness_status": "fresh",
            },
            "vix": {
                "value": 18.0,
                "status": "ok",
                "source": "CBOE",
                "source_badge": "official",
                "observation_date": "2026-01-01",
                "freshness_status": "fresh",
            },
        },
    )

    result = audit.build_coverage_audit(reports_dir=tmp_path)
    summary = result["module_coverage_summary"]

    assert summary["usable_row_count_by_module"]["credit_stress"] >= 2
    assert summary["missing_count_by_module"]["credit_stress"] >= 1
    assert summary["official_count_by_module"]["credit_stress"] >= 2
    assert summary["derived_or_proxy_count_by_module"]["credit_stress"] >= 1
    assert any(
        "credit_stress" in reason and "blocked_core_metrics" in reason
        for reason in result["dashboard_overall_degraded_reasons"]
    )
    assert result["data_sufficiency_assessment"]["insufficient_for_crisis_confirmation"] is True
    assert result["data_sufficiency_assessment"]["insufficient_for_valuation_judgment"] is True
    assert result["data_sufficiency_assessment"]["insufficient_for_breadth_judgment"] is True


def test_audit_detects_metadata_anomalies():
    rows = [
        _row(
            "rate_pressure",
            "dgs10",
            value=4.5,
            source_badge="missing",
            freshness_status="unknown",
            ai_context_allowed=True,
        )
    ]

    anomalies = audit._metadata_anomalies(rows)
    anomaly_types = {item["type"] for item in anomalies}

    assert "value_with_missing_source_badge" in anomaly_types
    assert "value_with_unknown_freshness" in anomaly_types
    assert "ai_allowed_with_missing_source_badge" in anomaly_types
    assert "ai_allowed_with_bad_freshness" in anomaly_types


def test_audit_flags_suspicious_large_yoy_metric():
    rows = [
        _row(
            "inflation_energy_pressure",
            "core_cpi_yoy",
            value=335.42,
            source_badge="official",
            ai_context_allowed=True,
        )
    ]

    anomalies = audit._metadata_anomalies(rows)

    assert any(
        item["type"] == "yoy_metric_suspiciously_large"
        and item["reason"] == "inflation_yoy_metric_blocked_due_to_index_level"
        for item in anomalies
    )


def test_audit_detects_derived_dependency_anomalies():
    rows = [
        _row("rate_pressure", "dgs10", value=None, status="missing"),
        _row("rate_pressure", "dgs30", value=None, status="missing"),
        _row(
            "rate_pressure",
            "dgs30_distance_to_5pct",
            value=0.2,
            status="ok",
            source_badge="derived",
        ),
        _row("equity_trend", "sp500_30d_return", value=None, status="insufficient_history"),
        _row(
            "equity_trend",
            "nasdaq100_30d_return",
            value=3.1,
            status="ok",
            source_badge="unofficial_fallback",
        ),
        _row(
            "equity_trend",
            "nasdaq_vs_sp500_30d",
            value=1.1,
            status="ok",
            source_badge="derived",
        ),
    ]
    modules = {
        "rate_pressure": _module("rate_pressure", "ok"),
        "equity_trend": _module("equity_trend", "ok"),
    }

    anomalies = audit._dependency_anomalies(modules, rows)
    anomaly_types = {item["type"] for item in anomalies}

    assert "dgs30_distance_ok_while_dgs30_missing" in anomaly_types
    assert "nasdaq_vs_sp500_ok_while_dependency_missing" in anomaly_types
    assert "module_ok_while_core_metrics_mostly_missing" in anomaly_types


def _row(
    module,
    metric_key,
    *,
    value,
    status="ok",
    source_badge="official",
    freshness_status="fresh",
    ai_context_allowed=False,
):
    return DashboardEvidenceRow(
        row_id=f"{module}:{metric_key}",
        module=module,
        metric_key=metric_key,
        display_name=metric_key,
        value=value,
        value_text=str(value) if value is not None else status,
        unit=None,
        status=status,
        source="FRED" if source_badge not in {"missing", "derived"} else None,
        source_badge=source_badge,
        observation_date="2026-01-01" if value is not None else None,
        generated_at=None,
        freshness_status=freshness_status,
        missing_reason=None,
        interpretation_hint=None,
        ai_context_allowed=ai_context_allowed,
    )


def _module(key, status):
    return DashboardModule(
        key=key,
        status=status,
        label=key,
        summary=None,
        source_badge="cached_report",
        updated_at=None,
        next_action=None,
        error_summary=None,
        key_metrics=[
            DashboardMetric(
                metric_key="placeholder",
                display_name="placeholder",
                value=None,
                value_text="missing",
                unit=None,
                status="missing",
                source=None,
                source_badge="missing",
                observation_date=None,
                generated_at=None,
                freshness_status="missing",
                missing_reason="missing",
                interpretation_hint=None,
                ai_context_allowed=False,
            )
        ],
    )


def _write_json(path, payload):
    path.write_text(json.dumps(payload), encoding="utf-8")


def _compact_dgs_metric(value, source_series):
    return {
        "value": value,
        "unit": "percent",
        "status": "ok",
        "source": f"FRED:{source_series}",
        "source_badge": "official",
        "source_series": source_series,
        "observation_date": "2026-03-02",
        "generated_at": "2026-03-02T00:00:00+00:00",
        "freshness_status": "fresh",
        "interpretation_hint": "FRED daily constant maturity yield; not intraday high.",
    }


def _insert_market_observation(
    db_path,
    metric_key,
    observation_date,
    value,
    *,
    source_badge="official",
    provider="test_source",
    source_series=None,
    metric_kind="raw",
    ai_context_allowed=True,
):
    market_history_store.upsert_market_observation(
        {
            "metric_key": metric_key,
            "observation_date": observation_date,
            "value": value,
            "value_text": str(value),
            "unit": "percent",
            "status": "ok",
            "source": "test_source",
            "source_badge": source_badge,
            "provider": provider,
            "source_series": source_series or metric_key.upper(),
            "generated_at": f"{observation_date}T00:00:00+00:00",
            "fetched_at": f"{observation_date}T00:00:00+00:00",
            "freshness_status": "fresh",
            "ai_context_allowed": ai_context_allowed,
            "metric_kind": metric_kind,
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
            _insert_market_observation(
                db_path,
                metric_key,
                observation_date,
                value,
                source_badge="proxy",
                provider="yfinance",
                source_series=series_by_metric[metric_key],
                metric_kind="proxy",
                ai_context_allowed=False,
            )


def _block_network(monkeypatch):
    def _raise_on_network(*args, **kwargs):
        raise AssertionError("Network access is not allowed in audit tests.")

    monkeypatch.setattr(socket, "create_connection", _raise_on_network)
