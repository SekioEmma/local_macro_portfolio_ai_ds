from __future__ import annotations

import csv
from dataclasses import asdict, dataclass
from datetime import date
from pathlib import Path
from typing import Any, Iterable


PHASE_E_MAIN_WINDOW_MIN_MONTHS = 84
PHASE_E_AUXILIARY_WINDOW_MIN_MONTHS = 60
PHASE_E_ROLLING_WINDOW_MONTHS = 120
MANUAL_AUDITED_DOWNLOAD = "manual_audited_download"


@dataclass(frozen=True)
class MonthlyObservation:
    month: str
    observation_date: str
    value: float
    source_method: str
    source_series: str
    source_url: str | None = None
    captured_at: str | None = None


@dataclass(frozen=True)
class SeriesCoverage:
    series_key: str
    status: str
    observation_count: int
    first_month: str | None
    last_month: str | None
    month_span_inclusive: int
    missing_months: list[str]
    duplicate_months: list[str]
    longest_consecutive_run_months: int
    trailing_120m_windows_with_at_least_84_observed: int
    meets_84_month_minimum: bool
    meets_60_month_auxiliary_minimum: bool


@dataclass(frozen=True)
class PhaseEFactorDiagnostic:
    factor_key: str
    status: str
    required: bool
    source_keys: list[str]
    coverage: SeriesCoverage | None
    missing_reason: str | None
    semantic_note: str


PHASE_E_FACTOR_SPECS: dict[str, dict[str, Any]] = {
    "real_yield_10y": {
        "source_keys": ["real_yield_10y"],
        "semantic_note": (
            "Phase E design says DGS10 - T5YIFR, while existing project config also uses DFII10. "
            "A policy choice is required before numerical output."
        ),
    },
    "credit_spread_hy": {
        "source_keys": ["high_yield_spread"],
        "semantic_note": (
            "HY OAS is a co-movement load factor, not a standalone causal shock. "
            "Manual audited MacroMicro/ICE data may only unlock history-length diagnostics until admitted."
        ),
    },
    "growth_momentum_zscore": {
        "source_keys": ["growth_momentum_zscore", "ism_pmi"],
        "semantic_note": "ISM PMI z-score represents growth momentum, not growth surprise.",
    },
    "vix_level": {
        "source_keys": ["vix"],
        "semantic_note": "VIX is an equity-volatility co-movement factor, not a standalone crisis trigger.",
    },
    "ust_slope": {
        "source_keys": ["ust_slope", "yield_curve_10y2y", "t10y2y"],
        "semantic_note": "10Y-2Y curve slope is macro context, not a trading signal.",
    },
    "commodity_trend": {
        "source_keys": ["commodity_trend", "brent"],
        "semantic_note": "Commodity trend should be aligned as monthly Brent momentum.",
    },
}


def load_manual_oas_monthly_csv(path: Path | str) -> list[MonthlyObservation]:
    resolved = Path(path)
    observations: list[MonthlyObservation] = []
    with resolved.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        required = {
            "month",
            "observation_date",
            "oas_percent",
            "source_method",
            "source_series",
            "source_url",
            "captured_at",
        }
        missing = required - set(reader.fieldnames or [])
        if missing:
            raise ValueError(f"missing required columns: {sorted(missing)}")
        for line_number, row in enumerate(reader, start=2):
            source_method = str(row["source_method"]).strip()
            if source_method != MANUAL_AUDITED_DOWNLOAD:
                raise ValueError(f"line {line_number}: unexpected source_method:{source_method}")
            observations.append(
                MonthlyObservation(
                    month=str(row["month"]).strip(),
                    observation_date=str(row["observation_date"]).strip(),
                    value=float(str(row["oas_percent"]).strip()),
                    source_method=source_method,
                    source_series=str(row["source_series"]).strip(),
                    source_url=str(row["source_url"]).strip(),
                    captured_at=str(row["captured_at"]).strip(),
                )
            )
    return observations


def build_phase_e_factor_diagnostics(
    series_by_key: dict[str, Iterable[MonthlyObservation]],
    *,
    real_yield_policy: str = "requires_decision",
) -> dict[str, Any]:
    diagnostics = [
        _factor_diagnostic(factor_key, spec, series_by_key, real_yield_policy=real_yield_policy)
        for factor_key, spec in PHASE_E_FACTOR_SPECS.items()
    ]
    blocking_factors = [
        item.factor_key for item in diagnostics if item.required and item.status != "ok"
    ]
    return {
        "status": "ok" if not blocking_factors else "insufficient_inputs",
        "mode": "diagnostic_only",
        "no_return_band_values": True,
        "main_window_min_months": PHASE_E_MAIN_WINDOW_MIN_MONTHS,
        "auxiliary_window_min_months": PHASE_E_AUXILIARY_WINDOW_MIN_MONTHS,
        "blocking_factors": blocking_factors,
        "factor_diagnostics": [asdict(item) for item in diagnostics],
        "semantic_boundary": (
            "This diagnostic only reviews input availability for Phase E. It does not run OLS, "
            "does not create scenario shocks, and does not output return ranges."
        ),
    }


def coverage_for_series(
    series_key: str,
    observations: Iterable[MonthlyObservation],
) -> SeriesCoverage:
    rows = sorted(observations, key=lambda item: item.month)
    month_counts: dict[str, int] = {}
    for row in rows:
        _parse_month(row.month)
        date.fromisoformat(row.observation_date)
        month_counts[row.month] = month_counts.get(row.month, 0) + 1
    unique_months = sorted(month_counts)
    duplicate_months = [month for month, count in sorted(month_counts.items()) if count > 1]
    missing_months = _missing_months(unique_months)
    longest_run = _longest_consecutive_run(unique_months)
    trailing_eligible = _count_trailing_eligible_windows(unique_months)
    observation_count = len(unique_months)
    meets_84 = observation_count >= PHASE_E_MAIN_WINDOW_MIN_MONTHS
    meets_60 = observation_count >= PHASE_E_AUXILIARY_WINDOW_MIN_MONTHS
    status = "ok" if meets_84 and meets_60 and not duplicate_months else "insufficient_history"
    return SeriesCoverage(
        series_key=series_key,
        status=status,
        observation_count=observation_count,
        first_month=unique_months[0] if unique_months else None,
        last_month=unique_months[-1] if unique_months else None,
        month_span_inclusive=_month_span(unique_months),
        missing_months=missing_months,
        duplicate_months=duplicate_months,
        longest_consecutive_run_months=longest_run,
        trailing_120m_windows_with_at_least_84_observed=trailing_eligible,
        meets_84_month_minimum=meets_84,
        meets_60_month_auxiliary_minimum=meets_60,
    )


def _factor_diagnostic(
    factor_key: str,
    spec: dict[str, Any],
    series_by_key: dict[str, Iterable[MonthlyObservation]],
    *,
    real_yield_policy: str,
) -> PhaseEFactorDiagnostic:
    if factor_key == "real_yield_10y" and real_yield_policy == "requires_decision":
        return PhaseEFactorDiagnostic(
            factor_key=factor_key,
            status="blocked",
            required=True,
            source_keys=spec["source_keys"],
            coverage=None,
            missing_reason="real_yield_policy_requires_user_decision",
            semantic_note=spec["semantic_note"],
        )

    for source_key in spec["source_keys"]:
        rows = list(series_by_key.get(source_key, []))
        if rows:
            coverage = coverage_for_series(source_key, rows)
            return PhaseEFactorDiagnostic(
                factor_key=factor_key,
                status=coverage.status,
                required=True,
                source_keys=spec["source_keys"],
                coverage=coverage,
                missing_reason=None if coverage.status == "ok" else coverage.status,
                semantic_note=spec["semantic_note"],
            )

    return PhaseEFactorDiagnostic(
        factor_key=factor_key,
        status="missing",
        required=True,
        source_keys=spec["source_keys"],
        coverage=None,
        missing_reason="no_monthly_series_supplied",
        semantic_note=spec["semantic_note"],
    )


def _missing_months(months: list[str]) -> list[str]:
    if not months:
        return []
    observed = set(months)
    missing: list[str] = []
    year, month = _parse_month(months[0])
    end = _parse_month(months[-1])
    while (year, month) <= end:
        label = _format_month(year, month)
        if label not in observed:
            missing.append(label)
        year, month = _next_month(year, month)
    return missing


def _longest_consecutive_run(months: list[str]) -> int:
    if not months:
        return 0
    observed = set(months)
    longest = 0
    current = 0
    year, month = _parse_month(months[0])
    end = _parse_month(months[-1])
    while (year, month) <= end:
        if _format_month(year, month) in observed:
            current += 1
            longest = max(longest, current)
        else:
            current = 0
        year, month = _next_month(year, month)
    return longest


def _count_trailing_eligible_windows(months: list[str]) -> int:
    if not months:
        return 0
    observed = set(months)
    calendar_months: list[tuple[int, int, bool]] = []
    year, month = _parse_month(months[0])
    end = _parse_month(months[-1])
    while (year, month) <= end:
        label = _format_month(year, month)
        calendar_months.append((year, month, label in observed))
        year, month = _next_month(year, month)

    eligible = 0
    for index in range(len(calendar_months)):
        window = calendar_months[max(0, index - PHASE_E_ROLLING_WINDOW_MONTHS + 1) : index + 1]
        observed_count = sum(1 for _, _, has_observation in window if has_observation)
        if len(window) >= PHASE_E_MAIN_WINDOW_MIN_MONTHS and observed_count >= PHASE_E_MAIN_WINDOW_MIN_MONTHS:
            eligible += 1
    return eligible


def _month_span(months: list[str]) -> int:
    if not months:
        return 0
    start_year, start_month = _parse_month(months[0])
    end_year, end_month = _parse_month(months[-1])
    return (end_year - start_year) * 12 + end_month - start_month + 1


def _parse_month(month: str) -> tuple[int, int]:
    year_text, month_text = month.split("-", 1)
    year = int(year_text)
    month_number = int(month_text)
    if not 1 <= month_number <= 12:
        raise ValueError(f"invalid month:{month}")
    return year, month_number


def _format_month(year: int, month: int) -> str:
    return f"{year:04d}-{month:02d}"


def _next_month(year: int, month: int) -> tuple[int, int]:
    month += 1
    if month == 13:
        return year + 1, 1
    return year, month
