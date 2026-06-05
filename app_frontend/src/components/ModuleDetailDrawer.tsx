import type {
  DashboardEvidenceRow,
  DashboardMetric,
  DashboardModule
} from "../types";
import type { ReactNode } from "react";
import { EvidenceRowsTable } from "./EvidenceRowsTable";
import { MetricBadge } from "./MetricBadge";

type ModuleDetailDrawerProps = {
  moduleKey: string;
  moduleLabel: string;
  moduleSummary: DashboardModule;
  evidenceRows: DashboardEvidenceRow[];
  evidenceError: string | null;
  onClose: () => void;
};

const blockedStatuses = new Set([
  "missing",
  "research_needed",
  "insufficient_history",
  "not_available",
  "stale"
]);

const interpretationBoundaries: Record<string, string> = {
  credit_stress:
    "VIX 升高不是系统性危机的充分条件；信用压力模块用于区分普通回调和系统性风险，不能单独生成交易建议。",
  rate_pressure:
    "DGS 是日度观测，不是盘中高点；5% 是启发式心理阈值，不是交易信号；没有 confirmed boolean 不得写站稳或突破确认。",
  real_yield_pressure:
    "实际利率是机制解释，不是黄金或成长股的唯一/主要驱动，不是交易信号。",
  inflation_energy_pressure:
    "CPI/PCE/PPI 是低频数据；没有 consensus 不得写超预期；PPIACO 不是 final demand PPI；油价变化不能机械推断通胀失控。",
  equity_trend:
    "指数回撤不是系统性危机的充分条件；没有 breadth/concentration 数据不得确认市场集中恶化。",
  portfolio_deviation:
    "组合偏离不能归因于宏观市场因素；只描述风险暴露；现金备用金不参与目标配置；不得输出交易指令。"
};

export function ModuleDetailDrawer({
  moduleKey,
  moduleLabel,
  moduleSummary,
  evidenceRows,
  evidenceError,
  onClose
}: ModuleDetailDrawerProps) {
  const missingRows = evidenceRows.filter((row) => blockedStatuses.has(row.status));
  const aiAllowed = evidenceRows.filter((row) => row.ai_context_allowed);
  const aiBlocked = evidenceRows.filter((row) => !row.ai_context_allowed);
  const blockedReasons = summarizeBlockedReasons(evidenceRows);

  return (
    <div className="drawer-backdrop" role="presentation" onClick={onClose}>
      <aside
        className="module-detail-drawer"
        aria-label={`${moduleLabel} detail`}
        onClick={(event) => event.stopPropagation()}
      >
        <header className="drawer-header">
          <div>
            <p className="eyebrow">Show All / 查看详情</p>
            <h2>{moduleLabel}</h2>
            <p className="muted">{moduleKey}</p>
          </div>
          <button
            aria-label="Close module detail"
            className="icon-button"
            type="button"
            onClick={onClose}
          >
            ×
          </button>
        </header>

        <div className="drawer-status-row">
          <MetricBadge status={moduleSummary.status} />
          <span>{moduleSummary.source_badge || "source unknown"}</span>
          <span>{moduleSummary.updated_at || "updated time unavailable"}</span>
        </div>

        <DrawerSection title="Status Summary">
          <p>{moduleSummary.summary || "No compact module summary available."}</p>
          {moduleSummary.error_summary && (
            <p className="error-text">{moduleSummary.error_summary}</p>
          )}
          {moduleSummary.next_action && (
            <p className="next-action">{moduleSummary.next_action}</p>
          )}
        </DrawerSection>

        <DrawerSection title="Key Metrics">
          <div className="drawer-metric-grid">
            {moduleSummary.key_metrics.map((metric) => (
              <MetricDetail key={metric.metric_key} metric={metric} />
            ))}
          </div>
        </DrawerSection>

        <DrawerSection title="Evidence Rows">
          {evidenceError && (
            <p className="error-text">
              evidence rows unavailable: {evidenceError}
            </p>
          )}
          <EvidenceRowsTable rows={evidenceRows} compact />
        </DrawerSection>

        <DrawerSection title="Interpretation Boundary">
          <p>{interpretationBoundaries[moduleKey] || "No boundary note configured."}</p>
        </DrawerSection>

        <DrawerSection title="Missing / Research Needed">
          {missingRows.length === 0 ? (
            <p className="muted">No missing, research-needed, insufficient-history, not-available, or stale rows.</p>
          ) : (
            <ul className="drawer-list">
              {missingRows.map((row) => (
                <li key={row.row_id}>
                  <div>
                    <strong>{row.display_name}</strong>
                    <small>{row.metric_key}</small>
                  </div>
                  <MetricBadge status={row.status} />
                  <p>
                    {row.missing_reason ||
                      row.interpretation_hint ||
                      blockedReason(row)}
                  </p>
                </li>
              ))}
            </ul>
          )}
        </DrawerSection>

        <DrawerSection title="AI Factual Context Eligibility">
          <div className="ai-eligibility-grid">
            <div>
              <span>可进入 AI factual context</span>
              <strong>{aiAllowed.length}</strong>
            </div>
            <div>
              <span>不进入 AI factual context</span>
              <strong>{aiBlocked.length}</strong>
            </div>
          </div>
          {blockedReasons.length > 0 && (
            <ul className="compact-list">
              {blockedReasons.map((reason) => (
                <li key={reason}>
                  <span>{reason}</span>
                  <small>blocked</small>
                </li>
              ))}
            </ul>
          )}
          <button className="secondary-button" type="button" disabled>
            Open in AI Chat later phase
          </button>
        </DrawerSection>
      </aside>
    </div>
  );
}

function DrawerSection({
  title,
  children
}: {
  title: string;
  children: ReactNode;
}) {
  return (
    <section className="drawer-section">
      <h3>{title}</h3>
      {children}
    </section>
  );
}

function MetricDetail({ metric }: { metric: DashboardMetric }) {
  const metadataIncomplete =
    metric.value !== null && metric.value !== undefined && !metric.ai_context_allowed;
  return (
    <article className="drawer-metric">
      <div className="module-card-head">
        <strong>{metric.display_name}</strong>
        <MetricBadge status={metric.status} />
      </div>
      <p className="drawer-value">{safeValueText(metric.value_text, metric.status)}</p>
      <dl>
        <div>
          <dt>source</dt>
          <dd>{metric.source_badge}</dd>
        </div>
        <div>
          <dt>freshness</dt>
          <dd>{metric.freshness_status}</dd>
        </div>
        <div>
          <dt>observation</dt>
          <dd>{metric.observation_date || "not available"}</dd>
        </div>
        <div>
          <dt>ai_context_allowed</dt>
          <dd>{metric.ai_context_allowed ? "可进入 AI 事实层" : "不进入 AI 事实层"}</dd>
        </div>
      </dl>
      {metadataIncomplete && (
        <p className="metric-reason">
          有值，但元数据不足，不进入 AI 事实层
        </p>
      )}
      {(metric.missing_reason || metric.interpretation_hint) && (
        <p className="metric-hint">
          {metric.missing_reason || metric.interpretation_hint}
        </p>
      )}
    </article>
  );
}

function summarizeBlockedReasons(rows: DashboardEvidenceRow[]) {
  return Array.from(new Set(rows.filter((row) => !row.ai_context_allowed).map(blockedReason)));
}

function blockedReason(row: DashboardEvidenceRow) {
  if (row.blocked_reason) return row.blocked_reason;
  if (blockedStatuses.has(row.status)) return row.status;
  if (["unknown", "missing", "stale", "insufficient_history"].includes(row.freshness_status)) {
    return row.freshness_status;
  }
  if (["missing", "research_needed", "search-derived", "proxy"].includes(row.source_badge)) {
    return row.source_badge;
  }
  if (!row.source && row.source_badge !== "local") return "no source";
  if (!row.observation_date && !row.generated_at) return "no date";
  return "not eligible";
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
