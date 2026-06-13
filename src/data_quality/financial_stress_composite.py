from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from data_quality import historical_percentile_metrics


FINANCIAL_STRESS_BOUNDARY = (
    "Financial stress score is a transparent pressure temperature, not crash "
    "probability. It does not produce buy/sell/hedge instructions. VIX alone "
    "is not systemic stress. Equity drawdown alone is not systemic stress. "
    "Percentile bands describe local historical rarity, not forecast probability. "
    "VIX percentile alone is not systemic stress. Equity drawdown percentile "
    "alone is not systemic stress. Credit percentile context is auxiliary unless "
    "core credit evidence is available. "
    "Proxy inputs are not official market breadth or official funding stress. "
    "Missing earnings, true breadth, valuation, and liquidity data limit crisis "
    "confirmation."
)

INTERPRETATION_HINT = (
    "Derived from local dashboard evidence only; use as risk review context, "
    "not as a trading signal, crash probability, or recession probability."
)

GROUP_WEIGHTS = {
    "credit_conditions": 40,
    "rates_real_yield": 20,
    "equity_damage_cross_asset": 25,
    "labor_deterioration": 15,
}

INPUT_GROUPS = {
    "credit_conditions": (
        "high_yield_spread",
        "investment_grade_spread",
        "vix",
        "credit_stress_status",
    ),
    "rates_real_yield": (
        "dgs30",
        "dgs10_dgs2_curve_slope",
        "dgs30_dgs10_curve_slope",
        "dfii10",
        "real_yield_pressure_status",
    ),
    "equity_damage_cross_asset": (
        "sp500_drawdown_3m",
        "sp500_drawdown_6m",
        "nasdaq100_drawdown_3m",
        "nasdaq100_drawdown_6m",
        "hyg_vs_lqd_30d",
        "hyg_vs_lqd_60d",
        "tlt_proxy_30d_return",
        "tlt_vs_shy_30d",
    ),
    "labor_deterioration": (
        "labor_deterioration_status",
        "sahm_rule_proxy_status",
        "initial_claims_4w_avg",
        "continuing_claims_4w_avg",
        "unemployment_rate_12m_low_gap",
        "nonfarm_payrolls",
    ),
}

CORE_CREDIT_INPUTS = ("high_yield_spread", "investment_grade_spread")
D13_PERCENTILE_KEYS = (
    "vix_percentile",
    "vix_robust_zscore",
    "dgs30_percentile",
    "dgs30_robust_zscore",
    "dfii10_percentile",
    "dfii10_robust_zscore",
    "sp500_drawdown_3m_percentile",
    "sp500_drawdown_3m_robust_zscore",
    "nasdaq100_drawdown_3m_percentile",
    "nasdaq100_drawdown_3m_robust_zscore",
    "initial_claims_4w_avg_percentile",
    "initial_claims_4w_avg_robust_zscore",
    "continuing_claims_4w_avg_percentile",
    "continuing_claims_4w_avg_robust_zscore",
    "high_yield_spread_percentile",
    "investment_grade_spread_percentile",
)
PERCENTILE_GROUPS = {
    "credit": ("high_yield_spread_percentile", "investment_grade_spread_percentile"),
    "rates": ("dgs30_percentile", "dgs30_robust_zscore", "dfii10_percentile", "dfii10_robust_zscore"),
    "equity": (
        "vix_percentile",
        "vix_robust_zscore",
        "sp500_drawdown_3m_percentile",
        "sp500_drawdown_3m_robust_zscore",
        "nasdaq100_drawdown_3m_percentile",
        "nasdaq100_drawdown_3m_robust_zscore",
    ),
    "labor": (
        "initial_claims_4w_avg_percentile",
        "initial_claims_4w_avg_robust_zscore",
        "continuing_claims_4w_avg_percentile",
        "continuing_claims_4w_avg_robust_zscore",
    ),
}
BAD_STATUSES = {
    "missing",
    "research_needed",
    "insufficient_history",
    "insufficient_evidence",
    "not_available",
    "stale",
}
BAD_FRESHNESS = {"missing", "unknown", "stale", "insufficient_history"}
STATUS_SCORES = {
    "ok": 10.0,
    "watch": 45.0,
    "pressure": 75.0,
    "stress": 95.0,
}
STATUS_THRESHOLDS = (
    (70.0, "stress"),
    (45.0, "pressure"),
    (25.0, "watch"),
    (0.0, "ok"),
)


def build_financial_stress_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    row_by_key = {str(row.get("metric_key")): row for row in rows}
    evidence_index = historical_percentile_metrics.build_evidence_index(rows)
    generated_at = datetime.now(timezone.utc).isoformat()
    input_evidence = [
        _input_snapshot(row_by_key[key])
        for group_keys in INPUT_GROUPS.values()
        for key in group_keys
        if key in row_by_key
    ]
    missing_inputs = [
        key
        for group_keys in INPUT_GROUPS.values()
        for key in group_keys
        if key not in row_by_key or not _usable(row_by_key[key])
    ]
    component_contributions = {
        group: _component(group, keys, row_by_key)
        for group, keys in INPUT_GROUPS.items()
    }
    percentile_context = _percentile_context(evidence_index)
    component_contributions_with_context = {
        **component_contributions,
        "percentile_context": percentile_context,
    }
    has_contributions = any(
        component["inputs"] for component in component_contributions.values()
    )
    core_credit_missing = [key for key in CORE_CREDIT_INPUTS if key in missing_inputs]
    score: float | None = None
    status = "missing"
    missing_reason: str | None = None
    if not input_evidence:
        missing_reason = "financial_stress_inputs_missing"
    elif core_credit_missing:
        status = "insufficient_evidence"
        missing_reason = "core_credit_inputs_missing"
    elif not has_contributions:
        missing_reason = "financial_stress_inputs_unusable"
    else:
        score = round(
            sum(
                component["score"] * component["weight"] / 100.0
                for component in component_contributions.values()
            ),
            2,
        )
        status = _status_for_score(score)
        score, status = _apply_conclusion_gates(
            score,
            status,
            component_contributions,
        )

    dominant = _dominant_pressure_source(component_contributions)
    observation_date = _latest_text(
        row.get("observation_date")
        for row in row_by_key.values()
        if isinstance(row.get("observation_date"), str)
    )
    freshness_status = "historical" if has_contributions else "missing"
    ai_context_allowed = status not in {"missing", "insufficient_evidence"}
    score_text = "--" if score is None else f"{score:.2f}/100"
    missing_text = "none" if not missing_inputs else ", ".join(missing_inputs)
    contribution_text = _contribution_text(component_contributions)
    percentile_context_text = _percentile_context_text(percentile_context)

    common = {
        "source": "local_dashboard_evidence",
        "source_badge": "derived",
        "source_series": None,
        "observation_date": observation_date,
        "generated_at": generated_at,
        "freshness_status": freshness_status,
        "missing_reason": missing_reason,
        "interpretation_hint": INTERPRETATION_HINT,
        "ai_context_allowed": ai_context_allowed,
        "input_evidence": input_evidence,
        "component_contributions": component_contributions_with_context,
        "missing_inputs": missing_inputs,
        "interpretation_boundary": FINANCIAL_STRESS_BOUNDARY,
    }
    return [
        {
            **common,
            "metric_key": "financial_stress_score",
            "display_name": "Financial stress score",
            "value": score,
            "value_text": score_text,
            "unit": "score_0_100",
            "status": status,
        },
        {
            **common,
            "metric_key": "financial_stress_status",
            "display_name": "Financial stress status",
            "value": status,
            "value_text": status,
            "unit": "text",
            "status": status,
        },
        {
            **common,
            "metric_key": "financial_stress_dominant_pressure_source",
            "display_name": "Financial stress dominant pressure source",
            "value": dominant,
            "value_text": dominant or "--",
            "unit": "text",
            "status": status,
        },
        {
            **common,
            "metric_key": "financial_stress_component_contributions",
            "display_name": "Financial stress component contributions",
            "value": contribution_text,
            "value_text": contribution_text,
            "unit": "json",
            "status": status,
        },
        {
            **common,
            "metric_key": "financial_stress_missing_inputs",
            "display_name": "Financial stress missing inputs",
            "value": missing_text,
            "value_text": missing_text,
            "unit": "text",
            "status": "ok" if not missing_inputs else status,
        },
        {
            **common,
            "metric_key": "financial_stress_interpretation_boundary",
            "display_name": "Financial stress interpretation boundary",
            "value": FINANCIAL_STRESS_BOUNDARY,
            "value_text": FINANCIAL_STRESS_BOUNDARY,
            "unit": "text",
            "status": status,
        },
        {
            **common,
            "metric_key": "financial_stress_percentile_context",
            "display_name": "Financial stress percentile context",
            "value": percentile_context_text,
            "value_text": percentile_context_text,
            "unit": "json",
            "status": "ok" if percentile_context["available_count"] else "watch",
        },
    ]


def _component(
    group: str,
    keys: tuple[str, ...],
    row_by_key: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    inputs: list[dict[str, Any]] = []
    scores: list[float] = []
    for key in keys:
        row = row_by_key.get(key)
        if row is None or not _usable(row):
            continue
        pressure_score = _input_pressure_score(key, row)
        snapshot = _input_snapshot(row)
        snapshot["pressure_score"] = pressure_score
        inputs.append(snapshot)
        scores.append(pressure_score)
    component_score = round(sum(scores) / len(scores), 2) if scores else 0.0
    return {
        "score": component_score,
        "weight": GROUP_WEIGHTS[group],
        "inputs": inputs,
    }


def _usable(row: dict[str, Any]) -> bool:
    if row.get("status") in BAD_STATUSES:
        return False
    if row.get("freshness_status") in BAD_FRESHNESS:
        return False
    if row.get("source_badge") in {"missing", "research_needed", "search-derived"}:
        return False
    if row.get("ai_context_allowed") is False:
        return False
    value = row.get("value")
    if value is None or value == "":
        return False
    return True


def _input_pressure_score(metric_key: str, row: dict[str, Any]) -> float:
    status_score = STATUS_SCORES.get(str(row.get("status")), 10.0)
    value_status_score = STATUS_SCORES.get(str(row.get("value")).lower())
    if value_status_score is not None and metric_key.endswith("_status"):
        return value_status_score
    value = _to_float(row.get("value"))
    if value is None:
        return status_score
    if metric_key == "high_yield_spread":
        return _threshold_score(value, ((6.0, 100), (4.5, 75), (3.5, 50), (0, 10)))
    if metric_key == "investment_grade_spread":
        return _threshold_score(value, ((2.0, 100), (1.5, 75), (1.0, 50), (0, 10)))
    if metric_key == "vix":
        return _threshold_score(value, ((35.0, 100), (25.0, 65), (20.0, 40), (0, 10)))
    if metric_key in {"dgs30", "dfii10"}:
        return _threshold_score(value, ((5.0, 75), (4.5, 45), (0, 10))) if metric_key == "dgs30" else _threshold_score(value, ((2.5, 75), (2.0, 50), (0, 10)))
    if metric_key == "dgs10_dgs2_curve_slope":
        return _inversion_score(value, severe=-0.5, watch=0.0)
    if metric_key == "dgs30_dgs10_curve_slope":
        return _inversion_score(value, severe=-0.25, watch=0.0)
    if metric_key in {
        "sp500_drawdown_3m",
        "sp500_drawdown_6m",
        "nasdaq100_drawdown_3m",
        "nasdaq100_drawdown_6m",
    }:
        return _drawdown_score(value)
    if metric_key in {"hyg_vs_lqd_30d", "hyg_vs_lqd_60d", "tlt_vs_shy_30d"}:
        return _underperformance_score(value)
    if metric_key == "tlt_proxy_30d_return":
        return _drawdown_score(value, severe=-12.0, pressure=-8.0, watch=-4.0)
    if metric_key == "unemployment_rate_12m_low_gap":
        return _threshold_score(value, ((0.5, 75), (0.3, 50), (0, 10)))
    if metric_key in {"initial_claims_4w_avg", "continuing_claims_4w_avg", "nonfarm_payrolls"}:
        return max(10.0, min(status_score, 45.0))
    return status_score


def _threshold_score(value: float, thresholds: tuple[tuple[float, float], ...]) -> float:
    for threshold, score in thresholds:
        if value >= threshold:
            return float(score)
    return 0.0


def _inversion_score(value: float, *, severe: float, watch: float) -> float:
    if value <= severe:
        return 75.0
    if value < watch:
        return 45.0
    return 10.0


def _drawdown_score(
    value: float,
    *,
    severe: float = -20.0,
    pressure: float = -12.0,
    watch: float = -7.0,
) -> float:
    if value <= severe:
        return 100.0
    if value <= pressure:
        return 75.0
    if value <= watch:
        return 45.0
    return 10.0


def _underperformance_score(value: float) -> float:
    if value <= -5.0:
        return 80.0
    if value <= -2.0:
        return 50.0
    return 10.0


def _status_for_score(score: float) -> str:
    for threshold, status in STATUS_THRESHOLDS:
        if score >= threshold:
            return status
    return "ok"


def _apply_conclusion_gates(
    score: float,
    status: str,
    contributions: dict[str, dict[str, Any]],
) -> tuple[float, str]:
    high_inputs = [
        input_row
        for component in contributions.values()
        for input_row in component["inputs"]
        if input_row.get("pressure_score", 0) >= 45
    ]
    high_keys = {str(input_row.get("metric_key")) for input_row in high_inputs}
    high_groups = {
        group
        for group, component in contributions.items()
        if any(input_row.get("pressure_score", 0) >= 45 for input_row in component["inputs"])
    }
    if high_keys and high_keys <= {"vix"}:
        return min(score, 44.0), "watch"
    if high_groups and high_groups <= {"equity_damage_cross_asset"} and status == "stress":
        return min(score, 69.0), "pressure"
    if status == "stress" and not any(
        input_row.get("source_badge") == "official" for input_row in high_inputs
    ):
        return min(score, 69.0), "pressure"
    return score, status


def _dominant_pressure_source(contributions: dict[str, dict[str, Any]]) -> str | None:
    weighted = {
        group: component["score"] * component["weight"] / 100.0
        for group, component in contributions.items()
        if component["inputs"]
    }
    if not weighted:
        return None
    return max(weighted, key=lambda key: weighted[key])


def _input_snapshot(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "module": row.get("module"),
        "metric_key": row.get("metric_key"),
        "value": row.get("value"),
        "value_text": row.get("value_text"),
        "status": row.get("status"),
        "source": row.get("source"),
        "source_badge": row.get("source_badge"),
        "source_series": row.get("source_series"),
        "observation_date": row.get("observation_date"),
        "generated_at": row.get("generated_at"),
        "freshness_status": row.get("freshness_status"),
    }


def _contribution_text(contributions: dict[str, dict[str, Any]]) -> str:
    return "; ".join(
        f"{group}={component['score']:.2f}x{component['weight']}%"
        for group, component in contributions.items()
    )


def _percentile_context(
    evidence_index: historical_percentile_metrics.EvidenceIndex,
) -> dict[str, Any]:
    available = evidence_index.available_d13_context(D13_PERCENTILE_KEYS)
    missing = evidence_index.missing_d13_context(D13_PERCENTILE_KEYS)
    by_group: dict[str, dict[str, Any]] = {}
    for group, keys in PERCENTILE_GROUPS.items():
        group_available = evidence_index.available_d13_context(keys)
        group_missing = evidence_index.missing_d13_context(keys)
        by_group[group] = {
            "available_count": len(group_available),
            "missing_count": len(group_missing),
            "available_metric_keys": [item["metric_key"] for item in group_available],
            "missing_metric_keys": [item["metric_key"] for item in group_missing],
        }
    return {
        "available_count": len(available),
        "missing_count": len(missing),
        "available": available,
        "missing": missing,
        "by_group": by_group,
        "normalization_boundary": (
            "Percentile bands describe local historical rarity, not forecast probability. "
            "VIX percentile alone is not systemic stress. Equity drawdown percentile alone "
            "is not systemic stress. Credit percentile context is auxiliary unless core "
            "credit evidence is available. Financial stress score remains a pressure "
            "temperature, not crash probability."
        ),
    }


def _percentile_context_text(context: dict[str, Any]) -> str:
    return (
        f"{context['available_count']} D13 auxiliary percentile rows available; "
        f"{context['missing_count']} missing or blocked"
    )


def _latest_text(values: Any) -> str | None:
    present = sorted(value for value in values if isinstance(value, str) and value)
    return present[-1] if present else None


def _to_float(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return float(str(value).strip())
    except (TypeError, ValueError):
        return None
