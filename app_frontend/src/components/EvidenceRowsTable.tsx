import type { DashboardEvidenceRow } from "../types";
import {
  getAiContextLabel,
  getFreshnessLabel,
  getSourceBadgeLabel
} from "../utils/displayLabels";
import { MetricBadge } from "./MetricBadge";

type EvidenceRowsTableProps = {
  rows: DashboardEvidenceRow[];
  compact?: boolean;
};

export function EvidenceRowsTable({ rows, compact = false }: EvidenceRowsTableProps) {
  if (rows.length === 0) {
    return <p className="muted">当前模块没有证据行。</p>;
  }

  return (
    <div className="evidence-table-wrap">
      <table className={compact ? "evidence-table compact" : "evidence-table"}>
        <thead>
          <tr>
            <th>metric_key</th>
            <th>名称</th>
            <th>显示值</th>
            <th>状态</th>
            <th>来源类型</th>
            <th>新鲜度</th>
            <th>观测日期</th>
            <th>AI 事实层</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.row_id}>
              <td>{row.metric_key}</td>
              <td>{row.display_name}</td>
              <td className="value-cell">{safeValueText(row.value_text, row.status)}</td>
              <td>
                <MetricBadge status={row.status} />
              </td>
              <td title={row.source_badge}>{getSourceBadgeLabel(row.source_badge)}</td>
              <td title={row.freshness_status}>{getFreshnessLabel(row.freshness_status)}</td>
              <td>{row.observation_date || "not available"}</td>
              <td>{aiContextLabel(row)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function aiContextLabel(row: DashboardEvidenceRow) {
  if (row.ai_context_allowed) return getAiContextLabel(true);
  if (row.value !== null && row.value !== undefined) {
    return `有值但阻断：${row.blocked_reason || "metadata_incomplete"}`;
  }
  return `${getAiContextLabel(false)}：${row.blocked_reason || "not_eligible"}`;
}

function safeValueText(valueText: string, status: string) {
  const text = valueText.trim();
  if (text && text !== "--") return text;
  if (status === "research_needed") return "research needed";
  if (status === "insufficient_history") return "insufficient history";
  if (status === "not_available") return "not available";
  if (status === "stale") return "stale";
  return "missing";
}
