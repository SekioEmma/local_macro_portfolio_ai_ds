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
    """Orchestrate the D13→D14→D10→D11→D17→D18→D15→D19→D16→Stage8 model row sequence.

    Extracted from build_dashboard_evidence_table for testability. Preserves the
    exact build order and input accumulation pattern from the original service.
    dashboard_service.py remains the public entry point; call this only from there.
    """

    def _to_dicts(rows: list[DashboardEvidenceRow]) -> list[dict]:
        return [_model_to_dict(r) for r in rows]

    def _make_rows(module_key: str, payloads: list[dict]) -> list[DashboardEvidenceRow]:
        return [build_evidence_row(module_key, DashboardMetric(**p)) for p in payloads]

    db_path_str = str(db_path) if db_path is not None else None

    # D13 — historical risk percentile (db-only; no upstream row dependency)
    percentile_rows = _make_rows(
        "historical_risk_percentile",
        historical_percentile_metrics.build_historical_percentile_rows(db_path=db_path_str),
    )

    # D14 — liquidity/funding stress (db-only; no upstream row dependency)
    liquidity_funding_rows = _make_rows(
        "liquidity_funding_stress",
        liquidity_funding_stress.build_liquidity_funding_rows(db_path=db_path),
    )

    # D10 — financial stress composite (consumes base + D13 + D14)
    financial_stress_rows = _make_rows(
        "financial_stress_composite",
        financial_stress_composite.build_financial_stress_rows(
            _to_dicts(base_rows + percentile_rows + liquidity_funding_rows)
        ),
    )

    # D11 — pullback systemic risk checklist (consumes base + D13 + D14 + D10)
    pullback_rows = _make_rows(
        "pullback_systemic_risk_checklist",
        pullback_systemic_checklist.build_pullback_checklist_rows(
            _to_dicts(
                base_rows + percentile_rows + liquidity_funding_rows + financial_stress_rows
            )
        ),
    )

    # D17 — growth/inflation macro pack (consumes base + D13 + D14 + D10 + D11)
    growth_inflation_rows = _make_rows(
        "growth_inflation_macro_pack",
        growth_inflation_macro_pack.build_growth_inflation_macro_pack_rows(
            _to_dicts(
                base_rows
                + percentile_rows
                + liquidity_funding_rows
                + financial_stress_rows
                + pullback_rows
            )
        ),
    )

    # D18 — valuation/equity structure (consumes base + D13 + D14 + D10 + D11 + D17)
    valuation_equity_rows = _make_rows(
        "valuation_equity_structure",
        valuation_equity_structure.build_valuation_equity_structure_rows(
            _to_dicts(
                base_rows
                + percentile_rows
                + liquidity_funding_rows
                + financial_stress_rows
                + pullback_rows
                + growth_inflation_rows
            )
        ),
    )

    # D15 — macro regime review (consumes base + D13 + D14 + D10 + D11 + D17 + D18)
    macro_regime_rows = _make_rows(
        "macro_regime_review",
        macro_regime_review.build_macro_regime_review_rows(
            _to_dicts(
                base_rows
                + percentile_rows
                + liquidity_funding_rows
                + financial_stress_rows
                + pullback_rows
                + growth_inflation_rows
                + valuation_equity_rows
            )
        ),
    )

    # D19 — historical validation (db-only; independent of upstream model rows)
    historical_validation_rows = _make_rows(
        "historical_validation",
        historical_validation.build_historical_validation_rows(db_path=db_path_str),
    )

    # D16 — scenario stress (consumes base + D13 + D14 + D10 + D11 + D17 + D18 + D15 + D19)
    scenario_stress_rows = _make_rows(
        "scenario_stress",
        scenario_stress.build_scenario_stress_rows(
            _to_dicts(
                base_rows
                + percentile_rows
                + liquidity_funding_rows
                + financial_stress_rows
                + pullback_rows
                + growth_inflation_rows
                + valuation_equity_rows
                + macro_regime_rows
                + historical_validation_rows
            )
        ),
    )

    # Stage 8 — portfolio exposure overlay
    # (consumes base + D13 + D14 + D10 + D11 + D17 + D18 + D15 + D16 + D19;
    #  note: scenario_stress replaces macro_regime_rows position vs D15 input)
    portfolio_exposure_rows = _make_rows(
        "portfolio_exposure_overlay",
        portfolio_exposure_overlay.build_portfolio_exposure_overlay_rows(
            _to_dicts(
                base_rows
                + percentile_rows
                + liquidity_funding_rows
                + financial_stress_rows
                + pullback_rows
                + growth_inflation_rows
                + valuation_equity_rows
                + macro_regime_rows
                + scenario_stress_rows
                + historical_validation_rows
            )
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
