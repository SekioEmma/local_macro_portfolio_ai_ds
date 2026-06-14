from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Iterable

from modeling.evidence_index import EvidenceIndex
from modeling.metric_lookup import MetricLookup
from modeling.model_output import ModelOutput
from modeling.model_registry import get_model_registry


MODEL_KEY = "scenario_stress_v0"
MODULE_KEY = "scenario_stress"
MODEL_VERSION = "scenario_stress_v0"
FORMULA_VERSION = "d16_scenario_matrix_v0"
BOUNDARY = (
    "Scenario stress is a hypothetical scenario matrix and current evidence "
    "transmission review, not a forecast, event-odds model, asset-direction "
    "call, allocation directive, or return estimate."
)
PUBLIC_OUTPUT_KEYS = get_model_registry().public_output_keys(MODULE_KEY)
PRESSURE_STATUSES = {"watch", "pressure", "stress"}
HIGH_PRESSURE_STATUSES = {"pressure", "stress"}
SEVERITY_ORDER = {"mild": 0, "moderate": 1, "severe": 2, "extreme": 3}
UNCERTAINTY_ORDER = {"low": 0, "medium": 1, "high": 2}


@dataclass(frozen=True)
class ScenarioDefinition:
    scenario_name: str
    required_groups: tuple[str, ...]
    affected_groups: tuple[str, ...]
    transmission_channels: tuple[str, ...]
    core_metrics: tuple[str, ...]
    auxiliary_metrics: tuple[str, ...] = ()
    missing_constraints: tuple[str, ...] = ()
    boundary: str = BOUNDARY


SCENARIO_REGISTRY: tuple[ScenarioDefinition, ...] = (
    ScenarioDefinition(
        scenario_name="high_rates_stay_high",
        required_groups=("rates_real_yield",),
        affected_groups=("rates_real_yield", "valuation_earnings_breadth", "credit"),
        transmission_channels=(
            "nominal rates pressure",
            "real yield pressure",
            "duration pressure",
            "valuation pressure",
            "refinancing cost pressure",
        ),
        core_metrics=("dgs10", "dgs30", "dfii10", "real_yield_pressure_status"),
        auxiliary_metrics=("tlt_vs_shy_30d", "tlt_proxy_30d_return", "shy_proxy_30d_return"),
    ),
    ScenarioDefinition(
        scenario_name="inflation_rebound",
        required_groups=("inflation_energy",),
        affected_groups=("inflation_energy", "rates_real_yield", "valuation_earnings_breadth"),
        transmission_channels=(
            "inflation persistence",
            "policy easing constraint",
            "rates pressure",
            "valuation pressure",
        ),
        core_metrics=("core_cpi_yoy", "core_pce_yoy", "ppiaco_yoy", "ppi_final_demand_yoy"),
        auxiliary_metrics=("wti_30d_change", "brent_30d_change", "t10yie"),
    ),
    ScenarioDefinition(
        scenario_name="credit_spread_widening",
        required_groups=("credit",),
        affected_groups=("credit", "liquidity_funding", "equity_structure"),
        transmission_channels=(
            "credit risk premium",
            "corporate financing cost",
            "equity risk premium",
            "funding interaction",
        ),
        core_metrics=("high_yield_spread", "investment_grade_spread", "credit_stress_status"),
        auxiliary_metrics=("vix", "hyg_vs_lqd_30d", "hyg_vs_lqd_60d", "sp500_drawdown_3m"),
    ),
    ScenarioDefinition(
        scenario_name="liquidity_funding_squeeze",
        required_groups=("liquidity_funding",),
        affected_groups=("liquidity_funding", "credit", "equity_structure"),
        transmission_channels=(
            "money-market pressure",
            "funding pressure",
            "risk asset deleveraging channel",
            "credit/funding interaction",
        ),
        core_metrics=(
            "policy_plumbing_status",
            "short_term_funding_pressure_status",
            "official_stress_reference_status",
            "liquidity_funding_stress_status",
        ),
        auxiliary_metrics=("sofr_effr_spread", "effr_iorb_spread", "cp_effr_spread", "cp_sofr_spread"),
    ),
    ScenarioDefinition(
        scenario_name="growth_slowdown",
        required_groups=("labor_growth",),
        affected_groups=("labor_growth", "valuation_earnings_breadth", "credit"),
        transmission_channels=(
            "labor deterioration",
            "demand slowdown",
            "earnings pressure channel",
            "credit risk channel",
        ),
        core_metrics=(
            "unemployment_rate",
            "initial_jobless_claims",
            "continuing_claims",
            "nonfarm_payrolls",
            "labor_deterioration_status",
        ),
        missing_constraints=("broad_growth_pack",),
    ),
    ScenarioDefinition(
        scenario_name="stagflation_pressure",
        required_groups=("inflation_energy", "labor_growth", "rates_real_yield"),
        affected_groups=(
            "inflation_energy",
            "labor_growth",
            "rates_real_yield",
            "valuation_earnings_breadth",
            "credit",
        ),
        transmission_channels=(
            "inflation persistence",
            "growth weakening",
            "policy constraint",
            "equity valuation and earnings dual pressure",
            "credit pressure channel",
        ),
        core_metrics=(
            "core_cpi_yoy",
            "core_pce_yoy",
            "labor_deterioration_status",
            "unemployment_rate",
            "initial_jobless_claims",
            "dgs10",
            "dfii10",
            "real_yield_pressure_status",
        ),
    ),
    ScenarioDefinition(
        scenario_name="ai_mega_cap_concentration_unwind",
        required_groups=("equity_structure",),
        affected_groups=("equity_structure", "valuation_earnings_breadth", "portfolio_overlay"),
        transmission_channels=(
            "concentration unwind",
            "mega-cap valuation pressure",
            "index leadership deterioration",
            "equity structure fragility",
        ),
        core_metrics=("nasdaq100_drawdown_3m", "sp500_drawdown_3m"),
        auxiliary_metrics=("qqq_vs_spy_30d", "qqq_vs_spy_60d", "spy_vs_rsp_30d", "spy_vs_rsp_60d"),
        missing_constraints=("valuation", "earnings", "true_breadth"),
    ),
)


def get_scenario_registry() -> tuple[ScenarioDefinition, ...]:
    return SCENARIO_REGISTRY


def build_scenario_stress_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    index = EvidenceIndex(rows)
    lookup = MetricLookup()
    scenarios = [_evaluate_scenario(item, index, lookup) for item in SCENARIO_REGISTRY]
    supported = [
        item
        for item in scenarios
        if item["support_band"] in {"moderate", "strong"}
    ]
    weak = [item for item in scenarios if item["support_band"] == "weak"]
    primary = _primary_scenario(supported)
    status = "available" if primary else "limited_evidence" if weak else "insufficient_evidence"
    status_for_rows = "ok" if status == "available" else status
    missing_inputs = sorted(
        {
            missing
            for scenario in scenarios
            for missing in scenario["missing_inputs"]
        }
    )
    supporting = [
        f"{scenario['scenario_name']}:{','.join(scenario['supporting_evidence_keys'])}"
        for scenario in scenarios
        if scenario["supporting_evidence_keys"]
    ]
    affected_groups = sorted(
        {
            group
            for scenario in scenarios
            if scenario["support_band"] != "unsupported"
            for group in scenario["affected_evidence_groups"]
        }
    )
    channels = sorted(
        {
            channel
            for scenario in scenarios
            if scenario["support_band"] != "unsupported"
            for channel in scenario["transmission_channels"]
        }
    )
    severity = _max_band(
        (scenario["severity_band"] for scenario in scenarios),
        order=SEVERITY_ORDER,
        default="mild",
    )
    uncertainty = _max_band(
        (scenario["uncertainty_band"] for scenario in scenarios),
        order=UNCERTAINTY_ORDER,
        default="high",
    )
    return {
        "status": status,
        "row_status": status_for_rows,
        "scenario_count": len(scenarios),
        "scenarios": scenarios,
        "primary_scenario": primary["scenario_name"] if primary else "none",
        "affected_groups": affected_groups,
        "transmission_channels": channels,
        "severity_band": severity if supported or weak else "mild",
        "uncertainty_band": uncertainty,
        "supporting_evidence": supporting,
        "missing_inputs": missing_inputs,
        "input_evidence": _input_evidence(index, scenarios),
        "as_of_date": _latest_observation_date(index, scenarios),
        "uses_model_registry": bool(get_model_registry().get(MODULE_KEY)),
        "uses_evidence_index": isinstance(index, EvidenceIndex),
    }


def build_scenario_stress_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    summary = build_scenario_stress_summary(rows)
    now = _utc_now()
    ai_context_allowed = summary["status"] == "available"
    base = {
        "model_key": MODEL_KEY,
        "module_key": MODULE_KEY,
        "status": summary["row_status"],
        "source_badge": "derived",
        "freshness_status": "historical",
        "interpretation_boundary": BOUNDARY,
        "component_contributions": {
            "scenarios": summary["scenarios"],
            "uses_model_registry": summary["uses_model_registry"],
            "uses_evidence_index": summary["uses_evidence_index"],
        },
        "ai_context_allowed": ai_context_allowed,
    }
    values: dict[str, tuple[str, Any]] = {
        "scenario_stress_status": ("Scenario stress status", summary["status"]),
        "scenario_stress_scenario_count": ("Scenario stress scenario count", summary["scenario_count"]),
        "scenario_stress_scenarios": (
            "Scenario stress scenarios",
            "; ".join(
                f"{item['scenario_name']}={item['support_band']}/{item['severity_band']}/{item['uncertainty_band']}"
                for item in summary["scenarios"]
            ),
        ),
        "scenario_stress_primary_scenario": ("Scenario stress primary scenario", summary["primary_scenario"]),
        "scenario_stress_affected_groups": (
            "Scenario stress affected groups",
            ", ".join(summary["affected_groups"]) or "none",
        ),
        "scenario_stress_transmission_channels": (
            "Scenario stress transmission channels",
            ", ".join(summary["transmission_channels"]) or "none",
        ),
        "scenario_stress_severity_band": ("Scenario stress severity band", summary["severity_band"]),
        "scenario_stress_uncertainty_band": ("Scenario stress uncertainty band", summary["uncertainty_band"]),
        "scenario_stress_supporting_evidence": (
            "Scenario stress supporting evidence",
            "; ".join(summary["supporting_evidence"]) or "none",
        ),
        "scenario_stress_missing_inputs": (
            "Scenario stress missing inputs",
            ", ".join(summary["missing_inputs"]) or "none",
        ),
        "scenario_stress_interpretation_boundary": ("Scenario stress interpretation boundary", BOUNDARY),
        "scenario_stress_model_version": ("Scenario stress model version", MODEL_VERSION),
        "scenario_stress_formula_version": ("Scenario stress formula version", FORMULA_VERSION),
        "scenario_stress_as_of_date": ("Scenario stress as-of date", summary["as_of_date"] or "not available"),
    }
    return [
        ModelOutput(
            metric_key=metric_key,
            value=value,
            value_text=str(value),
            **base,
        ).to_metric_payload(
            display_name=display_name,
            source="local_rules",
            source_series="D16_SCENARIO_MATRIX_V0",
            observation_date=summary["as_of_date"],
            generated_at=now,
            missing_reason=None if ai_context_allowed else summary["status"],
            input_evidence=summary["input_evidence"],
            missing_inputs=summary["missing_inputs"],
        )
        for metric_key, (display_name, value) in values.items()
    ]


def _evaluate_scenario(
    definition: ScenarioDefinition,
    index: EvidenceIndex,
    lookup: MetricLookup,
) -> dict[str, Any]:
    core_support = [
        metric
        for metric in definition.core_metrics
        if _metric_supports_pressure(metric, index, lookup, require_core_trigger=True)
    ]
    auxiliary_support = [
        metric
        for metric in definition.auxiliary_metrics
        if _metric_supports_pressure(metric, index, lookup, require_core_trigger=False)
    ]
    blocked_inputs = index.missing_or_blocked_inputs(
        [*definition.core_metrics, *definition.auxiliary_metrics],
        require_ai_context_allowed=False,
        require_core_trigger=False,
    )
    missing_inputs = sorted(set(blocked_inputs).union(definition.missing_constraints))
    support_band = _support_band(definition, core_support, auxiliary_support)
    scenario_status = (
        "available"
        if support_band in {"moderate", "strong"}
        else "limited_evidence"
        if support_band == "weak"
        else "insufficient_evidence"
    )
    proxy_constraints = _proxy_constraints(definition, index)
    if proxy_constraints and support_band == "strong":
        support_band = "moderate"
    severity_band = _severity_band(support_band, proxy_constraints)
    uncertainty_band = _uncertainty_band(support_band, missing_inputs, proxy_constraints)
    return {
        "scenario_name": definition.scenario_name,
        "scenario_status": scenario_status,
        "input_evidence_groups": list(definition.required_groups),
        "affected_evidence_groups": list(definition.affected_groups),
        "transmission_channels": list(definition.transmission_channels),
        "support_band": support_band,
        "severity_band": severity_band,
        "uncertainty_band": uncertainty_band,
        "supporting_evidence_keys": sorted(set(core_support + auxiliary_support)),
        "missing_inputs": missing_inputs,
        "blocked_inputs": sorted(set(blocked_inputs)),
        "proxy_constraints": proxy_constraints,
        "interpretation_boundary": BOUNDARY,
    }


def _metric_supports_pressure(
    metric_key: str,
    index: EvidenceIndex,
    lookup: MetricLookup,
    *,
    require_core_trigger: bool,
) -> bool:
    if not index.is_usable_for_support(
        metric_key,
        require_ai_context_allowed=False,
        require_core_trigger=require_core_trigger,
    ):
        return False
    row = index.by_metric_key(metric_key)
    if row is None:
        return False
    if require_core_trigger and not lookup.can_support_label(metric_key):
        return False
    value = _row_value(row, "value")
    status = str(_row_value(row, "status") or "")
    if isinstance(value, str) and value.lower() in PRESSURE_STATUSES:
        return True
    return status in PRESSURE_STATUSES


def _support_band(
    definition: ScenarioDefinition,
    core_support: list[str],
    auxiliary_support: list[str],
) -> str:
    if not core_support and not auxiliary_support:
        return "unsupported"
    required_count = len(definition.required_groups)
    if definition.scenario_name == "liquidity_funding_squeeze":
        if len(core_support) >= 3:
            return "strong"
        if len(core_support) >= 2:
            return "moderate"
        return "weak"
    if definition.scenario_name == "stagflation_pressure":
        has_inflation = any(metric in core_support for metric in ("core_cpi_yoy", "core_pce_yoy", "ppiaco_yoy", "ppi_final_demand_yoy"))
        has_labor = any(metric in core_support for metric in ("labor_deterioration_status", "unemployment_rate", "initial_jobless_claims"))
        has_rates = any(metric in core_support for metric in ("dgs10", "dfii10", "real_yield_pressure_status"))
        if has_inflation and has_labor and has_rates:
            return "strong"
        if sum((has_inflation, has_labor, has_rates)) >= 2:
            return "moderate"
        return "weak"
    if required_count > 1 and len(core_support) >= required_count:
        return "moderate"
    if len(core_support) >= 2:
        return "strong"
    if len(core_support) == 1:
        return "weak"
    return "weak" if auxiliary_support else "unsupported"


def _severity_band(support_band: str, proxy_constraints: list[str]) -> str:
    if support_band == "strong" and not proxy_constraints:
        return "severe"
    if support_band in {"strong", "moderate"}:
        return "moderate"
    return "mild"


def _uncertainty_band(
    support_band: str,
    missing_inputs: list[str],
    proxy_constraints: list[str],
) -> str:
    if support_band == "strong" and not missing_inputs and not proxy_constraints:
        return "low"
    if support_band in {"moderate", "strong"} and len(missing_inputs) <= 2:
        return "medium"
    return "high"


def _proxy_constraints(definition: ScenarioDefinition, index: EvidenceIndex) -> list[str]:
    proxy_present = [
        metric
        for metric in definition.auxiliary_metrics
        if index.blocked_reason(
            metric,
            require_ai_context_allowed=False,
            require_core_trigger=True,
        )
        == "proxy_only_cannot_trigger"
        and index.has_valid_value(metric)
    ]
    constraints = [f"{metric}_proxy_only" for metric in proxy_present]
    if definition.scenario_name == "ai_mega_cap_concentration_unwind":
        constraints.append("valuation_earnings_true_breadth_gaps_explicit")
    return sorted(set(constraints))


def _primary_scenario(scenarios: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not scenarios:
        return None
    support_order = {"strong": 3, "moderate": 2, "weak": 1, "unsupported": 0}
    return sorted(
        scenarios,
        key=lambda item: (
            support_order.get(item["support_band"], 0),
            SEVERITY_ORDER.get(item["severity_band"], 0),
            -UNCERTAINTY_ORDER.get(item["uncertainty_band"], 2),
            item["scenario_name"],
        ),
        reverse=True,
    )[0]


def _input_evidence(index: EvidenceIndex, scenarios: list[dict[str, Any]]) -> list[dict[str, Any]]:
    keys = sorted(
        {
            key
            for scenario in scenarios
            for key in scenario["supporting_evidence_keys"]
        }
    )
    return [index.public_payload(key) for key in keys if index.by_metric_key(key) is not None]


def _latest_observation_date(index: EvidenceIndex, scenarios: list[dict[str, Any]]) -> str | None:
    dates = [
        str(_row_value(index.by_metric_key(key), "observation_date"))
        for scenario in scenarios
        for key in scenario["supporting_evidence_keys"]
        if index.by_metric_key(key) is not None
        and _row_value(index.by_metric_key(key), "observation_date")
    ]
    return max(dates) if dates else None


def _max_band(
    values: Iterable[str],
    *,
    order: dict[str, int],
    default: str,
) -> str:
    ranked = sorted(values, key=lambda value: order.get(value, -1), reverse=True)
    return ranked[0] if ranked else default


def _row_value(row: Any, field: str) -> Any:
    if isinstance(row, dict):
        return row.get(field)
    return getattr(row, field, None)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()
