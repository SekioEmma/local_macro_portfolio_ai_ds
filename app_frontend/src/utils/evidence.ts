import type {
  DashboardEvidenceRow,
  DashboardMetric,
  DashboardModule
} from "../types";
import { formatEvidenceValueText } from "./displayLabels";

export const blockedStatuses = new Set([
  "missing",
  "research_needed",
  "insufficient_history",
  "insufficient_evidence",
  "not_available",
  "stale"
]);

export function rowsForModule(
  rows: DashboardEvidenceRow[],
  moduleKey: string
) {
  return rows.filter((row) => row.module === moduleKey);
}

export function findEvidenceRow(
  rows: DashboardEvidenceRow[],
  moduleKey: string,
  metricKey: string
) {
  return rows.find(
    (row) => row.module === moduleKey && row.metric_key === metricKey
  );
}

export function findMetric(
  module: DashboardModule | undefined,
  metricKey: string
) {
  return module?.key_metrics.find((metric) => metric.metric_key === metricKey);
}

export function usableMetric(metric: DashboardMetric | undefined) {
  return Boolean(metric && !blockedStatuses.has(metric.status));
}

export function usableRow(row: DashboardEvidenceRow | undefined) {
  return Boolean(row && !blockedStatuses.has(row.status));
}

export function evidenceValue(
  row: DashboardEvidenceRow | undefined,
  fallback = "not available"
) {
  if (!row) return fallback;
  return formatEvidenceValueText(row.value_text, row.status);
}

export function asRecord(value: unknown): Record<string, unknown> | null {
  return value !== null && typeof value === "object" && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : null;
}

export function asArray(value: unknown): unknown[] {
  return Array.isArray(value) ? value : [];
}

export function asRecordArray(value: unknown): Array<Record<string, unknown>> {
  if (Array.isArray(value)) {
    return value
      .map(asRecord)
      .filter((item): item is Record<string, unknown> => item !== null);
  }
  const record = asRecord(value);
  if (!record) return [];
  const nested =
    record.scenarios ||
    record.events ||
    record.rows ||
    record.items ||
    record.values;
  if (Array.isArray(nested)) return asRecordArray(nested);
  return Object.entries(record)
    .filter(([, item]) => asRecord(item) !== null)
    .map(([key, item]) => ({ key, ...(item as Record<string, unknown>) }));
}

export function stringList(value: unknown): string[] {
  if (Array.isArray(value)) {
    return value
      .map((item) => compactText(item))
      .filter((item): item is string => Boolean(item));
  }
  if (typeof value === "string") {
    return value
      .split(/[,;|]/)
      .map((item) => item.trim())
      .filter(Boolean);
  }
  const record = asRecord(value);
  if (!record) return [];
  return Object.entries(record).map(
    ([key, item]) => `${key}: ${compactText(item) || "not available"}`
  );
}

export function compactText(value: unknown): string {
  if (value === null || value === undefined || value === "") {
    return "not available";
  }
  if (typeof value === "string") return value;
  if (typeof value === "number" || typeof value === "boolean") {
    return String(value);
  }
  if (Array.isArray(value)) {
    return value.map(compactText).join(" · ");
  }
  const record = asRecord(value);
  if (!record) return String(value);
  return Object.entries(record)
    .slice(0, 8)
    .map(([key, item]) => `${key}: ${compactText(item)}`)
    .join(" · ");
}

export function recordEntries(value: unknown) {
  const record = asRecord(value);
  return record ? Object.entries(record) : [];
}

export function metricUpdatedAt(metric: DashboardMetric) {
  return metric.generated_at || metric.observation_date;
}

export function moduleUpdatedAt(module: DashboardModule) {
  if (module.updated_at) return module.updated_at;
  return (
    module.key_metrics.find((metric) => metric.generated_at)?.generated_at ||
    module.key_metrics.find((metric) => metric.observation_date)
      ?.observation_date ||
    null
  );
}

export function groupRowsByModule(rows: DashboardEvidenceRow[]) {
  const grouped = new Map<string, DashboardEvidenceRow[]>();
  for (const row of rows) {
    grouped.set(row.module, [...(grouped.get(row.module) || []), row]);
  }
  return grouped;
}

export function uniqueValues<T>(values: T[]) {
  return Array.from(new Set(values));
}
