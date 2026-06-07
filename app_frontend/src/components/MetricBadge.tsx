import { getStatusLabel } from "../utils/displayLabels";
import { statusClass } from "../utils/styleClasses";

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
