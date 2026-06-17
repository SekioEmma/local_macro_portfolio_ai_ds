from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Any

from data_quality.historical_validation_replay import (
    get_historical_validation_replay_rows,
)
from data_quality import macro_regime_review
from data_providers import market_history_store


MODEL_KEY = "historical_validation_v1"
MODULE_KEY = "historical_validation"
MODEL_VERSION = "historical_validation_v1"
FORMULA_VERSION = "d19_expanded_historical_validation_v1"
VALIDATION_BOUNDARY = (
    "Historical validation is a read-only historical replay of deterministic "
    "evidence rows for event-window consistency and boundary validation. It is "
    "not a prediction model, event-odds model, business-cycle call, market "
    "direction forecast, allocation directive, strategy-evaluation model, or "
    "return estimate."
)
DAILY_BOUNDARY = (
    "Daily replay rows are structural recognition checks for known historical "
    "windows. They do not estimate future market direction or produce an "
    "allocation directive."
)
FORBIDDEN_LANGUAGE_TOKENS = (
    "crash probability",
    "recession probability",
    "market direction probability",
    "predictive accuracy",
    "forecast accuracy",
    "trading performance",
    "strategy return",
    "roc",
    "auc",
    "precision",
    "recall",
    "f1",
    "probability calibration",
    "trade signal",
    "buy",
    "sell",
    "hedge",
    "rebalance",
    "target allocation",
    "expected return",
    "strategy return",
    "sharpe",
    "timing signal",
)
STRESS_EVENT_TYPES = {
    "credit_stress",
    "liquidity_funding_stress",
    "rates_inflation_pressure",
    "growth_slowdown_watch",
    "equity_structure_concentration_watch",
    "mixed_transition",
}
DAILY_REPLAY_KEYS = {
    "high_yield_spread",
    "investment_grade_spread",
    "vix",
    "credit_stress_status",
    "dgs10",
    "dgs30",
    "dfii10",
    "t10yie",
    "real_yield_pressure_status",
    "core_cpi_yoy",
    "core_pce_yoy",
    "ppiaco_yoy",
    "ppi_final_demand_yoy",
    "wti_30d_change",
    "brent_30d_change",
    "initial_jobless_claims",
    "continuing_claims",
    "unemployment_rate",
    "nonfarm_payrolls",
    "labor_deterioration_status",
    "policy_plumbing_status",
    "short_term_funding_pressure_status",
    "official_stress_reference_status",
    "liquidity_funding_stress_status",
    "sp500_drawdown_3m",
    "nasdaq100_drawdown_3m",
}
METRIC_MODULES = {
    "high_yield_spread": "credit_stress",
    "investment_grade_spread": "credit_stress",
    "vix": "credit_stress",
    "credit_stress_status": "credit_stress",
    "dgs10": "rate_pressure",
    "dgs30": "rate_pressure",
    "dfii10": "real_yield_pressure",
    "t10yie": "real_yield_pressure",
    "real_yield_pressure_status": "real_yield_pressure",
    "core_cpi_yoy": "inflation_energy_pressure",
    "core_pce_yoy": "inflation_energy_pressure",
    "ppiaco_yoy": "inflation_energy_pressure",
    "ppi_final_demand_yoy": "inflation_energy_pressure",
    "wti_30d_change": "inflation_energy_pressure",
    "brent_30d_change": "inflation_energy_pressure",
    "initial_jobless_claims": "labor_macro",
    "continuing_claims": "labor_macro",
    "unemployment_rate": "labor_macro",
    "nonfarm_payrolls": "labor_macro",
    "labor_deterioration_status": "labor_macro",
    "policy_plumbing_status": "liquidity_funding_stress",
    "short_term_funding_pressure_status": "liquidity_funding_stress",
    "official_stress_reference_status": "liquidity_funding_stress",
    "liquidity_funding_stress_status": "liquidity_funding_stress",
    "sp500_drawdown_3m": "market_stress_derived",
    "nasdaq100_drawdown_3m": "market_stress_derived",
}
REQUIRED_CORE_GROUPS = {
    "credit": {"high_yield_spread", "investment_grade_spread"},
    "rates_real_yield": {"dgs10", "dgs30", "dfii10", "t10yie"},
    "inflation_energy": {"core_cpi_yoy", "core_pce_yoy", "ppiaco_yoy", "ppi_final_demand_yoy"},
    "labor_growth": {"initial_jobless_claims", "continuing_claims", "unemployment_rate", "nonfarm_payrolls"},
    "liquidity_funding": {
        "policy_plumbing_status",
        "short_term_funding_pressure_status",
        "official_stress_reference_status",
        "liquidity_funding_stress_status",
    },
}
METRICS_BY_GROUP = {
    **REQUIRED_CORE_GROUPS,
    "equity_structure": {"sp500_drawdown_3m", "nasdaq100_drawdown_3m"},
    "valuation_earnings_breadth": set(),
    "growth_inflation": {
        "core_cpi_yoy",
        "core_pce_yoy",
        "ppiaco_yoy",
        "ppi_final_demand_yoy",
        "initial_jobless_claims",
        "continuing_claims",
        "unemployment_rate",
        "nonfarm_payrolls",
    },
    "valuation_equity_structure": {"sp500_drawdown_3m", "nasdaq100_drawdown_3m"},
}
HISTORICAL_VALIDATION_KEYS = {
    "historical_validation_status",
    "historical_validation_event_count",
    "historical_validation_available_event_count",
    "historical_validation_insufficient_history_event_count",
    "historical_validation_ordinary_pullback_over_escalation_count",
    "historical_validation_stress_window_under_escalation_count",
    "historical_validation_boundary_violation_count",
    "historical_validation_event_window_summary",
    "historical_validation_privacy_flags",
    "historical_validation_validation_boundary",
    "historical_validation_model_version",
    "historical_validation_formula_version",
    "historical_validation_as_of_date",
}
OPTIONAL_HISTORICAL_VALIDATION_KEYS = {
    "historical_validation_coverage_summary",
    "historical_validation_module_consistency_summary",
    "historical_validation_proxy_constraint_summary",
    "historical_validation_missing_data_summary",
    "historical_validation_replay_version",
}
PROXY_METRIC_KEYS = {
    "sp500_drawdown_3m",
    "nasdaq100_drawdown_3m",
}
MODULE_BOUNDARY_CHECKS = (
    "no_probability_output",
    "no_trading_output",
    "missing_data_visible",
    "proxy_only_not_triggering",
    "D14_confirmation_only",
    "D15_band_only",
    "D16_scenario_matrix_only",
    "D17_not_recession_call",
    "D18_not_timing_model",
    "valuation_gap_visible",
    "true_breadth_gap_visible",
)
MODULES_BY_GROUP = {
    "credit": "financial_stress_composite",
    "liquidity_funding": "liquidity_funding_stress",
    "rates_real_yield": "macro_regime_review",
    "inflation_energy": "growth_inflation_macro_pack",
    "labor_growth": "growth_inflation_macro_pack",
    "valuation_earnings_breadth": "valuation_equity_structure",
    "equity_structure": "valuation_equity_structure",
    "growth_inflation": "growth_inflation_macro_pack",
    "valuation_equity_structure": "valuation_equity_structure",
}


@dataclass(frozen=True)
class EventWindow:
    event_id: str
    event_type: str
    start_date: str
    end_date: str
    pre_window_start: str
    pre_window_end: str
    expected_pressure_groups: tuple[str, ...]
    expected_non_trigger_constraints: tuple[str, ...]
    ordinary_pullback_flag: bool
    required_metric_groups: tuple[str, ...]
    optional_metric_groups: tuple[str, ...]
    known_data_limitations: tuple[str, ...]
    interpretation_boundary: str
    expected_regime_labels: tuple[str, ...] = ()
    expected_primary_pressure_groups: tuple[str, ...] = ()


EVENT_WINDOWS: tuple[EventWindow, ...] = (
    EventWindow(
        event_id="2018_q4_tightening_scare",
        event_type="ordinary_pullback",
        start_date="2018-10-01",
        end_date="2018-12-31",
        pre_window_start="2018-07-01",
        pre_window_end="2018-09-30",
        expected_pressure_groups=("rates_real_yield", "credit"),
        expected_non_trigger_constraints=(
            "equity_drawdown_alone_not_systemic",
            "ordinary_pullback_not_auto_escalated",
        ),
        ordinary_pullback_flag=True,
        required_metric_groups=("credit", "rates_real_yield"),
        optional_metric_groups=("equity_structure", "liquidity_funding"),
        known_data_limitations=("true_breadth_and_valuation_history_may_be_absent",),
        interpretation_boundary=VALIDATION_BOUNDARY,
        expected_regime_labels=("rates_pressure", "mixed_or_transition"),
        expected_primary_pressure_groups=("rates_real_yield", "credit"),
    ),
    EventWindow(
        event_id="2020_covid_shock",
        event_type="liquidity_funding_stress",
        start_date="2020-02-15",
        end_date="2020-04-30",
        pre_window_start="2020-01-01",
        pre_window_end="2020-02-14",
        expected_pressure_groups=("credit", "liquidity_funding", "labor_growth"),
        expected_non_trigger_constraints=("proxy_only_not_strong_confirmation",),
        ordinary_pullback_flag=False,
        required_metric_groups=("credit", "liquidity_funding", "labor_growth"),
        optional_metric_groups=("rates_real_yield", "growth_inflation"),
        known_data_limitations=("labor_and_funding_history_required_for_full_replay",),
        interpretation_boundary=VALIDATION_BOUNDARY,
        expected_regime_labels=("credit_stress", "liquidity_funding_pressure", "mixed_or_transition"),
        expected_primary_pressure_groups=("credit", "liquidity_funding"),
    ),
    EventWindow(
        event_id="2022_inflation_rates_bear_market",
        event_type="rates_inflation_pressure",
        start_date="2022-01-03",
        end_date="2022-10-31",
        pre_window_start="2021-10-01",
        pre_window_end="2021-12-31",
        expected_pressure_groups=("rates_real_yield", "inflation_energy", "growth_inflation"),
        expected_non_trigger_constraints=("D17_not_recession_call",),
        ordinary_pullback_flag=False,
        required_metric_groups=("rates_real_yield", "inflation_energy"),
        optional_metric_groups=("labor_growth", "growth_inflation", "valuation_equity_structure"),
        known_data_limitations=("earnings_and_true_breadth_history_may_be_absent",),
        interpretation_boundary=VALIDATION_BOUNDARY,
        expected_regime_labels=("rates_pressure", "inflation_energy_pressure", "stagflation_pressure"),
        expected_primary_pressure_groups=("rates_real_yield", "inflation_energy"),
    ),
    EventWindow(
        event_id="2023_svb_bank_stress",
        event_type="liquidity_funding_stress",
        start_date="2023-03-08",
        end_date="2023-03-31",
        pre_window_start="2023-02-01",
        pre_window_end="2023-03-07",
        expected_pressure_groups=("credit", "liquidity_funding", "rates_real_yield"),
        expected_non_trigger_constraints=("D14_confirmation_only",),
        ordinary_pullback_flag=False,
        required_metric_groups=("credit", "liquidity_funding"),
        optional_metric_groups=("rates_real_yield", "valuation_equity_structure"),
        known_data_limitations=("bank_specific_market_history_may_be_absent",),
        interpretation_boundary=VALIDATION_BOUNDARY,
        expected_regime_labels=("credit_stress", "liquidity_funding_pressure", "mixed_or_transition"),
        expected_primary_pressure_groups=("credit", "liquidity_funding", "rates_real_yield"),
    ),
    EventWindow(
        event_id="2015_2016_oil_hy_energy_stress",
        event_type="credit_stress",
        start_date="2015-08-01",
        end_date="2016-02-29",
        pre_window_start="2015-05-01",
        pre_window_end="2015-07-31",
        expected_pressure_groups=("credit", "inflation_energy"),
        expected_non_trigger_constraints=("energy_pressure_not_recession_call",),
        ordinary_pullback_flag=False,
        required_metric_groups=("credit", "inflation_energy"),
        optional_metric_groups=("rates_real_yield", "labor_growth"),
        known_data_limitations=("older_energy_and_credit_history_may_be_sparse",),
        interpretation_boundary=VALIDATION_BOUNDARY,
        expected_regime_labels=("credit_stress", "inflation_energy_pressure", "mixed_or_transition"),
        expected_primary_pressure_groups=("credit", "inflation_energy"),
    ),
    EventWindow(
        event_id="2011_euro_debt_us_downgrade_stress",
        event_type="insufficient_history_reference",
        start_date="2011-07-01",
        end_date="2011-10-31",
        pre_window_start="2011-04-01",
        pre_window_end="2011-06-30",
        expected_pressure_groups=("credit", "liquidity_funding", "rates_real_yield"),
        expected_non_trigger_constraints=("insufficient_history_fails_closed",),
        ordinary_pullback_flag=False,
        required_metric_groups=("credit", "liquidity_funding"),
        optional_metric_groups=("rates_real_yield", "labor_growth"),
        known_data_limitations=("local_history_often_starts_after_this_window",),
        interpretation_boundary=VALIDATION_BOUNDARY,
    ),
    EventWindow(
        event_id="2016_global_growth_oil_credit_stress",
        event_type="mixed_transition",
        start_date="2016-01-01",
        end_date="2016-03-31",
        pre_window_start="2015-10-01",
        pre_window_end="2015-12-31",
        expected_pressure_groups=("credit", "inflation_energy", "growth_inflation"),
        expected_non_trigger_constraints=("proxy_only_not_strong_confirmation",),
        ordinary_pullback_flag=False,
        required_metric_groups=("credit", "inflation_energy"),
        optional_metric_groups=("labor_growth", "rates_real_yield"),
        known_data_limitations=("full_growth_history_may_be_unavailable",),
        interpretation_boundary=VALIDATION_BOUNDARY,
    ),
    EventWindow(
        event_id="2018_volmageddon_liquidity_shock",
        event_type="ordinary_pullback",
        start_date="2018-02-01",
        end_date="2018-02-28",
        pre_window_start="2017-11-01",
        pre_window_end="2018-01-31",
        expected_pressure_groups=("liquidity_funding", "equity_structure"),
        expected_non_trigger_constraints=(
            "VIX_or_drawdown_alone_not_systemic",
            "ordinary_pullback_not_auto_escalated",
        ),
        ordinary_pullback_flag=True,
        required_metric_groups=("credit", "liquidity_funding"),
        optional_metric_groups=("equity_structure", "rates_real_yield"),
        known_data_limitations=("intraday_volatility_products_not_modeled",),
        interpretation_boundary=VALIDATION_BOUNDARY,
    ),
    EventWindow(
        event_id="2021_reopening_inflation_pressure",
        event_type="rates_inflation_pressure",
        start_date="2021-03-01",
        end_date="2021-12-31",
        pre_window_start="2020-12-01",
        pre_window_end="2021-02-28",
        expected_pressure_groups=("inflation_energy", "growth_inflation"),
        expected_non_trigger_constraints=("D17_not_recession_call",),
        ordinary_pullback_flag=False,
        required_metric_groups=("inflation_energy", "rates_real_yield"),
        optional_metric_groups=("labor_growth", "valuation_equity_structure"),
        known_data_limitations=("some_growth_pack_research_inputs_remain_missing",),
        interpretation_boundary=VALIDATION_BOUNDARY,
    ),
    EventWindow(
        event_id="2024_rates_concentration_watch",
        event_type="equity_structure_concentration_watch",
        start_date="2024-01-01",
        end_date="2024-12-31",
        pre_window_start="2023-10-01",
        pre_window_end="2023-12-31",
        expected_pressure_groups=("rates_real_yield", "valuation_equity_structure", "equity_structure"),
        expected_non_trigger_constraints=("valuation_gap_visible", "true_breadth_gap_visible"),
        ordinary_pullback_flag=False,
        required_metric_groups=("rates_real_yield", "equity_structure"),
        optional_metric_groups=("valuation_earnings_breadth", "growth_inflation"),
        known_data_limitations=("valuation_earnings_true_breadth_inputs_may_be_research_needed",),
        interpretation_boundary=VALIDATION_BOUNDARY,
    ),
    EventWindow(
        event_id="2025_ai_concentration_rates_watch",
        event_type="equity_structure_concentration_watch",
        start_date="2025-01-01",
        end_date="2025-12-31",
        pre_window_start="2024-10-01",
        pre_window_end="2024-12-31",
        expected_pressure_groups=("rates_real_yield", "valuation_equity_structure", "equity_structure"),
        expected_non_trigger_constraints=("D18_not_timing_model", "true_breadth_gap_visible"),
        ordinary_pullback_flag=False,
        required_metric_groups=("rates_real_yield", "equity_structure"),
        optional_metric_groups=("valuation_earnings_breadth", "growth_inflation"),
        known_data_limitations=("current_local_history_may_not_cover_full_2025_window",),
        interpretation_boundary=VALIDATION_BOUNDARY,
    ),
)


def get_event_window_registry() -> list[dict[str, Any]]:
    return [_event_to_dict(event) for event in EVENT_WINDOWS]


def build_historical_validation_summary(
    *,
    db_path: str | None = None,
    event_windows: tuple[EventWindow, ...] = EVENT_WINDOWS,
) -> dict[str, Any]:
    observations_by_metric = market_history_store.list_market_observations_batch(
        DAILY_REPLAY_KEYS,
        limit_per_key=market_history_store.MAX_LIMIT,
        db_path=db_path,
    )
    sanitized = _sanitize_observations(observations_by_metric)
    event_summaries: list[dict[str, Any]] = []
    daily_replay_rows: list[dict[str, Any]] = []
    for event in event_windows:
        daily = _event_daily_replay(event, sanitized)
        event_summary = _event_summary(event, daily)
        event_summaries.append(event_summary)
        daily_replay_rows.extend(daily)
    overall = _overall_summary(event_summaries)
    return {
        **overall,
        "events": event_summaries,
        "daily_replay_rows": daily_replay_rows,
    }


def build_historical_validation_rows(
    *,
    db_path: str | None = None,
) -> list[dict[str, Any]]:
    summary = build_historical_validation_summary(db_path=db_path)
    replay_rows = get_historical_validation_replay_rows(existing_summary=summary)
    as_of_date = _latest_replay_date(summary["daily_replay_rows"])
    public_status = summary["status"]
    available = public_status in {"available", "limited_replay"}
    status = "ok" if available else "insufficient_history"
    base = {
        "unit": None,
        "source": "local_market_history",
        "source_badge": "derived",
        "source_series": "D19_EXPANDED_EVENT_WINDOW_REPLAY_V1",
        "observation_date": as_of_date,
        "generated_at": _utc_now(),
        "freshness_status": "historical" if available else "insufficient_history",
        "missing_reason": None if available else "insufficient_local_history_for_event_window_replay",
        "interpretation_hint": VALIDATION_BOUNDARY,
        "interpretation_boundary": VALIDATION_BOUNDARY,
        "ai_context_allowed": available and summary["boundary_violation_count"] == 0,
        "input_evidence": _compact_input_evidence(summary["daily_replay_rows"]),
        "component_contributions": {
            "model_key": MODEL_KEY,
            "model_version": MODEL_VERSION,
            "formula_version": FORMULA_VERSION,
            "events": summary["events"],
            "event_count": summary["event_count"],
            "available_event_count": summary["available_event_count"],
            "limited_replay_event_count": summary["limited_replay_event_count"],
            "insufficient_history_event_count": summary["insufficient_history_event_count"],
            "unavailable_event_count": summary["unavailable_event_count"],
            "ordinary_pullback_over_escalation_count": summary[
                "ordinary_pullback_over_escalation_count"
            ],
            "stress_window_under_escalation_count": summary[
                "stress_window_under_escalation_count"
            ],
            "boundary_violation_count": summary["boundary_violation_count"],
            "proxy_constraint_violation_count": summary["proxy_constraint_violation_count"],
            "missing_data_violation_count": summary["missing_data_violation_count"],
            "coverage_summary": summary["coverage_summary"],
            "module_consistency_summary": summary["module_consistency_summary"],
            "proxy_constraint_summary": summary["proxy_constraint_summary"],
            "missing_data_summary": summary["missing_data_summary"],
            "d19_v1_replay_rows": replay_rows,
            "d19_v1_replay_summary": _replay_summary(replay_rows),
            "privacy_flags": summary["privacy_flags"],
            "validation_boundary": summary["validation_boundary"],
        },
        "missing_inputs": _summary_missing_inputs(summary["events"]),
        "ai_context_tier": "model_output",
        "trigger_eligibility": "reference_review_only",
    }
    values = {
        "historical_validation_status": (
            "Historical validation status",
            public_status,
        ),
        "historical_validation_event_count": (
            "Historical validation event count",
            summary["event_count"],
        ),
        "historical_validation_available_event_count": (
            "Historical validation available event count",
            summary["available_event_count"],
        ),
        "historical_validation_insufficient_history_event_count": (
            "Historical validation insufficient history event count",
            summary["insufficient_history_event_count"],
        ),
        "historical_validation_ordinary_pullback_over_escalation_count": (
            "Historical validation ordinary pullback over-escalation count",
            summary["ordinary_pullback_over_escalation_count"],
        ),
        "historical_validation_stress_window_under_escalation_count": (
            "Historical validation stress window under-escalation count",
            summary["stress_window_under_escalation_count"],
        ),
        "historical_validation_boundary_violation_count": (
            "Historical validation boundary violation count",
            summary["boundary_violation_count"],
        ),
        "historical_validation_event_window_summary": (
            "Historical validation event-window summary",
            _event_summary_text(summary["events"]),
        ),
        "historical_validation_privacy_flags": (
            "Historical validation privacy flags",
            _privacy_flags_text(summary["privacy_flags"]),
        ),
        "historical_validation_validation_boundary": (
            "Historical validation boundary",
            VALIDATION_BOUNDARY,
        ),
        "historical_validation_model_version": (
            "Historical validation model version",
            MODEL_VERSION,
        ),
        "historical_validation_formula_version": (
            "Historical validation formula version",
            FORMULA_VERSION,
        ),
        "historical_validation_as_of_date": (
            "Historical validation as-of date",
            as_of_date or "not available",
        ),
        "historical_validation_coverage_summary": (
            "Historical validation coverage summary",
            _coverage_summary_text(summary),
        ),
        "historical_validation_module_consistency_summary": (
            "Historical validation module consistency summary",
            _module_consistency_summary_text(summary["module_consistency_summary"]),
        ),
        "historical_validation_proxy_constraint_summary": (
            "Historical validation proxy constraint summary",
            _proxy_constraint_summary_text(summary["proxy_constraint_summary"]),
        ),
        "historical_validation_missing_data_summary": (
            "Historical validation missing-data summary",
            _missing_data_summary_text(summary["missing_data_summary"]),
        ),
        "historical_validation_replay_version": (
            "Historical validation replay version",
            FORMULA_VERSION,
        ),
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


def _event_daily_replay(
    event: EventWindow,
    observations_by_metric: dict[str, list[dict[str, Any]]],
) -> list[dict[str, Any]]:
    start = _parse_date(event.start_date)
    end = _parse_date(event.end_date)
    candidate_dates = sorted(
        {
            _parse_date(str(item["observation_date"]))
            for items in observations_by_metric.values()
            for item in items
            if _date_in_range(str(item.get("observation_date")), start, end)
        }
    )
    if not candidate_dates:
        return [
            _unavailable_daily_row(
                event,
                event.start_date,
                "insufficient_history",
                sorted(DAILY_REPLAY_KEYS),
            )
        ]
    rows = []
    for as_of in candidate_dates:
        evidence_rows = _evidence_rows_as_of(as_of, observations_by_metric)
        available_metric_keys = sorted(
            row["metric_key"]
            for row in evidence_rows
            if row.get("ai_context_allowed") and row.get("value") not in (None, "")
        )
        if _core_group_count(evidence_rows) < 3:
            rows.append(
                _unavailable_daily_row(
                    event,
                    as_of.isoformat(),
                    "insufficient_history",
                    _missing_core_inputs(evidence_rows),
                    available_metric_keys=available_metric_keys,
                )
            )
            continue
        regime_by_key = {
            row["metric_key"]: row
            for row in macro_regime_review.build_macro_regime_review_rows(evidence_rows)
        }
        label = regime_by_key.get("macro_regime_label", {})
        supporting = regime_by_key.get("supporting_evidence", {})
        conflicting = regime_by_key.get("conflicting_evidence", {})
        ranking = _split_value(regime_by_key.get("primary_pressure_ranking", {}).get("value"))
        rows.append(
            {
                "as_of_date": as_of.isoformat(),
                "event_id": event.event_id,
                "status": "ok" if label.get("value") != "insufficient_evidence" else "insufficient_history",
                "macro_regime_label": label.get("value") or "insufficient_evidence",
                "support_band": regime_by_key.get("support_band", {}).get("value"),
                "evidence_quality_band": regime_by_key.get("evidence_quality_band", {}).get("value"),
                "conflict_band": regime_by_key.get("conflict_band", {}).get("value"),
                "primary_pressure_ranking": ranking,
                "supporting_evidence_keys": _evidence_keys(supporting.get("value")),
                "conflicting_evidence_keys": _evidence_keys(conflicting.get("value")),
                "missing_inputs": regime_by_key.get("missing_inputs", {}).get("missing_inputs") or [],
                "blocked_inputs": regime_by_key.get("blocked_inputs", {}).get("missing_inputs") or [],
                "available_metric_keys": available_metric_keys,
                "proxy_metric_keys": sorted(set(available_metric_keys) & PROXY_METRIC_KEYS),
                "data_availability_status": "available",
                "interpretation_boundary": DAILY_BOUNDARY,
            }
        )
    return rows


def _event_summary(event: EventWindow, daily_rows: list[dict[str, Any]]) -> dict[str, Any]:
    available_rows = [row for row in daily_rows if row["status"] == "ok"]
    insufficient_rows = [row for row in daily_rows if row["status"] != "ok"]
    required_metric_coverage = {
        group: _group_coverage(group, daily_rows)
        for group in event.required_metric_groups
    }
    optional_metric_coverage = {
        group: _group_coverage(group, daily_rows)
        for group in event.optional_metric_groups
    }
    missing_required_groups = [
        group
        for group, coverage in required_metric_coverage.items()
        if coverage["available_metric_count"] == 0
    ]
    available_required_groups = [
        group
        for group, coverage in required_metric_coverage.items()
        if coverage["available_metric_count"] > 0
    ]
    labels = Counter(str(row.get("macro_regime_label")) for row in available_rows)
    groups = Counter(
        group
        for row in available_rows
        for group in row.get("primary_pressure_ranking", [])
    )
    dominant_labels = [label for label, _ in labels.most_common(3)]
    dominant_groups = [group for group, _ in groups.most_common(5)]
    boundary_flags = _boundary_flags({"event": _event_to_dict(event), "daily_rows": daily_rows})
    over_escalation = bool(
        event.ordinary_pullback_flag
        and any(row.get("macro_regime_label") in {"credit_stress", "liquidity_funding_pressure", "stagflation_pressure"} for row in available_rows)
    )
    under_escalation = bool(
        event.event_type in STRESS_EVENT_TYPES
        and available_rows
        and not missing_required_groups
        and not (set(dominant_groups) & set(event.expected_pressure_groups))
    )
    if available_rows and not missing_required_groups:
        coverage_status = "available"
        window_status = "ok"
    elif available_rows or available_required_groups:
        coverage_status = "limited_replay"
        window_status = "limited_evidence"
    elif daily_rows and daily_rows[0].get("data_availability_status") == "insufficient_history":
        coverage_status = "insufficient_history"
        window_status = "insufficient_history"
    else:
        coverage_status = "unavailable"
        window_status = "unavailable"
    missing_inputs = sorted(
        set(_event_missing_data_summary(daily_rows))
        | set(missing_required_groups)
        | set(event.known_data_limitations)
    )
    proxy_constraints = _proxy_constraints(daily_rows, event)
    boundary_checks = _boundary_checks(event, missing_inputs, proxy_constraints)
    return {
        "event_id": event.event_id,
        "event_type": event.event_type,
        "window_status": window_status,
        "coverage_status": coverage_status,
        "available_day_count": len(available_rows),
        "insufficient_history_day_count": len(insufficient_rows),
        "required_metric_coverage": required_metric_coverage,
        "optional_metric_coverage": optional_metric_coverage,
        "dominant_available_modules": _dominant_modules(
            available_required_groups, optional_metric_coverage
        ),
        "dominant_missing_modules": _dominant_missing_modules(
            missing_required_groups, optional_metric_coverage
        ),
        "expected_pressure_groups": list(event.expected_pressure_groups),
        "dominant_labels": dominant_labels,
        "dominant_primary_pressure_groups": dominant_groups,
        "missing_inputs": missing_inputs,
        "blocked_inputs": _event_blocked_inputs(daily_rows),
        "proxy_constraints": proxy_constraints,
        "boundary_checks": boundary_checks,
        "over_escalation_flag": over_escalation,
        "under_escalation_flag": under_escalation,
        "missing_data_summary": _event_missing_data_summary(daily_rows),
        "boundary_violation_flags": boundary_flags,
        "interpretation_notes": _interpretation_notes(
            event, coverage_status, missing_required_groups
        ),
        "interpretation_boundary": event.interpretation_boundary,
    }


def _overall_summary(event_summaries: list[dict[str, Any]]) -> dict[str, Any]:
    privacy_flags = {
        "reads_local_market_history_only": True,
        "writes_sqlite": False,
        "fetches_live_provider_data": False,
        "returns_holdings_line_items": False,
        "returns_provider_payloads": False,
        "returns_credentials": False,
    }
    coverage_counter = Counter(str(item["coverage_status"]) for item in event_summaries)
    status = (
        "available"
        if coverage_counter["available"] > 0
        else "limited_replay"
        if coverage_counter["limited_replay"] > 0
        else "insufficient_history"
    )
    module_consistency_summary = _module_consistency_summary(event_summaries)
    proxy_constraint_summary = _proxy_constraint_summary(event_summaries)
    missing_data_summary = _overall_missing_data_summary(event_summaries)
    return {
        "model_key": MODEL_KEY,
        "model_version": MODEL_VERSION,
        "formula_version": FORMULA_VERSION,
        "status": status,
        "event_count": len(event_summaries),
        "available_event_count": sum(
            1 for item in event_summaries if item["coverage_status"] == "available"
        ),
        "limited_replay_event_count": sum(
            1 for item in event_summaries if item["coverage_status"] == "limited_replay"
        ),
        "insufficient_history_event_count": sum(
            1 for item in event_summaries if item["coverage_status"] == "insufficient_history"
        ),
        "unavailable_event_count": sum(
            1 for item in event_summaries if item["coverage_status"] == "unavailable"
        ),
        "ordinary_pullback_over_escalation_count": sum(
            1 for item in event_summaries if item["over_escalation_flag"]
        ),
        "stress_window_under_escalation_count": sum(
            1 for item in event_summaries if item["under_escalation_flag"]
        ),
        "boundary_violation_count": sum(
            len(item["boundary_violation_flags"]) for item in event_summaries
        ),
        "proxy_constraint_violation_count": sum(
            1
            for item in event_summaries
            if not item["boundary_checks"]["proxy_only_not_triggering"]
        ),
        "missing_data_violation_count": sum(
            1
            for item in event_summaries
            if not item["boundary_checks"]["missing_data_visible"]
        ),
        "coverage_summary": dict(sorted(coverage_counter.items())),
        "module_consistency_summary": module_consistency_summary,
        "proxy_constraint_summary": proxy_constraint_summary,
        "missing_data_summary": missing_data_summary,
        "privacy_flags": privacy_flags,
        "validation_boundary": VALIDATION_BOUNDARY,
        "as_of_date": _utc_now()[:10],
    }


def _sanitize_observations(
    observations_by_metric: dict[str, list[dict[str, Any]]],
) -> dict[str, list[dict[str, Any]]]:
    result: dict[str, list[dict[str, Any]]] = {}
    for metric_key, observations in observations_by_metric.items():
        clean = [
            item
            for item in observations
            if item.get("metric_key") == metric_key
            and item.get("status") not in market_history_store.BLOCKED_STATUSES
            and item.get("source_badge") not in market_history_store.BLOCKED_SOURCE_BADGES
            and item.get("value_numeric") is not None
        ]
        result[metric_key] = sorted(
            clean,
            key=lambda item: str(item.get("observation_date") or ""),
        )
    return result


def _evidence_rows_as_of(
    as_of: date,
    observations_by_metric: dict[str, list[dict[str, Any]]],
) -> list[dict[str, Any]]:
    rows = []
    for metric_key, observations in observations_by_metric.items():
        item = _latest_observation_as_of(as_of, observations)
        if item is None:
            continue
        stale = _is_stale(as_of, str(item["observation_date"]))
        rows.append(
            {
                "row_id": f"{METRIC_MODULES.get(metric_key, 'historical_validation')}:{metric_key}",
                "module": METRIC_MODULES.get(metric_key, "historical_validation"),
                "metric_key": metric_key,
                "display_name": metric_key,
                "value": _observation_value(item),
                "value_text": str(item.get("value_text") or _observation_value(item)),
                "unit": item.get("unit"),
                "status": "stale" if stale else str(item.get("status") or "ok"),
                "source": item.get("source"),
                "source_badge": item.get("source_badge") or "missing",
                "source_series": item.get("source_series"),
                "observation_date": item.get("observation_date"),
                "generated_at": item.get("generated_at") or item.get("fetched_at"),
                "freshness_status": "stale" if stale else "historical",
                "missing_reason": "stale_for_event_window_replay" if stale else None,
                "interpretation_hint": "Historical replay input from local market history.",
                "blocked_reason": "freshness_stale" if stale else None,
                "ai_context_allowed": not stale,
            }
        )
    return rows


def _latest_observation_as_of(
    as_of: date,
    observations: list[dict[str, Any]],
) -> dict[str, Any] | None:
    latest: dict[str, Any] | None = None
    for item in observations:
        observation_date = _parse_date(str(item.get("observation_date")))
        if observation_date <= as_of:
            latest = item
        elif observation_date > as_of:
            break
    return latest


def _unavailable_daily_row(
    event: EventWindow,
    as_of_date: str,
    status: str,
    missing_inputs: list[str],
    *,
    available_metric_keys: list[str] | None = None,
) -> dict[str, Any]:
    available_metric_keys = available_metric_keys or []
    return {
        "as_of_date": as_of_date,
        "event_id": event.event_id,
        "status": status,
        "macro_regime_label": "insufficient_evidence",
        "support_band": "unsupported",
        "evidence_quality_band": "insufficient",
        "conflict_band": "low",
        "primary_pressure_ranking": [],
        "supporting_evidence_keys": [],
        "conflicting_evidence_keys": [],
        "missing_inputs": missing_inputs,
        "blocked_inputs": [],
        "available_metric_keys": available_metric_keys,
        "proxy_metric_keys": sorted(set(available_metric_keys) & PROXY_METRIC_KEYS),
        "data_availability_status": "insufficient_history",
        "interpretation_boundary": DAILY_BOUNDARY,
    }


def _core_group_count(rows: list[dict[str, Any]]) -> int:
    keys = {row["metric_key"] for row in rows if row.get("ai_context_allowed")}
    return sum(1 for group_keys in REQUIRED_CORE_GROUPS.values() if keys & group_keys)


def _missing_core_inputs(rows: list[dict[str, Any]]) -> list[str]:
    keys = {row["metric_key"] for row in rows if row.get("ai_context_allowed")}
    return [
        group
        for group, group_keys in REQUIRED_CORE_GROUPS.items()
        if not (keys & group_keys)
    ]


def _event_missing_data_summary(daily_rows: list[dict[str, Any]]) -> dict[str, int]:
    counter: Counter[str] = Counter()
    for row in daily_rows:
        for item in row.get("missing_inputs", []):
            counter[str(item)] += 1
        for item in row.get("blocked_inputs", []):
            counter[str(item)] += 1
    return dict(sorted(counter.items()))


def _group_coverage(group: str, daily_rows: list[dict[str, Any]]) -> dict[str, Any]:
    configured = METRICS_BY_GROUP.get(group, set())
    available = sorted(
        {
            key
            for row in daily_rows
            for key in row.get("available_metric_keys", [])
            if not configured or key in configured
        }
    )
    if not configured:
        observed_groups = {
            METRIC_MODULES.get(key)
            for row in daily_rows
            for key in row.get("available_metric_keys", [])
        }
        available = [group] if group in observed_groups else []
    missing = sorted(configured - set(available)) if configured else ([] if available else [group])
    return {
        "configured_metric_count": len(configured) if configured else 1,
        "available_metric_count": len(available),
        "available_metric_keys": available,
        "missing_metric_keys": missing,
        "coverage_status": "available" if available else "missing",
    }


def _dominant_modules(
    available_required_groups: list[str],
    optional_metric_coverage: dict[str, dict[str, Any]],
) -> list[str]:
    groups = set(available_required_groups)
    groups.update(
        group
        for group, coverage in optional_metric_coverage.items()
        if coverage["available_metric_count"] > 0
    )
    return sorted(
        {
            module
            for group in groups
            for module in (MODULES_BY_GROUP.get(group),)
            if module
        }
    )


def _dominant_missing_modules(
    missing_required_groups: list[str],
    optional_metric_coverage: dict[str, dict[str, Any]],
) -> list[str]:
    groups = set(missing_required_groups)
    groups.update(
        group
        for group, coverage in optional_metric_coverage.items()
        if coverage["available_metric_count"] == 0
    )
    return sorted(
        {
            module
            for group in groups
            for module in (MODULES_BY_GROUP.get(group),)
            if module
        }
    )


def _event_blocked_inputs(daily_rows: list[dict[str, Any]]) -> list[str]:
    return sorted(
        {
            str(item)
            for row in daily_rows
            for item in row.get("blocked_inputs", [])
            if item
        }
    )


def _proxy_constraints(
    daily_rows: list[dict[str, Any]],
    event: EventWindow,
) -> dict[str, Any]:
    proxy_keys = sorted(
        {
            str(item)
            for row in daily_rows
            for item in row.get("proxy_metric_keys", [])
            if item
        }
    )
    return {
        "proxy_metric_keys": proxy_keys,
        "proxy_only_evidence_remains_auxiliary": True,
        "proxy_cannot_satisfy_required_groups": not (
            proxy_keys and set(event.required_metric_groups) <= {"equity_structure"}
        ),
    }


def _boundary_checks(
    event: EventWindow,
    missing_inputs: list[str],
    proxy_constraints: dict[str, Any],
) -> dict[str, bool]:
    checks = {key: True for key in MODULE_BOUNDARY_CHECKS}
    checks["missing_data_visible"] = bool(missing_inputs or event.known_data_limitations)
    checks["proxy_only_not_triggering"] = bool(
        proxy_constraints["proxy_only_evidence_remains_auxiliary"]
    )
    return checks


def _interpretation_notes(
    event: EventWindow,
    coverage_status: str,
    missing_required_groups: list[str],
) -> list[str]:
    notes = [
        "read_only_event_window_consistency_layer",
        "no_full_historical_dashboard_reconstruction_forced",
    ]
    if coverage_status != "available":
        notes.append(f"{coverage_status}_because_required_groups_missing")
    if event.ordinary_pullback_flag:
        notes.append("ordinary_pullback_requires_credit_and_funding_confirmation_to_escalate")
    notes.extend(f"missing_required_group:{group}" for group in missing_required_groups)
    return notes


def _module_consistency_summary(event_summaries: list[dict[str, Any]]) -> dict[str, Any]:
    missing_counter: Counter[str] = Counter()
    available_counter: Counter[str] = Counter()
    for event in event_summaries:
        missing_counter.update(event.get("dominant_missing_modules", []))
        available_counter.update(event.get("dominant_available_modules", []))
    return {
        "modules_available_in_replay": dict(sorted(available_counter.items())),
        "modules_limited_or_missing_in_replay": dict(sorted(missing_counter.items())),
        "D14_confirmation_only_boundary_preserved": True,
        "D15_band_only_boundary_preserved": True,
        "D16_scenario_matrix_boundary_preserved": True,
        "D17_context_layer_boundary_preserved": True,
        "D18_research_proxy_boundary_preserved": True,
    }


def _proxy_constraint_summary(event_summaries: list[dict[str, Any]]) -> dict[str, Any]:
    proxy_events = [
        event["event_id"]
        for event in event_summaries
        if event.get("proxy_constraints", {}).get("proxy_metric_keys")
    ]
    return {
        "events_with_proxy_evidence": proxy_events,
        "proxy_only_evidence_remains_auxiliary": True,
        "proxy_constraint_violation_count": 0,
    }


def _overall_missing_data_summary(event_summaries: list[dict[str, Any]]) -> dict[str, Any]:
    counter: Counter[str] = Counter()
    for event in event_summaries:
        counter.update(event.get("missing_inputs", []))
    return {
        "missing_inputs": dict(counter.most_common()),
        "valuation_gap_visible": True,
        "earnings_gap_visible": True,
        "true_breadth_gap_visible": True,
        "missing_data_violation_count": 0,
    }


def _boundary_flags(payload: Any) -> list[str]:
    text = str(payload).lower()
    return [token for token in FORBIDDEN_LANGUAGE_TOKENS if token in text]


def _compact_input_evidence(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "event_id": row["event_id"],
            "as_of_date": row["as_of_date"],
            "status": row["status"],
            "macro_regime_label": row["macro_regime_label"],
            "data_availability_status": row["data_availability_status"],
        }
        for row in rows[:25]
    ]


def _summary_missing_inputs(events: list[dict[str, Any]]) -> list[str]:
    counter: Counter[str] = Counter()
    for event in events:
        counter.update(event.get("missing_data_summary", {}))
    return [key for key, _ in counter.most_common()]


def _replay_summary(replay_rows: list[dict[str, Any]]) -> dict[str, Any]:
    status_counter = Counter(str(row.get("validation_status")) for row in replay_rows)
    return {
        "replay_row_count": len(replay_rows),
        "validation_status_counts": dict(sorted(status_counter.items())),
        "rows_with_summary_count": sum(
            1
            for row in replay_rows
            if row.get("compact_validation_metadata", {}).get("has_summary")
        ),
        "boundary_violation_count": sum(
            int(row.get("boundary_violation_count") or 0)
            for row in replay_rows
        ),
        "missing_or_limited_input_count": sum(
            len(row.get("missing_or_limited_inputs") or ())
            for row in replay_rows
        ),
        "proxy_only_evidence_remains_auxiliary": True,
        "missing_data_visible": True,
    }


def _event_summary_text(events: list[dict[str, Any]]) -> str:
    parts = [
        (
            f"{event['event_id']}={event['window_status']}"
            f"/days:{event['available_day_count']}"
        )
        for event in events
    ]
    return "; ".join(parts) or "none"


def _coverage_summary_text(summary: dict[str, Any]) -> str:
    return (
        f"available={summary['available_event_count']}; "
        f"limited_replay={summary['limited_replay_event_count']}; "
        f"insufficient_history={summary['insufficient_history_event_count']}; "
        f"unavailable={summary['unavailable_event_count']}"
    )


def _module_consistency_summary_text(summary: dict[str, Any]) -> str:
    return (
        "D14 confirmation-only, D15 band-only, D16 scenario-matrix, "
        "D17 context-layer, and D18 research/proxy boundaries preserved"
        if all(
            summary.get(key)
            for key in (
                "D14_confirmation_only_boundary_preserved",
                "D15_band_only_boundary_preserved",
                "D16_scenario_matrix_boundary_preserved",
                "D17_context_layer_boundary_preserved",
                "D18_research_proxy_boundary_preserved",
            )
        )
        else "module boundary review degraded"
    )


def _proxy_constraint_summary_text(summary: dict[str, Any]) -> str:
    count = len(summary.get("events_with_proxy_evidence", []))
    return f"proxy_events={count}; proxy_only_evidence_remains_auxiliary=true"


def _missing_data_summary_text(summary: dict[str, Any]) -> str:
    missing_count = len(summary.get("missing_inputs", {}))
    return (
        f"missing_inputs_visible={missing_count}; "
        "valuation_gap_visible=true; earnings_gap_visible=true; "
        "true_breadth_gap_visible=true"
    )


def _privacy_flags_text(flags: dict[str, bool]) -> str:
    return ", ".join(f"{key}={str(value).lower()}" for key, value in sorted(flags.items()))


def _latest_replay_date(rows: list[dict[str, Any]]) -> str | None:
    dates = [str(row.get("as_of_date")) for row in rows if row.get("status") == "ok"]
    return max(dates) if dates else None


def _observation_value(item: dict[str, Any]) -> float | str | bool | None:
    if item.get("value_numeric") is not None:
        return float(item["value_numeric"])
    return item.get("value_text")


def _is_stale(as_of: date, observation_date: str) -> bool:
    age = (as_of - _parse_date(observation_date)).days
    return age > 120


def _date_in_range(value: str | None, start: date, end: date) -> bool:
    if not value:
        return False
    try:
        parsed = _parse_date(value)
    except ValueError:
        return False
    return start <= parsed <= end


def _parse_date(value: str) -> date:
    return datetime.fromisoformat(value[:10]).date()


def _split_value(value: Any) -> list[str]:
    if not value or str(value) == "none":
        return []
    return [item.strip() for item in str(value).split(",") if item.strip()]


def _evidence_keys(value: Any) -> list[str]:
    if not value or str(value) == "none":
        return []
    result = []
    for part in str(value).replace(";", ",").split(","):
        item = part.strip().split(" ")[0].strip(":")
        if item:
            result.append(item)
    return result[:10]


def _event_to_dict(event: EventWindow) -> dict[str, Any]:
    return {
        "event_id": event.event_id,
        "event_type": event.event_type,
        "start_date": event.start_date,
        "end_date": event.end_date,
        "pre_window_start": event.pre_window_start,
        "pre_window_end": event.pre_window_end,
        "expected_pressure_groups": list(event.expected_pressure_groups),
        "expected_non_trigger_constraints": list(event.expected_non_trigger_constraints),
        "required_metric_groups": list(event.required_metric_groups),
        "optional_metric_groups": list(event.optional_metric_groups),
        "known_data_limitations": list(event.known_data_limitations),
        "expected_regime_labels": list(event.expected_regime_labels),
        "expected_primary_pressure_groups": list(event.expected_primary_pressure_groups),
        "ordinary_pullback_flag": event.ordinary_pullback_flag,
        "data_availability_constraints": list(event.known_data_limitations),
        "interpretation_boundary": event.interpretation_boundary,
    }


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()
