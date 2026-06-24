import json

from fastapi.testclient import TestClient

from app_backend.main import app
from app_backend.services import dashboard_service

from tests.helpers.dashboard_fixtures import block_network_calls


def test_value_with_missing_source_badge_is_not_ai_context(monkeypatch, tmp_path):
    block_network_calls(monkeypatch)
    _write_market(
        tmp_path,
        {
            "dgs10": {
                "value": 4.52,
                "status": "ok",
                "observation_date": "2026-01-01",
                "freshness_status": "fresh",
            }
        },
    )
    monkeypatch.setattr(dashboard_service, "DEFAULT_REPORTS_DIR", tmp_path)

    data = TestClient(app).get("/api/dashboard/evidence-table").json()
    dgs10 = _row(data, "rate_pressure", "dgs10")

    assert dgs10["source_badge"] == "missing"
    assert dgs10["ai_context_allowed"] is False


def test_value_with_unknown_freshness_is_not_ai_context(monkeypatch, tmp_path):
    block_network_calls(monkeypatch)
    _write_market(
        tmp_path,
        {
            "dgs10": {
                "value": 4.52,
                "status": "ok",
                "source": "FRED",
                "source_badge": "official",
                "observation_date": "2026-01-01",
            }
        },
    )
    monkeypatch.setattr(dashboard_service, "DEFAULT_REPORTS_DIR", tmp_path)

    data = TestClient(app).get("/api/dashboard/evidence-table").json()
    dgs10 = _row(data, "rate_pressure", "dgs10")

    assert dgs10["freshness_status"] == "unknown"
    assert dgs10["ai_context_allowed"] is False


def test_dgs30_missing_blocks_distance_to_5pct(monkeypatch, tmp_path):
    block_network_calls(monkeypatch)
    _write_market(
        tmp_path,
        {
            "dgs30_distance_to_5pct": {
                "value": 0.2,
                "status": "ok",
                "source": "FRED",
                "source_badge": "official",
                "observation_date": "2026-01-01",
                "freshness_status": "fresh",
            }
        },
    )
    monkeypatch.setattr(dashboard_service, "DEFAULT_REPORTS_DIR", tmp_path)

    data = TestClient(app).get("/api/dashboard/summary").json()
    distance = _metric(data, "rate_pressure", "dgs30_distance_to_5pct")

    assert distance["status"] == "missing"
    assert distance["value"] is None
    assert distance["source_badge"] == "missing"
    assert distance["ai_context_allowed"] is False
    assert "DGS30 is missing" in distance["missing_reason"]


def test_all_missing_real_yield_pressure_is_not_ok(monkeypatch, tmp_path):
    block_network_calls(monkeypatch)
    _write_market(tmp_path, {"real_yield_10y": {"status": "ok"}})
    monkeypatch.setattr(dashboard_service, "DEFAULT_REPORTS_DIR", tmp_path)

    data = TestClient(app).get("/api/dashboard/summary").json()

    assert data["modules"]["real_yield_pressure"]["status"] != "ok"


def test_all_insufficient_history_equity_trend_is_not_ok(monkeypatch, tmp_path):
    block_network_calls(monkeypatch)
    _write_market(tmp_path, {"sp500": {"status": "ok"}})
    monkeypatch.setattr(dashboard_service, "DEFAULT_REPORTS_DIR", tmp_path)

    data = TestClient(app).get("/api/dashboard/summary").json()

    assert data["modules"]["equity_trend"]["status"] != "ok"


def test_portfolio_deviation_without_compact_fields_is_not_ok(monkeypatch, tmp_path):
    block_network_calls(monkeypatch)
    (tmp_path / "portfolio_snapshot.json").write_text(
        json.dumps(
            {
                "generated_at": "2026-01-01T00:00:00+00:00",
                "status": "ok",
                "holdings_updated_at": {"value": "2026-01-01", "status": "ok"},
                "holdings": [{"ticker": "RAW", "amount": 999999}],
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(dashboard_service, "DEFAULT_REPORTS_DIR", tmp_path)

    data = TestClient(app).get("/api/dashboard/summary").json()

    assert data["modules"]["portfolio_deviation"]["status"] != "ok"
    body = json.dumps(data, sort_keys=True)
    assert "999999" not in body
    assert "RAW" not in body


def test_blocked_statuses_and_search_derived_do_not_enter_ai_context(monkeypatch, tmp_path):
    block_network_calls(monkeypatch)
    _write_market(
        tmp_path,
        {
            "high_yield_spread": {
                "value": 3.2,
                "status": "stale",
                "source": "FRED",
                "source_badge": "official",
                "observation_date": "2026-01-01",
                "freshness_status": "stale",
            },
            "vix": {
                "value": 19.0,
                "status": "ok",
                "source": "search",
                "source_badge": "search-derived",
                "observation_date": "2026-01-01",
                "freshness_status": "fresh",
            },
        },
    )
    monkeypatch.setattr(dashboard_service, "DEFAULT_REPORTS_DIR", tmp_path)

    data = TestClient(app).get("/api/dashboard/evidence-table").json()

    assert _row(data, "credit_stress", "high_yield_spread")["ai_context_allowed"] is False
    assert _row(data, "credit_stress", "vix")["ai_context_allowed"] is False


def test_error_payload_with_null_value_does_not_display_error_as_value(monkeypatch, tmp_path):
    block_network_calls(monkeypatch)
    _write_market(
        tmp_path,
        {
            "high_yield_spread": {
                "value": None,
                "status": "error",
                "source": "FRED",
                "source_badge": "official",
                "observation_date": None,
                "freshness_status": "unknown",
                "error": "provider failed",
            },
        },
    )
    monkeypatch.setattr(dashboard_service, "DEFAULT_REPORTS_DIR", tmp_path)

    data = TestClient(app).get("/api/dashboard/evidence-table").json()
    row = _row(data, "credit_stress", "high_yield_spread")

    assert row["value"] is None
    assert row["value_text"] == "missing"
    assert row["ai_context_allowed"] is False


def _write_market(tmp_path, metrics):
    payload = {
        "generated_at": "2026-01-01T00:00:00+00:00",
        "status": "ok",
        **metrics,
    }
    (tmp_path / "market_snapshot.json").write_text(json.dumps(payload), encoding="utf-8")


def _metric(data, module_key, metric_key):
    for metric in data["modules"][module_key]["key_metrics"]:
        if metric["metric_key"] == metric_key:
            return metric
    raise AssertionError(f"missing metric {module_key}.{metric_key}")


def _row(data, module_key, metric_key):
    for row in data["rows"]:
        if row["module"] == module_key and row["metric_key"] == metric_key:
            return row
    raise AssertionError(f"missing row {module_key}.{metric_key}")
