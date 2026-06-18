import { useMemo, useState, type CSSProperties } from "react";
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
  formatEvidenceValueText,
  getModuleLabel,
  getStatusLabel
} from "../utils/displayLabels";
import {
  blockedStatuses,
  findEvidenceRow,
  findMetric,
  groupRowsByModule,
  moduleUpdatedAt,
  usableMetric
} from "../utils/evidence";
import type { AppViewKey } from "./AppShell";
import { ModuleDetailDrawer } from "./ModuleDetailDrawer";
import { ResearchIcon, type ResearchIconName } from "./ResearchIcon";
import {
  AIContextBadge,
  BoundaryNotice,
  ErrorState,
  formatTimestamp,
  FreshnessBadge,
  LoadingState,
  MetaStrip,
  MetricValue,
  PageHeader,
  SectionHeading,
  SourceBadge,
  StatusBadge
} from "./ResearchUI";

type DashboardHomepageProps = {
  dashboard: ApiResult<DashboardSummaryResponse>;
  evidence: ApiResult<DashboardEvidenceTableResponse>;
  providerHealth: ApiResult<ProviderHealthResponse>;
  isLoading: boolean;
  onNavigate: (view: AppViewKey) => void;
};

const riskChannels: Array<{
  key: string;
  icon: ResearchIconName;
  primary: string;
  secondary: string;
}> = [
  {
    key: "credit_stress",
    icon: "shield",
    primary: "high_yield_spread",
    secondary: "investment_grade_spread"
  },
  {
    key: "rate_pressure",
    icon: "layers",
    primary: "dgs10",
    secondary: "dgs30_distance_to_5pct"
  },
  {
    key: "real_yield_pressure",
    icon: "diagnostics",
    primary: "dfii10",
    secondary: "t10yie"
  },
  {
    key: "inflation_energy_pressure",
    icon: "database",
    primary: "core_cpi_yoy",
    secondary: "core_pce_yoy"
  },
  {
    key: "equity_trend",
    icon: "dashboard",
    primary: "sp500_30d_return",
    secondary: "nasdaq100_30d_return"
  },
  {
    key: "breadth_concentration_proxy",
    icon: "evidence",
    primary: "spy_vs_rsp_30d",
    secondary: "qqq_vs_spy_30d"
  },
  {
    key: "market_stress_derived",
    icon: "scenario",
    primary: "sp500_drawdown_3m",
    secondary: "dgs10_dgs2_curve_slope"
  },
  {
    key: "portfolio_deviation",
    icon: "portfolio",
    primary: "max_deviation_pp",
    secondary: "equity_total_deviation_pp"
  }
];

const coreEvidenceKeys = riskChannels
  .filter((channel) =>
    [
      "credit_stress",
      "rate_pressure",
      "real_yield_pressure",
      "inflation_energy_pressure",
      "equity_trend",
      "market_stress_derived"
    ].includes(channel.key)
  )
  .map((channel) => channel.key);

const pressureStatuses = new Set(["watch", "pressure", "stress"]);

export function DashboardHomepage({
  dashboard,
  evidence,
  providerHealth,
  isLoading,
  onNavigate
}: DashboardHomepageProps) {
  const [selectedModuleKey, setSelectedModuleKey] = useState<string | null>(
    null
  );
  const data = dashboard.data;
  const evidenceRows = evidence.data?.rows || [];
  const rowsByModule = useMemo(
    () => groupRowsByModule(evidenceRows),
    [evidenceRows]
  );

  if (isLoading) return <LoadingState title="正在整理今日市场状态" />;
  if (dashboard.error || !data) {
    return <ErrorState title="首页证据暂不可用" message={dashboard.error} />;
  }

  const stressScoreRow = findEvidenceRow(
    evidenceRows,
    "financial_stress_composite",
    "financial_stress_score"
  );
  const stressStatusRow = findEvidenceRow(
    evidenceRows,
    "financial_stress_composite",
    "financial_stress_status"
  );
  const dominantPressureRow = findEvidenceRow(
    evidenceRows,
    "financial_stress_composite",
    "financial_stress_dominant_pressure_source"
  );
  const macroPressureRow = findEvidenceRow(
    evidenceRows,
    "macro_regime_review",
    "primary_pressure_ranking"
  );
  const stressScore =
    typeof stressScoreRow?.value === "number"
      ? Math.max(0, Math.min(100, stressScoreRow.value))
      : null;
  const marketModules = riskChannels
    .filter((channel) => channel.key !== "portfolio_deviation")
    .map((channel) => data.modules[channel.key])
    .filter((module): module is DashboardModule => Boolean(module));
  const pressureModules = marketModules.filter((module) =>
    pressureStatuses.has(module.status)
  );
  const pressureNames = pressureModules.map((module) =>
    getModuleLabel(module.key)
  );
  const dataQuality = summarizeDataQuality(evidenceRows);
  const providerStatus =
    providerHealth.data?.overall_status ||
    data.provider_health.overall_status ||
    "unknown";
  const selectedModule =
    selectedModuleKey && data.modules[selectedModuleKey]
      ? data.modules[selectedModuleKey]
      : null;

  return (
    <section className="dashboard-briefing">
      <div className="dashboard-heading-row">
        <PageHeader
          eyebrow="LOCAL MACRO RISK RESEARCH WORKBENCH · READ ONLY"
          subtitle="Local Macro Risk Briefing · Read Only"
          title="今日市场状态"
        />
        <MetaStrip
          items={[
            { label: "AS OF", value: formatTimestamp(data.generated_at) },
            {
              label: "EVIDENCE ROWS",
              value: evidence.data?.row_count ?? evidenceRows.length
            },
            { label: "MODE", value: "Local · Read only" },
            {
              label: "PROVIDER HEALTH",
              value: <StatusBadge status={providerStatus} />
            }
          ]}
        />
      </div>

      <EvidenceTemperatureBar
        score={stressScore}
        status={stressStatusRow?.status || stressScoreRow?.status || "unknown"}
        valueText={
          stressScoreRow
            ? formatEvidenceValueText(
                stressScoreRow.value_text,
                stressScoreRow.status
              )
            : "not available"
        }
      />

      <ExecutiveBrief
        dataQuality={dataQuality}
        dominantPressure={
          dominantPressureRow?.value_text || macroPressureRow?.value_text || null
        }
        pressureNames={pressureNames}
        stressStatus={stressStatusRow?.value_text || stressStatusRow?.status}
      />

      <section className="dashboard-section-stack">
        <SectionHeading
          description="八个风险通道展示金融状态、主指标、辅助指标与来源类别；点击进入模块审计抽屉。"
          index="I · RISK CHANNEL MAP"
          title="风险通道概览"
        />
        <div className="risk-channel-map">
          {riskChannels.map((channel) => {
            const module = data.modules[channel.key];
            if (!module) return null;
            return (
              <RiskChannelTile
                key={channel.key}
                channel={channel}
                module={module}
                onClick={() => setSelectedModuleKey(channel.key)}
              />
            );
          })}
        </div>
      </section>

      <section className="dashboard-section-stack">
        <SectionHeading
          description="首页只保留每个核心模块最关键的 2-3 项证据；完整来源、历史窗口与边界进入抽屉。"
          index="II · CORE EVIDENCE"
          title="核心市场证据"
        />
        <div className="compact-evidence-grid">
          {coreEvidenceKeys.map((moduleKey) => {
            const module = data.modules[moduleKey];
            if (!module) return null;
            return (
              <CompactEvidenceCard
                key={moduleKey}
                module={module}
                moduleKey={moduleKey}
                onClick={() => setSelectedModuleKey(moduleKey)}
              />
            );
          })}
        </div>
      </section>

      <section className="dashboard-section-stack">
        <SectionHeading
          description="代理、本地组合和数据质量不与核心市场证据等权，且不能单独确认系统性压力。"
          index="III · SUPPORTING CONTEXT"
          title="辅助与本地约束"
        />
        <div className="supporting-context-grid">
          <SupportingContextCard
            boundary="proxy only · not true breadth · cannot confirm systemic risk alone"
            module={data.modules.breadth_concentration_proxy}
            title="宽度 / 集中度代理"
            onClick={() => setSelectedModuleKey("breadth_concentration_proxy")}
          />
          <SupportingContextCard
            boundary="local only · does not trigger macro regime or systemic stress"
            module={data.modules.portfolio_deviation}
            title="组合偏离 / Local Portfolio Overlay"
            onClick={() => setSelectedModuleKey("portfolio_deviation")}
          />
          <DataQualityCard
            dataQuality={dataQuality}
            missingData={data.missing_data}
            totalRows={evidenceRows.length}
          />
        </div>
      </section>

      <section className="dashboard-section-stack">
        <SectionHeading
          description="专门页面承接全量审计、情景传导、历史覆盖与受控 AI 上下文。"
          index="IV · REVIEW SURFACES"
          title="复核入口"
        />
        <div className="review-surface-grid">
          <ReviewSurfaceCard
            description="筛选、搜索并追溯每一条事实、来源、新鲜度、AI 资格与解释边界。"
            icon="evidence"
            label="Evidence Audit"
            title="全量证据"
            onClick={() => onNavigate("evidence")}
          />
          <ReviewSurfaceCard
            description="查看假设冲击如何通过证据组传导；不是预测，也不输出事件概率。"
            icon="scenario"
            label="Scenario Stress Matrix"
            title="情景压力"
            onClick={() => onNavigate("scenario")}
          />
          <ReviewSurfaceCard
            description="复核历史事件窗口的证据覆盖与边界一致性；不是策略回测。"
            icon="history"
            label="Historical Validation Replay"
            title="历史验证"
            onClick={() => onNavigate("historical")}
          />
          <ReviewSurfaceCard
            description="审计哪些事实与模型输出可进入本地 AI factual context。"
            icon="ai"
            label="AI Context Preview"
            title="AI 记忆（只读）"
            onClick={() => onNavigate("ai-context")}
          />
        </div>
      </section>

      <BoundaryNotice title="研究边界">
        本页仅组织现有宏观风险证据与模型解释。证据温度不是事件概率，页面不提供交易动作、收益路径或配置指令。
      </BoundaryNotice>

      {selectedModuleKey && selectedModule && (
        <ModuleDetailDrawer
          evidenceError={evidence.error}
          evidenceRows={rowsByModule.get(selectedModuleKey) || []}
          moduleKey={selectedModuleKey}
          moduleLabel={getModuleLabel(selectedModuleKey)}
          moduleSummary={selectedModule}
          onClose={() => setSelectedModuleKey(null)}
        />
      )}
    </section>
  );
}

function EvidenceTemperatureBar({
  score,
  status,
  valueText
}: {
  score: number | null;
  status: string;
  valueText: string;
}) {
  const style =
    score === null
      ? undefined
      : ({
          "--temperature-position": `${score}%`
        } as CSSProperties);
  return (
    <section className="evidence-temperature-card">
      <header>
        <div>
          <p className="research-kicker">MARKET EVIDENCE TEMPERATURE</p>
          <h2>整体证据温度</h2>
        </div>
        <div className="temperature-reading">
          {score === null ? (
            <>
              <strong>not available</strong>
              <StatusBadge status={status} />
            </>
          ) : (
            <>
              <strong>{valueText}</strong>
              <small>压力温度</small>
            </>
          )}
        </div>
      </header>
      <div className="temperature-scale" style={style}>
        <div className="temperature-gradient" />
        {score !== null && (
          <span
            aria-label={`当前证据温度 ${score.toFixed(2)} / 100`}
            className="temperature-marker"
          />
        )}
      </div>
      <div className="temperature-labels">
        <span>低压 / 宽松</span>
        <span>中性 / 关注</span>
        <span>高压 / 承压</span>
      </div>
      <p>压力温度，不是事件概率，不是交易信号。</p>
    </section>
  );
}

function ExecutiveBrief({
  pressureNames,
  dominantPressure,
  stressStatus,
  dataQuality
}: {
  pressureNames: string[];
  dominantPressure: string | null;
  stressStatus: string | null | undefined;
  dataQuality: ReturnType<typeof summarizeDataQuality>;
}) {
  const primaryPressure = pressureNames.length
    ? pressureNames.join("、")
    : dominantPressure
      ? humanizeEvidenceText(dominantPressure)
      : "当前证据未形成明确的主要压力排序";
  const unconfirmed =
    dataQuality.blocked > 0
      ? `${dataQuality.blocked} 行证据因缺失、过期、历史不足或研究约束未进入完整判断`
      : "未发现由数据约束造成的新增阻断";
  return (
    <section className="executive-brief-card">
      <div className="executive-emblem">
        <ResearchIcon name="evidence" size={26} />
      </div>
      <div className="executive-copy">
        <p className="research-kicker">EXECUTIVE BRIEF</p>
        <h2>当前主要压力集中在：{primaryPressure}。</h2>
        <div className="executive-points">
          <article>
            <span className="point-dot point-pressure" />
            <div>
              <strong>主要压力</strong>
              <p>{primaryPressure}</p>
            </div>
          </article>
          <article>
            <span className="point-dot point-watch" />
            <div>
              <strong>未确认风险</strong>
              <p>{unconfirmed}</p>
            </div>
          </article>
          <article>
            <span className="point-dot point-quality" />
            <div>
              <strong>数据质量</strong>
              <p>
                fresh {dataQuality.fresh} · blocked {dataQuality.blocked} · AI
                allowed {dataQuality.aiAllowed}
              </p>
            </div>
          </article>
        </div>
      </div>
      <div className="executive-status">
        <span>Financial Stress</span>
        <strong>{humanizeEvidenceText(stressStatus || "not available")}</strong>
      </div>
    </section>
  );
}

function RiskChannelTile({
  channel,
  module,
  onClick
}: {
  channel: (typeof riskChannels)[number];
  module: DashboardModule;
  onClick: () => void;
}) {
  const primary = findMetric(module, channel.primary) || module.key_metrics[0];
  const secondary =
    findMetric(module, channel.secondary) ||
    module.key_metrics.find((metric) => metric.metric_key !== primary?.metric_key);
  return (
    <button className="risk-channel-tile" onClick={onClick} type="button">
      <header>
        <ResearchIcon name={channel.icon} size={21} />
        <div>
          <strong>{getModuleLabel(channel.key)}</strong>
          <small>{channel.key}</small>
        </div>
        <StatusBadge status={module.status} />
      </header>
      <div className="channel-readings">
        <ChannelReading metric={primary} />
        <ChannelReading metric={secondary} secondary />
      </div>
      <footer>
        <SourceBadge
          sourceBadge={primary?.source_badge || module.source_badge}
        />
        <ResearchIcon name="chevron" size={15} />
      </footer>
    </button>
  );
}

function ChannelReading({
  metric,
  secondary = false
}: {
  metric: DashboardMetric | undefined;
  secondary?: boolean;
}) {
  if (!metric) {
    return (
      <div className={secondary ? "channel-reading secondary" : "channel-reading"}>
        <span>not available</span>
        <strong>—</strong>
      </div>
    );
  }
  return (
    <div className={secondary ? "channel-reading secondary" : "channel-reading"}>
      <span>{metric.display_name}</span>
      <MetricValue
        status={metric.status}
        unit={metric.unit}
        valueText={metric.value_text}
      />
    </div>
  );
}

function CompactEvidenceCard({
  moduleKey,
  module,
  onClick
}: {
  moduleKey: string;
  module: DashboardModule;
  onClick: () => void;
}) {
  const metrics = compactMetrics(moduleKey, module);
  return (
    <article className="compact-evidence-card">
      <header>
        <div>
          <p className="research-kicker">{moduleKey}</p>
          <h3>{getModuleLabel(moduleKey)}</h3>
        </div>
        <StatusBadge status={module.status} />
      </header>
      {moduleKey === "rate_pressure" && <YieldCurveStrip module={module} />}
      {moduleKey === "equity_trend" && <MomentumBars metrics={metrics} />}
      {moduleKey === "market_stress_derived" && (
        <DrawdownBars metrics={metrics} />
      )}
      {!["rate_pressure", "equity_trend", "market_stress_derived"].includes(
        moduleKey
      ) && (
        <div className="compact-metric-list">
          {metrics.map((metric) => (
            <div key={metric.metric_key}>
              <span>{metric.display_name}</span>
              <MetricValue
                status={metric.status}
                unit={metric.unit}
                valueText={metric.value_text}
              />
            </div>
          ))}
        </div>
      )}
      <footer>
        <span>{formatTimestamp(moduleUpdatedAt(module))}</span>
        <button onClick={onClick} type="button">
          查看详情 <ResearchIcon name="chevron" size={14} />
        </button>
      </footer>
    </article>
  );
}

function YieldCurveStrip({ module }: { module: DashboardModule }) {
  const points = ["dgs2", "dgs10", "dgs30"]
    .map((key) => findMetric(module, key))
    .filter((metric): metric is DashboardMetric => Boolean(metric));
  return (
    <div className="yield-curve-strip">
      {points.map((metric, index) => (
        <div key={metric.metric_key}>
          <span>{["2Y", "10Y", "30Y"][index]}</span>
          <strong>
            {formatEvidenceValueText(metric.value_text, metric.status)}
          </strong>
        </div>
      ))}
    </div>
  );
}

function MomentumBars({ metrics }: { metrics: DashboardMetric[] }) {
  return (
    <div className="mini-bar-list">
      {metrics.map((metric) => (
        <div key={metric.metric_key}>
          <span>{metric.display_name}</span>
          <div className="mini-bar-track">
            <i style={{ width: `${normalizedBarWidth(metric.value)}%` }} />
          </div>
          <strong>
            {formatEvidenceValueText(metric.value_text, metric.status)}
          </strong>
        </div>
      ))}
    </div>
  );
}

function DrawdownBars({ metrics }: { metrics: DashboardMetric[] }) {
  return (
    <div className="mini-bar-list drawdown-list">
      {metrics.map((metric) => (
        <div key={metric.metric_key}>
          <span>{metric.display_name}</span>
          <div className="mini-bar-track">
            <i style={{ width: `${normalizedBarWidth(metric.value, 20)}%` }} />
          </div>
          <strong>
            {formatEvidenceValueText(metric.value_text, metric.status)}
          </strong>
        </div>
      ))}
    </div>
  );
}

function SupportingContextCard({
  title,
  boundary,
  module,
  onClick
}: {
  title: string;
  boundary: string;
  module: DashboardModule | undefined;
  onClick: () => void;
}) {
  return (
    <article className="supporting-context-card">
      <header>
        <div>
          <p className="research-kicker">SUPPORTING CONTEXT</p>
          <h3>{title}</h3>
        </div>
        {module && <StatusBadge status={module.status} />}
      </header>
      {module ? (
        <div className="compact-metric-list">
          {module.key_metrics.slice(0, 3).map((metric) => (
            <div key={metric.metric_key}>
              <span>{metric.display_name}</span>
              <MetricValue
                status={metric.status}
                unit={metric.unit}
                valueText={metric.value_text}
              />
            </div>
          ))}
        </div>
      ) : (
        <p className="not-available-copy">not available</p>
      )}
      <p className="supporting-boundary">{boundary}</p>
      <button disabled={!module} onClick={onClick} type="button">
        查看详情 <ResearchIcon name="chevron" size={14} />
      </button>
    </article>
  );
}

function DataQualityCard({
  dataQuality,
  missingData,
  totalRows
}: {
  dataQuality: ReturnType<typeof summarizeDataQuality>;
  missingData: Array<Record<string, unknown>>;
  totalRows: number;
}) {
  const usable = Math.max(0, totalRows - dataQuality.blocked);
  return (
    <article className="supporting-context-card">
      <header>
        <div>
          <p className="research-kicker">DATA QUALITY</p>
          <h3>缺失与新鲜度</h3>
        </div>
        <FreshnessBadge freshness={dataQuality.stale > 0 ? "stale" : "fresh"} />
      </header>
      <div className="quality-bar" aria-label="证据可用比例">
        <i
          style={{
            width: `${totalRows ? Math.round((usable / totalRows) * 100) : 0}%`
          }}
        />
      </div>
      <dl className="quality-stat-grid">
        <div>
          <dt>Fresh</dt>
          <dd>{dataQuality.fresh}</dd>
        </div>
        <div>
          <dt>Blocked</dt>
          <dd>{dataQuality.blocked}</dd>
        </div>
        <div>
          <dt>AI allowed</dt>
          <dd>{dataQuality.aiAllowed}</dd>
        </div>
        <div>
          <dt>Missing summary</dt>
          <dd>{missingData.length}</dd>
        </div>
      </dl>
      <p className="supporting-boundary">
        missing / stale / research_needed / insufficient_history 均保留可见。
      </p>
    </article>
  );
}

function ReviewSurfaceCard({
  label,
  title,
  description,
  icon,
  onClick
}: {
  label: string;
  title: string;
  description: string;
  icon: ResearchIconName;
  onClick: () => void;
}) {
  return (
    <button className="review-surface-card" onClick={onClick} type="button">
      <ResearchIcon name={icon} size={25} />
      <div>
        <p className="research-kicker">{label}</p>
        <h3>{title}</h3>
        <p>{description}</p>
      </div>
      <ResearchIcon name="chevron" size={17} />
    </button>
  );
}

function compactMetrics(moduleKey: string, module: DashboardModule) {
  const preferred: Record<string, string[]> = {
    credit_stress: ["high_yield_spread", "investment_grade_spread", "vix"],
    rate_pressure: ["dgs2", "dgs10", "dgs30"],
    real_yield_pressure: ["dfii10", "t10yie"],
    inflation_energy_pressure: [
      "core_cpi_yoy",
      "core_pce_yoy",
      "wti_30d_change",
      "ppi_final_demand_yoy"
    ],
    equity_trend: ["sp500_30d_return", "nasdaq100_30d_return"],
    market_stress_derived: [
      "sp500_drawdown_3m",
      "nasdaq100_drawdown_3m",
      "dgs10_dgs2_curve_slope"
    ]
  };
  const selected = (preferred[moduleKey] || [])
    .map((key) => findMetric(module, key))
    .filter((metric): metric is DashboardMetric => Boolean(metric));
  return (selected.length ? selected : module.key_metrics).slice(0, 3);
}

function summarizeDataQuality(rows: DashboardEvidenceRow[]) {
  return rows.reduce(
    (summary, row) => {
      if (row.freshness_status === "fresh") summary.fresh += 1;
      if (row.freshness_status === "stale" || row.status === "stale") {
        summary.stale += 1;
      }
      if (blockedStatuses.has(row.status)) summary.blocked += 1;
      if (row.ai_context_allowed) summary.aiAllowed += 1;
      return summary;
    },
    { fresh: 0, stale: 0, blocked: 0, aiAllowed: 0 }
  );
}

function normalizedBarWidth(value: DashboardMetric["value"], scale = 10) {
  if (typeof value !== "number") return 0;
  return Math.max(4, Math.min(100, Math.abs(value) * scale));
}

function humanizeEvidenceText(value: string) {
  return value.replace(/_/g, " ").replace(/\s+/g, " ").trim();
}
