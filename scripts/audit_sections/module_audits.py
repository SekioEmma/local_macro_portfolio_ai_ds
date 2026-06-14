from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app_backend.schemas.responses import DashboardEvidenceRow
from modeling.model_registry import get_model_registry

from .common import (
    BAD_FRESHNESS,
    CONCENTRATION_PROXY_METRIC_KEYS,
    CREDIT_PROXY_METRIC_KEYS,
    CROSS_ASSET_PROXY_METRIC_KEYS,
    CURVE_SLOPE_METRIC_KEYS,
    DRAWDOWN_METRIC_KEYS,
    FINANCIAL_STRESS_COMPOSITE_METRIC_KEYS,
    HISTORICAL_RISK_PERCENTILE_METRIC_KEYS,
    LIQUIDITY_FUNDING_DERIVED_METRIC_KEYS,
    LIQUIDITY_FUNDING_METRIC_KEYS,
    LIQUIDITY_FUNDING_RAW_METRIC_KEYS,
    MARKET_STRESS_DERIVED_METRIC_KEYS,
    PROJECT_ROOT,
    PROXY_BREADTH_METRIC_KEYS,
    PULLBACK_SYSTEMIC_CHECKLIST_METRIC_KEYS,
    _has_value,
    _row_payload,
    _row_has_ok_value,
    _row_status,
    _source_missing,
)

VALUATION_BLOCKED_METRIC_KEYS = (
    "sp500_trailing_pe",
    "sp500_forward_pe",
    "cape_shiller_pe",
    "earnings_yield",
    "equity_risk_premium_proxy",
    "nasdaq100_valuation_proxy",
    "earnings_revision",
    "eps_growth",
    "sp500_top10_weight",
)
MODEL_REGISTRY = get_model_registry()
MACRO_REGIME_REVIEW_METRIC_KEYS = set(
    MODEL_REGISTRY.public_output_keys("macro_regime_review")
)
HISTORICAL_VALIDATION_METRIC_KEYS = set(
    MODEL_REGISTRY.public_output_keys("historical_validation")
)
SCENARIO_STRESS_METRIC_KEYS = set(
    MODEL_REGISTRY.public_output_keys("scenario_stress")
)
GROWTH_INFLATION_MACRO_PACK_METRIC_KEYS = set(
    MODEL_REGISTRY.public_output_keys("growth_inflation_macro_pack")
)


def _proxy_breadth_audit(rows: list[DashboardEvidenceRow]) -> dict[str, Any]:
    proxy_rows = [row for row in rows if row.metric_key in PROXY_BREADTH_METRIC_KEYS]
    ok_rows = [row for row in proxy_rows if row.status == "ok" and _has_value(row)]
    insufficient_rows = [row for row in proxy_rows if row.status == "insufficient_history"]
    return {
        "breadth_proxy_available": any(
            row.metric_key in {"spy_vs_rsp_30d", "spy_vs_rsp_60d"}
            for row in ok_rows
        ),
        "breadth_proxy_metric_count": len(proxy_rows),
        "breadth_proxy_ok_count": len(ok_rows),
        "breadth_proxy_insufficient_history_count": len(insufficient_rows),
        "concentration_proxy_available": any(
            row.metric_key in CONCENTRATION_PROXY_METRIC_KEYS for row in ok_rows
        ),
        "credit_proxy_available": any(
            row.metric_key in CREDIT_PROXY_METRIC_KEYS for row in ok_rows
        ),
        "proxy_metrics_ai_context_allowed_count": sum(
            1 for row in proxy_rows if row.ai_context_allowed
        ),
        "proxy_metric_keys": sorted(row.metric_key for row in proxy_rows),
        "proxy_insufficient_history_metric_keys": sorted(
            row.metric_key for row in insufficient_rows
        ),
    }

def _market_stress_derived_audit(rows: list[DashboardEvidenceRow]) -> dict[str, Any]:
    stress_rows = [row for row in rows if row.metric_key in MARKET_STRESS_DERIVED_METRIC_KEYS]
    ok_rows = [row for row in stress_rows if row.status == "ok" and _has_value(row)]
    insufficient_rows = [row for row in stress_rows if row.status == "insufficient_history"]
    return {
        "market_stress_derived_available": bool(ok_rows),
        "market_stress_derived_metric_count": len(stress_rows),
        "market_stress_derived_ok_count": len(ok_rows),
        "market_stress_derived_insufficient_history_count": len(insufficient_rows),
        "drawdown_available": any(row.metric_key in DRAWDOWN_METRIC_KEYS for row in ok_rows),
        "curve_slope_available": any(row.metric_key in CURVE_SLOPE_METRIC_KEYS for row in ok_rows),
        "cross_asset_proxy_available": any(
            row.metric_key in CROSS_ASSET_PROXY_METRIC_KEYS for row in ok_rows
        ),
        "market_stress_ai_context_allowed_count": sum(
            1 for row in stress_rows if row.ai_context_allowed
        ),
        "market_stress_metric_keys": sorted(row.metric_key for row in stress_rows),
        "market_stress_insufficient_history_metric_keys": sorted(
            row.metric_key for row in insufficient_rows
        ),
    }

def _financial_stress_composite_audit(rows: list[DashboardEvidenceRow]) -> dict[str, Any]:
    stress_rows = [
        row for row in rows if row.metric_key in FINANCIAL_STRESS_COMPOSITE_METRIC_KEYS
    ]
    row_by_key = {row.metric_key: row for row in stress_rows}
    score = row_by_key.get("financial_stress_score")
    status = row_by_key.get("financial_stress_status")
    dominant = row_by_key.get("financial_stress_dominant_pressure_source")
    missing = row_by_key.get("financial_stress_missing_inputs")
    contributions = (
        getattr(score, "component_contributions", None)
        if score is not None
        else None
    )
    contribution_groups = (
        sorted(contributions.keys()) if isinstance(contributions, dict) else []
    )
    percentile_context = (
        contributions.get("percentile_context", {})
        if isinstance(contributions, dict)
        else {}
    )
    funding_liquidity = (
        contributions.get("funding_liquidity", {})
        if isinstance(contributions, dict)
        else {}
    )
    by_group = (
        percentile_context.get("by_group", {})
        if isinstance(percentile_context, dict)
        else {}
    )
    return {
        "financial_stress_composite_available": bool(score and _has_value(score)),
        "financial_stress_metric_count": len(stress_rows),
        "financial_stress_score": score.value if score is not None else None,
        "financial_stress_score_status": score.status if score is not None else "missing",
        "financial_stress_status": status.value if status is not None else "missing",
        "financial_stress_dominant_pressure_source": (
            dominant.value if dominant is not None else None
        ),
        "financial_stress_missing_inputs": missing.value if missing is not None else None,
        "financial_stress_contribution_groups": contribution_groups,
        "financial_stress_ai_context_allowed": bool(
            score is not None and score.ai_context_allowed
        ),
        "financial_stress_source_badge": score.source_badge if score is not None else "missing",
        "financial_stress_has_interpretation_boundary": bool(
            score is not None and getattr(score, "interpretation_boundary", None)
        ),
        "percentile_context_available": bool(
            isinstance(percentile_context, dict)
            and percentile_context.get("available_count", 0) > 0
        ),
        "percentile_context_metric_count": (
            percentile_context.get("available_count", 0)
            if isinstance(percentile_context, dict)
            else 0
        ),
        "credit_percentile_context_available": _group_context_available(by_group, "credit"),
        "rates_percentile_context_available": _group_context_available(by_group, "rates"),
        "equity_percentile_context_available": _group_context_available(by_group, "equity"),
        "labor_percentile_context_available": _group_context_available(by_group, "labor"),
        "percentile_context_missing_metric_keys": (
            [item.get("metric_key") for item in percentile_context.get("missing", [])]
            if isinstance(percentile_context, dict)
            else []
        ),
        "funding_liquidity_context_available": bool(
            isinstance(funding_liquidity, dict)
            and funding_liquidity.get("available_count", 0) > 0
        ),
        "funding_liquidity_context_metric_count": (
            funding_liquidity.get("available_count", 0)
            if isinstance(funding_liquidity, dict)
            else 0
        ),
        "funding_liquidity_component_status": (
            funding_liquidity.get("component_status")
            if isinstance(funding_liquidity, dict)
            else "missing"
        ),
        "funding_liquidity_contribution": (
            funding_liquidity.get("contribution", 0)
            if isinstance(funding_liquidity, dict)
            else 0
        ),
        "d14_used_as_confirmation_only": bool(
            isinstance(funding_liquidity, dict)
            and funding_liquidity.get("d14_used_as_confirmation_only")
        ),
        "official_reference_not_replacing_d10": bool(
            isinstance(funding_liquidity, dict)
            and funding_liquidity.get("official_reference_not_replacing_d10")
        ),
    }

def _pullback_systemic_checklist_audit(rows: list[DashboardEvidenceRow]) -> dict[str, Any]:
    checklist_rows = [
        row for row in rows if row.metric_key in PULLBACK_SYSTEMIC_CHECKLIST_METRIC_KEYS
    ]
    row_by_key = {row.metric_key: row for row in checklist_rows}
    classification = row_by_key.get("pullback_classification")
    missing = row_by_key.get("pullback_missing_critical_inputs")
    items = row_by_key.get("pullback_checklist_items")
    contributions = (
        getattr(items, "component_contributions", None) if items is not None else None
    )
    checklist_items = (
        contributions.get("checklist_items", [])
        if isinstance(contributions, dict)
        else []
    )
    percentile_context = (
        contributions.get("pullback_percentile_context", {})
        if isinstance(contributions, dict)
        else {}
    )
    liquidity_context = (
        contributions.get("pullback_liquidity_funding_context", {})
        if isinstance(contributions, dict)
        else {}
    )
    return {
        "pullback_systemic_risk_checklist_available": bool(
            classification and _has_value(classification)
        ),
        "pullback_metric_count": len(checklist_rows),
        "pullback_classification": (
            classification.value if classification is not None else "missing"
        ),
        "pullback_classification_status": (
            classification.status if classification is not None else "missing"
        ),
        "pullback_missing_critical_inputs": (
            missing.value if missing is not None else None
        ),
        "pullback_checklist_item_count": len(checklist_items),
        "pullback_ai_context_allowed": bool(
            classification is not None and classification.ai_context_allowed
        ),
        "pullback_source_badge": (
            classification.source_badge if classification is not None else "missing"
        ),
        "pullback_has_interpretation_boundary": bool(
            classification is not None and getattr(classification, "interpretation_boundary", None)
        ),
        "pullback_percentile_context_available": bool(
            isinstance(percentile_context, dict)
            and percentile_context.get("available_count", 0) > 0
        ),
        "pullback_percentile_context_metric_count": (
            percentile_context.get("available_count", 0)
            if isinstance(percentile_context, dict)
            else 0
        ),
        "credit_percentile_used_as_auxiliary": bool(
            isinstance(percentile_context, dict)
            and percentile_context.get("credit_percentile_used_as_auxiliary")
        ),
        "systemic_not_triggered_by_percentile_only": bool(
            isinstance(percentile_context, dict)
            and percentile_context.get("systemic_not_triggered_by_percentile_only")
        ),
        "liquidity_still_missing_until_d14": bool(
            isinstance(percentile_context, dict)
            and percentile_context.get("liquidity_still_missing_until_d14")
            and missing is not None
            and "liquidity" in str(missing.value)
        ),
        "pullback_liquidity_funding_context_available": bool(
            isinstance(liquidity_context, dict)
            and liquidity_context.get("available_count", 0) > 0
        ),
        "pullback_liquidity_funding_metric_count": (
            liquidity_context.get("available_count", 0)
            if isinstance(liquidity_context, dict)
            else 0
        ),
        "liquidity_missing_critical_input_removed_when_available": bool(
            isinstance(liquidity_context, dict)
            and liquidity_context.get("liquidity_available")
            and missing is not None
            and "liquidity" not in str(missing.value)
        ),
        "liquidity_still_missing_when_d14_insufficient": bool(
            isinstance(liquidity_context, dict)
            and liquidity_context.get("liquidity_still_missing_when_d14_insufficient")
        ),
        "systemic_requires_credit_and_funding_and_transmission": bool(
            isinstance(liquidity_context, dict)
            and liquidity_context.get("systemic_requires_credit_and_funding_and_transmission")
        ),
        "d14_alone_not_systemic_trigger": bool(
            isinstance(liquidity_context, dict)
            and liquidity_context.get("d14_alone_not_systemic_trigger")
        ),
    }

def _group_context_available(by_group: dict[str, Any], group: str) -> bool:
    item = by_group.get(group) if isinstance(by_group, dict) else None
    return bool(isinstance(item, dict) and item.get("available_count", 0) > 0)

def _liquidity_funding_stress_audit(rows: list[DashboardEvidenceRow]) -> dict[str, Any]:
    lf_rows = [
        row
        for row in rows
        if row.module == "liquidity_funding_stress"
        or row.metric_key in LIQUIDITY_FUNDING_METRIC_KEYS
    ]
    by_key = {row.metric_key: row for row in lf_rows}
    status = by_key.get("liquidity_funding_stress_status")
    boundary = by_key.get("liquidity_funding_interpretation_boundary")
    missing_mappings = sorted(
        row.metric_key for row in lf_rows if row.status == "research_needed"
    )
    return {
        "liquidity_funding_available": bool(status and _has_value(status)),
        "raw_metric_count": sum(
            1 for row in lf_rows if row.metric_key in LIQUIDITY_FUNDING_RAW_METRIC_KEYS
        ),
        "derived_metric_count": sum(
            1 for row in lf_rows if row.metric_key in LIQUIDITY_FUNDING_DERIVED_METRIC_KEYS
        ),
        "ok_count": sum(1 for row in lf_rows if row.status == "ok"),
        "watch_count": sum(1 for row in lf_rows if row.status == "watch"),
        "pressure_count": sum(1 for row in lf_rows if row.status == "pressure"),
        "stress_count": sum(1 for row in lf_rows if row.status == "stress"),
        "research_needed_count": sum(
            1 for row in lf_rows if row.status == "research_needed"
        ),
        "insufficient_evidence_count": sum(
            1 for row in lf_rows if row.status == "insufficient_evidence"
        ),
        "ai_context_allowed_count": sum(1 for row in lf_rows if row.ai_context_allowed),
        "official_count": sum(1 for row in lf_rows if row.source_badge == "official"),
        "official_fallback_count": sum(
            1 for row in lf_rows if row.source_badge == "official_fallback"
        ),
        "derived_count": sum(1 for row in lf_rows if row.source_badge == "derived"),
        "missing_source_mappings": missing_mappings,
        "cp_spread_available": _row_has_ok_value(by_key.get("cp_effr_spread"))
        or _row_has_ok_value(by_key.get("cp_sofr_spread")),
        "policy_plumbing_available": _row_has_ok_value(
            by_key.get("policy_plumbing_status")
        ),
        "official_stress_reference_available": _row_has_ok_value(
            by_key.get("official_stress_reference_status")
        ),
        "liquidity_funding_status": status.value if status is not None else "missing",
        "liquidity_funding_boundary_available": bool(boundary and boundary.value),
        "d14_integration_ready": bool(
            status
            and _has_value(status)
            and status.status in {"ok", "watch", "pressure", "stress"}
        ),
        "d14_eligible_fact_count": sum(1 for row in lf_rows if row.ai_context_allowed),
        "d14_status_rows_available": all(
            _row_has_ok_value(by_key.get(key))
            for key in (
                "liquidity_funding_stress_status",
                "short_term_funding_pressure_status",
                "official_stress_reference_status",
                "policy_plumbing_status",
            )
        ),
        "d14_reference_indices_available": all(
            _row_has_ok_value(by_key.get(key)) for key in ("stl_fsi", "nfci", "anfci")
        ),
        "d14_cp_spread_available": _row_has_ok_value(by_key.get("cp_effr_spread"))
        or _row_has_ok_value(by_key.get("cp_sofr_spread")),
    }

def _macro_regime_review_audit(rows: list[DashboardEvidenceRow]) -> dict[str, Any]:
    regime_rows = [
        row
        for row in rows
        if row.module == "macro_regime_review"
        or row.metric_key in MACRO_REGIME_REVIEW_METRIC_KEYS
    ]
    by_key = {row.metric_key: row for row in regime_rows}
    serialized = json.dumps([_row_payload(row) for row in regime_rows], ensure_ascii=False).lower()
    label = by_key.get("macro_regime_label")
    boundary = by_key.get("interpretation_boundary")
    contributions = (
        getattr(label, "component_contributions", None)
        if label is not None
        else None
    )
    hard_gates = (
        contributions.get("hard_gates", {})
        if isinstance(contributions, dict)
        else {}
    )
    blocked_inputs = by_key.get("blocked_inputs")
    public_keys = {row.metric_key for row in regime_rows}
    return {
        "macro_regime_review_available": bool(label and _has_value(label)),
        "macro_regime_review_metric_count": len(regime_rows),
        "configured_public_output_count": len(MACRO_REGIME_REVIEW_METRIC_KEYS),
        "public_output_keys": sorted(public_keys),
        "missing_public_output_keys": sorted(MACRO_REGIME_REVIEW_METRIC_KEYS - public_keys),
        "macro_regime_label": label.value if label is not None else "missing",
        "macro_regime_label_status": label.status if label is not None else "missing",
        "support_band": by_key.get("support_band").value if by_key.get("support_band") else None,
        "evidence_quality_band": (
            by_key.get("evidence_quality_band").value
            if by_key.get("evidence_quality_band")
            else None
        ),
        "conflict_band": by_key.get("conflict_band").value if by_key.get("conflict_band") else None,
        "ai_context_allowed_count": sum(1 for row in regime_rows if row.ai_context_allowed),
        "public_outputs_expose_macro_regime_score": "macro_regime_score" in serialized,
        "public_outputs_expose_numeric_internal_scores": any(
            token in serialized
            for token in ("support_score_internal", "group_score_internal")
        ),
        "contains_crash_probability_language": "crash probability" in serialized,
        "contains_recession_probability_language": "recession probability" in serialized,
        "boundary_available": bool(boundary and boundary.value),
        "blocked_inputs_visible": bool(blocked_inputs and blocked_inputs.value is not None),
        "hard_gate_count": sum(1 for value in hard_gates.values() if value is True),
        "hard_gates": hard_gates,
        "blocked_or_insufficient_inputs_excluded_from_support": bool(
            hard_gates.get(
                "missing_stale_blocked_research_needed_insufficient_history_cannot_support_label"
            )
        ),
    }

def _historical_validation_audit(rows: list[DashboardEvidenceRow]) -> dict[str, Any]:
    validation_rows = [
        row
        for row in rows
        if row.module == "historical_validation"
        or row.metric_key in HISTORICAL_VALIDATION_METRIC_KEYS
    ]
    by_key = {row.metric_key: row for row in validation_rows}
    serialized = json.dumps([_row_payload(row) for row in validation_rows], ensure_ascii=False).lower()
    contributions = (
        getattr(by_key.get("historical_validation_status"), "component_contributions", None)
        or {}
    )
    privacy_flags = (
        contributions.get("privacy_flags", {})
        if isinstance(contributions, dict)
        else {}
    )
    boundary_violation_count = _int_value(
        by_key.get("historical_validation_boundary_violation_count")
    )
    return {
        "historical_validation_available": bool(
            by_key.get("historical_validation_status")
            and by_key["historical_validation_status"].value == "available"
        ),
        "historical_validation_metric_count": len(validation_rows),
        "configured_public_output_count": len(HISTORICAL_VALIDATION_METRIC_KEYS),
        "public_output_keys": sorted({row.metric_key for row in validation_rows}),
        "missing_public_output_keys": sorted(
            HISTORICAL_VALIDATION_METRIC_KEYS
            - {row.metric_key for row in validation_rows}
        ),
        "event_count": _int_value(by_key.get("historical_validation_event_count")),
        "available_event_count": _int_value(
            by_key.get("historical_validation_available_event_count")
        ),
        "insufficient_history_event_count": _int_value(
            by_key.get("historical_validation_insufficient_history_event_count")
        ),
        "boundary_violation_count": boundary_violation_count,
        "public_outputs_expose_probability_language": any(
            token in serialized
            for token in (
                "crash probability",
                "recession probability",
                "market direction probability",
                "probability calibration",
            )
        ),
        "public_outputs_expose_trading_language": any(
            token in serialized
            for token in (
                "trade signal",
                "buy",
                "sell",
                "hedge",
                "rebalance",
                "target allocation",
                "expected return",
            )
        ),
        "privacy_flags": privacy_flags,
        "reads_local_market_history_only": bool(
            privacy_flags.get("reads_local_market_history_only")
        ),
        "writes_sqlite": bool(privacy_flags.get("writes_sqlite")),
        "fetches_live_provider_data": bool(
            privacy_flags.get("fetches_live_provider_data")
        ),
    }

def _scenario_stress_audit(rows: list[DashboardEvidenceRow]) -> dict[str, Any]:
    stress_rows = [
        row
        for row in rows
        if row.module == "scenario_stress"
        or row.metric_key in SCENARIO_STRESS_METRIC_KEYS
    ]
    by_key = {row.metric_key: row for row in stress_rows}
    serialized = json.dumps([_row_payload(row) for row in stress_rows], ensure_ascii=False).lower()
    status = by_key.get("scenario_stress_status")
    boundary = by_key.get("scenario_stress_interpretation_boundary")
    missing = by_key.get("scenario_stress_missing_inputs")
    contributions = (
        getattr(status, "component_contributions", None)
        if status is not None
        else None
    )
    return {
        "scenario_stress_available": bool(
            status is not None and status.value == "available"
        ),
        "scenario_stress_metric_count": len(stress_rows),
        "configured_public_output_count": len(SCENARIO_STRESS_METRIC_KEYS),
        "public_output_keys": sorted({row.metric_key for row in stress_rows}),
        "missing_public_output_keys": sorted(
            SCENARIO_STRESS_METRIC_KEYS - {row.metric_key for row in stress_rows}
        ),
        "scenario_count": _int_value(by_key.get("scenario_stress_scenario_count")),
        "primary_scenario": (
            by_key["scenario_stress_primary_scenario"].value
            if by_key.get("scenario_stress_primary_scenario")
            else "missing"
        ),
        "severity_band": (
            by_key["scenario_stress_severity_band"].value
            if by_key.get("scenario_stress_severity_band")
            else "missing"
        ),
        "uncertainty_band": (
            by_key["scenario_stress_uncertainty_band"].value
            if by_key.get("scenario_stress_uncertainty_band")
            else "missing"
        ),
        "public_outputs_expose_probability_language": any(
            token in serialized
            for token in (
                "scenario probability",
                "crash probability",
                "market direction probability",
            )
        ),
        "public_outputs_expose_trading_language": any(
            token in serialized
            for token in (
                "trade signal",
                "target allocation",
                "expected return",
            )
        ),
        "boundary_available": bool(boundary and boundary.value),
        "missing_inputs_visible": bool(missing and missing.value is not None),
        "uses_model_registry": bool(
            isinstance(contributions, dict)
            and contributions.get("uses_model_registry")
        ),
        "uses_evidence_index": bool(
            isinstance(contributions, dict)
            and contributions.get("uses_evidence_index")
        ),
    }

def _growth_inflation_macro_pack_audit(rows: list[DashboardEvidenceRow]) -> dict[str, Any]:
    pack_rows = [
        row
        for row in rows
        if row.module == "growth_inflation_macro_pack"
        or row.metric_key in GROWTH_INFLATION_MACRO_PACK_METRIC_KEYS
    ]
    by_key = {row.metric_key: row for row in pack_rows}
    serialized = json.dumps([_row_payload(row) for row in pack_rows], ensure_ascii=False).lower()
    public_keys = {row.metric_key for row in pack_rows}
    boundary_rows = [
        row
        for row in pack_rows
        if row.metric_key.endswith("_interpretation_boundary")
    ]
    missing_rows = [
        row
        for row in pack_rows
        if row.metric_key.endswith("_missing_inputs")
    ]
    return {
        "growth_inflation_macro_pack_available": bool(
            by_key.get("growth_macro_status")
            and by_key.get("inflation_macro_status")
            and by_key.get("policy_constraint_status")
            and by_key.get("stagflation_watch_status")
        ),
        "growth_inflation_macro_pack_metric_count": len(pack_rows),
        "configured_public_output_count": len(GROWTH_INFLATION_MACRO_PACK_METRIC_KEYS),
        "public_output_keys": sorted(public_keys),
        "missing_public_output_keys": sorted(
            GROWTH_INFLATION_MACRO_PACK_METRIC_KEYS - public_keys
        ),
        "growth_macro_status": (
            by_key["growth_macro_status"].value
            if by_key.get("growth_macro_status")
            else "missing"
        ),
        "inflation_macro_status": (
            by_key["inflation_macro_status"].value
            if by_key.get("inflation_macro_status")
            else "missing"
        ),
        "policy_constraint_status": (
            by_key["policy_constraint_status"].value
            if by_key.get("policy_constraint_status")
            else "missing"
        ),
        "stagflation_watch_status": (
            by_key["stagflation_watch_status"].value
            if by_key.get("stagflation_watch_status")
            else "missing"
        ),
        "research_needed_count": sum(1 for row in pack_rows if row.status == "research_needed"),
        "missing_count": sum(1 for row in pack_rows if row.status == "missing"),
        "ai_context_allowed_count": sum(1 for row in pack_rows if row.ai_context_allowed),
        "public_outputs_expose_probability_language": any(
            token in serialized
            for token in (
                "crash probability",
                "recession probability",
                "market direction probability",
            )
        ),
        "public_outputs_expose_trading_language": any(
            token in serialized
            for token in (
                "trade signal",
                "target allocation",
                "expected return",
            )
        ),
        "boundary_available": any(row.value for row in boundary_rows),
        "missing_inputs_visible": any(row.value is not None for row in missing_rows),
    }

def _int_value(row: DashboardEvidenceRow | None) -> int:
    if row is None:
        return 0
    try:
        return int(row.value)
    except (TypeError, ValueError):
        return 0

def _historical_risk_percentile_audit(rows: list[DashboardEvidenceRow]) -> dict[str, Any]:
    percentile_rows = [
        row for row in rows if row.metric_key in HISTORICAL_RISK_PERCENTILE_METRIC_KEYS
    ]
    ok_rows = [row for row in percentile_rows if row.status in {"ok", "watch", "pressure", "stress"} and _has_value(row)]
    insufficient_rows = [
        row for row in percentile_rows if row.status == "insufficient_history"
    ]
    missing_rows = [row for row in percentile_rows if row.status == "missing"]
    robust_rows = [row for row in percentile_rows if row.robust_zscore is not None]
    percentile_band_rows = [row for row in percentile_rows if row.percentile_band]
    limited_rows = [
        row for row in percentile_rows if row.history_quality_status == "limited_history"
    ]
    blocked_rows = [row for row in percentile_rows if not row.ai_context_allowed]
    by_key = {row.metric_key: row for row in percentile_rows}
    return {
        "historical_risk_percentile_available": bool(ok_rows),
        "configured_count": len(percentile_rows),
        "computed_count": len(ok_rows),
        "insufficient_history_count": len(insufficient_rows),
        "missing_count": len(missing_rows),
        "robust_zscore_computed_count": len(robust_rows),
        "percentile_band_count": len(percentile_band_rows),
        "ai_context_allowed_count": sum(
            1 for row in percentile_rows if row.ai_context_allowed
        ),
        "hard_trigger_allowed_count": sum(
            1 for row in percentile_rows if row.trigger_eligibility == "hard_trigger_allowed"
        ),
        "auxiliary_only_count": sum(
            1 for row in percentile_rows if row.trigger_eligibility == "auxiliary_only"
        ),
        "proxy_auxiliary_only_count": sum(
            1 for row in percentile_rows if row.trigger_eligibility == "proxy_auxiliary_only"
        ),
        "not_eligible_count": sum(
            1 for row in percentile_rows if row.trigger_eligibility == "not_eligible"
        ),
        "limited_history_count": len(limited_rows),
        "blocked_rows": [
            {
                "metric_key": row.metric_key,
                "status": row.status,
                "blocked_reason": row.blocked_reason,
                "missing_reason": row.missing_reason,
                "history_quality_status": row.history_quality_status,
                "observation_count": row.observation_count,
            }
            for row in blocked_rows
        ],
        "ai_context_allowed_metric_keys": sorted(
            row.metric_key for row in percentile_rows if row.ai_context_allowed
        ),
        "auxiliary_metric_keys": sorted(
            row.metric_key
            for row in percentile_rows
            if row.trigger_eligibility in {"auxiliary_only", "proxy_auxiliary_only"}
        ),
        "metric_keys": sorted(
            row.metric_key for row in percentile_rows
        ),
        "insufficient_history_metric_keys": sorted(
            row.metric_key for row in insufficient_rows
        ),
        "source_badges": sorted(
            {row.source_badge for row in percentile_rows}
        ),
        "d13_credit_percentile_status": {
            "high_yield_spread": _credit_percentile_status(by_key, "high_yield_spread"),
            "investment_grade_spread": _credit_percentile_status(by_key, "investment_grade_spread"),
        },
        "historical_risk_percentile_metric_count": len(percentile_rows),
        "historical_risk_percentile_computed_count": len(ok_rows),
        "historical_risk_percentile_insufficient_history_count": len(insufficient_rows),
        "historical_risk_percentile_ai_context_allowed_count": sum(
            1 for row in percentile_rows if row.ai_context_allowed
        ),
    }

def _credit_percentile_status(
    by_key: dict[str, DashboardEvidenceRow],
    source_metric: str,
) -> dict[str, Any]:
    percentile = by_key.get(f"{source_metric}_percentile")
    zscore = by_key.get(f"{source_metric}_zscore")
    robust = by_key.get(f"{source_metric}_robust_zscore")
    anchor = percentile or zscore or robust
    return {
        "percentile_available": bool(percentile and percentile.ai_context_allowed),
        "zscore_available": bool(zscore and zscore.ai_context_allowed),
        "robust_zscore_available": bool(robust and robust.ai_context_allowed),
        "observation_count": anchor.observation_count if anchor is not None else 0,
        "blocked_reason": (
            anchor.blocked_reason or anchor.missing_reason
            if anchor is not None and not anchor.ai_context_allowed
            else None
        ),
        "history_quality_status": (
            anchor.history_quality_status if anchor is not None else "missing"
        ),
    }

def _valuation_research_audit(rows: list[DashboardEvidenceRow]) -> dict[str, Any]:
    doc_path = PROJECT_ROOT / "docs" / "valuation_source_research.md"
    row_by_key = {row.metric_key: row for row in rows}
    ppi_row = row_by_key.get("ppi_final_demand")
    price_only_proxy_keys = sorted(
        row.metric_key
        for row in rows
        if row.metric_key in PROXY_BREADTH_METRIC_KEYS and _has_value(row)
    )
    return {
        "valuation_available": False,
        "valuation_public_research_candidate_available": _valuation_doc_has_public_research_candidate(
            doc_path
        ),
        "valuation_proxy_available": False,
        "valuation_blocked_metric_keys": list(VALUATION_BLOCKED_METRIC_KEYS),
        "missing_for_valuation": [
            "sp500_trailing_pe_dated_source",
            "sp500_forward_pe_consensus_source",
            "cape_redistribution_policy",
            "earnings_denominator",
            "earnings_revision_source",
            "sp500_top10_weight_source",
        ],
        "source_research_document_exists": doc_path.exists(),
        "ppi_final_demand_available": _ppi_final_demand_row_available(ppi_row),
        "ppi_final_demand_status": ppi_row.status if ppi_row is not None else "missing",
        "ppi_final_demand_ai_context_allowed": bool(
            ppi_row is not None and ppi_row.ai_context_allowed
        ),
        "price_only_proxy_metric_keys_seen": price_only_proxy_keys,
        "valuation_gate_boundary": (
            "Price-only returns and proxy breadth do not satisfy valuation; "
            "provider integration remains blocked until dated source, license, "
            "observation date, and AI-context rules are implemented."
        ),
    }

def _ppi_final_demand_row_available(row: DashboardEvidenceRow | None) -> bool:
    return bool(
        row is not None
        and row.metric_key == "ppi_final_demand"
        and row.status == "ok"
        and _has_value(row)
        and row.source_badge in {"official", "official_fallback"}
        and row.source
        and row.observation_date
        and row.generated_at
        and row.freshness_status not in BAD_FRESHNESS
        and row.ai_context_allowed
    )

def _valuation_doc_has_public_research_candidate(doc_path: Path) -> bool:
    if not doc_path.exists():
        return False
    try:
        text = doc_path.read_text(encoding="utf-8").lower()
    except OSError:
        return False
    return "public_research" in text and "cape" in text

def _portfolio_compact_audit(rows: list[DashboardEvidenceRow]) -> dict[str, Any]:
    portfolio_rows = [row for row in rows if row.module == "portfolio_deviation"]
    compact_keys = {
        "max_deviation_asset",
        "max_deviation_pp",
        "equity_total_deviation_pp",
        "cash_reserve_status",
        "holdings_updated_at",
    }
    compact_rows = [row for row in portfolio_rows if row.metric_key in compact_keys]
    value_rows = [row for row in compact_rows if _has_value(row)]
    missing_rows = [row for row in compact_rows if not _has_value(row)]
    required_keys = {
        "max_deviation_asset",
        "max_deviation_pp",
        "equity_total_deviation_pp",
        "cash_reserve_status",
    }
    keys_with_values = {row.metric_key for row in value_rows}
    holdings_row = next(
        (row for row in compact_rows if row.metric_key == "holdings_updated_at"),
        None,
    )
    return {
        "portfolio_compact_available": required_keys.issubset(keys_with_values),
        "portfolio_deviation_value_count": len(value_rows),
        "portfolio_deviation_missing_count": len(missing_rows),
        "portfolio_deviation_ai_context_allowed_count": sum(
            1 for row in compact_rows if row.ai_context_allowed
        ),
        "portfolio_has_raw_holdings_leak": _portfolio_has_raw_holdings_leak(compact_rows),
        "portfolio_cash_excluded_from_target": _portfolio_cash_excluded_from_target(compact_rows),
        "portfolio_stale_status": holdings_row.freshness_status if holdings_row else "unknown",
    }

def _portfolio_has_raw_holdings_leak(rows: list[DashboardEvidenceRow]) -> bool:
    forbidden_tokens = (
        "holding",
        "holdings",
        "ticker",
        "fund_code",
        "fund code",
        "amount",
        "current_value",
        "market_value",
        "cost_basis",
        "profit_loss",
        "raw_fund",
    )
    safe_tokens = {
        "holdings_updated_at",
        "holdings updated at",
    }
    for row in rows:
        payload = json.dumps(_row_payload(row), ensure_ascii=False).lower()
        for token in safe_tokens:
            payload = payload.replace(token, "")
        if any(token in payload for token in forbidden_tokens):
            return True
    return False

def _portfolio_cash_excluded_from_target(rows: list[DashboardEvidenceRow]) -> bool:
    for row in rows:
        if row.metric_key != "cash_reserve_status":
            continue
        text = " ".join(
            str(item or "")
            for item in (
                row.value,
                row.value_text,
                row.interpretation_hint,
            )
        ).lower()
        return "cash" in text and "excluded" in text and (
            "target mix" in text or "target allocation" in text
        )
    return False
