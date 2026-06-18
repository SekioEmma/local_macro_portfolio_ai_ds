import { useMemo, useState } from "react";
import type {
  ApiResult,
  DashboardEvidenceRow,
  DashboardEvidenceTableResponse,
  DashboardMetric,
  DashboardModule,
  DashboardSummaryResponse,
  ProviderHealthResponse
} from "../types";
import {
  formatCompactHint,
  formatEvidenceValueText,
  getAiContextLabel,
  getFreshnessLabel,
  getMissingReasonLabel,
  getModuleLabel,
  getSourceBadgeLabel,
  getStatusLabel
} from "../utils/displayLabels";
import { getModuleBoundary } from "../utils/moduleRegistry";
import {
  aiContextClass,
  freshnessClass,
  sourceBadgeClass,
  statusClass
} from "../utils/styleClasses";
import { ModuleDetailDrawer } from "./ModuleDetailDrawer";

type DashboardHomepageProps = {
  dashboard: ApiResult<DashboardSummaryResponse>;
  evidence: ApiResult<DashboardEvidenceTableResponse>;
  providerHealth: ApiResult<ProviderHealthResponse>;
  isLoading: boolean;
  onOpenEvidence: () => void;
};

type DataQualityStatus =
  | "fresh"
  | "historical"
  | "normal_lag"
  | "stale"
  | "missing"
  | "research_needed"
  | "insufficient_history"
  | "not_available"
  | "unknown";

const primaryMarketModuleKeys = [
  "credit_stress",
  "rate_pressure",
  "real_yield_pressure",
  "inflation_energy_pressure",
  "equity_trend",
  "market_stress_derived"
] as const;

const supportingModuleKeys = [
  "breadth_concentration_proxy",
  "portfolio_deviation"
] as const;

const marketModuleKeys = new Set<string>([
  ...primaryMarketModuleKeys,
  "breadth_concentration_proxy"
]);

const pressureStatuses = new Set(["watch", "pressure", "stress"]);
const blockedMetricStatuses = new Set([
  "missing",
  "research_needed",
  "insufficient_history",
  "not_available",
  "stale"
]);

const moduleDescriptions: Record<string, string> = {
  credit_stress: "信用利差与波动率证据，用于观察信用环境是否出现压力。",
  rate_pressure: "国债收益率与曲线证据；DGS 为日度观测，不是盘中行情。",
  real_yield_pressure: "实际收益率与通胀预期机制，用于解释估值与机会成本压力。",
  inflation_energy_pressure: "通胀与能源输入的低频证据，不用于生成方向预测。",
  equity_trend: "指数趋势与相对表现证据；回撤本身不能确认系统性风险。",
  breadth_concentration_proxy:
    "ETF 与指数关系形成的代理观察，不等同于真实成分股广度。",
  market_stress_derived:
    "基于历史窗口的回撤、曲线与跨资产派生证据，不是交易信号。",
  portfolio_deviation:
    "本地组合相对目标权重的紧凑偏离摘要，只用于风险暴露解释。"
};

const pressureLabels: Record<string, string> = {
  credit_stress: "信用",
  rate_pressure: "利率",
  real_yield_pressure: "实际收益率",
  inflation_energy_pressure: "通胀与能源",
  equity_trend: "权益趋势",
  breadth_concentration_proxy: "宽度代理",
  market_stress_derived: "市场压力派生"
};

export function DashboardHomepage({
  dashboard,
  evidence,
  providerHealth,
  isLoading,
  onOpenEvidence
}: DashboardHomepageProps) {
  const [selectedModuleKey, setSelectedModuleKey] = useState<string | null>(null);
  const data = dashboard.data;
  const evidenceRows = evidence.data?.rows || [];

  const rowsByModule = useMemo(() => {
    const grouped = new Map<string, DashboardEvidenceRow[]>();
    for (const row of evidenceRows) {
      const rows = grouped.get(row.module) || [];
      rows.push(row);
      grouped.set(row.module, rows);
    }
    return grouped;
  }, [evidenceRows]);

  if (isLoading) {
    return <PaperLoadingState />;
  }
  if (dashboard.error || !data) {
    return <PaperErrorState message={dashboard.error} />;
  }

  const selectedModule =
    selectedModuleKey && data.modules[selectedModuleKey]
      ? data.modules[selectedModuleKey]
      : null;
  const selectedRows = selectedModuleKey
    ? rowsByModule.get(selectedModuleKey) || []
    : [];
  const marketModules = Object.entries(data.modules).filter(([key]) =>
    marketModuleKeys.has(key)
  );
  const usableMarketModuleCount = marketModules.filter(
    ([, module]) => !blockedMetricStatuses.has(module.status)
  ).length;
  const pressureModules = marketModules.filter(([, module]) =>
    pressureStatuses.has(module.status)
  );
  const macroRegimeRows = rowsByModule.get("macro_regime_review") || [];
  const macroPressureRanking = evidenceValue(
    macroRegimeRows,
    "primary_pressure_ranking"
  );
  const pressureSummary = pressureModules.length
    ? pressureModules
        .map(([key]) => pressureLabels[key] || getModuleLabel(key))
        .join(" / ")
    : macroPressureRanking
      ? formatEvidenceEnum(macroPressureRanking)
      : null;
  const quality = summarizeDataQuality(evidenceRows);

  return (
    <section className="paper-dashboard">
      <header className="paper-report-header">
        <div>
          <p className="paper-kicker">LOCAL MACRO RISK BRIEFING · READ ONLY</p>
          <h2>今日市场状态</h2>
          <p className="paper-subtitle">
            Risk Monitoring and Evidence Panel
          </p>
        </div>
        <dl className="report-meta">
          <div>
            <dt>AS OF</dt>
            <dd>{formatTimestamp(data.generated_at)}</dd>
          </div>
          <div>
            <dt>EVIDENCE ROWS</dt>
            <dd>{evidence.data?.row_count ?? evidenceRows.length}</dd>
          </div>
          <div>
            <dt>MODE</dt>
            <dd>Local · Read only</dd>
          </div>
        </dl>
      </header>

      <section className="overview-strip" aria-label="首页证据总览">
        <OverviewBlock
          index="01"
          label="Market Evidence Status"
          value={usableMarketModuleCount > 0 ? "证据可用" : "输入不足"}
          note={`${usableMarketModuleCount}/${marketModules.length} 个市场模块可供复核；组合偏离不计入市场证据状态。`}
          tone={usableMarketModuleCount > 0 ? "ink" : "muted"}
        />
        <MacroRegimeOverview rows={macroRegimeRows} />
        <OverviewBlock
          index="03"
          label="Main Pressure Sources"
          value={pressureSummary || "暂无确认的市场压力"}
          note={
            pressureSummary
              ? "来自市场证据模块状态；本地组合偏离单独展示。"
              : "No confirmed market stress from available evidence."
          }
          tone={pressureSummary ? "pressure" : "ok"}
        />
        <DataQualityOverview quality={quality} />
        <OverviewBlock
          index="05"
          label="Provider Health"
          value={providerHealthLabel(
            providerHealth.data?.overall_status ||
              data.provider_health.overall_status
          )}
          note={
            providerHealth.data?.error_summary ||
            data.provider_health.error_summary ||
            "数据管线状态，不代表市场风险状态。"
          }
          tone="muted"
        />
      </section>

      <section className="pressure-summary" aria-label="当前证据摘要">
        <div>
          <p className="section-index">CURRENT EVIDENCE</p>
          <h3>
            {pressureSummary
              ? `主要市场压力集中在：${pressureSummary.split(" / ").join("、")}`
              : "当前可用证据未确认显著市场压力"}
          </h3>
        </div>
        <p>
          Financial Stress Composite 是压力温度；Pullback/Systemic Risk 是当前证据复核。
          VIX、回撤或代理证据不能单独确认系统性压力。
        </p>
      </section>

      <DashboardSection
        eyebrow="I · CORE MARKET EVIDENCE"
        title="核心市场证据"
        description="先看信用、利率、实际收益率、通胀能源、权益趋势与市场压力派生。"
      >
        <div className="paper-module-grid">
          {primaryMarketModuleKeys.map((moduleKey) => {
            const module = data.modules[moduleKey];
            if (!module) return null;
            return (
              <EvidenceModuleCard
                key={moduleKey}
                moduleKey={moduleKey}
                module={module}
                onShowAll={() => setSelectedModuleKey(moduleKey)}
              />
            );
          })}
        </div>
      </DashboardSection>

      <DashboardSection
        eyebrow="II · SUPPORTING CONTEXT"
        title="辅助证据与本地约束"
        description="代理宽度只能辅助观察；组合偏离只改变风险暴露解释，不触发市场状态。"
      >
        <div className="supporting-grid">
          {supportingModuleKeys.map((moduleKey) => {
            const module = data.modules[moduleKey];
            if (!module) return null;
            return (
              <EvidenceModuleCard
                key={moduleKey}
                moduleKey={moduleKey}
                module={module}
                variant={
                  moduleKey === "portfolio_deviation" ? "portfolio" : "proxy"
                }
                onShowAll={() => setSelectedModuleKey(moduleKey)}
              />
            );
          })}
          <MissingDataPanel items={data.missing_data} />
          <FreshnessPanel data={data.data_freshness} />
        </div>
      </DashboardSection>

      <DashboardSection
        eyebrow="III · SYSTEM & REVIEW SURFACES"
        title="系统状态与复核入口"
        description="只有已有页面可以进入；未完成或冻结表面保持明确禁用。"
      >
        <div className="system-review-grid">
          <ProviderHealthPanel
            providerHealth={providerHealth}
            fallback={data.provider_health}
          />
          <ReviewEntry
            title="全量证据表"
            description="按模块、状态、来源与 AI 事实层资格审计所有证据行。"
            actionLabel="打开 Evidence Table"
            onClick={onOpenEvidence}
          />
          <ReviewEntry
            title="Scenario Stress Matrix"
            description="情景是压力传导复核，不代表发生概率、收益路径或交易动作。"
            actionLabel="专用页面未开放"
            disabled
          />
          <ReviewEntry
            title="Historical Validation Replay"
            description="历史复核不是回测，也不用于评价预测能力或交易表现。"
            actionLabel="专用页面未开放"
            disabled
          />
          <ReviewEntry
            title="AI Context Preview"
            description="仅预览事实进入与阻断边界；不调用外部模型，不保存对话。"
            actionLabel="专用页面未开放"
            disabled
          />
        </div>
      </DashboardSection>

      {data.next_actions.length > 0 && (
        <section className="paper-note" aria-label="本地后续动作">
          <div>
            <p className="section-index">LOCAL NEXT ACTIONS</p>
            <h3>数据底座提示</h3>
          </div>
          <ul>
            {data.next_actions.map((action) => (
              <li key={action}>{action}</li>
            ))}
          </ul>
        </section>
      )}

      {selectedModuleKey && selectedModule && (
        <ModuleDetailDrawer
          moduleKey={selectedModuleKey}
          moduleLabel={getModuleLabel(selectedModuleKey)}
          moduleSummary={selectedModule}
          evidenceRows={selectedRows}
          evidenceError={evidence.error}
          onClose={() => setSelectedModuleKey(null)}
        />
      )}
    </section>
  );
}

function DashboardSection({
  eyebrow,
  title,
  description,
  children
}: {
  eyebrow: string;
  title: string;
  description: string;
  children: React.ReactNode;
}) {
  return (
    <section className="dashboard-section">
      <header className="section-heading">
        <div>
          <p className="section-index">{eyebrow}</p>
          <h3>{title}</h3>
        </div>
        <p>{description}</p>
      </header>
      {children}
    </section>
  );
}

function OverviewBlock({
  index,
  label,
  value,
  note,
  tone
}: {
  index: string;
  label: string;
  value: string;
  note: string;
  tone: "ink" | "ok" | "pressure" | "muted";
}) {
  return (
    <article className={`overview-block overview-${tone}`}>
      <div className="overview-label">
        <span>{index}</span>
        <p>{label}</p>
      </div>
      <strong>{value}</strong>
      <small>{note}</small>
    </article>
  );
}

function MacroRegimeOverview({ rows }: { rows: DashboardEvidenceRow[] }) {
  const label = evidenceValue(rows, "macro_regime_label");
  const support = evidenceValue(rows, "support_band");
  const quality = evidenceValue(rows, "evidence_quality_band");
  const conflict = evidenceValue(rows, "conflict_band");
  const ranking = evidenceValue(rows, "primary_pressure_ranking");
  const available = label !== null;

  return (
    <article className="overview-block overview-regime">
      <div className="overview-label">
        <span>02</span>
        <p>Macro Regime Review</p>
      </div>
      <strong>{available && label ? formatEvidenceEnum(label) : "未生成"}</strong>
      <small>
        {available
          ? `支持 ${formatEvidenceEnum(support || "未标注")} · 质量 ${formatEvidenceEnum(
              quality || "未标注"
            )} · 冲突 ${formatEvidenceEnum(conflict || "未标注")}${
              ranking ? ` · 压力 ${formatEvidenceEnum(ranking)}` : ""
            } · 当前证据复核`
          : "Dashboard modules available; regime summary not generated."}
      </small>
    </article>
  );
}

function DataQualityOverview({
  quality
}: {
  quality: ReturnType<typeof summarizeDataQuality>;
}) {
  const value =
    quality.stale + quality.missing + quality.researchNeeded > 0
      ? "存在数据约束"
      : "数据状态可用";
  return (
    <article className="overview-block overview-quality">
      <div className="overview-label">
        <span>04</span>
        <p>Data Quality</p>
      </div>
      <strong>{value}</strong>
      <ul className="quality-inline-list">
        <li>fresh {quality.fresh}</li>
        <li>stale {quality.stale}</li>
        <li>missing {quality.missing}</li>
        <li>research {quality.researchNeeded}</li>
        <li>history {quality.insufficientHistory}</li>
      </ul>
    </article>
  );
}

function EvidenceModuleCard({
  moduleKey,
  module,
  variant = "market",
  onShowAll
}: {
  moduleKey: string;
  module: DashboardModule;
  variant?: "market" | "proxy" | "portfolio";
  onShowAll: () => void;
}) {
  const dataStatus = moduleDataStatus(module.key_metrics);
  const sourceBadges = Array.from(
    new Set(
      [
        module.source_badge,
        ...module.key_metrics.map((metric) => metric.source_badge)
      ].filter((value): value is string => Boolean(value))
    )
  );

  return (
    <article className={`evidence-module-card module-${variant}`}>
      <header className="evidence-module-header">
        <div>
          <p className="module-key">{moduleKey}</p>
          <h4>
            {moduleKey === "portfolio_deviation"
              ? "组合偏离 / Local Portfolio Overlay"
              : getModuleLabel(moduleKey)}
          </h4>
        </div>
        <span className="module-number">
          {String(
            [...primaryMarketModuleKeys, ...supportingModuleKeys].indexOf(
              moduleKey as (typeof primaryMarketModuleKeys)[number]
            ) + 1
          ).padStart(2, "0")}
        </span>
      </header>

      <p className="module-explanation">
        {moduleDescriptions[moduleKey] || module.summary || "当前证据模块。"}
      </p>

      <div className="dual-status-row">
        <LabeledBadge
          label="金融状态"
          value={getStatusLabel(module.status)}
          className={statusClass(module.status)}
        />
        <LabeledBadge
          label="数据状态"
          value={dataQualityLabel(dataStatus)}
          className={dataQualityClass(dataStatus)}
        />
      </div>

      {variant === "proxy" && (
        <BoundaryCallout>
          仅为 proxy breadth / concentration observation，不等同于真实市场广度，
          不能单独确认系统性风险。
        </BoundaryCallout>
      )}
      {variant === "portfolio" && (
        <BoundaryCallout>
          Local context only · 不触发宏观状态 · 不触发系统性压力 · 不构成配置建议。
        </BoundaryCallout>
      )}

      <div className="paper-metric-list">
        {module.key_metrics.slice(0, 5).map((metric) => (
          <MetricPaperRow key={metric.metric_key} metric={metric} />
        ))}
      </div>

      <footer className="evidence-module-footer">
        <div>
          <span className="footer-label">SOURCE SUMMARY</span>
          <span className="source-summary">
            {sourceBadges.slice(0, 4).map((sourceBadge) => (
              <SourceBadge key={sourceBadge} sourceBadge={sourceBadge} />
            ))}
          </span>
        </div>
        <div>
          <span className="footer-label">UPDATED</span>
          <strong>{formatTimestamp(moduleUpdatedAt(module))}</strong>
        </div>
        <button
          className="paper-button"
          type="button"
          onClick={onShowAll}
          aria-label={`查看${getModuleLabel(moduleKey)}详情`}
        >
          查看详情
        </button>
      </footer>

      {(module.error_summary || module.next_action) && (
        <div className="module-system-note">
          {module.error_summary && <p>{module.error_summary}</p>}
          {module.next_action && <p>{module.next_action}</p>}
        </div>
      )}
    </article>
  );
}

function MetricPaperRow({ metric }: { metric: DashboardMetric }) {
  const needsExplanation = blockedMetricStatuses.has(metric.status);
  const explanation =
    getMissingReasonLabel(metric.missing_reason) ||
    formatCompactHint(metric.interpretation_hint) ||
    (needsExplanation ? getStatusLabel(metric.status) : "");

  return (
    <article className="paper-metric-row">
      <div className="metric-paper-heading">
        <div>
          <strong>{metric.display_name}</strong>
          <small>{metric.metric_key}</small>
        </div>
        <span className={`status-stamp ${statusClass(metric.status)}`}>
          {getStatusLabel(metric.status)}
        </span>
      </div>
      <div className="metric-reading">
        <span>{formatEvidenceValueText(metric.value_text, metric.status)}</span>
        {metric.unit && <small>{metric.unit}</small>}
      </div>
      <div className="metric-metadata">
        <SourceBadge sourceBadge={metric.source_badge} />
        <span
          className={`data-chip freshness-chip ${freshnessClass(
            metric.freshness_status
          )}`}
        >
          {getFreshnessLabel(metric.freshness_status)}
        </span>
        {metric.ai_context_tier === "model_output" && (
          <span className="data-chip source-chip source-model-output">
            模型输出
          </span>
        )}
        <span
          className={`data-chip ai-chip ${aiContextClass(
            metric.ai_context_allowed
          )}`}
        >
          {getAiContextLabel(metric.ai_context_allowed)}
        </span>
      </div>
      <div className="metric-paper-foot">
        <span>{metric.observation_date || "观测日期不可用"}</span>
        {metric.source_series && <span>{metric.source_series}</span>}
      </div>
      {explanation && (
        <p className="metric-interpretation" title={metric.interpretation_hint || ""}>
          {explanation}
        </p>
      )}
    </article>
  );
}

function LabeledBadge({
  label,
  value,
  className
}: {
  label: string;
  value: string;
  className: string;
}) {
  return (
    <div className="labeled-badge">
      <span>{label}</span>
      <strong className={`status-stamp ${className}`}>{value}</strong>
    </div>
  );
}

function SourceBadge({ sourceBadge }: { sourceBadge: string }) {
  return (
    <span
      className={`data-chip source-chip ${sourceBadgeClass(sourceBadge)}`}
      title={sourceBadge}
    >
      {getSourceBadgeLabel(sourceBadge)}
    </span>
  );
}

function BoundaryCallout({ children }: { children: React.ReactNode }) {
  return <p className="boundary-callout">{children}</p>;
}

function MissingDataPanel({
  items
}: {
  items: Array<Record<string, unknown>>;
}) {
  return (
    <article className="paper-context-panel">
      <header>
        <p className="section-index">MISSING DATA</p>
        <h4>缺失与输入约束</h4>
      </header>
      {items.length === 0 ? (
        <p className="panel-empty">当前 dashboard 未报告缺失数据。</p>
      ) : (
        <ul className="paper-list">
          {items.slice(0, 6).map((item, index) => (
            <li key={`${String(item.key || "missing")}-${index}`}>
              <strong>{String(item.key || "unknown")}</strong>
              <span>{String(item.summary || item.status || "missing")}</span>
            </li>
          ))}
        </ul>
      )}
    </article>
  );
}

function FreshnessPanel({ data }: { data: Record<string, unknown> }) {
  const files =
    data.files && typeof data.files === "object"
      ? Object.entries(data.files as Record<string, Record<string, unknown>>)
      : [];
  return (
    <article className="paper-context-panel">
      <header>
        <p className="section-index">DATA FRESHNESS</p>
        <h4>数据新鲜度</h4>
      </header>
      {files.length === 0 ? (
        <p className="panel-empty">新鲜度摘要不可用。</p>
      ) : (
        <ul className="paper-list">
          {files.slice(0, 6).map(([key, value]) => (
            <li key={key}>
              <strong>{key}</strong>
              <span>
                {getStatusLabel(String(value.status || "unknown"))} ·{" "}
                {formatTimestamp(String(value.generated_at || ""))}
              </span>
            </li>
          ))}
        </ul>
      )}
    </article>
  );
}

function ProviderHealthPanel({
  providerHealth,
  fallback
}: {
  providerHealth: ApiResult<ProviderHealthResponse>;
  fallback: DashboardSummaryResponse["provider_health"];
}) {
  const data = providerHealth.data;
  const status = data?.overall_status || fallback.overall_status || "unknown";
  return (
    <article className="paper-context-panel provider-panel">
      <header>
        <div>
          <p className="section-index">PROVIDER HEALTH</p>
          <h4>数据管线状态</h4>
        </div>
        <span className={`status-stamp ${statusClass(status)}`}>
          {providerHealthLabel(status)}
        </span>
      </header>
      <p className="provider-boundary">Provider 状态不代表市场风险状态。</p>
      {data?.checks && data.checks.length > 0 ? (
        <ul className="paper-list compact-provider-list">
          {data.checks.slice(0, 5).map((check) => (
            <li key={check.key}>
              <strong>{check.provider}</strong>
              <span>
                {getStatusLabel(check.status)}
                {check.observation_date ? ` · ${check.observation_date}` : ""}
              </span>
            </li>
          ))}
        </ul>
      ) : (
        <p className="panel-empty">
          {data?.error_summary ||
            fallback.error_summary ||
            "尚无 provider 检查明细。"}
        </p>
      )}
    </article>
  );
}

function ReviewEntry({
  title,
  description,
  actionLabel,
  disabled = false,
  onClick
}: {
  title: string;
  description: string;
  actionLabel: string;
  disabled?: boolean;
  onClick?: () => void;
}) {
  return (
    <article className={`review-entry ${disabled ? "is-disabled" : ""}`}>
      <div>
        <p className="section-index">REVIEW SURFACE</p>
        <h4>{title}</h4>
        <p>{description}</p>
      </div>
      <button
        className="paper-button"
        type="button"
        disabled={disabled}
        onClick={onClick}
      >
        {actionLabel}
      </button>
    </article>
  );
}

function PaperLoadingState() {
  return (
    <section className="paper-state" aria-live="polite">
      <p className="paper-kicker">LOCAL MACRO RISK BRIEFING</p>
      <h2>正在整理今日证据</h2>
      <p>读取本地 Dashboard 与 Evidence Table，不调用外部服务。</p>
      <div className="paper-loading-rule" />
    </section>
  );
}

function PaperErrorState({ message }: { message: string | null }) {
  return (
    <section className="paper-state" role="alert">
      <p className="paper-kicker">DASHBOARD UNAVAILABLE</p>
      <h2>首页证据暂不可用</h2>
      <p>{message || "请确认本地后端已启动。"}</p>
    </section>
  );
}

function evidenceValue(rows: DashboardEvidenceRow[], metricKey: string) {
  const row = rows.find((candidate) => candidate.metric_key === metricKey);
  if (!row || blockedMetricStatuses.has(row.status)) return null;
  return formatEvidenceValueText(row.value_text, row.status);
}

function summarizeDataQuality(rows: DashboardEvidenceRow[]) {
  return rows.reduce(
    (summary, row) => {
      if (row.freshness_status === "fresh") summary.fresh += 1;
      if (row.freshness_status === "stale" || row.status === "stale") {
        summary.stale += 1;
      }
      if (row.status === "missing") summary.missing += 1;
      if (row.status === "research_needed") summary.researchNeeded += 1;
      if (row.status === "insufficient_history") {
        summary.insufficientHistory += 1;
      }
      return summary;
    },
    {
      fresh: 0,
      stale: 0,
      missing: 0,
      researchNeeded: 0,
      insufficientHistory: 0
    }
  );
}

function moduleDataStatus(metrics: DashboardMetric[]): DataQualityStatus {
  if (metrics.length === 0) return "unknown";
  if (
    metrics.some(
      (metric) =>
        metric.status === "stale" || metric.freshness_status === "stale"
    )
  ) {
    return "stale";
  }
  if (metrics.some((metric) => metric.status === "missing")) return "missing";
  if (metrics.some((metric) => metric.status === "research_needed")) {
    return "research_needed";
  }
  if (metrics.some((metric) => metric.status === "insufficient_history")) {
    return "insufficient_history";
  }
  if (metrics.some((metric) => metric.status === "not_available")) {
    return "not_available";
  }
  if (metrics.every((metric) => metric.freshness_status === "historical")) {
    return "historical";
  }
  if (metrics.some((metric) => metric.freshness_status === "normal_lag")) {
    return "normal_lag";
  }
  if (metrics.some((metric) => metric.freshness_status === "fresh")) {
    return "fresh";
  }
  return "unknown";
}

function dataQualityLabel(status: DataQualityStatus) {
  if (status === "research_needed") return "需研究数据源";
  if (status === "not_available") return "不可用";
  if (["fresh", "historical", "normal_lag"].includes(status)) {
    return getFreshnessLabel(status);
  }
  return getStatusLabel(status);
}

function dataQualityClass(status: DataQualityStatus) {
  if (["fresh", "historical", "normal_lag"].includes(status)) {
    return freshnessClass(status);
  }
  return statusClass(status);
}

function providerHealthLabel(status: string | null | undefined) {
  if (status === "not_run_yet") return "尚未运行";
  return getStatusLabel(status || "unknown");
}

function formatTimestamp(value: string | null | undefined) {
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

function moduleUpdatedAt(module: DashboardModule) {
  if (module.updated_at) return module.updated_at;
  return (
    module.key_metrics.find((metric) => metric.generated_at)?.generated_at ||
    module.key_metrics.find((metric) => metric.observation_date)
      ?.observation_date ||
    null
  );
}

function formatEvidenceEnum(value: string) {
  const normalized = value.trim();
  const labels: Record<string, string> = {
    rates_pressure: "利率压力",
    real_yield_pressure: "实际收益率压力",
    rates_real_yield: "利率 / 实际收益率",
    credit_pressure: "信用压力",
    inflation_pressure: "通胀压力",
    equity_pressure: "权益压力",
    mixed_pressure: "混合压力",
    high: "高",
    moderate: "中等",
    medium: "中等",
    low: "低",
    limited: "有限",
    balanced: "均衡",
    benign: "温和"
  };
  return labels[normalized] || normalized.split("_").join(" ");
}
