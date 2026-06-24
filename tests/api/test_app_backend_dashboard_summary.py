import json

from fastapi.testclient import TestClient

from app_backend.main import app
from app_backend.services import dashboard_service

from tests.helpers.dashboard_fixtures import block_network_calls


MODULE_KEYS = {
    "credit_stress",
    "rate_pressure",
    "real_yield_pressure",
    "inflation_energy_pressure",
    "equity_trend",
    "breadth_concentration_proxy",
    "market_stress_derived",
    "portfolio_deviation",
}


def test_dashboard_summary_returns_missing_when_reports_absent(monkeypatch, tmp_path):
    block_network_calls(monkeypatch)
    monkeypatch.setattr(dashboard_service, "DEFAULT_REPORTS_DIR", tmp_path)

    response = TestClient(app).get("/api/dashboard/summary")

    assert response.status_code == 200
    data = response.json()
    assert data["overall_status"] in {"missing", "degraded"}
    assert set(data["modules"]) == MODULE_KEYS
    assert all(module["status"] == "missing" for module in data["modules"].values())
    assert data["provider_health"]["overall_status"] == "not_run_yet"
    assert data["next_actions"]


def test_dashboard_summary_returns_compact_fake_reports(monkeypatch, tmp_path):
    block_network_calls(monkeypatch)
    _write_json(
        tmp_path / "market_snapshot.json",
        {
            "generated_at": "2026-01-01T00:00:00+00:00",
            "status": "ok",
            "risk_level": "balanced",
            "financial_conditions": {"label": "neutral"},
            "high_yield_spread": {"status": "ok"},
            "dgs10": {"value": 4.2},
            "real_yield_10y": {"value": 1.9},
            "cpi": {"status": "ok"},
            "oil": {"status": "ok"},
            "sp500": {"status": "ok"},
            "raw_extra": "must_not_leak",
        },
    )
    _write_json(
        tmp_path / "market_temperature.json",
        {
            "generated_at": "2026-01-01T00:00:00+00:00",
            "status": "ok",
            "equity_temperature": {"label": "uptrend"},
            "raw_extra": "must_not_leak",
        },
    )
    _write_json(
        tmp_path / "portfolio_snapshot.json",
        {
            "generated_at": "2026-01-01T00:00:00+00:00",
            "status": "ok",
            "holdings": [{"ticker": "RAW", "amount": 999999}],
            "raw_extra": "must_not_leak",
        },
    )
    _write_json(
        tmp_path / "provider_health_check.json",
        {
            "generated_at": "2026-01-01T00:00:00+00:00",
            "overall_status": "ok",
            "summary": {"ok": 2},
            "checks": [
                {
                    "key": "fred_dgs10",
                    "provider": "FRED",
                    "status": "ok",
                    "source": "FRED",
                    "observation_date": "2026-01-01",
                    "value_present": True,
                    "raw_extra": "must_not_leak",
                }
            ],
            "raw_extra": "must_not_leak",
        },
    )
    monkeypatch.setattr(dashboard_service, "DEFAULT_REPORTS_DIR", tmp_path)

    response = TestClient(app).get("/api/dashboard/summary")

    assert response.status_code == 200
    data = response.json()
    assert set(data["modules"]) == MODULE_KEYS
    assert data["overall_status"] in {"ok", "degraded"}
    assert data["overall_risk_level"] == "balanced"
    assert data["provider_health"]["summary"] == {"ok": 2}

    body = json.dumps(data, sort_keys=True)
    assert "raw_extra" not in body
    assert "must_not_leak" not in body
    assert "999999" not in body
    assert "sk-" not in body
    assert "G:\\local_macro_portfolio_ai\\local_macro_portfolio_ai_ds" not in body


def test_dashboard_summary_handles_invalid_report_json(monkeypatch, tmp_path):
    block_network_calls(monkeypatch)
    (tmp_path / "market_snapshot.json").write_text("{invalid json", encoding="utf-8")
    monkeypatch.setattr(dashboard_service, "DEFAULT_REPORTS_DIR", tmp_path)

    response = TestClient(app).get("/api/dashboard/summary")

    assert response.status_code == 200
    data = response.json()
    assert data["overall_status"] in {"degraded", "error"}
    assert data["modules"]["credit_stress"]["status"] == "error"
    assert data["modules"]["credit_stress"]["error_summary"]
    assert len(data["modules"]["credit_stress"]["error_summary"]) <= 200


def test_dashboard_summary_accepts_bom_encoded_portfolio_snapshot(monkeypatch, tmp_path):
    block_network_calls(monkeypatch)
    (tmp_path / "portfolio_snapshot.json").write_text(
        json.dumps(
            {
                "generated_at": "2026-01-01T00:00:00+00:00",
                "status": "ok",
                "holdings": [{"ticker": "RAW", "amount": 999999}],
                "raw_extra": "must_not_leak",
            }
        ),
        encoding="utf-8-sig",
    )
    monkeypatch.setattr(dashboard_service, "DEFAULT_REPORTS_DIR", tmp_path)

    response = TestClient(app).get("/api/dashboard/summary")

    assert response.status_code == 200
    data = response.json()
    assert data["modules"]["portfolio_deviation"]["status"] == "unknown"
    assert "portfolio snapshot available" in data["modules"]["portfolio_deviation"]["summary"]
    assert not any(
        item["key"] == "portfolio_snapshot" and item["status"] == "error"
        for item in data["missing_data"]
    )

    body = json.dumps(data, sort_keys=True)
    assert "999999" not in body
    assert "raw_extra" not in body
    assert "must_not_leak" not in body


def test_dashboard_summary_does_not_read_real_outputs(monkeypatch, tmp_path):
    block_network_calls(monkeypatch)
    custom_reports = tmp_path / "custom_reports"
    custom_reports.mkdir()
    monkeypatch.setattr(dashboard_service, "DEFAULT_REPORTS_DIR", custom_reports)

    response = TestClient(app).get("/api/dashboard/summary")

    assert response.status_code == 200
    assert response.json()["data_freshness"]["files"]["market_snapshot"]["status"] == "missing"


def _write_json(path, payload):
    path.write_text(json.dumps(payload), encoding="utf-8")
