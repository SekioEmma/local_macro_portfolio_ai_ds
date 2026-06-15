from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from app_backend.schemas.ai_memo import (
    AIMemoContextUsedSummary,
    AIMemoPreview,
    AIMemoPrivacySummary,
    AIMemoSection,
    AIMemoValidatorResult,
)


NO_ELIGIBLE_CONTEXT = "No eligible context available in the current AI Context Manifest."
MODE = "local_deterministic_template"
BOUNDARY_NOTICE = (
    "Local deterministic template output only; not an action directive, not an "
    "event-odds model, not a return-estimation model, not a position-level "
    "output, and not external-model output."
)

MEMO_SECTION_KEYS: dict[str, list[str]] = {
    "daily_review_memo": [
        "as_of_context",
        "evidence_summary",
        "model_output_summary",
        "primary_pressure_channels",
        "missing_or_excluded_constraints",
        "interpretation_boundaries",
        "human_review_required",
    ],
    "risk_review_memo": [
        "current_macro_state",
        "financial_stress_context",
        "pullback_vs_systemic_review",
        "liquidity_funding_context",
        "scenario_stress_notes",
        "missing_constraints",
        "boundary_notice",
        "human_review_required",
    ],
    "scenario_review_memo": [
        "selected_scenario",
        "affected_evidence_groups",
        "transmission_channels",
        "uncertainty_conditions",
        "missing_inputs",
        "not_a_forecast_notice",
        "human_review_required",
    ],
    "portfolio_overlay_review": [
        "sanitized_portfolio_context_policy",
        "exposure_channel_summary",
        "macro_channel_mapping",
        "private_inputs_excluded",
        "not_action_directive_notice",
        "human_review_required",
    ],
    "macro_risk_report": [
        "executive_summary",
        "evidence_table_snapshot_summary",
        "D10_D19_model_summary",
        "Stage8_overlay_summary",
        "missing_data_and_research_needed",
        "boundary_and_privacy_notes",
        "appendix_manifest_stats",
    ],
    "evidence_audit_report": [
        "manifest_coverage",
        "included_context_summary",
        "excluded_context_summary",
        "source_and_freshness_notes",
        "privacy_policy_summary",
        "validator_findings",
        "human_review_required",
    ],
}

MEMO_TITLES = {
    "daily_review_memo": "Daily Review Memo Preview",
    "risk_review_memo": "Risk Review Memo Preview",
    "scenario_review_memo": "Scenario Review Memo Preview",
    "portfolio_overlay_review": "Portfolio Overlay Review Preview",
    "macro_risk_report": "Macro Risk Report Preview",
    "evidence_audit_report": "Evidence Audit Report Preview",
}

FORBIDDEN_GENERATED_OUTPUT_TERMS = (
    "buy",
    "sell",
    "add position",
    "reduce position",
    "clear position",
    "hedge",
    "rebalance",
    "target allocation",
    "target weight",
    "ideal allocation",
    "expected return",
    "predicted return",
    "future return",
    "market direction probability",
    "crash probability",
    "recession probability",
    "trade signal",
    "strategy return",
    "trading performance",
    "sharpe",
    "de-risk",
    "rotate into",
    "overweight",
    "underweight",
    "guaranteed",
    "will rise",
    "will fall",
)

PRIVACY_FORBIDDEN_TERMS = (
    "holdings line items",
    "account values",
    "position weights",
    "raw provider payload",
    "raw provider",
    "raw prompt",
    "api key",
    "api_key",
    ".env",
    "data/private",
    "current_holdings.csv",
    "transaction history",
    "credentials",
    "sk-",
)

MODEL_MODULE_LABELS = {
    "financial_stress_composite": "D10 financial stress",
    "pullback_systemic_risk_checklist": "D11 pullback/systemic review",
    "macro_regime_review": "D15 macro regime review",
    "scenario_stress": "D16 scenario stress",
    "growth_inflation_macro_pack": "D17 growth/inflation context",
    "valuation_equity_structure": "D18 valuation/equity structure",
    "historical_validation": "D19 historical validation",
    "portfolio_exposure_overlay": "Stage 8 portfolio exposure overlay",
}
EXCLUDED_RENDER_METRIC_KEYS = {
    "macro_regime_score",
}


def render_ai_memo_preview(memo_type: str, manifest: Any) -> AIMemoPreview:
    if memo_type not in MEMO_SECTION_KEYS:
        raise ValueError(f"Unsupported memo_type: {memo_type}")

    manifest_data = _manifest_to_dict(manifest)
    sections = [
        _render_section(section_key, manifest_data)
        for section_key in MEMO_SECTION_KEYS[memo_type]
    ]
    preview = AIMemoPreview(
        memo_type=memo_type,
        mode=MODE,
        title=MEMO_TITLES[memo_type],
        sections=sections,
        context_used_summary=_context_summary(manifest_data),
        privacy_summary=AIMemoPrivacySummary(
            uses_ai_context_manifest_only=True,
            uses_holdings_line_items=False,
            uses_raw_provider_payloads=False,
            uses_raw_prompts=False,
            external_model_called=False,
            search_called=False,
            saved_by_default=False,
        ),
        validator_result=AIMemoValidatorResult(
            passed=True,
            blocked_terms=[],
            privacy_findings=[],
        ),
        human_review_required=True,
        interpretation_boundary=BOUNDARY_NOTICE,
    )
    preview.validator_result = validate_ai_memo_preview(preview)
    return preview


def render_all_ai_memo_previews(manifest: Any) -> list[AIMemoPreview]:
    return [
        render_ai_memo_preview(memo_type, manifest)
        for memo_type in MEMO_SECTION_KEYS
    ]


def validate_ai_memo_preview(preview: AIMemoPreview | Mapping[str, Any]) -> AIMemoValidatorResult:
    payload = _preview_to_dict(preview)
    text = json.dumps(payload, sort_keys=True).lower()
    blocked_terms = sorted(
        term for term in FORBIDDEN_GENERATED_OUTPUT_TERMS if term in text
    )
    privacy_findings = sorted(term for term in PRIVACY_FORBIDDEN_TERMS if term in text)

    privacy_summary = payload.get("privacy_summary", {})
    if privacy_summary.get("external_model_called") is not False:
        privacy_findings.append("external_model_called")
    if privacy_summary.get("search_called") is not False:
        privacy_findings.append("search_called")
    if privacy_summary.get("saved_by_default") is not False:
        privacy_findings.append("saved_by_default")
    if payload.get("human_review_required") is not True:
        privacy_findings.append("human_review_required_missing")
    if not payload.get("interpretation_boundary"):
        privacy_findings.append("interpretation_boundary_missing")
    if not _sections_include_boundary(payload):
        privacy_findings.append("boundary_notice_missing")

    return AIMemoValidatorResult(
        passed=not blocked_terms and not privacy_findings,
        blocked_terms=blocked_terms,
        privacy_findings=sorted(set(privacy_findings)),
    )


def _render_section(section_key: str, manifest: dict[str, Any]) -> AIMemoSection:
    content, context = _section_content(section_key, manifest)
    return AIMemoSection(
        key=section_key,
        title=_title(section_key),
        content=content,
        source_context=context,
    )


def _section_content(section_key: str, manifest: dict[str, Any]) -> tuple[str, list[str]]:
    included_facts = _items(manifest, "included_facts")
    excluded_facts = _items(manifest, "excluded_facts")
    included_models = _items(manifest, "included_model_outputs")
    excluded_models = _items(manifest, "excluded_model_outputs")
    risk_boundaries = [str(item) for item in manifest.get("risk_boundaries") or []]

    if section_key == "as_of_context":
        generated_at = manifest.get("generated_at") or NO_ELIGIBLE_CONTEXT
        return f"Manifest generated at: {generated_at}", ["manifest.generated_at"]
    if section_key in {"evidence_summary", "included_context_summary"}:
        return _summarize_rows(included_facts, "Included facts"), _context_ids(included_facts)
    if section_key in {"model_output_summary", "D10_D19_model_summary"}:
        return _summarize_models(included_models), _context_ids(included_models)
    if section_key in {"primary_pressure_channels", "current_macro_state"}:
        rows = _rows_by_modules(
            included_models,
            {"financial_stress_composite", "macro_regime_review", "growth_inflation_macro_pack"},
        )
        return _summarize_models(rows), _context_ids(rows)
    if section_key in {"missing_or_excluded_constraints", "missing_constraints", "missing_inputs"}:
        return _summarize_constraints(excluded_facts, excluded_models), _context_ids(excluded_facts + excluded_models)
    if section_key in {"interpretation_boundaries", "boundary_notice", "boundary_and_privacy_notes"}:
        return _summarize_boundaries(risk_boundaries), ["manifest.risk_boundaries"]
    if section_key == "financial_stress_context":
        rows = _rows_by_modules(included_models, {"financial_stress_composite"})
        return _summarize_models(rows), _context_ids(rows)
    if section_key == "pullback_vs_systemic_review":
        rows = _rows_by_modules(included_models, {"pullback_systemic_risk_checklist"})
        return _summarize_models(rows), _context_ids(rows)
    if section_key == "liquidity_funding_context":
        rows = _rows_by_modules(included_facts + included_models, {"liquidity_funding_stress"})
        return _summarize_rows(rows, "Liquidity/funding context"), _context_ids(rows)
    if section_key in {"scenario_stress_notes", "selected_scenario", "affected_evidence_groups", "transmission_channels", "uncertainty_conditions"}:
        rows = _rows_by_modules(included_models + excluded_models, {"scenario_stress"})
        extra = "D16 remains a scenario matrix; no forecast phrasing or scenario odds."
        return _with_extra(_summarize_models(rows), extra), _context_ids(rows)
    if section_key == "not_a_forecast_notice":
        return "D16 remains a scenario matrix; not a forecast and not an event-odds model.", ["stage9.boundary.d16"]
    if section_key == "sanitized_portfolio_context_policy":
        policy = manifest.get("portfolio_context_policy") or {}
        mode = _safe(policy.get("mode")) or "compact_summary_only"
        return f"Portfolio context mode: {mode}. Private inputs remain excluded.", ["manifest.portfolio_context_policy"]
    if section_key in {"exposure_channel_summary", "macro_channel_mapping", "Stage8_overlay_summary"}:
        rows = _rows_by_modules(included_models + excluded_models, {"portfolio_exposure_overlay"})
        extra = "Stage 8 is sanitized compact explanatory overlay only; missing compact context remains a constraint."
        return _with_extra(_summarize_models(rows), extra), _context_ids(rows)
    if section_key == "private_inputs_excluded":
        return "Private inputs are excluded; sanitized compact context only.", ["manifest.privacy_policy"]
    if section_key == "not_action_directive_notice":
        return "This review is not an action directive and not a position-level output.", ["stage9.boundary.action"]
    if section_key == "executive_summary":
        return _executive_summary(included_facts, included_models), _context_ids(included_facts[:3] + included_models[:3])
    if section_key == "evidence_table_snapshot_summary":
        return _source_summary(manifest), ["manifest.source_summary"]
    if section_key == "missing_data_and_research_needed":
        return _summarize_constraints(excluded_facts, excluded_models), _context_ids(excluded_facts + excluded_models)
    if section_key == "appendix_manifest_stats":
        return _stats_summary(manifest), ["manifest.source_summary"]
    if section_key == "manifest_coverage":
        return _stats_summary(manifest), ["manifest.source_summary"]
    if section_key == "excluded_context_summary":
        return _summarize_constraints(excluded_facts, excluded_models), _context_ids(excluded_facts + excluded_models)
    if section_key == "source_and_freshness_notes":
        return _source_and_freshness_summary(included_facts), _context_ids(included_facts)
    if section_key == "privacy_policy_summary":
        return _privacy_policy_summary(manifest), ["manifest.privacy_policy", "manifest.persistence_policy", "manifest.search_policy"]
    if section_key == "validator_findings":
        return "Validator checks are required before display; current local template is validator-gated.", ["stage9.validator"]
    if section_key == "human_review_required":
        return "Human review is required before relying on this local deterministic preview.", ["stage9.human_review_required"]
    return NO_ELIGIBLE_CONTEXT, []


def _manifest_to_dict(manifest: Any) -> dict[str, Any]:
    if hasattr(manifest, "model_dump"):
        return manifest.model_dump()
    if hasattr(manifest, "dict"):
        return manifest.dict()
    if isinstance(manifest, Mapping):
        return dict(manifest)
    raise TypeError("manifest must be a mapping or Pydantic model")


def _preview_to_dict(preview: AIMemoPreview | Mapping[str, Any]) -> dict[str, Any]:
    if hasattr(preview, "model_dump"):
        return preview.model_dump()
    if hasattr(preview, "dict"):
        return preview.dict()
    return dict(preview)


def _items(manifest: dict[str, Any], key: str) -> list[dict[str, Any]]:
    return [item for item in manifest.get(key) or [] if isinstance(item, dict)]


def _context_summary(manifest: dict[str, Any]) -> AIMemoContextUsedSummary:
    return AIMemoContextUsedSummary(
        included_fact_count=len(_items(manifest, "included_facts")),
        excluded_fact_count=len(_items(manifest, "excluded_facts")),
        included_model_output_count=len(_items(manifest, "included_model_outputs")),
        excluded_model_output_count=len(_items(manifest, "excluded_model_outputs")),
    )


def _title(section_key: str) -> str:
    return section_key.replace("_", " ").title()


def _safe(value: Any) -> str:
    if value is None:
        return ""
    text = str(value)
    for term in PRIVACY_FORBIDDEN_TERMS:
        text = text.replace(term, "[excluded]")
    return text


def _row_label(row: dict[str, Any]) -> str:
    name = _safe(row.get("display_name") or row.get("metric_key") or "context")
    metric = _safe(row.get("metric_key") or "unknown_metric")
    module = _safe(row.get("module") or "unknown_module")
    status = _safe(row.get("status") or "unknown")
    source_badge = _safe(row.get("source_badge") or "unknown_source")
    freshness = _safe(row.get("freshness_status") or "unknown_freshness")
    boundary = _safe(row.get("interpretation_boundary") or row.get("interpretation_hint") or "")
    boundary_text = f"; boundary: {boundary}" if boundary else ""
    return f"{name} ({module}.{metric}) status={status}, source={source_badge}, freshness={freshness}{boundary_text}"


def _summarize_rows(rows: list[dict[str, Any]], heading: str) -> str:
    if not rows:
        return NO_ELIGIBLE_CONTEXT
    labels = [_row_label(row) for row in rows[:5]]
    suffix = f" Additional eligible rows: {len(rows) - 5}." if len(rows) > 5 else ""
    return f"{heading}: " + " | ".join(labels) + suffix


def _summarize_models(rows: list[dict[str, Any]]) -> str:
    rows = [
        row
        for row in rows
        if str(row.get("metric_key") or "") not in EXCLUDED_RENDER_METRIC_KEYS
    ]
    if not rows:
        return NO_ELIGIBLE_CONTEXT
    labels = []
    for row in rows[:6]:
        module = row.get("module")
        prefix = MODEL_MODULE_LABELS.get(str(module), str(module or "model context"))
        labels.append(f"{prefix}: {_row_label(row)}")
    suffix = f" Additional eligible model rows: {len(rows) - 6}." if len(rows) > 6 else ""
    return "Model context: " + " | ".join(labels) + suffix


def _summarize_constraints(
    excluded_facts: list[dict[str, Any]],
    excluded_models: list[dict[str, Any]],
) -> str:
    rows = excluded_facts + excluded_models
    if not rows:
        return NO_ELIGIBLE_CONTEXT
    labels = []
    for row in rows[:6]:
        reason = _safe(row.get("excluded_reason") or row.get("missing_reason") or "excluded")
        labels.append(f"{_row_label(row)}; constraint={reason}")
    suffix = f" Additional excluded rows: {len(rows) - 6}." if len(rows) > 6 else ""
    return "Excluded context constraints: " + " | ".join(labels) + suffix


def _summarize_boundaries(boundaries: list[str]) -> str:
    if not boundaries:
        return BOUNDARY_NOTICE
    selected = [_safe(boundary) for boundary in boundaries[:8]]
    return "Boundary notices: " + " | ".join(selected) + f" | {BOUNDARY_NOTICE}"


def _rows_by_modules(rows: list[dict[str, Any]], modules: set[str]) -> list[dict[str, Any]]:
    return [row for row in rows if row.get("module") in modules]


def _context_ids(rows: list[dict[str, Any]]) -> list[str]:
    ids = []
    allowed_rows = [
        row
        for row in rows
        if str(row.get("metric_key") or "") not in EXCLUDED_RENDER_METRIC_KEYS
    ]
    for row in allowed_rows[:10]:
        module = _safe(row.get("module") or "unknown_module")
        metric = _safe(row.get("metric_key") or "unknown_metric")
        ids.append(f"{module}.{metric}")
    return ids


def _with_extra(content: str, extra: str) -> str:
    if content == NO_ELIGIBLE_CONTEXT:
        return f"{content} {extra}"
    return f"{content} {extra}"


def _executive_summary(
    included_facts: list[dict[str, Any]],
    included_models: list[dict[str, Any]],
) -> str:
    if not included_facts and not included_models:
        return NO_ELIGIBLE_CONTEXT
    return (
        f"Manifest-backed local preview with {len(included_facts)} included facts "
        f"and {len(included_models)} included model outputs. {BOUNDARY_NOTICE}"
    )


def _source_summary(manifest: dict[str, Any]) -> str:
    source_summary = manifest.get("source_summary") or {}
    if not source_summary:
        return NO_ELIGIBLE_CONTEXT
    total = source_summary.get("total_evidence_rows", "unknown")
    badges = source_summary.get("source_badge_distribution") or {}
    return f"Evidence table snapshot: total_rows={total}, source_badges={badges}"


def _stats_summary(manifest: dict[str, Any]) -> str:
    summary = _context_summary(manifest)
    source_summary = manifest.get("source_summary") or {}
    total = source_summary.get("total_evidence_rows", "unknown")
    return (
        f"Manifest stats: total_rows={total}, included_facts={summary.included_fact_count}, "
        f"excluded_facts={summary.excluded_fact_count}, included_model_outputs="
        f"{summary.included_model_output_count}, excluded_model_outputs="
        f"{summary.excluded_model_output_count}."
    )


def _source_and_freshness_summary(rows: list[dict[str, Any]]) -> str:
    if not rows:
        return NO_ELIGIBLE_CONTEXT
    pairs = sorted(
        {
            (
                str(row.get("source_badge") or "unknown_source"),
                str(row.get("freshness_status") or "unknown_freshness"),
            )
            for row in rows
        }
    )
    return "Source/freshness combinations: " + ", ".join(
        f"{source}/{freshness}" for source, freshness in pairs
    )


def _privacy_policy_summary(manifest: dict[str, Any]) -> str:
    privacy = manifest.get("privacy_policy") or {}
    search = manifest.get("search_policy") or {}
    persistence = manifest.get("persistence_policy") or {}
    return (
        "Privacy policy: sanitized manifest context only; "
        f"returns_sanitized_evidence_rows_only={privacy.get('returns_sanitized_evidence_rows_only')}; "
        f"search_enabled={search.get('search_enabled')}; "
        f"saves_manifest={persistence.get('saves_manifest')}; "
        "local preview is not saved by default."
    )


def _sections_include_boundary(payload: dict[str, Any]) -> bool:
    section_text = " ".join(
        str(section.get("content", ""))
        for section in payload.get("sections", [])
        if isinstance(section, dict)
    ).lower()
    boundary = str(payload.get("interpretation_boundary") or "").lower()
    return bool(boundary) and (
        "not an action directive" in section_text
        or "human review is required" in section_text
        or "not an action directive" in boundary
    )
