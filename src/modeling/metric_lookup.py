from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable


D15_PUBLIC_OUTPUT_KEYS = (
    "macro_regime_label",
    "support_band",
    "evidence_quality_band",
    "conflict_band",
    "primary_pressure_ranking",
    "supporting_evidence",
    "conflicting_evidence",
    "missing_inputs",
    "blocked_inputs",
    "interpretation_boundary",
    "model_version",
    "formula_version",
    "as_of_date",
)
D19_PUBLIC_OUTPUT_KEYS = (
    "historical_validation_status",
    "historical_validation_event_count",
    "historical_validation_available_event_count",
    "historical_validation_insufficient_history_event_count",
    "historical_validation_ordinary_pullback_over_escalation_count",
    "historical_validation_stress_window_under_escalation_count",
    "historical_validation_boundary_violation_count",
    "historical_validation_event_window_summary",
    "historical_validation_privacy_flags",
    "historical_validation_validation_boundary",
    "historical_validation_model_version",
    "historical_validation_formula_version",
    "historical_validation_as_of_date",
    "historical_validation_coverage_summary",
    "historical_validation_module_consistency_summary",
    "historical_validation_proxy_constraint_summary",
    "historical_validation_missing_data_summary",
    "historical_validation_replay_version",
)
D16_PUBLIC_OUTPUT_KEYS = (
    "scenario_stress_status",
    "scenario_stress_scenario_count",
    "scenario_stress_scenarios",
    "scenario_stress_primary_scenario",
    "scenario_stress_affected_groups",
    "scenario_stress_transmission_channels",
    "scenario_stress_severity_band",
    "scenario_stress_uncertainty_band",
    "scenario_stress_supporting_evidence",
    "scenario_stress_missing_inputs",
    "scenario_stress_interpretation_boundary",
    "scenario_stress_model_version",
    "scenario_stress_formula_version",
    "scenario_stress_as_of_date",
)
D17_PUBLIC_OUTPUT_KEYS = (
    "growth_macro_status",
    "growth_macro_supporting_evidence",
    "growth_macro_missing_inputs",
    "growth_macro_interpretation_boundary",
    "inflation_macro_status",
    "inflation_macro_supporting_evidence",
    "inflation_macro_missing_inputs",
    "inflation_macro_interpretation_boundary",
    "policy_constraint_status",
    "policy_constraint_supporting_evidence",
    "policy_constraint_missing_inputs",
    "policy_constraint_interpretation_boundary",
    "stagflation_watch_status",
    "stagflation_watch_supporting_evidence",
    "stagflation_watch_missing_inputs",
    "stagflation_watch_interpretation_boundary",
    "growth_inflation_macro_pack_model_version",
    "growth_inflation_macro_pack_formula_version",
    "growth_inflation_macro_pack_as_of_date",
)
D18_PUBLIC_OUTPUT_KEYS = (
    "valuation_context_status",
    "valuation_pressure_hint",
    "valuation_metric_source_quality",
    "valuation_missing_inputs",
    "valuation_interpretation_boundary",
    "earnings_context_status",
    "earnings_missing_inputs",
    "earnings_interpretation_boundary",
    "equity_structure_status",
    "equity_structure_supporting_evidence",
    "equity_structure_missing_inputs",
    "equity_structure_interpretation_boundary",
    "breadth_concentration_context_status",
    "breadth_concentration_supporting_evidence",
    "breadth_concentration_missing_inputs",
    "breadth_concentration_interpretation_boundary",
    "valuation_equity_structure_model_version",
    "valuation_equity_structure_formula_version",
    "valuation_equity_structure_as_of_date",
)
D17_RESEARCH_NEEDED_KEYS = (
    "ism_manufacturing_pmi",
    "ism_services_pmi",
    "ism_new_orders",
    "ism_employment",
    "retail_sales_mom",
    "retail_sales_yoy",
    "retail_sales_control_group",
    "industrial_production_yoy",
    "capacity_utilization",
    "housing_starts",
    "building_permits",
    "new_home_sales",
    "mortgage_30y_rate",
    "core_cpi_goods_yoy",
    "core_cpi_services_yoy",
    "core_pce_goods_yoy",
    "core_pce_services_yoy",
    "ppi_final_demand_goods_yoy",
    "ppi_final_demand_services_yoy",
    "ism_prices_paid",
    "gasoline_price_context",
)
D18_RESEARCH_NEEDED_KEYS = (
    "sp500_trailing_pe",
    "sp500_forward_pe",
    "cape_shiller_pe",
    "earnings_yield",
    "equity_risk_premium_proxy",
    "earnings_revision",
    "eps_growth",
    "advance_decline_line",
    "percent_above_200dma",
    "new_highs_new_lows",
    "true_breadth",
    "sp500_top10_weight",
    "mag7_concentration",
)
D15_FORBIDDEN_PUBLIC_KEYS = (
    "macro_regime_score",
    "support_score_internal",
    "group_score_internal",
)


@dataclass(frozen=True)
class MetricMetadata:
    metric_key: str
    module: str
    label: str
    evidence_group: str
    role: str
    source_policy: str
    ai_context_policy: str
    trigger_policy: str
    public_output: bool
    interpretation_boundary_required: bool
    status_policy: str
    notes: str = ""


class MetricLookup:
    def __init__(self, metrics: Iterable[MetricMetadata] | None = None) -> None:
        self._metrics = {
            metric.metric_key: metric
            for metric in (tuple(metrics) if metrics is not None else DEFAULT_METRICS)
        }

    def get(self, metric_key: str) -> MetricMetadata | None:
        return self._metrics.get(metric_key)

    def require(self, metric_key: str) -> MetricMetadata:
        metric = self.get(metric_key)
        if metric is None:
            raise KeyError(f"unknown metric metadata: {metric_key}")
        return metric

    def all(self) -> list[MetricMetadata]:
        return list(self._metrics.values())

    def public_output_keys(self, module_key: str | None = None) -> tuple[str, ...]:
        return tuple(
            metric.metric_key
            for metric in self._metrics.values()
            if metric.public_output and (module_key is None or metric.module == module_key)
        )

    def metrics_by_group(self, evidence_group: str) -> list[MetricMetadata]:
        return [
            metric
            for metric in self._metrics.values()
            if metric.evidence_group == evidence_group
        ]

    def metrics_by_module(self, module_key: str) -> list[MetricMetadata]:
        return [
            metric
            for metric in self._metrics.values()
            if metric.module == module_key
        ]

    def can_strong_trigger(self, metric_key: str) -> bool:
        metric = self.get(metric_key)
        return bool(metric and metric.trigger_policy == "can_trigger")

    def can_support_label(self, metric_key: str) -> bool:
        metric = self.get(metric_key)
        if metric is None:
            return False
        return metric.status_policy == "usable_when_current" and metric.trigger_policy in {
            "can_trigger",
            "confirmation_only",
            "current_level_only",
        }


def _metric(
    metric_key: str,
    module: str,
    evidence_group: str,
    role: str,
    source_policy: str,
    trigger_policy: str,
    *,
    label: str | None = None,
    public_output: bool = False,
    ai_context_policy: str = "eligible_when_current",
    status_policy: str = "usable_when_current",
    boundary_required: bool = False,
    notes: str = "",
) -> MetricMetadata:
    return MetricMetadata(
        metric_key=metric_key,
        module=module,
        label=label or metric_key.replace("_", " "),
        evidence_group=evidence_group,
        role=role,
        source_policy=source_policy,
        ai_context_policy=ai_context_policy,
        trigger_policy=trigger_policy,
        public_output=public_output,
        interpretation_boundary_required=boundary_required,
        status_policy=status_policy,
        notes=notes,
    )


DEFAULT_METRICS: tuple[MetricMetadata, ...] = (
    _metric("high_yield_spread", "credit_stress", "credit", "core", "official_core", "can_trigger"),
    _metric("investment_grade_spread", "credit_stress", "credit", "core", "official_core", "can_trigger"),
    _metric("vix", "credit_stress", "credit", "auxiliary", "official_or_fallback_core", "confirmation_only"),
    _metric("hyg_vs_lqd_30d", "breadth_concentration_proxy", "credit", "proxy", "proxy_auxiliary_only", "proxy_never_strong_trigger", status_policy="auxiliary_only"),
    _metric("liquidity_funding_stress_status", "liquidity_funding_stress", "liquidity_funding", "derived", "derived_with_inputs", "confirmation_only", boundary_required=True),
    _metric("policy_plumbing_status", "liquidity_funding_stress", "liquidity_funding", "confirm", "derived_with_inputs", "confirmation_only"),
    _metric("short_term_funding_pressure_status", "liquidity_funding_stress", "liquidity_funding", "confirm", "derived_with_inputs", "confirmation_only"),
    _metric("official_stress_reference_status", "liquidity_funding_stress", "liquidity_funding", "confirm", "derived_with_inputs", "confirmation_only"),
    _metric("dgs10", "rate_pressure", "rates_real_yield", "core", "official_core", "can_trigger"),
    _metric("dgs30", "rate_pressure", "rates_real_yield", "core", "official_core", "current_level_only"),
    _metric("dfii10", "real_yield_pressure", "rates_real_yield", "core", "official_core", "can_trigger"),
    _metric("t10yie", "real_yield_pressure", "rates_real_yield", "confirm", "official_core", "confirmation_only"),
    _metric("real_yield_pressure_status", "real_yield_pressure", "rates_real_yield", "derived", "derived_with_inputs", "confirmation_only"),
    _metric("core_cpi_yoy", "inflation_energy_pressure", "inflation_energy", "core", "official_core", "can_trigger"),
    _metric("core_pce_yoy", "inflation_energy_pressure", "inflation_energy", "core", "official_core", "can_trigger"),
    _metric("ppiaco_yoy", "inflation_energy_pressure", "inflation_energy", "core", "official_core", "confirmation_only"),
    _metric("ppi_final_demand_yoy", "inflation_energy_pressure", "inflation_energy", "core", "official_core", "confirmation_only"),
    _metric("wti_30d_change", "inflation_energy_pressure", "inflation_energy", "auxiliary", "derived_with_inputs", "confirmation_only"),
    _metric("brent_30d_change", "inflation_energy_pressure", "inflation_energy", "auxiliary", "derived_with_inputs", "confirmation_only"),
    _metric("initial_jobless_claims", "labor_macro", "labor_growth", "core", "official_core", "can_trigger"),
    _metric("continuing_claims", "labor_macro", "labor_growth", "core", "official_core", "confirmation_only"),
    _metric("unemployment_rate", "labor_macro", "labor_growth", "core", "official_core", "can_trigger"),
    _metric("nonfarm_payrolls", "labor_macro", "labor_growth", "core", "official_core", "confirmation_only"),
    _metric("labor_deterioration_status", "labor_macro", "labor_growth", "derived", "derived_with_inputs", "confirmation_only"),
    _metric("growth_macro_status", "growth_inflation_macro_pack", "growth_macro", "derived", "derived_with_inputs", "confirmation_only", boundary_required=True),
    _metric("inflation_macro_status", "growth_inflation_macro_pack", "inflation_macro", "derived", "derived_with_inputs", "confirmation_only", boundary_required=True),
    _metric("policy_constraint_status", "growth_inflation_macro_pack", "policy_constraint", "derived", "derived_with_inputs", "confirmation_only", boundary_required=True),
    _metric("stagflation_watch_status", "growth_inflation_macro_pack", "stagflation_watch_context", "derived", "derived_with_inputs", "confirmation_only", boundary_required=True),
    _metric("sp500_drawdown_3m", "market_stress_derived", "equity_structure", "derived", "derived_with_inputs", "confirmation_only"),
    _metric("nasdaq100_drawdown_3m", "market_stress_derived", "equity_structure", "derived", "derived_with_inputs", "confirmation_only"),
    _metric("spy_vs_rsp_30d", "breadth_concentration_proxy", "equity_structure", "proxy", "proxy_auxiliary_only", "proxy_never_strong_trigger", status_policy="auxiliary_only"),
    _metric("earnings_revision", "valuation_research", "valuation_earnings_breadth", "research", "research_needed_only", "cannot_trigger", status_policy="research_needed"),
    _metric("eps_growth", "valuation_research", "valuation_earnings_breadth", "research", "research_needed_only", "cannot_trigger", status_policy="research_needed"),
    _metric("max_deviation_asset", "portfolio_deviation", "portfolio_overlay", "local_context", "local_context", "cannot_trigger", status_policy="context_only"),
    _metric("max_deviation_pp", "portfolio_deviation", "portfolio_overlay", "local_context", "local_context", "cannot_trigger", status_policy="context_only"),
    _metric("equity_total_deviation_pp", "portfolio_deviation", "portfolio_overlay", "local_context", "local_context", "cannot_trigger", status_policy="context_only"),
    *(
        _metric(
            metric_key,
            "growth_inflation_macro_pack",
            "growth_macro" if metric_key in {
                "ism_manufacturing_pmi",
                "ism_services_pmi",
                "ism_new_orders",
                "ism_employment",
                "retail_sales_mom",
                "retail_sales_yoy",
                "retail_sales_control_group",
                "industrial_production_yoy",
                "capacity_utilization",
                "housing_starts",
                "building_permits",
                "new_home_sales",
                "mortgage_30y_rate",
            } else "inflation_macro",
            "research",
            "research_needed_only",
            "cannot_trigger",
            status_policy="research_needed",
        )
        for metric_key in D17_RESEARCH_NEEDED_KEYS
    ),
    *(
        _metric(
            metric_key,
            "valuation_equity_structure",
            "valuation_earnings_breadth"
            if metric_key
            in {
                "sp500_trailing_pe",
                "sp500_forward_pe",
                "cape_shiller_pe",
                "earnings_yield",
                "equity_risk_premium_proxy",
                "earnings_revision",
                "eps_growth",
            }
            else "equity_structure",
            "research",
            "research_needed_only",
            "cannot_trigger",
            status_policy="research_needed",
        )
        for metric_key in D18_RESEARCH_NEEDED_KEYS
        if metric_key not in {"earnings_revision", "eps_growth"}
    ),
    *(
        _metric(
            metric_key,
            "macro_regime_review",
            "historical_validation" if metric_key == "as_of_date" else "macro_regime_review",
            "boundary" if "boundary" in metric_key else "version" if "version" in metric_key else "model_output",
            "model_output_only",
            "metadata_only",
            public_output=True,
            ai_context_policy="model_output",
            status_policy="model_output",
            boundary_required=metric_key == "interpretation_boundary",
        )
        for metric_key in D15_PUBLIC_OUTPUT_KEYS
    ),
    *(
        _metric(
            metric_key,
            "historical_validation",
            "historical_validation",
            "boundary" if "boundary" in metric_key else "version" if "version" in metric_key else "model_output",
            "model_output_only",
            "metadata_only",
            public_output=True,
            ai_context_policy="model_output",
            status_policy="model_output",
            boundary_required=metric_key == "historical_validation_validation_boundary",
        )
        for metric_key in D19_PUBLIC_OUTPUT_KEYS
    ),
    *(
        _metric(
            metric_key,
            "scenario_stress",
            "scenario_stress",
            "boundary" if "boundary" in metric_key else "version" if "version" in metric_key else "model_output",
            "model_output_only",
            "metadata_only",
            public_output=True,
            ai_context_policy="model_output",
            status_policy="model_output",
            boundary_required=metric_key == "scenario_stress_interpretation_boundary",
        )
        for metric_key in D16_PUBLIC_OUTPUT_KEYS
    ),
    *(
        _metric(
            metric_key,
            "growth_inflation_macro_pack",
            "growth_macro" if metric_key.startswith("growth_macro") else "inflation_macro" if metric_key.startswith("inflation_macro") else "policy_constraint" if metric_key.startswith("policy_constraint") else "stagflation_watch_context" if metric_key.startswith("stagflation_watch") else "growth_inflation_macro_pack",
            "derived" if metric_key.endswith("_status") else "boundary" if "boundary" in metric_key else "version" if "version" in metric_key else "model_output",
            "derived_with_inputs" if metric_key.endswith("_status") else "model_output_only",
            "confirmation_only" if metric_key.endswith("_status") else "metadata_only",
            public_output=True,
            ai_context_policy="fact_or_excluded_by_row",
            status_policy="usable_when_current" if metric_key.endswith("_status") else "model_output",
            boundary_required=metric_key.endswith("_interpretation_boundary"),
        )
        for metric_key in D17_PUBLIC_OUTPUT_KEYS
    ),
    *(
        _metric(
            metric_key,
            "valuation_equity_structure",
            "valuation_earnings_breadth"
            if metric_key.startswith(("valuation_", "earnings_"))
            else "equity_structure",
            "derived"
            if metric_key.endswith("_status") or metric_key == "valuation_pressure_hint"
            else "boundary"
            if "boundary" in metric_key
            else "version"
            if "version" in metric_key or metric_key.endswith("_as_of_date")
            else "model_output",
            "derived_with_inputs"
            if metric_key.endswith("_status") or metric_key == "valuation_pressure_hint"
            else "model_output_only",
            "cannot_trigger",
            public_output=True,
            ai_context_policy="fact_or_excluded_by_row",
            status_policy="auxiliary_only"
            if metric_key.endswith("_status") or metric_key == "valuation_pressure_hint"
            else "model_output",
            boundary_required=metric_key.endswith("_interpretation_boundary"),
            notes="D18 context cannot determine macro regime or systemic review.",
        )
        for metric_key in D18_PUBLIC_OUTPUT_KEYS
    ),
)
