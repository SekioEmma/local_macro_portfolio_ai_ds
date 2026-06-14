from pathlib import Path

from modeling.model_registry import ModelRegistry


FRONTEND_SRC = Path("app_frontend/src")


def test_frontend_registry_preserves_required_labels_and_boundaries():
    module_registry = (FRONTEND_SRC / "utils/moduleRegistry.ts").read_text(encoding="utf-8")
    metric_registry = (FRONTEND_SRC / "utils/metricRegistry.ts").read_text(encoding="utf-8")

    assert 'financial_stress_composite: "Financial stress composite"' in module_registry
    assert (
        'pullback_systemic_risk_checklist: "Pullback/systemic risk checklist"'
        in module_registry
    )
    assert 'historical_risk_percentile: "Historical risk percentile"' in module_registry
    assert 'liquidity_funding_stress: "Liquidity/funding stress"' in module_registry
    assert 'macro_regime_review: "Macro regime review"' in module_registry
    assert 'scenario_stress: "Scenario stress"' in module_registry
    assert 'historical_validation: "Historical validation"' in module_registry
    for module_key in ModelRegistry().model_output_module_keys():
        assert f"{module_key}:" in module_registry

    assert 'financial_stress_score: "Financial stress score"' in metric_registry
    assert 'pullback_classification: "Pullback classification"' in metric_registry
    assert 'high_yield_spread_percentile: "High-yield spread percentile"' in metric_registry
    assert (
        'liquidity_funding_stress_status: "Liquidity/funding stress status"'
        in metric_registry
    )
    assert 'macro_regime_label: "Macro regime label"' in metric_registry
    assert 'primary_pressure_ranking: "Primary pressure ranking"' in metric_registry
    assert (
        'historical_validation_status: "Historical validation status"'
        in metric_registry
    )
    assert 'scenario_stress_status: "Scenario stress status"' in metric_registry

    assert "event-odds model" in module_registry
    assert "allocation directive" in module_registry
    assert "not a forecast" in module_registry
    assert "scenario matrix" in module_registry
    assert "reference evidence" in module_registry
    assert "current evidence review" in module_registry
    assert "historical replay" in module_registry


def test_display_label_helpers_keep_unknown_fallbacks():
    display_labels = (FRONTEND_SRC / "utils/displayLabels.ts").read_text(encoding="utf-8")
    module_registry = (FRONTEND_SRC / "utils/moduleRegistry.ts").read_text(encoding="utf-8")

    assert "return moduleLabels[moduleKey] || moduleKey;" in display_labels
    assert "return metricLabels[metricKey] || metricKey;" in display_labels
    assert "return statusLabels[status] || status;" in display_labels
    assert "return sourceBadgeLabels[sourceBadge] || sourceBadge;" in display_labels
    assert "return interpretationBoundaries[moduleKey] ||" in module_registry


def test_module_detail_drawer_uses_registry_boundary():
    drawer = (FRONTEND_SRC / "components/ModuleDetailDrawer.tsx").read_text(
        encoding="utf-8"
    )

    assert 'import { getModuleBoundary } from "../utils/moduleRegistry";' in drawer
    assert "<InterpretationBoundary moduleKey={moduleKey} />" in drawer
    assert "const interpretationBoundaries" not in drawer


def test_frontend_files_do_not_contain_raw_provider_or_holdings_payload_logic():
    forbidden = ("raw_provider", "raw_holdings")
    offenders: list[str] = []
    for path in FRONTEND_SRC.rglob("*"):
        if path.suffix not in {".ts", ".tsx"}:
            continue
        text = path.read_text(encoding="utf-8")
        for token in forbidden:
            if token in text:
                offenders.append(f"{path}:{token}")

    assert offenders == []
