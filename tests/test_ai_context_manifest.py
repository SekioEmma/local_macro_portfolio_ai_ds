import json
import socket

from fastapi.testclient import TestClient

from app_backend.main import app
from app_backend.services import dashboard_service


def test_ai_context_manifest_includes_and_excludes_expected_rows(monkeypatch, tmp_path):
    _block_network(monkeypatch)
    _write_reports(tmp_path)
    monkeypatch.setattr(dashboard_service, "DEFAULT_REPORTS_DIR", tmp_path)

    response = TestClient(app).get("/api/ai/context-preview")

    assert response.status_code == 200
    data = response.json()
    included_keys = {row["metric_key"] for row in data["included_facts"]}
    excluded = {row["metric_key"]: row for row in data["excluded_facts"]}
    model_keys = {row["metric_key"] for row in data["included_model_outputs"]}

    assert "high_yield_spread" in included_keys
    assert "vix" in included_keys
    assert "dgs30_breakout_confirmed" in excluded
    assert excluded["dgs30_breakout_confirmed"]["excluded_reason"] in {
        "status_research_needed",
        "source_badge_research_needed",
    }
    assert "financial_stress_score" in model_keys
    assert "pullback_classification" in model_keys
    assert "financial_stress_score" not in included_keys
    assert "pullback_classification" not in included_keys


def test_model_outputs_preserve_derived_badge_and_boundaries(monkeypatch, tmp_path):
    _block_network(monkeypatch)
    _write_reports(tmp_path)
    monkeypatch.setattr(dashboard_service, "DEFAULT_REPORTS_DIR", tmp_path)

    data = TestClient(app).get("/api/context/manifest").json()
    stress = _model_output(data, "financial_stress_score")
    pullback = _model_output(data, "pullback_classification")

    assert stress["source_badge"] == "derived"
    assert "pressure temperature" in stress["interpretation_boundary"]
    assert stress["input_evidence"]
    assert pullback["source_badge"] == "derived"
    assert "This checklist is not crash probability." in pullback["interpretation_boundary"]
    assert pullback["input_evidence"]


def test_proxy_rows_keep_proxy_badge_and_search_is_excluded(monkeypatch, tmp_path):
    _block_network(monkeypatch)
    _write_reports(tmp_path)
    monkeypatch.setattr(dashboard_service, "DEFAULT_REPORTS_DIR", tmp_path)

    data = TestClient(app).get("/api/ai/context-preview").json()
    proxy_or_derived_rows = [
        row
        for row in data["included_facts"]
        if row["source_badge"] in {"proxy", "derived"}
    ]

    assert proxy_or_derived_rows
    assert all(row["source_badge"] != "official" for row in proxy_or_derived_rows)
    assert data["search_policy"]["search_enabled"] is False
    assert data["search_policy"]["search_derived_default"] == "excluded"


def test_portfolio_policy_excludes_holdings_line_items(monkeypatch, tmp_path):
    _block_network(monkeypatch)
    _write_reports(tmp_path)
    monkeypatch.setattr(dashboard_service, "DEFAULT_REPORTS_DIR", tmp_path)

    body = TestClient(app).get("/api/ai/context-preview").text
    data = json.loads(body)

    assert data["portfolio_context_policy"]["mode"] == "compact_summary_only"
    assert data["portfolio_context_policy"]["holdings_line_items_allowed"] is False
    assert "max_deviation_pp" in (
        data["portfolio_context_policy"]["included_portfolio_metric_keys"]
        + data["portfolio_context_policy"]["excluded_portfolio_metric_keys"]
    )
    assert "RAW_FUND" not in body
    assert "HOLDINGS_AMOUNT_MUST_NOT_LEAK" not in body


def test_manifest_does_not_leak_private_payloads_or_credentials(monkeypatch, tmp_path):
    _block_network(monkeypatch)
    _write_reports(tmp_path)
    monkeypatch.setattr(dashboard_service, "DEFAULT_REPORTS_DIR", tmp_path)

    body = TestClient(app).get("/api/ai/context-preview").text.lower()

    assert "sk-" not in body
    assert "api_key" not in body
    assert "deepseek_api_key" not in body
    assert "tavily_api_key" not in body
    assert ("raw_" + "prompt") not in body
    assert ("raw_" + "provider") not in body
    assert ("raw_" + "holdings") not in body
    assert "must_not_leak" not in body


def test_manifest_risk_boundaries_are_complete(monkeypatch, tmp_path):
    _block_network(monkeypatch)
    _write_reports(tmp_path)
    monkeypatch.setattr(dashboard_service, "DEFAULT_REPORTS_DIR", tmp_path)

    data = TestClient(app).get("/api/ai/context-preview").json()

    assert data["risk_boundaries"] == [
        "No trading instruction.",
        "No crash probability.",
        "No recession probability.",
        "VIX alone is not systemic crisis.",
        "Equity drawdown alone is not systemic crisis.",
        "Proxy breadth is not true breadth.",
        "Financial stress score is pressure temperature, not prediction.",
        "Pullback checklist is risk review, not forecast.",
        "Portfolio deviation cannot be attributed to macro factors.",
    ]


def _model_output(data, metric_key):
    for row in data["included_model_outputs"]:
        if row["metric_key"] == metric_key:
            return row
    raise AssertionError(f"missing model output {metric_key}")


def _write_reports(tmp_path):
    generated_at = "2026-01-01T00:00:00+00:00"

    def metric(value, source="FRED", badge="official", status="ok"):
        return {
            "value": value,
            "status": status,
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
                "investment_grade_spread": metric(1.2),
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
                "hyg_vs_lqd_30d": metric(-1.2, source="yfinance", badge="proxy"),
                "llm_context_pack": {"raw": "must_not_leak"},
                "raw_extra": "must_not_leak",
                "raw_" + "prompt": "must_not_leak",
                "raw_" + "provider_response": "must_not_leak",
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
                "raw_" + "holdings": "must_not_leak",
            }
        ),
        encoding="utf-8",
    )


def _block_network(monkeypatch):
    def _raise_on_network(*args, **kwargs):
        raise AssertionError("Network access is not allowed in manifest tests.")

    monkeypatch.setattr(socket, "create_connection", _raise_on_network)
