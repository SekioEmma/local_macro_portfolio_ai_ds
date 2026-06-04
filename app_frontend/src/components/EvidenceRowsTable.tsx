import type { DashboardEvidenceRow } from "../types";
import { MetricBadge } from "./MetricBadge";

type EvidenceRowsTableProps = {
  rows: DashboardEvidenceRow[];
  compact?: boolean;
};

export function EvidenceRowsTable({ rows, compact = false }: EvidenceRowsTableProps) {
  if (rows.length === 0) {
    return <p className="muted">No evidence rows available for this module.</p>;
  }

  return (
    <div className="evidence-table-wrap">
      <table className={compact ? "evidence-table compact" : "evidence-table"}>
        <thead>
          <tr>
            <th>metric_key</th>
            <th>display_name</th>
            <th>value_text</th>
            <th>status</th>
            <th>source_badge</th>
            <th>freshness_status</th>
            <th>observation_date</th>
            <th>ai_context_allowed</th>
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
              <td>{row.source_badge}</td>
              <td>{row.freshness_status}</td>
              <td>{row.observation_date || "not available"}</td>
              <td>
                {row.ai_context_allowed
                  ? "可进入 AI 事实层"
                  : "不进入 AI 事实层"}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
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
