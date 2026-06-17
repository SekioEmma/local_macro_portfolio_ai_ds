from __future__ import annotations

from typing import Any

from app_backend.schemas.responses import DashboardEvidenceRow, DashboardMetric


AI_BLOCKED_METRIC_STATUSES = {
    "missing",
    "research_needed",
    "not_available",
    "insufficient_history",
    "insufficient_evidence",
    "limited_evidence",
    "stale",
}
AI_BLOCKED_FRESHNESS_STATUSES = {
    "unknown",
    "missing",
    "stale",
    "insufficient_history",
}
AI_BLOCKED_SOURCE_BADGES = {
    "missing",
    "research_needed",
    "search-derived",
}


def build_evidence_row(module_key: str, metric: DashboardMetric) -> DashboardEvidenceRow:
    ai_context_allowed = evidence_ai_context_allowed(metric)
    blocked_reason = ppi_observation_date_blocked_reason(metric)
    if blocked_reason is not None:
        ai_context_allowed = False
    return DashboardEvidenceRow(
        row_id=f"{module_key}:{metric.metric_key}",
        module=module_key,
        metric_key=metric.metric_key,
        display_name=metric.display_name,
        value=metric.value,
        value_text=evidence_value_text(metric),
        unit=metric.unit,
        status=metric.status,
        source=metric.source,
        source_badge=metric.source_badge,
        source_series=metric.source_series,
        observation_date=metric.observation_date,
        generated_at=metric.generated_at,
        freshness_status=metric.freshness_status,
        missing_reason=metric.missing_reason,
        interpretation_hint=metric.interpretation_hint,
        blocked_reason=None
        if ai_context_allowed
        else blocked_reason or ai_context_blocked_reason(
            status=metric.status,
            value=metric.value,
            source=metric.source,
            source_badge=metric.source_badge,
            observation_date=metric.observation_date,
            generated_at=metric.generated_at,
            freshness_status=metric.freshness_status,
            interpretation_hint=metric.interpretation_hint,
        ),
        ai_context_allowed=ai_context_allowed,
        input_evidence=metric.input_evidence,
        component_contributions=metric.component_contributions,
        missing_inputs=metric.missing_inputs,
        interpretation_boundary=metric.interpretation_boundary,
        lookback_window=metric.lookback_window,
        lookback_start=metric.lookback_start,
        lookback_end=metric.lookback_end,
        observation_count=metric.observation_count,
        minimum_observation_count=metric.minimum_observation_count,
        history_quality_status=metric.history_quality_status,
        percentile=metric.percentile,
        percentile_band=metric.percentile_band,
        zscore=metric.zscore,
        zscore_band=metric.zscore_band,
        robust_zscore=metric.robust_zscore,
        robust_zscore_band=metric.robust_zscore_band,
        percentile_direction=metric.percentile_direction,
        frequency_class=metric.frequency_class,
        transform_class=metric.transform_class,
        ai_context_tier=metric.ai_context_tier,
        trigger_eligibility=metric.trigger_eligibility,
    )


def evidence_value_text(metric: DashboardMetric) -> str:
    text = str(metric.value_text or "").strip()
    if text and text != "--":
        return text
    return missing_value_text(metric.status)


def evidence_ai_context_allowed(metric: DashboardMetric) -> bool:
    if ppi_observation_date_blocked_reason(metric) is not None:
        return False
    return ai_context_allowed(
        status=metric.status,
        source=metric.source,
        source_badge=metric.source_badge,
        observation_date=metric.observation_date,
        generated_at=metric.generated_at,
        freshness_status=metric.freshness_status,
        interpretation_hint=metric.interpretation_hint,
    ) and bool(metric.ai_context_allowed)


def ppi_observation_date_blocked_reason(metric: DashboardMetric) -> str | None:
    if metric.metric_key in {"ppi_final_demand", "ppi_final_demand_yoy"} and not metric.observation_date:
        return "observation_date_missing"
    return None


def ai_context_allowed(
    *,
    status: str,
    source: str | None,
    source_badge: str,
    observation_date: str | None,
    generated_at: str | None,
    freshness_status: str,
    interpretation_hint: str | None = None,
) -> bool:
    if ai_context_blocked_reason(
        status=status,
        value=True,
        source=source,
        source_badge=source_badge,
        observation_date=observation_date,
        generated_at=generated_at,
        freshness_status=freshness_status,
        interpretation_hint=interpretation_hint,
    ):
        return False
    return True


def ai_context_blocked_reason(
    *,
    status: str,
    value: Any,
    source: str | None,
    source_badge: str,
    observation_date: str | None,
    generated_at: str | None,
    freshness_status: str,
    interpretation_hint: str | None = None,
) -> str | None:
    if value is None:
        return "value_missing"
    if status in AI_BLOCKED_METRIC_STATUSES:
        return f"status_{status}"
    if source_badge in AI_BLOCKED_SOURCE_BADGES:
        return f"source_badge_{source_badge}"
    has_date = bool(observation_date or generated_at)
    if freshness_status in AI_BLOCKED_FRESHNESS_STATUSES:
        if not (source_badge == "local" and bool(generated_at)):
            return f"freshness_{freshness_status}"
    if source_badge == "proxy":
        return "source_badge_proxy"
    if source_badge == "derived" and not derived_dependency_hint_complete(interpretation_hint):
        return "dependency_metadata_incomplete"
    if not source and source_badge not in {"local", "derived"}:
        return "source_missing"
    if not has_date:
        return "date_missing"
    return None


def missing_value_text(status: str) -> str:
    if status == "research_needed":
        return "research needed"
    if status == "insufficient_history":
        return "insufficient history"
    if status == "stale":
        return "stale"
    if status == "not_available":
        return "not available"
    if status == "unknown":
        return "unknown"
    return "missing"


def derived_dependency_hint_complete(interpretation_hint: str | None) -> bool:
    text = (interpretation_hint or "").lower()
    return any(
        marker in text
        for marker in (
            "derived",
            "average",
            "history",
            "historical",
            "observation",
            "observations",
            "window",
            "compact",
        )
    )
