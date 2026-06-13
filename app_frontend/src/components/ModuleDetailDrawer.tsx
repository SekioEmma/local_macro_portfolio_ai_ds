import type { ReactNode } from "react";
import type {
  DashboardEvidenceRow,
  DashboardMetric,
  DashboardModule
} from "../types";
import { EvidenceRowsTable } from "./EvidenceRowsTable";
import { MetricBadge } from "./MetricBadge";
import {
  formatCompactHint,
  getAiContextLabel,
  getFreshnessLabel,
  getMissingReasonLabel,
  getSourceBadgeLabel
} from "../utils/displayLabels";
import {
  aiContextClass,
  freshnessClass,
  sourceBadgeClass
} from "../utils/styleClasses";

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
    "VIX 升高不是系统性危机的充分条件；信用压力模块用于区分普通回调和信用压力，不输出交易建议。",
  rate_pressure:
    "DGS 是日度观测，不是盘中高点；5% 是解释阈值，不是交易信号；breakout 需要明确证据。",
  real_yield_pressure:
    "实际收益率是机制解释，不是黄金或成长股的单一驱动，也不是交易信号。",
  inflation_energy_pressure:
    "CPI/PCE/PPI 是低频数据；没有明确预期数据时不得写超预期；PPIACO 不是 final demand PPI；油价变化不能机械推断通胀失控。",
  equity_trend:
    "指数回撤不是系统性危机的充分条件；没有 breadth/concentration 数据不得确认市场集中恶化。",
  portfolio_deviation:
    "组合偏离不能归因于宏观市场因素；只描述风险暴露；现金备用金不参与目标配置；不输出交易指令。"
};

Object.assign(interpretationBoundaries, {
  breadth_concentration_proxy:
    "Uses ETF/index proxy relationships only. SPY/RSP/QQQ are not true constituent breadth. Proxy concentration cannot confirm mega-cap concentration without constituent weights. Do not treat proxy rows as official facts or use them alone for systemic or crash risk.",
  market_stress_derived:
    "Drawdown is an outcome, not a cause. Curve slope is macro context, not a trading signal. TLT/SHY/GLD are ETF proxies, not official macro series. VIX, drawdown, and proxy moves alone cannot confirm systemic crisis.",
  labor_macro:
    "Sahm rule proxy is a recession-warning proxy, not official recession confirmation. One-month unemployment increases do not confirm recession. Claims increases are labor-pressure observations, not crisis confirmation. Payrolls are revised; do not overstate certainty.",
  financial_stress_composite:
    "Financial stress score is a transparent pressure temperature, not crash probability. It does not produce buy/sell/hedge instructions. VIX alone and equity drawdown alone are not systemic stress. Proxy inputs are not official breadth or funding stress.",
  pullback_systemic_risk_checklist:
    "This checklist is not crash probability. It does not predict market bottom or top. It does not produce buy/sell/hedge instructions. Equity drawdown alone and VIX alone are not systemic risk. Proxy breadth is not true market breadth."
});

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
            <p className="eyebrow">查看详情</p>
            <h2>{moduleLabel}</h2>
            <p className="muted">{moduleKey}</p>
          </div>
          <button
            aria-label="关闭模块详情"
            className="icon-button"
            type="button"
            onClick={onClose}
          >
            x
          </button>
        </header>

        <div className="drawer-status-row">
          <MetricBadge status={moduleSummary.status} />
          <SourceChip sourceBadge={moduleSummary.source_badge || "missing"} />
          <span>{moduleSummary.updated_at || "更新时间不可用"}</span>
        </div>

        <DrawerSection title="状态摘要">
          <p>{moduleSummary.summary || "暂无模块摘要。"}</p>
          {moduleSummary.error_summary && (
            <p className="error-text">{moduleSummary.error_summary}</p>
          )}
          {moduleSummary.next_action && (
            <p className="next-action">{moduleSummary.next_action}</p>
          )}
        </DrawerSection>

        <DrawerSection title="关键指标">
          <div className="drawer-metric-grid">
            {moduleSummary.key_metrics.map((metric) => (
              <MetricDetail key={metric.metric_key} metric={metric} />
            ))}
          </div>
        </DrawerSection>

        <DrawerSection title="证据表">
          {evidenceError && (
            <p className="error-text">证据行不可用：{evidenceError}</p>
          )}
          <EvidenceRowsTable rows={evidenceRows} compact />
        </DrawerSection>

        <DrawerSection title="解释边界">
          <p>{interpretationBoundaries[moduleKey] || "暂无解释边界。"}</p>
        </DrawerSection>

        <DrawerSection title="缺失 / 待研究">
          {missingRows.length === 0 ? (
            <p className="muted">没有缺失、待研究、历史不足、不可用或过期的行。</p>
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
                    {getMissingReasonLabel(row.missing_reason) ||
                      formatCompactHint(row.interpretation_hint) ||
                      blockedReason(row)}
                  </p>
                </li>
              ))}
            </ul>
          )}
        </DrawerSection>

        <DrawerSection title="AI 事实层资格">
          <div className="ai-eligibility-grid">
            <div>
              <span>{getAiContextLabel(true)}</span>
              <strong>{aiAllowed.length}</strong>
            </div>
            <div>
              <span>{getAiContextLabel(false)}</span>
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
            后续阶段打开 AI Chat
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
          <dt>来源</dt>
          <dd>
            <SourceChip sourceBadge={metric.source_badge} />
          </dd>
        </div>
        <div>
          <dt>新鲜度</dt>
          <dd>
            <FreshnessChip freshnessStatus={metric.freshness_status} />
          </dd>
        </div>
        <div>
          <dt>观测</dt>
          <dd>{metric.observation_date || "not available"}</dd>
        </div>
        <div>
          <dt>AI 事实层</dt>
          <dd>
            <span
              className={`data-chip ai-chip ${aiContextClass(metric.ai_context_allowed)}`}
            >
              {getAiContextLabel(metric.ai_context_allowed)}
            </span>
          </dd>
        </div>
      </dl>
      {metadataIncomplete && (
        <p className="metric-reason">有值但元数据不足，不进入 AI 事实层。</p>
      )}
      {(metric.missing_reason || metric.interpretation_hint) && (
        <p
          className="metric-hint"
          title={metric.missing_reason || metric.interpretation_hint || ""}
        >
          {getMissingReasonLabel(metric.missing_reason) ||
            formatCompactHint(metric.interpretation_hint)}
        </p>
      )}
    </article>
  );
}

function SourceChip({ sourceBadge }: { sourceBadge: string }) {
  return (
    <span
      className={`data-chip source-chip ${sourceBadgeClass(sourceBadge)}`}
      title={sourceBadge}
    >
      {getSourceBadgeLabel(sourceBadge)}
    </span>
  );
}

function FreshnessChip({ freshnessStatus }: { freshnessStatus: string }) {
  return (
    <span
      className={`data-chip freshness-chip ${freshnessClass(freshnessStatus)}`}
      title={freshnessStatus}
    >
      {getFreshnessLabel(freshnessStatus)}
    </span>
  );
}

function summarizeBlockedReasons(rows: DashboardEvidenceRow[]) {
  return Array.from(
    new Set(rows.filter((row) => !row.ai_context_allowed).map(blockedReason))
  );
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
