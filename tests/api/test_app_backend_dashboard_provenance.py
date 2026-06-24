import json

from fastapi.testclient import TestClient

from app_backend.main import app
from app_backend.services import dashboard_service

from tests.helpers.dashboard_fixtures import block_network_calls


def test_high_yield_with_complete_provenance_enters_ai_context(monkeypatch, tmp_path):
    block_network_calls(monkeypatch)
    _write_market(
        tmp_path,
        {
            "financial_conditions": {
                "high_yield_spread": _metric(
                    2.72,
                    source="FRED",
                    source_tier="official_or_public_data_api",
                    freshness="fresh",
                    observation_date="2026-05-28",
                )
            }
        },
    )
    monkeypatch.setattr(dashboard_service, "DEFAULT_REPORTS_DIR", tmp_path)

    row = _row(TestClient(app).get("/api/dashboard/evidence-table").json(), "credit_stress", "high_yield_spread")

    assert row["source_badge"] == "official"
    assert row["freshness_status"] == "fresh"
    assert row["observation_date"] == "2026-05-28"
    assert row["ai_context_allowed"] is True
    assert row["blocked_reason"] is None


def test_dgs10_official_quality_metadata_enters_ai_context(monkeypatch, tmp_path):
    block_network_calls(monkeypatch)
    _write_market(
        tmp_path,
        {
            "macro_data": {
                "dgs10": {
                    "value": 4.45,
                    "status": "ok",
                    "source": "FRED",
                    "source_tier": "official_api",
                    "observation_date": "2026-05-28",
                }
            },
            "data_quality": {
                "market_data_quality": {
                    "dgs10": {
                        "status": "ok",
                        "source_tier": "official_api",
                        "freshness_status": "fresh",
                        "observation_date": "2026-05-28",
                    }
                }
            },
        },
    )
    monkeypatch.setattr(dashboard_service, "DEFAULT_REPORTS_DIR", tmp_path)

    row = _row(TestClient(app).get("/api/dashboard/evidence-table").json(), "rate_pressure", "dgs10")

    assert row["source_badge"] == "official"
    assert row["freshness_status"] == "fresh"
    assert row["ai_context_allowed"] is True
    assert "not intraday" in row["interpretation_hint"]


def test_derived_dgs10_average_without_hint_is_blocked(monkeypatch, tmp_path):
    block_network_calls(monkeypatch)
    _write_market(
        tmp_path,
        {
            "market_data_package": {
                "treasury_yields": {
                    "dgs10_5d_avg": {
                        "value": 4.512,
                        "status": "ok",
                        "source": "FRED:DGS10",
                        "source_series": "FRED:DGS10",
                        "source_tier": "official_or_public_data_api",
                        "freshness": "fresh",
                        "observation_date": "2026-05-28",
                    }
                }
            }
        },
    )
    monkeypatch.setattr(dashboard_service, "DEFAULT_REPORTS_DIR", tmp_path)

    row = _row(TestClient(app).get("/api/dashboard/evidence-table").json(), "rate_pressure", "dgs10_5d_avg")

    assert row["source_badge"] == "derived"
    assert row["ai_context_allowed"] is False
    assert row["blocked_reason"] == "dependency_metadata_incomplete"


def test_holdings_updated_at_is_local_fresh_without_holdings_detail(monkeypatch, tmp_path):
    block_network_calls(monkeypatch)
    (tmp_path / "portfolio_snapshot.json").write_text(
        json.dumps(
            {
                "status": "ok",
                "holdings_updated_at": "2026-05-27",
                "holdings_freshness_status": "fresh",
                "holdings": [{"ticker": "RAW_FUND", "amount": "HOLDINGS_AMOUNT_MUST_NOT_LEAK"}],
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(dashboard_service, "DEFAULT_REPORTS_DIR", tmp_path)

    response = TestClient(app).get("/api/dashboard/evidence-table")
    row = _row(response.json(), "portfolio_deviation", "holdings_updated_at")

    assert row["source_badge"] == "local"
    assert row["freshness_status"] == "fresh"
    assert row["observation_date"] == "2026-05-27"
    assert row["ai_context_allowed"] is True
    assert "RAW_FUND" not in response.text
    assert "HOLDINGS_AMOUNT_MUST_NOT_LEAK" not in response.text


def test_value_with_missing_provenance_has_blocked_reason(monkeypatch, tmp_path):
    block_network_calls(monkeypatch)
    _write_market(
        tmp_path,
        {
            "financial_conditions": {
                "vix": {
                    "value": 15.74,
                    "status": "ok",
                }
            }
        },
    )
    monkeypatch.setattr(dashboard_service, "DEFAULT_REPORTS_DIR", tmp_path)

    row = _row(TestClient(app).get("/api/dashboard/evidence-table").json(), "credit_stress", "vix")

    assert row["ai_context_allowed"] is False
    assert row["blocked_reason"] == "source_badge_missing"
    assert row["source_badge"] == "missing"


def _metric(value, *, source, source_tier, freshness, observation_date):
    return {
        "value": value,
        "status": "ok",
        "source": source,
        "source_tier": source_tier,
        "freshness": freshness,
        "observation_date": observation_date,
        "interpretation_hint": "Audited compact provenance.",
    }


def _write_market(tmp_path, payload):
    (tmp_path / "market_snapshot.json").write_text(
        json.dumps(
            {
                "generated_at": "2026-01-01T00:00:00+00:00",
                "status": "ok",
                **payload,
            }
        ),
        encoding="utf-8",
    )


def _row(data, module_key, metric_key):
    for row in data["rows"]:
        if row["module"] == module_key and row["metric_key"] == metric_key:
            return row
    raise AssertionError(f"missing row {module_key}.{metric_key}")
