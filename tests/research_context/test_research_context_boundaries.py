from __future__ import annotations

import importlib.util
from pathlib import Path

from research_context.gdelt_registry import (
    FORBIDDEN_TRIGGER_TARGETS,
    GDELT_POLICY,
    QUERY_PRESETS,
    audit_gdelt_registry,
)


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "audit_research_context_boundaries.py"
SPEC = importlib.util.spec_from_file_location("audit_research_context_boundaries", SCRIPT)
assert SPEC and SPEC.loader
audit = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(audit)


def test_registry_boundary_policy():
    assert audit_gdelt_registry() == []
    assert GDELT_POLICY["included_facts_allowed"] is False
    assert GDELT_POLICY["allowed_context_collection"] == "included_research_context"
    assert {
        "financial_stress_score",
        "systemic_risk_status",
        "macro_regime_label",
        "portfolio_action",
        "probability_output",
    } <= FORBIDDEN_TRIGGER_TARGETS


def test_required_presets_are_configured():
    assert {
        "middle_east_energy_risk",
        "ukraine_energy_infrastructure",
        "global_conflict_pressure",
        "taiwan_strait_political_risk",
        "energy_assets_global_summary",
    } <= set(QUERY_PRESETS)


def test_core_models_do_not_import_research_context():
    assert audit.audit_core_import_boundaries() == []
