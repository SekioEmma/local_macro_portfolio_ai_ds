from __future__ import annotations

import audit_data_foundation_gaps as g0
from data_quality import liquidity_funding_stress as d14


EXPECTED_D14_MAPPINGS = {
    "sofr": ("SOFR", "official"),
    "effr": ("EFFR", "official"),
    "iorb": ("IORB", "official"),
    "on_rrp": ("RRPONTSYD", "official"),
    "commercial_paper_rate": ("DCPF3M", "official_fallback"),
    "stl_fsi": ("STLFSI4", "official_fallback"),
    "nfci": ("NFCI", "official_fallback"),
    "anfci": ("ANFCI", "official_fallback"),
}
REQUIRED_FIELDS = (
    "source",
    "source_badge",
    "source_series",
    "provider",
    "unit",
    "expected_frequency",
    "interpretation_hint",
    "ai_context_allowed_rule",
)


def test_d14_official_source_registry_is_complete():
    config = d14.load_liquidity_funding_config()

    for key, (series, badge) in EXPECTED_D14_MAPPINGS.items():
        item = config[key]
        assert item["provider"] == "fred"
        assert item["source"] == "FRED"
        assert item["source_series"] == series
        assert item["source_badge"] == badge
        assert item["ai_context_allowed_rule"] == "allowed_when_ok_with_complete_metadata"
        for field in REQUIRED_FIELDS:
            assert item[field] not in (None, "")


def test_d14_ofr_fsi_remains_source_gated_research_needed():
    ofr = d14.load_liquidity_funding_config()["ofr_fsi"]

    assert ofr["status"] == "research_needed"
    assert ofr["source_badge"] == "research_needed"
    assert ofr["provider"] == "research_needed"
    assert ofr["source"] is None
    assert ofr["source_series"] is None
    assert ofr["missing_reason"] == "source_mapping_required"
    assert ofr["ai_context_allowed_rule"] == "never_until_source_mapping_verified"


def test_d14_source_badges_are_policy_allowed():
    config = d14.load_liquidity_funding_config()

    assert {
        item["source_badge"] for item in config.values()
    }.issubset(g0.ALLOWED_SOURCE_BADGES)


def test_planned_source_mappings_expose_only_verified_series():
    planned, missing = d14.planned_source_mappings()

    assert set(planned) == set(EXPECTED_D14_MAPPINGS)
    assert missing == ["ofr_fsi"]
    for key, (series, badge) in EXPECTED_D14_MAPPINGS.items():
        assert planned[key]["provider"] == "fred"
        assert planned[key]["source"] == "FRED"
        assert planned[key]["source_series"] == series
        assert planned[key]["source_badge"] == badge


def test_data_foundation_audit_reports_d14_registry_without_errors():
    config = g0.load_data_sources()
    findings = g0.audit_data_sources(config)
    official = {
        item.item
        for item in findings
        if item.category == "official_mapping_candidates"
    }
    research_needed = {
        item.item for item in findings if item.category == "research_needed_items"
    }

    assert g0.findings_to_payload(findings)["status"] == "PASS"
    assert set(EXPECTED_D14_MAPPINGS).issubset(official)
    assert "ofr_fsi" in research_needed
