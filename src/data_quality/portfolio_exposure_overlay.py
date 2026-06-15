from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Iterable

from modeling.evidence_index import EvidenceIndex
from modeling.model_output import ModelOutput
from modeling.model_registry import get_model_registry


MODEL_KEY = "portfolio_exposure_overlay_v0"
MODULE_KEY = "portfolio_exposure_overlay"
MODEL_VERSION = "portfolio_exposure_overlay_v0"
FORMULA_VERSION = "stage8_portfolio_exposure_overlay_v0"
BOUNDARY = (
    "Portfolio exposure overlay is a privacy-preserving explanatory layer "
    "that maps sanitized compact portfolio context to macro risk channels. It is not "
    "an optimization layer, action directive, event-odds model, "
    "return-estimation model, or position-level output. It does not expose "
    "private portfolio line items."
)
PRIVATE_INPUT_POLICY = (
    "Uses sanitized compact dashboard context only; private portfolio inputs "
    "remain excluded."
)
PUBLIC_OUTPUT_KEYS = get_model_registry().public_output_keys(MODULE_KEY)
PORTFOLIO_COMPACT_KEYS = (
    "max_deviation_asset",
    "max_deviation_pp",
    "equity_total_deviation_pp",
    "cash_reserve_status",
)
CHANNEL_ORDER = (
    "equity_beta",
    "rates_duration",
    "credit_spread",
    "liquidity_funding",
    "inflation_energy",
    "growth_slowdown",
    "valuation_earnings_breadth",
    "equity_concentration",
    "cash_liquidity_buffer",
    "historical_validation_context",
)
CHANNEL_OUTPUT_KEYS = {
    "equity_beta": "portfolio_exposure_equity_beta_context",
    "rates_duration": "portfolio_exposure_rates_duration_context",
    "credit_spread": "portfolio_exposure_credit_context",
    "liquidity_funding": "portfolio_exposure_liquidity_context",
    "inflation_energy": "portfolio_exposure_inflation_energy_context",
    "valuation_earnings_breadth": "portfolio_exposure_valuation_context",
    "equity_concentration": "portfolio_exposure_concentration_context",
    "cash_liquidity_buffer": "portfolio_exposure_cash_buffer_context",
}
CHANNEL_SUPPORT_KEYS = {
    "equity_beta": (
        "financial_stress_status",
        "pullback_classification",
        "scenario_stress_affected_groups",
        "scenario_stress_transmission_channels",
        "equity_structure_status",
        "breadth_concentration_context_status",
        "sp500_drawdown_3m",
        "nasdaq100_drawdown_3m",
    ),
    "rates_duration": (
        "dgs10",
        "dgs30",
        "dfii10",
        "real_yield_pressure_status",
        "macro_regime_label",
        "scenario_stress_scenarios",
    ),
    "credit_spread": (
        "financial_stress_status",
        "financial_stress_dominant_pressure_source",
        "high_yield_spread",
        "investment_grade_spread",
        "scenario_stress_scenarios",
    ),
    "liquidity_funding": (
        "liquidity_funding_stress_status",
        "policy_plumbing_status",
        "short_term_funding_pressure_status",
        "official_stress_reference_status",
        "scenario_stress_scenarios",
        "historical_validation_module_consistency_summary",
    ),
    "inflation_energy": (
        "inflation_macro_status",
        "core_cpi_yoy",
        "core_pce_yoy",
        "wti_30d_change",
        "brent_30d_change",
        "macro_regime_label",
        "scenario_stress_scenarios",
    ),
    "growth_slowdown": (
        "growth_macro_status",
        "labor_deterioration_status",
        "initial_jobless_claims",
        "continuing_claims",
        "unemployment_rate",
        "scenario_stress_scenarios",
    ),
    "valuation_earnings_breadth": (
        "valuation_context_status",
        "earnings_context_status",
        "valuation_missing_inputs",
        "earnings_missing_inputs",
        "breadth_concentration_missing_inputs",
    ),
    "equity_concentration": (
        "equity_structure_status",
        "breadth_concentration_context_status",
        "equity_structure_supporting_evidence",
        "breadth_concentration_supporting_evidence",
        "scenario_stress_scenarios",
    ),
    "cash_liquidity_buffer": ("cash_reserve_status",),
    "historical_validation_context": (
        "historical_validation_status",
        "historical_validation_coverage_summary",
        "historical_validation_module_consistency_summary",
        "historical_validation_missing_data_summary",
    ),
}
CHANNEL_PORTFOLIO_HINTS = {
    "equity_beta": ("equity", "sp500", "nasdaq", "stock"),
    "rates_duration": ("bond", "duration", "treasury"),
    "credit_spread": ("bond", "credit"),
    "liquidity_funding": ("cash", "liquidity"),
    "inflation_energy": ("energy", "commodity", "gold"),
    "growth_slowdown": ("equity", "stock"),
    "valuation_earnings_breadth": ("equity", "sp500", "nasdaq", "stock"),
    "equity_concentration": ("equity", "sp500", "nasdaq", "stock"),
    "cash_liquidity_buffer": ("cash", "liquidity"),
    "historical_validation_context": (),
}
PRESSURE_VALUES = {"pressure", "stress", "credit_stress", "liquidity_funding_pressure"}
WATCH_VALUES = {
    "watch",
    "limited_evidence",
    "limited_context",
    "mixed_or_transition",
    "rates_pressure",
    "inflation_energy_pressure",
    "growth_slowdown_watch",
    "stagflation_pressure",
}
BLOCKING_STATUSES = {
    "missing",
    "research_needed",
    "insufficient_history",
    "insufficient_evidence",
    "not_available",
    "stale",
}


def build_portfolio_exposure_overlay_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    index = EvidenceIndex(rows)
    portfolio_context = _portfolio_context(index)
    channels = {
        channel: _channel_context(channel, index, portfolio_context)
        for channel in CHANNEL_ORDER
    }
    primary_channels = _primary_channels(channels)
    supporting = sorted(
        {
            key
            for channel in channels.values()
            for key in channel["supporting_evidence"]
        }
    )
    missing = sorted(
        {
            item
            for channel in channels.values()
            for item in channel["missing_inputs"]
        }
    )
    overall_status = _overall_status(portfolio_context, channels)
    return {
        "status": overall_status,
        "channels": channels,
        "primary_channels": primary_channels,
        "supporting_evidence": supporting,
        "missing_inputs": missing,
        "portfolio_context": portfolio_context,
        "input_evidence": _compact_input_evidence(index, supporting),
        "as_of_date": _latest_observation_date(index, supporting),
        "hard_gates": {
            "portfolio_overlay_cannot_trigger_macro_regime": True,
            "portfolio_overlay_cannot_trigger_systemic_stress": True,
            "portfolio_overlay_cannot_change_scenario_severity": True,
            "portfolio_overlay_cannot_create_d15_support": True,
            "portfolio_overlay_cannot_create_d19_availability": True,
            "portfolio_overlay_downstream_only": True,
            "uses_sanitized_portfolio_context_only": True,
            "reads_holdings_line_items": False,
            "returns_holdings_line_items": False,
            "returns_position_weights": False,
            "returns_account_values": False,
        },
        "uses_model_registry": bool(get_model_registry().get(MODULE_KEY)),
        "uses_evidence_index": isinstance(index, EvidenceIndex),
    }


def build_portfolio_exposure_overlay_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    summary = build_portfolio_exposure_overlay_summary(rows)
    now = _utc_now()
    base_status = _row_status(summary["status"])
    ai_allowed = summary["status"] in {"available", "limited_context"} and not _boundary_flags(summary)
    component_contributions = {
        "model_key": MODEL_KEY,
        "model_version": MODEL_VERSION,
        "formula_version": FORMULA_VERSION,
        "channels": summary["channels"],
        "primary_channels": summary["primary_channels"],
        "portfolio_context_status": summary["portfolio_context"]["status"],
        "private_inputs_excluded": summary["portfolio_context"]["private_inputs_excluded"],
        "missing_inputs_visible": bool(summary["missing_inputs"]),
        "private_input_policy": PRIVATE_INPUT_POLICY,
        "hard_gates": summary["hard_gates"],
        "uses_model_registry": summary["uses_model_registry"],
        "uses_evidence_index": summary["uses_evidence_index"],
    }
    values: dict[str, tuple[str, Any, str, bool]] = {
        "portfolio_exposure_overlay_status": (
            "Portfolio exposure overlay status",
            summary["status"],
            base_status,
            ai_allowed,
        ),
        "portfolio_exposure_channel_summary": (
            "Portfolio exposure channel summary",
            _channel_summary_text(summary["channels"]),
            base_status,
            ai_allowed,
        ),
        "portfolio_exposure_primary_channels": (
            "Portfolio exposure primary channels",
            _join(summary["primary_channels"]),
            base_status,
            ai_allowed,
        ),
        "portfolio_exposure_supporting_evidence": (
            "Portfolio exposure supporting evidence",
            _supporting_evidence_text(summary["channels"]),
            base_status,
            ai_allowed,
        ),
        "portfolio_exposure_missing_inputs": (
            "Portfolio exposure missing inputs",
            _join(summary["missing_inputs"]),
            _missing_row_status(summary["missing_inputs"]),
            False,
        ),
        "portfolio_exposure_private_input_policy": (
            "Portfolio exposure private input policy",
            PRIVATE_INPUT_POLICY,
            base_status,
            ai_allowed,
        ),
        "portfolio_exposure_interpretation_boundary": (
            "Portfolio exposure interpretation boundary",
            BOUNDARY,
            base_status,
            ai_allowed,
        ),
        "portfolio_exposure_model_version": (
            "Portfolio exposure model version",
            MODEL_VERSION,
            "ok",
            True,
        ),
        "portfolio_exposure_formula_version": (
            "Portfolio exposure formula version",
            FORMULA_VERSION,
            "ok",
            True,
        ),
        "portfolio_exposure_as_of_date": (
            "Portfolio exposure as-of date",
            summary["as_of_date"] or now[:10],
            "ok",
            True,
        ),
    }
    for channel, metric_key in CHANNEL_OUTPUT_KEYS.items():
        item = summary["channels"][channel]
        values[metric_key] = (
            f"Portfolio exposure {channel.replace('_', ' ')} context",
            item["status"],
            _row_status(item["status"]),
            item["ai_context_allowed"],
        )

    return [
        ModelOutput(
            metric_key=metric_key,
            value=value,
            value_text=str(value),
            status=status,
            source_badge="derived",
            freshness_status="historical" if status != "insufficient_evidence" else "insufficient_history",
            interpretation_boundary=BOUNDARY,
            component_contributions=component_contributions,
            ai_context_allowed=ai_context_allowed,
            model_key=MODEL_KEY,
            module_key=MODULE_KEY,
        ).to_metric_payload(
            display_name=display_name,
            source="local_rules",
            source_series="STAGE8_PORTFOLIO_EXPOSURE_OVERLAY_V0",
            observation_date=summary["as_of_date"],
            generated_at=now,
            missing_reason=None if ai_context_allowed else _missing_reason(status),
            input_evidence=summary["input_evidence"],
            missing_inputs=summary["missing_inputs"],
            ai_context_tier="compact_safe_only",
            trigger_eligibility="overlay_only",
        )
        for metric_key, (display_name, value, status, ai_context_allowed) in values.items()
    ]


def _portfolio_context(index: EvidenceIndex) -> dict[str, Any]:
    available = [
        key
        for key in PORTFOLIO_COMPACT_KEYS
        if index.is_usable_for_support(
            key,
            require_ai_context_allowed=False,
            require_core_trigger=False,
        )
    ]
    asset_value = _row_text(index.by_metric_key("max_deviation_asset"), "value")
    return {
        "status": "available" if available else "private_inputs_excluded",
        "available_metric_keys": available,
        "missing_metric_keys": sorted(set(PORTFOLIO_COMPACT_KEYS) - set(available)),
        "private_inputs_excluded": True,
        "sanitized_compact_context_available": bool(available),
        "asset_bucket_hint": asset_value.lower() if asset_value else None,
    }


def _channel_context(
    channel: str,
    index: EvidenceIndex,
    portfolio_context: dict[str, Any],
) -> dict[str, Any]:
    if not portfolio_context["sanitized_compact_context_available"]:
        return _context(
            status="private_input_excluded",
            supporting=[],
            missing=["sanitized_portfolio_context"],
            ai_context_allowed=False,
            hard_gates={"missing_sanitized_context_not_low_or_high": True},
        )
    support_keys = [
        key
        for key in CHANNEL_SUPPORT_KEYS[channel]
        if index.is_usable_for_support(
            key,
            require_ai_context_allowed=False,
            require_core_trigger=False,
        )
    ]
    missing = [
        key
        for key in CHANNEL_SUPPORT_KEYS[channel]
        if key not in support_keys and key not in PORTFOLIO_COMPACT_KEYS
    ]
    if channel != "historical_validation_context" and _portfolio_hint_matches(
        channel, portfolio_context
    ):
        support_keys.append("sanitized_portfolio_context")
    if channel == "cash_liquidity_buffer" and "cash_reserve_status" not in support_keys:
        return _context(
            status="missing",
            supporting=[],
            missing=["sanitized_cash_buffer_context"],
            ai_context_allowed=False,
            hard_gates={"cash_buffer_context_not_action_directive": True},
        )
    if not support_keys:
        status = "missing"
    elif _has_pressure(index, support_keys):
        status = "pressure"
    elif _has_watch(index, support_keys):
        status = "watch"
    else:
        status = "limited_context"
    return _context(
        status=status,
        supporting=sorted(set(support_keys)),
        missing=missing,
        ai_context_allowed=status in {"limited_context", "watch", "pressure"},
        hard_gates=_channel_hard_gates(channel),
    )


def _context(
    *,
    status: str,
    supporting: list[str],
    missing: list[str],
    ai_context_allowed: bool,
    hard_gates: dict[str, bool],
) -> dict[str, Any]:
    return {
        "status": status,
        "supporting_evidence": sorted(set(supporting)),
        "missing_inputs": sorted(set(missing)),
        "hard_gates": hard_gates,
        "ai_context_allowed": ai_context_allowed,
    }


def _channel_hard_gates(channel: str) -> dict[str, bool]:
    gates = {
        "channel_is_explanatory_overlay_only": True,
        "cannot_trigger_macro_regime": True,
        "cannot_trigger_systemic_stress": True,
        "cannot_change_scenario_severity": True,
        "missing_context_not_low_or_high": True,
    }
    if channel == "cash_liquidity_buffer":
        gates["cash_buffer_context_not_action_directive"] = True
    if channel == "equity_concentration":
        gates["concentration_context_not_action_directive"] = True
    if channel == "rates_duration":
        gates["rates_duration_context_not_action_directive"] = True
    if channel == "credit_spread":
        gates["credit_context_not_action_directive"] = True
    return gates


def _portfolio_hint_matches(channel: str, portfolio_context: dict[str, Any]) -> bool:
    hint = portfolio_context.get("asset_bucket_hint")
    if not hint:
        return False
    return any(token in hint for token in CHANNEL_PORTFOLIO_HINTS[channel])


def _has_pressure(index: EvidenceIndex, metric_keys: Iterable[str]) -> bool:
    return any(_row_signal(index.by_metric_key(key)) in PRESSURE_VALUES for key in metric_keys)


def _has_watch(index: EvidenceIndex, metric_keys: Iterable[str]) -> bool:
    return any(_row_signal(index.by_metric_key(key)) in WATCH_VALUES for key in metric_keys)


def _row_signal(row: Any) -> str:
    value = str(_row_value(row, "value") or "").lower()
    status = str(_row_value(row, "status") or "").lower()
    return value if value in PRESSURE_VALUES | WATCH_VALUES else status


def _overall_status(
    portfolio_context: dict[str, Any],
    channels: dict[str, dict[str, Any]],
) -> str:
    if not portfolio_context["sanitized_compact_context_available"]:
        return "private_inputs_excluded"
    statuses = {item["status"] for item in channels.values()}
    if statuses & {"pressure", "watch"}:
        return "available"
    if statuses & {"limited_context"}:
        return "limited_context"
    return "insufficient_context"


def _primary_channels(channels: dict[str, dict[str, Any]]) -> list[str]:
    ranked = [
        channel
        for channel in CHANNEL_ORDER
        if channels[channel]["status"] in {"pressure", "watch"}
    ]
    if ranked:
        return ranked[:4]
    return [
        channel
        for channel in CHANNEL_ORDER
        if channels[channel]["status"] == "limited_context"
    ][:4]


def _row_status(status: str) -> str:
    if status in {"available", "limited_context"}:
        return "ok"
    if status == "watch":
        return "watch"
    if status == "pressure":
        return "pressure"
    if status in {"private_inputs_excluded", "insufficient_context"}:
        return "insufficient_evidence"
    if status == "missing":
        return "missing"
    return "not_available"


def _missing_row_status(missing_inputs: list[str]) -> str:
    return "insufficient_evidence" if missing_inputs else "ok"


def _missing_reason(status: str) -> str | None:
    if status in {"ok", "watch", "pressure"}:
        return None
    if status == "missing":
        return "missing_sanitized_or_macro_context"
    if status == "insufficient_evidence":
        return "private_inputs_excluded_or_insufficient_context"
    return status


def _compact_input_evidence(
    index: EvidenceIndex,
    metric_keys: Iterable[str],
) -> list[dict[str, Any]]:
    payloads = []
    for metric_key in sorted(set(metric_keys)):
        row = index.by_metric_key(metric_key)
        if row is None:
            continue
        payloads.append(
            {
                "module": _row_value(row, "module"),
                "metric_key": metric_key,
                "status": _row_value(row, "status"),
                "source_badge": _row_value(row, "source_badge"),
                "observation_date": _row_value(row, "observation_date"),
                "freshness_status": _row_value(row, "freshness_status"),
                "trigger_eligibility": _row_value(row, "trigger_eligibility"),
            }
        )
    return payloads


def _latest_observation_date(index: EvidenceIndex, metric_keys: Iterable[str]) -> str | None:
    dates = [
        str(_row_value(index.by_metric_key(metric_key), "observation_date"))
        for metric_key in metric_keys
        if index.by_metric_key(metric_key) is not None
        and _row_value(index.by_metric_key(metric_key), "observation_date")
    ]
    return max(dates) if dates else None


def _channel_summary_text(channels: dict[str, dict[str, Any]]) -> str:
    return "; ".join(f"{channel}={channels[channel]['status']}" for channel in CHANNEL_ORDER)


def _supporting_evidence_text(channels: dict[str, dict[str, Any]]) -> str:
    parts = []
    for channel in CHANNEL_ORDER:
        evidence = [
            key
            for key in channels[channel]["supporting_evidence"]
            if key != "sanitized_portfolio_context"
        ]
        if evidence:
            parts.append(f"{channel}:{','.join(evidence[:4])}")
    return "; ".join(parts) or "none"


def _join(items: list[str]) -> str:
    return ", ".join(items) if items else "none"


def _boundary_flags(payload: Any) -> list[str]:
    text = str(payload).lower()
    forbidden = (
        "crash probability",
        "recession probability",
        "market direction probability",
        "expected return",
        "trade signal",
        "buy",
        "sell",
        "hedge",
        "rebalance",
        "target allocation",
        "target weight",
        "ideal allocation",
        "add position",
        "reduce position",
        "clear position",
        "strategy return",
        "trading performance",
        "sharpe",
        "predicted return",
        "de-risk",
        "rotate into",
        "overweight",
        "underweight",
    )
    return [token for token in forbidden if token in text]


def _row_value(row: Any, field: str) -> Any:
    if isinstance(row, dict):
        return row.get(field)
    return getattr(row, field, None)


def _row_text(row: Any, field: str) -> str | None:
    value = _row_value(row, field)
    if value is None:
        return None
    return str(value)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()
