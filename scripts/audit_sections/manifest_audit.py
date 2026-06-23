from __future__ import annotations

import json
from typing import Any

from app_backend.schemas.responses import DashboardEvidenceTableResponse
from app_backend.services import ai_context_service
from app_backend.services.dashboard_context import DashboardPipelineContext
from modeling.model_registry import ModelRegistry


MODEL_REGISTRY = ModelRegistry()
D10_D11_MODULES = {
    MODEL_REGISTRY.require("financial_stress_composite").module_key,
    MODEL_REGISTRY.require("pullback_systemic_risk_checklist").module_key,
}
D15_MODULE = MODEL_REGISTRY.require("macro_regime_review").module_key
D16_MODULE = MODEL_REGISTRY.require("scenario_stress").module_key

def _ai_context_manifest_audit(
    evidence: DashboardEvidenceTableResponse,
) -> dict[str, Any]:
    context = DashboardPipelineContext(evidence_table=evidence)
    manifest = ai_context_service.build_ai_context_manifest(context=context)
    source_summary = manifest.source_summary
    return {
        "manifest_available": True,
        "included_facts_count": source_summary.get("included_facts_count", 0),
        "excluded_facts_count": source_summary.get("excluded_facts_count", 0),
        "included_model_outputs_count": source_summary.get(
            "included_model_outputs_count", 0
        ),
        "excluded_model_outputs_count": source_summary.get(
            "excluded_model_outputs_count", 0
        ),
        "included_model_output_keys": sorted(
            row.get("metric_key") for row in manifest.included_model_outputs
        ),
        "portfolio_context_mode": manifest.portfolio_context_policy.get("mode"),
        "search_derived_default": manifest.search_policy.get("search_derived_default"),
        "returns_holdings_line_items": manifest.privacy_policy.get(
            "returns_holdings_line_items"
        ),
        "returns_provider_payloads": manifest.privacy_policy.get(
            "returns_provider_payloads"
        ),
        "returns_credentials": manifest.privacy_policy.get("returns_credentials"),
        "risk_boundary_count": len(manifest.risk_boundaries),
        "included_d13_fact_count": sum(
            1
            for row in manifest.included_facts
            if row.get("module") == "historical_risk_percentile"
        ),
        "included_d10_d11_model_outputs_with_percentile_context": sum(
            1
            for row in manifest.included_model_outputs
            if row.get("module") in D10_D11_MODULES
            and "percentile_context" in json.dumps(row.get("component_contributions", {}))
        ),
        "included_d10_d11_model_outputs_with_liquidity_context": sum(
            1
            for row in manifest.included_model_outputs
            if row.get("module") in D10_D11_MODULES
            and (
                "funding_liquidity" in json.dumps(row.get("component_contributions", {}))
                or "pullback_liquidity_funding_context"
                in json.dumps(row.get("component_contributions", {}))
            )
        ),
        "included_d15_model_output_count": sum(
            1
            for row in manifest.included_model_outputs
            if row.get("module") == D15_MODULE
        ),
        "excluded_d15_model_output_count": sum(
            1
            for row in manifest.excluded_model_outputs
            if row.get("module") == D15_MODULE
        ),
        "included_d16_model_output_count": sum(
            1
            for row in manifest.included_model_outputs
            if row.get("module") == D16_MODULE
        ),
        "excluded_d16_model_output_count": sum(
            1
            for row in manifest.excluded_model_outputs
            if row.get("module") == D16_MODULE
        ),
        "excluded_d13_insufficient_history_count": sum(
            1
            for row in manifest.excluded_facts
            if row.get("module") == "historical_risk_percentile"
            and row.get("status") == "insufficient_history"
        ),
        "included_d14_fact_count": sum(
            1
            for row in manifest.included_facts
            if row.get("module") == "liquidity_funding_stress"
        ),
        "excluded_d14_ineligible_count": sum(
            1
            for row in manifest.excluded_facts
            if row.get("module") == "liquidity_funding_stress"
        ),
        "included_d14_boundary_count": sum(
            1
            for row in manifest.included_facts
            if row.get("module") == "liquidity_funding_stress"
            and row.get("interpretation_boundary")
        ),
    }
