import type {
  ApiResult,
  DashboardEvidenceRow,
  DashboardEvidenceTableResponse,
  DashboardSummaryResponse
} from "../types";
import {
  asRecord,
  compactText,
  findMetric,
  rowsForModule,
  stringList
} from "../utils/evidence";
import { ResearchIcon, type ResearchIconName } from "./ResearchIcon";
import {
  BoundaryNotice,
  EmptyState,
  ErrorState,
  formatTimestamp,
  LoadingState,
  MetaStrip,
  MetricValue,
  PageHeader,
  SourceBadge,
  StatusBadge,
  humanizeKey
} from "./ResearchUI";

const channelDefinitions: Array<{
  key: string;
  metricKey: string;
  label: string;
  icon: ResearchIconName;
}> = [
  {
    key: "equity_beta",
    metricKey: "portfolio_exposure_equity_beta_context",
    label: "权益 Beta",
    icon: "dashboard"
  },
  {
    key: "rates_duration",
    metricKey: "portfolio_exposure_rates_duration_context",
    label: "利率 Duration",
    icon: "layers"
  },
  {
    key: "credit",
    metricKey: "portfolio_exposure_credit_context",
    label: "信用 Spread",
    icon: "shield"
  },
  {
    key: "liquidity",
    metricKey: "portfolio_exposure_liquidity_context",
    label: "流动性",
    icon: "diagnostics"
  },
  {
    key: "inflation_energy",
    metricKey: "portfolio_exposure_inflation_energy_context",
    label: "通胀 / 黄金",
    icon: "scenario"
  },
  {
    key: "concentration",
    metricKey: "portfolio_exposure_concentration_context",
    label: "集中度",
    icon: "evidence"
  },
  {
    key: "valuation",
    metricKey: "portfolio_exposure_valuation_context",
    label: "估值上下文",
    icon: "database"
  },
  {
    key: "cash_buffer",
    metricKey: "portfolio_exposure_cash_buffer_context",
    label: "现金缓冲",
    icon: "portfolio"
  }
];

export function PortfolioOverlayPage({
  dashboard,
  evidence,
  isLoading
}: {
  dashboard: ApiResult<DashboardSummaryResponse>;
  evidence: ApiResult<DashboardEvidenceTableResponse>;
  isLoading: boolean;
}) {
  if (isLoading) return <LoadingState title="正在读取本地组合上下文" />;
  if (evidence.error || !evidence.data || dashboard.error || !dashboard.data) {
    return (
      <ErrorState
        title="账户概览暂不可用"
        message={evidence.error || dashboard.error}
      />
    );
  }

  const localModule = dashboard.data.modules.portfolio_deviation;
  const rows = rowsForModule(evidence.data.rows, "portfolio_exposure_overlay");
  const statusRow = findRow(rows, "portfolio_exposure_overlay_status");
  const contributions = asRecord(statusRow?.component_contributions);
  const channels = asRecord(contributions?.channels);
  const primaryChannels = stringList(
    findRow(rows, "portfolio_exposure_primary_channels")?.value
  );

  return (
    <section className="portfolio-overlay-page">
      <PageHeader
        eyebrow="LOCAL MACRO RISK RESEARCH WORKBENCH · READ ONLY"
        subtitle="Local Portfolio Overlay · Read Only"
        title="账户概览（只读）"
      />
      <MetaStrip
        items={[
          {
            label: "AS OF",
            value:
              findRow(rows, "portfolio_exposure_as_of_date")?.value_text ||
              formatTimestamp(dashboard.data.generated_at)
          },
          {
            label: "OVERLAY STATUS",
            value: <StatusBadge status={statusRow?.status || "not_available"} />
          },
          { label: "CONTEXT", value: "Local · Sanitized" },
          {
            label: "PRIMARY CHANNELS",
            value: primaryChannels.length
              ? primaryChannels.join(" / ")
              : "not available"
          }
        ]}
      />

      <BoundaryNotice title="本地只读边界" tone="local">
        Does not trigger macro regime · does not trigger systemic stress · no
        allocation advice · no trade action · no holdings line items.
      </BoundaryNotice>

      <section className="portfolio-summary-grid">
        <PortfolioSummaryCard
          label="最大偏离资产"
          metric={findMetric(localModule, "max_deviation_asset")}
        />
        <PortfolioSummaryCard
          label="最大偏离"
          metric={findMetric(localModule, "max_deviation_pp")}
        />
        <PortfolioSummaryCard
          label="权益总偏离"
          metric={findMetric(localModule, "equity_total_deviation_pp")}
        />
        <PortfolioSummaryCard
          label="现金备用金状态"
          metric={findMetric(localModule, "cash_reserve_status")}
        />
        <PortfolioSummaryCard
          label="本地上下文更新时间"
          metric={findMetric(localModule, "holdings_updated_at")}
        />
      </section>

      <section className="model-section-stack">
        <ModelSectionHeader
          description="通道只解释本地脱敏组合对宏观风险因子的粗粒度敏感性；状态缺失时不推断为低风险或高风险。"
          index="I · EXPOSURE CHANNEL MAP"
          title="风险通道暴露"
        />
        <div className="exposure-channel-grid">
          {channelDefinitions.map((definition) => (
            <ExposureChannelCard
              key={definition.key}
              definition={definition}
              row={findRow(rows, definition.metricKey)}
              structured={asRecord(channels?.[definition.key])}
            />
          ))}
        </div>
      </section>

      <section className="model-section-stack">
        <ModelSectionHeader
          description="仅显示后端公开的聚合摘要，不展示账户金额、持仓代码、单只仓位或交易记录。"
          index="II · SANITIZED LOCAL SUMMARY"
          title="本地聚合摘要"
        />
        {localModule ? (
          <div className="sanitized-summary-table-wrap">
            <table className="sanitized-summary-table">
              <thead>
                <tr>
                  <th>指标</th>
                  <th>数值</th>
                  <th>状态</th>
                  <th>来源</th>
                  <th>解释</th>
                </tr>
              </thead>
              <tbody>
                {localModule.key_metrics.map((metric) => (
                  <tr key={metric.metric_key}>
                    <td>
                      <strong>{metric.display_name}</strong>
                      <small>{metric.metric_key}</small>
                    </td>
                    <td>
                      <MetricValue
                        status={metric.status}
                        unit={metric.unit}
                        valueText={metric.value_text}
                      />
                    </td>
                    <td>
                      <StatusBadge status={metric.status} />
                    </td>
                    <td>
                      <SourceBadge sourceBadge={metric.source_badge} />
                    </td>
                    <td>
                      {metric.interpretation_hint || "仅作本地暴露解释"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <EmptyState
            description="当前 Dashboard summary 没有 portfolio_deviation 聚合模块。"
            icon="portfolio"
            title="本地组合聚合摘要不可用"
          />
        )}
      </section>

      <section className="portfolio-policy-grid">
        <PolicySummary
          data={contributions?.hard_gates}
          title="Hard Gates"
        />
        <PolicySummary
          data={
            findRow(rows, "portfolio_exposure_private_input_policy")?.value
          }
          title="Private Input Policy"
        />
        <PolicySummary
          data={
            findRow(rows, "portfolio_exposure_missing_inputs")?.value
          }
          title="Missing Inputs"
        />
      </section>
    </section>
  );
}

function PortfolioSummaryCard({
  label,
  metric
}: {
  label: string;
  metric: ReturnType<typeof findMetric>;
}) {
  return (
    <article>
      <span>{label}</span>
      {metric ? (
        <>
          <MetricValue
            status={metric.status}
            unit={metric.unit}
            valueText={metric.value_text}
          />
          <StatusBadge status={metric.status} />
        </>
      ) : (
        <strong>not available</strong>
      )}
    </article>
  );
}

function ExposureChannelCard({
  definition,
  row,
  structured
}: {
  definition: (typeof channelDefinitions)[number];
  row: DashboardEvidenceRow | undefined;
  structured: Record<string, unknown> | null;
}) {
  const status = row?.value_text || String(structured?.status || "not available");
  const evidence = stringList(
    structured?.supporting_evidence || structured?.evidence_used
  );
  return (
    <article className="exposure-channel-card">
      <header>
        <ResearchIcon name={definition.icon} size={20} />
        <div>
          <h3>{definition.label}</h3>
          <small>{definition.key}</small>
        </div>
        <StatusBadge status={row?.status || status} />
      </header>
      <strong className="exposure-reading">{humanizeKey(status)}</strong>
      {evidence.length > 0 && (
        <ul>
          {evidence.slice(0, 3).map((item) => (
            <li key={item}>{item}</li>
          ))}
        </ul>
      )}
      <p>{row?.interpretation_boundary || "Local explanatory context only."}</p>
    </article>
  );
}

function PolicySummary({ title, data }: { title: string; data: unknown }) {
  const record = asRecord(data);
  return (
    <article className="portfolio-policy-card">
      <header>
        <ResearchIcon name="shield" size={17} />
        <h3>{title}</h3>
      </header>
      {record ? (
        <dl>
          {Object.entries(record).map(([key, value]) => (
            <div key={key}>
              <dt>{humanizeKey(key)}</dt>
              <dd>{compactText(value)}</dd>
            </div>
          ))}
        </dl>
      ) : (
        <p>{compactText(data)}</p>
      )}
    </article>
  );
}

function ModelSectionHeader({
  index,
  title,
  description
}: {
  index: string;
  title: string;
  description: string;
}) {
  return (
    <header className="model-section-header">
      <div>
        <p className="research-kicker">{index}</p>
        <h2>{title}</h2>
      </div>
      <p>{description}</p>
    </header>
  );
}

function findRow(rows: DashboardEvidenceRow[], key: string) {
  return rows.find((row) => row.metric_key === key);
}
