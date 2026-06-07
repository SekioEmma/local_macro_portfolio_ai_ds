import json
import socket

from fastapi.testclient import TestClient

from app_backend.main import app
from app_backend.services import dashboard_service


MODULE_KEYS = {
    "credit_stress",
    "rate_pressure",
    "real_yield_pressure",
    "inflation_energy_pressure",
    "equity_trend",
    "portfolio_deviation",
}


def test_dashboard_key_metrics_present_for_all_modules(monkeypatch, tmp_path):
    _block_network(monkeypatch)
    _write_fake_reports(tmp_path)
    monkeypatch.setattr(dashboard_service, "DEFAULT_REPORTS_DIR", tmp_path)

    response = TestClient(app).get("/api/dashboard/summary")

    assert response.status_code == 200
    data = response.json()
    assert set(data["modules"]) == MODULE_KEYS
    for module in data["modules"].values():
      assert module["key_metrics"]
      for metric in module["key_metrics"]:
          assert metric["metric_key"]
          assert metric["display_name"]
          assert metric["value_text"]
          assert metric["source_badge"]
          assert metric["freshness_status"]
          assert "ai_context_allowed" in metric


def test_dashboard_key_metrics_missing_fields_are_explicit(monkeypatch, tmp_path):
    _block_network(monkeypatch)
    (tmp_path / "market_snapshot.json").write_text(
        json.dumps({"generated_at": "2026-01-01T00:00:00+00:00", "status": "ok"}),
        encoding="utf-8",
    )
    monkeypatch.setattr(dashboard_service, "DEFAULT_REPORTS_DIR", tmp_path)

    data = TestClient(app).get("/api/dashboard/summary").json()

    metric = _metric(data, "rate_pressure", "dgs10_5d_avg")
    assert metric["status"] == "insufficient_history"
    assert metric["value_text"] == "insufficient history"
    assert metric["ai_context_allowed"] is False

    breakout = _metric(data, "rate_pressure", "dgs30_breakout_confirmed")
    assert breakout["status"] == "missing"
    assert breakout["value_text"] == "missing"
    assert breakout["ai_context_allowed"] is False


def test_dashboard_key_metrics_do_not_leak_raw_or_holdings(monkeypatch, tmp_path):
    _block_network(monkeypatch)
    _write_fake_reports(tmp_path)
    monkeypatch.setattr(dashboard_service, "DEFAULT_REPORTS_DIR", tmp_path)

    body = TestClient(app).get("/api/dashboard/summary").text

    assert "raw_extra" not in body
    assert "must_not_leak" not in body
    assert "HOLDINGS_AMOUNT_MUST_NOT_LEAK" not in body
    assert "RAW_FUND" not in body


def test_ppiaco_and_dgs_financial_boundaries(monkeypatch, tmp_path):
    _block_network(monkeypatch)
    _write_fake_reports(tmp_path)
    monkeypatch.setattr(dashboard_service, "DEFAULT_REPORTS_DIR", tmp_path)

    data = TestClient(app).get("/api/dashboard/summary").json()
    ppiaco = _metric(data, "inflation_energy_pressure", "ppiaco_yoy")
    dgs10 = _metric(data, "rate_pressure", "dgs10")

    assert "not final demand PPI" in ppiaco["interpretation_hint"]
    assert "intraday" in dgs10["interpretation_hint"]
    assert "盘中" not in json.dumps(dgs10, ensure_ascii=False)


def test_provider_health_not_run_yet_is_not_provider_broken(monkeypatch, tmp_path):
    _block_network(monkeypatch)
    monkeypatch.setattr(dashboard_service, "DEFAULT_REPORTS_DIR", tmp_path)

    data = TestClient(app).get("/api/dashboard/summary").json()

    assert data["provider_health"]["overall_status"] == "not_run_yet"
    assert data["provider_health"]["next_action"] == "python scripts/run_provider_health_check.py --save"
    assert data["provider_health"]["error_summary"] is None


def test_credit_stress_status_derives_partial_when_ig_missing(monkeypatch, tmp_path):
    _block_network(monkeypatch)
    generated_at = "2026-01-01T00:00:00+00:00"
    metric = lambda value, source="FRED", source_badge="official": {
        "value": value,
        "status": "ok",
        "source": source,
        "source_badge": source_badge,
        "observation_date": "2026-01-01",
        "freshness_status": "fresh",
    }
    _write_json(
        tmp_path / "market_snapshot.json",
        {
            "generated_at": generated_at,
            "status": "ok",
            "financial_conditions": {"label": "partial"},
            "high_yield_spread": metric(3.0),
            "vix": metric(18.0, source="CBOE"),
        },
    )
    monkeypatch.setattr(dashboard_service, "DEFAULT_REPORTS_DIR", tmp_path)

    data = TestClient(app).get("/api/dashboard/summary").json()
    credit = data["modules"]["credit_stress"]
    status = _metric(data, "credit_stress", "credit_stress_status")
    ig = _metric(data, "credit_stress", "investment_grade_spread")

    assert ig["status"] == "missing"
    assert status["status"] == "watch"
    assert status["value"] == "partial_coverage"
    assert "Investment-grade spread is missing" in status["missing_reason"]
    assert credit["status"] == "unknown"
    assert "partial core metric coverage" in credit["summary"]


def test_credit_stress_status_does_not_infer_crisis_from_vix_alone(monkeypatch, tmp_path):
    _block_network(monkeypatch)
    _write_json(
        tmp_path / "market_snapshot.json",
        {
            "generated_at": "2026-01-01T00:00:00+00:00",
            "status": "ok",
            "financial_conditions": {"label": "vix only"},
            "vix": {
                "value": 42.0,
                "status": "ok",
                "source": "CBOE",
                "source_badge": "official",
                "observation_date": "2026-01-01",
                "freshness_status": "fresh",
            },
        },
    )
    monkeypatch.setattr(dashboard_service, "DEFAULT_REPORTS_DIR", tmp_path)

    data = TestClient(app).get("/api/dashboard/summary").json()
    status = _metric(data, "credit_stress", "credit_stress_status")

    assert status["status"] == "unknown"
    assert status["ai_context_allowed"] is False
    assert "VIX alone is not sufficient" in status["missing_reason"]
    assert status["value_text"] == "unknown"


def _metric(data, module_key, metric_key):
    for metric in data["modules"][module_key]["key_metrics"]:
        if metric["metric_key"] == metric_key:
            return metric
    raise AssertionError(f"missing metric {module_key}.{metric_key}")


def _write_json(path, payload):
    path.write_text(json.dumps(payload), encoding="utf-8")


def _write_fake_reports(tmp_path):
    generated_at = "2026-01-01T00:00:00+00:00"
    metric = lambda value, source="FRED", source_badge="official": {
        "value": value,
        "status": "ok",
        "source": source,
        "source_badge": source_badge,
        "observation_date": "2026-01-01",
        "freshness_status": "fresh",
    }
    (tmp_path / "market_snapshot.json").write_text(
        json.dumps(
            {
                "generated_at": generated_at,
                "status": "ok",
                "risk_level": "watch",
                "high_yield_spread": metric(3.4),
                "vix": metric(18.2, source="CBOE"),
                "credit_stress_status": metric("watch"),
                "dgs10": metric(4.52),
                "dgs30": metric(4.83),
                "dfii10": metric(2.1),
                "t10yie": metric(2.35),
                "real_yield_pressure_status": metric("pressure"),
                "core_cpi_yoy": metric(3.1),
                "core_pce_yoy": metric(2.8),
                "ppiaco_yoy": metric(1.7),
                "wti_30d_change": metric(-4.2, source="EIA", source_badge="official_fallback"),
                "brent_30d_change": metric(-3.8, source="EIA", source_badge="official_fallback"),
                "sp500_30d_return": metric(2.2, source="yfinance", source_badge="unofficial_fallback"),
                "sp500_60d_return": metric(5.1, source="yfinance", source_badge="unofficial_fallback"),
                "nasdaq100_30d_return": metric(3.3, source="yfinance", source_badge="unofficial_fallback"),
                "nasdaq100_60d_return": metric(6.4, source="yfinance", source_badge="unofficial_fallback"),
                "raw_extra": "must_not_leak",
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "portfolio_snapshot.json").write_text(
        json.dumps(
            {
                "generated_at": generated_at,
                "status": "ok",
                "max_deviation_asset": {"value": "equity", "status": "ok"},
                "max_deviation_pp": {"value": 2.3, "status": "ok"},
                "equity_total_deviation_pp": {"value": 1.4, "status": "ok"},
                "cash_reserve_status": {"value": "available", "status": "ok"},
                "holdings_updated_at": {"value": "2026-01-01", "status": "ok"},
                "holdings": [{"ticker": "RAW_FUND", "amount": "HOLDINGS_AMOUNT_MUST_NOT_LEAK"}],
                "raw_extra": "must_not_leak",
            }
        ),
        encoding="utf-8",
    )


def _block_network(monkeypatch):
    def _raise_on_network(*args, **kwargs):
        raise AssertionError("Network access is not allowed in key metrics tests.")

    monkeypatch.setattr(socket, "create_connection", _raise_on_network)
