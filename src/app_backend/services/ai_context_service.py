from __future__ import annotations

from collections import Counter
from typing import Any

from app_backend.schemas.responses import AIContextManifestResponse, DashboardEvidenceRow
from app_backend.services import dashboard_service
from modeling.model_registry import get_model_registry


MODEL_OUTPUT_MODULES = get_model_registry().model_output_module_keys()
D14_FACT_MODULES = {"liquidity_funding_stress"}
EXCLUDED_STATUSES = {
    "missing",
    "research_needed",
    "insufficient_history",
    "insufficient_evidence",
    "stale",
    "not_available",
}
EXCLUDED_FRESHNESS = {"unknown", "missing", "stale", "insufficient_history"}
EXCLUDED_SOURCE_BADGES = {"search-derived", "missing", "research_needed"}
RISK_BOUNDARIES = [
    "Reference evidence only.",
    "No event-odds model.",
    "No business-cycle call.",
    "VIX alone is not systemic crisis.",
    "Equity drawdown alone is not systemic crisis.",
    "Proxy breadth is not true breadth.",
    "Financial stress score is pressure temperature, not prediction.",
    "Pullback checklist is risk review, not forecast.",
    "Portfolio deviation cannot be attributed to macro factors.",
    "Liquidity/funding stress rows are reference evidence, not allocation directives.",
    "Official stress indices do not replace the project financial stress composite.",
    "Commercial paper spread cannot alone prove systemic crisis.",
    "ON RRP usage alone is not a risk trigger.",
    "Macro regime review is current evidence review, not future market direction.",
    "Macro regime review produces no probability or allocation directive.",
    "Historical validation is event-window replay, not future market direction.",
    "Historical validation produces no event odds or allocation directive.",
]


def build_ai_context_manifest(
    context: dashboard_service.DashboardPipelineContext | None = None,
) -> AIContextManifestResponse:
    if context is not None and context.evidence_table is not None:
        evidence = context.evidence_table
    else:
        evidence = dashboard_service.build_dashboard_evidence_table(
            write_last_good=False,
            context=context,
        )
    included_facts: list[dict[str, Any]] = []
    excluded_facts: list[dict[str, Any]] = []
    included_model_outputs: list[dict[str, Any]] = []
    excluded_model_outputs: list[dict[str, Any]] = []

    for row in evidence.rows:
        snapshot = _row_manifest(row)
        excluded_reason = _excluded_reason(row)
        if row.module in MODEL_OUTPUT_MODULES:
            if excluded_reason is None:
                included_model_outputs.append(snapshot)
            else:
                excluded_model_outputs.append({**snapshot, "excluded_reason": excluded_reason})
            continue
        if excluded_reason is None:
            included_facts.append(snapshot)
        else:
            excluded_facts.append({**snapshot, "excluded_reason": excluded_reason})

    return AIContextManifestResponse(
        generated_at=evidence.generated_at,
        included_facts=included_facts,
        excluded_facts=excluded_facts,
        included_model_outputs=included_model_outputs,
        excluded_model_outputs=excluded_model_outputs,
        portfolio_context_policy=_portfolio_context_policy(included_facts, excluded_facts),
        privacy_policy=_privacy_policy(),
        search_policy=_search_policy(),
        model_destination={
            "chat_enabled": False,
            "deepseek_enabled": False,
            "tavily_enabled": False,
            "destination": "local_preview_only",
        },
        persistence_policy={
            "saves_manifest": False,
            "saves_prompt_text": False,
            "writes_chat_history": False,
            "source": "computed_from_current_sanitized_evidence_rows",
        },
        risk_boundaries=RISK_BOUNDARIES,
        source_summary=_source_summary(
            included_facts=included_facts,
            excluded_facts=excluded_facts,
            included_model_outputs=included_model_outputs,
            excluded_model_outputs=excluded_model_outputs,
            rows=evidence.rows,
        ),
    )


def _excluded_reason(row: DashboardEvidenceRow) -> str | None:
    if row.source_badge in EXCLUDED_SOURCE_BADGES:
        return f"source_badge_{row.source_badge}"
    if row.status in EXCLUDED_STATUSES:
        return f"status_{row.status}"
    if row.freshness_status in EXCLUDED_FRESHNESS:
        return f"freshness_{row.freshness_status}"
    if not row.ai_context_allowed:
        return row.blocked_reason or "ai_context_not_allowed"
    return None


def _row_manifest(row: DashboardEvidenceRow) -> dict[str, Any]:
    payload = {
        "row_id": row.row_id,
        "module": row.module,
        "metric_key": row.metric_key,
        "display_name": row.display_name,
        "value": row.value,
        "value_text": row.value_text,
        "unit": row.unit,
        "status": row.status,
        "source": row.source,
        "source_badge": row.source_badge,
        "source_series": row.source_series,
        "observation_date": row.observation_date,
        "generated_at": row.generated_at,
        "freshness_status": row.freshness_status,
        "missing_reason": row.missing_reason,
        "interpretation_hint": row.interpretation_hint,
        "interpretation_boundary": row.interpretation_boundary,
        "ai_context_allowed": row.ai_context_allowed,
    }
    for field in (
        "lookback_window",
        "lookback_start",
        "lookback_end",
        "observation_count",
        "minimum_observation_count",
        "history_quality_status",
        "percentile",
        "percentile_band",
        "zscore",
        "zscore_band",
        "robust_zscore",
        "robust_zscore_band",
        "percentile_direction",
        "frequency_class",
        "transform_class",
        "ai_context_tier",
        "trigger_eligibility",
    ):
        value = getattr(row, field, None)
        if value is not None:
            payload[field] = value
    if row.module in MODEL_OUTPUT_MODULES:
        payload["input_evidence"] = _safe_input_evidence(row.input_evidence)
        payload["component_contributions"] = row.component_contributions
        payload["missing_inputs"] = row.missing_inputs
    if row.module in D14_FACT_MODULES:
        payload["input_evidence"] = _safe_input_evidence(row.input_evidence)
        payload["component_contributions"] = row.component_contributions
        payload["missing_inputs"] = row.missing_inputs
    return payload


def _safe_input_evidence(input_evidence: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    if not input_evidence:
        return []
    allowed_keys = {
        "module",
        "metric_key",
        "value",
        "value_text",
        "status",
        "source",
        "source_badge",
        "source_series",
        "observation_date",
        "generated_at",
        "freshness_status",
        "lookback_window",
        "lookback_start",
        "lookback_end",
        "observation_count",
        "minimum_observation_count",
        "history_quality_status",
        "percentile_band",
        "zscore_band",
        "robust_zscore_band",
        "trigger_eligibility",
        "interpretation_boundary",
    }
    return [
        {key: value for key, value in item.items() if key in allowed_keys}
        for item in input_evidence
        if isinstance(item, dict)
    ]


def _portfolio_context_policy(
    included_facts: list[dict[str, Any]],
    excluded_facts: list[dict[str, Any]],
) -> dict[str, Any]:
    included_keys = sorted(
        row["metric_key"]
        for row in included_facts
        if row.get("module") == "portfolio_deviation"
    )
    excluded_keys = sorted(
        row["metric_key"]
        for row in excluded_facts
        if row.get("module") == "portfolio_deviation"
    )
    return {
        "mode": "compact_summary_only",
        "included_portfolio_metric_keys": included_keys,
        "excluded_portfolio_metric_keys": excluded_keys,
        "holdings_line_items_allowed": False,
        "portfolio_deviation_attribution_allowed": False,
        "notes": (
            "Portfolio context may include sanitized deviation summary rows only; "
            "individual holdings, account records, and macro attribution are excluded."
        ),
    }


def _privacy_policy() -> dict[str, Any]:
    return {
        "explicit_exclusions": [
            "API credentials",
            "provider payloads",
            "prompt text",
            "holdings details",
            "holdings line items",
            "report file contents",
            "search results",
            "private data",
        ],
        "returns_sanitized_evidence_rows_only": True,
        "returns_holdings_line_items": False,
        "returns_provider_payloads": False,
        "returns_credentials": False,
    }


def _search_policy() -> dict[str, Any]:
    return {
        "search_enabled": False,
        "search_derived_default": "excluded",
        "allowed_source_badges": ["official", "official_fallback", "unofficial_fallback", "proxy", "derived", "local"],
        "excluded_source_badges": sorted(EXCLUDED_SOURCE_BADGES),
    }


def _source_summary(
    *,
    included_facts: list[dict[str, Any]],
    excluded_facts: list[dict[str, Any]],
    included_model_outputs: list[dict[str, Any]],
    excluded_model_outputs: list[dict[str, Any]],
    rows: list[DashboardEvidenceRow],
) -> dict[str, Any]:
    source_badges = Counter(row.source_badge for row in rows)
    modules = Counter(row.module for row in rows)
    return {
        "total_evidence_rows": len(rows),
        "included_facts_count": len(included_facts),
        "excluded_facts_count": len(excluded_facts),
        "included_model_outputs_count": len(included_model_outputs),
        "excluded_model_outputs_count": len(excluded_model_outputs),
        "source_badge_distribution": dict(sorted(source_badges.items())),
        "module_distribution": dict(sorted(modules.items())),
    }
