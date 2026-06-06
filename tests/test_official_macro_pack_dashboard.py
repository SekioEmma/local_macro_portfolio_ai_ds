import json
import socket

from fastapi.testclient import TestClient

from app_backend.main import app
from app_backend.services import dashboard_service
from data_quality import official_macro_pack


def test_official_macro_pack_definitions_are_stable():
    metrics = official_macro_pack.OFFICIAL_MACRO_METRICS

    assert metrics["dgs2"].source_series == "DGS2"
    assert metrics["dgs30"].source_series == "DGS30"
    assert metrics["dfii10"].source_series == "DFII10"
    assert metrics["t10yie"].source_series == "T10YIE"
    assert metrics["core_cpi_yoy"].source_series == "CPILFESL"
    assert metrics["core_pce_yoy"].source_series == "PCEPILFE"
    assert metrics["unemployment_rate"].source_series == "UNRATE"
    assert metrics["initial_jobless_claims"].source_series == "ICSA"
    assert metrics["ppi_final_demand"].status_when_missing == "research_needed"
    assert metrics["ppi_final_demand"].source_series is None


def test_official_macro_values_surface_with_provenance(monkeypatch, tmp_path):
    _block_network(monkeypatch)
    _write_market(
        tmp_path,
        {
            "dgs2": _metric(4.1),
            "dgs30": _metric(4.8),
            "dfii10": _metric(2.0),
            "t10yie": _metric(2.3),
            "core_cpi_yoy": _metric(3.2),
            "core_pce_yoy": _metric(2.7),
        },
    )
    monkeypatch.setattr(dashboard_service, "DEFAULT_REPORTS_DIR", tmp_path)

    data = TestClient(app).get("/api/dashboard/evidence-table").json()

    for module, key in (
        ("rate_pressure", "dgs2"),
        ("rate_pressure", "dgs30"),
        ("real_yield_pressure", "dfii10"),
        ("real_yield_pressure", "t10yie"),
        ("inflation_energy_pressure", "core_cpi_yoy"),
        ("inflation_energy_pressure", "core_pce_yoy"),
    ):
        row = _row(data, module, key)
        assert row["status"] == "ok"
        assert row["source"] == "FRED"
        assert row["source_badge"] == "official"
        assert row["observation_date"] == "2026-01-01"
        assert row["freshness_status"] == "fresh"
        assert row["interpretation_hint"]
        assert row["ai_context_allowed"] is True


def test_official_macro_aliases_surface_real_yield_rows(monkeypatch, tmp_path):
    _block_network(monkeypatch)
    _write_market(
        tmp_path,
        {
            "real_yield_10y": _metric(1.9),
            "breakeven_inflation_10y": _metric(2.4),
        },
    )
    monkeypatch.setattr(dashboard_service, "DEFAULT_REPORTS_DIR", tmp_path)

    data = TestClient(app).get("/api/dashboard/evidence-table").json()

    dfii10 = _row(data, "real_yield_pressure", "dfii10")
    t10yie = _row(data, "real_yield_pressure", "t10yie")
    assert dfii10["value"] == 1.9
    assert t10yie["value"] == 2.4
    assert dfii10["source_badge"] == "official"
    assert t10yie["source_badge"] == "official"


def test_missing_official_macro_rows_are_blocked_with_reason(monkeypatch, tmp_path):
    _block_network(monkeypatch)
    _write_market(tmp_path, {})
    monkeypatch.setattr(dashboard_service, "DEFAULT_REPORTS_DIR", tmp_path)

    data = TestClient(app).get("/api/dashboard/evidence-table").json()

    for module, key in (
        ("rate_pressure", "dgs2"),
        ("real_yield_pressure", "dfii10"),
        ("real_yield_pressure", "t10yie"),
        ("inflation_energy_pressure", "core_cpi_yoy"),
        ("inflation_energy_pressure", "core_pce_yoy"),
    ):
        row = _row(data, module, key)
        assert row["status"] == "missing"
        assert row["source"]
        assert row["source_badge"] == "missing"
        assert row["missing_reason"]
        assert row["interpretation_hint"]
        assert row["ai_context_allowed"] is False


def test_ppi_boundary_preserves_research_needed(monkeypatch, tmp_path):
    _block_network(monkeypatch)
    _write_market(tmp_path, {"ppiaco_yoy": _metric(1.6)})
    monkeypatch.setattr(dashboard_service, "DEFAULT_REPORTS_DIR", tmp_path)

    data = TestClient(app).get("/api/dashboard/evidence-table").json()
    ppiaco = _row(data, "inflation_energy_pressure", "ppiaco_yoy")
    final_demand = _row(data, "inflation_energy_pressure", "ppi_final_demand")

    assert "not final demand PPI" in ppiaco["interpretation_hint"]
    assert final_demand["status"] == "research_needed"
    assert final_demand["source_badge"] == "research_needed"
    assert "do not use PPIACO as final demand" in final_demand["missing_reason"]
    assert final_demand["ai_context_allowed"] is False


def test_core_inflation_index_levels_are_not_displayed_as_yoy(monkeypatch, tmp_path):
    _block_network(monkeypatch)
    _write_market(
        tmp_path,
        {
            "core_cpi_yoy": _metric(335.42, unit="index"),
            "core_pce_yoy": _metric(129.63, unit="index"),
        },
    )
    monkeypatch.setattr(dashboard_service, "DEFAULT_REPORTS_DIR", tmp_path)

    data = TestClient(app).get("/api/dashboard/evidence-table").json()
    cpi = _row(data, "inflation_energy_pressure", "core_cpi_yoy")
    pce = _row(data, "inflation_energy_pressure", "core_pce_yoy")

    for row in (cpi, pce):
        assert row["status"] == "insufficient_history"
        assert row["value"] is None
        assert row["value_text"] == "insufficient history"
        assert row["source_badge"] == "missing"
        assert row["ai_context_allowed"] is False
        assert row["missing_reason"] == (
            "Only index level is available; YoY requires historical comparison."
        )
    assert "+335.42%" not in json.dumps(data)
    assert "+129.63%" not in json.dumps(data)


def test_core_inflation_yoy_decimal_and_percent_format_correctly(monkeypatch, tmp_path):
    _block_network(monkeypatch)
    _write_market(
        tmp_path,
        {
            "core_cpi_yoy": _metric(0.0335),
            "core_pce_yoy": _metric(3.12),
        },
    )
    monkeypatch.setattr(dashboard_service, "DEFAULT_REPORTS_DIR", tmp_path)

    data = TestClient(app).get("/api/dashboard/evidence-table").json()

    assert _row(data, "inflation_energy_pressure", "core_cpi_yoy")["value_text"] == "+3.35%"
    assert _row(data, "inflation_energy_pressure", "core_pce_yoy")["value_text"] == "+3.12%"


def test_official_macro_response_avoids_raw_and_consensus_words(monkeypatch, tmp_path):
    _block_network(monkeypatch)
    _write_market(
        tmp_path,
        {
            "dgs2": _metric(4.1),
            "core_cpi_yoy": _metric(3.2),
            "raw_provider_response": "must_not_leak",
            "holdings": [{"ticker": "RAW_HOLDING"}],
            "api_key": "API_SECRET_PLACEHOLDER_MUST_NOT_APPEAR",
        },
    )
    monkeypatch.setattr(dashboard_service, "DEFAULT_REPORTS_DIR", tmp_path)

    body = TestClient(app).get("/api/dashboard/evidence-table").text
    lower_body = body.lower()

    assert "must_not_leak" not in body
    assert "RAW_HOLDING" not in body
    assert "API_SECRET_PLACEHOLDER_MUST_NOT_APPEAR" not in body
    assert "consensus" not in lower_body
    assert "surprise" not in lower_body


def _metric(value, *, unit=None):
    return {
        "value": value,
        "status": "ok",
        "observation_date": "2026-01-01",
        "freshness_status": "fresh",
        **({"unit": unit} if unit else {}),
    }


def _write_market(tmp_path, metrics):
    payload = {
        "generated_at": "2026-01-01T00:00:00+00:00",
        "status": "ok",
        **metrics,
    }
    (tmp_path / "market_snapshot.json").write_text(json.dumps(payload), encoding="utf-8")


def _row(data, module_key, metric_key):
    for row in data["rows"]:
        if row["module"] == module_key and row["metric_key"] == metric_key:
            return row
    raise AssertionError(f"missing row {module_key}.{metric_key}")


def _block_network(monkeypatch):
    def _raise_on_network(*args, **kwargs):
        raise AssertionError("Network access is not allowed in official macro tests.")

    monkeypatch.setattr(socket, "create_connection", _raise_on_network)
