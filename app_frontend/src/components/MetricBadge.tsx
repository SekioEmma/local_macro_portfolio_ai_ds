import { getStatusLabel } from "../utils/displayLabels";

type MetricBadgeProps = {
  status: string;
};

export function MetricBadge({ status }: MetricBadgeProps) {
  return (
    <span className={`status-pill ${statusClass(status)}`} title={status}>
      {getStatusLabel(status)}
    </span>
  );
}

function statusClass(status: string) {
  if (status === "ok") return "ok";
  if (status === "stress" || status === "error") return "error";
  if (["watch", "pressure", "degraded", "stale"].includes(status)) return "warn";
  if (
    [
      "missing",
      "not_run_yet",
      "research_needed",
      "insufficient_history",
      "not_available"
    ].includes(status)
  ) {
    return "missing";
  }
  return "unknown";
}
