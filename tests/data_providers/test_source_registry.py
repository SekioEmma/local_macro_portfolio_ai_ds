from __future__ import annotations

import pytest

from data_providers.provider_client_contract import validate_provider_response
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
        "eia",
        "ofr",
        "gdelt_cloud",
    } <= set(PROVIDER_REGISTRY)
    assert audit_source_registry() == []


def test_high_risk_provider_boundaries_are_encoded():
    assert validate_source_assignment("alpha_vantage", "official") == [
        "provider_badge_not_allowed:alpha_vantage:official"
    ]
    assert "gdelt_trigger_must_be_research_context_only" in validate_source_assignment(
        "gdelt_cloud", "research_context", "eligible"
    )
    assert "ofr_trigger_must_be_reference_only" in validate_source_assignment(
        "ofr", "official_reference", "eligible"
    )
    assert PROVIDER_REGISTRY["eia"].allowed_source_badges == frozenset(
        {"dataset_official"}
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


def test_paid_and_out_of_scope_sources_remain_excluded():
    assert EXCLUDED_SOURCE_REGISTRY["cboe_paid_history"]["source_badge"] == (
        "commercial_licensed_required"
    )
    assert EXCLUDED_SOURCE_REGISTRY["sec_edgar_advanced"]["source_badge"] == (
        "not_available"
    )


def test_provider_contract_rejects_raw_or_secret_fields():
    valid = {
        "status": "ok",
        "provider": "fred",
        "source_series": "DGS10",
        "data": [],
        "retrieved_at": "2026-06-19T00:00:00+00:00",
    }
    validate_provider_response(valid)
    with pytest.raises(ValueError, match="forbidden"):
        validate_provider_response({**valid, "api_key": "never"})
