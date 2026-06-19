from __future__ import annotations

from data_providers.source_registry import (
    EXCLUDED_SOURCE_REGISTRY,
    PROVIDER_REGISTRY,
    audit_source_registry,
    source_audit_metadata,
    validate_source_assignment,
)


def test_registry_has_required_providers_and_passes_audit():
    assert {
        "fred",
        "bls",
        "bea",
        "alpha_vantage",
        "ofr",
    } <= set(PROVIDER_REGISTRY)
    assert audit_source_registry() == []


def test_high_risk_provider_boundaries_are_encoded():
    assert validate_source_assignment("alpha_vantage", "official") == [
        "provider_badge_not_allowed:alpha_vantage:official"
    ]
    assert "ofr_trigger_must_be_reference_only" in validate_source_assignment(
        "ofr", "official_reference", "eligible"
    )


def test_source_audit_metadata_contains_required_fields():
    metadata = source_audit_metadata(
        "fred",
        source_series="DGS10",
        retrieval_method="api",
        freshness_policy="business_daily",
        ingested_at="2026-06-19T00:00:00+00:00",
    )
    assert {
        "provider",
        "source",
        "source_badge",
        "source_series",
        "retrieval_method",
        "freshness_policy",
        "ai_context_allowed",
        "trigger_eligibility",
        "interpretation_boundary",
        "ingested_at",
    } <= set(metadata)


def test_multi_badge_providers_have_deterministic_defaults():
    assert PROVIDER_REGISTRY["alpha_vantage"].default_source_badge == (
        "commercial_api_fallback"
    )
    assert PROVIDER_REGISTRY["ofr"].default_source_badge == "official_reference"


def test_paid_and_out_of_scope_sources_remain_excluded():
    assert EXCLUDED_SOURCE_REGISTRY["cboe_paid_history"]["source_badge"] == (
        "commercial_licensed_required"
    )
    assert EXCLUDED_SOURCE_REGISTRY["sec_edgar_advanced"]["source_badge"] == (
        "not_available"
    )
