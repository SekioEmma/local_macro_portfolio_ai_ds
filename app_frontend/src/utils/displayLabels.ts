import { moduleLabels } from "./moduleRegistry";
import { metricLabels } from "./metricRegistry";
import { sourceBadgeLabels } from "./sourceBadgeRegistry";
import { freshnessLabels, missingReasonLabels, statusLabels } from "./statusRegistry";

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

export function formatEvidenceValueText(valueText: string, status: string) {
  const text = valueText.trim();
  if (text && text !== "--") return text;
  if (status === "research_needed") return "research needed";
  if (status === "insufficient_history") return "insufficient history";
  if (status === "not_available") return "not available";
  if (status === "stale") return "stale";
  return "missing";
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
