import { useEffect, useState } from "react";
import {
  fetchDashboardEvidenceTable,
  fetchDashboardSummary,
  fetchFavorites,
  fetchProviderHealth,
  fetchRefreshRuns,
  fetchSettings,
  fetchStatus,
  fetchStorageStatus
} from "./api/client";
import { DashboardHomepage } from "./components/DashboardHomepage";
import type {
  ApiResult,
  AppSettingsResponse,
  DashboardEvidenceFilters,
  DashboardEvidenceRow,
  DashboardEvidenceTableResponse,
  DashboardSummaryResponse,
  FavoriteAnswer,
  ProviderHealthResponse,
  RefreshRun,
  StatusResponse,
  StorageStatusResponse
} from "./types";
import {
  getAiContextLabel,
  getFreshnessLabel,
  getMissingReasonLabel,
  getModuleLabel,
  getSourceBadgeLabel,
  getStatusLabel
} from "./utils/displayLabels";
import {
  aiContextClass,
  freshnessClass,
  sourceBadgeClass,
  statusClass
} from "./utils/styleClasses";

type ViewKey = "dashboard" | "evidence" | "chat" | "account" | "diagnostics";

type EvidenceFilterState = {
  module: string;
  status: string;
  sourceBadge: string;
  aiContextAllowed: string;
};

const defaultEvidenceFilters: EvidenceFilterState = {
  module: "all",
  status: "all",
  sourceBadge: "all",
  aiContextAllowed: "all"
};

const navItems: Array<{ key: ViewKey; label: string }> = [
  { key: "dashboard", label: "市场仪表盘" },
  { key: "evidence", label: "全量证据表" },
  { key: "chat", label: "AI 对话（冻结）" },
  { key: "account", label: "账户概览（只读）" },
  { key: "diagnostics", label: "诊断" }
];

export default function App() {
  const [activeView, setActiveView] = useState<ViewKey>("dashboard");
  const [status, setStatus] = useState<ApiResult<StatusResponse>>({
    data: null,
    error: null
  });
  const [providerHealth, setProviderHealth] = useState<
    ApiResult<ProviderHealthResponse>
  >({ data: null, error: null });
  const [dashboard, setDashboard] = useState<
    ApiResult<DashboardSummaryResponse>
  >({ data: null, error: null });
  const [evidence, setEvidence] = useState<
    ApiResult<DashboardEvidenceTableResponse>
  >({ data: null, error: null });
  const [filteredEvidence, setFilteredEvidence] = useState<
    ApiResult<DashboardEvidenceTableResponse>
  >({ data: null, error: null });
  const [storage, setStorage] = useState<ApiResult<StorageStatusResponse>>({
    data: null,
    error: null
  });
  const [settings, setSettings] = useState<ApiResult<AppSettingsResponse>>({
    data: null,
    error: null
  });
  const [refreshRuns, setRefreshRuns] = useState<ApiResult<RefreshRun[]>>({
    data: null,
    error: null
  });
  const [favorites, setFavorites] = useState<ApiResult<FavoriteAnswer[]>>({
    data: null,
    error: null
  });
  const [evidenceFilters, setEvidenceFilters] = useState<EvidenceFilterState>(
    defaultEvidenceFilters
  );
  const [isLoading, setIsLoading] = useState(true);

  const loadAll = (nextEvidenceFilters = evidenceFilters) => {
    setIsLoading(true);
    Promise.all([
      fetchStatus(),
      fetchProviderHealth(),
      fetchDashboardSummary(),
      fetchDashboardEvidenceTable(),
      fetchDashboardEvidenceTable(toApiEvidenceFilters(nextEvidenceFilters)),
      fetchStorageStatus(),
      fetchSettings(),
      fetchRefreshRuns(),
      fetchFavorites()
    ])
      .then(
        ([
          statusResult,
          providerResult,
          dashboardResult,
          evidenceResult,
          filteredEvidenceResult,
          storageResult,
          settingsResult,
          refreshResult,
          favoritesResult
        ]) => {
          setStatus(statusResult);
          setProviderHealth(providerResult);
          setDashboard(dashboardResult);
          setEvidence(evidenceResult);
          setFilteredEvidence(filteredEvidenceResult);
          setStorage(storageResult);
          setSettings(settingsResult);
          setRefreshRuns(refreshResult);
          setFavorites(favoritesResult);
        }
      )
      .finally(() => setIsLoading(false));
  };

  useEffect(() => {
    loadAll();
  }, []);

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand">
          <span className="brand-mark">LM</span>
          <div>
            <h1>本地宏观组合</h1>
            <p>Dashboard key metrics</p>
          </div>
        </div>
        <nav className="nav-list" aria-label="主导航">
          {navItems.map((item) => (
            <button
              key={item.key}
              className={activeView === item.key ? "nav-item active" : "nav-item"}
              type="button"
              onClick={() => setActiveView(item.key)}
            >
              {item.label}
            </button>
          ))}
        </nav>
      </aside>

      <main className="main-panel">
        {activeView === "dashboard" && (
          <DashboardHomepage
            dashboard={dashboard}
            evidence={evidence}
            providerHealth={providerHealth}
            isLoading={isLoading}
            onOpenEvidence={() => setActiveView("evidence")}
          />
        )}
        {activeView === "evidence" && (
          <EvidenceTableView
            evidence={filteredEvidence}
            filters={evidenceFilters}
            isLoading={isLoading}
            onFiltersChange={(nextFilters) => {
              setEvidenceFilters(nextFilters);
              setIsLoading(true);
              fetchDashboardEvidenceTable(toApiEvidenceFilters(nextFilters))
                .then(setFilteredEvidence)
                .finally(() => setIsLoading(false));
            }}
          />
        )}
        {activeView === "chat" && (
          <PlaceholderView
            title="AI 对话"
            text="该产品表面尚未批准并保持冻结。当前页面不发送数据、不调用 DeepSeek 或 Tavily，也不保存对话。"
          />
        )}
        {activeView === "account" && (
          <PlaceholderView
            title="账户概览"
            text="当前仅保留本地只读占位，不提供账户、持仓或目标权重编辑。"
          />
        )}
        {activeView === "diagnostics" && (
          <DiagnosticsView
            status={status}
            providerHealth={providerHealth}
            storage={storage}
            settings={settings}
            refreshRuns={refreshRuns}
            favorites={favorites}
            isLoading={isLoading}
            reload={loadAll}
          />
        )}
      </main>
    </div>
  );
}

function EvidenceTableView({
  evidence,
  filters,
  isLoading,
  onFiltersChange
}: {
  evidence: ApiResult<DashboardEvidenceTableResponse>;
  filters: EvidenceFilterState;
  isLoading: boolean;
  onFiltersChange: (filters: EvidenceFilterState) => void;
}) {
  const data = evidence.data;
  const filteredRows = data?.rows || [];

  const available = data?.filters.available || {};
  const moduleOptions = available.modules || data?.modules || [];
  const statusOptions =
    available.statuses || uniqueSorted(data?.rows.map((row) => row.status) || []);
  const sourceOptions =
    available.source_badges ||
    uniqueSorted(data?.rows.map((row) => row.source_badge) || []);

  if (isLoading) return <LoadingState title="全量证据表" />;
  if (evidence.error || !data) {
    return <ErrorState title="全量证据表" message={evidence.error} />;
  }

  return (
    <section className="page-stack">
      <header className="page-header">
        <div>
          <p className="eyebrow">Show All Data</p>
          <h2>全量证据表</h2>
          <p className="muted">
            本地只读 evidence table，用于审计 dashboard 指标来源，不是交易建议。
          </p>
        </div>
        <StatusPill status={data.overall_status} />
      </header>

      <section className="status-strip">
        <Metric label="整体状态" value={getStatusLabel(data.overall_status)} />
        <Metric label="生成时间" value={data.generated_at || "not available"} />
        <Metric label="总行数" value={String(data.row_count)} />
        <Metric label="筛选后" value={String(filteredRows.length)} />
      </section>

      <section className="filter-bar" aria-label="evidence filters">
        <FilterSelect
          label="模块"
          value={filters.module}
          options={moduleOptions}
          formatOption={getModuleLabel}
          onChange={(value) => onFiltersChange({ ...filters, module: value })}
        />
        <FilterSelect
          label="状态"
          value={filters.status}
          options={statusOptions}
          formatOption={getStatusLabel}
          onChange={(value) => onFiltersChange({ ...filters, status: value })}
        />
        <FilterSelect
          label="来源类型"
          value={filters.sourceBadge}
          options={sourceOptions}
          formatOption={getSourceBadgeLabel}
          onChange={(value) => onFiltersChange({ ...filters, sourceBadge: value })}
        />
        <label className="filter-control">
          AI 事实层
          <select
            value={filters.aiContextAllowed}
            onChange={(event) =>
              onFiltersChange({ ...filters, aiContextAllowed: event.target.value })
            }
          >
            <option value="all">全部</option>
            <option value="true">{getAiContextLabel(true)}</option>
            <option value="false">{getAiContextLabel(false)}</option>
          </select>
        </label>
      </section>

      {data.next_actions.length > 0 && (
        <InfoPanel title="Next Actions">
          <ul className="compact-list">
            {data.next_actions.map((action) => (
              <li key={action}>
                <span>{action}</span>
                <small>local command</small>
              </li>
            ))}
          </ul>
        </InfoPanel>
      )}

      <EvidenceTable rows={filteredRows} />
    </section>
  );
}

function FilterSelect({
  label,
  value,
  options,
  formatOption,
  onChange
}: {
  label: string;
  value: string;
  options: string[];
  formatOption?: (value: string) => string;
  onChange: (value: string) => void;
}) {
  return (
    <label className="filter-control">
      {label}
      <select
        value={value}
        onChange={(event) => onChange(event.target.value)}
      >
        <option value="all">全部</option>
        {options.map((option) => (
          <option key={option} value={option}>
            {formatOption ? formatOption(option) : option}
          </option>
        ))}
      </select>
    </label>
  );
}

function EvidenceTable({ rows }: { rows: DashboardEvidenceRow[] }) {
  if (rows.length === 0) {
    return (
      <section className="info-panel">
        <p className="muted">当前筛选条件下没有 evidence rows。</p>
      </section>
    );
  }

  return (
    <section className="table-panel" aria-label="dashboard evidence table">
      <div className="evidence-table-wrap">
        <table className="evidence-table">
          <thead>
            <tr>
              <th>模块</th>
              <th>metric_key</th>
              <th>名称</th>
              <th>显示值</th>
              <th>状态</th>
              <th>来源类型</th>
              <th>新鲜度</th>
              <th>观测日期</th>
              <th>生成时间</th>
              <th>AI 事实层</th>
              <th>缺失原因</th>
              <th>解释边界</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.row_id}>
                <td>
                  <span>{getModuleLabel(row.module)}</span>
                  <small className="table-subtext">{row.module}</small>
                </td>
                <td>{row.metric_key}</td>
                <td>{row.display_name}</td>
                <td className="value-cell">{row.value_text}</td>
                <td>
                  <StatusPill status={row.status} />
                </td>
                <td>
                  <SourceChip sourceBadge={row.source_badge} />
                </td>
                <td>
                  <FreshnessChip freshnessStatus={row.freshness_status} />
                </td>
                <td>{row.observation_date || "not available"}</td>
                <td>{row.generated_at || "not available"}</td>
                <td>
                  <AiContextChip row={row} />
                </td>
                <td className="long-cell" title={row.missing_reason || ""}>
                  <span className="long-cell-text">
                    {getMissingReasonLabel(row.missing_reason)}
                  </span>
                </td>
                <td className="long-cell" title={row.interpretation_hint || ""}>
                  <span className="long-cell-text">
                    {row.interpretation_hint || ""}
                  </span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function aiContextLabel(row: DashboardEvidenceRow) {
  if (row.ai_context_allowed) return getAiContextLabel(true);
  if (row.value !== null && row.value !== undefined) {
    return `有值但阻断：${row.blocked_reason || "metadata_incomplete"}`;
  }
  return `${getAiContextLabel(false)}：${row.blocked_reason || "not_eligible"}`;
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

function AiContextChip({ row }: { row: DashboardEvidenceRow }) {
  return (
    <span
      className={`data-chip ai-chip ${aiContextClass(row.ai_context_allowed)}`}
      title={row.blocked_reason || ""}
    >
      {aiContextLabel(row)}
    </span>
  );
}

function uniqueSorted(values: string[]) {
  return Array.from(new Set(values)).sort();
}

function toApiEvidenceFilters(
  filters: EvidenceFilterState
): DashboardEvidenceFilters {
  return {
    module: filters.module === "all" ? undefined : filters.module,
    status: filters.status === "all" ? undefined : filters.status,
    source_badge:
      filters.sourceBadge === "all" ? undefined : filters.sourceBadge,
    ai_context_allowed:
      filters.aiContextAllowed === "all"
        ? undefined
        : filters.aiContextAllowed === "true"
  };
}

function DiagnosticsView({
  status,
  providerHealth,
  storage,
  settings,
  refreshRuns,
  favorites,
  isLoading,
  reload
}: {
  status: ApiResult<StatusResponse>;
  providerHealth: ApiResult<ProviderHealthResponse>;
  storage: ApiResult<StorageStatusResponse>;
  settings: ApiResult<AppSettingsResponse>;
  refreshRuns: ApiResult<RefreshRun[]>;
  favorites: ApiResult<FavoriteAnswer[]>;
  isLoading: boolean;
  reload: () => void;
}) {
  if (isLoading) return <LoadingState title="诊断" />;

  return (
    <section className="page-stack">
      <header className="page-header">
        <div>
          <p className="eyebrow">Diagnostics and local app state</p>
          <h2>诊断</h2>
        </div>
        <button className="secondary-button" type="button" onClick={reload}>
          重新读取
        </button>
      </header>

      <section className="content-grid">
        <InfoPanel title="API Status">
          {status.error || !status.data ? (
            <p className="error-text">{status.error || "状态不可用。"}</p>
          ) : (
            <ul className="compact-list">
              <li>
                <span>app</span>
                <small>{status.data.app_name}</small>
              </li>
              <li>
                <span>mode</span>
                <small>{status.data.mode}</small>
              </li>
              {Object.entries(status.data.api_keys_configured).map(([key, value]) => (
                <li key={key}>
                  <span>{key}</span>
                  <small>{value ? "configured" : "missing"}</small>
                </li>
              ))}
            </ul>
          )}
        </InfoPanel>

        <InfoPanel title="Storage">
          {storage.error || !storage.data ? (
            <p className="error-text">{storage.error || "storage 不可用。"}</p>
          ) : (
            <ul className="compact-list">
              <li>
                <span>mode</span>
                <small>{storage.data.storage_mode}</small>
              </li>
              <li>
                <span>database</span>
                <small>{storage.data.database_exists ? "exists" : "missing"}</small>
              </li>
              <li>
                <span>schema</span>
                <small>{storage.data.schema_version ?? "unknown"}</small>
              </li>
            </ul>
          )}
        </InfoPanel>

        <InfoPanel title="Settings">
          {settings.error || !settings.data ? (
            <p className="error-text">{settings.error || "settings 不可用。"}</p>
          ) : (
            <RecordMap data={settings.data.settings} />
          )}
        </InfoPanel>

        <InfoPanel title="Provider Health">
          {providerHealth.error || !providerHealth.data ? (
            <p className="error-text">{providerHealth.error || "provider health 不可用。"}</p>
          ) : (
            <>
              <div className="status-row">
                <StatusPill status={providerHealth.data.overall_status} />
                <span>{providerHealthText(providerHealth.data.overall_status)}</span>
              </div>
              <ul className="compact-list">
                {providerHealth.data.checks.map((check) => (
                  <li key={check.key}>
                    <span>{check.key}</span>
                    <small>
                      {check.provider} / {getStatusLabel(check.status)}
                    </small>
                  </li>
                ))}
              </ul>
            </>
          )}
        </InfoPanel>

        <InfoPanel title="Refresh Runs">
          <RecordList items={refreshRuns.data || []} error={refreshRuns.error} />
        </InfoPanel>

        <InfoPanel title="Favorites">
          <RecordList items={favorites.data || []} error={favorites.error} />
        </InfoPanel>
      </section>
    </section>
  );
}

function providerHealthText(status: string | null | undefined) {
  if (status === "not_run_yet") return "尚未运行健康检查";
  return getStatusLabel(status || "unknown");
}

function RecordMap({ data }: { data: Record<string, unknown> }) {
  return (
    <ul className="compact-list">
      {Object.entries(data).map(([key, value]) => (
        <li key={key}>
          <span>{key}</span>
          <small>{String(value)}</small>
        </li>
      ))}
    </ul>
  );
}

function RecordList({
  items,
  error
}: {
  items: Array<{
    id: number;
    kind?: string;
    title?: string | null;
    question?: string;
    status?: string;
    created_at?: string;
  }>;
  error: string | null;
}) {
  if (error) return <p className="error-text">{error}</p>;
  if (items.length === 0) return <p className="muted">暂无记录。</p>;
  return (
    <ul className="compact-list">
      {items.slice(0, 5).map((item) => (
        <li key={String(item.id)}>
          <span>{String(item.kind || item.title || item.question || "record")}</span>
          <small>{String(item.status || item.created_at || "saved")}</small>
        </li>
      ))}
    </ul>
  );
}

function PlaceholderView({ title, text }: { title: string; text: string }) {
  return (
    <section className="placeholder-page">
      <p className="eyebrow">Phase placeholder</p>
      <h2>{title}</h2>
      <p>{text}</p>
    </section>
  );
}

function InfoPanel({
  title,
  children
}: {
  title: string;
  children: React.ReactNode;
}) {
  return (
    <section className="info-panel">
      <h3>{title}</h3>
      {children}
    </section>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="metric">
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function StatusPill({ status }: { status: string }) {
  return (
    <span className={`status-pill ${statusClass(status)}`} title={status}>
      {getStatusLabel(status)}
    </span>
  );
}

function LoadingState({ title }: { title: string }) {
  return (
    <section className="placeholder-page">
      <p className="eyebrow">Loading</p>
      <h2>{title}</h2>
      <p>正在读取本地 API。</p>
    </section>
  );
}

function ErrorState({
  title,
  message
}: {
  title: string;
  message: string | null;
}) {
  return (
    <section className="placeholder-page">
      <p className="eyebrow">Unavailable</p>
      <h2>{title}</h2>
      <p className="error-text">{message || "页面数据不可用。"}</p>
    </section>
  );
}
