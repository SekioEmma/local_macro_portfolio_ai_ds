import { useEffect, useMemo, useState } from "react";
import {
  createFavorite,
  createRefreshRun,
  fetchDashboardEvidenceTable,
  fetchDashboardSummary,
  fetchFavorites,
  fetchProviderHealth,
  fetchRefreshRuns,
  fetchSettings,
  fetchStatus,
  fetchStorageStatus,
  updateSettings
} from "./api/client";
import { ModuleDetailDrawer } from "./components/ModuleDetailDrawer";
import type {
  ApiResult,
  AppSettings,
  AppSettingsResponse,
  DashboardEvidenceRow,
  DashboardEvidenceTableResponse,
  DashboardMetric,
  DashboardModule,
  DashboardSummaryResponse,
  FavoriteAnswer,
  ProviderHealthResponse,
  RefreshRun,
  StatusResponse,
  StorageStatusResponse
} from "./types";

type ViewKey = "dashboard" | "evidence" | "chat" | "account" | "diagnostics";

const moduleLabels: Record<string, string> = {
  credit_stress: "信用压力",
  rate_pressure: "利率压力",
  real_yield_pressure: "真实收益率压力",
  inflation_energy_pressure: "通胀与能源压力",
  equity_trend: "权益趋势",
  portfolio_deviation: "组合偏离"
};

const navItems: Array<{ key: ViewKey; label: string }> = [
  { key: "dashboard", label: "市场仪表盘" },
  { key: "evidence", label: "全量证据表" },
  { key: "chat", label: "AI 对话" },
  { key: "account", label: "账户概览" },
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
  const [isLoading, setIsLoading] = useState(true);

  const loadAll = () => {
    setIsLoading(true);
    Promise.all([
      fetchStatus(),
      fetchProviderHealth(),
      fetchDashboardSummary(),
      fetchDashboardEvidenceTable(),
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
          storageResult,
          settingsResult,
          refreshResult,
          favoritesResult
        ]) => {
          setStatus(statusResult);
          setProviderHealth(providerResult);
          setDashboard(dashboardResult);
          setEvidence(evidenceResult);
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
          <DashboardView
            dashboard={dashboard}
            evidence={evidence}
            isLoading={isLoading}
          />
        )}
        {activeView === "evidence" && (
          <EvidenceTableView evidence={evidence} isLoading={isLoading} />
        )}
        {activeView === "chat" && (
          <PlaceholderView
            title="AI 对话"
            text="DeepSeek chat will be added in a later phase. This page does not send data yet."
          />
        )}
        {activeView === "account" && (
          <PlaceholderView
            title="账户概览"
            text="Account editing will be added in a later phase. Current phase remains read-only for holdings."
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
            setSettings={setSettings}
            setRefreshRuns={setRefreshRuns}
            setFavorites={setFavorites}
          />
        )}
      </main>
    </div>
  );
}

function DashboardView({
  dashboard,
  evidence,
  isLoading
}: {
  dashboard: ApiResult<DashboardSummaryResponse>;
  evidence: ApiResult<DashboardEvidenceTableResponse>;
  isLoading: boolean;
}) {
  const [selectedModuleKey, setSelectedModuleKey] = useState<string | null>(null);
  const data = dashboard.data;
  const modules = useMemo(() => {
    if (!data) return [];
    return Object.entries(data.modules);
  }, [data]);
  const selectedModule = selectedModuleKey && data
    ? data.modules[selectedModuleKey]
    : null;
  const selectedRows = evidence.data?.rows.filter(
    (row) => row.module === selectedModuleKey
  ) || [];

  if (isLoading) {
    return <LoadingState title="市场仪表盘" />;
  }

  if (dashboard.error || !data) {
    return <ErrorState title="市场仪表盘" message={dashboard.error} />;
  }

  return (
    <section className="page-stack">
      <header className="page-header">
        <div>
          <p className="eyebrow">Risk monitoring and evidence panel</p>
          <h2>今日市场状态</h2>
        </div>
        <StatusPill status={data.overall_status} />
      </header>

      <section className="status-strip">
        <Metric label="整体状态" value={data.overall_status} />
        <Metric label="风险等级" value={data.overall_risk_level || "unknown"} />
        <Metric label="更新时间" value={data.generated_at || "not available"} />
        <Metric
          label="Provider Health"
          value={providerHealthText(data.provider_health.overall_status)}
        />
      </section>

      <section className="module-grid">
        {modules.map(([key, module]) => (
          <ModuleCard
            key={key}
            moduleKey={key}
            module={module}
            onShowAll={() => setSelectedModuleKey(key)}
          />
        ))}
      </section>

      <section className="content-grid">
        <InfoPanel title="Missing Data">
          {data.missing_data.length === 0 ? (
            <p className="muted">暂无缺失数据提示。</p>
          ) : (
            <ul className="compact-list">
              {data.missing_data.map((item, index) => (
                <li key={`${String(item.key)}-${index}`}>
                  <span>{String(item.key || "unknown")}</span>
                  <small>{String(item.summary || item.status || "missing")}</small>
                </li>
              ))}
            </ul>
          )}
        </InfoPanel>

        <InfoPanel title="Data Freshness">
          <FreshnessList data={data.data_freshness} />
        </InfoPanel>
      </section>

      {selectedModuleKey && selectedModule && (
        <ModuleDetailDrawer
          moduleKey={selectedModuleKey}
          moduleLabel={moduleLabels[selectedModuleKey] || selectedModuleKey}
          moduleSummary={selectedModule}
          evidenceRows={selectedRows}
          evidenceError={evidence.error}
          onClose={() => setSelectedModuleKey(null)}
        />
      )}
    </section>
  );
}

function ModuleCard({
  moduleKey,
  module,
  onShowAll
}: {
  moduleKey: string;
  module: DashboardModule;
  onShowAll: () => void;
}) {
  return (
    <article className="module-card">
      <div className="module-card-head">
        <h3>{moduleLabels[moduleKey] || moduleKey}</h3>
        <StatusPill status={module.status} />
      </div>
      <p className="module-label">{module.label || "未标注"}</p>
      <p>{module.summary || "暂无摘要。"}</p>
      <div className="metric-list">
        {module.key_metrics.slice(0, 5).map((metric) => (
          <MetricRow key={metric.metric_key} metric={metric} />
        ))}
      </div>
      <dl>
        <div>
          <dt>Source</dt>
          <dd>{module.source_badge || "unknown"}</dd>
        </div>
        <div>
          <dt>Updated</dt>
          <dd>{module.updated_at || "not available"}</dd>
        </div>
      </dl>
      {module.error_summary && (
        <p className="error-text">{module.error_summary}</p>
      )}
      {module.next_action && <p className="next-action">{module.next_action}</p>}
      <button className="secondary-button detail-button" type="button" onClick={onShowAll}>
        Show All / 查看详情
      </button>
    </article>
  );
}

function MetricRow({ metric }: { metric: DashboardMetric }) {
  const needsExplanation = [
    "missing",
    "research_needed",
    "insufficient_history",
    "stale",
    "not_available"
  ].includes(metric.status);
  const metadataIncomplete =
    metric.value !== null &&
    metric.value !== undefined &&
    !metric.ai_context_allowed &&
    !needsExplanation;
  return (
    <div className="metric-row">
      <div>
        <strong>{metric.display_name}</strong>
        <small>
          {metric.source_badge} / {metric.freshness_status}
        </small>
      </div>
      <div className="metric-value">
        <span>{metric.value_text}</span>
        <StatusPill status={metric.status} />
      </div>
      {needsExplanation && (
        <p className="metric-reason">
          {metric.missing_reason || metric.interpretation_hint || metric.status}
        </p>
      )}
      {!needsExplanation && metric.interpretation_hint && (
        <p className="metric-hint">{metric.interpretation_hint}</p>
      )}
      {metadataIncomplete && (
        <p className="metric-reason">
          有值，但元数据不足，不进入 AI 事实层
        </p>
      )}
    </div>
  );
}

function FreshnessList({ data }: { data: Record<string, unknown> }) {
  const files = data.files;
  if (!files || typeof files !== "object") {
    return <p className="muted">freshness unavailable</p>;
  }
  return (
    <ul className="compact-list">
      {Object.entries(files as Record<string, Record<string, unknown>>).map(
        ([key, value]) => (
          <li key={key}>
            <span>{key}</span>
            <small>
              {String(value.status || "unknown")} /{" "}
              {String(value.generated_at || "not available")} / stale_cache:{" "}
              {String(Boolean(value.stale_cache))}
              {value.next_action ? ` / ${String(value.next_action)}` : ""}
            </small>
          </li>
        )
      )}
    </ul>
  );
}

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

function EvidenceTableView({
  evidence,
  isLoading
}: {
  evidence: ApiResult<DashboardEvidenceTableResponse>;
  isLoading: boolean;
}) {
  const [filters, setFilters] = useState<EvidenceFilterState>(
    defaultEvidenceFilters
  );
  const data = evidence.data;

  const filteredRows = useMemo(() => {
    if (!data) return [];
    return data.rows.filter((row) => {
      if (filters.module !== "all" && row.module !== filters.module) return false;
      if (filters.status !== "all" && row.status !== filters.status) return false;
      if (
        filters.sourceBadge !== "all" &&
        row.source_badge !== filters.sourceBadge
      ) {
        return false;
      }
      if (filters.aiContextAllowed !== "all") {
        return row.ai_context_allowed === (filters.aiContextAllowed === "true");
      }
      return true;
    });
  }, [data, filters]);

  const available = data?.filters.available || {};
  const moduleOptions = available.modules || data?.modules || [];
  const statusOptions =
    available.statuses || uniqueSorted(data?.rows.map((row) => row.status) || []);
  const sourceOptions =
    available.source_badges ||
    uniqueSorted(data?.rows.map((row) => row.source_badge) || []);

  if (isLoading) {
    return <LoadingState title="全量证据表" />;
  }

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
        <Metric label="overall_status" value={data.overall_status} />
        <Metric label="generated_at" value={data.generated_at || "not available"} />
        <Metric label="row_count" value={String(data.row_count)} />
        <Metric label="filtered_rows" value={String(filteredRows.length)} />
      </section>

      <section className="filter-bar" aria-label="evidence filters">
        <FilterSelect
          label="module"
          value={filters.module}
          options={moduleOptions}
          onChange={(value) => setFilters({ ...filters, module: value })}
        />
        <FilterSelect
          label="status"
          value={filters.status}
          options={statusOptions}
          onChange={(value) => setFilters({ ...filters, status: value })}
        />
        <FilterSelect
          label="source_badge"
          value={filters.sourceBadge}
          options={sourceOptions}
          onChange={(value) => setFilters({ ...filters, sourceBadge: value })}
        />
        <label className="filter-control">
          ai_context_allowed
          <select
            value={filters.aiContextAllowed}
            onChange={(event) =>
              setFilters({ ...filters, aiContextAllowed: event.target.value })
            }
          >
            <option value="all">all</option>
            <option value="true">可进入 AI 事实层</option>
            <option value="false">不进入 AI 事实层</option>
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
  onChange
}: {
  label: string;
  value: string;
  options: string[];
  onChange: (value: string) => void;
}) {
  return (
    <label className="filter-control">
      {label}
      <select
        value={value}
        onChange={(event) => onChange(event.target.value)}
      >
        <option value="all">all</option>
        {options.map((option) => (
          <option key={option} value={option}>
            {option}
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
        <p className="muted">当前过滤条件下没有 evidence rows。</p>
      </section>
    );
  }

  return (
    <section className="table-panel" aria-label="dashboard evidence table">
      <div className="evidence-table-wrap">
        <table className="evidence-table">
          <thead>
            <tr>
              <th>module</th>
              <th>metric_key</th>
              <th>display_name</th>
              <th>value_text</th>
              <th>status</th>
              <th>source_badge</th>
              <th>freshness_status</th>
              <th>observation_date</th>
              <th>generated_at</th>
              <th>ai_context_allowed</th>
              <th>missing_reason</th>
              <th>interpretation_hint</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.row_id}>
                <td>{row.module}</td>
                <td>{row.metric_key}</td>
                <td>{row.display_name}</td>
                <td className="value-cell">{row.value_text}</td>
                <td>
                  <StatusPill status={row.status} />
                </td>
                <td>{row.source_badge}</td>
                <td>{row.freshness_status}</td>
                <td>{row.observation_date || "not available"}</td>
                <td>{row.generated_at || "not available"}</td>
                <td>
                  {aiContextLabel(row)}
                </td>
                <td className="long-cell" title={row.missing_reason || ""}>
                  {row.missing_reason || ""}
                </td>
                <td className="long-cell" title={row.interpretation_hint || ""}>
                  {row.interpretation_hint || ""}
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
  if (row.ai_context_allowed) return "可进入 AI 事实层";
  if (row.value !== null && row.value !== undefined) {
    return "有值，但元数据不足，不进入 AI 事实层";
  }
  return "不进入 AI 事实层";
}

function uniqueSorted(values: string[]) {
  return Array.from(new Set(values)).sort();
}

function DiagnosticsView({
  status,
  providerHealth,
  storage,
  settings,
  refreshRuns,
  favorites,
  isLoading,
  reload,
  setSettings,
  setRefreshRuns,
  setFavorites
}: {
  status: ApiResult<StatusResponse>;
  providerHealth: ApiResult<ProviderHealthResponse>;
  storage: ApiResult<StorageStatusResponse>;
  settings: ApiResult<AppSettingsResponse>;
  refreshRuns: ApiResult<RefreshRun[]>;
  favorites: ApiResult<FavoriteAnswer[]>;
  isLoading: boolean;
  reload: () => void;
  setSettings: (value: ApiResult<AppSettingsResponse>) => void;
  setRefreshRuns: (value: ApiResult<RefreshRun[]>) => void;
  setFavorites: (value: ApiResult<FavoriteAnswer[]>) => void;
}) {
  if (isLoading) {
    return <LoadingState title="诊断" />;
  }

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
              <li>
                <span>initialized</span>
                <small>{storage.data.initialized ? "yes" : "no"}</small>
              </li>
            </ul>
          )}
        </InfoPanel>

        <InfoPanel title="Settings">
          {settings.error || !settings.data ? (
            <p className="error-text">{settings.error || "settings 不可用。"}</p>
          ) : (
            <SettingsForm current={settings.data.settings} onSaved={setSettings} />
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
              <p className="muted">{JSON.stringify(providerHealth.data.summary)}</p>
              <ul className="compact-list">
                {providerHealth.data.checks.map((check) => (
                  <li key={check.key}>
                    <span>{check.key}</span>
                    <small>
                      {check.provider} / {check.status}
                    </small>
                  </li>
                ))}
              </ul>
            </>
          )}
        </InfoPanel>

        <InfoPanel title="Refresh Runs">
          <button
            className="secondary-button"
            type="button"
            onClick={() => createRefreshRun().then((result) => {
              if (result.error) {
                setRefreshRuns({ data: refreshRuns.data, error: result.error });
                return;
              }
              fetchRefreshRuns().then(setRefreshRuns);
            })}
          >
            写入占位 refresh run
          </button>
          <RecordList items={refreshRuns.data || []} error={refreshRuns.error} />
        </InfoPanel>

        <InfoPanel title="Favorites">
          <button
            className="secondary-button"
            type="button"
            onClick={() => createFavorite().then((result) => {
              if (result.error) {
                setFavorites({ data: favorites.data, error: result.error });
                return;
              }
              fetchFavorites().then(setFavorites);
            })}
          >
            写入占位 favorite
          </button>
          <RecordList items={favorites.data || []} error={favorites.error} />
        </InfoPanel>
      </section>
    </section>
  );
}

function providerHealthText(status: string | null | undefined) {
  if (status === "not_run_yet") {
    return "尚未运行健康检查";
  }
  return status || "unknown";
}

function SettingsForm({
  current,
  onSaved
}: {
  current: AppSettings;
  onSaved: (value: ApiResult<AppSettingsResponse>) => void;
}) {
  const [draft, setDraft] = useState<AppSettings>({
    ui_language: current.ui_language || "zh-CN",
    default_context_mode: current.default_context_mode || "full",
    search_enabled_by_default: Boolean(current.search_enabled_by_default),
    save_chat_by_default: Boolean(current.save_chat_by_default),
    show_cost_detail: current.show_cost_detail || "details_only"
  });
  const [message, setMessage] = useState<string | null>(null);

  const save = () => {
    updateSettings(draft).then((result) => {
      onSaved(result);
      setMessage(result.error ? result.error : "设置已保存。");
    });
  };

  return (
    <div className="settings-form">
      <label>
        UI language
        <select
          value={draft.ui_language}
          onChange={(event) => setDraft({ ...draft, ui_language: event.target.value })}
        >
          <option value="zh-CN">zh-CN</option>
        </select>
      </label>
      <label>
        context mode
        <select
          value={draft.default_context_mode}
          onChange={(event) =>
            setDraft({ ...draft, default_context_mode: event.target.value })
          }
        >
          <option value="full">full</option>
          <option value="sanitized">sanitized</option>
        </select>
      </label>
      <label>
        cost detail
        <select
          value={draft.show_cost_detail}
          onChange={(event) =>
            setDraft({ ...draft, show_cost_detail: event.target.value })
          }
        >
          <option value="details_only">details_only</option>
          <option value="always">always</option>
          <option value="hidden">hidden</option>
        </select>
      </label>
      <label className="checkbox-row">
        <input
          checked={Boolean(draft.search_enabled_by_default)}
          type="checkbox"
          onChange={(event) =>
            setDraft({ ...draft, search_enabled_by_default: event.target.checked })
          }
        />
        search enabled by default
      </label>
      <label className="checkbox-row">
        <input
          checked={Boolean(draft.save_chat_by_default)}
          type="checkbox"
          onChange={(event) =>
            setDraft({ ...draft, save_chat_by_default: event.target.checked })
          }
        />
        save chat by default
      </label>
      <button className="secondary-button" type="button" onClick={save}>
        保存设置
      </button>
      {message && <p className="muted">{message}</p>}
    </div>
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
  if (error) {
    return <p className="error-text">{error}</p>;
  }
  if (items.length === 0) {
    return <p className="muted">暂无记录。</p>;
  }
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
  return <span className={`status-pill ${statusClass(status)}`}>{status}</span>;
}

function statusClass(status: string) {
  if (status === "ok") return "ok";
  if (status === "stress" || status === "error") return "error";
  if (["watch", "pressure", "degraded", "stale"].includes(status)) return "warn";
  if (
    ["missing", "not_run_yet", "research_needed", "insufficient_history", "not_available"].includes(
      status
    )
  ) {
    return "missing";
  }
  return "unknown";
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
