from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


MODULE_KEY = "macro_regime_review"
MODEL_VERSION = "macro_regime_review_v0"
FORMULA_VERSION = "d15_rules_v0"
BOUNDARY = (
    "Macro regime review is a current evidence review derived from current "
    "sanitized evidence rows, not a classifier, prediction model, downside-event "
    "model, business-cycle call, or market direction forecast. It is for "
    "reference review only and does not produce target allocation or expected "
    "return."
)
BAD_STATUSES = {
    "missing",
    "stale",
    "research_needed",
    "insufficient_history",
    "insufficient_evidence",
    "not_available",
}
BAD_FRESHNESS = {"unknown", "missing", "stale", "insufficient_history"}
BAD_SOURCE_BADGES = {"missing", "research_needed", "search-derived"}
AUXILIARY_SOURCE_BADGES = {"proxy", "unofficial_fallback"}
PRESSURE_STATUSES = {"watch", "pressure", "stress"}
HIGH_PRESSURE_STATUSES = {"pressure", "stress"}
CORE_GROUPS = (
    "credit",
    "liquidity_funding",
    "rates_real_yield",
    "inflation_energy",
    "labor_growth",
)


def build_macro_regime_review_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_key = {str(row.get("metric_key")): row for row in rows}
    groups = _group_evidence(by_key)
    valid_core_count = sum(1 for key in CORE_GROUPS if groups[key]["valid_count"] > 0)
    pressure_groups = [
        key
        for key in CORE_GROUPS
        if groups[key]["pressure_level"] in HIGH_PRESSURE_STATUSES
    ]
    watch_groups = [
        key
        for key in CORE_GROUPS
        if groups[key]["pressure_level"] in PRESSURE_STATUSES
    ]
    missing_inputs = sorted(
        {
            item
            for group in groups.values()
            for item in group["missing_inputs"]
        }
    )
    blocked_inputs = sorted(
        {
            item
            for group in groups.values()
            for item in group["blocked_inputs"]
        }
    )

    label = _label(groups, valid_core_count, pressure_groups, watch_groups)
    support_band = _support_band(label, groups, pressure_groups, watch_groups)
    evidence_quality_band = _evidence_quality_band(valid_core_count, blocked_inputs)
    conflict_band = _conflict_band(groups, pressure_groups, watch_groups)
    ranking = _primary_pressure_ranking(groups)
    supporting = _supporting_evidence(groups, ranking)
    conflicting = _conflicting_evidence(groups)
    as_of_date = _latest_observation_date(groups)
    status = "insufficient_evidence" if label == "insufficient_evidence" else "ok"
    ai_context_allowed = label != "insufficient_evidence"
    component_contributions = {
        "group_bands": {
            key: {
                "pressure_level": value["pressure_level"],
                "evidence_count_band": _count_band(value["valid_count"]),
                "auxiliary_only": value["auxiliary_only"],
                "hard_gate": value["hard_gate"],
            }
            for key, value in groups.items()
        },
        "hard_gates": {
            "vix_alone_cannot_trigger_credit_stress": True,
            "equity_drawdown_alone_cannot_trigger_stress": True,
            "d14_alone_cannot_trigger_liquidity_or_systemic_regime": True,
            "percentile_only_cannot_determine_regime": True,
            "proxy_only_cannot_determine_pressure_high_label": True,
            "missing_stale_blocked_research_needed_insufficient_history_cannot_support_label": True,
            "valuation_earnings_true_breadth_gaps_remain_explicit": True,
            "dgs30_breakout_alone_cannot_trigger_high_rates_pressure": True,
            "oil_or_breakeven_alone_cannot_trigger_inflation_energy_pressure": True,
            "labor_watch_alone_cannot_trigger_recession_like_interpretation": True,
        },
    }
    base = {
        "unit": None,
        "source": "local_rules",
        "source_badge": "derived",
        "source_series": "D15_RULES_V0",
        "observation_date": as_of_date,
        "generated_at": _utc_now(),
        "freshness_status": "historical",
        "missing_reason": None if ai_context_allowed else "core_regime_evidence_insufficient",
        "interpretation_hint": BOUNDARY,
        "interpretation_boundary": BOUNDARY,
        "ai_context_allowed": ai_context_allowed,
        "input_evidence": _input_evidence(groups),
        "component_contributions": component_contributions,
        "missing_inputs": missing_inputs,
        "ai_context_tier": "model_output",
        "trigger_eligibility": "reference_review_only",
    }
    values = {
        "macro_regime_label": ("Macro regime label", label),
        "support_band": ("Macro regime support band", support_band),
        "evidence_quality_band": ("Macro regime evidence quality band", evidence_quality_band),
        "conflict_band": ("Macro regime conflict band", conflict_band),
        "primary_pressure_ranking": ("Primary pressure ranking", ", ".join(ranking) or "none"),
        "supporting_evidence": ("Supporting evidence", supporting or "none"),
        "conflicting_evidence": ("Conflicting evidence", conflicting or "none"),
        "missing_inputs": ("Macro regime missing inputs", ", ".join(missing_inputs) or "none"),
        "blocked_inputs": ("Macro regime blocked inputs", ", ".join(blocked_inputs) or "none"),
        "interpretation_boundary": ("Macro regime interpretation boundary", BOUNDARY),
        "model_version": ("Macro regime model version", MODEL_VERSION),
        "formula_version": ("Macro regime formula version", FORMULA_VERSION),
        "as_of_date": ("Macro regime as-of date", as_of_date or "not available"),
    }
    return [
        {
            **base,
            "metric_key": metric_key,
            "display_name": display_name,
            "value": value,
            "value_text": str(value),
            "status": status,
        }
        for metric_key, (display_name, value) in values.items()
    ]


def _group_evidence(by_key: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {
        "credit": _credit_group(by_key),
        "liquidity_funding": _liquidity_group(by_key),
        "rates_real_yield": _rates_group(by_key),
        "inflation_energy": _inflation_group(by_key),
        "labor_growth": _labor_group(by_key),
        "equity_structure": _equity_group(by_key),
        "valuation_earnings_breadth": _valuation_group(by_key),
    }


def _credit_group(by_key: dict[str, dict[str, Any]]) -> dict[str, Any]:
    core = _valid_rows(by_key, ("high_yield_spread", "investment_grade_spread"))
    status_row = _valid_row(by_key.get("credit_stress_status"))
    vix = _valid_row(by_key.get("vix"))
    pressure = _status_value(status_row)
    high = bool(core) and pressure in HIGH_PRESSURE_STATUSES
    watch = bool(core) and pressure in PRESSURE_STATUSES
    level = pressure if high else ("watch" if watch else "ok" if core else "missing")
    return _group(
        "credit",
        [*core, status_row, vix],
        level,
        missing=["high_yield_spread_or_investment_grade_spread"] if not core else [],
        hard_gate="credit stress requires HY or IG current-level core evidence; VIX, HYG-LQD, and equity drawdown cannot trigger it alone.",
    )


def _liquidity_group(by_key: dict[str, dict[str, Any]]) -> dict[str, Any]:
    keys = (
        "policy_plumbing_status",
        "short_term_funding_pressure_status",
        "official_stress_reference_status",
        "liquidity_funding_stress_status",
    )
    rows = _valid_rows(by_key, keys)
    pressure_subgroups = [
        row
        for row in rows
        if row.get("metric_key") != "liquidity_funding_stress_status"
        and _status_value(row) in HIGH_PRESSURE_STATUSES
    ]
    status_row = _valid_row(by_key.get("liquidity_funding_stress_status"))
    status_value = _status_value(status_row)
    if len(pressure_subgroups) >= 2 and status_value in HIGH_PRESSURE_STATUSES:
        level = status_value
    elif status_value in PRESSURE_STATUSES and len(pressure_subgroups) >= 1:
        level = "watch"
    else:
        level = "ok" if rows else "missing"
    return _group(
        "liquidity_funding",
        rows,
        level,
        missing=["two_funding_sub_evidence_groups"] if len(pressure_subgroups) < 2 else [],
        hard_gate="D14 alone cannot trigger liquidity or systemic regime; at least two funding sub-evidence groups are required.",
    )


def _rates_group(by_key: dict[str, dict[str, Any]]) -> dict[str, Any]:
    core = _valid_rows(by_key, ("dgs10", "dgs30", "dfii10", "t10yie"))
    status_row = _valid_row(by_key.get("real_yield_pressure_status"))
    pressure = _status_value(status_row)
    if len(core) >= 2 and pressure in HIGH_PRESSURE_STATUSES:
        level = pressure
    elif len(core) >= 2 and pressure in PRESSURE_STATUSES:
        level = "watch"
    else:
        level = "ok" if len(core) >= 2 else "missing"
    return _group(
        "rates_real_yield",
        [*core, status_row],
        level,
        missing=["two_valid_rates_or_real_yield_core_inputs"] if len(core) < 2 else [],
        hard_gate="Rates pressure requires at least two valid rates/real-yield core inputs; DGS30 breakout alone cannot trigger high rates pressure.",
    )


def _inflation_group(by_key: dict[str, dict[str, Any]]) -> dict[str, Any]:
    core = _valid_rows(
        by_key,
        ("core_cpi_yoy", "core_pce_yoy", "ppiaco_yoy", "ppi_final_demand_yoy"),
    )
    oil = _valid_rows(by_key, ("wti_30d_change", "brent_30d_change", "t10yie"))
    pressure = any(_status_value(row) in HIGH_PRESSURE_STATUSES for row in core)
    watch = any(_status_value(row) in PRESSURE_STATUSES for row in core)
    level = "pressure" if pressure else "watch" if watch else "ok" if core else "missing"
    return _group(
        "inflation_energy",
        [*core, *oil],
        level,
        missing=["core_inflation_input"] if not core else [],
        hard_gate="Inflation/energy pressure requires at least one core inflation input; oil or breakeven alone cannot trigger it.",
    )


def _labor_group(by_key: dict[str, dict[str, Any]]) -> dict[str, Any]:
    claims = _valid_rows(by_key, ("initial_jobless_claims", "initial_claims_4w_avg", "continuing_claims", "continuing_claims_4w_avg"))
    labor = _valid_rows(by_key, ("unemployment_rate", "unemployment_rate_3m_avg", "nonfarm_payrolls", "labor_deterioration_status"))
    status_row = _valid_row(by_key.get("labor_deterioration_status"))
    pressure = _status_value(status_row)
    if claims and labor and pressure in HIGH_PRESSURE_STATUSES:
        level = pressure
    elif claims and labor and pressure in PRESSURE_STATUSES:
        level = "watch"
    else:
        level = "ok" if claims and labor else "missing"
    return _group(
        "labor_growth",
        [*claims, *labor, status_row],
        level,
        missing=["claims_plus_unemployment_or_payrolls_style_evidence"] if not (claims and labor) else [],
        hard_gate="Labor watch alone cannot trigger recession-like interpretation or downturn odds.",
    )


def _equity_group(by_key: dict[str, dict[str, Any]]) -> dict[str, Any]:
    rows = _valid_rows(by_key, ("sp500_drawdown_3m", "nasdaq100_drawdown_3m", "sp500_30d_return", "nasdaq100_30d_return"))
    return _group(
        "equity_structure",
        rows,
        "watch" if rows else "missing",
        missing=["true_breadth_and_constituent_concentration"] if rows else ["equity_structure_evidence"],
        hard_gate="Equity drawdown and proxy breadth cannot trigger stress regime alone.",
        auxiliary_only=True,
    )


def _valuation_group(by_key: dict[str, dict[str, Any]]) -> dict[str, Any]:
    rows = _valid_rows(by_key, ("sp500_trailing_pe", "sp500_forward_pe", "earnings_revision", "eps_growth"))
    return _group(
        "valuation_earnings_breadth",
        rows,
        "missing",
        missing=["valuation", "earnings", "true_breadth"],
        hard_gate="Valuation, earnings, and true breadth are currently missing constraints, not strong support.",
        auxiliary_only=True,
    )


def _label(
    groups: dict[str, dict[str, Any]],
    valid_core_count: int,
    pressure_groups: list[str],
    watch_groups: list[str],
) -> str:
    if valid_core_count < 3:
        return "insufficient_evidence"
    if _stagflation(groups):
        return "stagflation_pressure"
    if groups["credit"]["pressure_level"] in HIGH_PRESSURE_STATUSES:
        return "credit_stress"
    if groups["liquidity_funding"]["pressure_level"] in HIGH_PRESSURE_STATUSES:
        return "liquidity_funding_pressure"
    if groups["rates_real_yield"]["pressure_level"] in HIGH_PRESSURE_STATUSES:
        return "rates_pressure"
    if groups["inflation_energy"]["pressure_level"] in HIGH_PRESSURE_STATUSES:
        return "inflation_energy_pressure"
    if groups["labor_growth"]["pressure_level"] in PRESSURE_STATUSES:
        return "growth_slowdown_watch"
    if len(watch_groups) >= 2:
        return "mixed_or_transition"
    if valid_core_count >= 4 and not pressure_groups and not watch_groups:
        return "low_stress_liquidity_support"
    return "mixed_or_transition"


def _stagflation(groups: dict[str, dict[str, Any]]) -> bool:
    return (
        groups["inflation_energy"]["pressure_level"] in HIGH_PRESSURE_STATUSES
        and groups["labor_growth"]["pressure_level"] in PRESSURE_STATUSES
        and groups["rates_real_yield"]["valid_count"] >= 2
    )


def _support_band(
    label: str,
    groups: dict[str, dict[str, Any]],
    pressure_groups: list[str],
    watch_groups: list[str],
) -> str:
    if label == "insufficient_evidence":
        return "unsupported"
    if label == "low_stress_liquidity_support":
        return "moderate" if sum(groups[key]["valid_count"] > 0 for key in CORE_GROUPS) >= 4 else "weak"
    if len(pressure_groups) >= 2:
        return "strong"
    if pressure_groups or len(watch_groups) >= 2:
        return "moderate"
    return "weak"


def _evidence_quality_band(valid_core_count: int, blocked_inputs: list[str]) -> str:
    if valid_core_count < 3:
        return "insufficient"
    if valid_core_count >= 5 and not blocked_inputs:
        return "high"
    if valid_core_count >= 4:
        return "medium"
    return "low"


def _conflict_band(
    groups: dict[str, dict[str, Any]],
    pressure_groups: list[str],
    watch_groups: list[str],
) -> str:
    low_groups = [
        key
        for key in CORE_GROUPS
        if groups[key]["valid_count"] > 0 and groups[key]["pressure_level"] == "ok"
    ]
    elevated = len(set(pressure_groups).union(watch_groups))
    if elevated >= 2 and low_groups:
        return "high"
    if elevated and low_groups:
        return "moderate"
    return "low"


def _primary_pressure_ranking(groups: dict[str, dict[str, Any]]) -> list[str]:
    order = {"stress": 3, "pressure": 2, "watch": 1, "ok": 0, "missing": -1}
    ranked = sorted(
        CORE_GROUPS,
        key=lambda key: (order.get(groups[key]["pressure_level"], -1), groups[key]["valid_count"]),
        reverse=True,
    )
    return [
        key
        for key in ranked
        if groups[key]["pressure_level"] in PRESSURE_STATUSES
    ]


def _supporting_evidence(groups: dict[str, dict[str, Any]], ranking: list[str]) -> str:
    parts = []
    for key in ranking[:4]:
        metric_keys = [
            row.get("metric_key")
            for row in groups[key]["rows"]
            if isinstance(row, dict) and row.get("metric_key")
        ][:4]
        parts.append(f"{key}: {groups[key]['pressure_level']} via {', '.join(metric_keys)}")
    return "; ".join(parts)


def _conflicting_evidence(groups: dict[str, dict[str, Any]]) -> str:
    low = [key for key in CORE_GROUPS if groups[key]["pressure_level"] == "ok"]
    elevated = [
        key for key in CORE_GROUPS if groups[key]["pressure_level"] in PRESSURE_STATUSES
    ]
    if low and elevated:
        return f"elevated={', '.join(elevated)}; low={', '.join(low)}"
    return ""


def _count_band(count: int) -> str:
    if count <= 0:
        return "none"
    if count == 1:
        return "single"
    if count <= 3:
        return "several"
    return "broad"


def _group(
    name: str,
    rows: list[dict[str, Any] | None],
    pressure_level: str,
    *,
    missing: list[str],
    hard_gate: str,
    auxiliary_only: bool = False,
) -> dict[str, Any]:
    valid = [row for row in rows if isinstance(row, dict) and _supports_label(row)]
    blocked = [
        str(row.get("metric_key"))
        for row in rows
        if isinstance(row, dict) and not _supports_label(row)
    ]
    if auxiliary_only and pressure_level in HIGH_PRESSURE_STATUSES:
        pressure_level = "watch"
    return {
        "name": name,
        "rows": valid,
        "valid_count": len(valid),
        "pressure_level": pressure_level if valid else "missing",
        "missing_inputs": missing,
        "blocked_inputs": blocked,
        "hard_gate": hard_gate,
        "auxiliary_only": auxiliary_only or all(_auxiliary(row) for row in valid) if valid else auxiliary_only,
    }


def _valid_rows(
    by_key: dict[str, dict[str, Any]],
    keys: tuple[str, ...],
) -> list[dict[str, Any]]:
    return [row for row in (_valid_row(by_key.get(key)) for key in keys) if row]


def _valid_row(row: dict[str, Any] | None) -> dict[str, Any] | None:
    return row if isinstance(row, dict) and _supports_label(row) else None


def _supports_label(row: dict[str, Any]) -> bool:
    if row.get("status") in BAD_STATUSES:
        return False
    if row.get("freshness_status") in BAD_FRESHNESS:
        return False
    if row.get("source_badge") in BAD_SOURCE_BADGES:
        return False
    if row.get("ai_context_allowed") is False:
        return False
    if row.get("value") in (None, ""):
        return False
    return True


def _auxiliary(row: dict[str, Any]) -> bool:
    return row.get("source_badge") in AUXILIARY_SOURCE_BADGES or row.get("trigger_eligibility") in {
        "auxiliary_only",
        "proxy_auxiliary_only",
        "context_only",
    }


def _status_value(row: dict[str, Any] | None) -> str | None:
    if not row:
        return None
    value = row.get("value")
    if isinstance(value, str) and value in {"ok", "watch", "pressure", "stress"}:
        return value
    status = row.get("status")
    return status if status in {"ok", "watch", "pressure", "stress"} else None


def _input_evidence(groups: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for group_name, group in groups.items():
        for row in group["rows"]:
            result.append(
                {
                    "group": group_name,
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
            )
    return result


def _latest_observation_date(groups: dict[str, dict[str, Any]]) -> str | None:
    dates = [
        str(row.get("observation_date"))
        for group in groups.values()
        for row in group["rows"]
        if row.get("observation_date")
    ]
    return max(dates) if dates else None


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()
