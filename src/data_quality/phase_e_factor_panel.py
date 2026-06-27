from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Iterable

from data_quality.phase_e_return_band_diagnostics import (
    MonthlyObservation,
    PHASE_E_FACTOR_SPECS,
    PHASE_E_MAIN_WINDOW_MIN_MONTHS,
)


PHASE_E_CANONICAL_FACTOR_KEYS = tuple(PHASE_E_FACTOR_SPECS)


@dataclass(frozen=True)
class MonthlyFactorRow:
    month: str
    values: dict[str, float]


@dataclass(frozen=True)
class FactorPanel:
    status: str
    factor_keys: list[str]
    row_count: int
    first_month: str | None
    last_month: str | None
    min_required_months: int
    missing_factors: list[str]
    missing_months_by_factor: dict[str, list[str]]
    rows: list[MonthlyFactorRow]
    semantic_boundary: str

    def as_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["rows"] = [{"month": row.month, "values": row.values} for row in self.rows]
        return payload


def build_monthly_factor_panel(
    series_by_factor: dict[str, Iterable[MonthlyObservation]],
    *,
    factor_keys: Iterable[str] = PHASE_E_CANONICAL_FACTOR_KEYS,
    min_required_months: int = PHASE_E_MAIN_WINDOW_MIN_MONTHS,
) -> FactorPanel:
    factors = list(factor_keys)
    mapped: dict[str, dict[str, float]] = {}
    missing_factors: list[str] = []
    for factor_key in factors:
        rows = list(series_by_factor.get(factor_key, []))
        if not rows:
            missing_factors.append(factor_key)
            mapped[factor_key] = {}
            continue
        mapped[factor_key] = _month_value_map(factor_key, rows)

    months_by_factor = {factor_key: set(values) for factor_key, values in mapped.items()}
    common_months = (
        sorted(set.intersection(*(months_by_factor[factor_key] for factor_key in factors)))
        if factors and not missing_factors
        else []
    )
    rows = [
        MonthlyFactorRow(
            month=month,
            values={factor_key: mapped[factor_key][month] for factor_key in factors},
        )
        for month in common_months
    ]
    missing_months_by_factor = _missing_months_by_factor(factors, months_by_factor)
    status = _panel_status(
        row_count=len(rows),
        missing_factors=missing_factors,
        min_required_months=min_required_months,
    )
    return FactorPanel(
        status=status,
        factor_keys=factors,
        row_count=len(rows),
        first_month=rows[0].month if rows else None,
        last_month=rows[-1].month if rows else None,
        min_required_months=min_required_months,
        missing_factors=missing_factors,
        missing_months_by_factor=missing_months_by_factor,
        rows=rows,
        semantic_boundary=(
            "This panel only aligns confirmed monthly factor observations. It does not impute missing "
            "months, estimate betas, construct scenario shocks, or compute return-band values."
        ),
    )


def _month_value_map(
    factor_key: str,
    observations: Iterable[MonthlyObservation],
) -> dict[str, float]:
    month_values: dict[str, float] = {}
    duplicate_months: set[str] = set()
    for row in observations:
        _validate_month(row.month)
        if row.month in month_values:
            duplicate_months.add(row.month)
        month_values[row.month] = float(row.value)
    if duplicate_months:
        raise ValueError(f"{factor_key}: duplicate month(s): {sorted(duplicate_months)}")
    return month_values


def _missing_months_by_factor(
    factors: list[str],
    months_by_factor: dict[str, set[str]],
) -> dict[str, list[str]]:
    union_months: set[str] = set()
    for months in months_by_factor.values():
        union_months.update(months)
    return {
        factor_key: sorted(union_months - months_by_factor[factor_key])
        for factor_key in factors
        if union_months - months_by_factor[factor_key]
    }


def _panel_status(
    *,
    row_count: int,
    missing_factors: list[str],
    min_required_months: int,
) -> str:
    if missing_factors:
        return "missing_factors"
    if row_count < min_required_months:
        return "insufficient_common_history"
    return "ok"


def _validate_month(month: str) -> None:
    year_text, month_text = month.split("-", 1)
    int(year_text)
    month_number = int(month_text)
    if not 1 <= month_number <= 12:
        raise ValueError(f"invalid month:{month}")
