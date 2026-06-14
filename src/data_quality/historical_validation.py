from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Any

from data_quality import macro_regime_review
from data_quality import market_history_store


MODEL_KEY = "historical_validation_v0"
MODULE_KEY = "historical_validation"
MODEL_VERSION = "historical_validation_v0"
FORMULA_VERSION = "d19_event_window_replay_v0"
VALIDATION_BOUNDARY = (
    "Historical validation is a read-only historical replay of deterministic "
    "evidence rows for event-window consistency and boundary validation. It is "
    "not a prediction model, event-odds model, business-cycle call, market "
    "direction forecast, allocation directive, or return estimate."
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
)
STRESS_EVENT_TYPES = {"stress", "rates_inflation_stress", "funding_stress"}
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


@dataclass(frozen=True)
class EventWindow:
    event_id: str
    event_type: str
    start_date: str
    end_date: str
    pre_window_start: str
    pre_window_end: str
    expected_regime_labels: tuple[str, ...]
    expected_primary_pressure_groups: tuple[str, ...]
    ordinary_pullback_flag: bool
    data_availability_constraints: tuple[str, ...]
    interpretation_boundary: str


EVENT_WINDOWS: tuple[EventWindow, ...] = (
    EventWindow(
        event_id="2018_q4_tightening_scare",
        event_type="ordinary_pullback",
        start_date="2018-10-01",
        end_date="2018-12-31",
        pre_window_start="2018-07-01",
        pre_window_end="2018-09-30",
        expected_regime_labels=("rates_pressure", "mixed_or_transition"),
        expected_primary_pressure_groups=("rates_real_yield", "credit"),
        ordinary_pullback_flag=True,
        data_availability_constraints=("credit_and_rates_history_required",),
        interpretation_boundary=VALIDATION_BOUNDARY,
    ),
    EventWindow(
        event_id="2020_covid_shock",
        event_type="stress",
        start_date="2020-02-15",
        end_date="2020-04-30",
        pre_window_start="2020-01-01",
        pre_window_end="2020-02-14",
        expected_regime_labels=("credit_stress", "liquidity_funding_pressure", "mixed_or_transition"),
        expected_primary_pressure_groups=("credit", "liquidity_funding"),
        ordinary_pullback_flag=False,
        data_availability_constraints=("credit_rates_labor_and_funding_history_required",),
        interpretation_boundary=VALIDATION_BOUNDARY,
    ),
    EventWindow(
        event_id="2022_inflation_rates_bear_market",
        event_type="rates_inflation_stress",
        start_date="2022-01-03",
        end_date="2022-10-31",
        pre_window_start="2021-10-01",
        pre_window_end="2021-12-31",
        expected_regime_labels=("rates_pressure", "inflation_energy_pressure", "stagflation_pressure"),
        expected_primary_pressure_groups=("rates_real_yield", "inflation_energy"),
        ordinary_pullback_flag=False,
        data_availability_constraints=("rates_real_yield_and_inflation_history_required",),
        interpretation_boundary=VALIDATION_BOUNDARY,
    ),
    EventWindow(
        event_id="2023_svb_bank_stress",
        event_type="funding_stress",
        start_date="2023-03-08",
        end_date="2023-03-31",
        pre_window_start="2023-02-01",
        pre_window_end="2023-03-07",
        expected_regime_labels=("credit_stress", "liquidity_funding_pressure", "mixed_or_transition"),
        expected_primary_pressure_groups=("credit", "liquidity_funding", "rates_real_yield"),
        ordinary_pullback_flag=False,
        data_availability_constraints=("credit_and_funding_history_required",),
        interpretation_boundary=VALIDATION_BOUNDARY,
    ),
    EventWindow(
        event_id="2015_2016_oil_hy_energy_stress",
        event_type="stress",
        start_date="2015-08-01",
        end_date="2016-02-29",
        pre_window_start="2015-05-01",
        pre_window_end="2015-07-31",
        expected_regime_labels=("credit_stress", "inflation_energy_pressure", "mixed_or_transition"),
        expected_primary_pressure_groups=("credit", "inflation_energy"),
        ordinary_pullback_flag=False,
        data_availability_constraints=("credit_and_energy_history_required",),
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
    as_of_date = _latest_replay_date(summary["daily_replay_rows"])
    available = summary["available_event_count"] > 0
    status = "ok" if available else "insufficient_history"
    base = {
        "unit": None,
        "source": "local_market_history",
        "source_badge": "derived",
        "source_series": "D19_EVENT_WINDOW_REPLAY_V0",
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
            "events": summary["events"],
            "event_count": summary["event_count"],
            "available_event_count": summary["available_event_count"],
            "insufficient_history_event_count": summary["insufficient_history_event_count"],
            "ordinary_pullback_over_escalation_count": summary[
                "ordinary_pullback_over_escalation_count"
            ],
            "stress_window_under_escalation_count": summary[
                "stress_window_under_escalation_count"
            ],
            "boundary_violation_count": summary["boundary_violation_count"],
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
            "available" if available else "insufficient_history",
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
        if _core_group_count(evidence_rows) < 3:
            rows.append(
                _unavailable_daily_row(
                    event,
                    as_of.isoformat(),
                    "insufficient_history",
                    _missing_core_inputs(evidence_rows),
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
                "data_availability_status": "available",
                "interpretation_boundary": DAILY_BOUNDARY,
            }
        )
    return rows


def _event_summary(event: EventWindow, daily_rows: list[dict[str, Any]]) -> dict[str, Any]:
    available_rows = [row for row in daily_rows if row["status"] == "ok"]
    insufficient_rows = [row for row in daily_rows if row["status"] != "ok"]
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
        and not (
            set(dominant_labels) & set(event.expected_regime_labels)
            or set(dominant_groups) & set(event.expected_primary_pressure_groups)
        )
    )
    window_status = "available" if available_rows else "insufficient_history"
    return {
        "event_id": event.event_id,
        "event_type": event.event_type,
        "window_status": window_status,
        "available_day_count": len(available_rows),
        "insufficient_history_day_count": len(insufficient_rows),
        "dominant_labels": dominant_labels,
        "dominant_primary_pressure_groups": dominant_groups,
        "over_escalation_flag": over_escalation,
        "under_escalation_flag": under_escalation,
        "missing_data_summary": _event_missing_data_summary(daily_rows),
        "boundary_violation_flags": boundary_flags,
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
    return {
        "model_key": MODEL_KEY,
        "event_count": len(event_summaries),
        "available_event_count": sum(
            1 for item in event_summaries if item["window_status"] == "available"
        ),
        "insufficient_history_event_count": sum(
            1 for item in event_summaries if item["window_status"] == "insufficient_history"
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
        "privacy_flags": privacy_flags,
        "validation_boundary": VALIDATION_BOUNDARY,
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
) -> dict[str, Any]:
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


def _event_summary_text(events: list[dict[str, Any]]) -> str:
    parts = [
        (
            f"{event['event_id']}={event['window_status']}"
            f"/days:{event['available_day_count']}"
        )
        for event in events
    ]
    return "; ".join(parts) or "none"


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
        "expected_regime_labels": list(event.expected_regime_labels),
        "expected_primary_pressure_groups": list(event.expected_primary_pressure_groups),
        "ordinary_pullback_flag": event.ordinary_pullback_flag,
        "data_availability_constraints": list(event.data_availability_constraints),
        "interpretation_boundary": event.interpretation_boundary,
    }


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()
