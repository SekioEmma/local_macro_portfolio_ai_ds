"""Domain-aware validation for local research and prompt previews."""

from __future__ import annotations

import re
from typing import Any

from app_backend.schemas.ai_memo import AIMemoValidatorResult
from app_backend.schemas.ai_preview import (
    AIResearchValidationResult,
    AISemanticFinding,
)
from app_backend.services.ai_memo_renderer import (
    FORBIDDEN_GENERATED_OUTPUT_TERMS,
    PRIVACY_FORBIDDEN_TERMS,
)
from app_backend.services.ai_semantic_validator import (
    ResearchSemanticFinding,
    validate_structured_research_semantics,
)


_SEVERITY_ORDER = {"info": 0, "warning": 1, "error": 2, "blocker": 3}
_CHINESE_ACTION_PATTERNS = (
    re.compile(
        r"(建议|应该|可以|现在要|需要)(立即|马上)?"
        r"(买入|卖出|加仓|减仓|清仓|抄底|对冲|再平衡)"
    ),
    re.compile(r"(危机|衰退|股灾)概率\s*(为|是|达到|约为)"),
    re.compile(r"(目标配置|目标权重|目标价|最优配置)"),
)


def validate_research_domains(
    *,
    system_boundary: str,
    task_instruction: str,
    selected_context: str,
    model_answer: str,
    validator_explanation: str,
    sections: list[Any],
    selected_cards: list[Any],
    prompt_ready: bool = True,
) -> tuple[AIMemoValidatorResult, AIResearchValidationResult]:
    """Validate text domains without scanning fixed boundary copy as output.

    Generated-output terms are scanned only in ``model_answer``. Privacy
    markers are scanned in both ``selected_context`` and ``model_answer``.
    The fixed server-owned boundary/task/validator domains are reported as
    isolated, but they are not treated as generated financial advice.
    """

    findings: list[AISemanticFinding] = []
    blocked_terms = _generated_output_findings(model_answer)
    privacy_findings = _privacy_findings(
        selected_context=selected_context,
        model_answer=model_answer,
    )
    for term in blocked_terms:
        findings.append(
            AISemanticFinding(
                code=f"forbidden_generated_output:{term}",
                category="language_boundary",
                severity="blocker",
                message_zh="本地研究预览出现了交易动作、概率或收益预测语言。",
                matched_claims=[term],
            )
        )
    for _term in privacy_findings:
        findings.append(
            AISemanticFinding(
                code="privacy_marker_detected",
                category="privacy",
                severity="blocker",
                message_zh="选中上下文或研究答案出现了禁止的隐私标记。",
                matched_claims=[],
            )
        )

    for finding in validate_structured_research_semantics(
        sections,
        selected_cards=selected_cards,
    ):
        findings.append(_semantic_model(finding))

    if not prompt_ready:
        findings.append(
            AISemanticFinding(
                code="p1_context_exceeds_prompt_budget",
                category="prompt_budget",
                severity="error",
                message_zh=(
                    "P1 核心上下文本身超过本地预算；核心证据未截断，"
                    "因此 Prompt 当前不可发送。"
                ),
                required_context=["manual_budget_review"],
            )
        )

    blocked = any(finding.severity == "blocker" for finding in findings)
    max_severity = (
        max(
            (finding.severity for finding in findings),
            key=lambda severity: _SEVERITY_ORDER[severity],
        )
        if findings
        else None
    )
    legacy = AIMemoValidatorResult(
        passed=not blocked,
        blocked_terms=blocked_terms,
        privacy_findings=(
            ["privacy_marker_detected"] if privacy_findings else []
        ),
    )
    result = AIResearchValidationResult(
        passed=not blocked,
        blocked=blocked,
        max_severity=max_severity,
        findings=findings,
        domain_checks={
            "system_boundary": "fixed_server_template_not_output_scanned",
            "task_instruction": "fixed_server_template_not_output_scanned",
            "selected_context": "privacy_scanned",
            "model_answer": "language_and_privacy_scanned",
            "validator_explanation": (
                "fixed_server_explanation_not_output_scanned"
                if validator_explanation
                else "not_present"
            ),
        },
    )
    return legacy, result


def _generated_output_findings(text: str) -> list[str]:
    lowered = text.lower()
    findings = {
        term for term in FORBIDDEN_GENERATED_OUTPUT_TERMS if term in lowered
    }
    for pattern in _CHINESE_ACTION_PATTERNS:
        match = pattern.search(text)
        if match:
            findings.add(match.group(0))
    return sorted(findings)


def _privacy_findings(
    *,
    selected_context: str,
    model_answer: str,
) -> list[str]:
    text = f"{selected_context}\n{model_answer}".lower()
    return sorted(term for term in PRIVACY_FORBIDDEN_TERMS if term in text)


_CLAIM_TYPE_PATTERN = re.compile(
    r"\[claim_type\s*=\s*"
    r"(direct_evidence|cross_evidence_inference|interpretive|watchlist)\s*\]"
)
_THRESHOLD_SOURCE_PATTERN = re.compile(
    r"\[threshold_source\s*=\s*"
    r"(project_band|historical_percentile|heuristic_watchlist)\s*\]"
)
_NUMERIC_THRESHOLD_PATTERN = re.compile(
    r"\d+\.?\d*\s*(%|pp|个百分点|bp|bps|基点)"
)
_SOURCE_BADGE_KEYWORDS = (
    "source_badge", "official", "official_fallback", "proxy", "derived",
    "reference_only", "freshness",
)


def validate_deepseek_output_constraints(
    model_answer: str,
) -> list[AISemanticFinding]:
    """Check DeepSeek output for claim_type, threshold_source, and source_badge."""
    findings: list[AISemanticFinding] = []

    claim_type_matches = _CLAIM_TYPE_PATTERN.findall(model_answer)
    if not claim_type_matches:
        findings.append(
            AISemanticFinding(
                code="missing_claim_type_annotations",
                category="evidence_layer",
                severity="warning",
                message_zh="DeepSeek 输出未包含任何 [claim_type=...] 标注，无法区分证据直接支持和经验解释。",
            )
        )

    numeric_thresholds = _NUMERIC_THRESHOLD_PATTERN.findall(model_answer)
    threshold_sources = _THRESHOLD_SOURCE_PATTERN.findall(model_answer)
    if len(numeric_thresholds) > 0 and len(threshold_sources) == 0:
        findings.append(
            AISemanticFinding(
                code="missing_threshold_source_annotations",
                category="evidence_layer",
                severity="warning",
                message_zh="DeepSeek 输出包含数值阈值但未标注 [threshold_source=...]，无法区分项目触发线和模型自生阈值。",
            )
        )

    data_constraint_match = re.search(
        r"##\s*数据约束(.*?)(?=##|\Z)", model_answer, re.DOTALL
    )
    if data_constraint_match:
        section_text = data_constraint_match.group(1)
        has_badge_info = any(kw in section_text.lower() for kw in _SOURCE_BADGE_KEYWORDS)
        if not has_badge_info:
            findings.append(
                AISemanticFinding(
                    code="missing_source_badge_summary",
                    category="source_quality",
                    severity="warning",
                    message_zh="「数据约束」段未包含 source_badge / freshness 分布摘要。",
                )
            )

    return findings


def _semantic_model(finding: ResearchSemanticFinding) -> AISemanticFinding:
    return AISemanticFinding(
        code=finding.code,
        category=finding.category,
        severity=finding.severity,  # type: ignore[arg-type]
        message_zh=finding.message_zh,
        matched_claims=finding.matched_claims,
        cited_context_ids=finding.cited_context_ids,
        required_context=finding.required_context,
    )


__all__ = ["validate_deepseek_output_constraints", "validate_research_domains"]
