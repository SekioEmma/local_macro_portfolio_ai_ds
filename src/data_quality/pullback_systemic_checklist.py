from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from data_quality import historical_percentile_metrics


PULLBACK_BOUNDARY = (
    "This checklist is not crash probability. It does not predict market bottom "
    "or top. It does not produce buy/sell/hedge instructions. Equity drawdown "
    "alone is not systemic risk. VIX alone is not systemic risk. Percentile "
    "evidence is auxiliary and cannot alone trigger systemic_risk_review. "
    "Equity drawdown percentile alone is not systemic risk. VIX percentile alone "
    "is not systemic risk. Proxy evidence is not true breadth or official funding "
    "stress. Liquidity/funding remains a critical missing input until D14 is "
    "implemented. Missing earnings, valuation, liquidity, and true breadth limit "
    "crisis confirmation."
)

INTERPRETATION_HINT = (
    "Derived from local dashboard evidence as a transparent risk review "
    "checklist for separating ordinary pullback, valuation drawdown, macro "
    "pressure, credit warning, and systemic risk review. It is not probability, "
    "recession prediction, or trading advice."
)

INPUT_KEYS = (
    "financial_stress_score",
    "financial_stress_status",
    "financial_stress_component_contributions",
    "high_yield_spread",
    "investment_grade_spread",
    "vix",
    "credit_stress_status",
    "sp500_drawdown_3m",
    "sp500_drawdown_6m",
    "nasdaq100_drawdown_3m",
    "nasdaq100_drawdown_6m",
    "dgs30",
    "dfii10",
    "dgs10_dgs2_curve_slope",
    "dgs30_dgs10_curve_slope",
    "real_yield_pressure_status",
    "core_cpi_yoy",
    "core_pce_yoy",
    "ppi_final_demand_yoy",
    "hyg_vs_lqd_30d",
    "hyg_vs_lqd_60d",
    "labor_deterioration_status",
    "sahm_rule_proxy_status",
    "initial_claims_4w_avg",
    "continuing_claims_4w_avg",
    "unemployment_rate_12m_low_gap",
)

CORE_CREDIT_INPUTS = ("high_yield_spread", "investment_grade_spread")
D13_PULLBACK_KEYS = (
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
ITEM_PERCENTILE_KEYS = {
    "equity_damage": (
        "sp500_drawdown_3m_percentile",
        "sp500_drawdown_3m_robust_zscore",
        "nasdaq100_drawdown_3m_percentile",
        "nasdaq100_drawdown_3m_robust_zscore",
    ),
    "credit_spread_confirmation": (
        "high_yield_spread_percentile",
        "investment_grade_spread_percentile",
    ),
    "volatility_confirmation": ("vix_percentile", "vix_robust_zscore"),
    "rates_real_yield_pressure": (
        "dgs30_percentile",
        "dgs30_robust_zscore",
        "dfii10_percentile",
        "dfii10_robust_zscore",
    ),
    "labor_deterioration": (
        "initial_claims_4w_avg_percentile",
        "initial_claims_4w_avg_robust_zscore",
        "continuing_claims_4w_avg_percentile",
        "continuing_claims_4w_avg_robust_zscore",
    ),
}
ALWAYS_MISSING_CRITICAL_INPUTS = (
    "valuation",
    "earnings",
    "true_breadth",
    "liquidity",
)
BAD_STATUSES = {
    "missing",
    "research_needed",
    "insufficient_history",
    "insufficient_evidence",
    "not_available",
    "stale",
}
BAD_FRESHNESS = {"missing", "unknown", "stale", "insufficient_history"}
STATUS_SEVERITY = {
    "ok": "none",
    "watch": "watch",
    "pressure": "pressure",
    "stress": "stress",
}
CLASSIFICATION_STATUS = {
    "ordinary_pullback": "ok",
    "valuation_drawdown": "watch",
    "macro_pressure": "pressure",
    "credit_warning": "pressure",
    "systemic_risk_review": "stress",
    "insufficient_evidence": "insufficient_evidence",
}


def build_pullback_checklist_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    row_by_key = {str(row.get("metric_key")): row for row in rows}
    evidence_index = historical_percentile_metrics.build_evidence_index(rows)
    generated_at = datetime.now(timezone.utc).isoformat()
    input_evidence = [
        _input_snapshot(row_by_key[key]) for key in INPUT_KEYS if key in row_by_key
    ]
    missing_inputs = [
        key for key in INPUT_KEYS if key not in row_by_key or not _usable(row_by_key[key])
    ]
    missing_critical_inputs = list(ALWAYS_MISSING_CRITICAL_INPUTS)
    core_credit_missing = [key for key in CORE_CREDIT_INPUTS if key in missing_inputs]
    if core_credit_missing:
        missing_critical_inputs.extend(core_credit_missing)

    checklist_items = _checklist_items(row_by_key, evidence_index)
    percentile_context = _percentile_context(evidence_index)
    classification = _classify(
        row_by_key=row_by_key,
        checklist_items=checklist_items,
        core_credit_missing=core_credit_missing,
    )
    row_status = CLASSIFICATION_STATUS[classification]
    ai_context_allowed = row_status != "insufficient_evidence"
    observation_date = _latest_text(
        row.get("observation_date")
        for row in row_by_key.values()
        if isinstance(row.get("observation_date"), str)
    )
    common = {
        "source": "local_dashboard_evidence",
        "source_badge": "derived",
        "source_series": None,
        "observation_date": observation_date,
        "generated_at": generated_at,
        "freshness_status": "historical" if input_evidence else "missing",
        "missing_reason": "core_credit_inputs_missing" if core_credit_missing else None,
        "interpretation_hint": INTERPRETATION_HINT,
        "ai_context_allowed": ai_context_allowed,
        "input_evidence": input_evidence,
        "missing_inputs": missing_critical_inputs,
        "component_contributions": {
            "checklist_items": checklist_items,
            "missing_critical_inputs": missing_critical_inputs,
            "pullback_percentile_context": percentile_context,
            "systemic_not_triggered_by_percentile_only": True,
        },
        "interpretation_boundary": PULLBACK_BOUNDARY,
    }
    return [
        {
            **common,
            "metric_key": "pullback_classification",
            "display_name": "Pullback classification",
            "value": classification,
            "value_text": classification,
            "unit": "text",
            "status": row_status,
        },
        {
            **common,
            "metric_key": "pullback_checklist_items",
            "display_name": "Pullback checklist items",
            "value": _items_value_text(checklist_items),
            "value_text": _items_value_text(checklist_items),
            "unit": "json",
            "status": row_status,
        },
        {
            **common,
            "metric_key": "pullback_missing_critical_inputs",
            "display_name": "Pullback missing critical inputs",
            "value": ", ".join(missing_critical_inputs),
            "value_text": ", ".join(missing_critical_inputs),
            "unit": "text",
            "status": "watch" if missing_critical_inputs and row_status != "insufficient_evidence" else row_status,
        },
        {
            **common,
            "metric_key": "pullback_supporting_evidence",
            "display_name": "Pullback supporting evidence",
            "value": f"{len(input_evidence)} inputs",
            "value_text": f"{len(input_evidence)} input evidence rows",
            "unit": "count",
            "status": row_status,
        },
        {
            **common,
            "metric_key": "pullback_interpretation_boundary",
            "display_name": "Pullback interpretation boundary",
            "value": PULLBACK_BOUNDARY,
            "value_text": PULLBACK_BOUNDARY,
            "unit": "text",
            "status": row_status,
        },
        {
            **common,
            "metric_key": "pullback_percentile_context",
            "display_name": "Pullback percentile context",
            "value": _percentile_context_text(percentile_context),
            "value_text": _percentile_context_text(percentile_context),
            "unit": "json",
            "status": "ok" if percentile_context["available_count"] else "watch",
        },
    ]


def _checklist_items(
    row_by_key: dict[str, dict[str, Any]],
    evidence_index: historical_percentile_metrics.EvidenceIndex,
) -> list[dict[str, Any]]:
    return [
        _item(
            "equity_damage",
            _equity_damage(row_by_key),
            _evidence(row_by_key, (
                "sp500_drawdown_3m",
                "sp500_drawdown_6m",
                "nasdaq100_drawdown_3m",
                "nasdaq100_drawdown_6m",
            )),
            "Equity drawdown is outcome evidence, not systemic-risk proof by itself.",
            evidence_index,
        ),
        _item(
            "credit_spread_confirmation",
            _credit_spread_confirmation(row_by_key),
            _evidence(row_by_key, ("high_yield_spread", "investment_grade_spread", "credit_stress_status")),
            "Requires HY and IG spread confirmation for systemic-risk escalation.",
            evidence_index,
        ),
        _item(
            "volatility_confirmation",
            _volatility_confirmation(row_by_key),
            _evidence(row_by_key, ("vix",)),
            "VIX alone is not systemic risk.",
            evidence_index,
        ),
        _item(
            "rates_real_yield_pressure",
            _rates_real_yield_pressure(row_by_key),
            _evidence(row_by_key, (
                "dgs30",
                "dfii10",
                "dgs10_dgs2_curve_slope",
                "dgs30_dgs10_curve_slope",
                "real_yield_pressure_status",
            )),
            "Rates and real yield are macro context, not trading signals.",
            evidence_index,
        ),
        _item(
            "labor_deterioration",
            _labor_deterioration(row_by_key),
            _evidence(row_by_key, (
                "labor_deterioration_status",
                "sahm_rule_proxy_status",
                "initial_claims_4w_avg",
                "continuing_claims_4w_avg",
                "unemployment_rate_12m_low_gap",
            )),
            "Labor deterioration supports macro review but does not alone confirm crisis.",
            evidence_index,
        ),
        _item(
            "inflation_fed_constraint",
            _inflation_fed_constraint(row_by_key),
            _evidence(row_by_key, ("core_cpi_yoy", "core_pce_yoy", "ppi_final_demand_yoy")),
            "Inflation constraints are macro context and not a market-bottom/top signal.",
            evidence_index,
        ),
        _item(
            "cross_asset_proxy_confirmation",
            _cross_asset_proxy_confirmation(row_by_key),
            _evidence(row_by_key, ("hyg_vs_lqd_30d", "hyg_vs_lqd_60d")),
            "HYG/LQD is proxy evidence, not official funding stress.",
            evidence_index,
        ),
        _gap_item("valuation_gap"),
        _gap_item("earnings_gap"),
        _gap_item("true_breadth_gap"),
        _gap_item("liquidity_gap"),
    ]


def _classify(
    *,
    row_by_key: dict[str, dict[str, Any]],
    checklist_items: list[dict[str, Any]],
    core_credit_missing: list[str],
) -> str:
    if core_credit_missing:
        return "insufficient_evidence"
    equity = _by_item(checklist_items, "equity_damage")
    credit = _by_item(checklist_items, "credit_spread_confirmation")
    volatility = _by_item(checklist_items, "volatility_confirmation")
    labor = _by_item(checklist_items, "labor_deterioration")
    rates = _by_item(checklist_items, "rates_real_yield_pressure")
    proxy_only = _proxy_only(row_by_key)
    stress_status = str(row_by_key.get("financial_stress_status", {}).get("value", ""))

    if proxy_only:
        return "macro_pressure" if equity["status"] == "confirmed" else "ordinary_pullback"
    if (
        stress_status in {"pressure", "stress"}
        and credit["severity"] in {"pressure", "stress"}
        and labor["severity"] in {"pressure", "stress"}
    ):
        return "systemic_risk_review"
    if (
        equity["status"] == "confirmed"
        and volatility["severity"] in {"pressure", "stress"}
        and credit["severity"] in {"pressure", "stress"}
    ):
        return "credit_warning"
    if equity["status"] == "confirmed" and volatility["severity"] in {"pressure", "stress"}:
        return "macro_pressure" if rates["severity"] in {"watch", "pressure", "stress"} else "valuation_drawdown"
    if equity["status"] == "confirmed":
        return "valuation_drawdown" if _any_gap(checklist_items) else "ordinary_pullback"
    return "ordinary_pullback"


def _equity_damage(row_by_key: dict[str, dict[str, Any]]) -> tuple[str, str]:
    values = [
        _to_float(row_by_key.get(key, {}).get("value"))
        for key in (
            "sp500_drawdown_3m",
            "sp500_drawdown_6m",
            "nasdaq100_drawdown_3m",
            "nasdaq100_drawdown_6m",
        )
        if _usable(row_by_key.get(key, {}))
    ]
    if not values:
        return ("missing", "none")
    worst = min(values)
    if worst <= -20.0:
        return ("confirmed", "stress")
    if worst <= -12.0:
        return ("confirmed", "pressure")
    if worst <= -7.0:
        return ("confirmed", "watch")
    return ("not_confirmed", "none")


def _credit_spread_confirmation(row_by_key: dict[str, dict[str, Any]]) -> tuple[str, str]:
    hy = _to_float(row_by_key.get("high_yield_spread", {}).get("value"))
    ig = _to_float(row_by_key.get("investment_grade_spread", {}).get("value"))
    if not _usable(row_by_key.get("high_yield_spread", {})) or not _usable(row_by_key.get("investment_grade_spread", {})):
        return ("missing", "none")
    if hy is None or ig is None:
        return ("missing", "none")
    if hy >= 6.0 and ig >= 2.0:
        return ("confirmed", "stress")
    if hy >= 4.5 or ig >= 1.5:
        return ("confirmed", "pressure")
    if hy >= 3.5 or ig >= 1.0:
        return ("mixed", "watch")
    return ("not_confirmed", "none")


def _volatility_confirmation(row_by_key: dict[str, dict[str, Any]]) -> tuple[str, str]:
    vix = _to_float(row_by_key.get("vix", {}).get("value"))
    if vix is None or not _usable(row_by_key.get("vix", {})):
        return ("missing", "none")
    if vix >= 35.0:
        return ("confirmed", "stress")
    if vix >= 25.0:
        return ("confirmed", "pressure")
    if vix >= 20.0:
        return ("mixed", "watch")
    return ("not_confirmed", "none")


def _rates_real_yield_pressure(row_by_key: dict[str, dict[str, Any]]) -> tuple[str, str]:
    status = _status_value(row_by_key.get("real_yield_pressure_status"))
    if status in {"pressure", "stress"}:
        return ("confirmed", status)
    dgs30 = _to_float(row_by_key.get("dgs30", {}).get("value"))
    dfii10 = _to_float(row_by_key.get("dfii10", {}).get("value"))
    slope = _to_float(row_by_key.get("dgs10_dgs2_curve_slope", {}).get("value"))
    if dgs30 is None and dfii10 is None and slope is None:
        return ("missing", "none")
    if (dfii10 is not None and dfii10 >= 2.5) or (slope is not None and slope <= -0.5):
        return ("confirmed", "pressure")
    if (dfii10 is not None and dfii10 >= 2.0) or (dgs30 is not None and dgs30 >= 4.5) or (slope is not None and slope < 0):
        return ("mixed", "watch")
    return ("not_confirmed", "none")


def _labor_deterioration(row_by_key: dict[str, dict[str, Any]]) -> tuple[str, str]:
    status = _status_value(row_by_key.get("labor_deterioration_status"))
    sahm = _status_value(row_by_key.get("sahm_rule_proxy_status"))
    gap = _to_float(row_by_key.get("unemployment_rate_12m_low_gap", {}).get("value"))
    if status in {"pressure", "stress"} or sahm in {"pressure", "stress"}:
        return ("confirmed", "pressure")
    if status == "watch" or sahm == "watch" or (gap is not None and gap >= 0.3):
        return ("mixed", "watch")
    if any(_usable(row_by_key.get(key, {})) for key in ("labor_deterioration_status", "sahm_rule_proxy_status", "unemployment_rate_12m_low_gap")):
        return ("not_confirmed", "none")
    return ("missing", "none")


def _inflation_fed_constraint(row_by_key: dict[str, dict[str, Any]]) -> tuple[str, str]:
    values = [
        _to_float(row_by_key.get(key, {}).get("value"))
        for key in ("core_cpi_yoy", "core_pce_yoy", "ppi_final_demand_yoy")
        if _usable(row_by_key.get(key, {}))
    ]
    if not values:
        return ("missing", "none")
    if max(values) >= 4.0:
        return ("confirmed", "pressure")
    if max(values) >= 3.0:
        return ("mixed", "watch")
    return ("not_confirmed", "none")


def _cross_asset_proxy_confirmation(row_by_key: dict[str, dict[str, Any]]) -> tuple[str, str]:
    values = [
        _to_float(row_by_key.get(key, {}).get("value"))
        for key in ("hyg_vs_lqd_30d", "hyg_vs_lqd_60d")
        if _usable(row_by_key.get(key, {}))
    ]
    if not values:
        return ("missing", "none")
    if min(values) <= -5.0:
        return ("confirmed", "pressure")
    if min(values) <= -2.0:
        return ("mixed", "watch")
    return ("not_confirmed", "none")


def _gap_item(key: str) -> dict[str, Any]:
    return {
        "key": key,
        "status": "missing",
        "severity": "watch",
        "evidence": [],
        "notes": "Critical input gap; limits crisis confirmation.",
    }


def _item(
    key: str,
    status_severity: tuple[str, str],
    evidence: list[dict[str, Any]],
    notes: str,
    evidence_index: historical_percentile_metrics.EvidenceIndex,
) -> dict[str, Any]:
    status, severity = status_severity
    percentile_evidence = evidence_index.available_d13_context(ITEM_PERCENTILE_KEYS.get(key, ()))
    return {
        "key": key,
        "status": status,
        "severity": severity,
        "evidence": evidence,
        "percentile_evidence": percentile_evidence,
        "rarity_note": _rarity_note(percentile_evidence),
        "notes": notes,
    }


def _evidence(
    row_by_key: dict[str, dict[str, Any]],
    keys: tuple[str, ...],
) -> list[dict[str, Any]]:
    return [_input_snapshot(row_by_key[key]) for key in keys if key in row_by_key]


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


def _usable(row: dict[str, Any]) -> bool:
    if not row:
        return False
    if row.get("status") in BAD_STATUSES:
        return False
    if row.get("freshness_status") in BAD_FRESHNESS:
        return False
    if row.get("source_badge") in {"missing", "research_needed", "search-derived"}:
        return False
    if row.get("ai_context_allowed") is False:
        return False
    value = row.get("value")
    return value is not None and value != ""


def _status_value(row: dict[str, Any] | None) -> str:
    if not row or not _usable(row):
        return ""
    value = str(row.get("value", "")).lower()
    if value in STATUS_SEVERITY:
        return value
    return str(row.get("status", "")).lower()


def _by_item(items: list[dict[str, Any]], key: str) -> dict[str, Any]:
    for item in items:
        if item["key"] == key:
            return item
    return {"status": "missing", "severity": "none"}


def _any_gap(items: list[dict[str, Any]]) -> bool:
    return any(item["key"].endswith("_gap") and item["status"] == "missing" for item in items)


def _proxy_only(row_by_key: dict[str, dict[str, Any]]) -> bool:
    usable_rows = [row for key, row in row_by_key.items() if key in INPUT_KEYS and _usable(row)]
    if not usable_rows:
        return False
    return all(row.get("source_badge") in {"proxy", "derived"} for row in usable_rows)


def _items_value_text(items: list[dict[str, Any]]) -> str:
    confirmed = sum(1 for item in items if item["status"] == "confirmed")
    mixed = sum(1 for item in items if item["status"] == "mixed")
    missing = sum(1 for item in items if item["status"] == "missing")
    return f"{len(items)} items; confirmed={confirmed}; mixed={mixed}; missing={missing}"


def _percentile_context(
    evidence_index: historical_percentile_metrics.EvidenceIndex,
) -> dict[str, Any]:
    available = evidence_index.available_d13_context(D13_PULLBACK_KEYS)
    missing = evidence_index.missing_d13_context(D13_PULLBACK_KEYS)
    return {
        "available_count": len(available),
        "missing_count": len(missing),
        "available": available,
        "missing": missing,
        "credit_percentile_used_as_auxiliary": any(
            item.get("metric_key") in ITEM_PERCENTILE_KEYS["credit_spread_confirmation"]
            for item in available
        ),
        "systemic_not_triggered_by_percentile_only": True,
        "liquidity_still_missing_until_d14": True,
        "normalization_boundary": (
            "This checklist is not crash probability. Percentile evidence is auxiliary "
            "and cannot alone trigger systemic_risk_review. Equity drawdown percentile "
            "alone is not systemic risk. VIX percentile alone is not systemic risk. "
            "Proxy evidence is not true breadth or official funding stress. Liquidity/"
            "funding remains a critical missing input until D14 is implemented."
        ),
    }


def _percentile_context_text(context: dict[str, Any]) -> str:
    return (
        f"{context['available_count']} D13 auxiliary percentile rows available; "
        f"{context['missing_count']} missing or blocked"
    )


def _rarity_note(percentile_evidence: list[dict[str, Any]]) -> str | None:
    if not percentile_evidence:
        return None
    bands = [
        item.get("percentile_band") or item.get("robust_zscore_band") or item.get("zscore_band")
        for item in percentile_evidence
    ]
    bands = [str(band) for band in bands if band]
    if not bands:
        return None
    return f"D13 auxiliary rarity bands: {', '.join(bands)}."


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
