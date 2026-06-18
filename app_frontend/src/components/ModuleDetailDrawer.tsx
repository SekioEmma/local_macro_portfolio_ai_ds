import {
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode
} from "react";
import type {
  DashboardEvidenceRow,
  DashboardMetric,
  DashboardModule
} from "../types";
import {
  formatCompactHint,
  formatEvidenceValueText,
  getMissingReasonLabel
} from "../utils/displayLabels";
import { blockedStatuses, uniqueValues } from "../utils/evidence";
import { getModuleBoundary } from "../utils/moduleRegistry";
import { ResearchIcon } from "./ResearchIcon";
import {
  AIContextBadge,
  BoundaryNotice,
  formatTimestamp,
  FreshnessBadge,
  MetricValue,
  SourceBadge,
  StatusBadge
} from "./ResearchUI";

type DrawerTab = "overview" | "metrics" | "sources" | "boundaries";

type ModuleDetailDrawerProps = {
  moduleKey: string;
  moduleLabel: string;
  moduleSummary: DashboardModule;
  evidenceRows: DashboardEvidenceRow[];
  evidenceError: string | null;
  onClose: () => void;
};

const tabs: Array<{ key: DrawerTab; label: string }> = [
  { key: "overview", label: "概览" },
  { key: "metrics", label: "指标" },
  { key: "sources", label: "来源" },
  { key: "boundaries", label: "边界" }
];

const hardBoundaries: Record<string, string[]> = {
  credit_stress: [
    "VIX alone is not systemic crisis.",
    "Proxy-only evidence cannot confirm credit stress by itself."
  ],
  rate_pressure: [
    "DGS is daily, not intraday.",
    "No confirmed boolean means no breakout confirmation."
  ],
  inflation_energy_pressure: [
    "PPIACO is not final demand PPI.",
    "Low-frequency inflation observations do not support intraday conclusions."
  ],
  equity_trend: [
    "Equity drawdown alone does not confirm systemic risk.",
    "Return windows describe observed history, not a future path."
  ],
  breadth_concentration_proxy: [
    "Proxy breadth is not true breadth.",
    "Proxy evidence cannot confirm systemic risk alone."
  ],
  market_stress_derived: [
    "Drawdown is an outcome, not a cause.",
    "Curve slope is macro context, not a trading signal."
  ],
  portfolio_deviation: [
    "Portfolio deviation is local context only.",
    "Cash reserve must not be interpreted as action capital.",
    "No allocation or trading action is produced."
  ]
};

export function ModuleDetailDrawer({
  moduleKey,
  moduleLabel,
  moduleSummary,
  evidenceRows,
  evidenceError,
  onClose
}: ModuleDetailDrawerProps) {
  const [activeTab, setActiveTab] = useState<DrawerTab>("overview");
  const closeButtonRef = useRef<HTMLButtonElement>(null);
  const missingRows = evidenceRows.filter((row) =>
    blockedStatuses.has(row.status)
  );
  const aiAllowed = evidenceRows.filter((row) => row.ai_context_allowed).length;
  const sourceRows = evidenceRows.length
    ? evidenceRows
    : moduleSummary.key_metrics.map(metricToEvidenceLike);

  useEffect(() => {
    const previous = document.activeElement as HTMLElement | null;
    closeButtonRef.current?.focus();
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => {
      window.removeEventListener("keydown", handleKeyDown);
      previous?.focus();
    };
  }, [onClose]);

  return (
    <div className="drawer-backdrop" onMouseDown={onClose} role="presentation">
      <aside
        aria-label={`${moduleLabel} 模块详情`}
        aria-modal="true"
        className="module-audit-drawer"
        onMouseDown={(event) => event.stopPropagation()}
        role="dialog"
      >
        <header className="module-audit-header">
          <div>
            <p className="research-kicker">MODULE EVIDENCE AUDIT</p>
            <h2>{moduleLabel}</h2>
            <p>{moduleKey}</p>
          </div>
          <button
            ref={closeButtonRef}
            aria-label="关闭模块详情"
            className="drawer-close-button"
            onClick={onClose}
            type="button"
          >
            <ResearchIcon name="close" size={20} />
          </button>
        </header>

        <div className="module-audit-meta">
          <StatusBadge status={moduleSummary.status} />
          <SourceBadge sourceBadge={moduleSummary.source_badge} />
          <span>{formatTimestamp(moduleSummary.updated_at)}</span>
        </div>

        <div className="drawer-tabs" role="tablist" aria-label="模块详情分组">
          {tabs.map((tab) => (
            <button
              key={tab.key}
              aria-selected={activeTab === tab.key}
              className={activeTab === tab.key ? "is-active" : ""}
              onClick={() => setActiveTab(tab.key)}
              role="tab"
              type="button"
            >
              {tab.label}
            </button>
          ))}
        </div>

        <div className="drawer-tab-panel" role="tabpanel">
          {activeTab === "overview" && (
            <OverviewTab
              aiAllowed={aiAllowed}
              evidenceRows={evidenceRows}
              missingRows={missingRows}
              moduleSummary={moduleSummary}
            />
          )}
          {activeTab === "metrics" && (
            <MetricsTab
              evidenceError={evidenceError}
              metrics={moduleSummary.key_metrics}
              rows={evidenceRows}
            />
          )}
          {activeTab === "sources" && <SourcesTab rows={sourceRows} />}
          {activeTab === "boundaries" && (
            <BoundariesTab moduleKey={moduleKey} rows={evidenceRows} />
          )}
        </div>
      </aside>
    </div>
  );
}

function OverviewTab({
  moduleSummary,
  evidenceRows,
  missingRows,
  aiAllowed
}: {
  moduleSummary: DashboardModule;
  evidenceRows: DashboardEvidenceRow[];
  missingRows: DashboardEvidenceRow[];
  aiAllowed: number;
}) {
  const mainPressure = moduleSummary.key_metrics.find((metric) =>
    ["watch", "pressure", "stress"].includes(metric.status)
  );
  return (
    <div className="drawer-tab-stack">
      <DrawerSection title="状态摘要">
        <p className="drawer-lead">
          {moduleSummary.summary || "当前模块未提供摘要。"}
        </p>
        {moduleSummary.error_summary && (
          <p className="drawer-error">{moduleSummary.error_summary}</p>
        )}
        {moduleSummary.next_action && (
          <p className="drawer-next-action">{moduleSummary.next_action}</p>
        )}
      </DrawerSection>

      <div className="drawer-overview-grid">
        <OverviewStat
          label="关键指标"
          value={String(moduleSummary.key_metrics.length)}
        />
        <OverviewStat label="证据行" value={String(evidenceRows.length)} />
        <OverviewStat label="AI 可用" value={String(aiAllowed)} />
        <OverviewStat label="受限 / 缺失" value={String(missingRows.length)} />
      </div>

      <DrawerSection title="主要压力解释">
        {mainPressure ? (
          <article className="drawer-primary-metric">
            <div>
              <strong>{mainPressure.display_name}</strong>
              <small>{mainPressure.metric_key}</small>
            </div>
            <MetricValue
              status={mainPressure.status}
              unit={mainPressure.unit}
              valueText={mainPressure.value_text}
            />
            <StatusBadge status={mainPressure.status} />
          </article>
        ) : (
          <p className="drawer-muted">当前关键指标未标记为观察或承压。</p>
        )}
      </DrawerSection>

      <DrawerSection title="数据质量摘要">
        <div className="drawer-quality-summary">
          <span>
            fresh{" "}
            {
              moduleSummary.key_metrics.filter(
                (metric) => metric.freshness_status === "fresh"
              ).length
            }
          </span>
          <span>
            stale{" "}
            {
              moduleSummary.key_metrics.filter(
                (metric) => metric.freshness_status === "stale"
              ).length
            }
          </span>
          <span>blocked {missingRows.length}</span>
        </div>
      </DrawerSection>
    </div>
  );
}

function MetricsTab({
  metrics,
  rows,
  evidenceError
}: {
  metrics: DashboardMetric[];
  rows: DashboardEvidenceRow[];
  evidenceError: string | null;
}) {
  const metricMap = useMemo(
    () => new Map(rows.map((row) => [row.metric_key, row])),
    [rows]
  );
  return (
    <div className="drawer-tab-stack">
      {evidenceError && <p className="drawer-error">{evidenceError}</p>}
      <div className="drawer-metrics-list">
        {metrics.map((metric) => {
          const row = metricMap.get(metric.metric_key);
          return (
            <article key={metric.metric_key}>
              <header>
                <div>
                  <strong>{metric.display_name}</strong>
                  <small>{metric.metric_key}</small>
                </div>
                <StatusBadge status={metric.status} />
              </header>
              <MetricValue
                status={metric.status}
                unit={metric.unit}
                valueText={metric.value_text}
              />
              <div className="drawer-metric-badges">
                <SourceBadge sourceBadge={metric.source_badge} />
                <FreshnessBadge freshness={metric.freshness_status} />
                <AIContextBadge
                  allowed={metric.ai_context_allowed}
                  reason={row?.blocked_reason}
                />
              </div>
              <dl>
                <div>
                  <dt>观测日期</dt>
                  <dd>{metric.observation_date || "not available"}</dd>
                </div>
                <div>
                  <dt>频率</dt>
                  <dd>{metric.frequency_class || "not available"}</dd>
                </div>
                <div>
                  <dt>历史窗口</dt>
                  <dd>{metric.lookback_window || "not available"}</dd>
                </div>
                <div>
                  <dt>触发资格</dt>
                  <dd>{metric.trigger_eligibility || "not available"}</dd>
                </div>
              </dl>
              {(metric.missing_reason || metric.interpretation_hint) && (
                <p>
                  {getMissingReasonLabel(metric.missing_reason) ||
                    formatCompactHint(metric.interpretation_hint)}
                </p>
              )}
            </article>
          );
        })}
      </div>
    </div>
  );
}

function SourcesTab({
  rows
}: {
  rows: Array<
    Pick<
      DashboardEvidenceRow,
      | "row_id"
      | "display_name"
      | "metric_key"
      | "source"
      | "source_badge"
      | "source_series"
      | "observation_date"
      | "generated_at"
      | "freshness_status"
      | "ai_context_allowed"
      | "blocked_reason"
      | "missing_reason"
      | "lookback_window"
      | "observation_count"
      | "trigger_eligibility"
    >
  >;
}) {
  return (
    <div className="drawer-source-table-wrap">
      <table className="drawer-source-table">
        <thead>
          <tr>
            <th>指标</th>
            <th>来源</th>
            <th>序列</th>
            <th>观测 / 生成</th>
            <th>新鲜度</th>
            <th>AI</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.row_id}>
              <td>
                <strong>{row.display_name}</strong>
                <small>{row.metric_key}</small>
              </td>
              <td>
                <SourceBadge sourceBadge={row.source_badge} />
                <small>{row.source || "not available"}</small>
              </td>
              <td>{row.source_series || "not available"}</td>
              <td>
                {row.observation_date || row.generated_at || "not available"}
              </td>
              <td>
                <FreshnessBadge freshness={row.freshness_status} />
              </td>
              <td>
                <AIContextBadge
                  allowed={row.ai_context_allowed}
                  reason={row.blocked_reason}
                />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function BoundariesTab({
  moduleKey,
  rows
}: {
  moduleKey: string;
  rows: DashboardEvidenceRow[];
}) {
  const rowBoundaries = uniqueValues(
    rows
      .map((row) => row.interpretation_boundary)
      .filter((value): value is string => Boolean(value))
  );
  const missingInputs = uniqueValues(
    rows.flatMap((row) => row.missing_inputs || [])
  );
  const blockedReasons = uniqueValues(
    rows
      .map((row) => row.blocked_reason || row.missing_reason)
      .filter((value): value is string => Boolean(value))
  );
  return (
    <div className="drawer-tab-stack">
      <BoundaryNotice title="模块解释边界">
        {getModuleBoundary(moduleKey)}
      </BoundaryNotice>

      <DrawerSection title="固定边界">
        <ul className="drawer-boundary-list">
          {(hardBoundaries[moduleKey] || [
            "Current evidence review only.",
            "No trading action or allocation directive."
          ]).map((boundary) => (
            <li key={boundary}>{boundary}</li>
          ))}
        </ul>
      </DrawerSection>

      {rowBoundaries.length > 0 && (
        <DrawerSection title="证据行边界">
          <ul className="drawer-boundary-list">
            {rowBoundaries.map((boundary) => (
              <li key={boundary}>{boundary}</li>
            ))}
          </ul>
        </DrawerSection>
      )}

      <div className="drawer-boundary-grid">
        <DrawerSection title="缺失输入">
          {missingInputs.length ? (
            <ul className="drawer-boundary-list">
              {missingInputs.map((item) => (
                <li key={item}>{item}</li>
              ))}
            </ul>
          ) : (
            <p className="drawer-muted">没有公开的 missing inputs。</p>
          )}
        </DrawerSection>
        <DrawerSection title="阻断原因">
          {blockedReasons.length ? (
            <ul className="drawer-boundary-list">
              {blockedReasons.map((item) => (
                <li key={item}>{item}</li>
              ))}
            </ul>
          ) : (
            <p className="drawer-muted">没有公开的 blocked reason。</p>
          )}
        </DrawerSection>
      </div>
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
    <section className="drawer-audit-section">
      <h3>{title}</h3>
      {children}
    </section>
  );
}

function OverviewStat({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function metricToEvidenceLike(metric: DashboardMetric) {
  return {
    row_id: metric.metric_key,
    display_name: metric.display_name,
    metric_key: metric.metric_key,
    source: metric.source,
    source_badge: metric.source_badge,
    source_series: metric.source_series,
    observation_date: metric.observation_date,
    generated_at: metric.generated_at,
    freshness_status: metric.freshness_status,
    ai_context_allowed: metric.ai_context_allowed,
    blocked_reason: null,
    missing_reason: metric.missing_reason,
    lookback_window: metric.lookback_window || null,
    observation_count: metric.observation_count || null,
    trigger_eligibility: metric.trigger_eligibility || null
  };
}
