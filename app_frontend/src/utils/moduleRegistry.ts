export type ModuleRegistryEntry = {
  moduleKey: string;
  label: string;
  interpretationBoundary?: string;
  category?: "core" | "derived" | "model_output" | "research";
};

export const moduleLabels: Record<string, string> = {
  credit_stress: "信用压力",
  rate_pressure: "利率压力",
  real_yield_pressure: "实际收益率压力",
  inflation_energy_pressure: "通胀与能源压力",
  equity_trend: "权益趋势",
  breadth_concentration_proxy: "宽度/集中度代理",
  market_stress_derived: "市场压力派生",
  portfolio_deviation: "组合偏离",
  labor_macro: "劳动力宏观"
};

Object.assign(moduleLabels, {
  financial_stress_composite: "Financial stress composite",
  macro_regime_review: "Macro regime review",
  pullback_systemic_risk_checklist: "Pullback/systemic risk checklist",
  historical_risk_percentile: "Historical risk percentile",
  liquidity_funding_stress: "Liquidity/funding stress"
});

export const interpretationBoundaries: Record<string, string> = {
  credit_stress:
    "VIX 升高不是系统性危机的充分条件；信用压力模块用于区分普通回调和信用压力，不输出交易建议。",
  rate_pressure:
    "DGS 是日度观测，不是盘中高点；5% 是解释阈值，不是交易信号；breakout 需要明确证据。",
  real_yield_pressure:
    "实际收益率是机制解释，不是黄金或成长股的单一驱动，也不是交易信号。",
  inflation_energy_pressure:
    "CPI/PCE/PPI 是低频数据；没有明确预期数据时不得写超预期；PPIACO 不是 final demand PPI；油价变化不能机械推断通胀失控。",
  equity_trend:
    "指数回撤不是系统性危机的充分条件；没有 breadth/concentration 数据不得确认市场集中恶化。",
  portfolio_deviation:
    "组合偏离不能归因于宏观市场因素；只描述风险暴露；现金备用金不参与目标配置；不输出交易指令。"
};

Object.assign(interpretationBoundaries, {
  breadth_concentration_proxy:
    "Uses ETF/index proxy relationships only. SPY/RSP/QQQ are not true constituent breadth. Proxy concentration cannot confirm mega-cap concentration without constituent weights. Do not treat proxy rows as official facts or use them alone for systemic or crash risk.",
  market_stress_derived:
    "Drawdown is an outcome, not a cause. Curve slope is macro context, not a trading signal. TLT/SHY/GLD are ETF proxies, not official macro series. VIX, drawdown, and proxy moves alone cannot confirm systemic crisis.",
  labor_macro:
    "Sahm rule proxy is a recession-warning proxy, not official recession confirmation. One-month unemployment increases do not confirm recession. Claims increases are labor-pressure observations, not crisis confirmation. Payrolls are revised; do not overstate certainty.",
  financial_stress_composite:
    "Financial stress score is a transparent pressure temperature, not crash probability. It does not produce buy/sell/hedge instructions. VIX alone and equity drawdown alone are not systemic stress. Liquidity/funding evidence is confirmation context only. Official stress indices do not replace the project financial stress composite.",
  macro_regime_review:
    "Macro regime review is a current evidence review, not a prediction model, downside-event model, business-cycle call, or market direction forecast. It is for reference review only and does not produce probability, target allocation, or expected return.",
  pullback_systemic_risk_checklist:
    "This checklist is not crash probability. It does not predict market bottom or top. It does not produce buy/sell/hedge instructions. D14 cannot alone trigger systemic risk review. Liquidity/funding confirmation can upgrade review only when credit and transmission evidence also confirm. Missing valuation, earnings, and true breadth continue to limit crisis confirmation.",
  historical_risk_percentile:
    "Historical percentile is relative to available local history, not a forecast. Z-score is a normalization statistic, not crash probability. Short history can make percentile unstable. Different frequencies must not be mixed.",
  liquidity_funding_stress:
    "Liquidity/funding stress rows are reference evidence, not trading signals. Official stress indices are external reference layers and do not replace the project financial stress composite. Commercial paper spread can support funding-pressure confirmation but cannot alone prove systemic crisis. SOFR/EFFR/IORB/ON RRP describe policy plumbing and money-market backdrop, not market direction. ON RRP usage alone is not a risk trigger. Different frequencies must not be mixed without explicit as-of alignment. No crash probability or recession probability is produced. No buy/sell/hedge instruction is produced."
});

const moduleCategories: Record<string, ModuleRegistryEntry["category"]> = {
  financial_stress_composite: "model_output",
  macro_regime_review: "model_output",
  pullback_systemic_risk_checklist: "model_output",
  historical_risk_percentile: "derived",
  liquidity_funding_stress: "derived",
  market_stress_derived: "derived",
  breadth_concentration_proxy: "research",
  portfolio_deviation: "core"
};

export const moduleRegistry: Record<string, ModuleRegistryEntry> = Object.fromEntries(
  Object.entries(moduleLabels).map(([moduleKey, label]) => [
    moduleKey,
    {
      moduleKey,
      label,
      interpretationBoundary: interpretationBoundaries[moduleKey],
      category: moduleCategories[moduleKey]
    }
  ])
);

export function getModuleBoundary(moduleKey: string) {
  return interpretationBoundaries[moduleKey] || "暂无解释边界。";
}
