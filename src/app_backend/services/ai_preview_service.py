from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from app_backend.schemas.ai_memo import (
    AIMemoContextUsedSummary,
    AIMemoPrivacySummary,
    AIMemoSection,
    AIMemoValidatorResult,
)
from app_backend.schemas.ai_preview import (
    AIContextPreviewResponse,
    AIPreviewChatRequest,
    AIPreviewChatResponse,
    AIPreviewMemoResponse,
    AIPreviewReportRequest,
    AIPreviewMemoRequest,
)
from app_backend.schemas.responses import AIContextManifestResponse
from app_backend.services import ai_context_service
from app_backend.services.ai_memo_renderer import (
    BOUNDARY_NOTICE,
    FORBIDDEN_GENERATED_OUTPUT_TERMS,
    NO_ELIGIBLE_CONTEXT,
    PRIVACY_FORBIDDEN_TERMS,
    render_ai_memo_preview,
)


CHAT_SECTION_KEYS = [
    "request_scope",
    "evidence_summary",
    "model_output_summary",
    "missing_or_excluded_constraints",
    "portfolio_overlay_summary",
    "boundary_notice",
    "human_review_required",
]
MODE = "local_preview"


def build_context_preview() -> AIContextPreviewResponse:
    manifest = ai_context_service.build_ai_context_manifest()
    data = _manifest_to_dict(manifest)
    summary = _context_summary(data)
    return AIContextPreviewResponse(
        **data,
        mode=MODE,
        search_enabled=False,
        external_model_called=False,
        search_called=False,
        saved_by_default=False,
        included_fact_count=summary.included_fact_count,
        excluded_fact_count=summary.excluded_fact_count,
        included_model_output_count=summary.included_model_output_count,
        excluded_model_output_count=summary.excluded_model_output_count,
        context_stats={
            "included_fact_count": summary.included_fact_count,
            "excluded_fact_count": summary.excluded_fact_count,
            "included_model_output_count": summary.included_model_output_count,
            "excluded_model_output_count": summary.excluded_model_output_count,
            "source_summary": data.get("source_summary") or {},
        },
        last_generated_at=data.get("generated_at"),
    )


def render_chat_preview(request: AIPreviewChatRequest) -> AIPreviewChatResponse:
    manifest = ai_context_service.build_ai_context_manifest()
    manifest_data = _manifest_to_dict(manifest)
    sections = [
        _chat_section(section_key, request, manifest_data)
        for section_key in CHAT_SECTION_KEYS
    ]
    answer_preview = _answer_preview(request, manifest_data)
    response = AIPreviewChatResponse(
        mode=MODE,
        answer_preview=answer_preview,
        sections=sections,
        context_used_summary=_context_summary(manifest_data),
        privacy_summary=_privacy_summary(),
        validator_result=AIMemoValidatorResult(
            passed=True,
            blocked_terms=[],
            privacy_findings=[],
        ),
        not_sent_to_external_model=True,
        human_review_required=True,
        interpretation_boundary=BOUNDARY_NOTICE,
    )
    response.validator_result = validate_ai_preview_payload(response)
    return response


def render_memo_preview(request: AIPreviewMemoRequest) -> AIPreviewMemoResponse:
    manifest = ai_context_service.build_ai_context_manifest()
    preview = render_ai_memo_preview(request.memo_type, manifest).as_dict()
    preview["mode"] = MODE
    preview["not_sent_to_external_model"] = True
    response = AIPreviewMemoResponse(**preview)
    response.validator_result = validate_ai_preview_payload(response)
    return response


def render_report_preview(request: AIPreviewReportRequest) -> AIPreviewMemoResponse:
    manifest = ai_context_service.build_ai_context_manifest()
    preview = render_ai_memo_preview(request.report_type, manifest).as_dict()
    preview["mode"] = MODE
    preview["not_sent_to_external_model"] = True
    response = AIPreviewMemoResponse(**preview)
    response.validator_result = validate_ai_preview_payload(response)
    return response


def validate_ai_preview_payload(payload: Any) -> AIMemoValidatorResult:
    data = _model_to_dict(payload)
    text = json.dumps(data, sort_keys=True).lower()
    blocked_terms = sorted(
        term for term in FORBIDDEN_GENERATED_OUTPUT_TERMS if term in text
    )
    privacy_findings = sorted(term for term in PRIVACY_FORBIDDEN_TERMS if term in text)

    privacy_summary = data.get("privacy_summary", {})
    if privacy_summary.get("external_model_called") is not False:
        privacy_findings.append("external_model_called")
    if privacy_summary.get("search_called") is not False:
        privacy_findings.append("search_called")
    if privacy_summary.get("saved_by_default") is not False:
        privacy_findings.append("saved_by_default")
    if data.get("not_sent_to_external_model") is not True:
        privacy_findings.append("not_sent_to_external_model_missing")
    if data.get("human_review_required") is not True:
        privacy_findings.append("human_review_required_missing")
    if not data.get("interpretation_boundary"):
        privacy_findings.append("interpretation_boundary_missing")
    if not _sections_include_boundary(data):
        privacy_findings.append("boundary_notice_missing")

    return AIMemoValidatorResult(
        passed=not blocked_terms and not privacy_findings,
        blocked_terms=blocked_terms,
        privacy_findings=sorted(set(privacy_findings)),
    )


def _chat_section(
    section_key: str,
    request: AIPreviewChatRequest,
    manifest: dict[str, Any],
) -> AIMemoSection:
    content, source_context = _chat_section_content(section_key, request, manifest)
    return AIMemoSection(
        key=section_key,
        title=section_key.replace("_", " ").title(),
        content=content,
        source_context=source_context,
    )


def _chat_section_content(
    section_key: str,
    request: AIPreviewChatRequest,
    manifest: dict[str, Any],
) -> tuple[str, list[str]]:
    included_facts = _items(manifest, "included_facts")
    included_models = _items(manifest, "included_model_outputs")
    excluded_facts = _items(manifest, "excluded_facts")
    excluded_models = _items(manifest, "excluded_model_outputs")

    if section_key == "request_scope":
        return (
            f"Local preview request summarized without prompt storage; style={request.style}, context_mode={request.context_mode}.",
            ["request.local_preview"],
        )
    if section_key == "evidence_summary":
        if request.context_mode == "model_outputs_only":
            return _count_only("Facts", included_facts), []
        return _summarize_rows(included_facts, "Eligible facts"), _context_ids(included_facts)
    if section_key == "model_output_summary":
        if request.context_mode == "facts_only":
            return _count_only("Model outputs", included_models), []
        return _summarize_rows(included_models, "Eligible model context"), _context_ids(included_models)
    if section_key == "missing_or_excluded_constraints":
        return _summarize_constraints(excluded_facts, excluded_models), _context_ids(excluded_facts + excluded_models)
    if section_key == "portfolio_overlay_summary":
        policy = manifest.get("portfolio_context_policy") or {}
        mode = _safe(policy.get("mode")) or "compact_summary_only"
        rows = [
            row
            for row in included_models + excluded_models
            if row.get("module") == "portfolio_exposure_overlay"
        ]
        if not rows:
            return f"Portfolio overlay policy: {mode}. No eligible overlay context is available.", ["manifest.portfolio_context_policy"]
        return (
            f"Portfolio overlay policy: {mode}. {_summarize_rows(rows, 'Sanitized overlay context')}",
            _context_ids(rows),
        )
    if section_key == "boundary_notice":
        return BOUNDARY_NOTICE, ["stage9.boundary"]
    if section_key == "human_review_required":
        return "Human review is required before relying on this local deterministic preview.", ["stage9.human_review_required"]
    return NO_ELIGIBLE_CONTEXT, []


def _answer_preview(request: AIPreviewChatRequest, manifest: dict[str, Any]) -> str:
    summary = _context_summary(manifest)
    facts = _items(manifest, "included_facts")
    models = _items(manifest, "included_model_outputs")
    excluded = _items(manifest, "excluded_facts") + _items(manifest, "excluded_model_outputs")

    if request.context_mode == "facts_only":
        support = _summarize_rows(facts, "eligible facts")
    elif request.context_mode == "model_outputs_only":
        support = _summarize_rows(models, "eligible model context")
    else:
        support = (
            f"{_summarize_rows(facts, 'eligible facts')} "
            f"{_summarize_rows(models, 'eligible model context')}"
        )
    constraints = _summarize_constraints(excluded, [])
    if request.style == "structured":
        return (
            "Local preview only.\n"
            f"- Eligible context counts: facts={summary.included_fact_count}, model_outputs={summary.included_model_output_count}.\n"
            f"- Context summary: {support}\n"
            f"- Constraints: {constraints}\n"
            f"- Boundary: {BOUNDARY_NOTICE}"
        )
    return (
        "Local preview only. Based on the current AI Context Manifest, the eligible "
        f"context includes {summary.included_fact_count} facts and "
        f"{summary.included_model_output_count} model outputs. {support} "
        f"Missing or excluded constraints include: {constraints}. {BOUNDARY_NOTICE}"
    )


def _manifest_to_dict(manifest: AIContextManifestResponse | Mapping[str, Any]) -> dict[str, Any]:
    return _model_to_dict(manifest)


def _model_to_dict(value: Any) -> dict[str, Any]:
    if hasattr(value, "model_dump"):
        return value.model_dump()
    if hasattr(value, "dict"):
        return value.dict()
    if isinstance(value, Mapping):
        return dict(value)
    raise TypeError("value must be a mapping or Pydantic model")


def _context_summary(manifest: dict[str, Any]) -> AIMemoContextUsedSummary:
    return AIMemoContextUsedSummary(
        included_fact_count=len(_items(manifest, "included_facts")),
        excluded_fact_count=len(_items(manifest, "excluded_facts")),
        included_model_output_count=len(_items(manifest, "included_model_outputs")),
        excluded_model_output_count=len(_items(manifest, "excluded_model_outputs")),
    )


def _privacy_summary() -> AIMemoPrivacySummary:
    return AIMemoPrivacySummary(
        uses_ai_context_manifest_only=True,
        uses_holdings_line_items=False,
        uses_raw_provider_payloads=False,
        uses_raw_prompts=False,
        external_model_called=False,
        search_called=False,
        saved_by_default=False,
    )


def _items(manifest: dict[str, Any], key: str) -> list[dict[str, Any]]:
    return [item for item in manifest.get(key) or [] if isinstance(item, dict)]


def _safe(value: Any) -> str:
    if value is None:
        return ""
    text = str(value)
    for term in PRIVACY_FORBIDDEN_TERMS:
        text = text.replace(term, "[excluded]")
    return text


def _row_label(row: dict[str, Any]) -> str:
    name = _safe(row.get("display_name") or row.get("metric_key") or "context")
    module = _safe(row.get("module") or "unknown_module")
    metric = _safe(row.get("metric_key") or "unknown_metric")
    status = _safe(row.get("status") or "unknown")
    source_badge = _safe(row.get("source_badge") or "unknown_source")
    freshness = _safe(row.get("freshness_status") or "unknown_freshness")
    boundary = _safe(row.get("interpretation_boundary") or "")
    boundary_text = f"; boundary: {boundary}" if boundary else ""
    return f"{name} ({module}.{metric}) status={status}, source={source_badge}, freshness={freshness}{boundary_text}"


def _summarize_rows(rows: list[dict[str, Any]], heading: str) -> str:
    if not rows:
        return NO_ELIGIBLE_CONTEXT
    labels = [_row_label(row) for row in rows[:4]]
    suffix = f" Additional rows available: {len(rows) - 4}." if len(rows) > 4 else ""
    return f"{heading}: " + " | ".join(labels) + suffix


def _count_only(label: str, rows: list[dict[str, Any]]) -> str:
    return f"{label} available in manifest: {len(rows)}. Not used as support for this context mode."


def _summarize_constraints(
    excluded_facts: list[dict[str, Any]],
    excluded_models: list[dict[str, Any]],
) -> str:
    rows = excluded_facts + excluded_models
    if not rows:
        return NO_ELIGIBLE_CONTEXT
    labels = []
    for row in rows[:5]:
        reason = _safe(row.get("excluded_reason") or row.get("missing_reason") or "excluded")
        labels.append(f"{_row_label(row)}; constraint={reason}")
    suffix = f" Additional excluded rows: {len(rows) - 5}." if len(rows) > 5 else ""
    return "Excluded context constraints: " + " | ".join(labels) + suffix


def _context_ids(rows: list[dict[str, Any]]) -> list[str]:
    return [
        f"{_safe(row.get('module') or 'unknown_module')}.{_safe(row.get('metric_key') or 'unknown_metric')}"
        for row in rows[:10]
    ]


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
