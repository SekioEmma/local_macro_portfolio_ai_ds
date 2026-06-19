"""Answer-mode registry for the local controlled research preview."""

from __future__ import annotations

from app_backend.schemas.ai_preview import AnswerMode


ANSWER_MODE_TO_MEMO_TYPE: dict[AnswerMode, str] = {
    "daily_brief": "daily_review_memo",
    "risk_review": "risk_review_memo",
    "scenario_review": "scenario_review_memo",
    "portfolio_overlay": "portfolio_overlay_review",
    "evidence_audit": "evidence_audit_report",
    "research_memo": "macro_risk_report",
}
MEMO_TYPE_TO_ANSWER_MODE = {
    memo_type: answer_mode
    for answer_mode, memo_type in ANSWER_MODE_TO_MEMO_TYPE.items()
}

ANSWER_MODE_TITLES_ZH: dict[AnswerMode, str] = {
    "daily_brief": "每日市场简报",
    "risk_review": "风险复核",
    "scenario_review": "情景压力解释",
    "portfolio_overlay": "组合暴露解释",
    "evidence_audit": "证据审计",
    "research_memo": "宏观投研报告",
}

ANSWER_MODE_TASKS_ZH: dict[AnswerMode, str] = {
    "daily_brief": "概括当前市场状态、主要压力来源、未确认风险、数据质量与观察指标。",
    "risk_review": "复核当前证据更接近普通回调、估值回撤、宏观压力、信用预警、系统性风险复核或证据不足。",
    "scenario_review": "解释情景压力的假设、传导通道、受影响证据组、不确定条件与缺失约束。",
    "portfolio_overlay": "仅基于本地清洗后的紧凑上下文解释组合暴露的宏观风险通道。",
    "evidence_audit": "审计哪些事实与模型输出可用，哪些因缺失、陈旧、代理或来源门禁而不能使用。",
    "research_memo": "形成较完整的中文宏观金融证据复核报告，区分事实、模型输出、约束与边界。",
}

P2_MODULES_BY_MODE: dict[AnswerMode, set[str]] = {
    "daily_brief": {
        "inflation_energy_pressure",
        "growth_inflation_macro_pack",
        "equity_trend",
        "market_stress_derived",
        "historical_risk_percentile",
    },
    "risk_review": {
        "equity_trend",
        "market_stress_derived",
        "historical_risk_percentile",
    },
    "scenario_review": {
        "inflation_energy_pressure",
        "growth_inflation_macro_pack",
        "equity_trend",
        "market_stress_derived",
    },
    "portfolio_overlay": {
        "equity_trend",
        "market_stress_derived",
        "historical_risk_percentile",
    },
    "evidence_audit": {
        "inflation_energy_pressure",
        "growth_inflation_macro_pack",
        "equity_trend",
        "market_stress_derived",
        "historical_risk_percentile",
    },
    "research_memo": {
        "inflation_energy_pressure",
        "growth_inflation_macro_pack",
        "equity_trend",
        "market_stress_derived",
        "historical_risk_percentile",
    },
}

P3_MODULES_BY_MODE: dict[AnswerMode, set[str]] = {
    "daily_brief": {
        "breadth_concentration_proxy",
        "data_quality_diagnostics",
    },
    "risk_review": {
        "breadth_concentration_proxy",
        "scenario_stress",
        "historical_validation",
        "data_quality_diagnostics",
    },
    "scenario_review": {
        "scenario_stress",
        "historical_validation",
        "data_quality_diagnostics",
    },
    "portfolio_overlay": {
        "portfolio_exposure_overlay",
        "portfolio_deviation",
        "data_quality_diagnostics",
    },
    "evidence_audit": {
        "breadth_concentration_proxy",
        "valuation_equity_structure",
        "historical_validation",
        "data_quality_diagnostics",
    },
    "research_memo": {
        "breadth_concentration_proxy",
        "valuation_equity_structure",
        "scenario_stress",
        "historical_validation",
        "portfolio_exposure_overlay",
        "portfolio_deviation",
        "data_quality_diagnostics",
    },
}


def answer_mode_for_memo_type(memo_type: str) -> AnswerMode:
    return MEMO_TYPE_TO_ANSWER_MODE.get(memo_type, "risk_review")  # type: ignore[return-value]


__all__ = [
    "ANSWER_MODE_TASKS_ZH",
    "ANSWER_MODE_TITLES_ZH",
    "ANSWER_MODE_TO_MEMO_TYPE",
    "MEMO_TYPE_TO_ANSWER_MODE",
    "P2_MODULES_BY_MODE",
    "P3_MODULES_BY_MODE",
    "answer_mode_for_memo_type",
]
