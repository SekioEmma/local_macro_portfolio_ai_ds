import json
import socket

from fastapi.testclient import TestClient

from app_backend.main import app
from app_backend.services import dashboard_service


def test_dashboard_exposes_portfolio_deviation_compact_fields(monkeypatch, tmp_path):
    _block_network(monkeypatch)
    _write_portfolio_snapshot(tmp_path)
    monkeypatch.setattr(dashboard_service, "DEFAULT_REPORTS_DIR", tmp_path)

    data = TestClient(app).get("/api/dashboard/summary").json()
    module = data["modules"]["portfolio_deviation"]

    assert module["status"] == "watch"
    assert _metric(module, "max_deviation_asset")["value"] == "sp500"
    assert _metric(module, "max_deviation_pp")["value_text"] == "+4.00pp"
    assert _metric(module, "equity_total_deviation_pp")["value_text"] == "+1.00pp"
    assert (
        _metric(module, "cash_reserve_status")["value"]
        == "cash_excluded_from_target_allocation"
    )
    assert _metric(module, "holdings_updated_at")["freshness_status"] == "fresh"

    body = json.dumps(data, ensure_ascii=False, sort_keys=True)
    assert "RAW_FUND" not in body
    assert "1234567" not in body
    assert "999999" not in body
    assert "buy" not in body.lower()
    assert "sell" not in body.lower()
    assert "market factors" in body
    assert "cash reserve excluded from target mix" in body.lower()


def test_evidence_table_allows_only_portfolio_compact_context(monkeypatch, tmp_path):
    _block_network(monkeypatch)
    _write_portfolio_snapshot(tmp_path)
    monkeypatch.setattr(dashboard_service, "DEFAULT_REPORTS_DIR", tmp_path)

    data = TestClient(app).get("/api/dashboard/evidence-table?module=portfolio_deviation").json()
    rows = data["rows"]

    assert {row["metric_key"] for row in rows} == {
        "max_deviation_asset",
        "max_deviation_pp",
        "equity_total_deviation_pp",
        "cash_reserve_status",
        "holdings_updated_at",
    }
    assert all(row["source"] == "local_portfolio_compact" for row in rows)
    assert all(row["source_badge"] == "local" for row in rows)
    assert all(row["ai_context_allowed"] is True for row in rows)
    assert all(row["blocked_reason"] is None for row in rows)

    body = json.dumps(data, ensure_ascii=False, sort_keys=True)
    assert "RAW_FUND" not in body
    assert "1234567" not in body
    assert "999999" not in body


def test_stale_portfolio_compact_is_not_ok_or_ai_allowed(monkeypatch, tmp_path):
    _block_network(monkeypatch)
    _write_portfolio_snapshot(tmp_path, holdings_updated_at="2026-04-01")
    monkeypatch.setattr(dashboard_service, "DEFAULT_REPORTS_DIR", tmp_path)

    client = TestClient(app)
    summary = client.get("/api/dashboard/summary").json()
    evidence = client.get("/api/dashboard/evidence-table?module=portfolio_deviation").json()

    assert summary["modules"]["portfolio_deviation"]["status"] == "stale"
    assert all(row["status"] == "stale" for row in evidence["rows"])
    assert all(row["ai_context_allowed"] is False for row in evidence["rows"])


def _write_portfolio_snapshot(
    tmp_path,
    *,
    holdings_updated_at="2026-06-01",
):
    (tmp_path / "portfolio_snapshot.json").write_text(
        json.dumps(
            {
                "generated_at": "2026-06-10T00:00:00+00:00",
                "status": "ok",
                "holdings_updated_at": holdings_updated_at,
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
            }
        ),
        encoding="utf-8",
    )


def _metric(module, metric_key):
    for metric in module["key_metrics"]:
        if metric["metric_key"] == metric_key:
            return metric
    raise AssertionError(f"missing portfolio_deviation.{metric_key}")


def _block_network(monkeypatch):
    def _raise_on_network(*args, **kwargs):
        raise AssertionError("Network access is not allowed in portfolio dashboard tests.")

    monkeypatch.setattr(socket, "create_connection", _raise_on_network)
