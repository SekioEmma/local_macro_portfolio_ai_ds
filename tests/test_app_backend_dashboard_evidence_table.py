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
EVIDENCE_MODULE_KEYS = MODULE_KEYS | {"labor_macro"}


def test_dashboard_evidence_table_returns_rows(monkeypatch, tmp_path):
    _block_network(monkeypatch)
    _write_fake_reports(tmp_path)
    monkeypatch.setattr(dashboard_service, "DEFAULT_REPORTS_DIR", tmp_path)

    response = TestClient(app).get("/api/dashboard/evidence-table")

    assert response.status_code == 200
    data = response.json()
    assert data["row_count"] == len(data["rows"])
    assert data["row_count"] > 0
    assert set(data["modules"]) == EVIDENCE_MODULE_KEYS
    assert {row["module"] for row in data["rows"]} == EVIDENCE_MODULE_KEYS
    assert data["filters"]["available"]["modules"] == sorted(EVIDENCE_MODULE_KEYS)

    for row in data["rows"]:
        assert row["row_id"] == f"{row['module']}:{row['metric_key']}"
        assert row["module"]
        assert row["metric_key"]
        assert row["display_name"]
        assert row["value_text"]
        assert row["value_text"] != "--"
        assert row["source_badge"]
        assert row["freshness_status"]
        assert "ai_context_allowed" in row


def test_dashboard_evidence_table_filters_rows(monkeypatch, tmp_path):
    _block_network(monkeypatch)
    _write_fake_reports(tmp_path)
    monkeypatch.setattr(dashboard_service, "DEFAULT_REPORTS_DIR", tmp_path)

    response = TestClient(app).get(
        "/api/dashboard/evidence-table",
        params={
            "module": "rate_pressure",
            "status": "ok",
            "source_badge": "official",
            "ai_context_allowed": True,
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["row_count"] == len(data["rows"])
    assert data["filters"]["applied"] == {
        "module": "rate_pressure",
        "status": "ok",
        "source_badge": "official",
        "ai_context_allowed": True,
    }
    assert data["rows"]
    assert all(row["module"] == "rate_pressure" for row in data["rows"])
    assert all(row["status"] == "ok" for row in data["rows"])
    assert all(row["source_badge"] == "official" for row in data["rows"])
    assert all(row["ai_context_allowed"] is True for row in data["rows"])


def test_dashboard_evidence_table_blocks_missing_from_ai_context(monkeypatch, tmp_path):
    _block_network(monkeypatch)
    (tmp_path / "market_snapshot.json").write_text(
        json.dumps(
            {
                "generated_at": "2026-01-01T00:00:00+00:00",
                "status": "ok",
                "high_yield_spread": {
                    "value": 3.4,
                    "status": "not_available",
                    "source": "FRED",
                    "source_badge": "official",
                    "observation_date": "2026-01-01",
                    "freshness_status": "fresh",
                },
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(dashboard_service, "DEFAULT_REPORTS_DIR", tmp_path)

    rows = TestClient(app).get("/api/dashboard/evidence-table").json()["rows"]

    blocked_statuses = {
        "missing",
        "research_needed",
        "insufficient_history",
        "not_available",
    }
    blocked_rows = [row for row in rows if row["status"] in blocked_statuses]
    assert blocked_rows
    assert all(row["ai_context_allowed"] is False for row in blocked_rows)


def test_dashboard_evidence_table_blocks_search_derived_from_ai_context(
    monkeypatch, tmp_path
):
    _block_network(monkeypatch)
    _write_fake_reports(tmp_path, source_badge="search-derived")
    monkeypatch.setattr(dashboard_service, "DEFAULT_REPORTS_DIR", tmp_path)

    rows = TestClient(app).get("/api/dashboard/evidence-table").json()["rows"]
    search_rows = [row for row in rows if row["source_badge"] == "search-derived"]

    assert search_rows
    assert all(row["ai_context_allowed"] is False for row in search_rows)


def test_dashboard_evidence_table_does_not_leak_raw_or_holdings(
    monkeypatch, tmp_path
):
    _block_network(monkeypatch)
    _write_fake_reports(tmp_path)
    monkeypatch.setattr(dashboard_service, "DEFAULT_REPORTS_DIR", tmp_path)

    body = TestClient(app).get("/api/dashboard/evidence-table").text

    assert "raw_extra" not in body
    assert "market_snapshot" not in body
    assert "portfolio_snapshot" not in body
    assert "llm_context_pack" not in body
    assert "RAW_FUND" not in body
    assert "HOLDINGS_AMOUNT_MUST_NOT_LEAK" not in body
    assert "must_not_leak" not in body
    assert "sk-" not in body
    assert "G:\\local_macro_portfolio_ai\\local_macro_portfolio_ai_ds" not in body


def test_dashboard_evidence_table_preserves_financial_boundaries(
    monkeypatch, tmp_path
):
    _block_network(monkeypatch)
    _write_fake_reports(tmp_path)
    monkeypatch.setattr(dashboard_service, "DEFAULT_REPORTS_DIR", tmp_path)

    data = TestClient(app).get("/api/dashboard/evidence-table").json()
    ppiaco = _row(data, "inflation_energy_pressure", "ppiaco_yoy")
    dgs10 = _row(data, "rate_pressure", "dgs10")
    max_deviation = _row(data, "portfolio_deviation", "max_deviation_pp")

    assert "not final demand PPI" in ppiaco["interpretation_hint"]
    assert "not intraday" in dgs10["interpretation_hint"]
    assert "is intraday" not in dgs10["interpretation_hint"]
    assert "market factors" in max_deviation["interpretation_hint"]


def test_dashboard_evidence_table_handles_missing_and_invalid_reports(
    monkeypatch, tmp_path
):
    _block_network(monkeypatch)
    (tmp_path / "market_snapshot.json").write_text("{invalid json", encoding="utf-8")
    monkeypatch.setattr(dashboard_service, "DEFAULT_REPORTS_DIR", tmp_path)

    response = TestClient(app).get("/api/dashboard/evidence-table")

    assert response.status_code == 200
    data = response.json()
    assert data["overall_status"] in {"degraded", "error"}
    assert data["row_count"] == len(data["rows"])
    assert data["rows"]
    assert data["next_actions"]


def _row(data, module_key, metric_key):
    for row in data["rows"]:
        if row["module"] == module_key and row["metric_key"] == metric_key:
            return row
    raise AssertionError(f"missing row {module_key}.{metric_key}")


def _write_fake_reports(tmp_path, source_badge="official"):
    generated_at = "2026-01-01T00:00:00+00:00"

    def metric(value, source="FRED", badge=source_badge):
        return {
            "value": value,
            "status": "ok",
            "source": source,
            "source_badge": badge,
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
                "unemployment_rate": metric(4.0),
                "initial_jobless_claims": metric(230000),
                "wti_30d_change": metric(-4.2, source="EIA"),
                "brent_30d_change": metric(-3.8, source="EIA"),
                "sp500_30d_return": metric(2.2, source="yfinance"),
                "sp500_60d_return": metric(5.1, source="yfinance"),
                "nasdaq100_30d_return": metric(3.3, source="yfinance"),
                "nasdaq100_60d_return": metric(6.4, source="yfinance"),
                "llm_context_pack": {"raw": "must_not_leak"},
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
                "holdings": [
                    {
                        "ticker": "RAW_FUND",
                        "amount": "HOLDINGS_AMOUNT_MUST_NOT_LEAK",
                    }
                ],
                "raw_extra": "must_not_leak",
            }
        ),
        encoding="utf-8",
    )


def _block_network(monkeypatch):
    def _raise_on_network(*args, **kwargs):
        raise AssertionError("Network access is not allowed in evidence table tests.")

    monkeypatch.setattr(socket, "create_connection", _raise_on_network)
