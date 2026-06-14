import {
  formatEvidenceValueText,
  getMetricLabel,
  getModuleLabel,
  getSourceBadgeLabel,
  getStatusLabel
} from "./displayLabels";
import { getModuleBoundary } from "./moduleRegistry";

export const registryContractChecks = {
  moduleLabels: [
    getModuleLabel("financial_stress_composite") === "Financial stress composite",
    getModuleLabel("pullback_systemic_risk_checklist") ===
      "Pullback/systemic risk checklist",
    getModuleLabel("historical_risk_percentile") === "Historical risk percentile",
    getModuleLabel("liquidity_funding_stress") === "Liquidity/funding stress",
    getModuleLabel("unknown_module_key") === "unknown_module_key"
  ],
  metricLabels: [
    getMetricLabel("financial_stress_score") === "Financial stress score",
    getMetricLabel("pullback_classification") === "Pullback classification",
    getMetricLabel("high_yield_spread_percentile") ===
      "High-yield spread percentile",
    getMetricLabel("liquidity_funding_stress_status") ===
      "Liquidity/funding stress status",
    getMetricLabel("macro_regime_label") === "Macro regime label",
    getMetricLabel("unknown_metric_key") === "unknown_metric_key"
  ],
  statusAndSourceFallbacks: [
    getStatusLabel("unknown_status_key") === "unknown_status_key",
    getSourceBadgeLabel("unknown_source_badge") === "unknown_source_badge"
  ],
  boundaries: [
    getModuleBoundary("financial_stress_composite").includes(
      "pressure temperature"
    ),
    getModuleBoundary("pullback_systemic_risk_checklist").includes(
      "reference review only"
    ),
    getModuleBoundary("historical_risk_percentile").includes("not a forecast"),
    getModuleBoundary("liquidity_funding_stress").includes(
      "reference evidence"
    ),
    getModuleBoundary("macro_regime_review").includes("current evidence review")
  ],
  valueFallbacks: [
    formatEvidenceValueText("--", "research_needed") === "research needed",
    formatEvidenceValueText("--", "insufficient_history") ===
      "insufficient history",
    formatEvidenceValueText("--", "not_available") === "not available",
    formatEvidenceValueText("--", "stale") === "stale"
  ]
} as const;
