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
