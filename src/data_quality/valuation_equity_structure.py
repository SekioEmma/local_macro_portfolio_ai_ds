from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Iterable

from modeling.evidence_index import EvidenceIndex
from modeling.model_output import ModelOutput
from modeling.model_registry import get_model_registry


MODEL_KEY = "valuation_equity_structure_v0"
MODULE_KEY = "valuation_equity_structure"
MODEL_VERSION = "valuation_equity_structure_v0"
FORMULA_VERSION = "d18_valuation_equity_structure_v0"
BOUNDARY = (
    "Valuation/equity structure is a conservative research/proxy context "
    "layer for valuation vulnerability, earnings gaps, breadth gaps, and "
    "concentration context. It is derived from current sanitized evidence rows "
    "and is not a forecast, timing model, event-odds model, allocation "
    "directive, or return estimate. Proxy breadth/concentration does not "
    "replace true breadth."
)
VALUATION_FACT_KEYS = (
    "sp500_trailing_pe",
    "sp500_forward_pe",
    "cape_shiller_pe",
    "earnings_yield",
    "equity_risk_premium_proxy",
)
VALUATION_MISSING_INPUTS = (
    "sp500_trailing_pe_source_gate",
    "sp500_forward_pe_source_gate",
    "sp500_cape_source_gate",
    "sp500_erp_source_gate",
    "sp500_top10_weight_source_gate",
    "mag7_concentration_source_gate",
)
EARNINGS_FACT_KEYS = ("earnings_revision", "eps_growth")
EARNINGS_MISSING_INPUTS = (
    "earnings_revision_source_gate",
    "eps_growth_source_gate",
)
TRUE_BREADTH_KEYS = (
    "advance_decline_line",
    "percent_above_200dma",
    "new_highs_new_lows",
    "true_breadth",
)
TRUE_BREADTH_MISSING_INPUTS = (
    "true_breadth_source_gate",
    "constituent_breadth_source_gate",
)
EQUITY_STRUCTURE_PROXY_KEYS = (
    "qqq_vs_spy_30d",
    "qqq_vs_spy_60d",
    "nasdaq_vs_sp500_30d",
    "nasdaq100_drawdown_3m",
    "nasdaq100_drawdown_6m",
    "sp500_drawdown_3m",
    "sp500_drawdown_6m",
)
BREADTH_CONCENTRATION_PROXY_KEYS = (
    "spy_vs_rsp_30d",
    "spy_vs_rsp_60d",
    "qqq_vs_spy_30d",
    "qqq_vs_spy_60d",
)
PRESSURE_STATUSES = {"watch", "pressure", "stress"}
HIGH_PRESSURE_STATUSES = {"pressure", "stress"}
PUBLIC_OUTPUT_KEYS = get_model_registry().public_output_keys(MODULE_KEY)


def build_valuation_equity_structure_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    index = EvidenceIndex(rows)
    valuation = _valuation_context(index)
    earnings = _earnings_context(index)
    equity_structure = _equity_structure_context(index)
    breadth_concentration = _breadth_concentration_context(index)
    supporting = sorted(
        set(valuation["supporting_evidence"])
        | set(earnings["supporting_evidence"])
        | set(equity_structure["supporting_evidence"])
        | set(breadth_concentration["supporting_evidence"])
    )
    missing = sorted(
        set(valuation["missing_inputs"])
        | set(earnings["missing_inputs"])
        | set(equity_structure["missing_inputs"])
        | set(breadth_concentration["missing_inputs"])
    )
    return {
        "valuation": valuation,
        "earnings": earnings,
        "equity_structure": equity_structure,
        "breadth_concentration": breadth_concentration,
        "as_of_date": _latest_observation_date(index, supporting),
        "input_evidence": _input_evidence(index, supporting),
        "missing_inputs": missing,
        "uses_model_registry": bool(get_model_registry().get(MODULE_KEY)),
        "uses_evidence_index": isinstance(index, EvidenceIndex),
    }


def build_valuation_equity_structure_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    summary = build_valuation_equity_structure_summary(rows)
    now = _utc_now()
    base = {
        "model_key": MODEL_KEY,
        "module_key": MODULE_KEY,
        "source_badge": "derived",
        "freshness_status": "historical",
        "interpretation_boundary": BOUNDARY,
        "component_contributions": {
            "valuation": summary["valuation"],
            "earnings": summary["earnings"],
            "equity_structure": summary["equity_structure"],
            "breadth_concentration": summary["breadth_concentration"],
            "hard_gates": {
                "valuation_cannot_trigger_macro_regime": True,
                "valuation_cannot_trigger_systemic_review": True,
                "proxy_breadth_not_true_breadth": True,
                "proxy_only_context_cannot_create_strong_label": True,
            },
            "uses_model_registry": summary["uses_model_registry"],
            "uses_evidence_index": summary["uses_evidence_index"],
        },
    }
    values: dict[str, tuple[str, Any, str, bool]] = {
        "valuation_context_status": (
            "Valuation context status",
            summary["valuation"]["status"],
            summary["valuation"]["row_status"],
            summary["valuation"]["ai_context_allowed"],
        ),
        "valuation_pressure_hint": (
            "Valuation pressure hint",
            summary["valuation"]["pressure_hint"],
            summary["valuation"]["pressure_row_status"],
            summary["valuation"]["ai_context_allowed"],
        ),
        "valuation_metric_source_quality": (
            "Valuation metric source quality",
            summary["valuation"]["source_quality"],
            summary["valuation"]["row_status"],
            summary["valuation"]["ai_context_allowed"],
        ),
        "valuation_missing_inputs": (
            "Valuation missing inputs",
            _join(summary["valuation"]["missing_inputs"]),
            _missing_row_status(summary["valuation"]["missing_inputs"]),
            False,
        ),
        "valuation_interpretation_boundary": (
            "Valuation interpretation boundary",
            BOUNDARY,
            summary["valuation"]["row_status"],
            summary["valuation"]["ai_context_allowed"],
        ),
        "earnings_context_status": (
            "Earnings context status",
            summary["earnings"]["status"],
            summary["earnings"]["row_status"],
            summary["earnings"]["ai_context_allowed"],
        ),
        "earnings_missing_inputs": (
            "Earnings missing inputs",
            _join(summary["earnings"]["missing_inputs"]),
            _missing_row_status(summary["earnings"]["missing_inputs"]),
            False,
        ),
        "earnings_interpretation_boundary": (
            "Earnings interpretation boundary",
            BOUNDARY,
            summary["earnings"]["row_status"],
            summary["earnings"]["ai_context_allowed"],
        ),
        "equity_structure_status": (
            "Equity structure status",
            summary["equity_structure"]["status"],
            summary["equity_structure"]["row_status"],
            summary["equity_structure"]["ai_context_allowed"],
        ),
        "equity_structure_supporting_evidence": (
            "Equity structure supporting evidence",
            _join(summary["equity_structure"]["supporting_evidence"]),
            summary["equity_structure"]["row_status"],
            summary["equity_structure"]["ai_context_allowed"],
        ),
        "equity_structure_missing_inputs": (
            "Equity structure missing inputs",
            _join(summary["equity_structure"]["missing_inputs"]),
            _missing_row_status(summary["equity_structure"]["missing_inputs"]),
            False,
        ),
        "equity_structure_interpretation_boundary": (
            "Equity structure interpretation boundary",
            BOUNDARY,
            summary["equity_structure"]["row_status"],
            summary["equity_structure"]["ai_context_allowed"],
        ),
        "breadth_concentration_context_status": (
            "Breadth/concentration context status",
            summary["breadth_concentration"]["status"],
            summary["breadth_concentration"]["row_status"],
            summary["breadth_concentration"]["ai_context_allowed"],
        ),
        "breadth_concentration_supporting_evidence": (
            "Breadth/concentration supporting evidence",
            _join(summary["breadth_concentration"]["supporting_evidence"]),
            summary["breadth_concentration"]["row_status"],
            summary["breadth_concentration"]["ai_context_allowed"],
        ),
        "breadth_concentration_missing_inputs": (
            "Breadth/concentration missing inputs",
            _join(summary["breadth_concentration"]["missing_inputs"]),
            _missing_row_status(summary["breadth_concentration"]["missing_inputs"]),
            False,
        ),
        "breadth_concentration_interpretation_boundary": (
            "Breadth/concentration interpretation boundary",
            BOUNDARY,
            summary["breadth_concentration"]["row_status"],
            summary["breadth_concentration"]["ai_context_allowed"],
        ),
        "valuation_equity_structure_model_version": (
            "Valuation/equity structure model version",
            MODEL_VERSION,
            "ok",
            True,
        ),
        "valuation_equity_structure_formula_version": (
            "Valuation/equity structure formula version",
            FORMULA_VERSION,
            "ok",
            True,
        ),
        "valuation_equity_structure_as_of_date": (
            "Valuation/equity structure as-of date",
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
            source_series="D18_VALUATION_EQUITY_STRUCTURE_V0",
            observation_date=summary["as_of_date"],
            generated_at=now,
            missing_reason=None if ai_allowed else status,
            input_evidence=summary["input_evidence"],
            missing_inputs=summary["missing_inputs"],
            ai_context_tier="fact_or_excluded_by_row",
            trigger_eligibility="auxiliary_only",
        )
        for metric_key, (display_name, value, status, ai_allowed) in values.items()
    ]


def _valuation_context(index: EvidenceIndex) -> dict[str, Any]:
    facts = [key for key in VALUATION_FACT_KEYS if _source_gated(index, key)]
    pressure = [key for key in facts if _pressure_value(index, key) in HIGH_PRESSURE_STATUSES]
    watch = [key for key in facts if _pressure_value(index, key) in PRESSURE_STATUSES]
    missing = sorted(
        set(VALUATION_MISSING_INPUTS).union(
            index.missing_or_blocked_inputs(
                VALUATION_FACT_KEYS,
                require_ai_context_allowed=False,
                require_core_trigger=False,
            )
        )
    )
    if pressure:
        status = "available"
        pressure_hint = "elevated"
        source_quality = "source_gated"
    elif watch:
        status = "available"
        pressure_hint = "watch"
        source_quality = "source_gated"
    elif facts:
        status = "available"
        pressure_hint = "none"
        source_quality = "source_gated"
    else:
        status = "research_needed"
        pressure_hint = "research_needed"
        source_quality = "source_gated_inputs_missing"
    return _context(
        status=status,
        supporting=facts,
        missing=missing,
        hard_gates={
            "forward_pe_requires_reliable_source_gate": True,
            "valuation_high_is_vulnerability_context_only": True,
            "missing_valuation_not_low_or_high": not facts,
        },
        pressure_hint=pressure_hint,
        source_quality=source_quality,
    )


def _earnings_context(index: EvidenceIndex) -> dict[str, Any]:
    facts = [key for key in EARNINGS_FACT_KEYS if _source_gated(index, key)]
    missing = sorted(
        set(EARNINGS_MISSING_INPUTS).union(
            index.missing_or_blocked_inputs(
                EARNINGS_FACT_KEYS,
                require_ai_context_allowed=False,
                require_core_trigger=False,
            )
        )
    )
    if len(facts) >= 2:
        status = "available"
    elif facts:
        status = "limited_context"
    else:
        status = "research_needed"
    return _context(
        status=status,
        supporting=facts,
        missing=missing,
        hard_gates={
            "earnings_revisions_require_reliable_source_gate": True,
            "missing_earnings_not_low_or_high": not facts,
        },
    )


def _equity_structure_context(index: EvidenceIndex) -> dict[str, Any]:
    proxies = [key for key in EQUITY_STRUCTURE_PROXY_KEYS if _usable_proxy(index, key)]
    pressure = [key for key in proxies if _pressure_value(index, key) in HIGH_PRESSURE_STATUSES]
    watch = [key for key in proxies if _pressure_value(index, key) in PRESSURE_STATUSES]
    missing = sorted(
        set(VALUATION_MISSING_INPUTS)
        | set(EARNINGS_MISSING_INPUTS)
        | set(TRUE_BREADTH_MISSING_INPUTS)
        | set(index.missing_or_blocked_inputs(TRUE_BREADTH_KEYS, require_ai_context_allowed=False))
    )
    if len(pressure) >= 2:
        status = "pressure"
    elif len(watch) >= 2:
        status = "watch"
    elif proxies:
        status = "limited_proxy_context"
    else:
        status = "unavailable"
    return _context(
        status=status,
        supporting=proxies,
        missing=missing,
        hard_gates={
            "nasdaq_underperformance_is_equity_structure_context_only": True,
            "ai_mega_cap_context_requires_credit_funding_labor_confirmation_for_systemic_review": True,
            "single_proxy_cannot_create_pressure": bool(proxies and len(watch) < 2),
        },
    )


def _breadth_concentration_context(index: EvidenceIndex) -> dict[str, Any]:
    proxies = [
        key for key in BREADTH_CONCENTRATION_PROXY_KEYS if _usable_proxy(index, key)
    ]
    pressure = [key for key in proxies if _pressure_value(index, key) in HIGH_PRESSURE_STATUSES]
    watch = [key for key in proxies if _pressure_value(index, key) in PRESSURE_STATUSES]
    missing = sorted(
        set(TRUE_BREADTH_MISSING_INPUTS)
        | set(index.missing_or_blocked_inputs(TRUE_BREADTH_KEYS, require_ai_context_allowed=False))
    )
    if len(pressure) >= 2:
        status = "pressure"
    elif len(watch) >= 2:
        status = "watch"
    elif proxies:
        status = "limited_proxy_context"
    else:
        status = "research_needed"
    return _context(
        status=status,
        supporting=proxies,
        missing=missing,
        hard_gates={
            "spy_rsp_qqq_proxy_auxiliary_only": True,
            "proxy_breadth_does_not_replace_true_breadth": True,
            "single_proxy_cannot_create_pressure": bool(proxies and len(watch) < 2),
        },
    )


def _context(
    *,
    status: str,
    supporting: list[str],
    missing: list[str],
    hard_gates: dict[str, bool],
    pressure_hint: str | None = None,
    source_quality: str | None = None,
) -> dict[str, Any]:
    row_status = _row_status(status)
    ai_context_allowed = row_status not in {
        "missing",
        "research_needed",
        "insufficient_history",
        "insufficient_evidence",
        "not_available",
        "unknown",
    }
    return {
        "status": status,
        "row_status": row_status,
        "pressure_hint": pressure_hint,
        "pressure_row_status": _row_status(pressure_hint or status),
        "source_quality": source_quality,
        "supporting_evidence": sorted(set(supporting)),
        "missing_inputs": sorted(set(missing)),
        "hard_gates": hard_gates,
        "ai_context_allowed": ai_context_allowed,
    }


def _row_status(status: str) -> str:
    if status in {"available", "limited_context", "limited_proxy_context", "none"}:
        return "ok"
    if status == "watch":
        return "watch"
    if status in {"pressure", "elevated"}:
        return "pressure"
    if status == "unavailable":
        return "not_available"
    return status


def _missing_row_status(missing_inputs: list[str]) -> str:
    return "research_needed" if missing_inputs else "ok"


def _source_gated(index: EvidenceIndex, metric_key: str) -> bool:
    row = index.by_metric_key(metric_key)
    if row is None:
        return False
    if not index.is_usable_for_support(
        metric_key,
        require_ai_context_allowed=False,
        require_core_trigger=False,
    ):
        return False
    return _row_value(row, "source_badge") in {"official", "official_fallback", "derived"}


def _usable_proxy(index: EvidenceIndex, metric_key: str) -> bool:
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
