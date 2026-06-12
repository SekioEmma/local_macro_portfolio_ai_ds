const moduleLabels: Record<string, string> = {
  credit_stress: "信用压力",
  rate_pressure: "利率压力",
  real_yield_pressure: "实际收益率压力",
  inflation_energy_pressure: "通胀与能源压力",
  equity_trend: "权益趋势",
  breadth_concentration_proxy: "宽度/集中度代理",
  portfolio_deviation: "组合偏离",
  labor_macro: "劳动力宏观"
};

const statusLabels: Record<string, string> = {
  ok: "正常",
  watch: "观察",
  pressure: "承压",
  stress: "压力显著",
  missing: "缺失",
  unknown: "未知",
  insufficient_history: "历史不足",
  research_needed: "需研究数据源",
  not_available: "不可用",
  stale: "过期",
  degraded: "降级",
  error: "错误",
  not_run_yet: "未运行"
};

const sourceBadgeLabels: Record<string, string> = {
  official: "官方",
  official_fallback: "官方备用",
  unofficial_fallback: "非官方备用",
  proxy: "代理指标",
  derived: "派生",
  local: "本地",
  "search-derived": "搜索派生",
  missing: "来源缺失",
  research_needed: "待研究"
};

const freshnessLabels: Record<string, string> = {
  fresh: "新鲜",
  historical: "历史数据",
  normal_lag: "正常滞后",
  stale: "过期",
  unknown: "新鲜度未知",
  missing: "新鲜度缺失",
  insufficient_history: "历史不足"
};

const missingReasonLabels: Record<string, string> = {
  "Only index level is available; YoY requires historical comparison.":
    "只有指数水平；YoY 需要历史同比比较。",
  "PPI final demand series is not configured; do not use PPIACO as final demand.":
    "PPI final demand 尚未配置；不能用 PPIACO 代替。",
  "FRED PPIFIS PPI final demand compact observation is missing; do not use PPIACO as final demand.":
    "PPI 最终需求官方观测值缺失，不能用 PPIACO 替代。",
  "PPI final demand YoY requires at least 13 monthly PPIFIS observations; do not use index level as YoY.":
    "PPI 最终需求同比需要至少 13 个月 PPIFIS 历史，不能把指数水平当同比。"
};

const metricLabels: Record<string, string> = {
  ppi_final_demand: "PPI 最终需求",
  ppi_final_demand_yoy: "PPI 最终需求同比",
  ppi_final_demand_mom: "PPI 最终需求环比"
};

export function getModuleLabel(moduleKey: string) {
  return moduleLabels[moduleKey] || moduleKey;
}

export function getStatusLabel(status: string) {
  return statusLabels[status] || status;
}

export function getSourceBadgeLabel(sourceBadge: string) {
  return sourceBadgeLabels[sourceBadge] || sourceBadge;
}

export function getFreshnessLabel(freshnessStatus: string) {
  return freshnessLabels[freshnessStatus] || freshnessStatus;
}

export function getAiContextLabel(aiContextAllowed: boolean) {
  return aiContextAllowed ? "可进入 AI 事实层" : "不进入 AI 事实层";
}

export function getMissingReasonLabel(reason: string | null | undefined) {
  if (!reason) return "";
  return missingReasonLabels[reason] || reason;
}

export function getMetricLabel(metricKey: string) {
  return metricLabels[metricKey] || metricKey;
}

export function formatCompactHint(text: string | null | undefined) {
  if (!text) return "";
  const normalized = text.replace(/\s+/g, " ").trim();
  if (normalized.length <= 120) return normalized;
  return `${normalized.slice(0, 117)}...`;
}

export function formatSourceFreshness(sourceBadge: string, freshnessStatus: string) {
  return `${getSourceBadgeLabel(sourceBadge)} / ${getFreshnessLabel(freshnessStatus)}`;
}
