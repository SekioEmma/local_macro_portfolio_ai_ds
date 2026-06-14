from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Iterable

from modeling.evidence_index import EvidenceIndex
from modeling.model_output import ModelOutput
from modeling.model_registry import get_model_registry


MODEL_KEY = "growth_inflation_macro_pack_v0"
MODULE_KEY = "growth_inflation_macro_pack"
MODEL_VERSION = "growth_inflation_macro_pack_v0"
FORMULA_VERSION = "d17_growth_inflation_context_v0"
BOUNDARY = (
    "Growth/inflation macro pack is a conservative current-evidence context "
    "layer for growth, inflation, policy-constraint, and stagflation-watch "
    "interpretation. It is derived from current sanitized evidence rows and is "
    "not a forecast, business-cycle call, event-odds model, allocation "
    "directive, or return estimate. CPI/PCE/PPI are low-frequency data; "
    "retail, industrial production, housing, payroll, and survey inputs require "
    "source-gated evidence before use."
)
PRESSURE_STATUSES = {"watch", "pressure", "stress"}
HIGH_PRESSURE_STATUSES = {"pressure", "stress"}
GROWTH_CURRENT_KEYS = (
    "unemployment_rate",
    "unemployment_rate_3m_avg",
    "initial_jobless_claims",
    "initial_claims_4w_avg",
    "continuing_claims",
    "continuing_claims_4w_avg",
    "nonfarm_payrolls",
    "labor_deterioration_status",
)
GROWTH_RESEARCH_NEEDED_KEYS = (
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
)
INFLATION_CORE_KEYS = (
    "core_cpi_yoy",
    "core_pce_yoy",
    "ppiaco_yoy",
    "ppi_final_demand_yoy",
)
INFLATION_AUXILIARY_KEYS = ("wti_30d_change", "brent_30d_change", "t10yie")
INFLATION_RESEARCH_NEEDED_KEYS = (
    "core_cpi_goods_yoy",
    "core_cpi_services_yoy",
    "core_pce_goods_yoy",
    "core_pce_services_yoy",
    "ppi_final_demand_goods_yoy",
    "ppi_final_demand_services_yoy",
    "ism_prices_paid",
    "gasoline_price_context",
)
RATES_POLICY_KEYS = ("dgs10", "dgs30", "dfii10", "t10yie", "real_yield_pressure_status")
PUBLIC_OUTPUT_KEYS = get_model_registry().public_output_keys(MODULE_KEY)


def build_growth_inflation_macro_pack_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    index = EvidenceIndex(rows)
    growth = _growth_context(index)
    inflation = _inflation_context(index)
    policy = _policy_context(index, growth, inflation)
    stagflation = _stagflation_context(growth, inflation, policy)
    all_supporting = sorted(
        set(growth["supporting_evidence"])
        | set(inflation["supporting_evidence"])
        | set(policy["supporting_evidence"])
        | set(stagflation["supporting_evidence"])
    )
    return {
        "growth": growth,
        "inflation": inflation,
        "policy": policy,
        "stagflation": stagflation,
        "as_of_date": _latest_observation_date(index, all_supporting),
        "input_evidence": _input_evidence(index, all_supporting),
        "missing_inputs": sorted(
            set(growth["missing_inputs"])
            | set(inflation["missing_inputs"])
            | set(policy["missing_inputs"])
            | set(stagflation["missing_inputs"])
        ),
        "uses_model_registry": bool(get_model_registry().get(MODULE_KEY)),
        "uses_evidence_index": isinstance(index, EvidenceIndex),
    }


def build_growth_inflation_macro_pack_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    summary = build_growth_inflation_macro_pack_summary(rows)
    now = _utc_now()
    base = {
        "model_key": MODEL_KEY,
        "module_key": MODULE_KEY,
        "source_badge": "derived",
        "freshness_status": "historical",
        "interpretation_boundary": BOUNDARY,
        "component_contributions": {
            "growth": summary["growth"],
            "inflation": summary["inflation"],
            "policy": summary["policy"],
            "stagflation": summary["stagflation"],
            "uses_model_registry": summary["uses_model_registry"],
            "uses_evidence_index": summary["uses_evidence_index"],
        },
        "ai_context_allowed": True,
    }
    values: dict[str, tuple[str, Any, str, bool]] = {
        "growth_macro_status": (
            "Growth macro status",
            summary["growth"]["status"],
            summary["growth"]["row_status"],
            summary["growth"]["ai_context_allowed"],
        ),
        "growth_macro_supporting_evidence": (
            "Growth macro supporting evidence",
            _join(summary["growth"]["supporting_evidence"]),
            summary["growth"]["row_status"],
            summary["growth"]["ai_context_allowed"],
        ),
        "growth_macro_missing_inputs": (
            "Growth macro missing inputs",
            _join(summary["growth"]["missing_inputs"]),
            _missing_row_status(summary["growth"]["missing_inputs"]),
            False,
        ),
        "growth_macro_interpretation_boundary": (
            "Growth macro interpretation boundary",
            BOUNDARY,
            summary["growth"]["row_status"],
            summary["growth"]["ai_context_allowed"],
        ),
        "inflation_macro_status": (
            "Inflation macro status",
            summary["inflation"]["status"],
            summary["inflation"]["row_status"],
            summary["inflation"]["ai_context_allowed"],
        ),
        "inflation_macro_supporting_evidence": (
            "Inflation macro supporting evidence",
            _join(summary["inflation"]["supporting_evidence"]),
            summary["inflation"]["row_status"],
            summary["inflation"]["ai_context_allowed"],
        ),
        "inflation_macro_missing_inputs": (
            "Inflation macro missing inputs",
            _join(summary["inflation"]["missing_inputs"]),
            _missing_row_status(summary["inflation"]["missing_inputs"]),
            False,
        ),
        "inflation_macro_interpretation_boundary": (
            "Inflation macro interpretation boundary",
            BOUNDARY,
            summary["inflation"]["row_status"],
            summary["inflation"]["ai_context_allowed"],
        ),
        "policy_constraint_status": (
            "Policy constraint status",
            summary["policy"]["status"],
            summary["policy"]["row_status"],
            summary["policy"]["ai_context_allowed"],
        ),
        "policy_constraint_supporting_evidence": (
            "Policy constraint supporting evidence",
            _join(summary["policy"]["supporting_evidence"]),
            summary["policy"]["row_status"],
            summary["policy"]["ai_context_allowed"],
        ),
        "policy_constraint_missing_inputs": (
            "Policy constraint missing inputs",
            _join(summary["policy"]["missing_inputs"]),
            _missing_row_status(summary["policy"]["missing_inputs"]),
            False,
        ),
        "policy_constraint_interpretation_boundary": (
            "Policy constraint interpretation boundary",
            BOUNDARY,
            summary["policy"]["row_status"],
            summary["policy"]["ai_context_allowed"],
        ),
        "stagflation_watch_status": (
            "Stagflation watch status",
            summary["stagflation"]["status"],
            summary["stagflation"]["row_status"],
            summary["stagflation"]["ai_context_allowed"],
        ),
        "stagflation_watch_supporting_evidence": (
            "Stagflation watch supporting evidence",
            _join(summary["stagflation"]["supporting_evidence"]),
            summary["stagflation"]["row_status"],
            summary["stagflation"]["ai_context_allowed"],
        ),
        "stagflation_watch_missing_inputs": (
            "Stagflation watch missing inputs",
            _join(summary["stagflation"]["missing_inputs"]),
            _missing_row_status(summary["stagflation"]["missing_inputs"]),
            False,
        ),
        "stagflation_watch_interpretation_boundary": (
            "Stagflation watch interpretation boundary",
            BOUNDARY,
            summary["stagflation"]["row_status"],
            summary["stagflation"]["ai_context_allowed"],
        ),
        "growth_inflation_macro_pack_model_version": (
            "Growth/inflation macro pack model version",
            MODEL_VERSION,
            "ok",
            True,
        ),
        "growth_inflation_macro_pack_formula_version": (
            "Growth/inflation macro pack formula version",
            FORMULA_VERSION,
            "ok",
            True,
        ),
        "growth_inflation_macro_pack_as_of_date": (
            "Growth/inflation macro pack as-of date",
            summary["as_of_date"] or "not available",
            "ok" if summary["as_of_date"] else "missing",
            bool(summary["as_of_date"]),
        ),
    }
    return [
        ModelOutput(
            metric_key=metric_key,
            value=value,
            value_text=str(value),
            status=status,
            source_badge=base["source_badge"],
            freshness_status=base["freshness_status"],
            interpretation_boundary=base["interpretation_boundary"],
            component_contributions=base["component_contributions"],
            ai_context_allowed=ai_allowed,
            model_key=base["model_key"],
            module_key=base["module_key"],
        ).to_metric_payload(
            display_name=display_name,
            source="local_rules",
            source_series="D17_GROWTH_INFLATION_CONTEXT_V0",
            observation_date=summary["as_of_date"],
            generated_at=now,
            missing_reason=None if ai_allowed else status,
            input_evidence=summary["input_evidence"],
            missing_inputs=summary["missing_inputs"],
        )
        for metric_key, (display_name, value, status, ai_allowed) in values.items()
    ]


def _growth_context(index: EvidenceIndex) -> dict[str, Any]:
    supporting = [
        key
        for key in GROWTH_CURRENT_KEYS
        if _usable(index, key)
    ]
    pressure = [
        key
        for key in supporting
        if _pressure_value(index, key) in HIGH_PRESSURE_STATUSES
    ]
    watch = [
        key
        for key in supporting
        if _pressure_value(index, key) in PRESSURE_STATUSES
    ]
    missing = sorted(set(GROWTH_RESEARCH_NEEDED_KEYS).union(index.missing_or_blocked_inputs(GROWTH_CURRENT_KEYS, require_ai_context_allowed=False)))
    if pressure and len(supporting) >= 2:
        status = "pressure"
    elif watch:
        status = "watch"
    elif supporting:
        status = "ok"
    else:
        status = "research_needed"
    return _context(
        status=status,
        supporting=supporting,
        missing=missing,
        hard_gates={
            "labor_watch_alone_not_business_cycle_call": True,
            "broad_growth_pack_missing_until_source_gated": bool(set(GROWTH_RESEARCH_NEEDED_KEYS) & set(missing)),
        },
    )


def _inflation_context(index: EvidenceIndex) -> dict[str, Any]:
    core = [key for key in INFLATION_CORE_KEYS if _usable(index, key)]
    auxiliary = [key for key in INFLATION_AUXILIARY_KEYS if _usable(index, key)]
    pressure = [
        key
        for key in core
        if _pressure_value(index, key) in HIGH_PRESSURE_STATUSES
    ]
    watch = [
        key
        for key in core
        if _pressure_value(index, key) in PRESSURE_STATUSES
    ]
    missing = sorted(
        set(INFLATION_RESEARCH_NEEDED_KEYS).union(
            index.missing_or_blocked_inputs(INFLATION_CORE_KEYS, require_ai_context_allowed=False)
        )
    )
    if pressure:
        status = "pressure"
    elif watch:
        status = "watch"
    elif core:
        status = "ok"
    elif auxiliary:
        status = "missing"
        missing = sorted(set(missing).union(INFLATION_CORE_KEYS))
    else:
        status = "research_needed"
    return _context(
        status=status,
        supporting=[*core, *auxiliary],
        missing=missing,
        hard_gates={
            "oil_alone_cannot_trigger_inflation_pressure": bool(auxiliary and not core),
            "low_frequency_inflation_data_boundary": True,
        },
    )


def _policy_context(
    index: EvidenceIndex,
    growth: dict[str, Any],
    inflation: dict[str, Any],
) -> dict[str, Any]:
    rates = [key for key in RATES_POLICY_KEYS if _usable(index, key)]
    rates_pressure = [
        key
        for key in rates
        if _pressure_value(index, key) in PRESSURE_STATUSES
    ]
    missing = index.missing_or_blocked_inputs(RATES_POLICY_KEYS, require_ai_context_allowed=False)
    inflation_elevated = inflation["status"] in {"watch", "pressure"}
    growth_soft = growth["status"] in {"watch", "pressure"}
    if not rates or inflation["status"] in {"missing", "research_needed"}:
        status = "insufficient_evidence"
    elif inflation["status"] == "pressure" and rates_pressure and growth_soft:
        status = "highly_constrained"
    elif inflation_elevated and rates_pressure:
        status = "constrained"
    elif inflation_elevated or rates_pressure:
        status = "neutral"
    else:
        status = "loose_or_supportive"
    return _context(
        status=status,
        supporting=rates + inflation["supporting_evidence"][:4] + growth["supporting_evidence"][:4],
        missing=missing,
        hard_gates={
            "rates_and_inflation_required_for_policy_constraint": True,
        },
    )


def _stagflation_context(
    growth: dict[str, Any],
    inflation: dict[str, Any],
    policy: dict[str, Any],
) -> dict[str, Any]:
    inflation_pressure = inflation["status"] == "pressure"
    growth_soft = growth["status"] in {"watch", "pressure"}
    policy_constrained = policy["status"] in {"constrained", "highly_constrained"}
    missing = sorted(
        set(growth["missing_inputs"])
        | set(inflation["missing_inputs"])
        | set(policy["missing_inputs"])
    )
    if inflation_pressure and growth_soft and policy_constrained:
        status = "pressure"
    elif sum((inflation_pressure, growth_soft, policy_constrained)) >= 2:
        status = "watch"
    elif growth["status"] in {"research_needed", "missing"} or inflation["status"] in {"research_needed", "missing"}:
        status = "insufficient_evidence"
    else:
        status = "not_supported"
    return _context(
        status=status,
        supporting=sorted(
            set(growth["supporting_evidence"])
            | set(inflation["supporting_evidence"])
            | set(policy["supporting_evidence"])
        ),
        missing=missing,
        hard_gates={
            "requires_inflation_growth_and_policy_constraint": True,
            "cpi_alone_cannot_trigger_stagflation_watch_pressure": True,
        },
    )


def _context(
    *,
    status: str,
    supporting: list[str],
    missing: list[str],
    hard_gates: dict[str, bool],
) -> dict[str, Any]:
    row_status = _row_status(status)
    return {
        "status": status,
        "row_status": row_status,
        "supporting_evidence": sorted(set(supporting)),
        "missing_inputs": sorted(set(missing)),
        "hard_gates": hard_gates,
        "ai_context_allowed": row_status not in {"missing", "research_needed", "insufficient_history", "insufficient_evidence", "unknown"},
    }


def _row_status(status: str) -> str:
    if status in {"loose_or_supportive", "neutral", "not_supported"}:
        return "ok"
    if status in {"constrained", "watch"}:
        return "watch"
    if status in {"highly_constrained", "pressure"}:
        return "pressure"
    return status


def _missing_row_status(missing_inputs: list[str]) -> str:
    return "research_needed" if missing_inputs else "ok"


def _usable(index: EvidenceIndex, metric_key: str) -> bool:
    return index.is_usable_for_support(
        metric_key,
        require_ai_context_allowed=False,
        require_core_trigger=False,
    )


def _pressure_value(index: EvidenceIndex, metric_key: str) -> str | None:
    row = index.by_metric_key(metric_key)
    value = _row_value(row, "value")
    if isinstance(value, str) and value.lower() in {"ok", "watch", "pressure", "stress"}:
        return value.lower()
    status = str(_row_value(row, "status") or "")
    return status if status in {"ok", "watch", "pressure", "stress"} else None


def _input_evidence(index: EvidenceIndex, metric_keys: Iterable[str]) -> list[dict[str, Any]]:
    return [
        index.public_payload(metric_key)
        for metric_key in sorted(set(metric_keys))
        if index.by_metric_key(metric_key) is not None
    ]


def _latest_observation_date(index: EvidenceIndex, metric_keys: Iterable[str]) -> str | None:
    dates = [
        str(_row_value(index.by_metric_key(metric_key), "observation_date"))
        for metric_key in metric_keys
        if index.by_metric_key(metric_key) is not None
        and _row_value(index.by_metric_key(metric_key), "observation_date")
    ]
    return max(dates) if dates else None


def _row_value(row: Any, field: str) -> Any:
    if isinstance(row, dict):
        return row.get(field)
    return getattr(row, field, None)


def _join(items: list[str]) -> str:
    return ", ".join(items) if items else "none"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()
