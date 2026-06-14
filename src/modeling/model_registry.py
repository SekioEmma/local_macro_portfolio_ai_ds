from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from modeling.metric_lookup import D15_PUBLIC_OUTPUT_KEYS, D19_PUBLIC_OUTPUT_KEYS


D10_PUBLIC_OUTPUT_KEYS = (
    "financial_stress_score",
    "financial_stress_status",
    "financial_stress_dominant_pressure_source",
    "financial_stress_component_contributions",
    "financial_stress_missing_inputs",
    "financial_stress_interpretation_boundary",
    "financial_stress_percentile_context",
    "financial_stress_funding_liquidity_context",
)
D11_PUBLIC_OUTPUT_KEYS = (
    "pullback_classification",
    "pullback_checklist_items",
    "pullback_missing_critical_inputs",
    "pullback_supporting_evidence",
    "pullback_interpretation_boundary",
    "pullback_percentile_context",
    "pullback_liquidity_funding_context",
)
D13_PUBLIC_OUTPUT_KEYS = (
    "high_yield_spread_percentile",
    "high_yield_spread_zscore",
    "high_yield_spread_robust_zscore",
    "investment_grade_spread_percentile",
    "investment_grade_spread_zscore",
    "investment_grade_spread_robust_zscore",
    "vix_percentile",
    "vix_zscore",
    "vix_robust_zscore",
    "dgs30_percentile",
    "dgs30_zscore",
    "dgs30_robust_zscore",
    "dfii10_percentile",
    "dfii10_zscore",
    "dfii10_robust_zscore",
    "sp500_drawdown_3m_percentile",
    "sp500_drawdown_3m_robust_zscore",
    "nasdaq100_drawdown_3m_percentile",
    "nasdaq100_drawdown_3m_robust_zscore",
    "initial_claims_4w_avg_percentile",
    "initial_claims_4w_avg_robust_zscore",
    "continuing_claims_4w_avg_percentile",
    "continuing_claims_4w_avg_robust_zscore",
)
D14_PUBLIC_OUTPUT_KEYS = (
    "sofr_effr_spread",
    "effr_iorb_spread",
    "cp_effr_spread",
    "cp_sofr_spread",
    "policy_plumbing_status",
    "short_term_funding_pressure_status",
    "official_stress_reference_status",
    "liquidity_funding_stress_status",
    "liquidity_funding_interpretation_boundary",
)
FORBIDDEN_PUBLIC_OUTPUT_KEYS = (
    "macro_regime_score",
    "support_score_internal",
    "group_score_internal",
    "crash_probability",
    "recession_probability",
    "market_direction_probability",
    "expected_return",
    "trade_signal",
    "target_allocation",
)
D19_FORBIDDEN_TERMS = (
    "roc",
    "auc",
    "precision",
    "recall",
    "f1",
    "probability_calibration",
    "trading_backtest",
)


@dataclass(frozen=True)
class ModelRegistration:
    model_key: str
    module_key: str
    version_prefix: str
    category: str
    public_output_keys: tuple[str, ...]
    required_input_groups: tuple[str, ...]
    optional_input_groups: tuple[str, ...]
    ai_context_policy: str
    audit_policy: str
    frontend_registry_policy: str
    forbidden_language_policy: tuple[str, ...]
    interpretation_boundary: str
    notes: str = ""


class ModelRegistry:
    def __init__(self, registrations: Iterable[ModelRegistration] | None = None) -> None:
        self._registrations = {
            item.module_key: item
            for item in (
                tuple(registrations)
                if registrations is not None
                else DEFAULT_MODEL_REGISTRATIONS
            )
        }

    def get(self, module_key: str) -> ModelRegistration | None:
        return self._registrations.get(module_key)

    def require(self, module_key: str) -> ModelRegistration:
        item = self.get(module_key)
        if item is None:
            raise KeyError(f"unknown model module: {module_key}")
        return item

    def all(self) -> list[ModelRegistration]:
        return list(self._registrations.values())

    def module_keys(self) -> tuple[str, ...]:
        return tuple(sorted(self._registrations))

    def model_output_module_keys(self) -> set[str]:
        return {
            item.module_key
            for item in self._registrations.values()
            if item.ai_context_policy == "model_output"
        }

    def public_output_keys(self, module_key: str) -> tuple[str, ...]:
        return self.require(module_key).public_output_keys


def get_model_registry() -> ModelRegistry:
    return ModelRegistry()


DEFAULT_MODEL_REGISTRATIONS: tuple[ModelRegistration, ...] = (
    ModelRegistration(
        model_key="financial_stress_composite_v0",
        module_key="financial_stress_composite",
        version_prefix="financial_stress",
        category="model_output",
        public_output_keys=D10_PUBLIC_OUTPUT_KEYS,
        required_input_groups=("credit", "rates_real_yield", "equity_structure"),
        optional_input_groups=("liquidity_funding", "labor_growth"),
        ai_context_policy="model_output",
        audit_policy="audit_d10_financial_stress",
        frontend_registry_policy="model_output_module_label_and_boundary",
        forbidden_language_policy=(
            "pressure temperature, not event odds",
            "no action instruction",
            "VIX alone is not systemic",
            "equity drawdown alone is not systemic",
        ),
        interpretation_boundary=(
            "Financial stress score is a transparent pressure temperature, not "
            "an event-odds model. VIX alone and equity drawdown alone are not "
            "systemic stress."
        ),
        notes="D10 stays deterministic and evidence-only.",
    ),
    ModelRegistration(
        model_key="pullback_systemic_risk_checklist_v0",
        module_key="pullback_systemic_risk_checklist",
        version_prefix="pullback_checklist",
        category="model_output",
        public_output_keys=D11_PUBLIC_OUTPUT_KEYS,
        required_input_groups=("credit", "equity_structure"),
        optional_input_groups=("liquidity_funding", "valuation_earnings_breadth"),
        ai_context_policy="model_output",
        audit_policy="audit_d11_pullback_checklist",
        frontend_registry_policy="model_output_module_label_and_boundary",
        forbidden_language_policy=(
            "current evidence review only",
            "not event odds",
            "D14 alone cannot trigger systemic review",
            "missing valuation earnings true breadth remain constraints",
        ),
        interpretation_boundary=(
            "Pullback checklist is a current evidence review, not an event-odds "
            "model. D14 alone cannot trigger systemic review."
        ),
        notes="Missing valuation, earnings, and true breadth stay visible.",
    ),
    ModelRegistration(
        model_key="historical_risk_percentile_v0",
        module_key="historical_risk_percentile",
        version_prefix="historical_percentile",
        category="derived_context",
        public_output_keys=D13_PUBLIC_OUTPUT_KEYS,
        required_input_groups=("historical_validation",),
        optional_input_groups=("credit", "rates_real_yield", "equity_structure", "labor_growth"),
        ai_context_policy="fact_or_excluded_by_row",
        audit_policy="audit_d13_historical_percentile",
        frontend_registry_policy="derived_module_label_and_boundary",
        forbidden_language_policy=(
            "normalization context only",
            "insufficient history tolerated",
            "percentile and z-score are not event odds",
            "no regime determination alone",
        ),
        interpretation_boundary=(
            "Historical percentile is relative to available local history. "
            "Z-score is a normalization statistic, not event odds."
        ),
        notes="D13 rows may be facts, but blocked rows remain visible.",
    ),
    ModelRegistration(
        model_key="liquidity_funding_stress_v0",
        module_key="liquidity_funding_stress",
        version_prefix="liquidity_funding",
        category="derived_context",
        public_output_keys=D14_PUBLIC_OUTPUT_KEYS,
        required_input_groups=("liquidity_funding",),
        optional_input_groups=("credit", "rates_real_yield"),
        ai_context_policy="fact_with_context",
        audit_policy="audit_d14_liquidity_funding",
        frontend_registry_policy="derived_module_label_and_boundary",
        forbidden_language_policy=(
            "confirmation context",
            "D14 alone cannot trigger liquidity or systemic regime",
            "ON RRP alone is not a risk trigger",
            "official stress indices do not replace project composite",
        ),
        interpretation_boundary=(
            "Liquidity/funding stress rows are reference evidence. D14 alone "
            "cannot trigger liquidity or systemic regime."
        ),
        notes="D14 supports D10/D11/D15 as confirmation context.",
    ),
    ModelRegistration(
        model_key="macro_regime_review_v0",
        module_key="macro_regime_review",
        version_prefix="macro_regime_review",
        category="model_output",
        public_output_keys=D15_PUBLIC_OUTPUT_KEYS,
        required_input_groups=("credit", "liquidity_funding", "rates_real_yield", "inflation_energy", "labor_growth"),
        optional_input_groups=("equity_structure", "valuation_earnings_breadth"),
        ai_context_policy="model_output",
        audit_policy="audit_d15_macro_regime_review",
        frontend_registry_policy="model_output_module_label_and_boundary",
        forbidden_language_policy=(
            "current evidence review",
            "not classifier",
            "not forecast",
            "no public macro regime score",
            "no public internal support or group scores",
            "band-only public support quality conflict",
            "no event odds or allocation directive",
        ),
        interpretation_boundary=(
            "Macro regime review is a current evidence review, not a classifier "
            "or forecast. It exposes bands and ranked evidence, not public scores."
        ),
        notes="D15 public keys are band and evidence outputs only.",
    ),
    ModelRegistration(
        model_key="historical_validation_v0",
        module_key="historical_validation",
        version_prefix="historical_validation",
        category="model_output",
        public_output_keys=D19_PUBLIC_OUTPUT_KEYS,
        required_input_groups=("historical_validation",),
        optional_input_groups=("credit", "liquidity_funding", "rates_real_yield", "inflation_energy", "labor_growth"),
        ai_context_policy="model_output",
        audit_policy="audit_d19_historical_validation",
        frontend_registry_policy="model_output_module_label_and_boundary",
        forbidden_language_policy=(
            "read-only historical replay",
            "not model skill scoring",
            "not event odds",
            "not trading evaluation",
            "fail closed when local history is insufficient",
        ),
        interpretation_boundary=(
            "Historical validation is read-only historical replay for "
            "event-window consistency and boundary validation. It fails closed "
            "when local history is insufficient."
        ),
        notes="D19 v0 is structural validation, not future-outcome evaluation.",
    ),
)
