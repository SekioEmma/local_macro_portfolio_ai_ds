export const statusLabels: Record<string, string> = {
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

export const freshnessLabels: Record<string, string> = {
  fresh: "新鲜",
  historical: "历史数据",
  normal_lag: "正常滞后",
  stale: "过期",
  unknown: "新鲜度未知",
  missing: "新鲜度缺失",
  insufficient_history: "历史不足"
};

export const missingReasonLabels: Record<string, string> = {
  "Only index level is available; YoY requires historical comparison.":
    "只有指数水平；YoY 需要历史同比比较。",
  "PPI final demand series is not configured; do not use PPIACO as final demand.":
    "PPI final demand 尚未配置；不能用 PPIACO 代替。",
  "FRED PPIFIS PPI final demand compact observation is missing; do not use PPIACO as final demand.":
    "PPI 最终需求官方观测值缺失，不能用 PPIACO 替代。",
  "PPI final demand YoY requires at least 13 monthly PPIFIS observations; do not use index level as YoY.":
    "PPI 最终需求同比需要至少 13 个月 PPIFIS 历史，不能把指数水平当同比。"
};

Object.assign(statusLabels, {
  insufficient_evidence: "Insufficient evidence"
});

