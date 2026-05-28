from __future__ import annotations

import re
from typing import Any


EXTERNAL_SOURCES = [
    "Reuters",
    "FactSet",
    "Bloomberg",
    "FRED",
    "FedWatch",
    "Goldman",
    "Wind",
]
DGS_CONTEXT_LABEL_PATTERN = (
    r"(?:DGS10|DGS30|10\s*年期|30\s*年期|10\s*年美债|30\s*年美债|"
    r"10\s*年期?国债|30\s*年期?国债|十年期|三十年期|10Y|30Y|"
    r"Treasury\s*yield|美债收益率|美国国债收益率|长端利率|长端收益率)"
)
DGS_CONTEXT_VALUE_PATTERN = (
    r"(?:\d+(?:\.\d+)?\s*[%％]|above[^\n。；]{0,12}5(?!\d)\s*[%％]?|below[^\n。；]{0,12}5(?!\d)\s*[%％]?|"
    r"站上[^\n。；]{0,12}5(?!\d)\s*[%％]?|高于[^\n。；]{0,12}5(?!\d)\s*[%％]?|低于[^\n。；]{0,12}5(?!\d)\s*[%％]?|"
    r"距离[^\n。；]{0,12}5(?!\d)\s*[%％]?|盘中|intraday)"
)
PAUSE_DCA_PATTERN = r"(?:暂停|停止|中断)(?:长期)?定投"
TRADE_LIKE_PATTERNS = [
    r"应(?:该)?买入",
    r"应(?:该)?卖出",
    r"建议买入",
    r"建议卖出",
    r"需(?:要)?增加持仓",
    r"需(?:要)?减持",
    r"清仓",
    r"越跌越买",
    r"等跌再买",
    r"补仓",
    r"立即调整",
    r"加速买入",
    r"加仓(?:标普|纳指|纳斯达克|短债|债券|黄金|sp500|nasdaq|gold|bond)",
    r"增配(?:标普|纳指|纳斯达克|短债|债券|黄金|sp500|nasdaq|gold|bond)",
    r"减配(?:标普|纳指|纳斯达克|短债|债券|黄金|sp500|nasdaq|gold|bond)",
    r"调整为\s*\d+\s*/\s*\d+",
]
TRADE_NEGATION_MARKERS = [
    "不建议",
    "不能",
    "不应",
    "不构成",
    "不是",
    "无法",
    "不要",
    "并非",
    "不把",
    "不宜",
    "不属于",
    "不能据此",
    "无法得出",
]
THINKING_PATTERNS = [r"<think>", r"</think>", r"Thinking", r"思考过程"]
BROADER_BOUNDARY_MARKERS = [
    "未提供",
    "没有提供",
    "没有直接提供",
    "本地 context 未提供",
    "本地上下文未提供",
    "本地数据未提供",
    "本地数据没有提供",
    "本地数据不足",
    "缺少",
    "缺失",
    "没有",
    "无法",
    "无法获取",
    "无法引用",
    "无法确认",
    "不能确认",
    "不能判断",
    "没有数据支持",
    "无数据",
    "无相关数据",
    "缺少时间戳",
    "not_available",
    "not available",
    "not intraday",
    "research_needed",
    "not_available",
    "尚未配置",
    "不能将",
    "尚未达到确认条件",
    "未达到确认条件",
    "未满足确认条件",
    "未同步确认",
    "未确认突破",
    "无法验证",
    "无法得到确认",
    "未能成功获取",
    "未经核实",
    "不能验证",
    "不能确认",
    "而非",
    "不可用",
    "无法得知",
    "不能补",
    "不能编造",
    "不编造",
    "无法基于具体数值",
    "未被提供",
    "不可用",
    "未提供",
    "不包含",
]


def validate_comparison_answer(answer_text: str, validator_facts: dict[str, Any] | None = None) -> dict[str, Any]:
    facts = validator_facts if isinstance(validator_facts, dict) else {}
    external = _external_source_mentions(answer_text, facts)
    hard_flags = {
        "thinking_leak": _has_any_regex(answer_text, THINKING_PATTERNS),
        "external_source_mentioned": external["unsupported_mentions"],
        "unsupported_market_data_claim": _unsupported_market_data_claims(answer_text, facts),
        "trade_like_instruction": _trade_like_instruction(answer_text),
        "cash_reserve_misuse": _cash_reserve_misuse(answer_text),
        "current_holdings_realtime_misstatement": _current_holdings_realtime_misstatement(answer_text),
        "portfolio_direction_conflict": _portfolio_direction_conflicts(answer_text, facts),
        "missing_data_boundary_absent": _missing_data_boundary_absent(answer_text, facts),
        "dgs_breakout_confirmation_conflict": _dgs_breakout_confirmation_conflicts(answer_text, facts),
        "unsupported_inflation_trend_or_surprise": _unsupported_inflation_trend_or_surprise(answer_text, facts),
        "stale_data_used_as_current": _stale_data_used_as_current(answer_text, facts),
    }
    soft_flags = {
        "too_template_like": _too_template_like(answer_text),
        "evidence_table_absent": _evidence_table_absent(answer_text),
        "body_metric_not_in_evidence_table": _body_metric_not_in_evidence_table(answer_text, facts),
        "hypothesis_written_as_confirmed_fact": _hypothesis_written_as_confirmed_fact(answer_text),
        "deterministic_short_bond_loss": _deterministic_short_bond_loss(answer_text),
        "real_yield_gold_logic_too_linear": _real_yield_gold_logic_too_linear(answer_text),
        "unsupported_real_yield_primary_driver_claim": _unsupported_real_yield_primary_driver_claim(answer_text),
        "unsupported_market_psychology_inference": _unsupported_market_psychology_inference(answer_text),
        "dgs_5pct_wording_without_confirmation": _dgs_5pct_wording_without_confirmation(answer_text, facts),
        "current_vs_target_allocation_confusion": _current_vs_target_allocation_confusion(answer_text, facts),
    }
    return {
        "hard_flags": hard_flags,
        "soft_flags": soft_flags,
        "boundary_statements": {
            "external_source_boundary": external["boundary_mentions"],
        },
        "has_hard_flag": any(bool(value) for value in hard_flags.values()),
        "has_soft_flag": any(bool(value) for value in soft_flags.values()),
    }


def _external_source_mentions(text: str, facts: dict[str, Any]) -> dict[str, list[str]]:
    unsupported = []
    boundary = []
    allowed_sources = {
        str(source).lower()
        for source in facts.get("allowed_external_sources", [])
        if str(source).strip()
    }
    for source in EXTERNAL_SOURCES:
        for sentence in _sentences(text):
            if not re.search(re.escape(source), sentence, re.IGNORECASE):
                continue
            if source == "FRED" and re.search(
                r"DGS2|DGS10|DGS30|DGS|CPI|PCE|PPI|WTI|Brent|daily|intraday|日度|盘中",
                sentence,
                re.IGNORECASE,
            ):
                continue
            if source.lower() in allowed_sources:
                continue
            if _has_boundary_marker(sentence):
                boundary.append(source)
            elif re.search(r"报道|数据显示|根据|引用|指出|称|预测|认为|数据", sentence):
                unsupported.append(source)
            else:
                unsupported.append(source)
    return {
        "unsupported_mentions": sorted(set(unsupported)),
        "boundary_mentions": sorted(set(boundary)),
    }


def _unsupported_market_data_claims(text: str, facts: dict[str, Any]) -> list[str]:
    patterns = [
        r"(?:PE|市盈率|估值倍数)[^\n。；]{0,24}\d+(?:\.\d+)?",
        r"(?:FedWatch|概率)[^\n。；]{0,24}\d+(?:\.\d+)?%",
        r"(?:10年期|十年期|美债|收益率)[^\n。；]{0,32}\d+(?:\.\d+)?%",
        r"(?:黄金价格|金价)[^\n。；]{0,32}\d+(?:\.\d+)?",
    ]
    hits = []
    for pattern in patterns:
        hits.extend(match.group(0) for match in re.finditer(pattern, text, re.IGNORECASE))
    hits.extend(
        match.group(0)
        for match in re.finditer(
            r"(?:DGS2|DGS10|DGS30|CPIAUCSL|CPILFESL|PCEPI|PCEPILFE|PPIACO|DCOILWTICO|DCOILBRENTEU|WTI|Brent)[^\n。；]{0,32}\d+(?:\.\d+)?%?",
            text,
            re.IGNORECASE,
        )
    )
    hits.extend(
        match.group(0)
        for match in re.finditer(
            r"(?:10\s*年期|30\s*年期|10Y|30Y)[^\n。；]{0,60}(?:收益率|名义国债收益率|日度收益率|站上|高于|距离|为|在|已经)[^\n。；]{0,36}\d+(?:\.\d+)?\s*(?:%|个百分点)?",
            text,
            re.IGNORECASE,
        )
    )
    filtered = []
    for sentence in _sentences(text):
        if _is_evidence_table_row_with_provided_metric_key(sentence, facts):
            continue
        if _is_intraday_boundary_statement(sentence):
            continue
        if _is_dgs_threshold_topic_only(sentence):
            continue
        if not _requires_context_backed_dgs_check(sentence):
            continue
        if _has_boundary_marker(sentence):
            continue
        if not _context_backed_dgs_claim(sentence, facts):
            filtered.append(sentence[:120])

    for hit in hits:
        sentence = _sentence_containing(text, hit)
        window = _surrounding_text(text, hit, 100)
        if sentence and _is_evidence_table_row_with_provided_metric_key(sentence, facts):
            continue
        if sentence and _is_intraday_boundary_statement(sentence):
            continue
        if _is_intraday_boundary_statement(window):
            continue
        if _raw_provided_metric_key_fragment(hit, facts):
            continue
        if _is_dgs_threshold_topic_only(sentence or window):
            continue
        if _claim_has_boundary_context(text, hit):
            continue
        if _has_boundary_marker(window):
            continue
        if _is_observation_date_reference(window):
            continue
        if _context_backed_dgs_claim(sentence or window, facts):
            continue
        if sentence and _provided_market_data_claim(sentence, facts):
            continue
        if _provided_market_data_claim(window, facts):
            continue
        filtered.append(hit)
    filtered.extend(_unsupported_unprovided_phrase_claims(text, facts))
    return sorted(set(filtered))


def _raw_provided_metric_key_fragment(hit: str, facts: dict[str, Any]) -> bool:
    normalized_hit = re.sub(r"\s+", "", hit).lower()
    if not re.fullmatch(r"[a-z0-9_]+", normalized_hit):
        return False
    values = facts.get("provided_market_data_values")
    if not isinstance(values, dict):
        return False
    return any(str(key).lower().startswith(normalized_hit) for key in values)


def _is_evidence_table_row_with_provided_metric_key(text: str, facts: dict[str, Any]) -> bool:
    return (
        _provided_metric_key_in_markdown_table_row(text, facts) is not None
        and not _evidence_table_row_has_blocked_claim(text)
    )


def _provided_metric_key_in_markdown_table_row(text: str, facts: dict[str, Any]) -> str | None:
    cells = _markdown_table_cells(text)
    if not cells:
        return None
    values = facts.get("provided_market_data_values")
    if not isinstance(values, dict):
        return None
    provided_keys = {str(key).strip().lower(): str(key) for key in values.keys() if str(key).strip()}
    for cell in cells:
        normalized_cell = cell.strip().strip("`").strip().lower()
        if normalized_cell in provided_keys:
            return provided_keys[normalized_cell]
    return None


def _markdown_table_cells(text: str) -> list[str]:
    stripped = text.strip()
    if not stripped.startswith("|") or stripped.count("|") < 3:
        return []
    return [cell.strip() for cell in stripped.strip("|").split("|")]


def _evidence_table_row_has_blocked_claim(text: str) -> bool:
    if re.search(r"(?:FedWatch|降息概率|加息概率)[^\n|]{0,40}\d+(?:\.\d+)?\s*%", text, re.IGNORECASE):
        return True
    if re.search(
        r"(?:forward\s*PE|PE|CAPE|市盈率|估值倍数|valuation percentile|估值百分位)[^\n|]{0,40}\d",
        text,
        re.IGNORECASE,
    ):
        return True
    if re.search(r"(?:Reuters|FactSet|Bloomberg|Goldman|Wind)", text, re.IGNORECASE):
        return True
    if _inflation_surprise_claim_without_boundary(text):
        return True
    if re.search(r"(?:final demand PPI|PPI final demand|最终需求\s*PPI)", text, re.IGNORECASE) and not re.search(
        r"(?:非|不是|不等于|并非|not)[^\n|]{0,16}(?:final demand PPI|PPI final demand|最终需求\s*PPI)",
        text,
        re.IGNORECASE,
    ):
        return True
    if re.search(
        r"(?:market breadth|市场广度|mega[- ]cap concentration|巨头集中度|equal[- ]weight|cap[- ]weight|等权|市值加权)",
        text,
        re.IGNORECASE,
    ):
        return True
    return _intraday_high_numeric_claim(text)


def _claim_has_boundary_context(text: str, hit: str) -> bool:
    for sentence in _sentences(text):
        if hit not in sentence:
            continue
        if _has_boundary_marker(sentence):
            return True
        if re.search(r"(?:如果|假如|若|假设|if)", sentence, re.IGNORECASE):
            return True
        if re.search(r"(?:如果|假如|若|假设|if)[^\n。；]{0,40}" + re.escape(hit), sentence, re.IGNORECASE):
            return True
        if re.search(re.escape(hit) + r"[^\n。；]{0,40}(?:不能确认|无法确认|无法验证|未经核实|not confirmed)", sentence, re.IGNORECASE):
            return True
    return False


def _is_intraday_boundary_statement(text: str) -> bool:
    if not text:
        return False
    if re.search(r"(?:Reuters|FactSet|Bloomberg|FedWatch|Goldman|Wind)", text, re.IGNORECASE):
        return False
    if not re.search(r"(?:盘中|intraday)", text, re.IGNORECASE):
        return False
    if not re.search(r"(?:DGS10|DGS30|FRED|Treasury|美债|国债|constant maturity|日度|daily)", text, re.IGNORECASE):
        return False
    if re.search(r"\d+(?:\.\d+)?\s*(?:%|％|bp|bps|基点|点)", text):
        return False
    boundary_pattern = (
        r"(?:不是|非|不能替代|不等于|不代表|无法|不能|未提供|不可用|not|cannot|can't)"
        r"[^\n。；]{0,12}(?:盘中高点|intraday high|intraday highs)"
    )
    if re.search(boundary_pattern, text, re.IGNORECASE):
        return True
    if re.search(r"(?:intraday high not available|no intraday high|not intraday high)", text, re.IGNORECASE):
        return True
    return False


def _intraday_high_numeric_claim(text: str) -> bool:
    return bool(
        re.search(
            r"(?:盘中|intraday)[^\n。；|]{0,30}(?:最高|高点|high|为|达到|站上)?"
            r"[^\n。；|]{0,20}\d+(?:\.\d+)?\s*(?:%|％|bp|bps|基点)",
            text,
            re.IGNORECASE,
        )
    )


def _is_dgs_threshold_topic_only(text: str) -> bool:
    if not re.search(DGS_CONTEXT_LABEL_PATTERN, text, re.IGNORECASE):
        return False
    if not re.search(r"5\s*[%％]?\s*(?:关口|阈值|附近|压力)", text, re.IGNORECASE):
        return False
    if re.search(
        r"(?:站稳|确认突破|持续处于|高压区已经确认|高于|超过|突破|站上|处于|位于|above|confirmed)",
        text,
        re.IGNORECASE,
    ):
        return False
    return True


def _provided_market_data_claim(text: str, facts: dict[str, Any]) -> bool:
    terms = facts.get("provided_market_data_terms")
    if not isinstance(terms, list):
        return False
    if _provided_real_yield_claim(text, facts):
        return True
    if _looks_like_real_yield_claim(text):
        return False
    if _requires_context_backed_dgs_check(text):
        return _context_backed_dgs_claim(text, facts)
    if _provided_rates_inflation_oil_claim(text, terms):
        return True
    if any(
        str(term).strip() and re.search(re.escape(str(term)), text, re.IGNORECASE)
        for term in terms
    ):
        return True

    normalized_text = re.sub(r"\s+", "", text)
    normalized_terms = {re.sub(r"\s+", "", str(term)).lower() for term in terms}
    has_yield_curve_context = bool(
        normalized_terms.intersection({"yield_curve_10y2y", "10y-2y", "10年-2年", "收益率曲线"})
    )
    if has_yield_curve_context and re.search(
        r"(?:10年(?:与|和|-)?2年|10年期(?:与|和|-)?2年期|10Y(?:-|–)?2Y|收益率曲线|(?:美债|国债)利差)",
        normalized_text,
        re.IGNORECASE,
    ):
        return True
    return False


def _provided_real_yield_claim(text: str, facts: dict[str, Any]) -> bool:
    if not _looks_like_real_yield_claim(text):
        return False
    if re.search(r"(?:Reuters|FactSet|Bloomberg|FedWatch|Goldman|Wind)", text, re.IGNORECASE):
        return False
    values = facts.get("provided_market_data_values")
    if not isinstance(values, dict):
        return False
    item = values.get("real_yield_10y")
    return isinstance(item, dict) and item.get("status") == "ok" and item.get("value") is not None


def _looks_like_real_yield_claim(text: str) -> bool:
    return bool(
        re.search(
            r"(?:real[_\s-]*yield(?:_10y)?|real_yield_10y|实际利率|实际收益率|10年期实际利率)",
            text,
            re.IGNORECASE,
        )
    )


def _is_observation_date_reference(text: str) -> bool:
    if not re.search(r"观测值|观察日期|observation_date|取自|截至", text, re.IGNORECASE):
        return False
    return bool(re.search(r"20\d{2}[-‑–/年]\d{1,2}", text))


def _provided_rates_inflation_oil_claim(text: str, terms: list[Any]) -> bool:
    normalized_text = re.sub(r"\s+", "", text)
    normalized_terms = {re.sub(r"\s+", "", str(term)).lower() for term in terms}
    if _requires_context_backed_dgs_check(text) or _looks_like_dgs_value_claim(text):
        return False
    if normalized_terms.intersection(
        {
            "dgs2",
            "dgs10",
            "dgs30",
            "nominal_yield_2y",
            "nominal_yield_10y",
            "nominal_yield_30y",
            "nominalyield",
            "10-yeartreasuryyield",
            "30-yeartreasuryyield",
        }
    ) and re.search(r"(?:DGS2|DGS10|DGS30|Treasuryyield|nominalyield)", normalized_text, re.IGNORECASE):
        return True
    if normalized_terms.intersection({"cpi", "corecpi", "pce", "corepce", "ppiaco", "ppi"}) and re.search(
        r"(?:CPI|PCE|PPI|PPIACO)",
        normalized_text,
        re.IGNORECASE,
    ):
        return True
    if normalized_terms.intersection({"wti", "brent", "oil", "dcoilwtico", "dcoilbrenteu"}) and re.search(
        r"(?:WTI|Brent|oil)",
        normalized_text,
        re.IGNORECASE,
    ):
        return True
    return False


def _looks_like_dgs_value_claim(text: str) -> bool:
    if _looks_like_real_yield_claim(text):
        return False
    if re.search(r"(?:10Y\s*-\s*2Y|10Y-2Y|10年\s*-\s*2年|收益率曲线|利差)", text, re.IGNORECASE):
        return False
    return _requires_context_backed_dgs_check(text)


def _requires_context_backed_dgs_check(text: str) -> bool:
    if _looks_like_real_yield_claim(text):
        return False
    if re.search(r"(?:breakeven|盈亏平衡|通胀预期|T10YIE)", text, re.IGNORECASE):
        return False
    if re.search(r"(?:10Y\s*-\s*2Y|10Y-2Y|10年\s*-\s*2年|收益率曲线|利差)", text, re.IGNORECASE):
        return False
    if re.search(
        r"dgs(?:10|30)_(?:above_5pct_days_\d+d|\d+d_avg|5pct_breakout_confirmed|distance_to_5pct|above_5pct)",
        text,
        re.IGNORECASE,
    ):
        return False
    if not re.search(DGS_CONTEXT_LABEL_PATTERN, text, re.IGNORECASE):
        return False
    return bool(re.search(DGS_CONTEXT_VALUE_PATTERN, text, re.IGNORECASE))


def _context_backed_dgs_claim(text: str, facts: dict[str, Any]) -> bool:
    if not _looks_like_dgs_value_claim(text):
        return False
    if re.search(r"(?:盘中|intraday)[^\n。；]{0,30}\d+(?:\.\d+)?\s*%", text, re.IGNORECASE):
        return False

    values = facts.get("provided_market_data_values")
    if not isinstance(values, dict):
        return False

    checks = []
    if re.search(r"(?:DGS10|10\s*年期|10\s*年美债|10\s*年期?国债|10Y)", text, re.IGNORECASE):
        checks.append(("nominal_yield_10y", "dgs10_distance_to_5pct"))
    if re.search(r"(?:DGS30|30\s*年期|30\s*年美债|30\s*年期?国债|30Y)", text, re.IGNORECASE):
        checks.append(("nominal_yield_30y", "dgs30_distance_to_5pct"))
    if not checks:
        return False
    relevant_checks = []
    for value_key, distance_key in checks:
        segment = _dgs_relevant_text(text, value_key)
        if _has_boundary_marker(segment):
            continue
        if not re.search(DGS_CONTEXT_VALUE_PATTERN, segment, re.IGNORECASE):
            continue
        relevant_checks.append((segment, value_key, distance_key))
    if not relevant_checks:
        return True
    return all(
        _dgs_text_matches_context(segment, values, value_key, distance_key)
        for segment, value_key, distance_key in relevant_checks
    )


def _dgs_breakout_statement(text: str) -> bool:
    return bool(
        re.search(
            r"(?:5\s*[%％]?[^\n。；]{0,16}(?:突破确认|阈值确认|确认条件|已确认)|"
            r"(?:确认|已确认|持续位于|持续处于)[^\n。；]{0,24}5\s*[%％]?\s*(?:以上|上方)?)",
            text,
            re.IGNORECASE,
        )
    )


def _dgs_negative_breakout_statement(text: str) -> bool:
    return bool(
        re.search(r"(?:(?:突破确认|确认值)[^\n。；]{0,12}(?:False|false|否|未|不成立)|未确认突破)", text, re.IGNORECASE)
    )


def _dgs_relevant_text(text: str, value_key: str) -> str:
    if value_key == "nominal_yield_10y":
        match = re.search(r"(?:DGS10|10\s*年期|10\s*年美债|10\s*年期?国债|10Y)[^\n。；]{0,160}", text, re.IGNORECASE)
        if not match:
            return text
        segment = match.group(0)
        return re.split(r"(?:而|；|;)?\s*(?:DGS30|30\s*年期|30Y)", segment, maxsplit=1, flags=re.IGNORECASE)[0]
    if value_key == "nominal_yield_30y":
        match = re.search(r"(?:DGS30|30\s*年期|30\s*年美债|30\s*年期?国债|30Y)[^\n。；]{0,160}", text, re.IGNORECASE)
        if match:
            segment = match.group(0)
            return re.split(
                r"(?:但|而|相比之下|相较之下)[^\n。；]{0,12}(?:DGS10|10\s*年期|10\s*年美债|10\s*年期?国债|10Y)",
                segment,
                maxsplit=1,
                flags=re.IGNORECASE,
            )[0]
    return text


def _dgs_text_matches_context(
    text: str,
    values: dict[str, Any],
    value_key: str,
    distance_key: str,
) -> bool:
    item = values.get(value_key)
    if not isinstance(item, dict):
        return False
    value = _float_or_none(item.get("value"))
    if value is None:
        return False

    numbers = _numbers_in_text(text)
    if not numbers:
        return False

    negative_breakout_claim = bool(
        re.search(r"(?:突破确认|确认值)[^\n。；]{0,12}(?:False|false|否|未|不成立)", text, re.IGNORECASE)
    )
    if negative_breakout_claim:
        target = "dgs10" if value_key == "nominal_yield_10y" else "dgs30"
        return not _dgs_breakout_confirmed_from_values(target, values)
    if _dgs_breakout_statement(text):
        target = "dgs10" if value_key == "nominal_yield_10y" else "dgs30"
        return _dgs_breakout_confirmed_from_values(target, values)

    above_5_claim = bool(
        re.search(
            r"(?:(?:站上|超过|高于|突破|处于|位于|不低于|above)[^\n。；]{0,12}5(?!\d)\s*[%％]?|"
            r"5(?!\d)\s*[%％]?[^\n。；]{0,12}(?:以上|上方|突破|确认))",
            text,
            re.IGNORECASE,
        )
    )
    if above_5_claim:
        return value >= 4.995
    below_5_claim = bool(re.search(r"(?:未触及|未站上|没有站上|低于|below)[^\n。；]{0,12}5(?!\d)\s*[%％]?", text, re.IGNORECASE))
    if below_5_claim:
        return value < 5.005

    for number in numbers:
        if _close_enough(number, value, tolerance=0.015):
            return True

    distance_item = values.get(distance_key)
    distance = _float_or_none(distance_item.get("value")) if isinstance(distance_item, dict) else None
    if distance is not None and re.search(r"(?:距离|高于|低于|above|below)[^\n。；]{0,24}5\s*%", text, re.IGNORECASE):
        return any(_close_enough(number, abs(distance), tolerance=0.025) for number in numbers)
    if distance is not None and re.search(r"(?:距|距离|高于|低于)[^\n。；]{0,24}5\s*%?[^\n。；]{0,24}基点", text, re.IGNORECASE):
        return any(_close_enough(number, abs(distance) * 100, tolerance=1.5) for number in numbers)
    return False


def _dgs_breakout_confirmed_from_values(target: str, values: dict[str, Any]) -> bool:
    item = values.get(f"{target}_5pct_breakout_confirmed")
    return isinstance(item, dict) and item.get("value") is True and item.get("status") == "ok"


def _unsupported_unprovided_phrase_claims(text: str, facts: dict[str, Any]) -> list[str]:
    unsupported = []
    values = facts.get("provided_market_data_values")
    if not isinstance(values, dict):
        values = {}
    for sentence in _sentences(text):
        if _is_evidence_table_row_with_provided_metric_key(sentence, facts):
            continue
        if _has_boundary_marker(sentence):
            continue
        if re.search(r"(?:CPI|PPI)[^\n。；]{0,20}(?:超预期|surprise|consensus|expected)", sentence, re.IGNORECASE):
            unsupported.append(sentence[:120])
            continue
        if re.search(r"(?:final demand PPI|PPI final demand|最终需求PPI|最终需求 PPI)", sentence, re.IGNORECASE):
            if re.search(r"(?:非|不是|不等于|并非|not)[^\n。；]{0,16}(?:final demand PPI|PPI final demand|最终需求PPI|最终需求 PPI)", sentence, re.IGNORECASE):
                continue
            item = values.get("ppi_final_demand")
            if not isinstance(item, dict) or item.get("status") != "ok" or item.get("value") is None:
                unsupported.append(sentence[:120])
            continue
        if _intraday_high_numeric_claim(sentence):
            unsupported.append(sentence[:120])
    return unsupported


def _dgs_breakout_confirmation_conflicts(text: str, facts: dict[str, Any]) -> list[str]:
    conflicts = []
    conflict_pattern = (
        r"(?:确认突破|confirmed\s+breakout|高压区已经确认|5\s*[%％]?\s*阈值已满足确认条件|"
        r"按本项目定义[^\n。；]{0,24}确认|breakout_confirmed[^\n。；]{0,12}true)"
    )
    for sentence in _sentences(text):
        if _dgs_false_breakout_boundary(sentence, facts):
            continue
        if _has_boundary_marker(sentence) or _is_dgs_threshold_topic_only(sentence):
            continue
        if not re.search(conflict_pattern, sentence, re.IGNORECASE):
            continue
        if _dgs_negative_breakout_statement(sentence):
            continue
        if not re.search(DGS_CONTEXT_LABEL_PATTERN, sentence, re.IGNORECASE):
            continue
        targets = _dgs_targets(sentence) or ["dgs10", "dgs30"]
        if any(not _dgs_breakout_confirmed(target, facts) for target in targets):
            conflicts.append(sentence[:120])
    return sorted(set(conflicts))


def _dgs_5pct_wording_without_confirmation(text: str, facts: dict[str, Any]) -> list[str]:
    flagged = []
    strong_pattern = (
        r"(?:站稳|确认突破|confirmed\s+breakout|持续处于|事实上的利率压力信号|高压区已经确认|"
        r"长端利率持续处于\s*5\s*[%％]?\s*以上)"
    )
    for sentence in _sentences(text):
        if _dgs_false_breakout_boundary(sentence, facts):
            continue
        if _has_boundary_marker(sentence) or _is_dgs_threshold_topic_only(sentence):
            continue
        if not re.search(DGS_CONTEXT_LABEL_PATTERN, sentence, re.IGNORECASE):
            continue
        if not re.search(r"5\s*[%％]?", sentence):
            continue
        if _dgs_negative_breakout_statement(sentence):
            continue
        if not re.search(strong_pattern, sentence, re.IGNORECASE):
            continue
        targets = _dgs_targets(sentence)
        if not targets:
            targets = ["dgs10", "dgs30"]
        if any(not _dgs_breakout_confirmed(target, facts) for target in targets):
            flagged.append(sentence[:120])
    return sorted(set(flagged))


def _dgs_targets(text: str) -> list[str]:
    targets = []
    if re.search(r"(?:DGS10|10\s*年期|10\s*年美债|10\s*年期?国债|10Y|十年期)", text, re.IGNORECASE):
        targets.append("dgs10")
    if re.search(r"(?:DGS30|30\s*年期|30\s*年美债|30\s*年期?国债|30Y|三十年期|长端利率)", text, re.IGNORECASE):
        targets.append("dgs30")
    return targets


def _dgs_breakout_confirmed(target: str, facts: dict[str, Any]) -> bool:
    values = facts.get("provided_market_data_values")
    if not isinstance(values, dict):
        return False
    item = values.get(f"{target}_5pct_breakout_confirmed")
    return isinstance(item, dict) and item.get("value") is True and item.get("status") == "ok"


def _dgs_false_breakout_boundary(text: str, facts: dict[str, Any]) -> bool:
    match = re.search(r"(dgs(?:10|30)_5pct_breakout_confirmed)", text, re.IGNORECASE)
    if not match:
        return False
    key = match.group(1).lower()
    values = facts.get("provided_market_data_values")
    if not isinstance(values, dict):
        return False
    item = values.get(key)
    if not isinstance(item, dict) or item.get("value") is not False:
        return False
    if not re.search(
        r"(?:false|False|否|未达确认条件|未达到确认条件|未满足确认条件|尚未达到确认条件|not confirmed|未确认突破)",
        text,
        re.IGNORECASE,
    ):
        return False
    if re.search(
        r"(?:但|但是|却|however|but)[^\n。；|]{0,40}"
        r"(?:确认突破|已确认突破|站稳|持续站上|高压区已经确认|已满足确认条件|满足确认条件|"
        r"breakout_confirmed[^\n。；|]{0,12}true)",
        text,
        re.IGNORECASE,
    ):
        return False
    positive_text = re.sub(
        r"(?:未确认突破|未达确认条件|未达到确认条件|未满足确认条件|尚未达到确认条件)",
        "",
        text,
        flags=re.IGNORECASE,
    )
    if re.search(
        r"(?:确认突破|已确认突破|站稳|持续站上|高压区已经确认|已满足确认条件|满足确认条件|"
        r"breakout_confirmed[^\n。；|]{0,12}true)",
        positive_text,
        re.IGNORECASE,
    ):
        return False
    return True


def _unsupported_inflation_trend_or_surprise(text: str, facts: dict[str, Any]) -> list[str]:
    unsupported = []
    trend_pattern = r"(?:温和偏高|明显降温|没有明显降温|没有降温|未明显降温|未降温|降温|偏高)"
    surprise_pattern = (
        r"(?:超预期|低于预期|高于预期|beat expectations|miss expectations|"
        r"surprise|consensus|expected|expectations)"
    )
    for sentence in _sentences(text):
        if _is_evidence_table_row_with_provided_metric_key(sentence, facts):
            continue
        if _inflation_boundary_sentence(sentence):
            continue
        if re.search(r"(?:如果|假如|若|假设|if)", sentence, re.IGNORECASE) and not re.search(
            r"(?:当前|目前|数据显示|本地数据|数据包)", sentence, re.IGNORECASE
        ):
            continue
        if not re.search(r"(?:CPI|PCE|PPI|PPIACO)", sentence, re.IGNORECASE):
            continue
        if re.search(surprise_pattern, sentence, re.IGNORECASE) and not _inflation_consensus_available(sentence, facts):
            unsupported.append(sentence[:120])
            continue
        if re.search(trend_pattern, sentence, re.IGNORECASE) and not _inflation_sentence_has_derived_support(sentence):
            unsupported.append(sentence[:120])
    return sorted(set(unsupported))


def _inflation_boundary_sentence(sentence: str) -> bool:
    if _inflation_surprise_denial(sentence):
        return True
    return bool(
        re.search(
            r"(?:不能|不得|不要|不可|不应|无法|不能确认|缺少|缺失|未提供|没有提供|not provided|not available)"
            r"[^\n。；]{0,40}(?:CPI|PCE|PPI|超预期|低于预期|高于预期|降温|偏高|surprise|consensus)",
            sentence,
            re.IGNORECASE,
        )
    )


def _inflation_surprise_claim_without_boundary(text: str) -> bool:
    if not re.search(r"(?:CPI|PCE|PPI|PPIACO)", text, re.IGNORECASE):
        return False
    if not re.search(
        r"(?:超预期|低于预期|高于预期|beat expectations|miss expectations|surprise|consensus|expected)",
        text,
        re.IGNORECASE,
    ):
        return False
    return not _inflation_surprise_denial(text)


def _inflation_surprise_denial(text: str) -> bool:
    return bool(
        re.search(
            r"(?:非超预期|不能写超预期|不代表超预期|不代表低于预期|不能判断超预期或低于预期|"
            r"不能判断[^\n。；|]{0,20}(?:超预期|低于预期|高于预期)|"
            r"not a consensus[- ]surprise|no consensus|not a surprise|"
            r"cannot determine[^\n。；|]{0,20}(?:surprise|expected|expectations))",
            text,
            re.IGNORECASE,
        )
    )


def _inflation_consensus_available(sentence: str, facts: dict[str, Any]) -> bool:
    values = facts.get("provided_market_data_values")
    if not isinstance(values, dict):
        return False
    if re.search(r"CPI", sentence, re.IGNORECASE):
        item = values.get("consensus_cpi")
        return isinstance(item, dict) and item.get("status") == "ok" and item.get("value") is not None
    if re.search(r"PPI", sentence, re.IGNORECASE):
        item = values.get("consensus_ppi")
        return isinstance(item, dict) and item.get("status") == "ok" and item.get("value") is not None
    return False


def _inflation_sentence_has_derived_support(sentence: str) -> bool:
    return bool(
        re.search(
            r"(?:同比|环比|YoY|MoM|year-over-year|month-over-month|"
            r"(?:headline|core)?_?(?:cpi|pce|ppi)[^\n。；]{0,24}(?:mom|yoy)_pct)",
            sentence,
            re.IGNORECASE,
        )
    )


def _unsupported_real_yield_primary_driver_claim(text: str) -> bool:
    for sentence in _sentences(text):
        if _has_boundary_marker(sentence):
            continue
        if re.search(
            r"(?:(?:主要由|主要力量|主因|主要驱动)[^\n。；]{0,24}(?:实际利率|实际收益率|real\s*yield)|"
            r"(?:实际利率|实际收益率|real\s*yield)[^\n。；]{0,24}(?:主要力量|主因|主要驱动))",
            sentence,
            re.IGNORECASE,
        ):
            return True
    return False


def _unsupported_market_psychology_inference(text: str) -> list[str]:
    flagged = []
    pattern = (
        r"(?:债券市场相信|市场相信|市场认为[^\n。；]{0,30}暂时性冲击|"
        r"市场已经定价为|已经定价为[^\n。；]{0,24}暂时|market\s+believes|market\s+has\s+priced)"
    )
    for sentence in _sentences(text):
        if _has_boundary_marker(sentence):
            continue
        if re.search(pattern, sentence, re.IGNORECASE):
            flagged.append(sentence[:120])
    return sorted(set(flagged))


def _body_metric_not_in_evidence_table(text: str, facts: dict[str, Any]) -> list[str]:
    evidence_table, body = _split_evidence_table(text)
    if not evidence_table:
        return []

    table_numbers = _numbers_in_text(_strip_dates(evidence_table))
    flagged = []
    for sentence in _sentences(body):
        if sentence.lstrip().startswith("#"):
            continue
        if re.match(r"^\**\s*\d+\s*[.、]", sentence):
            continue
        if _is_dgs_threshold_topic_only(sentence):
            continue
        clean_sentence = _strip_dates(sentence)
        sentence_numbers = _market_metric_numbers(clean_sentence)
        if not sentence_numbers:
            continue
        for metric_name, labels in _market_metric_label_groups():
            if not _contains_any_label(clean_sentence, labels):
                continue
            if not _contains_any_label(evidence_table, labels):
                flagged.append(f"{metric_name}: {sentence[:120]}")
                break
            numbers_to_check = [
                number
                for number in sentence_numbers
                if not _is_threshold_reference_number(number, clean_sentence)
            ]
            if numbers_to_check and not all(
                any(_close_enough(number, table_number, tolerance=_metric_number_tolerance(number)) for table_number in table_numbers)
                for number in numbers_to_check
            ):
                flagged.append(f"{metric_name}: {sentence[:120]}")
                break
    return sorted(set(flagged))


def _split_evidence_table(text: str) -> tuple[str, str]:
    lines = text.splitlines()
    header_index = None
    marker_index = None
    for index, line in enumerate(lines):
        if marker_index is None and re.search(r"数据证据表|证据表", line):
            marker_index = index
        if re.search(r"\|", line) and re.search(r"指标", line) and re.search(r"数值", line):
            header_index = index
            break
    if header_index is None:
        return "", text

    start = marker_index if marker_index is not None and 0 <= header_index - marker_index <= 3 else header_index
    end = header_index
    while end < len(lines) and (lines[end].strip().startswith("|") or end == start):
        end += 1
    table_text = "\n".join(lines[start:end])
    body_text = "\n".join([*lines[:start], *lines[end:]])
    return table_text, body_text


def _market_metric_label_groups() -> list[tuple[str, list[str]]]:
    return [
        ("DGS10", ["DGS10", "10年期", "10年美债", "10年国债", "10Y", "十年期", "nominal_yield_10y", "dgs10_"]),
        ("DGS30", ["DGS30", "30年期", "30年美债", "30年国债", "30Y", "三十年期", "nominal_yield_30y", "dgs30_"]),
        ("DGS2", ["DGS2", "2年期", "2Y", "nominal_yield_2y"]),
        ("real_yield_10y", ["real_yield_10y", "DFII10", "实际利率", "实际收益率", "real yield"]),
        ("breakeven_inflation_10y", ["breakeven", "T10YIE", "盈亏平衡通胀", "通胀预期"]),
        ("VIX", ["VIX", "vix", "波动率"]),
        ("high_yield_spread", ["high_yield_spread", "high yield spread", "信用利差", "高收益利差"]),
        ("WTI", ["WTI", "DCOILWTICO", "wti_oil", "wti_oil_30d_change", "油价", "原油"]),
        ("Brent", ["Brent", "DCOILBRENTEU", "brent_oil", "brent_oil_30d_change"]),
        ("CPI", ["CPI", "CPIAUCSL", "headline_cpi", "core_cpi", "CPILFESL"]),
        ("PCE", ["PCE", "PCEPI", "headline_pce", "core_pce", "PCEPILFE"]),
        ("PPI", ["PPI", "PPIACO", "ppi_all_commodities"]),
    ]


def _contains_any_label(text: str, labels: list[str]) -> bool:
    return any(label and re.search(re.escape(label), text, re.IGNORECASE) for label in labels)


def _strip_dates(text: str) -> str:
    text = re.sub(r"20\d{2}[-/年]\d{1,2}(?:[-/月]\d{1,2}日?)?", "", text)
    text = re.sub(r"20\d{2}\s*年", "", text)
    text = re.sub(r"\d{1,2}\s*月(?:份|以后|以来|之前|初|中旬|下旬|上旬)?", "", text)
    return text


def _market_metric_numbers(text: str) -> list[float]:
    return _numbers_in_text(text)


def _is_threshold_reference_number(number: float, text: str) -> bool:
    return _close_enough(number, 5.0, tolerance=0.0001) and bool(
        re.search(r"5\s*[%％]?\s*(?:关口|阈值|附近|以上|上方)", text)
    )


def _metric_number_tolerance(number: float) -> float:
    return 0.015 if abs(number) < 20 else 0.05


def _float_or_none(value: Any) -> float | None:
    try:
        if isinstance(value, bool) or value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _numbers_in_text(text: str) -> list[float]:
    numbers = []
    for match in re.finditer(r"\d+(?:\.\d+)?", text):
        value = _float_or_none(match.group(0))
        if value is not None:
            numbers.append(value)
    return numbers


def _close_enough(left: float, right: float, *, tolerance: float) -> bool:
    return abs(left - right) <= tolerance


def _trade_like_instruction(text: str) -> bool:
    for sentence in _sentences(text):
        if re.search(PAUSE_DCA_PATTERN, sentence):
            if _is_negated_trade_sentence(sentence):
                continue
            if _is_pause_dca_directive(sentence):
                return True
            continue
        if not _has_any_regex(sentence, TRADE_LIKE_PATTERNS):
            continue
        if _is_negated_trade_sentence(sentence):
            continue
        return True
    return False


def _cash_reserve_misuse(text: str) -> bool:
    for sentence in _sentences(text):
        if not re.search(r"cash reserve|现金准备金|余额宝", sentence, re.IGNORECASE):
            continue
        if not re.search(r"待配置资产|闲置资金|应投入|应立即投入|加仓资金|补仓", sentence):
            continue
        if re.search(r"不(?:是|等于|参与|应|可|该)|不是|不等于|不参与|非待配置|not", sentence, re.IGNORECASE):
            continue
        return True
    return False


def _current_holdings_realtime_misstatement(text: str) -> bool:
    for sentence in _sentences(text):
        if not re.search(r"current_holdings|持仓", sentence, re.IGNORECASE):
            continue
        if not re.search(r"实时|同步|real-time", sentence, re.IGNORECASE):
            continue
        if re.search(
            r"不是实时|非实时|不保证实时|不等于实时|不能反映[^\n。；]{0,12}实时|无法反映[^\n。；]{0,12}实时|not real-time|not realtime",
            sentence,
            re.IGNORECASE,
        ):
            continue
        return True
    return False


def _portfolio_direction_conflicts(text: str, facts: dict[str, Any]) -> list[dict[str, str]]:
    direction = facts.get("allocation_direction")
    if not isinstance(direction, dict):
        return []
    names = {
        "sp500": ["sp500", "标普", "标普500", "S&P 500"],
        "nasdaq100": ["nasdaq100", "纳指", "纳斯达克", "Nasdaq 100"],
        "short_bond": ["short_bond", "短债", "短期债", "short bond"],
        "gold": ["gold", "黄金"],
    }
    high_terms = r"高配|超配|overweight|高于目标|相对目标偏高|偏高"
    low_terms = r"低配|underweight|低于目标|相对目标偏低|偏低"
    conflicts = []
    for asset, expected in direction.items():
        expected_text = str(expected)
        labels = names.get(asset, [asset])
        asset_clauses = [
            clause
            for clause in _clauses(text)
            if any(re.search(re.escape(label), clause, re.IGNORECASE) for label in labels)
        ]
        for clause in asset_clauses:
            specific = _asset_specific_direction(clause, labels, high_terms, low_terms)
            has_high = specific == "overweight" or (
                specific is None and bool(re.search(high_terms, clause, re.IGNORECASE))
            )
            has_low = specific == "underweight" or (
                specific is None and bool(re.search(low_terms, clause, re.IGNORECASE))
            )
            if has_high and has_low:
                continue
            if expected_text == "underweight" and has_high:
                conflicts.append({"asset": asset, "expected": expected_text, "observed": clause[:120]})
                break
            if expected_text == "overweight" and has_low:
                conflicts.append({"asset": asset, "expected": expected_text, "observed": clause[:120]})
                break
    return conflicts


def _asset_specific_direction(
    clause: str,
    labels: list[str],
    high_terms: str,
    low_terms: str,
) -> str | None:
    for label in labels:
        escaped_label = re.escape(label)
        if re.search(
            rf"{escaped_label}[^\n。；;，,、]{{0,8}}(?:{high_terms})",
            clause,
            re.IGNORECASE,
        ):
            return "overweight"
        if re.search(
            rf"{escaped_label}[^\n。；;，,、]{{0,8}}(?:{low_terms})",
            clause,
            re.IGNORECASE,
        ):
            return "underweight"
        if re.search(
            rf"(?:{high_terms})[^\n。；;，,、]{{0,8}}{escaped_label}",
            clause,
            re.IGNORECASE,
        ):
            return "overweight"
        if re.search(
            rf"(?:{low_terms})[^\n。；;，,、]{{0,8}}{escaped_label}",
            clause,
            re.IGNORECASE,
        ):
            return "underweight"
    return None


def _missing_data_boundary_absent(text: str, facts: dict[str, Any]) -> bool:
    terms = facts.get("missing_data_terms")
    if not isinstance(terms, list):
        terms = ["PE", "forward PE", "CAPE", "估值", "FedWatch", "信用利差", "VIX", "Reuters", "FactSet", "Bloomberg"]
    relevant_sentences = []
    for sentence in _sentences(text):
        if _is_evidence_table_row_with_provided_metric_key(sentence, facts):
            continue
        matched_terms = _matched_missing_terms(sentence, terms)
        if not matched_terms:
            continue
        if _only_broad_analytical_terms(matched_terms):
            if not _broad_terms_used_as_unsupported_data(sentence):
                continue
            if _provided_market_data_claim(sentence, facts):
                continue
        relevant_sentences.append(sentence)
    if not relevant_sentences:
        return False
    if any(_has_boundary_marker(sentence) for sentence in relevant_sentences):
        return False
    combined = "。".join(relevant_sentences)
    if _has_boundary_marker(combined):
        return False
    factual_assertion_patterns = [
        r"\d+(?:\.\d+)?%?",
        r"处于(?:历史)?(?:高位|低位)",
        r"显示",
        r"表明",
        r"根据",
        r"报道",
        r"数据显示",
    ]
    for sentence in relevant_sentences:
        if _has_any_regex(sentence, factual_assertion_patterns):
            return True
    return False


def _matched_missing_terms(sentence: str, terms: list[Any]) -> list[str]:
    return [
        str(term)
        for term in terms
        if str(term) and _missing_term_matches(sentence, str(term))
    ]


def _missing_term_matches(sentence: str, term: str) -> bool:
    if re.fullmatch(r"[A-Za-z]{1,4}", term):
        return bool(re.search(rf"(?<![A-Za-z]){re.escape(term)}(?![A-Za-z])", sentence, re.IGNORECASE))
    if re.fullmatch(r"[A-Za-z][A-Za-z\s/-]{1,32}", term):
        return bool(
            re.search(
                rf"(?<![A-Za-z]){re.escape(term)}(?![A-Za-z])",
                sentence,
                re.IGNORECASE,
            )
        )
    return bool(re.search(re.escape(term), sentence, re.IGNORECASE))


def _only_broad_analytical_terms(terms: list[str]) -> bool:
    broad_terms = {"估值", "收益率点位", "黄金价格"}
    return bool(terms) and all(term in broad_terms for term in terms)


def _broad_terms_used_as_unsupported_data(sentence: str) -> bool:
    return bool(
        re.search(
            r"估值[^\n。；]{0,16}(?:历史)?(?:高位|低位|分位|百分位|倍数|水平)",
            sentence,
            re.IGNORECASE,
        )
        or re.search(
            r"估值[^\n。；]{0,8}(?:为|是|达到)\s*\d",
            sentence,
            re.IGNORECASE,
        )
        or re.search(
            r"(?:收益率点位|黄金价格)[^\n。；]{0,16}(?:为|是|报|处于|达到)\s*\d",
            sentence,
            re.IGNORECASE,
        )
    )


def _too_template_like(text: str) -> bool:
    headings = len(re.findall(r"(?m)^#{1,4}\s+", text))
    bullets = len(re.findall(r"(?m)^\s*[-*]\s+", text))
    return headings >= 8 or bullets >= 20


def _evidence_table_absent(text: str) -> bool:
    if re.search(r"数据证据表|证据表|指标\s*\|\s*数值|指标\s+数值", text):
        return False
    if re.search(r"metric_key", text, re.IGNORECASE) and re.search(r"observation_date", text, re.IGNORECASE):
        return False
    return not (
        re.search(r"observation_date|source|freshness|status", text, re.IGNORECASE)
        and re.search(r"DGS10|DGS30|CPI|PCE|PPI|WTI|Brent|VIX|high_yield", text, re.IGNORECASE)
    )


def _hypothesis_written_as_confirmed_fact(text: str) -> bool:
    for sentence in _sentences(text):
        if _has_boundary_marker(sentence):
            continue
        if re.search(r"(?:当前|现在|本地数据|数据包)[^\n。；]{0,24}(?:CPI|PPI)[^\n。；]{0,24}(?:没有明显降温|未明显降温|没有降温|未降温)", sentence, re.IGNORECASE):
            return True
    return False


def _deterministic_short_bond_loss(text: str) -> bool:
    for sentence in _sentences(text):
        if not re.search(r"(?:短债|short_bond|short bond)", sentence, re.IGNORECASE):
            continue
        if re.search(r"(?:并非|并不|不是|不等于|不能|不应|非)[^\n。；]{0,12}(?:确定回撤|必然回撤|稳赚|无风险|免疫利率风险)", sentence, re.IGNORECASE):
            continue
        if re.search(
            r"(?:短债|short_bond|short bond)[^\n。；]{0,30}(?:确定回撤|必然回撤|稳赚|无风险|免疫利率风险)",
            sentence,
            re.IGNORECASE,
        ):
            return True
    return False


def _real_yield_gold_logic_too_linear(text: str) -> bool:
    linear_patterns = [
        r"油价上涨[^\n。；]{0,20}(?:直接|必然)[^\n。；]{0,20}实际利率",
        r"通胀预期上升[^\n。；]{0,20}必然[^\n。；]{0,20}黄金(?:上涨|下跌|承压|受益)",
        r"盈亏平衡通胀率上升[^\n。；]{0,12}(?:等于|就是|意味着)[^\n。；]{0,12}实际利率上升",
    ]
    return _has_any_regex(text, linear_patterns)


def _current_vs_target_allocation_confusion(text: str, facts: dict[str, Any]) -> bool:
    direction = facts.get("allocation_direction")
    if not isinstance(direction, dict):
        return False
    equity_underweight = direction.get("sp500") == "underweight" and direction.get("nasdaq100") == "underweight"
    if not equity_underweight:
        return False
    for sentence in _sentences(text):
        if _has_boundary_marker(sentence):
            continue
        if not re.search(r"(?:当前|本地快照|持仓快照|现在)", sentence, re.IGNORECASE):
            continue
        if re.search(r"(?:权益|标普|纳指|sp500|nasdaq)[^\n。；]{0,8}(?:低配|underweight)", sentence, re.IGNORECASE):
            continue
        equity_high = re.search(
            r"(?:(?:当前|本地快照|持仓快照|现在)[^\n。；]{0,8}(?:权益|标普|纳指|sp500|nasdaq)[^\n。；]{0,8}(?:高配|超配|overweight)|(?:当前|本地快照|持仓快照|现在)[^\n。；]{0,8}(?:高配|超配|overweight)[^\n。；]{0,8}(?:权益|标普|纳指|sp500|nasdaq))",
            sentence,
            re.IGNORECASE,
        )
        if equity_high:
            return True
    return False


def _stale_data_used_as_current(text: str, facts: dict[str, Any]) -> bool:
    values = facts.get("provided_market_data_values")
    if not isinstance(values, dict):
        return False
    risky_current_pattern = r"(?:当前|正在|目前|实时|当前最新|形成共振|飙升中|短期飙升|仍在|today|right now|current|currently)"
    stale_safe_pattern = (
        r"(?:截至|观察日|observation_date|stale|需要(?:后续)?更新验证|近期代理|历史代理|"
        r"曾显示|如果后续更新|若后续更新|缺少[^\n。；]{0,24}实时油价|缺乏[^\n。；]{0,24}实时油价|"
        r"不能[^\n。；]{0,24}实时|截至[^\n。；]{0,24}的数据)"
    )
    stale_items = [
        (str(key), item)
        for key, item in values.items()
        if isinstance(item, dict) and item.get("freshness") == "stale"
    ]
    if not stale_items:
        return False
    for sentence in _sentences(text):
        if re.search(stale_safe_pattern, sentence, re.IGNORECASE):
            continue
        if not re.search(risky_current_pattern, sentence, re.IGNORECASE):
            continue
        for key, _item in stale_items:
            labels = _labels_for_market_key(key)
            if _contains_any_label(sentence, labels) and _current_term_near_labels(
                sentence,
                labels,
                risky_current_pattern,
            ):
                return True
    return False


def _current_term_near_labels(
    sentence: str,
    labels: list[str],
    current_pattern: str,
    *,
    radius: int = 20,
) -> bool:
    label_spans = []
    for label in labels:
        if not label:
            continue
        label_spans.extend(match.span() for match in re.finditer(re.escape(label), sentence, re.IGNORECASE))
    if not label_spans:
        return False
    for match in re.finditer(current_pattern, sentence, re.IGNORECASE):
        current_start, current_end = match.span()
        for label_start, label_end in label_spans:
            if current_start <= label_end + radius and current_end >= label_start - radius:
                return True
    return False


def _labels_for_market_key(key: str) -> list[str]:
    labels = [key]
    if key.startswith("wti") or key.startswith("brent"):
        labels.extend(["WTI", "Brent", "oil", "原油", "油价"])
    if key.startswith("dgs10") or key == "nominal_yield_10y":
        labels.extend(["DGS10", "10年期", "10Y", "十年期", "美债收益率"])
    if key.startswith("dgs30") or key == "nominal_yield_30y":
        labels.extend(["DGS30", "30年期", "30Y", "三十年期", "长端利率"])
    if "cpi" in key:
        labels.extend(["CPI", "通胀"])
    if "pce" in key:
        labels.extend(["PCE", "通胀"])
    if "ppi" in key:
        labels.extend(["PPI", "PPIACO"])
    if "breakeven" in key:
        labels.extend(["breakeven", "盈亏平衡通胀", "通胀预期"])
    if "real_yield" in key:
        labels.extend(["real yield", "实际利率", "实际收益率"])
    if key == "vix":
        labels.extend(["VIX", "波动率"])
    if key == "high_yield_spread":
        labels.extend(["high yield spread", "信用利差", "高收益利差"])
    return _dedupe_strings(labels)


def _has_any_regex(text: str, patterns: list[str]) -> bool:
    return any(re.search(pattern, text, re.IGNORECASE) for pattern in patterns)


def _surrounding_text(text: str, needle: str, radius: int) -> str:
    index = text.find(needle)
    if index < 0:
        return needle
    return text[max(0, index - radius) : min(len(text), index + len(needle) + radius)]


def _sentence_containing(text: str, needle: str) -> str:
    for sentence in _sentences(text):
        if needle in sentence:
            return sentence
    return ""


def _sentences(text: str) -> list[str]:
    return [item.strip() for item in re.split(r"[\n。；;]+", text) if item.strip()]


def _clauses(text: str) -> list[str]:
    return [item.strip() for item in re.split(r"[\n。；;，,、]+", text) if item.strip()]


def _has_boundary_marker(text: str) -> bool:
    return any(marker in text for marker in BROADER_BOUNDARY_MARKERS)


def _dedupe_strings(values: list[str]) -> list[str]:
    seen = set()
    result = []
    for value in values:
        if not value or value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result


def _is_negated_trade_sentence(sentence: str) -> bool:
    if "越跌越买" in sentence:
        return False
    if re.search(rf"是否(?:应|应该|该)?[^\n。；]{{0,8}}{PAUSE_DCA_PATTERN}", sentence):
        return True
    if any(marker in sentence for marker in TRADE_NEGATION_MARKERS):
        return True
    return bool(re.search(r"不是[^\n。；]{0,20}(?:交易|操作|指令|建议)", sentence))


def _is_pause_dca_directive(sentence: str) -> bool:
    directive_pattern = rf"(?:应|应该|该|建议|需要|需|必须|最好|可以考虑|考虑)[^\n。；]{{0,10}}{PAUSE_DCA_PATTERN}"
    if re.search(directive_pattern, sentence):
        return True
    stripped = re.sub(r"[\s，,。；;！!？?]+", "", sentence)
    return bool(re.fullmatch(PAUSE_DCA_PATTERN, stripped))
