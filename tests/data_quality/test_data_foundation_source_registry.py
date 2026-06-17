from __future__ import annotations

import audit_data_foundation_gaps as g0
from data_quality import official_macro_pack


CONFIG = g0.load_data_sources()


def test_ppi_final_demand_is_official_ppifis_not_research_needed():
    assert CONFIG["fred_series"]["ppi_final_demand"]["series_id"] == "PPIFIS"
    assert (
        CONFIG["deepseek_market_data_package"]["inflation_indicators"]["ppi_final_demand"][
            "series_id"
        ]
        == "PPIFIS"
    )
    data_quality = CONFIG["data_quality"]["ppi_final_demand"]

    assert data_quality["source_tier"] == "official_or_public_data_api"
    assert data_quality["source_tier"] != "research_needed"
    assert "PPIACO" in data_quality["definition_note"]
    assert "YoY" in data_quality["definition_note"]


def test_ppiaco_and_ppifis_boundaries_are_separate():
    assert CONFIG["fred_series"]["ppi_all_commodities"]["series_id"] == "PPIACO"
    assert CONFIG["fred_series"]["ppi_final_demand"]["series_id"] == "PPIFIS"
    assert (
        CONFIG["deepseek_market_data_package"]["inflation_indicators"][
            "ppi_all_commodities"
        ]["series_id"]
        == "PPIACO"
    )
    assert (
        CONFIG["deepseek_market_data_package"]["inflation_indicators"][
            "ppi_final_demand"
        ]["series_id"]
        == "PPIFIS"
    )

    ppiaco = official_macro_pack.OFFICIAL_MACRO_METRICS["ppiaco_yoy"]
    final_demand = official_macro_pack.OFFICIAL_MACRO_METRICS["ppi_final_demand"]

    assert ppiaco.source_series == "PPIACO"
    assert final_demand.source_series == "PPIFIS"
    assert "do not use PPIACO" in final_demand.missing_reason


def test_ppi_final_demand_yoy_remains_history_gated():
    yoy = official_macro_pack.OFFICIAL_MACRO_METRICS["ppi_final_demand_yoy"]

    assert yoy.source_series == "PPIFIS"
    assert yoy.status_when_missing == "insufficient_history"
    assert "requires at least 13" in yoy.missing_reason
    assert "do not use index level as YoY" in yoy.missing_reason


def test_valuation_and_fedwatch_remain_out_of_factual_layer():
    financial = CONFIG["financial_conditions"]
    unavailable = CONFIG["deepseek_market_data_package"]["unavailable_or_research_needed"]

    for key in ("valuation_proxy", "fedwatch_probability"):
        assert financial[key]["provider"] == "not_available"
        assert financial[key]["source_tier"] == "not_available"
        assert financial[key]["unavailable_reason"]
        assert unavailable[key]["status"] == "not_available"
        assert unavailable[key]["unavailable_reason"]


def test_baa_reference_series_are_not_hy_or_ig_oas_aliases():
    financial = CONFIG["financial_conditions"]

    assert financial["high_yield_spread"]["series_id"] == "BAMLH0A0HYM2"
    assert financial["investment_grade_spread"]["series_id"] == "BAMLC0A0CM"
    assert financial["high_yield_spread"]["series_id"] not in g0.REFERENCE_ONLY_SERIES
    assert (
        financial["investment_grade_spread"]["series_id"]
        not in g0.REFERENCE_ONLY_SERIES
    )


def test_data_foundation_gap_audit_passes_and_reports_gated_items():
    findings = g0.audit_data_sources(CONFIG)
    payload = g0.findings_to_payload(findings)
    by_category = {
        category: [item.item for item in findings if item.category == category]
        for category in {item.category for item in findings}
    }

    assert payload["status"] == "PASS"
    assert payload["error_count"] == 0
    assert "ofr_fsi" in by_category["research_needed_items"]
    assert {"valuation_proxy", "fedwatch_probability"}.issubset(
        set(by_category["not_available_items"])
    )
    assert "ppi_final_demand" in by_category["official_mapping_candidates"]
