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
    assert metrics["ppiaco_yoy"].source_series == "PPIACO"
    assert metrics["unemployment_rate"].source_series == "UNRATE"
    assert metrics["initial_jobless_claims"].source_series == "ICSA"
    assert metrics["nonfarm_payrolls"].source_series == "PAYEMS"
    assert metrics["continuing_claims"].source_series == "CCSA"
    assert metrics["ppi_final_demand"].status_when_missing == "missing"
    assert metrics["ppi_final_demand"].source_series == "PPIFIS"
    assert metrics["ppi_final_demand_yoy"].status_when_missing == "insufficient_history"
    assert metrics["ppi_final_demand_yoy"].source_series == "PPIFIS"


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


def test_official_labor_compact_rows_surface_in_evidence_table(monkeypatch, tmp_path):
    _block_network(monkeypatch)
    _write_market(
        tmp_path,
        {
            "market_data_package": {
                "labor_indicators": {
                    "unemployment_rate": _metric(
                        4.0,
                        unit="percent",
                        source="FRED:UNRATE",
                        source_tier="official_or_public_data_api",
                    ),
                    "initial_jobless_claims": _metric(
                        230000,
                        unit="claims",
                        source="FRED:ICSA",
                        source_tier="official_or_public_data_api",
                    ),
                    "nonfarm_payrolls": _metric(
                        160000,
                        unit="thousand_persons",
                        source="FRED:PAYEMS",
                        source_tier="official_or_public_data_api",
                    ),
                    "continuing_claims": _metric(
                        1700000,
                        unit="claims",
                        source="FRED:CCSA",
                        source_tier="official_or_public_data_api",
                    ),
                }
            }
        },
    )
    monkeypatch.setattr(dashboard_service, "DEFAULT_REPORTS_DIR", tmp_path)

    data = TestClient(app).get("/api/dashboard/evidence-table").json()
    unemployment = _row(data, "labor_macro", "unemployment_rate")
    claims = _row(data, "labor_macro", "initial_jobless_claims")
    payrolls = _row(data, "labor_macro", "nonfarm_payrolls")
    continuing = _row(data, "labor_macro", "continuing_claims")

    assert unemployment["status"] == "ok"
    assert unemployment["value_text"] == "4.00%"
    assert unemployment["source_badge"] == "official"
    assert unemployment["ai_context_allowed"] is True
    assert claims["status"] == "ok"
    assert claims["value"] == 230000
    assert claims["value_text"] == "230,000"
    assert claims["source_badge"] == "official"
    assert claims["ai_context_allowed"] is True
    assert payrolls["status"] == "ok"
    assert payrolls["source_series"] == "PAYEMS"
    assert payrolls["source_badge"] == "official"
    assert continuing["status"] == "ok"
    assert continuing["value_text"] == "1,700,000"
    assert continuing["source_series"] == "CCSA"
    assert continuing["source_badge"] == "official"

    summary = TestClient(app).get("/api/dashboard/summary").json()
    assert "labor_macro" not in summary["modules"]


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
        ("labor_macro", "unemployment_rate"),
        ("labor_macro", "initial_jobless_claims"),
        ("labor_macro", "nonfarm_payrolls"),
        ("labor_macro", "continuing_claims"),
    ):
        row = _row(data, module, key)
        assert row["status"] == "missing"
        assert row["source"]
        assert row["source_badge"] == "missing"
        assert row["missing_reason"]
        assert row["interpretation_hint"]
        assert row["ai_context_allowed"] is False


def test_ppi_boundary_preserves_missing_final_demand(monkeypatch, tmp_path):
    _block_network(monkeypatch)
    _write_market(tmp_path, {"ppiaco_yoy": _metric(1.6)})
    monkeypatch.setattr(dashboard_service, "DEFAULT_REPORTS_DIR", tmp_path)

    data = TestClient(app).get("/api/dashboard/evidence-table").json()
    ppiaco = _row(data, "inflation_energy_pressure", "ppiaco_yoy")
    final_demand = _row(data, "inflation_energy_pressure", "ppi_final_demand")

    assert "not final demand PPI" in ppiaco["interpretation_hint"]
    assert final_demand["status"] == "missing"
    assert final_demand["source_badge"] == "missing"
    assert "do not use PPIACO as final demand" in final_demand["missing_reason"]
    assert final_demand["ai_context_allowed"] is False


def test_ppi_final_demand_official_metadata_allows_ai_context(monkeypatch, tmp_path):
    _block_network(monkeypatch)
    _write_market(
        tmp_path,
        {
            "market_data_package": {
                "inflation_indicators": {
                    "ppi_final_demand": _metric(
                        157.659,
                        unit="index",
                        source="FRED:PPIFIS",
                        source_tier="official_or_public_data_api",
                    ),
                    "ppi_final_demand_yoy_pct": _metric(
                        2.64,
                        unit="percent",
                        source="FRED:PPIFIS",
                        source_tier="official_or_public_data_api",
                    ),
                }
            }
        },
    )
    monkeypatch.setattr(dashboard_service, "DEFAULT_REPORTS_DIR", tmp_path)

    data = TestClient(app).get("/api/dashboard/evidence-table").json()
    index_row = _row(data, "inflation_energy_pressure", "ppi_final_demand")
    yoy_row = _row(data, "inflation_energy_pressure", "ppi_final_demand_yoy")

    assert index_row["status"] == "ok"
    assert index_row["source"] == "FRED:PPIFIS"
    assert index_row["source_badge"] == "official"
    assert index_row["observation_date"] == "2026-01-01"
    assert index_row["generated_at"] == "2026-01-01T00:00:00+00:00"
    assert index_row["ai_context_allowed"] is True
    assert "PPIACO" in index_row["interpretation_hint"]
    assert "consensus" in index_row["interpretation_hint"]
    assert yoy_row["status"] == "ok"
    assert yoy_row["value_text"] == "+2.64%"
    assert yoy_row["source_badge"] == "official"
    assert yoy_row["ai_context_allowed"] is True


def test_ppi_final_demand_missing_metadata_blocks_ai_context(monkeypatch, tmp_path):
    _block_network(monkeypatch)
    _write_market(
        tmp_path,
        {
            "market_data_package": {
                "inflation_indicators": {
                    "ppi_final_demand": {
                        "value": 157.659,
                        "status": "ok",
                        "source": "FRED:PPIFIS",
                        "source_tier": "official_or_public_data_api",
                        "freshness_status": "fresh",
                    }
                }
            }
        },
    )
    monkeypatch.setattr(dashboard_service, "DEFAULT_REPORTS_DIR", tmp_path)

    data = TestClient(app).get("/api/dashboard/evidence-table").json()
    row = _row(data, "inflation_energy_pressure", "ppi_final_demand")

    assert row["status"] == "ok"
    assert row["source_badge"] == "official"
    assert row["observation_date"] is None
    assert row["ai_context_allowed"] is False
    assert row["blocked_reason"] == "observation_date_missing"


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


def test_ppi_final_demand_index_level_is_not_displayed_as_yoy(monkeypatch, tmp_path):
    _block_network(monkeypatch)
    _write_market(
        tmp_path,
        {
            "ppi_final_demand_yoy": _metric(157.659, unit="index", source="FRED:PPIFIS"),
        },
    )
    monkeypatch.setattr(dashboard_service, "DEFAULT_REPORTS_DIR", tmp_path)

    data = TestClient(app).get("/api/dashboard/evidence-table").json()
    row = _row(data, "inflation_energy_pressure", "ppi_final_demand_yoy")

    assert row["status"] == "insufficient_history"
    assert row["value"] is None
    assert row["source_badge"] == "missing"
    assert row["ai_context_allowed"] is False
    assert "+157.66%" not in json.dumps(data)


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


def test_official_macro_yoy_aliases_surface_existing_compact_fields(monkeypatch, tmp_path):
    _block_network(monkeypatch)
    _write_market(
        tmp_path,
        {
            "market_data_package": {
                "inflation_indicators": {
                    "core_cpi_yoy_pct": _metric(
                        2.74,
                        unit="percent",
                        source="FRED:CPILFESL",
                        source_tier="official_or_public_data_api",
                    ),
                    "core_pce_yoy_pct": _metric(
                        3.29,
                        unit="percent",
                        source="FRED:PCEPILFE",
                        source_tier="official_or_public_data_api",
                    ),
                    "ppi_all_commodities_yoy_pct": _metric(
                        9.82,
                        unit="percent",
                        source="FRED:PPIACO",
                        source_tier="official_or_public_data_api",
                    ),
                }
            }
        },
    )
    monkeypatch.setattr(dashboard_service, "DEFAULT_REPORTS_DIR", tmp_path)

    data = TestClient(app).get("/api/dashboard/evidence-table").json()

    for key, expected in (
        ("core_cpi_yoy", "+2.74%"),
        ("core_pce_yoy", "+3.29%"),
        ("ppiaco_yoy", "+9.82%"),
    ):
        row = _row(data, "inflation_energy_pressure", key)
        assert row["status"] == "ok"
        assert row["value_text"] == expected
        assert row["source_badge"] == "official"
        assert row["ai_context_allowed"] is True

    assert "not final demand PPI" in _row(
        data,
        "inflation_energy_pressure",
        "ppiaco_yoy",
    )["interpretation_hint"]
    final_demand = _row(data, "inflation_energy_pressure", "ppi_final_demand")
    assert final_demand["status"] == "missing"
    assert final_demand["ai_context_allowed"] is False


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
    assert "above expectations" not in lower_body
    assert "below expectations" not in lower_body


def _metric(value, *, unit=None, source=None, source_tier=None):
    return {
        "value": value,
        "status": "ok",
        "observation_date": "2026-01-01",
        "freshness_status": "fresh",
        **({"unit": unit} if unit else {}),
        **({"source": source} if source else {}),
        **({"source_tier": source_tier} if source_tier else {}),
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
