import type {
  ApiResult,
  AppSettingsResponse,
  DashboardEvidenceTableResponse,
  DashboardSummaryResponse,
  ProviderHealthResponse,
  StatusResponse,
  StorageStatusResponse
} from "../types";
import { compactText } from "../utils/evidence";
import { ResearchIcon } from "./ResearchIcon";
import {
  BoundaryNotice,
  ErrorState,
  formatTimestamp,
  FreshnessBadge,
  LoadingState,
  MetaStrip,
  PageHeader,
  SourceBadge,
  StatusBadge,
  humanizeKey
} from "./ResearchUI";

export function DiagnosticsPage({
  status,
  providerHealth,
  dashboard,
  evidence,
  storage,
  settings,
  isLoading
}: {
  status: ApiResult<StatusResponse>;
  providerHealth: ApiResult<ProviderHealthResponse>;
  dashboard: ApiResult<DashboardSummaryResponse>;
  evidence: ApiResult<DashboardEvidenceTableResponse>;
  storage: ApiResult<StorageStatusResponse>;
  settings: ApiResult<AppSettingsResponse>;
  isLoading: boolean;
}) {
  if (isLoading) return <LoadingState title="正在读取本地诊断状态" />;
  if (status.error || !status.data) {
    return <ErrorState title="诊断暂不可用" message={status.error} />;
  }

  const provider = providerHealth.data;
  const summary = dashboard.data;
  const rows = evidence.data?.rows || [];
  const limitedRows = rows.filter(
    (row) =>
      ["missing", "research_needed", "insufficient_history", "stale"].includes(
        row.status
      ) || !row.ai_context_allowed
  );
  const freshnessFiles =
    summary?.data_freshness.files &&
    typeof summary.data_freshness.files === "object"
      ? Object.entries(
          summary.data_freshness.files as Record<
            string,
            Record<string, unknown>
          >
        )
      : [];

  return (
    <section className="diagnostics-page">
      <PageHeader
        eyebrow="LOCAL MACRO RISK RESEARCH WORKBENCH · READ ONLY"
        subtitle="数据管线、provider、新鲜度、缺失与 validator boundary 的审计台。"
        title="诊断 / Provider & Data Diagnostics"
      />
      <MetaStrip
        items={[
          { label: "APP MODE", value: status.data.mode },
          { label: "STORAGE MODE", value: status.data.storage_mode },
          {
            label: "PROVIDER HEALTH",
            value: (
              <StatusBadge
                status={provider?.overall_status || "not_run_yet"}
              />
            )
          },
          {
            label: "EVIDENCE ROWS",
            value: evidence.data?.row_count || "not available"
          },
          {
            label: "GENERATED AT",
            value: formatTimestamp(
              provider?.generated_at || summary?.generated_at
            )
          }
        ]}
      />

      <BoundaryNotice title="只读诊断">
        此页面不触发 provider fetch/write，不调用外部 AI，不显示密钥值，也不暴露完整账户或持仓数据。
      </BoundaryNotice>

      <section className="diagnostics-grid">
        <article className="diagnostic-panel diagnostic-wide">
          <PanelHeader
            icon="database"
            subtitle="Provider checks and source availability"
            title="Provider Health"
          />
          {provider ? (
            <>
              <div className="provider-overall-row">
                <StatusBadge status={provider.overall_status} />
                <span>{provider.error_summary || provider.next_action || "当前 provider 检查结果如下。"}</span>
              </div>
              <div className="provider-check-table-wrap">
                <table className="provider-check-table">
                  <thead>
                    <tr>
                      <th>Provider</th>
                      <th>Status</th>
                      <th>Source</th>
                      <th>Observation</th>
                      <th>Value present</th>
                      <th>Error</th>
                    </tr>
                  </thead>
                  <tbody>
                    {provider.checks.map((check) => (
                      <tr key={check.key}>
                        <td>
                          <strong>{check.provider}</strong>
                          <small>{check.key}</small>
                        </td>
                        <td>
                          <StatusBadge status={check.status} />
                        </td>
                        <td>{check.source || "not available"}</td>
                        <td>{check.observation_date || "not available"}</td>
                        <td>
                          {check.value_present === null
                            ? "not available"
                            : check.value_present
                              ? "yes"
                              : "no"}
                        </td>
                        <td>
                          {check.error_summary ||
                            check.error_type ||
                            "—"}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </>
          ) : (
            <p className="diagnostic-empty">
              {providerHealth.error || "Provider health 不可用。"}
            </p>
          )}
        </article>

        <article className="diagnostic-panel">
          <PanelHeader
            icon="clock"
            subtitle="Current report freshness"
            title="Data Freshness"
          />
          {freshnessFiles.length ? (
            <ul className="diagnostic-list">
              {freshnessFiles.map(([key, value]) => (
                <li key={key}>
                  <div>
                    <strong>{humanizeKey(key)}</strong>
                    <small>{compactText(value.generated_at)}</small>
                  </div>
                  <FreshnessBadge
                    freshness={String(value.status || "unknown")}
                  />
                </li>
              ))}
            </ul>
          ) : (
            <p className="diagnostic-empty">新鲜度摘要不可用。</p>
          )}
        </article>

        <article className="diagnostic-panel">
          <PanelHeader
            icon="diagnostics"
            subtitle="Missing, stale, blocked, research-needed"
            title="Missing / Research Needed"
          />
          {limitedRows.length ? (
            <ul className="diagnostic-list">
              {limitedRows.slice(0, 12).map((row) => (
                <li key={row.row_id}>
                  <div>
                    <strong>{row.display_name}</strong>
                    <small>
                      {row.module} ·{" "}
                      {row.missing_reason ||
                        row.blocked_reason ||
                        row.status}
                    </small>
                  </div>
                  <SourceBadge sourceBadge={row.source_badge} />
                </li>
              ))}
            </ul>
          ) : (
            <p className="diagnostic-empty">当前没有公开的受限证据行。</p>
          )}
        </article>

        <article className="diagnostic-panel">
          <PanelHeader
            icon="shield"
            subtitle="Privacy and product boundaries"
            title="System Boundaries"
          />
          <ul className="boundary-check-list">
            {status.data.privacy_boundaries.map((boundary) => (
              <li key={boundary}>
                <ResearchIcon name="check" size={14} />
                <span>{boundary}</span>
              </li>
            ))}
            <li>
              <ResearchIcon name="check" size={14} />
              <span>No hidden live fetch/write from this page.</span>
            </li>
            <li>
              <ResearchIcon name="check" size={14} />
              <span>No external AI or search product surface.</span>
            </li>
          </ul>
        </article>

        <article className="diagnostic-panel">
          <PanelHeader
            icon="evidence"
            subtitle="Local app-state visibility"
            title="Storage & Settings"
          />
          <dl className="diagnostic-record">
            <div>
              <dt>Database exists</dt>
              <dd>
                {storage.data
                  ? String(storage.data.database_exists)
                  : "not available"}
              </dd>
            </div>
            <div>
              <dt>Schema version</dt>
              <dd>{storage.data?.schema_version ?? "not available"}</dd>
            </div>
            <div>
              <dt>Initialized</dt>
              <dd>
                {storage.data
                  ? String(storage.data.initialized)
                  : "not available"}
              </dd>
            </div>
            {Object.entries(settings.data?.settings || {}).map(
              ([key, value]) => (
                <div key={key}>
                  <dt>{humanizeKey(key)}</dt>
                  <dd>{String(value)}</dd>
                </div>
              )
            )}
          </dl>
        </article>

        <article className="diagnostic-panel">
          <PanelHeader
            icon="layers"
            subtitle="Visible contract status only"
            title="Validation"
          />
          <ul className="boundary-check-list">
            <li>
              <ResearchIcon name="check" size={14} />
              <span>Frontend consumes current read-only response contracts.</span>
            </li>
            <li>
              <ResearchIcon name="check" size={14} />
              <span>Missing and blocked evidence stays visible.</span>
            </li>
            <li>
              <ResearchIcon name="check" size={14} />
              <span>Build/typecheck result is not fabricated in runtime UI.</span>
            </li>
          </ul>
        </article>
      </section>
    </section>
  );
}

function PanelHeader({
  title,
  subtitle,
  icon
}: {
  title: string;
  subtitle: string;
  icon:
    | "database"
    | "clock"
    | "diagnostics"
    | "shield"
    | "evidence"
    | "layers";
}) {
  return (
    <header className="diagnostic-panel-header">
      <ResearchIcon name={icon} size={18} />
      <div>
        <h2>{title}</h2>
        <p>{subtitle}</p>
      </div>
    </header>
  );
}
