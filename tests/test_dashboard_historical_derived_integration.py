import json
import socket

from fastapi.testclient import TestClient

from app_backend.main import app
from app_backend.services import dashboard_service
from data_quality import market_history_store


def test_equity_historical_derived_metrics_integrate_into_dashboard(monkeypatch, tmp_path):
    _block_network(monkeypatch)
    db_path = tmp_path / "market_history.sqlite3"
    _insert(db_path, "sp500", "2026-01-01", 100.0, source_series="^GSPC")
    _insert(db_path, "sp500", "2026-03-02", 110.0, source_series="^GSPC")
    _insert(db_path, "nasdaq100", "2026-01-01", 100.0, source_series="^NDX")
    _insert(db_path, "nasdaq100", "2026-03-02", 130.0, source_series="^NDX")
    _write_market_report(tmp_path)
    monkeypatch.setattr(dashboard_service, "DEFAULT_REPORTS_DIR", tmp_path)
    monkeypatch.setattr(dashboard_service, "DEFAULT_MARKET_HISTORY_DB_PATH", db_path)

    data = TestClient(app).get("/api/dashboard/summary").json()
    equity = data["modules"]["equity_trend"]

    assert equity["status"] == "ok"
    assert _metric(equity, "sp500_30d_return")["value_text"] == "+10.00%"
    assert _metric(equity, "nasdaq100_60d_return")["value_text"] == "+30.00%"
    assert _metric(equity, "nasdaq_vs_sp500_30d")["value_text"] == "+20.00pp"
    for key in (
        "sp500_30d_return",
        "sp500_60d_return",
        "nasdaq100_30d_return",
        "nasdaq100_60d_return",
        "nasdaq_vs_sp500_30d",
    ):
        metric = _metric(equity, key)
        assert metric["status"] == "ok"
        assert metric["source"] == "local_market_history"
        assert metric["source_badge"] == "derived"
        assert "derived from local market history" in metric["interpretation_hint"].lower()
        assert "yfinance unofficial_fallback/proxy" in metric["interpretation_hint"].lower()
        assert "not an official market breadth or valuation measure" in metric[
            "interpretation_hint"
        ].lower()
        assert metric["observation_date"] == "2026-03-02"
        assert metric["freshness_status"] == "historical"
        assert metric["ai_context_allowed"] is True


def test_evidence_table_uses_integrated_equity_rows(monkeypatch, tmp_path):
    _block_network(monkeypatch)
    db_path = tmp_path / "market_history.sqlite3"
    _insert(db_path, "sp500", "2026-01-01", 100.0, source_series="^GSPC")
    _insert(db_path, "sp500", "2026-03-02", 110.0, source_series="^GSPC")
    _insert(db_path, "nasdaq100", "2026-01-01", 100.0, source_series="^NDX")
    _insert(db_path, "nasdaq100", "2026-03-02", 130.0, source_series="^NDX")
    _write_market_report(tmp_path)
    monkeypatch.setattr(dashboard_service, "DEFAULT_REPORTS_DIR", tmp_path)
    monkeypatch.setattr(dashboard_service, "DEFAULT_MARKET_HISTORY_DB_PATH", db_path)

    data = TestClient(app).get("/api/dashboard/evidence-table?module=equity_trend").json()

    assert data["row_count"] == 5
    assert all(row["status"] == "ok" for row in data["rows"])
    assert all(row["source_badge"] == "derived" for row in data["rows"])
    assert _row(data, "nasdaq_vs_sp500_30d")["value_text"] == "+20.00pp"


def test_proxy_breadth_metrics_surface_in_evidence_table(monkeypatch, tmp_path):
    _block_network(monkeypatch)
    db_path = tmp_path / "market_history.sqlite3"
    _insert_proxy_series(db_path)
    _write_market_report(tmp_path)
    monkeypatch.setattr(dashboard_service, "DEFAULT_REPORTS_DIR", tmp_path)
    monkeypatch.setattr(dashboard_service, "DEFAULT_MARKET_HISTORY_DB_PATH", db_path)

    summary = TestClient(app).get("/api/dashboard/summary").json()
    proxy_module = summary["modules"]["breadth_concentration_proxy"]
    evidence = TestClient(app).get(
        "/api/dashboard/evidence-table?module=breadth_concentration_proxy"
    ).json()

    assert proxy_module["status"] == "ok"
    assert evidence["row_count"] == 12
    spy = _row(evidence, "spy_proxy_30d_return")
    spread = _row(evidence, "spy_vs_rsp_30d")
    tech = _row(evidence, "qqq_vs_spy_30d")
    credit = _row(evidence, "hyg_vs_lqd_30d")

    assert spy["value_text"] == "+9.09%"
    assert spread["value_text"] == "+4.33pp"
    assert tech["value_text"] == "+12.65pp"
    assert credit["value_text"] == "+0.97pp"
    for row in evidence["rows"]:
        assert row["source"] == "local_market_history"
        assert row["source_badge"] == "derived"
        assert row["freshness_status"] == "historical"
        assert row["ai_context_allowed"] is True
        assert row["source_badge"] != "official"
        assert "yfinance ETF proxy" in row["interpretation_hint"]
        assert "not official market breadth" in row["interpretation_hint"]
        assert "not valuation data" in row["interpretation_hint"]
        assert "not a crash confirmation signal" in row["interpretation_hint"]


def test_proxy_breadth_metrics_stay_blocked_when_history_missing(monkeypatch, tmp_path):
    _block_network(monkeypatch)
    db_path = tmp_path / "market_history.sqlite3"
    _insert_proxy(db_path, "spy_proxy", "2026-03-02", 120.0, source_series="SPY")
    _write_market_report(tmp_path)
    monkeypatch.setattr(dashboard_service, "DEFAULT_REPORTS_DIR", tmp_path)
    monkeypatch.setattr(dashboard_service, "DEFAULT_MARKET_HISTORY_DB_PATH", db_path)

    evidence = TestClient(app).get(
        "/api/dashboard/evidence-table?module=breadth_concentration_proxy"
    ).json()
    spy = _row(evidence, "spy_proxy_30d_return")

    assert spy["status"] == "insufficient_history"
    assert spy["source_badge"] == "missing"
    assert spy["ai_context_allowed"] is False


def test_market_stress_derived_metrics_surface_in_evidence_table(monkeypatch, tmp_path):
    _block_network(monkeypatch)
    db_path = tmp_path / "market_history.sqlite3"
    _insert(db_path, "sp500", "2025-08-01", 95.0, source_series="^GSPC")
    _insert(db_path, "sp500", "2025-11-01", 100.0, source_series="^GSPC")
    _insert(db_path, "sp500", "2026-01-01", 120.0, source_series="^GSPC")
    _insert(db_path, "sp500", "2026-03-02", 96.0, source_series="^GSPC")
    _insert(db_path, "nasdaq100", "2025-08-01", 90.0, source_series="^NDX")
    _insert(db_path, "nasdaq100", "2025-11-01", 100.0, source_series="^NDX")
    _insert(db_path, "nasdaq100", "2026-01-01", 150.0, source_series="^NDX")
    _insert(db_path, "nasdaq100", "2026-03-02", 120.0, source_series="^NDX")
    _insert_official_rate(db_path, "dgs2", "2026-03-02", 4.25, source_series="DGS2")
    _insert_official_rate(db_path, "dgs10", "2026-03-02", 4.75, source_series="DGS10")
    _insert_official_rate(db_path, "dgs30", "2026-03-02", 5.10, source_series="DGS30")
    _insert_cross_asset_proxy_series(db_path)
    _write_market_report(tmp_path)
    monkeypatch.setattr(dashboard_service, "DEFAULT_REPORTS_DIR", tmp_path)
    monkeypatch.setattr(dashboard_service, "DEFAULT_MARKET_HISTORY_DB_PATH", db_path)

    summary = TestClient(app).get("/api/dashboard/summary").json()
    module = summary["modules"]["market_stress_derived"]
    evidence = TestClient(app).get(
        "/api/dashboard/evidence-table?module=market_stress_derived"
    ).json()

    assert module["status"] == "ok"
    assert evidence["row_count"] == 10
    assert _row(evidence, "sp500_drawdown_3m")["value_text"] == "-20.00%"
    assert _row(evidence, "nasdaq100_drawdown_3m")["value_text"] == "-20.00%"
    assert _row(evidence, "dgs10_dgs2_curve_slope")["value_text"] == "+0.50pp"
    assert _row(evidence, "dgs30_dgs10_curve_slope")["value_text"] == "+0.35pp"
    assert _row(evidence, "tlt_proxy_30d_return")["value_text"] == "+5.00%"
    assert _row(evidence, "tlt_vs_shy_30d")["value_text"] == "+4.50pp"
    for row in evidence["rows"]:
        assert row["source"] == "local_market_history"
        assert row["source_badge"] == "derived"
        assert row["freshness_status"] == "historical"
        assert row["observation_date"] == "2026-03-02"
        assert row["ai_context_allowed"] is True
    assert "market outcome" in _row(evidence, "sp500_drawdown_3m")["interpretation_hint"]
    assert "not a trading signal" in _row(evidence, "dgs10_dgs2_curve_slope")[
        "interpretation_hint"
    ]
    assert "ETF proxy" in _row(evidence, "tlt_proxy_30d_return")["interpretation_hint"]
    assert "not an official bond-risk indicator" in _row(evidence, "tlt_vs_shy_30d")[
        "interpretation_hint"
    ]
    assert _row(evidence, "tlt_proxy_30d_return")["source_series"] == "TLT"
    assert _row(evidence, "dgs10_dgs2_curve_slope")["source_series"] == "DGS10, DGS2"


def test_market_stress_derived_metrics_block_when_history_missing(monkeypatch, tmp_path):
    _block_network(monkeypatch)
    db_path = tmp_path / "market_history.sqlite3"
    _insert(db_path, "sp500", "2026-03-02", 96.0, source_series="^GSPC")
    _write_market_report(tmp_path)
    monkeypatch.setattr(dashboard_service, "DEFAULT_REPORTS_DIR", tmp_path)
    monkeypatch.setattr(dashboard_service, "DEFAULT_MARKET_HISTORY_DB_PATH", db_path)

    evidence = TestClient(app).get(
        "/api/dashboard/evidence-table?module=market_stress_derived"
    ).json()
    drawdown = _row(evidence, "sp500_drawdown_3m")
    curve = _row(evidence, "dgs10_dgs2_curve_slope")

    assert drawdown["status"] == "insufficient_history"
    assert drawdown["source_badge"] == "missing"
    assert drawdown["ai_context_allowed"] is False
    assert curve["status"] == "insufficient_history"
    assert curve["ai_context_allowed"] is False


def test_market_stress_curve_slope_uses_compact_dgs_fallback(monkeypatch, tmp_path):
    _block_network(monkeypatch)
    db_path = tmp_path / "market_history.sqlite3"
    _insert(db_path, "sp500", "2025-08-01", 95.0, source_series="^GSPC")
    _insert(db_path, "sp500", "2026-03-02", 96.0, source_series="^GSPC")
    _insert_cross_asset_proxy_series(db_path)
    _write_market_report(tmp_path, extra=_compact_dgs_payload())
    monkeypatch.setattr(dashboard_service, "DEFAULT_REPORTS_DIR", tmp_path)
    monkeypatch.setattr(dashboard_service, "DEFAULT_MARKET_HISTORY_DB_PATH", db_path)

    evidence = TestClient(app).get(
        "/api/dashboard/evidence-table?module=market_stress_derived"
    ).json()
    dgs10_dgs2 = _row(evidence, "dgs10_dgs2_curve_slope")
    dgs30_dgs10 = _row(evidence, "dgs30_dgs10_curve_slope")

    assert dgs10_dgs2["status"] == "ok"
    assert dgs10_dgs2["value_text"] == "+0.50pp"
    assert dgs30_dgs10["status"] == "ok"
    assert dgs30_dgs10["value_text"] == "+0.35pp"
    assert dgs10_dgs2["source_badge"] == "derived"
    assert dgs10_dgs2["source_series"] == "DGS10, DGS2"
    assert dgs30_dgs10["source_series"] == "DGS30, DGS10"
    assert dgs10_dgs2["observation_date"] == "2026-03-02"
    assert dgs10_dgs2["freshness_status"] == "historical"
    assert dgs10_dgs2["ai_context_allowed"] is True
    assert "compact/dashboard official DGS fallback" in dgs10_dgs2["interpretation_hint"]
    assert "not a trading signal" in dgs10_dgs2["interpretation_hint"]


def test_market_stress_curve_slope_blocks_when_compact_dgs_value_missing(monkeypatch, tmp_path):
    _block_network(monkeypatch)
    db_path = tmp_path / "market_history.sqlite3"
    payload = _compact_dgs_payload()
    payload["dgs10"]["value"] = None
    _write_market_report(tmp_path, extra=payload)
    monkeypatch.setattr(dashboard_service, "DEFAULT_REPORTS_DIR", tmp_path)
    monkeypatch.setattr(dashboard_service, "DEFAULT_MARKET_HISTORY_DB_PATH", db_path)

    evidence = TestClient(app).get(
        "/api/dashboard/evidence-table?module=market_stress_derived"
    ).json()
    curve = _row(evidence, "dgs10_dgs2_curve_slope")

    assert curve["status"] == "insufficient_history"
    assert curve["source_badge"] == "missing"
    assert curve["ai_context_allowed"] is False


def test_market_stress_curve_slope_blocks_when_compact_dgs_metadata_missing(monkeypatch, tmp_path):
    _block_network(monkeypatch)
    db_path = tmp_path / "market_history.sqlite3"
    payload = _compact_dgs_payload()
    payload["dgs2"].pop("source")
    _write_market_report(tmp_path, extra=payload)
    monkeypatch.setattr(dashboard_service, "DEFAULT_REPORTS_DIR", tmp_path)
    monkeypatch.setattr(dashboard_service, "DEFAULT_MARKET_HISTORY_DB_PATH", db_path)

    evidence = TestClient(app).get(
        "/api/dashboard/evidence-table?module=market_stress_derived"
    ).json()
    curve = _row(evidence, "dgs10_dgs2_curve_slope")

    assert curve["status"] == "insufficient_history"
    assert curve["ai_context_allowed"] is False


def test_rate_and_oil_metrics_are_not_replaced_by_equity_history(monkeypatch, tmp_path):
    _block_network(monkeypatch)
    db_path = tmp_path / "market_history.sqlite3"
    _insert(db_path, "sp500", "2026-01-01", 100.0, source_series="^GSPC")
    _insert(db_path, "sp500", "2026-03-02", 110.0, source_series="^GSPC")
    _insert(db_path, "nasdaq100", "2026-01-01", 100.0, source_series="^NDX")
    _insert(db_path, "nasdaq100", "2026-03-02", 130.0, source_series="^NDX")
    _write_market_report(tmp_path)
    monkeypatch.setattr(dashboard_service, "DEFAULT_REPORTS_DIR", tmp_path)
    monkeypatch.setattr(dashboard_service, "DEFAULT_MARKET_HISTORY_DB_PATH", db_path)

    data = TestClient(app).get("/api/dashboard/summary").json()

    assert _metric(data["modules"]["rate_pressure"], "dgs10_5d_avg")["status"] == (
        "insufficient_history"
    )
    assert _metric(data["modules"]["inflation_energy_pressure"], "wti_30d_change")[
        "status"
    ] == "insufficient_history"
    assert _metric(data["modules"]["inflation_energy_pressure"], "wti_30d_change")[
        "ai_context_allowed"
    ] is False


def test_oil_historical_derived_metrics_integrate_into_dashboard(monkeypatch, tmp_path):
    _block_network(monkeypatch)
    db_path = tmp_path / "market_history.sqlite3"
    _insert_official_energy(db_path, "wti", "2026-01-31", 70.0, source_series="DCOILWTICO")
    _insert_official_energy(db_path, "wti", "2026-03-02", 77.0, source_series="DCOILWTICO")
    _insert_official_energy(db_path, "brent", "2026-01-31", 75.0, source_series="DCOILBRENTEU")
    _insert_official_energy(db_path, "brent", "2026-03-02", 72.0, source_series="DCOILBRENTEU")
    _write_market_report(tmp_path)
    monkeypatch.setattr(dashboard_service, "DEFAULT_REPORTS_DIR", tmp_path)
    monkeypatch.setattr(dashboard_service, "DEFAULT_MARKET_HISTORY_DB_PATH", db_path)

    data = TestClient(app).get("/api/dashboard/summary").json()
    inflation = data["modules"]["inflation_energy_pressure"]
    wti = _metric(inflation, "wti_30d_change")
    brent = _metric(inflation, "brent_30d_change")

    assert wti["status"] == "ok"
    assert wti["value_text"] == "+10.00%"
    assert brent["status"] == "ok"
    assert brent["value_text"] == "-4.00%"
    for metric in (wti, brent):
        assert metric["source"] == "local_market_history"
        assert metric["source_badge"] == "derived"
        assert metric["freshness_status"] == "historical"
        assert metric["ai_context_allowed"] is True
        assert "official FRED/EIA daily oil history" in metric["interpretation_hint"]
        assert "not a real-time oil quote" in metric["interpretation_hint"]


def test_oil_historical_derived_prefers_official_market_history(monkeypatch, tmp_path):
    _block_network(monkeypatch)
    db_path = tmp_path / "market_history.sqlite3"
    _insert_official_energy(db_path, "wti", "2026-01-31", 70.0, source_series="DCOILWTICO")
    _insert_official_energy(db_path, "wti", "2026-03-02", 77.0, source_series="DCOILWTICO")
    _write_market_report(
        tmp_path,
        extra={
            "wti_oil_30d_change": {
                "value": -1.5,
                "status": "ok",
                "unit": "percent",
                "source": "FRED:DCOILWTICO",
                "source_badge": "derived",
                "source_series": "DCOILWTICO",
                "observation_date": "2026-03-02",
                "freshness_status": "fresh",
            }
        },
    )
    monkeypatch.setattr(dashboard_service, "DEFAULT_REPORTS_DIR", tmp_path)
    monkeypatch.setattr(dashboard_service, "DEFAULT_MARKET_HISTORY_DB_PATH", db_path)

    data = TestClient(app).get("/api/dashboard/summary").json()
    wti = _metric(data["modules"]["inflation_energy_pressure"], "wti_30d_change")

    assert wti["status"] == "ok"
    assert wti["value_text"] == "+10.00%"
    assert wti["source"] == "local_market_history"
    assert wti["freshness_status"] == "historical"
    assert "official FRED/EIA daily oil history" in wti["interpretation_hint"]


def test_oil_historical_derived_requires_official_history(monkeypatch, tmp_path):
    _block_network(monkeypatch)
    db_path = tmp_path / "market_history.sqlite3"
    _insert(db_path, "wti", "2026-01-31", 70.0, source_series="DCOILWTICO")
    _insert(db_path, "wti", "2026-03-02", 77.0, source_series="DCOILWTICO")
    _write_market_report(tmp_path)
    monkeypatch.setattr(dashboard_service, "DEFAULT_REPORTS_DIR", tmp_path)
    monkeypatch.setattr(dashboard_service, "DEFAULT_MARKET_HISTORY_DB_PATH", db_path)

    data = TestClient(app).get("/api/dashboard/summary").json()
    wti = _metric(data["modules"]["inflation_energy_pressure"], "wti_30d_change")

    assert wti["status"] == "insufficient_history"
    assert wti["ai_context_allowed"] is False


def test_ppifis_history_surfaces_final_demand_and_yoy(monkeypatch, tmp_path):
    _block_network(monkeypatch)
    db_path = tmp_path / "market_history.sqlite3"
    values = [
        150.0,
        151.0,
        152.0,
        153.0,
        154.0,
        155.0,
        156.0,
        157.0,
        158.0,
        159.0,
        160.0,
        161.0,
        162.0,
    ]
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
    for observation_date, value in zip(dates, values):
        _insert_official_ppifis(db_path, observation_date, value)
    _write_market_report(tmp_path)
    monkeypatch.setattr(dashboard_service, "DEFAULT_REPORTS_DIR", tmp_path)
    monkeypatch.setattr(dashboard_service, "DEFAULT_MARKET_HISTORY_DB_PATH", db_path)

    data = TestClient(app).get("/api/dashboard/evidence-table?module=inflation_energy_pressure").json()
    index_row = _row(data, "ppi_final_demand")
    yoy_row = _row(data, "ppi_final_demand_yoy")

    assert index_row["status"] == "ok"
    assert index_row["value"] == 162.0
    assert index_row["source"] == "FRED"
    assert index_row["source_badge"] == "official"
    assert index_row["source_series"] == "PPIFIS"
    assert index_row["observation_date"] == "2026-01-01"
    assert index_row["generated_at"] == "2026-01-01T00:00:00+00:00"
    assert index_row["freshness_status"] == "historical"
    assert index_row["ai_context_allowed"] is True
    assert "PPIACO" in index_row["interpretation_hint"]

    assert yoy_row["status"] == "ok"
    assert yoy_row["value_text"] == "+8.00%"
    assert yoy_row["source_badge"] == "derived"
    assert yoy_row["source_series"] == "PPIFIS"
    assert yoy_row["ai_context_allowed"] is True
    assert "PPIFIS" in yoy_row["interpretation_hint"]
    assert "PPIACO" in yoy_row["interpretation_hint"]


def test_ppifis_yoy_stays_blocked_with_insufficient_history(monkeypatch, tmp_path):
    _block_network(monkeypatch)
    db_path = tmp_path / "market_history.sqlite3"
    _insert_official_ppifis(db_path, "2026-01-01", 162.0)
    _write_market_report(tmp_path)
    monkeypatch.setattr(dashboard_service, "DEFAULT_REPORTS_DIR", tmp_path)
    monkeypatch.setattr(dashboard_service, "DEFAULT_MARKET_HISTORY_DB_PATH", db_path)

    data = TestClient(app).get("/api/dashboard/evidence-table?module=inflation_energy_pressure").json()
    index_row = _row(data, "ppi_final_demand")
    yoy_row = _row(data, "ppi_final_demand_yoy")

    assert index_row["status"] == "ok"
    assert index_row["source_series"] == "PPIFIS"
    assert yoy_row["status"] == "insufficient_history"
    assert yoy_row["value"] is None
    assert yoy_row["source_badge"] == "missing"
    assert yoy_row["ai_context_allowed"] is False
    assert "+162.00%" not in json.dumps(data)


def test_equity_history_insufficient_keeps_dashboard_insufficient(monkeypatch, tmp_path):
    _block_network(monkeypatch)
    db_path = tmp_path / "market_history.sqlite3"
    _insert(db_path, "sp500", "2026-03-02", 110.0, source_series="^GSPC")
    _insert(db_path, "nasdaq100", "2026-03-02", 130.0, source_series="^NDX")
    _write_market_report(tmp_path)
    monkeypatch.setattr(dashboard_service, "DEFAULT_REPORTS_DIR", tmp_path)
    monkeypatch.setattr(dashboard_service, "DEFAULT_MARKET_HISTORY_DB_PATH", db_path)

    data = TestClient(app).get("/api/dashboard/summary").json()

    assert _metric(data["modules"]["equity_trend"], "sp500_30d_return")["status"] == (
        "insufficient_history"
    )
    assert data["modules"]["equity_trend"]["status"] != "ok"


def test_dashboard_historical_derived_response_is_compact(monkeypatch, tmp_path):
    _block_network(monkeypatch)
    db_path = tmp_path / "market_history.sqlite3"
    _insert(db_path, "sp500", "2026-01-01", 100.0, source_series="^GSPC")
    _insert(db_path, "sp500", "2026-03-02", 110.0, source_series="^GSPC")
    _insert(db_path, "nasdaq100", "2026-01-01", 100.0, source_series="^NDX")
    _insert(db_path, "nasdaq100", "2026-03-02", 130.0, source_series="^NDX")
    _write_market_report(tmp_path)
    monkeypatch.setattr(dashboard_service, "DEFAULT_REPORTS_DIR", tmp_path)
    monkeypatch.setattr(dashboard_service, "DEFAULT_MARKET_HISTORY_DB_PATH", db_path)

    body = TestClient(app).get("/api/dashboard/evidence-table").text

    assert "raw_yfinance" not in body.lower()
    assert "raw_provider_response" not in body.lower()
    assert "market_history.sqlite3" not in body
    assert str(tmp_path) not in body
    assert "current_holdings.csv" not in body


def _write_market_report(tmp_path, *, extra=None):
    payload = {
        "generated_at": "2026-03-02T00:00:00+00:00",
        "status": "ok",
    }
    if extra:
        payload.update(extra)
    (tmp_path / "market_snapshot.json").write_text(
        json.dumps(payload),
        encoding="utf-8",
    )


def _compact_dgs_payload():
    return {
        "dgs2": _compact_dgs_metric(4.25, "DGS2"),
        "dgs10": _compact_dgs_metric(4.75, "DGS10"),
        "dgs30": _compact_dgs_metric(5.10, "DGS30"),
    }


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


def _insert(db_path, metric_key, observation_date, value, *, source_series):
    market_history_store.upsert_market_observation(
        {
            "metric_key": metric_key,
            "observation_date": observation_date,
            "value": value,
            "value_text": str(value),
            "unit": "index",
            "status": "ok",
            "source": "Yahoo Finance via yfinance",
            "source_badge": "unofficial_fallback",
            "provider": "yfinance",
            "source_series": source_series,
            "generated_at": f"{observation_date}T00:00:00+00:00",
            "fetched_at": f"{observation_date}T00:00:00+00:00",
            "freshness_status": "historical",
            "ai_context_allowed": False,
            "metric_kind": "index",
            "lineage": {
                "source_badge": "unofficial_fallback",
                "value_field": "Adjusted Close",
            },
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


def _insert_official_energy(db_path, metric_key, observation_date, value, *, source_series):
    market_history_store.upsert_market_observation(
        {
            "metric_key": metric_key,
            "observation_date": observation_date,
            "value": value,
            "value_text": str(value),
            "unit": "USD per barrel",
            "status": "ok",
            "source": f"FRED:{source_series}",
            "source_badge": "official",
            "provider": "FRED",
            "source_series": source_series,
            "generated_at": f"{observation_date}T00:00:00+00:00",
            "fetched_at": f"{observation_date}T00:00:00+00:00",
            "freshness_status": "historical",
            "ai_context_allowed": True,
            "metric_kind": "raw",
            "lineage": {
                "provider": "FRED",
                "source_series": source_series,
                "source_detail": "EIA daily crude oil price series distributed through FRED",
            },
        },
        db_path=db_path,
    )


def _insert_official_rate(db_path, metric_key, observation_date, value, *, source_series):
    market_history_store.upsert_market_observation(
        {
            "metric_key": metric_key,
            "observation_date": observation_date,
            "value": value,
            "value_text": str(value),
            "unit": "percent",
            "status": "ok",
            "source": f"FRED:{source_series}",
            "source_badge": "official",
            "provider": "FRED",
            "source_series": source_series,
            "generated_at": f"{observation_date}T00:00:00+00:00",
            "fetched_at": f"{observation_date}T00:00:00+00:00",
            "freshness_status": "historical",
            "ai_context_allowed": True,
            "metric_kind": "raw",
            "lineage": {
                "provider": "FRED",
                "source_series": source_series,
            },
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


def _insert_official_ppifis(db_path, observation_date, value):
    market_history_store.upsert_market_observation(
        {
            "metric_key": "ppi_final_demand",
            "observation_date": observation_date,
            "value": value,
            "value_text": str(value),
            "unit": "index",
            "status": "ok",
            "source": "FRED",
            "source_badge": "official",
            "provider": "FRED",
            "source_series": "PPIFIS",
            "generated_at": f"{observation_date}T00:00:00+00:00",
            "fetched_at": f"{observation_date}T00:00:00+00:00",
            "freshness_status": "historical",
            "ai_context_allowed": True,
            "metric_kind": "raw",
            "lineage": {
                "provider": "FRED",
                "source_series": "PPIFIS",
                "source_detail": "Headline PPI Final Demand index relayed by FRED; distinct from PPIACO.",
            },
        },
        db_path=db_path,
    )


def _metric(module, metric_key):
    for metric in module["key_metrics"]:
        if metric["metric_key"] == metric_key:
            return metric
    raise AssertionError(f"missing metric {metric_key}")


def _row(data, metric_key):
    for row in data["rows"]:
        if row["metric_key"] == metric_key:
            return row
    raise AssertionError(f"missing row {metric_key}")


def _block_network(monkeypatch):
    def _raise_on_network(*args, **kwargs):
        raise AssertionError("Network access is not allowed in dashboard derived tests.")

    monkeypatch.setattr(socket, "create_connection", _raise_on_network)
