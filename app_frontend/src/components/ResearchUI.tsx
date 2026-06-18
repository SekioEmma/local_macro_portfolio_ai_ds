import type { ReactNode } from "react";
import {
  formatEvidenceValueText,
  getAiContextLabel,
  getFreshnessLabel,
  getSourceBadgeLabel,
  getStatusLabel
} from "../utils/displayLabels";
import {
  aiContextClass,
  freshnessClass,
  sourceBadgeClass,
  statusClass
} from "../utils/styleClasses";
import { ResearchIcon, type ResearchIconName } from "./ResearchIcon";

export function PageHeader({
  eyebrow,
  title,
  subtitle,
  actions
}: {
  eyebrow: string;
  title: string;
  subtitle: string;
  actions?: ReactNode;
}) {
  return (
    <header className="research-page-header">
      <div>
        <p className="research-kicker">{eyebrow}</p>
        <h1>{title}</h1>
        <p className="research-subtitle">{subtitle}</p>
      </div>
      {actions && <div className="page-header-actions">{actions}</div>}
    </header>
  );
}

export function SectionHeading({
  index,
  title,
  description
}: {
  index?: string;
  title: string;
  description?: string;
}) {
  return (
    <header className="research-section-heading">
      <div>
        {index && <p className="research-kicker">{index}</p>}
        <h2>{title}</h2>
      </div>
      {description && <p>{description}</p>}
    </header>
  );
}

export function MetaStrip({
  items
}: {
  items: Array<{ label: string; value: ReactNode; tone?: string }>;
}) {
  return (
    <dl className="briefing-meta-strip">
      {items.map((item) => (
        <div key={item.label} className={item.tone ? `meta-${item.tone}` : ""}>
          <dt>{item.label}</dt>
          <dd>{item.value}</dd>
        </div>
      ))}
    </dl>
  );
}

export function StatusBadge({ status }: { status: string }) {
  return (
    <span className={`status-badge ${statusClass(status)}`} title={status}>
      {getStatusLabel(status)}
    </span>
  );
}

export function SourceBadge({
  sourceBadge
}: {
  sourceBadge: string | null | undefined;
}) {
  const normalized = sourceBadge || "missing";
  return (
    <span
      className={`data-badge source-badge ${sourceBadgeClass(normalized)}`}
      title={normalized}
    >
      {getSourceBadgeLabel(normalized)}
    </span>
  );
}

export function FreshnessBadge({
  freshness
}: {
  freshness: string | null | undefined;
}) {
  const normalized = freshness || "unknown";
  return (
    <span
      className={`data-badge freshness-badge ${freshnessClass(normalized)}`}
      title={normalized}
    >
      {getFreshnessLabel(normalized)}
    </span>
  );
}

export function AIContextBadge({
  allowed,
  reason
}: {
  allowed: boolean;
  reason?: string | null;
}) {
  return (
    <span
      className={`data-badge ai-context-badge ${aiContextClass(allowed)}`}
      title={reason || ""}
    >
      {getAiContextLabel(allowed)}
    </span>
  );
}

export function BoundaryNotice({
  title = "边界说明",
  children,
  tone = "neutral"
}: {
  title?: string;
  children: ReactNode;
  tone?: "neutral" | "local" | "warning";
}) {
  return (
    <aside className={`boundary-notice boundary-${tone}`}>
      <ResearchIcon name="shield" size={17} />
      <div>
        <strong>{title}</strong>
        <div>{children}</div>
      </div>
    </aside>
  );
}

export function EmptyState({
  title,
  description,
  icon = "database"
}: {
  title: string;
  description: string;
  icon?: ResearchIconName;
}) {
  return (
    <section className="empty-state">
      <ResearchIcon name={icon} size={28} />
      <h2>{title}</h2>
      <p>{description}</p>
    </section>
  );
}

export function LoadingState({ title }: { title: string }) {
  return (
    <section className="empty-state" aria-live="polite">
      <span className="loading-mark" />
      <h2>{title}</h2>
      <p>正在读取本地只读证据，不调用外部服务。</p>
    </section>
  );
}

export function ErrorState({
  title,
  message
}: {
  title: string;
  message: string | null;
}) {
  return (
    <section className="empty-state empty-state-error" role="alert">
      <ResearchIcon name="diagnostics" size={28} />
      <h2>{title}</h2>
      <p>{message || "页面数据不可用，请确认本地后端已启动。"}</p>
    </section>
  );
}

export function DisabledSurfaceNotice({
  title,
  description
}: {
  title: string;
  description: string;
}) {
  return (
    <section className="disabled-surface-notice" aria-disabled="true">
      <ResearchIcon name="shield" size={20} />
      <div>
        <strong>{title}</strong>
        <p>{description}</p>
      </div>
    </section>
  );
}

export function MetricValue({
  valueText,
  status,
  unit
}: {
  valueText: string;
  status: string;
  unit?: string | null;
}) {
  return (
    <span className="metric-value-text">
      {formatEvidenceValueText(valueText, status)}
      {unit && <small>{unit}</small>}
    </span>
  );
}

export function formatTimestamp(value: string | null | undefined) {
  if (!value) return "not available";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return value;
  return new Intl.DateTimeFormat("zh-CN", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false
  }).format(parsed);
}

export function humanizeKey(value: string) {
  return value
    .replace(/_/g, " ")
    .replace(/\b\w/g, (char: string) => char.toUpperCase());
}
