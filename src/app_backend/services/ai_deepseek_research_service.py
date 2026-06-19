"""AI-2 single-turn DeepSeek research service.

Orchestrates: input validation → manifest → prompt context → DeepSeek call
→ output validation → structured response.

Single-turn only. No multi-turn, no SSE, no persistence, no search.
Context comes exclusively from selected_prompt_context (not raw data).
"""

from __future__ import annotations

import re
import time
import uuid
from typing import Any

from app_backend.schemas.ai_external import (
    ExternalAIRequest,
    ExternalAIRuntimePolicy,
)
from app_backend.schemas.ai_memo import (
    AIMemoContextUsedSummary,
    AIMemoPrivacySummary,
    AIMemoValidatorResult,
)
from app_backend.schemas.ai_preview import (
    AIDeepSeekResearchRequest,
    AIDeepSeekResearchResponse,
    AISelectedPromptContext,
    AnswerMode,
    DetailLevel,
)
from app_backend.services import ai_context_service
from app_backend.services.ai_prompt_context import select_prompt_context
from app_backend.services.ai_research_modes import (
    ANSWER_MODE_TASKS_ZH,
    ANSWER_MODE_TITLES_ZH,
    ANSWER_MODE_TO_MEMO_TYPE,
)
from app_backend.services.ai_research_renderer import (
    INTERPRETATION_BOUNDARY_ZH,
    OUTPUT_CONTRACT_ZH,
    PREFLIGHT_CHECKLIST_ZH,
    SYSTEM_BOUNDARY_ZH,
)
from app_backend.services.ai_research_validator import (
    validate_deepseek_output_constraints,
    validate_research_domains,
)
from app_backend.services.deepseek_adapter import (
    BlockedAdapterError,
    DeepSeekNetworkAdapter,
    network_config,
)
from app_backend.services.deepseek_real_transport import (
    DeepSeekRealTransport,
    load_deepseek_api_key_from_env,
)

_CHINESE_ACTION_PATTERNS = (
    re.compile(
        r"(建议|应该|可以|现在要|需要)(立即|马上)?"
        r"(买入|卖出|加仓|减仓|清仓|抄底|对冲|再平衡)"
    ),
    re.compile(r"(危机|衰退|股灾)概率"),
    re.compile(r"(目标配置|目标权重|目标价|最优配置)"),
    re.compile(r"(我的|我账户的|账户)(持仓|仓位|权重|明细|交易)"),
    re.compile(r"(api.?key|密钥|密码)"),
)

_FORBIDDEN_INPUT_TERMS = {
    "buy", "sell", "target allocation", "target weight",
    "crash probability", "recession probability",
    "holdings line items", "account values",
    "position weights", "transaction history",
    "api_key", "api key", "deepseek_api_key",
}

_SECTION_FORMAT_INSTRUCTION = """请严格按以下 7 段结构回答，每段以标题行开头。
每段核心判断必须在行首标注 [claim_type=xxx]，可选值：
  direct_evidence — 直接由单一证据卡片支持的事实陈述
  cross_evidence_inference — 多张卡片交叉推断的结论
  interpretive — 宏观经验判断或历史类比，需明确标注证据不足
  watchlist — 观察性启发条件，不构成结论

## 当前结论
（基于当前证据，市场宏观状态的核心判断。每条判断标注 [claim_type=...]，必须注明证据支持程度。）

## 支持证据
（列出支持当前结论的具体证据，引用对应的 evidence/model context id。每条标注 [claim_type=direct_evidence] 或 [claim_type=cross_evidence_inference]。）

## 反向证据
（列出与结论矛盾或削弱结论的证据，同样引用 context id。反向证据只约束其对应叙事，不扩展为其他叙事的反证。）

## 数据约束
（列出缺失、代理、陈旧或来源门禁约束，明确哪些结论因此不够可靠。必须包含引用证据的 source_badge 分布（official/official_fallback/proxy/derived/reference_only）和 freshness 分布（fresh/stale/historical）。不能引用 excluded 项作为强结论支撑。）

## 宏观解释
（对上述证据做宏观金融逻辑串联，解释传导路径。每条判断标注 [claim_type=...]。宏观经验判断和历史类比必须标注 [claim_type=interpretive]，并明确证据边界。"市场可能认为"类推断必须标注 [claim_type=interpretive] 且加注证据不足。）

## 组合通道
（仅限本地清洗后的紧凑风险通道解释；不输出持仓、配置或交易建议。）

## 观察清单与边界
（列出后续需要观察的指标和边界条件。任何数值阈值后必须标注 [threshold_source=project_band|historical_percentile|heuristic_watchlist]。模型自行生成的阈值为 heuristic_watchlist，不得描述为项目触发线。明确本回答不是预测、不是概率、不是交易建议。）"""


def validate_user_question(question: str) -> tuple[bool, list[str]]:
    """Validate user question against input boundary rules."""
    findings: list[str] = []
    lowered = question.lower()

    for term in _FORBIDDEN_INPUT_TERMS:
        if term in lowered:
            findings.append(f"forbidden_input_term:{term}")

    for pattern in _CHINESE_ACTION_PATTERNS:
        match = pattern.search(question)
        if match:
            findings.append(f"forbidden_input_pattern:{match.group(0)}")

    return len(findings) == 0, findings


def build_deepseek_prompt(
    *,
    answer_mode: AnswerMode,
    detail_level: DetailLevel,
    user_question: str,
    selected_context: AISelectedPromptContext,
) -> str:
    """Construct the full prompt text for DeepSeek."""
    task_zh = ANSWER_MODE_TASKS_ZH.get(answer_mode, "请基于证据进行宏观研究分析。")
    title_zh = ANSWER_MODE_TITLES_ZH.get(answer_mode, "宏观研究")
    detail_instruction = {
        "brief": "请简洁回答，每段 2-3 句。",
        "standard": "请适度展开，每段 3-5 句。",
        "deep": "请深入分析，每段 5-8 句，充分引用证据。",
    }[detail_level]

    output_contract = "\n".join(f"- {item}" for item in OUTPUT_CONTRACT_ZH)
    preflight = "\n".join(f"- {item}" for item in PREFLIGHT_CHECKLIST_ZH)
    source_quality = _build_source_quality_summary(selected_context.selected_cards)

    parts = [
        f"[系统边界]\n{SYSTEM_BOUNDARY_ZH}",
        f"[任务: {title_zh}]\n{task_zh}",
        f"[详细程度]\n{detail_instruction}",
        f"[输出合同]\n{output_contract}",
        f"[预检清单]\n{preflight}",
        f"[选中的证据上下文]\n{selected_context.selected_context_text}",
        f"[上下文选择说明]\n" + "\n".join(selected_context.selection_notes),
        f"[约束摘要]\n{selected_context.constraint_summary.summary_zh}",
        f"[来源与新鲜度摘要]\n{source_quality}",
        _SECTION_FORMAT_INSTRUCTION,
        f"[用户问题]\n{user_question}",
    ]
    return "\n\n".join(parts)


def _build_source_quality_summary(selected_cards: list[Any]) -> str:
    """Pre-aggregate source_badge and freshness distributions for the prompt."""
    from collections import Counter

    badge_counter: Counter[str] = Counter()
    freshness_counter: Counter[str] = Counter()
    for card in selected_cards:
        badge = getattr(card, "source_badge", None) or "unknown"
        freshness = getattr(card, "freshness_status", None) or "unknown"
        badge_counter[str(badge)] += 1
        freshness_counter[str(freshness)] += 1

    total = len(selected_cards)
    if total == 0:
        return "无选中证据卡片。"

    badge_parts = [f"{k}={v}" for k, v in sorted(badge_counter.items())]
    freshness_parts = [f"{k}={v}" for k, v in sorted(freshness_counter.items())]
    return (
        f"本次引用 {total} 张证据卡片。\n"
        f"source_badge 分布: {', '.join(badge_parts)}\n"
        f"freshness 分布: {', '.join(freshness_parts)}\n"
        f"请在「数据约束」段复述此分布，不能引用 excluded 项作为强结论支撑。"
    )


def _build_runtime_policy() -> ExternalAIRuntimePolicy:
    """Build a fully-approved runtime policy for AI-2 single-turn."""
    return ExternalAIRuntimePolicy(
        provider="deepseek",
        external_ai_enabled=True,
        provider_network_enabled=True,
        user_controlled_switch_enabled=True,
        single_request_user_approved=True,
        context_preview_confirmed=True,
        request_built_from_manifest=True,
        request_guard_passed=True,
        response_guard_required=True,
        stage9_validator_required=True,
        human_review_required=True,
        save_raw_prompt=False,
        save_raw_response=False,
        persist_chat_by_default=False,
        allow_search=False,
        allow_tavily=False,
        allow_background_call=False,
        allow_app_start_call=False,
        allow_page_load_call=False,
        allow_holdings_line_items=False,
        allow_account_values=False,
        allow_position_weights=False,
        allow_transaction_history=False,
        policy_version="ai_2_single_turn",
    )


def _manifest_to_dict(manifest: Any) -> dict[str, Any]:
    if hasattr(manifest, "model_dump"):
        return manifest.model_dump()
    if isinstance(manifest, dict):
        return manifest
    return dict(manifest)


def _context_summary(manifest: dict[str, Any]) -> AIMemoContextUsedSummary:
    included_facts = manifest.get("included_facts") or []
    excluded_facts = manifest.get("excluded_facts") or []
    included_models = manifest.get("included_model_outputs") or []
    excluded_models = manifest.get("excluded_model_outputs") or []
    return AIMemoContextUsedSummary(
        included_fact_count=len(included_facts),
        excluded_fact_count=len(excluded_facts),
        included_model_output_count=len(included_models),
        excluded_model_output_count=len(excluded_models),
    )


def run_deepseek_research(
    request: AIDeepSeekResearchRequest,
) -> AIDeepSeekResearchResponse:
    """Execute a single-turn DeepSeek research call."""
    t0 = time.monotonic()

    input_ok, input_findings = validate_user_question(request.user_question)
    if not input_ok:
        return _blocked_response(
            request=request,
            reason="input_validation_failed",
            input_findings=input_findings,
        )

    manifest = ai_context_service.build_ai_context_manifest()
    manifest_data = _manifest_to_dict(manifest)

    selected_context, budget = select_prompt_context(
        manifest_data,
        answer_mode=request.answer_mode,
    )

    if not budget.ready:
        return _blocked_response(
            request=request,
            reason="prompt_budget_not_ready",
            input_findings=[],
            selected_context=selected_context,
            budget=budget,
            manifest_data=manifest_data,
        )

    prompt_text = build_deepseek_prompt(
        answer_mode=request.answer_mode,
        detail_level=request.detail_level,
        user_question=request.user_question,
        selected_context=selected_context,
    )

    api_key = load_deepseek_api_key_from_env()
    transport = DeepSeekRealTransport(api_key=api_key, timeout_seconds=60.0)
    policy = _build_runtime_policy()
    config = network_config()
    adapter = DeepSeekNetworkAdapter(
        config, transport=transport, runtime_policy=policy,
    )

    request_id = str(uuid.uuid4())
    external_request = ExternalAIRequest(
        request_id=request_id,
        provider="deepseek",
        mode="network",
        user_intent_summary=request.user_question,
        context_preview_summary=prompt_text,
        included_fact_count=budget.selected_card_count,
        included_model_output_count=0,
        excluded_context_summary=selected_context.constraint_summary.summary_zh,
        boundary_notices=[
            INTERPRETATION_BOUNDARY_ZH,
            "单轮研究，不保存，不搜索，必须人工复核。",
        ],
        memo_type=ANSWER_MODE_TO_MEMO_TYPE.get(request.answer_mode),
        preview_type="deepseek_single_turn",
        validator_required=True,
    )

    try:
        external_response = adapter.generate_external_response(external_request)
    except BlockedAdapterError as exc:
        return _blocked_response(
            request=request,
            reason=f"adapter_blocked: {'; '.join(exc.findings)}",
            input_findings=[],
            selected_context=selected_context,
            budget=budget,
            manifest_data=manifest_data,
            prompt_text=prompt_text,
        )

    deepseek_text = external_response.content
    finish_reason = "stop"

    legacy_validator, semantic_result = validate_research_domains(
        system_boundary=SYSTEM_BOUNDARY_ZH,
        task_instruction=ANSWER_MODE_TASKS_ZH.get(
            request.answer_mode, ""
        ),
        selected_context=selected_context.selected_context_text,
        model_answer=deepseek_text,
        validator_explanation="DeepSeek 单轮研究输出，必须通过语义检查和人工复核。",
        sections=[],
        selected_cards=selected_context.selected_cards,
        prompt_ready=budget.ready,
    )

    ds_constraint_findings = validate_deepseek_output_constraints(deepseek_text)
    if ds_constraint_findings:
        all_findings = list(semantic_result.findings) + ds_constraint_findings
        max_sev = max(
            (f.severity for f in all_findings),
            key=lambda s: {"info": 0, "warning": 1, "error": 2, "blocker": 3}[s],
        )
        semantic_result = semantic_result.model_copy(
            update={
                "findings": all_findings,
                "max_severity": max_sev,
                "domain_checks": {
                    **semantic_result.domain_checks,
                    "deepseek_output_constraints": "claim_type_threshold_source_badge_checked",
                },
            }
        )

    elapsed = time.monotonic() - t0

    return AIDeepSeekResearchResponse(
        mode="deepseek_single_turn",
        answer_mode=request.answer_mode,
        detail_level=request.detail_level,
        user_question=request.user_question,
        deepseek_raw_output=deepseek_text,
        finish_reason=finish_reason,
        selected_prompt_context=selected_context,
        prompt_budget=budget,
        prompt_text=prompt_text,
        context_used_summary=_context_summary(manifest_data),
        privacy_summary=AIMemoPrivacySummary(
            uses_ai_context_manifest_only=True,
            uses_holdings_line_items=False,
            uses_raw_provider_payloads=False,
            uses_raw_prompts=False,
            external_model_called=True,
            search_called=False,
            saved_by_default=False,
        ),
        validator_result=legacy_validator,
        semantic_validator_result=semantic_result,
        input_validation_passed=True,
        input_validation_findings=[],
        output_blocked=semantic_result.blocked,
        human_review_required=True,
        interpretation_boundary=INTERPRETATION_BOUNDARY_ZH,
        elapsed_seconds=round(elapsed, 2),
    )


def _blocked_response(
    *,
    request: AIDeepSeekResearchRequest,
    reason: str,
    input_findings: list[str],
    selected_context: AISelectedPromptContext | None = None,
    budget: Any | None = None,
    manifest_data: dict[str, Any] | None = None,
    prompt_text: str = "",
) -> AIDeepSeekResearchResponse:
    """Build a blocked response without calling DeepSeek."""
    from app_backend.schemas.ai_preview import (
        AIConstraintSummary,
        AIPromptBudgetSummary,
        AIResearchValidationResult,
        AISemanticFinding,
    )

    if selected_context is None:
        empty_constraint = AIConstraintSummary(
            total_count=0,
            excluded_reason_distribution={},
            module_distribution={},
            freshness_distribution={},
            summary_zh="请求被输入验证拦截，未构建上下文。",
        )
        selected_context = AISelectedPromptContext(
            selected_cards=[],
            constraint_summary=empty_constraint,
            selected_context_text="",
            selection_notes=[f"请求被拦截: {reason}"],
        )
    if budget is None:
        budget = AIPromptBudgetSummary(
            card_limit=96, char_limit=32000, estimated_token_limit=12000,
            selected_card_count=0, selected_char_count=0,
            estimated_token_count=0, omitted_card_count=0,
            omitted_by_priority={}, omitted_by_reason={},
            ready=False, status_reason=reason,
        )

    finding = AISemanticFinding(
        code="request_blocked",
        category="input_boundary",
        severity="blocker",
        message_zh=f"请求被拦截: {reason}",
    )
    semantic_result = AIResearchValidationResult(
        passed=False, blocked=True, max_severity="blocker",
        findings=[finding], domain_checks={"input": "blocked"},
    )

    context_summary = (
        _context_summary(manifest_data) if manifest_data
        else AIMemoContextUsedSummary(
            included_fact_count=0, excluded_fact_count=0,
            included_model_output_count=0, excluded_model_output_count=0,
        )
    )

    return AIDeepSeekResearchResponse(
        mode="deepseek_single_turn",
        answer_mode=request.answer_mode,
        detail_level=request.detail_level,
        user_question=request.user_question,
        deepseek_raw_output="",
        finish_reason="blocked",
        selected_prompt_context=selected_context,
        prompt_budget=budget,
        prompt_text=prompt_text,
        context_used_summary=context_summary,
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
            passed=False, blocked_terms=[], privacy_findings=[],
        ),
        semantic_validator_result=semantic_result,
        input_validation_passed=len(input_findings) == 0,
        input_validation_findings=input_findings,
        output_blocked=True,
        human_review_required=True,
        interpretation_boundary=INTERPRETATION_BOUNDARY_ZH,
    )


__all__ = [
    "build_deepseek_prompt",
    "run_deepseek_research",
    "validate_user_question",
]
