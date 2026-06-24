from __future__ import annotations

import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from llm.comparison_validator import validate_comparison_answer  # noqa: E402


SYNTHETIC_FACTS = {
    "allocation_direction": {
        "sp500": "underweight",
        "nasdaq100": "underweight",
        "short_bond": "overweight",
        "gold": "overweight",
    },
    "missing_data_terms": [
        "PE",
        "forward PE",
        "CAPE",
        "valuation percentile",
        "FedWatch probability",
        "consensus CPI",
        "CPI surprise",
        "consensus PPI",
        "PPI surprise",
        "intraday Treasury high",
        "Reuters",
        "FactSet",
        "Bloomberg",
        "Goldman",
        "market breadth",
        "mega-cap concentration",
    ],
    "allowed_external_sources": ["FRED", "FRED:DGS10", "FRED:CPIAUCSL", "FRED:DCOILWTICO"],
    "provided_market_data_terms": [
        "real_yield_10y",
        "dgs10_30d_high",
        "dgs10_5d_avg",
        "dgs10_10d_avg",
        "headline_cpi_yoy_pct",
        "dgs10_5pct_breakout_confirmed",
        "nominal_yield_10y",
        "nominal_yield_30y",
        "dgs30_5d_avg",
        "dgs30_5pct_breakout_confirmed",
        "high_yield_spread",
        "wti_oil",
        "brent_oil",
        "wti_oil_30d_change",
        "brent_oil_30d_change",
        "ppi_all_commodities_yoy_pct",
        "DGS10",
        "FRED",
        "WTI",
        "CPI",
        "PPIACO",
    ],
    "provided_market_data_values": {
        "real_yield_10y": {
            "value": 2.16,
            "unit": "percent",
            "source": "FRED",
            "observation_date": "2026-05-22",
            "freshness": "fresh",
            "status": "ok",
            "error": None,
        },
        "dgs10_30d_high": {
            "value": 4.98,
            "unit": "percent",
            "source": "FRED:DGS10",
            "observation_date": "2026-05-22",
            "freshness": "fresh",
            "status": "ok",
            "error": None,
        },
        "dgs10_5d_avg": {
            "value": 4.54,
            "unit": "percent",
            "source": "FRED:DGS10",
            "observation_date": "2026-05-26",
            "freshness": "fresh",
            "status": "ok",
            "error": None,
        },
        "dgs10_10d_avg": {
            "value": 4.55,
            "unit": "percent",
            "source": "FRED:DGS10",
            "observation_date": "2026-05-26",
            "freshness": "fresh",
            "status": "ok",
            "error": None,
        },
        "dgs10_5pct_breakout_confirmed": {
            "value": False,
            "unit": "boolean",
            "source": "FRED:DGS10",
            "observation_date": "2026-05-22",
            "freshness": "fresh",
            "status": "ok",
            "error": None,
        },
        "nominal_yield_10y": {
            "value": 4.5,
            "unit": "percent",
            "source": "FRED:DGS10",
            "observation_date": "2026-05-26",
            "freshness": "fresh",
            "status": "ok",
            "error": None,
        },
        "nominal_yield_30y": {
            "value": 5.03,
            "unit": "percent",
            "source": "FRED:DGS30",
            "observation_date": "2026-05-26",
            "freshness": "fresh",
            "status": "ok",
            "error": None,
        },
        "dgs30_5d_avg": {
            "value": 5.098,
            "unit": "percent",
            "source": "FRED:DGS30",
            "observation_date": "2026-05-26",
            "freshness": "fresh",
            "status": "ok",
            "error": None,
        },
        "dgs30_5pct_breakout_confirmed": {
            "value": True,
            "unit": "boolean",
            "source": "FRED:DGS30",
            "observation_date": "2026-05-26",
            "freshness": "fresh",
            "status": "ok",
            "error": None,
        },
        "headline_cpi_yoy_pct": {
            "value": 3.78,
            "unit": "percent",
            "source": "FRED:CPIAUCSL",
            "observation_date": "2026-04-01",
            "freshness": "normal_lag",
            "status": "ok",
            "error": None,
        },
        "wti_oil": {
            "value": 112.25,
            "unit": "USD per barrel",
            "source": "FRED:DCOILWTICO",
            "observation_date": "2026-05-18",
            "freshness": "stale",
            "status": "ok",
            "error": None,
        },
        "brent_oil": {
            "value": 118.75,
            "unit": "USD per barrel",
            "source": "FRED:DCOILBRENTEU",
            "observation_date": "2026-05-18",
            "freshness": "stale",
            "status": "ok",
            "error": None,
        },
        "wti_oil_30d_change": {
            "value": 6.2,
            "unit": "percent",
            "source": "FRED:DCOILWTICO",
            "observation_date": "2026-05-18",
            "freshness": "stale",
            "status": "ok",
            "error": None,
        },
        "brent_oil_30d_change": {
            "value": 4.8,
            "unit": "percent",
            "source": "FRED:DCOILBRENTEU",
            "observation_date": "2026-05-18",
            "freshness": "stale",
            "status": "ok",
            "error": None,
        },
        "ppi_all_commodities_yoy_pct": {
            "value": 9.82,
            "unit": "percent",
            "source": "FRED:PPIACO",
            "observation_date": "2026-04-01",
            "freshness": "normal_lag",
            "status": "ok",
            "error": None,
        },
        "high_yield_spread": {
            "value": 2.71,
            "unit": "percent",
            "source": "FRED",
            "observation_date": "2026-05-27",
            "freshness": "fresh",
            "status": "ok",
            "error": None,
        },
    },
}


ALLOWED_CASES = {
    "real_yield_10y evidence row": (
        "| metric_key | 指标 | 数值 | 单位 | observation_date | source | freshness/status | 用途/解释 |\n"
        "| real_yield_10y | 10年期实际利率 | 2.16 | percent | 2026-05-22 | FRED | fresh | 10年期实际利率 |"
    ),
    "dgs10_30d_high non-intraday row": (
        "| metric_key | 指标 | 数值 | 单位 | observation_date | source | freshness/status | 用途/解释 |\n"
        "| dgs10_30d_high | 10年期美债30日高点 | 4.98 | percent | 2026-05-22 | FRED:DGS10 | fresh | FRED日度高点，非盘中高点 |"
    ),
    "headline_cpi_yoy_pct non-surprise row": (
        "| metric_key | 指标 | 数值 | 单位 | observation_date | source | freshness/status | 用途/解释 |\n"
        "| headline_cpi_yoy_pct | CPI同比 | 3.78 | percent | 2026-04-01 | FRED:CPIAUCSL | normal_lag | CPI同比数据，非超预期/低于预期判断 |"
    ),
    "false breakout boundary row": (
        "| metric_key | 指标 | 数值 | 单位 | observation_date | source | freshness/status | 用途/解释 |\n"
        "| dgs10_5pct_breakout_confirmed | 10年期5%阈值确认 | false | boolean | 2026-05-22 | FRED:DGS10 | fresh | 按本项目定义的10年期5%阈值未达确认条件 |"
    ),
    "DGS daily non-intraday boundary": "FRED DGS10/DGS30 为日度 constant maturity yield，不是盘中高点。",
    "stale WTI safe boundary": "截至 observation_date 的 WTI 数据曾显示能源价格压力；由于 freshness=stale，不能确认当前实时油价。",
    "DGS30 latest and 5d average supported": (
        "首先，根据FRED的日度观察数据（非盘中高点），30年期美债收益率 latest daily observation 为5.03%，"
        "其5日观察均值为5.098%"
    ),
    "DGS10 false breakout boundary supported": (
        "必须指出，这并非基于盘中高点，且 10年期美债收益率（4.5%）尚未触发该确认"
        "（dgs10_5pct_breakout_confirmed 为 false），反映长端利率压力在久期最远端更为突出"
    ),
    "DGS10 rolling averages with exact evidence keys": (
        "数据证据表\n"
        "| metric_key | 指标 | 数值 | 单位 | observation_date | source | freshness/status | 用途/解释 |\n"
        "| dgs10_5d_avg | DGS10 5日均值 | 4.54 | percent | 2026-05-26 | FRED:DGS10 | fresh | FRED daily observation rolling average; not intraday high |\n"
        "| dgs10_10d_avg | DGS10 10日均值 | 4.55 | percent | 2026-05-26 | FRED:DGS10 | fresh | FRED daily observation rolling average; not intraday high |\n\n"
        "DGS10的5日均值为4.54%，10日均值为4.55%，这些来自 FRED daily observation rolling averages，不是盘中高点。"
    ),
}


BLOCKED_CASES = {
    "FedWatch probability": "FedWatch显示降息概率为70%。",
    "forward PE": "forward PE 为 22。",
    "intraday yield high": "盘中收益率高点达到5.2%。",
    "CPI surprise": "CPI超预期。",
    "false breakout but confirmed": "dgs10_5pct_breakout_confirmed=false 但已确认突破5%。",
    "stale oil as current": "当前油价正在飙升并推动通胀。",
    "cash reserve redeploy": "现金准备金可用于立即补仓。",
    "trade-like Nasdaq instruction": "建议立即加仓纳指。",
}


REGRESSION_CASES = {
    "DGS10 rolling averages missing exact evidence keys": (
        "数据证据表\n"
        "| metric_key | 指标 | 数值 | 单位 | observation_date | source | freshness/status | 用途/解释 |\n"
        "| nominal_yield_10y | DGS10 | 4.50 | percent | 2026-05-26 | FRED:DGS10 | fresh | FRED daily observation; not intraday high |\n\n"
        "DGS10的5日均值为4.54%，10日均值为4.55%，仍距阈值有一段距离。"
    ),
    "DGS10 rolling averages with exact evidence keys": ALLOWED_CASES[
        "DGS10 rolling averages with exact evidence keys"
    ],
    "oil metrics missing exact evidence keys": (
        "数据证据表\n"
        "| metric_key | 指标 | 数值 | 单位 | observation_date | source | freshness/status | 用途/解释 |\n"
        "| headline_cpi_yoy_pct | CPI同比 | 3.78 | percent | 2026-04-01 | FRED:CPIAUCSL | normal_lag | CPI同比数据 |\n\n"
        "WTI为112.25美元/桶，Brent为118.75美元/桶，wti_oil_30d_change为6.2%，brent_oil_30d_change为4.8%。"
    ),
    "oil metrics with exact evidence keys": (
        "数据证据表\n"
        "| metric_key | 指标 | 数值 | 单位 | observation_date | source | freshness/status | 用途/解释 |\n"
        "| wti_oil | WTI | 112.25 | USD per barrel | 2026-05-18 | FRED:DCOILWTICO | stale | 截至 observation_date 的 WTI 数据，非实时油价 |\n"
        "| brent_oil | Brent | 118.75 | USD per barrel | 2026-05-18 | FRED:DCOILBRENTEU | stale | 截至 observation_date 的 Brent 数据，非实时油价 |\n"
        "| wti_oil_30d_change | WTI 30d change | 6.2 | percent | 2026-05-18 | FRED:DCOILWTICO | stale | 30d change，非实时油价 |\n"
        "| brent_oil_30d_change | Brent 30d change | 4.8 | percent | 2026-05-18 | FRED:DCOILBRENTEU | stale | 30d change，非实时油价 |\n\n"
        "截至 observation_date 的 WTI 为112.25美元/桶，Brent为118.75美元/桶；wti_oil_30d_change为6.2%，brent_oil_30d_change为4.8%，这些都是 stale 历史代理变量，不代表当前实时油价。"
    ),
    "Brent under WTI label": (
        "数据证据表\n"
        "| metric_key | 指标 | 数值 | 单位 | observation_date | source | freshness/status | 用途/解释 |\n"
        "| brent_oil | Brent | 102.75 | USD per barrel | 2026-05-18 | FRED:DCOILBRENTEU | stale | 截至 observation_date 的 Brent 数据，非实时油价 |\n"
        "| brent_oil_30d_change | Brent 30d change | -9.78 | percent | 2026-05-18 | FRED:DCOILBRENTEU | stale | 30d change，非实时油价 |\n\n"
        "WTI: Brent报102.75美元/桶，30日变动达-9.78%，意味着近一个月全球油价的压力有所缓解。"
    ),
    "Brent exact evidence keys": (
        "数据证据表\n"
        "| metric_key | 指标 | 数值 | 单位 | observation_date | source | freshness/status | 用途/解释 |\n"
        "| brent_oil | Brent | 118.75 | USD per barrel | 2026-05-18 | FRED:DCOILBRENTEU | stale | 截至 observation_date 的 Brent 数据，非实时油价 |\n"
        "| brent_oil_30d_change | Brent 30d change | 4.8 | percent | 2026-05-18 | FRED:DCOILBRENTEU | stale | 30d change，非实时油价 |\n\n"
        "截至 observation_date 的 Brent 为118.75美元/桶，brent_oil_30d_change为4.8%，这是 stale 历史代理变量，不代表当前实时油价。"
    ),
    "real yield primary driver wording": "黄金压力主要由实际利率决定，主要压力来自实际利率。",
    "PPI YoY missing exact evidence key": (
        "数据证据表\n"
        "| metric_key | 指标 | 数值 | 单位 | observation_date | source | freshness/status | 用途/解释 |\n"
        "| ppi_all_commodities | PPIACO index | 265.1 | index | 2026-04-01 | FRED:PPIACO | normal_lag | PPI all commodities index; not final demand PPI |\n\n"
        "PPI: PPIACO同比涨幅为9.82%，它不等同于最终需求PPI，不能直接解释为全面下游通胀压力。"
    ),
    "PPI YoY with exact evidence key": (
        "数据证据表\n"
        "| metric_key | 指标 | 数值 | 单位 | observation_date | source | freshness/status | 用途/解释 |\n"
        "| ppi_all_commodities_yoy_pct | PPIACO YoY | 9.82 | percent | 2026-04-01 | FRED:PPIACO | normal_lag | PPI all commodities YoY; not final demand PPI |\n\n"
        "PPI: PPIACO同比涨幅为9.82%，但它不等同于最终需求PPI，不能直接解释为全面下游通胀压力。"
    ),
    "allocation attribution unsupported": "当前短债高配主要原因是权益市值收缩。",
    "allocation attribution boundary": "当前数据包只能确认相对目标配置的方向和幅度；偏离成因可能来自建仓进度、价格变动、现金流和既有DCA路径等多因素，当前 context 不支持归因分解。",
    "FedWatch missing boundary": "缺失 FedWatch probability：无法量化市场隐含的加息/降息概率。",
    "DGS30 true DGS10 false consistency": (
        "30年期美债名义收益率按本项目定义的5%阈值确认条件已满足（dgs30_5pct_breakout_confirmed=true），"
        "但10年期尚未满足对应条件（dgs10_5pct_breakout_confirmed=false）。"
    ),
    "DGS conditional future confirmation": "如果曲线继续陡峭化、10年期同样进入5%以上区间并满足确认条件，贴现率对权益和黄金的压力将进一步扩大。",
    "DGS oil high yield exact evidence keys": (
        "数据证据表\n"
        "| 指标 | metric_key | 数值 | 单位 | observation_date | source | freshness/status | 用途/解释 |\n"
        "| 10年期美债名义收益率 | nominal_yield_10y | 4.50 | % | 2026-05-26 | FRED:DGS10 | fresh | 长端利率压力核心指标 |\n"
        "| DGS10 5日滚动均值 | dgs10_5d_avg | 4.54 | % | 2026-05-26 | FRED:DGS10 | fresh | 判断10年期是否接近5% |\n"
        "| DGS10 5%阈值确认 | dgs10_5pct_breakout_confirmed | false | boolean | 2026-05-26 | FRED:DGS10 | fresh | 10年期尚未满足阈值确认条件 |\n"
        "| 30年期美债名义收益率 | nominal_yield_30y | 5.03 | % | 2026-05-26 | FRED:DGS30 | fresh | 超长端利率压力阈值观察 |\n"
        "| DGS30 5日滚动均值 | dgs30_5d_avg | 5.098 | % | 2026-05-26 | FRED:DGS30 | fresh | 判断30年期是否持续高于5% |\n"
        "| DGS30 5%阈值确认 | dgs30_5pct_breakout_confirmed | true | boolean | 2026-05-26 | FRED:DGS30 | fresh | 按项目规则确认30年期5%阈值条件 |\n"
        "| WTI原油 | wti_oil | 112.25 | USD/bbl | 2026-05-18 | FRED:DCOILWTICO | stale | 能源价格压力 |\n"
        "| Brent原油 | brent_oil | 118.75 | USD/bbl | 2026-05-18 | FRED:DCOILBRENTEU | stale | 全球能源价格压力 |\n"
        "| 高收益债OAS利差 | high_yield_spread | 2.71 | % | 2026-05-27 | FRED | fresh | 信用压力观察 |\n\n"
        "DGS10最新读数为4.50%（nominal_yield_10y），5日均值为4.54%（dgs10_5d_avg），距5%仍有约50个基点，dgs10_5pct_breakout_confirmed=false。\n"
        "30年期美债（nominal_yield_30y）最新读数为5.03%，5日滚动均值（dgs30_5d_avg）为5.098%，最近10个日度观察全部在5%以上，dgs30_5pct_breakout_confirmed=true。\n"
        "截至 observation_date 的 WTI（wti_oil）报112.25美元/桶，Brent（brent_oil）报118.75美元/桶；美国高收益债OAS利差（high_yield_spread）为2.71%。"
    ),
    "DGS oil high yield missing exact evidence keys": (
        "数据证据表\n"
        "| 指标 | metric_key | 数值 | 单位 | observation_date | source | freshness/status | 用途/解释 |\n"
        "| CPI同比 | headline_cpi_yoy_pct | 3.78 | % | 2026-04-01 | FRED:CPIAUCSL | normal_lag | CPI同比数据 |\n\n"
        "DGS10最新读数为4.50%，WTI报112.25美元/桶，高收益债OAS利差为2.71%。"
    ),
    "allocation defensive skew attribution": "在利率维持高位背景下，组合自然呈现出防御型偏斜，反映了持续的利率压力与风险偏好收缩。",
}


def main() -> int:
    failures = []
    for name, answer_text in ALLOWED_CASES.items():
        result = validate_comparison_answer(answer_text, SYNTHETIC_FACTS)
        if result.get("has_hard_flag"):
            failures.append(f"allowed case raised hard flag: {name} -> {_true_flags(result['hard_flags'])}")

    for name, answer_text in BLOCKED_CASES.items():
        result = validate_comparison_answer(answer_text, SYNTHETIC_FACTS)
        if not result.get("has_hard_flag"):
            failures.append(f"blocked case did not raise hard flag: {name}")

    missing_keys_result = validate_comparison_answer(
        REGRESSION_CASES["DGS10 rolling averages missing exact evidence keys"],
        SYNTHETIC_FACTS,
    )
    missing_keys_hard = missing_keys_result.get("hard_flags", {})
    if not (
        missing_keys_hard.get("unsupported_market_data_claim")
        or missing_keys_hard.get("body_metric_not_in_evidence_table")
    ):
        failures.append(
            "regression case did not flag DGS10 rolling averages missing exact metric_key evidence rows"
        )

    exact_keys_result = validate_comparison_answer(
        REGRESSION_CASES["DGS10 rolling averages with exact evidence keys"],
        SYNTHETIC_FACTS,
    )
    exact_keys_hard = exact_keys_result.get("hard_flags", {})
    if exact_keys_hard.get("unsupported_market_data_claim"):
        failures.append("regression case raised unsupported_market_data_claim with exact DGS10 rolling keys")
    if exact_keys_hard.get("body_metric_not_in_evidence_table"):
        failures.append("regression case raised body_metric_not_in_evidence_table with exact DGS10 rolling keys")

    missing_oil_result = validate_comparison_answer(
        REGRESSION_CASES["oil metrics missing exact evidence keys"],
        SYNTHETIC_FACTS,
    )
    missing_oil_hard = missing_oil_result.get("hard_flags", {})
    if not (
        missing_oil_hard.get("unsupported_market_data_claim")
        or missing_oil_hard.get("body_metric_not_in_evidence_table")
    ):
        failures.append("regression case did not flag oil metrics missing exact metric_key evidence rows")

    exact_oil_result = validate_comparison_answer(
        REGRESSION_CASES["oil metrics with exact evidence keys"],
        SYNTHETIC_FACTS,
    )
    exact_oil_hard = exact_oil_result.get("hard_flags", {})
    if exact_oil_hard.get("unsupported_market_data_claim"):
        failures.append("regression case raised unsupported_market_data_claim with exact oil metric keys")
    if exact_oil_hard.get("body_metric_not_in_evidence_table"):
        failures.append("regression case raised body_metric_not_in_evidence_table with exact oil metric keys")

    brent_under_wti_result = validate_comparison_answer(
        REGRESSION_CASES["Brent under WTI label"],
        SYNTHETIC_FACTS,
    )
    brent_under_wti_hard = brent_under_wti_result.get("hard_flags", {})
    if not (
        brent_under_wti_hard.get("unsupported_market_data_claim")
        or brent_under_wti_hard.get("body_metric_not_in_evidence_table")
    ):
        failures.append("regression case did not flag Brent values written under WTI label")

    brent_exact_result = validate_comparison_answer(
        REGRESSION_CASES["Brent exact evidence keys"],
        SYNTHETIC_FACTS,
    )
    brent_exact_hard = brent_exact_result.get("hard_flags", {})
    if brent_exact_hard.get("unsupported_market_data_claim"):
        failures.append("regression case raised unsupported_market_data_claim with exact Brent metric keys")
    if brent_exact_hard.get("body_metric_not_in_evidence_table"):
        failures.append("regression case raised body_metric_not_in_evidence_table with exact Brent metric keys")

    real_yield_driver_result = validate_comparison_answer(
        REGRESSION_CASES["real yield primary driver wording"],
        SYNTHETIC_FACTS,
    )
    if not real_yield_driver_result.get("soft_flags", {}).get("unsupported_real_yield_primary_driver_claim"):
        failures.append("regression case did not soft-flag real_yield primary-driver wording")

    ppi_missing_result = validate_comparison_answer(
        REGRESSION_CASES["PPI YoY missing exact evidence key"],
        SYNTHETIC_FACTS,
    )
    ppi_missing_hard = ppi_missing_result.get("hard_flags", {})
    if not (
        ppi_missing_hard.get("unsupported_market_data_claim")
        or ppi_missing_hard.get("body_metric_not_in_evidence_table")
    ):
        failures.append("regression case did not flag PPI YoY missing exact metric_key evidence row")

    ppi_exact_result = validate_comparison_answer(
        REGRESSION_CASES["PPI YoY with exact evidence key"],
        SYNTHETIC_FACTS,
    )
    ppi_exact_hard = ppi_exact_result.get("hard_flags", {})
    if ppi_exact_hard.get("unsupported_market_data_claim"):
        failures.append("regression case raised unsupported_market_data_claim with exact PPI YoY metric key")
    if ppi_exact_hard.get("body_metric_not_in_evidence_table"):
        failures.append("regression case raised body_metric_not_in_evidence_table with exact PPI YoY metric key")

    allocation_bad_result = validate_comparison_answer(
        REGRESSION_CASES["allocation attribution unsupported"],
        SYNTHETIC_FACTS,
    )
    if not allocation_bad_result.get("soft_flags", {}).get("current_vs_target_allocation_confusion"):
        failures.append("regression case did not soft-flag unsupported allocation attribution")

    allocation_boundary_result = validate_comparison_answer(
        REGRESSION_CASES["allocation attribution boundary"],
        SYNTHETIC_FACTS,
    )
    if allocation_boundary_result.get("soft_flags", {}).get("current_vs_target_allocation_confusion"):
        failures.append("regression case soft-flagged allocation attribution boundary wording")

    fedwatch_boundary_result = validate_comparison_answer(
        REGRESSION_CASES["FedWatch missing boundary"],
        SYNTHETIC_FACTS,
    )
    if fedwatch_boundary_result.get("hard_flags", {}).get("external_source_mentioned"):
        failures.append("regression case hard-flagged FedWatch missing-data boundary")

    dgs_mixed_result = validate_comparison_answer(
        REGRESSION_CASES["DGS30 true DGS10 false consistency"],
        SYNTHETIC_FACTS,
    )
    if dgs_mixed_result.get("hard_flags", {}).get("dgs_breakout_confirmation_conflict"):
        failures.append("regression case hard-flagged DGS30 true / DGS10 false consistency wording")

    dgs_conditional_result = validate_comparison_answer(
        REGRESSION_CASES["DGS conditional future confirmation"],
        SYNTHETIC_FACTS,
    )
    if dgs_conditional_result.get("hard_flags", {}).get("unsupported_market_data_claim"):
        failures.append("regression case hard-flagged conditional future DGS confirmation hypothesis")

    exact_market_result = validate_comparison_answer(
        REGRESSION_CASES["DGS oil high yield exact evidence keys"],
        SYNTHETIC_FACTS,
    )
    exact_market_hard = exact_market_result.get("hard_flags", {})
    if exact_market_hard.get("unsupported_market_data_claim"):
        failures.append("regression case raised unsupported_market_data_claim with exact DGS/oil/high_yield keys")
    if exact_market_hard.get("dgs_breakout_confirmation_conflict"):
        failures.append("regression case raised dgs_breakout_confirmation_conflict with exact DGS keys")
    if exact_market_hard.get("body_metric_not_in_evidence_table"):
        failures.append("regression case raised body_metric_not_in_evidence_table with exact DGS/oil/high_yield keys")

    missing_market_result = validate_comparison_answer(
        REGRESSION_CASES["DGS oil high yield missing exact evidence keys"],
        SYNTHETIC_FACTS,
    )
    missing_market_hard = missing_market_result.get("hard_flags", {})
    if not (
        missing_market_hard.get("unsupported_market_data_claim")
        or missing_market_hard.get("body_metric_not_in_evidence_table")
    ):
        failures.append("regression case did not flag missing exact DGS/oil/high_yield evidence keys")

    allocation_defensive_result = validate_comparison_answer(
        REGRESSION_CASES["allocation defensive skew attribution"],
        SYNTHETIC_FACTS,
    )
    if not allocation_defensive_result.get("soft_flags", {}).get("current_vs_target_allocation_confusion"):
        failures.append("regression case did not soft-flag defensive-skew allocation attribution")

    if failures:
        print("validator boundary check failed", file=sys.stderr)
        for failure in failures:
            print(f"- {failure}", file=sys.stderr)
        return 1

    print(
        f"validator boundary check passed: allowed={len(ALLOWED_CASES)} "
        f"blocked={len(BLOCKED_CASES)} regression={len(REGRESSION_CASES)}"
    )
    return 0


def _true_flags(flags: dict) -> list[str]:
    return [key for key, value in flags.items() if bool(value)]


if __name__ == "__main__":
    raise SystemExit(main())
