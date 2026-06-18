"""Financial semantic validator for AI preview / memo output.

Goes beyond the term-blacklist validators in `ai_memo_renderer.py` and
`ai_preview_service.py`. Those check whether forbidden words or privacy
tokens appear in output. This module checks whether *financial reasoning
logic* is properly bounded:

- If output references systemic risk, it must also reference credit,
  funding/liquidity, and transmission evidence. Calling a state "systemic"
  on the basis of VIX alone is a known low-quality pattern.
- If output references a credit warning, it cannot rest only on a VIX or
  HYG/LQD proxy. HY/IG OAS or another official credit reference is
  required.
- If output references valuation pressure, it must acknowledge whether
  valuation / earnings / true breadth data is missing or proxy-only.
- If output references a scenario, it must include a "not a forecast"
  notice (no event odds, no return path, no action directive).
- If output references historical validation, it must include a "not a
  backtest / not prediction accuracy" notice.
- If output references portfolio context, it must include a local-only /
  sanitized / no-allocation-advice notice.
- If output references a financial stress score, it must clarify that the
  score is a pressure temperature, not a probability or forecast.

All rules are conservative and bilingual: each anchor and each required
phrase has both English and Chinese form so the validator works on the
current English memo templates and on future Chinese templates.

This validator does not call external models, does not consume holdings,
does not produce any allocation, probability, or forecast output, and does
not modify the input payload.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, Iterable


@dataclass(frozen=True)
class SemanticRule:
    """A single semantic rule.

    `anchors` is a list of trigger phrases. If any anchor appears in the
    payload text (case-insensitive), the rule is "active" and at least one
    item from each group in `required_groups` must also appear.
    `required_groups` is a list of lists: each inner list is an "any-of"
    group; the outer list is an "all-of" requirement.
    """

    name: str
    description_zh: str
    anchors: tuple[str, ...]
    required_groups: tuple[tuple[str, ...], ...]


@dataclass
class SemanticRuleFinding:
    rule: str
    description_zh: str
    matched_anchor: str
    missing_groups: list[list[str]] = field(default_factory=list)


@dataclass
class SemanticValidatorResult:
    passed: bool
    findings: list[SemanticRuleFinding] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "findings": [
                {
                    "rule": finding.rule,
                    "description_zh": finding.description_zh,
                    "matched_anchor": finding.matched_anchor,
                    "missing_groups": finding.missing_groups,
                }
                for finding in self.findings
            ],
        }


# ----------------------------------------------------------------------
# Rule catalog
# ----------------------------------------------------------------------

SEMANTIC_RULES: tuple[SemanticRule, ...] = (
    SemanticRule(
        name="systemic_risk_requires_credit_funding_transmission",
        description_zh=(
            "若提到系统性风险，必须同时引用信用、流动性/融资、以及传导证据；"
            "仅凭 VIX 或权益回撤不能被升级为系统性风险结论。"
        ),
        anchors=(
            "systemic risk",
            "systemic-risk",
            "systemic crisis",
            "系统性风险",
            "系统性危机",
        ),
        required_groups=(
            (
                "credit",
                "high yield",
                "hy oas",
                "ig oas",
                "信用",
                "高收益",
                "信用利差",
            ),
            (
                "funding",
                "liquidity",
                "sofr",
                "commercial paper",
                "rrp",
                "流动性",
                "融资",
                "短期融资",
            ),
            (
                "transmission",
                "channel",
                "传导",
                "通道",
            ),
        ),
    ),
    SemanticRule(
        name="credit_warning_cannot_rely_only_on_vix_or_etf_proxy",
        description_zh=(
            "若提到信用预警，必须引用 HY OAS / IG OAS / 信用利差等官方信用证据，"
            "不能仅凭 VIX 或 HYG/LQD/ETF 代理；HYG/LQD 是 ETF 价格代理，不等于 OAS。"
        ),
        anchors=(
            "credit warning",
            "credit alert",
            "credit stress alert",
            "信用预警",
            "信用警示",
        ),
        required_groups=(
            (
                "hy oas",
                "ig oas",
                "high yield spread",
                "investment grade spread",
                "信用利差",
                "high yield oas",
                "credit spread",
            ),
        ),
    ),
    SemanticRule(
        name="valuation_pressure_must_acknowledge_missing_or_proxy",
        description_zh=(
            "若提到估值压力，必须显式说明估值/盈利/真实广度数据是否缺失或仅为代理，"
            "不能在缺失数据下给出估值泡沫或广度恶化结论。"
        ),
        anchors=(
            "valuation pressure",
            "valuation bubble",
            "valuation risk",
            "估值压力",
            "估值泡沫",
            "估值风险",
        ),
        required_groups=(
            (
                "missing",
                "research_needed",
                "research needed",
                "proxy",
                "not_available",
                "not available",
                "limited_evidence",
                "limited evidence",
                "insufficient",
                "缺失",
                "代理",
                "不可用",
                "证据有限",
                "需要研究",
            ),
        ),
    ),
    SemanticRule(
        name="scenario_requires_not_a_forecast_notice",
        description_zh=(
            "若提到情景压力矩阵或情景传导，必须明确说明这是假设传导矩阵，"
            "不是预测、不是事件概率、不是收益估计、不是仓位指令。"
        ),
        anchors=(
            "scenario stress",
            "scenario matrix",
            "scenario transmission",
            "selected scenario",
            "scenario stress matrix",
            "情景压力",
            "情景矩阵",
            "情景传导",
        ),
        required_groups=(
            (
                "not a forecast",
                "not forecast",
                "not an event-odds",
                "not an event odds",
                "not event-odds",
                "no event odds",
                "no event-odds",
                "not action directive",
                "not an action directive",
                "not a return-estimation",
                "not return-estimation",
                "model-output scenario context",
                "model output scenario context",
                "不是预测",
                "不构成预测",
                "不构成事件概率",
                "不构成收益估计",
                "不构成仓位指令",
                "不是预报",
            ),
        ),
    ),
    SemanticRule(
        name="historical_validation_requires_not_a_backtest_notice",
        description_zh=(
            "若提到历史验证 / D19 / 历史事件复盘，必须说明这是事件窗口复盘，"
            "不是回测、不是预测准确率、不是策略收益。"
        ),
        anchors=(
            "historical validation",
            "historical replay",
            "event replay",
            "d19 historical",
            "historical event-window",
            "历史验证",
            "历史复盘",
            "事件复盘",
        ),
        required_groups=(
            (
                "not a backtest",
                "not backtest",
                "not prediction accuracy",
                "no prediction accuracy",
                "event-window replay",
                "event window replay",
                "reference-only",
                "reference only",
                "不是回测",
                "不构成回测",
                "事件窗口复盘",
                "仅供参考",
                "仅作参考",
            ),
        ),
    ),
    SemanticRule(
        name="portfolio_requires_local_sanitized_no_allocation",
        description_zh=(
            "若提到组合 / 持仓 / 暴露解释，必须说明上下文是本地 sanitized compact "
            "context，不读 holdings line items，不输出 allocation / rebalance / "
            "target weight 等仓位指令。"
        ),
        anchors=(
            "portfolio exposure",
            "portfolio overlay",
            "portfolio context",
            "portfolio deviation",
            "stage 8 overlay",
            "组合暴露",
            "组合解释",
            "持仓暴露",
        ),
        required_groups=(
            (
                "sanitized",
                "compact_summary_only",
                "compact summary only",
                "compact context",
                "local-only",
                "local only",
                "not an action directive",
                "not action directive",
                "no allocation",
                "no allocation directive",
                "sanitized compact",
                "本地",
                "本地化",
                "仅本地",
                "已 sanitize",
                "不构成仓位指令",
                "不构成配置建议",
                "不构成分配建议",
                "不构成调仓建议",
            ),
        ),
    ),
    SemanticRule(
        name="financial_stress_score_must_clarify_pressure_temperature",
        description_zh=(
            "若提到金融压力评分 / D10 financial stress score，必须明确说明这是"
            "压力温度 (pressure temperature)，不是概率 / 不是预测 / 不是事件概率。"
        ),
        anchors=(
            "financial stress score",
            "financial stress composite score",
            "stress composite score",
            "d10 score",
            "金融压力评分",
            "压力综合评分",
        ),
        required_groups=(
            (
                "pressure temperature",
                "not a probability",
                "not probability",
                "not prediction",
                "not a prediction",
                "not forecast",
                "not a forecast",
                "压力温度",
                "不是概率",
                "不是预测",
                "不构成概率",
                "不构成预测",
            ),
        ),
    ),
)


# ----------------------------------------------------------------------
# Public API
# ----------------------------------------------------------------------


def validate_financial_semantics(
    payload: Any,
    *,
    extra_text: str | None = None,
    rules: Iterable[SemanticRule] | None = None,
) -> SemanticValidatorResult:
    """Run financial semantic rules against an AI preview / memo payload.

    Accepts Pydantic models, dicts, or strings. Anything else is coerced to
    string. `extra_text` lets callers feed in additional context (e.g., the
    chat answer_preview) without mutating the payload.
    """

    text = _payload_to_text(payload)
    if extra_text:
        text = text + " " + extra_text
    text_lower = text.lower()

    active_rules = tuple(rules) if rules is not None else SEMANTIC_RULES
    findings: list[SemanticRuleFinding] = []
    for rule in active_rules:
        matched_anchor = _first_match(text_lower, rule.anchors)
        if matched_anchor is None:
            continue
        missing_groups: list[list[str]] = []
        for group in rule.required_groups:
            if not _any_match(text_lower, group):
                missing_groups.append(list(group))
        if missing_groups:
            findings.append(
                SemanticRuleFinding(
                    rule=rule.name,
                    description_zh=rule.description_zh,
                    matched_anchor=matched_anchor,
                    missing_groups=missing_groups,
                )
            )
    return SemanticValidatorResult(passed=not findings, findings=findings)


def explain_findings(result: SemanticValidatorResult, *, language: str = "zh") -> list[str]:
    """Render findings as human-readable lines (default Chinese)."""

    if result.passed:
        return []
    lines: list[str] = []
    for finding in result.findings:
        if language == "zh":
            missing_summary = "; ".join(
                "/".join(group) for group in finding.missing_groups
            ) or "—"
            lines.append(
                f"[{finding.rule}] 命中 '{finding.matched_anchor}' "
                f"但缺少所需上下文：{missing_summary}。{finding.description_zh}"
            )
        else:
            missing_summary = "; ".join(
                "/".join(group) for group in finding.missing_groups
            ) or "-"
            lines.append(
                f"[{finding.rule}] anchor '{finding.matched_anchor}' "
                f"matched but missing: {missing_summary}."
            )
    return lines


# ----------------------------------------------------------------------
# Internal helpers
# ----------------------------------------------------------------------


def _payload_to_text(payload: Any) -> str:
    if payload is None:
        return ""
    if isinstance(payload, str):
        return payload
    if hasattr(payload, "model_dump"):
        data: Any = payload.model_dump()
    elif hasattr(payload, "dict"):
        data = payload.dict()
    elif isinstance(payload, Mapping):
        data = dict(payload)
    else:
        return str(payload)
    return _walk(data)


def _walk(obj: Any) -> str:
    if obj is None:
        return ""
    if isinstance(obj, str):
        return obj
    if isinstance(obj, (int, float, bool)):
        return str(obj)
    if isinstance(obj, Mapping):
        return " ".join(_walk(value) for value in obj.values())
    if isinstance(obj, (list, tuple, set)):
        return " ".join(_walk(item) for item in obj)
    return str(obj)


def _first_match(text_lower: str, phrases: tuple[str, ...]) -> str | None:
    for phrase in phrases:
        needle = phrase.lower()
        if needle and needle in text_lower:
            return phrase
    return None


def _any_match(text_lower: str, phrases: tuple[str, ...]) -> bool:
    return _first_match(text_lower, phrases) is not None
