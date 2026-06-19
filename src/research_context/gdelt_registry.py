from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .gdelt_schema import (
    INTERPRETATION_BOUNDARY,
    PROVIDER,
    SOURCE_BADGE,
    TRIGGER_ELIGIBILITY,
)


@dataclass(frozen=True)
class GdeltQueryPreset:
    query_key: str
    endpoint: str
    group_by: str
    params: dict[str, Any]


QUERY_PRESETS: dict[str, GdeltQueryPreset] = {
    "middle_east_energy_risk": GdeltQueryPreset(
        query_key="middle_east_energy_risk",
        endpoint="events",
        group_by="category",
        params={
            "region": "Middle East",
            "search": "oil shipping energy infrastructure",
            "sort": "recent",
        },
    ),
    "ukraine_energy_infrastructure": GdeltQueryPreset(
        query_key="ukraine_energy_infrastructure",
        endpoint="events",
        group_by="date",
        params={
            "country": "Ukraine",
            "search": "energy infrastructure",
            "sort": "recent",
        },
    ),
    "global_conflict_pressure": GdeltQueryPreset(
        query_key="global_conflict_pressure",
        endpoint="events",
        group_by="region",
        params={
            "category": "Battles,Explosions/Remote violence,Protests",
            "sort": "recent",
        },
    ),
    "taiwan_strait_political_risk": GdeltQueryPreset(
        query_key="taiwan_strait_political_risk",
        endpoint="events",
        group_by="category",
        params={
            "search": "Taiwan Strait",
            "category": "POLITICAL",
            "sort": "recent",
        },
    ),
    "energy_assets_global_summary": GdeltQueryPreset(
        query_key="energy_assets_global_summary",
        endpoint="energy/assets",
        group_by="country",
        params={},
    ),
}

GDELT_POLICY = {
    "provider": PROVIDER,
    "source_badge": SOURCE_BADGE,
    "trigger_eligibility": TRIGGER_ELIGIBILITY,
    "ai_context_allowed": False,
    "interpretation_boundary": INTERPRETATION_BOUNDARY,
    "raw_article_body_persistence_allowed": False,
    "included_facts_allowed": False,
    "allowed_context_collection": "included_research_context",
}

FORBIDDEN_TRIGGER_TARGETS = {
    "financial_stress_score",
    "systemic_risk_status",
    "macro_regime_label",
    "portfolio_action",
    "target_allocation",
    "trading_guidance",
    "probability_output",
}


def get_query_preset(query_key: str) -> GdeltQueryPreset:
    try:
        return QUERY_PRESETS[query_key]
    except KeyError as exc:
        raise ValueError(f"unknown_gdelt_query_preset:{query_key}") from exc


def audit_gdelt_registry() -> list[str]:
    errors = []
    if GDELT_POLICY["source_badge"] != "research_context":
        errors.append("gdelt_source_badge_invalid")
    if GDELT_POLICY["trigger_eligibility"] != "research_context_only":
        errors.append("gdelt_trigger_eligibility_invalid")
    if GDELT_POLICY["ai_context_allowed"]:
        errors.append("gdelt_ai_context_default_must_be_false")
    if GDELT_POLICY["included_facts_allowed"]:
        errors.append("gdelt_must_not_enter_included_facts")
    if GDELT_POLICY["raw_article_body_persistence_allowed"]:
        errors.append("gdelt_raw_article_body_persistence_forbidden")
    return errors
