from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Iterable

from data_quality.phase_e_return_band_diagnostics import PHASE_E_MAIN_WINDOW_MIN_MONTHS


TRAILING_RETURN_MONTHS = 3


@dataclass(frozen=True)
class MonthlyPriceObservation:
    month: str
    observation_date: str
    value: float
    source_key: str


@dataclass(frozen=True)
class MonthlyReturnObservation:
    month: str
    observation_date: str
    return_3m: float
    source_key: str


@dataclass(frozen=True)
class MonthlyReturnSeries:
    status: str
    source_key: str
    row_count: int
    first_month: str | None
    last_month: str | None
    min_required_months: int
    missing_lag_months: list[str]
    rows: list[MonthlyReturnObservation]
    semantic_boundary: str

    def as_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["rows"] = [asdict(row) for row in self.rows]
        return payload


def compute_trailing_3m_returns(
    observations: Iterable[MonthlyPriceObservation],
    *,
    source_key: str,
    min_required_months: int = PHASE_E_MAIN_WINDOW_MIN_MONTHS,
) -> MonthlyReturnSeries:
    month_values = _month_value_map(source_key, observations)
    returns: list[MonthlyReturnObservation] = []
    missing_lag_months: list[str] = []
    for month in sorted(month_values):
        lag_month = _shift_month(month, -TRAILING_RETURN_MONTHS)
        current = month_values[month]
        lagged = month_values.get(lag_month)
        if lagged is None:
            missing_lag_months.append(month)
            continue
        returns.append(
            MonthlyReturnObservation(
                month=month,
                observation_date=current["observation_date"],
                return_3m=current["value"] / lagged["value"] - 1.0,
                source_key=source_key,
            )
        )
    status = "ok" if len(returns) >= min_required_months else "insufficient_history"
    return MonthlyReturnSeries(
        status=status,
        source_key=source_key,
        row_count=len(returns),
        first_month=returns[0].month if returns else None,
        last_month=returns[-1].month if returns else None,
        min_required_months=min_required_months,
        missing_lag_months=missing_lag_months,
        rows=returns,
        semantic_boundary=(
            "This series computes overlapping trailing 3-month ETF returns from supplied monthly "
            "total-return levels. It does not forecast, annualize, optimize, or create return-band values."
        ),
    )


def _month_value_map(
    source_key: str,
    observations: Iterable[MonthlyPriceObservation],
) -> dict[str, dict[str, float | str]]:
    values: dict[str, dict[str, float | str]] = {}
    duplicates: set[str] = set()
    for row in observations:
        _validate_month(row.month)
        numeric_value = float(row.value)
        if numeric_value <= 0:
            raise ValueError(f"{source_key}: non-positive price level at {row.month}")
        if row.month in values:
            duplicates.add(row.month)
        values[row.month] = {
            "value": numeric_value,
            "observation_date": row.observation_date,
        }
    if duplicates:
        raise ValueError(f"{source_key}: duplicate month(s): {sorted(duplicates)}")
    return values


def _shift_month(month: str, shift: int) -> str:
    year, month_number = _parse_month(month)
    zero_based = year * 12 + month_number - 1 + shift
    shifted_year = zero_based // 12
    shifted_month = zero_based % 12 + 1
    return f"{shifted_year:04d}-{shifted_month:02d}"


def _parse_month(month: str) -> tuple[int, int]:
    year_text, month_text = month.split("-", 1)
    year = int(year_text)
    month_number = int(month_text)
    return year, month_number


def _validate_month(month: str) -> None:
    year, month_number = _parse_month(month)
    if year < 1900 or not 1 <= month_number <= 12:
        raise ValueError(f"invalid month:{month}")
