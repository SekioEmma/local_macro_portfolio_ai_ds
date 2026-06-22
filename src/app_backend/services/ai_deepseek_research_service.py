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
from typing import Any, Literal

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
    AIDeepSeekClaimMetadata,
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
from app_backend.services.ai_external_runtime_policy import (
    guard_external_ai_runtime_policy,
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
from app_backend.services.deepseek_transport_contract import (
    DeepSeekTransportError,
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

_GUIDANCE_INPUTS = frozenset(
    {
        "你好",
        "您好",
        "哈喽",
        "嗨",
        "在吗",
        "早上好",
        "下午好",
        "晚上好",
        "谢谢",
        "多谢",
        "再见",
        "你是谁",
        "你能做什么",
        "介绍一下你自己",
        "hello",
        "hi",
        "hey",
        "thanks",
        "thankyou",
        "goodmorning",
        "goodafternoon",
        "goodevening",
        "whatareyou",
        "whatcanyoudo",
        "help",
    }
)

_DETAIL_CONTEXT_LIMITS: dict[DetailLevel, dict[str, int]] = {
    "brief": {
        "card_limit": 64,
        "char_limit": 20_000,
        "estimated_token_limit": 7_000,
    },
    "standard": {
        "card_limit": 72,
        "char_limit": 24_000,
        "estimated_token_limit": 8_000,
    },
    "deep": {
        "card_limit": 96,
        "char_limit": 32_000,
        "estimated_token_limit": 12_000,
    },
}

_DETAIL_OUTPUT_TOKEN_LIMITS: dict[DetailLevel, int] = {
    "brief": 1_200,
    "standard": 2_400,
    "deep": 4_000,
}

_USER_FOCUS_INSTRUCTION = """[最高优先级：回答用户问题]
1. 用户问题是唯一主任务；证据上下文只是回答材料，不是要求你逐项复述的提纲。
2. 先判断问题是否属于宏观、市场风险、证据审计、情景或组合风险研究。
3. 若问题只是问候、致谢、身份询问或能力询问，只用 1-2 句自然回应，并邀请用户提出具体宏观研究问题；不要输出七段研究模板，不要复述市场证据。
4. 若问题属于研究范围，只使用与问题直接相关的证据。没有相关证据时明确说“当前本地证据不足”，不要用无关指标拼成长篇市场综述。
5. 回答必须在开头直接回应问题，不能先输出通用宏观背景。"""

_SECTION_FORMAT_INSTRUCTION = """仅当用户提出有效的宏观研究问题时，按以下 7 段结构回答，每段以标题行开头。

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

_EXPRESSION_RULES = """[金融表达约束（必须遵守）]
1. direct_evidence 段只能陈述字段事实和数值，不得包含"反映""意味着""通常对应""可能由……驱动"等解释性语言。解释性内容必须移入 interpretive 段。
2. interpretive 段可以解释传导机制，但必须避免把外部市场叙事写成项目已验证事实。
3. 曲线斜率为正只能说明"不支持当前倒挂强化叙事"，不能单独排除衰退或增长放缓风险。须补充"仍需结合就业、信用、盈利与融资压力共同判断"。
4. historical freshness 不等于 stale。标注为 historical 的证据应解释为"历史分位/历史统计上下文"，而不是简单说"新鲜度不足"。
5. 所有 pp 距离保留两位小数。不得把 0.03pp 四舍五入写成 0.0pp。
6. "软着陆""金发姑娘""AI 生产率叙事"等宏观标签，除非选中证据卡片中有对应字段，否则只能作为待验证解释框架，并明确标注"当前 Manifest 未提供对应证据"。
7. "可能触发""将导致""未来会"等预测倾向表述统一改为"作为观察条件""需要后续证据确认""构成风险传导路径的条件之一"。
8. ON RRP / 隔夜逆回购单独变化不能推断准备金稀缺，必须同时引用 SOFR-EFFR 利差、EFFR-IORB 利差或银行准备金证据。"""


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


def classify_user_question(
    question: str,
) -> Literal["research", "guidance"]:
    """Route trivial conversation away from the expensive research pipeline."""
    normalized = re.sub(
        r"[\s，。！？!?、,.；;：:~～'\"“”‘’\-—_]+",
        "",
        question,
    ).casefold()
    if normalized in _GUIDANCE_INPUTS:
        return "guidance"
    return "research"


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
        _USER_FOCUS_INSTRUCTION,
        f"[用户问题]\n{user_question}",
        f"[任务: {title_zh}]\n{task_zh}",
        f"[详细程度]\n{detail_instruction}",
        f"[输出合同]\n{output_contract}",
        f"[预检清单]\n{preflight}",
        f"[选中的证据上下文]\n{selected_context.selected_context_text}",
        f"[上下文选择说明]\n" + "\n".join(selected_context.selection_notes),
        f"[约束摘要]\n{selected_context.constraint_summary.summary_zh}",
        f"[来源与新鲜度摘要]\n{source_quality}",
        _SECTION_FORMAT_INSTRUCTION,
        _EXPRESSION_RULES,
        (
            "[回答前再次核对]\n"
            f"请只回答这个问题：{user_question}\n"
            "若上下文与问题无关，明确说明证据不足，不要改答成通用市场综述。"
        ),
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


_CLAIM_TYPE_RE = re.compile(
    r"\[claim_type\s*=\s*"
    r"(direct_evidence|cross_evidence_inference|interpretive|watchlist)\s*\]"
)
_THRESHOLD_SOURCE_RE = re.compile(
    r"\[threshold_source\s*=\s*"
    r"(project_band|historical_percentile|heuristic_watchlist)\s*\]"
)


def _postprocess_deepseek_output(
    raw_output: str,
) -> tuple[str, AIDeepSeekClaimMetadata]:
    """Strip claim_type/threshold_source tags from display output; extract metadata."""
    from collections import Counter

    claim_counts: Counter[str] = Counter()
    threshold_counts: Counter[str] = Counter()

    for match in _CLAIM_TYPE_RE.finditer(raw_output):
        claim_counts[match.group(1)] += 1
    for match in _THRESHOLD_SOURCE_RE.finditer(raw_output):
        threshold_counts[match.group(1)] += 1

    memo_output = _CLAIM_TYPE_RE.sub("", raw_output)
    memo_output = _THRESHOLD_SOURCE_RE.sub("", memo_output)
    memo_output = re.sub(r"\n\s*\n\s*\n+", "\n\n", memo_output)
    memo_output = re.sub(r"^[ \t]+", "", memo_output, flags=re.MULTILINE)

    metadata = AIDeepSeekClaimMetadata(
        claim_type_counts=dict(claim_counts),
        threshold_source_counts=dict(threshold_counts),
        total_claims=sum(claim_counts.values()),
    )
    return memo_output.strip(), metadata


def _external_ai_capability() -> tuple[bool, str]:
    """Resolve whether the external DeepSeek path is operationally enabled.

    The user-controlled switch for AI-2 is the presence of the provider API
    key in the environment: absent key -> capability unavailable, and the
    runtime policy gates fail closed instead of raising. The key value is
    never logged, embedded in schemas, or returned to the client.
    """
    try:
        return True, load_deepseek_api_key_from_env()
    except DeepSeekTransportError:
        return False, ""


def _build_runtime_policy(
    *,
    external_ai_enabled: bool,
    context_preview_ready: bool,
) -> ExternalAIRuntimePolicy:
    """Build the AI-2 single-turn runtime policy from real preconditions.

    The operational/consent gates reflect actual runtime state so the 22-flag
    guard genuinely fails closed when external AI is not enabled (no provider
    key / switch off) or when the manifest context is not ready. They are not
    hardcoded constants. The structural commitments (validator + human review
    required) and the dangerous-permission denials are fixed by the AI-2
    single-turn contract: no persistence, no search, no holdings/account/
    position/transaction data, and no background/app-start/page-load call.
    """
    return ExternalAIRuntimePolicy(
        provider="deepseek",
        # Operational gates — derived from the user-controlled switch (key).
        external_ai_enabled=external_ai_enabled,
        provider_network_enabled=external_ai_enabled,
        user_controlled_switch_enabled=external_ai_enabled,
        # Single-turn, synchronous, user-initiated POST; background / app-start
        # / page-load calls are separately denied below.
        single_request_user_approved=True,
        # Context provenance — derived from the manifest budget readiness.
        context_preview_confirmed=context_preview_ready,
        request_built_from_manifest=context_preview_ready,
        request_guard_passed=True,
        # Structural commitments honored by this code path.
        response_guard_required=True,
        stage9_validator_required=True,
        human_review_required=True,
        # Dangerous permissions — denied by the AI-2 single-turn contract.
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

    if classify_user_question(request.user_question) == "guidance":
        return _guidance_response(request=request, started_at=t0)

    manifest = ai_context_service.build_ai_context_manifest()
    manifest_data = _manifest_to_dict(manifest)
    context_limits = _DETAIL_CONTEXT_LIMITS[request.detail_level]

    selected_context, budget = select_prompt_context(
        manifest_data,
        answer_mode=request.answer_mode,
        **context_limits,
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

    external_ai_available, api_key = _external_ai_capability()
    policy = _build_runtime_policy(
        external_ai_enabled=external_ai_available,
        context_preview_ready=budget.ready,
    )
    policy_guard = guard_external_ai_runtime_policy(policy)
    if not policy_guard.passed:
        return _blocked_response(
            request=request,
            reason=f"runtime_policy_blocked: {'; '.join(policy_guard.findings)}",
            input_findings=[],
            selected_context=selected_context,
            budget=budget,
            manifest_data=manifest_data,
            prompt_text=prompt_text,
        )

    transport = DeepSeekRealTransport(
        api_key=api_key,
        timeout_seconds=150.0,
        max_tokens=_DETAIL_OUTPUT_TOKEN_LIMITS[request.detail_level],
    )
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
    finish_reason = external_response.finish_reason

    memo_output, claim_metadata = _postprocess_deepseek_output(deepseek_text)

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
        response_kind="research",
        answer_mode=request.answer_mode,
        detail_level=request.detail_level,
        user_question=request.user_question,
        deepseek_raw_output=deepseek_text,
        deepseek_memo_output=memo_output,
        claim_metadata=claim_metadata,
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


def _guidance_response(
    *,
    request: AIDeepSeekResearchRequest,
    started_at: float,
) -> AIDeepSeekResearchResponse:
    """Return a small local response for greetings without calling DeepSeek."""
    from app_backend.schemas.ai_preview import (
        AIConstraintSummary,
        AIPromptBudgetSummary,
        AIResearchValidationResult,
    )

    selected_context = AISelectedPromptContext(
        selected_cards=[],
        constraint_summary=AIConstraintSummary(
            total_count=0,
            excluded_reason_distribution={},
            module_distribution={},
            freshness_distribution={},
            summary_zh="这是简短会话引导，未读取或发送研究上下文。",
        ),
        selected_context_text="",
        selection_notes=["本地意图路由识别为问候或能力询问。"],
    )
    budget = AIPromptBudgetSummary(
        card_limit=0,
        char_limit=0,
        estimated_token_limit=0,
        selected_card_count=0,
        selected_char_count=0,
        estimated_token_count=0,
        omitted_card_count=0,
        omitted_by_priority={},
        omitted_by_reason={},
        ready=True,
        status_reason="local_guidance_no_prompt_required",
    )
    semantic_result = AIResearchValidationResult(
        passed=True,
        blocked=False,
        max_severity=None,
        findings=[],
        domain_checks={"intent": "local_guidance"},
    )
    memo = (
        "你好！这里是 AI 宏观研究入口。请给我一个具体的宏观或市场风险问题，"
        "例如“当前高实际利率对信用风险意味着什么？”或"
        "“哪些本地证据支持通胀压力正在缓和？”"
    )
    return AIDeepSeekResearchResponse(
        mode="deepseek_single_turn",
        response_kind="guidance",
        answer_mode=request.answer_mode,
        detail_level=request.detail_level,
        user_question=request.user_question,
        deepseek_raw_output="",
        deepseek_memo_output=memo,
        finish_reason="local_guidance",
        selected_prompt_context=selected_context,
        prompt_budget=budget,
        prompt_text="",
        context_used_summary=AIMemoContextUsedSummary(
            included_fact_count=0,
            excluded_fact_count=0,
            included_model_output_count=0,
            excluded_model_output_count=0,
        ),
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
        semantic_validator_result=semantic_result,
        input_validation_passed=True,
        input_validation_findings=[],
        output_blocked=False,
        human_review_required=True,
        interpretation_boundary=INTERPRETATION_BOUNDARY_ZH,
        elapsed_seconds=round(time.monotonic() - started_at, 4),
        model_provider="local_intent_router",
        not_saved_by_default=True,
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
    "classify_user_question",
    "run_deepseek_research",
    "validate_user_question",
]
