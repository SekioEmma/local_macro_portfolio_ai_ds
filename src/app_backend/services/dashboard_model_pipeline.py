from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from app_backend.schemas.responses import DashboardEvidenceRow, DashboardMetric
from data_quality import financial_stress_composite
from data_quality import growth_inflation_macro_pack
from data_quality import historical_percentile_metrics
from data_quality import historical_validation
from data_quality import liquidity_funding_stress
from data_quality import macro_regime_review
from data_quality import portfolio_exposure_overlay
from data_quality import pullback_systemic_checklist
from data_quality import scenario_stress
from data_quality import valuation_equity_structure


def _model_to_dict(value: Any) -> dict:
    if hasattr(value, "model_dump"):
        return value.model_dump()
    return value.dict()


@dataclass(frozen=True)
class DashboardModelPipelineResult:
    rows: list[DashboardEvidenceRow]
    row_groups: dict[str, list[DashboardEvidenceRow]]


def build_dashboard_model_rows(
    *,
    base_rows: list[DashboardEvidenceRow],
    db_path: Path | str | None = None,
    build_evidence_row: Callable[[str, DashboardMetric], DashboardEvidenceRow],
) -> DashboardModelPipelineResult:
    """Orchestrate the model row sequence with dict-accumulator optimization.

    Pipeline order (each group converted to dicts once, then reused):

        Historical Risk Normalization (legacy: D13)
        → Liquidity & Funding Stress (legacy: D14)
        → Financial Stress Composite (legacy: D10)
        → Pullback vs Systemic Risk Review (legacy: D11)
        → Growth & Inflation Context (legacy: D17)
        → Valuation & Equity Structure Context (legacy: D18)
        → Macro Regime Review (legacy: D15)
        → Historical Validation Replay (legacy: D19)
        → Scenario Stress Matrix (legacy: D16)
        → Portfolio Exposure Overlay (legacy: Stage 8)

    P-M1 optimization: each row group is converted to dicts exactly once via
    _model_to_dict, then appended to a shared dict accumulator. Downstream
    models receive the accumulated dicts directly instead of re-converting
    the same DashboardEvidenceRow objects on every call.

    dashboard_service.py remains the public entry point; call this only from there.
    """

    def _to_dicts(rows: list[DashboardEvidenceRow]) -> list[dict]:
        return [_model_to_dict(r) for r in rows]

    def _make_rows(module_key: str, payloads: list[dict]) -> list[DashboardEvidenceRow]:
        return [build_evidence_row(module_key, DashboardMetric(**p)) for p in payloads]

    db_path_str = str(db_path) if db_path is not None else None

    # Convert base rows to dicts once; this is the seed for the accumulator.
    base_dict_rows = _to_dicts(base_rows)

    # Historical Risk Normalization (legacy: D13) — db-only; no upstream row dependency
    percentile_rows = _make_rows(
        "historical_risk_percentile",
        historical_percentile_metrics.build_historical_percentile_rows(db_path=db_path_str),
    )
    percentile_dict_rows = _to_dicts(percentile_rows)

    # Liquidity & Funding Stress (legacy: D14) — db-only; no upstream row dependency
    liquidity_funding_rows = _make_rows(
        "liquidity_funding_stress",
        liquidity_funding_stress.build_liquidity_funding_rows(db_path=db_path),
    )
    liquidity_funding_dict_rows = _to_dicts(liquidity_funding_rows)

    # Dict accumulator: base + D13 + D14. Extended after each model group.
    model_input_dicts: list[dict] = [
        *base_dict_rows,
        *percentile_dict_rows,
        *liquidity_funding_dict_rows,
    ]

    # Financial Stress Composite (legacy: D10) — consumes base + D13 + D14
    financial_stress_rows = _make_rows(
        "financial_stress_composite",
        financial_stress_composite.build_financial_stress_rows(model_input_dicts),
    )
    financial_stress_dict_rows = _to_dicts(financial_stress_rows)
    model_input_dicts.extend(financial_stress_dict_rows)

    # Pullback vs Systemic Risk Review (legacy: D11) — consumes base + D13..D10
    pullback_rows = _make_rows(
        "pullback_systemic_risk_checklist",
        pullback_systemic_checklist.build_pullback_checklist_rows(model_input_dicts),
    )
    pullback_dict_rows = _to_dicts(pullback_rows)
    model_input_dicts.extend(pullback_dict_rows)

    # Growth & Inflation Context (legacy: D17) — consumes base + D13..D11
    growth_inflation_rows = _make_rows(
        "growth_inflation_macro_pack",
        growth_inflation_macro_pack.build_growth_inflation_macro_pack_rows(
            model_input_dicts
        ),
    )
    growth_inflation_dict_rows = _to_dicts(growth_inflation_rows)
    model_input_dicts.extend(growth_inflation_dict_rows)

    # Valuation & Equity Structure Context (legacy: D18) — consumes base + D13..D17
    valuation_equity_rows = _make_rows(
        "valuation_equity_structure",
        valuation_equity_structure.build_valuation_equity_structure_rows(
            model_input_dicts
        ),
    )
    valuation_equity_dict_rows = _to_dicts(valuation_equity_rows)
    model_input_dicts.extend(valuation_equity_dict_rows)

    # Macro Regime Review (legacy: D15) — consumes base + D13..D18
    macro_regime_rows = _make_rows(
        "macro_regime_review",
        macro_regime_review.build_macro_regime_review_rows(model_input_dicts),
    )
    macro_regime_dict_rows = _to_dicts(macro_regime_rows)
    model_input_dicts.extend(macro_regime_dict_rows)

    # Snapshot before Historical Validation Replay for Scenario Stress Matrix
    # and Portfolio Exposure Overlay input construction.
    pre_validation_input_dicts = list(model_input_dicts)

    # Historical Validation Replay (legacy: D19) — db-only; independent
    historical_validation_rows = _make_rows(
        "historical_validation",
        historical_validation.build_historical_validation_rows(db_path=db_path_str),
    )
    historical_validation_dict_rows = _to_dicts(historical_validation_rows)

    # Scenario Stress Matrix (legacy: D16) — consumes base + D13..D15 + D19
    scenario_input_dicts = [
        *pre_validation_input_dicts,
        *historical_validation_dict_rows,
    ]
    scenario_stress_rows = _make_rows(
        "scenario_stress",
        scenario_stress.build_scenario_stress_rows(scenario_input_dicts),
    )
    scenario_stress_dict_rows = _to_dicts(scenario_stress_rows)

    # Portfolio Exposure Overlay (legacy: Stage 8) — consumes
    # base + D13..D15 + D16 + D19
    portfolio_input_dicts = [
        *pre_validation_input_dicts,
        *scenario_stress_dict_rows,
        *historical_validation_dict_rows,
    ]
    portfolio_exposure_rows = _make_rows(
        "portfolio_exposure_overlay",
        portfolio_exposure_overlay.build_portfolio_exposure_overlay_rows(
            portfolio_input_dicts
        ),
    )

    row_groups: dict[str, list[DashboardEvidenceRow]] = {
        "historical_risk_percentile": percentile_rows,
        "liquidity_funding_stress": liquidity_funding_rows,
        "financial_stress_composite": financial_stress_rows,
        "pullback_systemic_risk_checklist": pullback_rows,
        "growth_inflation_macro_pack": growth_inflation_rows,
        "valuation_equity_structure": valuation_equity_rows,
        "macro_regime_review": macro_regime_rows,
        "historical_validation": historical_validation_rows,
        "scenario_stress": scenario_stress_rows,
        "portfolio_exposure_overlay": portfolio_exposure_rows,
    }

    # Preserve exact assembly order from original dashboard_service.py.
    # D13 (percentile) and D14 (liquidity) appear last even though computed first,
    # because they are support inputs rather than primary model outputs in the UI.
    rows = (
        financial_stress_rows
        + pullback_rows
        + growth_inflation_rows
        + valuation_equity_rows
        + macro_regime_rows
        + scenario_stress_rows
        + historical_validation_rows
        + portfolio_exposure_rows
        + percentile_rows
        + liquidity_funding_rows
    )

    return DashboardModelPipelineResult(rows=rows, row_groups=row_groups)
