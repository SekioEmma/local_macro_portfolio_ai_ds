from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from data_providers import market_data_service
from data_quality import market_history_store


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG_PATH = PROJECT_ROOT / "configs" / "data_sources.yaml"
MODULE_KEY = "liquidity_funding_stress"
RAW_METRIC_KEYS = (
    "sofr",
    "effr",
    "iorb",
    "on_rrp",
    "commercial_paper_rate",
    "ofr_fsi",
    "stl_fsi",
    "nfci",
    "anfci",
)
DERIVED_METRIC_KEYS = (
    "sofr_effr_spread",
    "effr_iorb_spread",
    "cp_effr_spread",
    "cp_sofr_spread",
    "policy_plumbing_status",
    "short_term_funding_pressure_status",
    "official_stress_reference_status",
    "liquidity_funding_stress_status",
    "liquidity_funding_interpretation_boundary",
)
ALL_METRIC_KEYS = RAW_METRIC_KEYS + DERIVED_METRIC_KEYS
BOUNDARY = (
    "Liquidity/funding stress rows are reference evidence, not trading signals. "
    "Official stress indices are external reference layers and do not replace the "
    "project financial stress composite. Commercial paper spread can support "
    "funding-pressure confirmation but cannot alone prove systemic crisis. "
    "SOFR/EFFR/IORB/ON RRP describe policy plumbing and money-market backdrop, "
    "not market direction. ON RRP usage alone is not a risk trigger. Different "
    "frequencies must not be mixed without explicit as-of alignment. No crash "
    "probability or recession probability is produced. No buy/sell/hedge "
    "instruction is produced."
)
NO_TRADING_HINT = " Reference evidence only; no trading instruction, crash probability, or recession probability."
CONTEXT_FIELDS = (
    "metric_key",
    "display_name",
    "value",
    "value_text",
    "status",
    "source",
    "source_badge",
    "source_series",
    "observation_date",
    "generated_at",
    "freshness_status",
    "input_evidence",
    "missing_inputs",
    "interpretation_hint",
    "interpretation_boundary",
    "ai_context_allowed",
    "missing_reason",
    "blocked_reason",
)
BAD_CONTEXT_STATUSES = {
    "missing",
    "research_needed",
    "insufficient_evidence",
    "insufficient_history",
    "stale",
    "not_available",
}
BAD_CONTEXT_FRESHNESS = {"missing", "unknown", "stale", "insufficient_history", "insufficient_evidence"}


def load_liquidity_funding_config(
    config_path: Path | str | None = None,
) -> dict[str, dict[str, Any]]:
    data_sources = market_data_service.load_data_source_config(
        str(config_path or DEFAULT_CONFIG_PATH)
    )
    section = data_sources.get(MODULE_KEY) if isinstance(data_sources, dict) else {}
    if not isinstance(section, dict):
        return {}
    return {
        key: _normalize_config_item(key, item)
        for key, item in section.items()
        if isinstance(item, dict)
    }


def build_liquidity_funding_rows(
    *,
    db_path: Path | str | None = None,
    config_path: Path | str | None = None,
) -> list[dict[str, Any]]:
    config = load_liquidity_funding_config(config_path)
    prefetched = market_history_store.list_market_observations_batch(
        list(RAW_METRIC_KEYS),
        limit_per_key=100,
        db_path=db_path,
    )
    raw_rows = [_raw_row(metric_key, config.get(metric_key), db_path=db_path, prefetched=prefetched) for metric_key in RAW_METRIC_KEYS]
    by_key = {row["metric_key"]: row for row in raw_rows}
    spread_rows = [
        _spread_row("sofr_effr_spread", "SOFR-EFFR spread", by_key.get("sofr"), by_key.get("effr")),
        _spread_row("effr_iorb_spread", "EFFR-IORB spread", by_key.get("effr"), by_key.get("iorb")),
        _spread_row("cp_effr_spread", "CP-EFFR spread", by_key.get("commercial_paper_rate"), by_key.get("effr")),
        _spread_row("cp_sofr_spread", "CP-SOFR spread", by_key.get("commercial_paper_rate"), by_key.get("sofr")),
    ]
    by_key.update({row["metric_key"]: row for row in spread_rows})
    status_rows = [
        _policy_plumbing_status(by_key),
        _short_term_funding_status(by_key),
        _official_reference_status(by_key),
    ]
    by_key.update({row["metric_key"]: row for row in status_rows})
    status_rows.append(_liquidity_funding_status(by_key))
    return raw_rows + spread_rows + status_rows + [_boundary_row()]


class EvidenceIndex:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self._rows = {str(row.get("metric_key")): row for row in rows}

    def by_metric_key(self, metric_key: str) -> dict[str, Any] | None:
        return self._rows.get(metric_key)

    def d14_context(self, metric_key: str) -> dict[str, Any] | None:
        row = self.by_metric_key(metric_key)
        if row is None:
            return None
        if row.get("module") != MODULE_KEY:
            return None
        return sanitized_d14_context(row)

    def available_d14_context(self, keys: tuple[str, ...] | list[str]) -> list[dict[str, Any]]:
        return [
            context
            for key in keys
            for context in [self.d14_context(key)]
            if context is not None and hard_confirmation_context(context)
        ]

    def missing_d14_context(self, keys: tuple[str, ...] | list[str]) -> list[dict[str, Any]]:
        missing: list[dict[str, Any]] = []
        for key in keys:
            context = self.d14_context(key)
            if context is None:
                missing.append(
                    {
                        "metric_key": key,
                        "status": "missing",
                        "source_badge": "missing",
                        "missing_reason": "d14_context_row_missing",
                    }
                )
            elif not hard_confirmation_context(context):
                missing.append(context)
        return missing


def build_evidence_index(rows: list[dict[str, Any]]) -> EvidenceIndex:
    return EvidenceIndex(rows)


def sanitized_d14_context(row: dict[str, Any]) -> dict[str, Any]:
    return {field: row.get(field) for field in CONTEXT_FIELDS if field in row}


def hard_confirmation_context(context: dict[str, Any]) -> bool:
    if context.get("status") in BAD_CONTEXT_STATUSES:
        return False
    if context.get("freshness_status") in BAD_CONTEXT_FRESHNESS:
        return False
    if context.get("source_badge") in {"missing", "research_needed", "search-derived"}:
        return False
    if context.get("ai_context_allowed") is False:
        return False
    if context.get("value") in (None, ""):
        return False
    return True


def planned_source_mappings(
    config_path: Path | str | None = None,
) -> tuple[dict[str, dict[str, Any]], list[str]]:
    config = load_liquidity_funding_config(config_path)
    planned: dict[str, dict[str, Any]] = {}
    missing: list[str] = []
    for key in RAW_METRIC_KEYS:
        item = config.get(key)
        if not item or item.get("status") == "research_needed" or not item.get("source_series"):
            missing.append(key)
            continue
        planned[key] = {
            "metric_key": key,
            "display_name": item["display_name"],
            "provider": item["provider"],
            "source": item["source"],
            "source_badge": item["source_badge"],
            "source_series": item["source_series"],
            "unit": item["unit"],
            "expected_frequency": item["expected_frequency"],
        }
    return planned, missing


def latest_history_summary(
    *,
    db_path: Path | str | None = None,
    config_path: Path | str | None = None,
) -> dict[str, Any]:
    rows = build_liquidity_funding_rows(db_path=db_path, config_path=config_path)
    raw_rows = [row for row in rows if row["metric_key"] in RAW_METRIC_KEYS]
    derived_rows = [row for row in rows if row["metric_key"] in DERIVED_METRIC_KEYS]
    return {
        "raw_history_counts": _history_counts(RAW_METRIC_KEYS, db_path=db_path),
        "derived_history_counts": _history_counts(DERIVED_METRIC_KEYS, db_path=db_path),
        "latest_observation_by_metric": {
            row["metric_key"]: row["observation_date"]
            for row in raw_rows + derived_rows
            if row.get("observation_date")
        },
        "missing_history_metric_keys": [
            row["metric_key"]
            for row in raw_rows
            if row["status"] in {"missing", "research_needed", "insufficient_evidence"}
        ],
        "source_badge_distribution": _count_by(rows, "source_badge"),
    }


def _normalize_config_item(metric_key: str, item: dict[str, Any]) -> dict[str, Any]:
    return {
        "metric_key": item.get("metric_key") or metric_key,
        "display_name": item.get("display_name") or metric_key,
        "source": item.get("source"),
        "source_badge": item.get("source_badge") or "research_needed",
        "source_series": item.get("source_series"),
        "provider": item.get("provider"),
        "unit": item.get("unit"),
        "expected_frequency": item.get("expected_frequency"),
        "freshness_policy": item.get("freshness_policy") or "historical",
        "interpretation_hint": item.get("interpretation_hint"),
        "ai_context_allowed_rule": item.get("ai_context_allowed_rule"),
        "status": item.get("status"),
        "missing_reason": item.get("missing_reason"),
    }


def _raw_row(
    metric_key: str,
    item: dict[str, Any] | None,
    *,
    db_path: Path | str | None,
    prefetched: dict[str, list[dict[str, Any]]] | None = None,
) -> dict[str, Any]:
    if not item or item.get("status") == "research_needed" or not item.get("source_series"):
        display = (item or {}).get("display_name") or metric_key
        return _metric(
            metric_key=metric_key,
            display_name=display,
            value=None,
            value_text="research needed",
            unit=(item or {}).get("unit"),
            status="research_needed",
            source=(item or {}).get("source"),
            source_badge="research_needed",
            source_series=(item or {}).get("source_series"),
            observation_date=None,
            generated_at=_utc_now(),
            freshness_status="missing",
            missing_reason=(item or {}).get("missing_reason") or "source_mapping_required",
            interpretation_hint=((item or {}).get("interpretation_hint") or "Source mapping required.") + NO_TRADING_HINT,
            ai_context_allowed=False,
            missing_inputs=[metric_key],
        )
    observation = _latest_observation(metric_key, item, db_path=db_path, prefetched=prefetched)
    if observation is None:
        return _metric(
            metric_key=metric_key,
            display_name=item["display_name"],
            value=None,
            value_text="missing",
            unit=item["unit"],
            status="missing",
            source=item["source"],
            source_badge=item["source_badge"],
            source_series=item["source_series"],
            observation_date=None,
            generated_at=_utc_now(),
            freshness_status="missing",
            missing_reason="history_missing",
            interpretation_hint=item["interpretation_hint"] + NO_TRADING_HINT,
            ai_context_allowed=False,
            missing_inputs=[metric_key],
        )
    value = observation.get("value_numeric")
    return _metric(
        metric_key=metric_key,
        display_name=item["display_name"],
        value=value,
        value_text=_format_value(value, item["unit"]),
        unit=item["unit"],
        status="ok",
        source=observation.get("source") or item["source"],
        source_badge=observation.get("source_badge") or item["source_badge"],
        source_series=observation.get("source_series") or item["source_series"],
        observation_date=observation.get("observation_date"),
        generated_at=observation.get("generated_at") or observation.get("fetched_at"),
        freshness_status=observation.get("freshness_status") or "historical",
        missing_reason=None,
        interpretation_hint=item["interpretation_hint"] + NO_TRADING_HINT,
        ai_context_allowed=bool(observation.get("ai_context_allowed", True)),
    )


def _latest_observation(
    metric_key: str,
    item: dict[str, Any],
    *,
    db_path: Path | str | None,
    prefetched: dict[str, list[dict[str, Any]]] | None = None,
) -> dict[str, Any] | None:
    if prefetched is not None:
        rows = prefetched.get(metric_key, [])
    else:
        rows = market_history_store.list_market_observations(metric_key=metric_key, limit=100, db_path=db_path)
    expected_series = item.get("source_series")
    expected_badge = item.get("source_badge")
    for row in rows:
        if row.get("status") != "ok":
            continue
        if row.get("value_numeric") is None:
            continue
        if expected_series and row.get("source_series") != expected_series:
            continue
        if expected_badge and row.get("source_badge") != expected_badge:
            continue
        return row
    return None


def _spread_row(
    metric_key: str,
    display_name: str,
    left: dict[str, Any] | None,
    right: dict[str, Any] | None,
) -> dict[str, Any]:
    inputs = [item for item in (left, right) if item is not None]
    missing = [item["metric_key"] for item in (left, right) if not _usable_numeric(item)]
    input_evidence = [_input_evidence(item) for item in inputs]
    if missing:
        return _metric(
            metric_key=metric_key,
            display_name=display_name,
            value=None,
            value_text="insufficient evidence",
            unit="pp",
            status="insufficient_evidence",
            source="market_history",
            source_badge="derived",
            source_series=_source_series(inputs),
            observation_date=_latest_date(inputs),
            generated_at=_utc_now(),
            freshness_status="insufficient_evidence",
            missing_reason="spread_inputs_missing",
            interpretation_hint=(
                "Spread requires both rate inputs. Different frequencies use explicit as-of alignment; "
                "no forward-fill daily series is fabricated." + NO_TRADING_HINT
            ),
            ai_context_allowed=False,
            input_evidence=input_evidence,
            missing_inputs=missing,
            component_contributions=_alignment(inputs),
        )
    value = round(float(left["value"]) - float(right["value"]), 6)
    return _metric(
        metric_key=metric_key,
        display_name=display_name,
        value=value,
        value_text=f"{value:.2f}pp",
        unit="pp",
        status="ok",
        source="market_history",
        source_badge="derived",
        source_series=_source_series(inputs),
        observation_date=_latest_date(inputs),
        generated_at=_utc_now(),
        freshness_status="historical",
        missing_reason=None,
        interpretation_hint=(
            "Derived spread equals left rate minus right rate in percentage points. "
            "As-of alignment metadata preserves input observation dates." + NO_TRADING_HINT
        ),
        ai_context_allowed=True,
        input_evidence=input_evidence,
        missing_inputs=[],
        component_contributions=_alignment(inputs),
    )


def _policy_plumbing_status(rows: dict[str, dict[str, Any]]) -> dict[str, Any]:
    sofr_effr = _numeric(rows.get("sofr_effr_spread"))
    effr_iorb = _numeric(rows.get("effr_iorb_spread"))
    on_rrp = _numeric(rows.get("on_rrp"))
    inputs = [rows.get(key) for key in ("sofr_effr_spread", "effr_iorb_spread", "on_rrp") if rows.get(key)]
    if sofr_effr is None and effr_iorb is None:
        return _status_blocked("policy_plumbing_status", "Policy plumbing status", inputs, ["sofr_effr_spread", "effr_iorb_spread"])
    abnormal = max(abs(sofr_effr or 0.0), abs(effr_iorb or 0.0))
    if abnormal >= 0.25:
        status = value = "pressure"
    elif abnormal >= 0.10:
        status = value = "watch"
    else:
        status = value = "ok"
    if value == "ok" and on_rrp is not None:
        value = "ok"
    return _status_row("policy_plumbing_status", "Policy plumbing status", value, status, inputs, "ON RRP usage alone is not a risk trigger.")


def _short_term_funding_status(rows: dict[str, dict[str, Any]]) -> dict[str, Any]:
    cp_effr = _numeric(rows.get("cp_effr_spread"))
    cp_sofr = _numeric(rows.get("cp_sofr_spread"))
    inputs = [rows.get(key) for key in ("cp_effr_spread", "cp_sofr_spread") if rows.get(key)]
    if cp_effr is None and cp_sofr is None:
        return _status_blocked("short_term_funding_pressure_status", "Short-term funding pressure status", inputs, ["cp_effr_spread", "cp_sofr_spread"])
    elevated = max(cp_effr or 0.0, cp_sofr or 0.0)
    if elevated >= 2.0:
        status = value = "stress"
    elif elevated >= 1.0:
        status = value = "pressure"
    elif elevated >= 0.5:
        status = value = "watch"
    else:
        status = value = "ok"
    return _status_row("short_term_funding_pressure_status", "Short-term funding pressure status", value, status, inputs, "CP spread can support funding-pressure confirmation but cannot alone prove systemic crisis.")


def _official_reference_status(rows: dict[str, dict[str, Any]]) -> dict[str, Any]:
    reference_keys = ("stl_fsi", "nfci", "anfci")
    inputs = [rows.get(key) for key in reference_keys if rows.get(key)]
    values = [_reference_level(key, rows.get(key)) for key in reference_keys]
    values = [item for item in values if item is not None]
    if not values:
        return _status_blocked("official_stress_reference_status", "Official stress reference status", inputs, list(reference_keys))
    if values.count("stress") >= 2:
        status = value = "stress"
    elif "pressure" in values or "stress" in values:
        status = value = "pressure"
    elif "watch" in values:
        status = value = "watch"
    else:
        status = value = "ok"
    return _status_row("official_stress_reference_status", "Official stress reference status", value, status, inputs, "Official stress indices are reference layers and do not replace D10.")


def _liquidity_funding_status(rows: dict[str, dict[str, Any]]) -> dict[str, Any]:
    policy = _status_value(rows.get("policy_plumbing_status"))
    cp = _status_value(rows.get("short_term_funding_pressure_status"))
    reference = _status_value(rows.get("official_stress_reference_status"))
    inputs = [rows.get(key) for key in ("policy_plumbing_status", "short_term_funding_pressure_status", "official_stress_reference_status") if rows.get(key)]
    if cp is None and reference is None:
        return _status_blocked("liquidity_funding_stress_status", "Liquidity/funding stress status", inputs, ["short_term_funding_pressure_status", "official_stress_reference_status"])
    elevated_refs = sum(1 for key in ("stl_fsi", "nfci", "anfci") if _reference_level(key, rows.get(key)) in {"pressure", "stress"})
    if cp == "stress" and elevated_refs >= 2 and policy in {"pressure", "stress"}:
        status = value = "stress"
    elif cp in {"pressure", "stress"} and reference in {"watch", "pressure", "stress"}:
        status = value = "pressure"
    elif cp in {"watch", "pressure", "stress"} or reference in {"watch", "pressure", "stress"} or policy in {"watch", "pressure"}:
        status = value = "watch"
    else:
        status = value = "ok"
    return _status_row("liquidity_funding_stress_status", "Liquidity/funding stress status", value, status, inputs, "Reference status only; D14 does not change D10/D11 classifications.")


def _boundary_row() -> dict[str, Any]:
    return _metric(
        metric_key="liquidity_funding_interpretation_boundary",
        display_name="Liquidity/funding interpretation boundary",
        value=BOUNDARY,
        value_text=BOUNDARY,
        unit=None,
        status="ok",
        source="local_rules",
        source_badge="derived",
        source_series=None,
        observation_date=None,
        generated_at=_utc_now(),
        freshness_status="historical",
        missing_reason=None,
        interpretation_hint="Derived from local rule boundary. " + BOUNDARY,
        interpretation_boundary=BOUNDARY,
        ai_context_allowed=True,
    )


def _status_blocked(metric_key: str, display_name: str, inputs: list[dict[str, Any]], missing: list[str]) -> dict[str, Any]:
    return _metric(
        metric_key=metric_key,
        display_name=display_name,
        value=None,
        value_text="insufficient evidence",
        unit=None,
        status="insufficient_evidence",
        source="market_history",
        source_badge="derived",
        source_series=_source_series(inputs),
        observation_date=_latest_date(inputs),
        generated_at=_utc_now(),
        freshness_status="insufficient_evidence",
        missing_reason="status_inputs_missing",
        interpretation_hint="Liquidity/funding status requires CP and reference evidence; missing inputs are not fabricated." + NO_TRADING_HINT,
        ai_context_allowed=False,
        input_evidence=[_input_evidence(item) for item in inputs],
        missing_inputs=missing,
    )


def _status_row(
    metric_key: str,
    display_name: str,
    value: str,
    status: str,
    inputs: list[dict[str, Any]],
    note: str,
) -> dict[str, Any]:
    return _metric(
        metric_key=metric_key,
        display_name=display_name,
        value=value,
        value_text=value,
        unit=None,
        status=status,
        source="market_history",
        source_badge="derived",
        source_series=_source_series(inputs),
        observation_date=_latest_date(inputs),
        generated_at=_utc_now(),
        freshness_status="historical",
        missing_reason=None,
        interpretation_hint=(
            "Derived from local market history status inputs. " + note + " " + BOUNDARY
        ),
        interpretation_boundary=BOUNDARY,
        ai_context_allowed=True,
        input_evidence=[_input_evidence(item) for item in inputs],
        missing_inputs=[],
        component_contributions={"status_rule": note, "input_statuses": {item["metric_key"]: item["status"] for item in inputs}},
    )


def _metric(**kwargs: Any) -> dict[str, Any]:
    kwargs.setdefault("input_evidence", None)
    kwargs.setdefault("component_contributions", None)
    kwargs.setdefault("missing_inputs", None)
    kwargs.setdefault("interpretation_boundary", BOUNDARY)
    return kwargs


def _input_evidence(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "module": MODULE_KEY,
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
        "interpretation_boundary": row.get("interpretation_boundary"),
    }


def _alignment(inputs: list[dict[str, Any]]) -> dict[str, Any]:
    dates = {item["metric_key"]: item.get("observation_date") for item in inputs}
    return {
        "alignment": "as_of_latest_available_observations",
        "input_observation_dates": dates,
        "mixed_frequency": len(set(value for value in dates.values() if value)) > 1,
        "forward_fill_used": False,
    }


def _usable_numeric(row: dict[str, Any] | None) -> bool:
    return bool(row and row.get("status") == "ok" and _numeric(row) is not None)


def _numeric(row: dict[str, Any] | None) -> float | None:
    if not row:
        return None
    try:
        return float(row.get("value"))
    except (TypeError, ValueError):
        return None


def _status_value(row: dict[str, Any] | None) -> str | None:
    if not row or row.get("status") == "insufficient_evidence":
        return None
    value = row.get("value")
    return str(value) if value is not None else None


def _reference_level(metric_key: str, row: dict[str, Any] | None) -> str | None:
    value = _numeric(row)
    if value is None:
        return None
    if metric_key == "stl_fsi":
        if value >= 2.0:
            return "stress"
        if value >= 1.0:
            return "pressure"
        if value >= 0.5:
            return "watch"
        return "ok"
    if value >= 1.0:
        return "stress"
    if value >= 0.5:
        return "pressure"
    if value > 0.0:
        return "watch"
    return "ok"


def _source_series(inputs: list[dict[str, Any]]) -> str | None:
    values = [str(item.get("source_series")) for item in inputs if item.get("source_series")]
    return ", ".join(values) or None


def _latest_date(inputs: list[dict[str, Any]]) -> str | None:
    values = sorted(str(item.get("observation_date")) for item in inputs if item.get("observation_date"))
    return values[-1] if values else None


def _format_value(value: Any, unit: str | None) -> str:
    if value is None:
        return "missing"
    try:
        number = float(value)
    except (TypeError, ValueError):
        return str(value)
    if unit == "percent":
        return f"{number:.2f}%"
    if unit == "billions_usd":
        return f"${number:,.1f}B"
    return f"{number:.4g}"


def _history_counts(metric_keys: tuple[str, ...], *, db_path: Path | str | None) -> dict[str, int]:
    counts = market_history_store.count_observations_by_metric(db_path=db_path)
    return {key: counts.get(key, 0) for key in metric_keys}


def _count_by(rows: list[dict[str, Any]], field: str) -> dict[str, int]:
    result: dict[str, int] = {}
    for row in rows:
        key = str(row.get(field) or "missing")
        result[key] = result.get(key, 0) + 1
    return dict(sorted(result.items()))


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()
