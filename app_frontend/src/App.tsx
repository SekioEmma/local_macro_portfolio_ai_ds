import { useEffect, useMemo, useState } from "react";
import {
  createFavorite,
  createRefreshRun,
  fetchDashboardSummary,
  fetchFavorites,
  fetchProviderHealth,
  fetchRefreshRuns,
  fetchSettings,
  fetchStatus,
  fetchStorageStatus,
  updateSettings
} from "./api/client";
import type {
  ApiResult,
  AppSettings,
  AppSettingsResponse,
  DashboardMetric,
  DashboardModule,
  DashboardSummaryResponse,
  FavoriteAnswer,
  ProviderHealthResponse,
  RefreshRun,
  StatusResponse,
  StorageStatusResponse
} from "./types";

type ViewKey = "dashboard" | "chat" | "account" | "diagnostics";

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
          storageResult,
          settingsResult,
          refreshResult,
          favoritesResult
        ]) => {
          setStatus(statusResult);
          setProviderHealth(providerResult);
          setDashboard(dashboardResult);
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
          <DashboardView dashboard={dashboard} isLoading={isLoading} />
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
  isLoading
}: {
  dashboard: ApiResult<DashboardSummaryResponse>;
  isLoading: boolean;
}) {
  const data = dashboard.data;
  const modules = useMemo(() => {
    if (!data) return [];
    return Object.entries(data.modules);
  }, [data]);

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
          <ModuleCard key={key} moduleKey={key} module={module} />
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
    </section>
  );
}

function ModuleCard({
  moduleKey,
  module
}: {
  moduleKey: string;
  module: DashboardModule;
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
