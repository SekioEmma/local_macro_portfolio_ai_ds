from __future__ import annotations

from dataclasses import dataclass
from typing import Any


SOURCE_CLASSES = {
    "official",
    "official_fallback",
    "official_reference",
    "dataset_official",
    "commercial_api_fallback",
    "proxy",
    "scraped_official_reference",
    "research_context",
    "commercial_licensed_required",
    "not_available",
}

TRIGGER_ELIGIBILITY = {
    "eligible",
    "support_only",
    "reference_only",
    "research_context_only",
    "ineligible",
}


@dataclass(frozen=True)
class ProviderSpec:
    provider_key: str
    display_name: str
    requires_api_key: bool
    supports_history: bool
    supports_latest: bool
    allowed_source_badges: frozenset[str]
    default_ai_context_allowed: bool
    default_trigger_eligibility: str
    license_usage_notes: str
    raw_payload_persistence_allowed: bool = False
    interpretation_boundary: str = ""


PROVIDER_REGISTRY: dict[str, ProviderSpec] = {
    "fred": ProviderSpec(
        provider_key="fred",
        display_name="Federal Reserve Economic Data",
        requires_api_key=True,
        supports_history=True,
        supports_latest=True,
        allowed_source_badges=frozenset({"official_fallback"}),
        default_ai_context_allowed=True,
        default_trigger_eligibility="eligible",
        license_usage_notes="Public Federal Reserve Bank of St. Louis API; retain series identifiers.",
        interpretation_boundary="FRED mirrors official series and is fallback when a first-party agency feed succeeds.",
    ),
    "bls": ProviderSpec(
        provider_key="bls",
        display_name="U.S. Bureau of Labor Statistics",
        requires_api_key=False,
        supports_history=True,
        supports_latest=True,
        allowed_source_badges=frozenset({"official"}),
        default_ai_context_allowed=True,
        default_trigger_eligibility="eligible",
        license_usage_notes="First-party public BLS API data.",
    ),
    "bea": ProviderSpec(
        provider_key="bea",
        display_name="U.S. Bureau of Economic Analysis",
        requires_api_key=True,
        supports_history=True,
        supports_latest=True,
        allowed_source_badges=frozenset({"official"}),
        default_ai_context_allowed=True,
        default_trigger_eligibility="eligible",
        license_usage_notes="First-party BEA API data; table and line metadata must be validated.",
    ),
    "alpha_vantage": ProviderSpec(
        provider_key="alpha_vantage",
        display_name="Alpha Vantage",
        requires_api_key=True,
        supports_history=True,
        supports_latest=True,
        allowed_source_badges=frozenset({"commercial_api_fallback", "proxy"}),
        default_ai_context_allowed=True,
        default_trigger_eligibility="support_only",
        license_usage_notes="Commercial API terms and rate limits apply; use only for fallback/proxy observations.",
        interpretation_boundary=(
            "Market proxies cannot replace true breadth, official macro series, HY OAS, or IG OAS."
        ),
    ),
    "eia": ProviderSpec(
        provider_key="eia",
        display_name="U.S. Energy Information Administration",
        requires_api_key=False,
        supports_history=True,
        supports_latest=True,
        allowed_source_badges=frozenset({"dataset_official"}),
        default_ai_context_allowed=True,
        default_trigger_eligibility="eligible",
        license_usage_notes="First-party controlled dataset files; preserve file hash and dataset identifier.",
        interpretation_boundary="Energy observations provide current/historical context, not price forecasts or trading signals.",
    ),
    "ofr": ProviderSpec(
        provider_key="ofr",
        display_name="Office of Financial Research",
        requires_api_key=False,
        supports_history=True,
        supports_latest=True,
        allowed_source_badges=frozenset(
            {"official_reference", "scraped_official_reference"}
        ),
        default_ai_context_allowed=True,
        default_trigger_eligibility="reference_only",
        license_usage_notes="Official OFR reference indicator downloaded from the OFR website.",
        interpretation_boundary=(
            "OFR FSI is reference evidence only and does not replace internal D10 or D11 models."
        ),
    ),
    "gdelt_cloud": ProviderSpec(
        provider_key="gdelt_cloud",
        display_name="GDELT Cloud",
        requires_api_key=True,
        supports_history=True,
        supports_latest=True,
        allowed_source_badges=frozenset({"research_context"}),
        default_ai_context_allowed=False,
        default_trigger_eligibility="research_context_only",
        license_usage_notes="Aggregate research context only; never persist full article bodies.",
        interpretation_boundary=(
            "News and event intensity is research context, not probability, financial fact, or market forecast."
        ),
    ),
}

EXCLUDED_SOURCE_REGISTRY: dict[str, dict[str, str]] = {
    "cboe_paid_history": {
        "source_badge": "commercial_licensed_required",
        "reason": "Paid historical volatility license is not configured.",
    },
    "factset_bloomberg_lseg": {
        "source_badge": "commercial_licensed_required",
        "reason": "Institutional consensus and constituent history require licensed feeds.",
    },
    "sec_edgar_advanced": {
        "source_badge": "not_available",
        "reason": "Advanced company-fundamental integration is outside this supplementation round.",
    },
}


def get_provider_spec(provider_key: str) -> ProviderSpec:
    try:
        return PROVIDER_REGISTRY[provider_key]
    except KeyError as exc:
        raise ValueError(f"unknown_provider:{provider_key}") from exc


def validate_source_assignment(
    provider_key: str,
    source_badge: str,
    trigger_eligibility: str | None = None,
) -> list[str]:
    errors: list[str] = []
    try:
        spec = get_provider_spec(provider_key)
    except ValueError as exc:
        return [str(exc)]
    if source_badge not in SOURCE_CLASSES:
        errors.append(f"unknown_source_badge:{source_badge}")
    if source_badge not in spec.allowed_source_badges:
        errors.append(f"provider_badge_not_allowed:{provider_key}:{source_badge}")
    eligibility = trigger_eligibility or spec.default_trigger_eligibility
    if eligibility not in TRIGGER_ELIGIBILITY:
        errors.append(f"unknown_trigger_eligibility:{eligibility}")
    if provider_key == "gdelt_cloud" and eligibility != "research_context_only":
        errors.append("gdelt_trigger_must_be_research_context_only")
    if provider_key == "ofr" and eligibility != "reference_only":
        errors.append("ofr_trigger_must_be_reference_only")
    if provider_key == "alpha_vantage" and eligibility != "support_only":
        errors.append("alpha_vantage_trigger_must_be_support_only")
    return errors


def audit_source_registry() -> list[str]:
    errors: list[str] = []
    required = {"fred", "bls", "bea", "alpha_vantage", "eia", "ofr", "gdelt_cloud"}
    missing = sorted(required - set(PROVIDER_REGISTRY))
    errors.extend(f"missing_provider:{key}" for key in missing)
    for key, spec in sorted(PROVIDER_REGISTRY.items()):
        if key != spec.provider_key:
            errors.append(f"provider_key_mismatch:{key}")
        if spec.raw_payload_persistence_allowed:
            errors.append(f"raw_payload_persistence_must_default_false:{key}")
        for badge in spec.allowed_source_badges:
            errors.extend(validate_source_assignment(key, badge))
    if "official" in PROVIDER_REGISTRY["alpha_vantage"].allowed_source_badges:
        errors.append("alpha_vantage_cannot_be_official")
    if "official" in PROVIDER_REGISTRY["gdelt_cloud"].allowed_source_badges:
        errors.append("gdelt_cannot_be_official")
    if PROVIDER_REGISTRY["eia"].allowed_source_badges != frozenset({"dataset_official"}):
        errors.append("eia_must_be_dataset_official")
    return sorted(set(errors))


def source_audit_metadata(
    provider_key: str,
    *,
    source_series: str,
    retrieval_method: str,
    freshness_policy: str,
    source_badge: str | None = None,
    trigger_eligibility: str | None = None,
    ai_context_allowed: bool | None = None,
    interpretation_boundary: str | None = None,
    ingested_at: str | None = None,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    spec = get_provider_spec(provider_key)
    badge = source_badge or next(iter(spec.allowed_source_badges))
    eligibility = trigger_eligibility or spec.default_trigger_eligibility
    errors = validate_source_assignment(provider_key, badge, eligibility)
    if errors:
        raise ValueError(";".join(errors))
    payload: dict[str, Any] = {
        "provider": provider_key,
        "source": spec.display_name,
        "source_badge": badge,
        "source_series": source_series,
        "retrieval_method": retrieval_method,
        "freshness_policy": freshness_policy,
        "ai_context_allowed": (
            spec.default_ai_context_allowed
            if ai_context_allowed is None
            else bool(ai_context_allowed)
        ),
        "trigger_eligibility": eligibility,
        "interpretation_boundary": (
            interpretation_boundary
            if interpretation_boundary is not None
            else spec.interpretation_boundary
        ),
        "ingested_at": ingested_at,
    }
    if extra:
        payload.update(extra)
    return payload
