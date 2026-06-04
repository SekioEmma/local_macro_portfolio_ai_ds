import { useEffect, useMemo, useState } from "react";
import {
  fetchDashboardSummary,
  fetchProviderHealth,
  fetchStatus
} from "./api/client";
import type {
  ApiResult,
  DashboardModule,
  DashboardSummaryResponse,
  ProviderHealthResponse,
  StatusResponse
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
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    let isMounted = true;
    Promise.all([fetchStatus(), fetchProviderHealth(), fetchDashboardSummary()])
      .then(([statusResult, providerResult, dashboardResult]) => {
        if (!isMounted) return;
        setStatus(statusResult);
        setProviderHealth(providerResult);
        setDashboard(dashboardResult);
      })
      .finally(() => {
        if (isMounted) setIsLoading(false);
      });

    return () => {
      isMounted = false;
    };
  }, []);

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand">
          <span className="brand-mark">LM</span>
          <div>
            <h1>本地宏观组合</h1>
            <p>Phase 1 只读 Web Shell</p>
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
            text="Account editing will be added in a later phase. Current Phase 1 is read-only."
          />
        )}
        {activeView === "diagnostics" && (
          <DiagnosticsView
            status={status}
            providerHealth={providerHealth}
            isLoading={isLoading}
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
          <p className="eyebrow">Local read-only dashboard</p>
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
          value={data.provider_health.overall_status || "unknown"}
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
          <pre className="json-panel">{JSON.stringify(data.data_freshness, null, 2)}</pre>
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

function DiagnosticsView({
  status,
  providerHealth,
  isLoading
}: {
  status: ApiResult<StatusResponse>;
  providerHealth: ApiResult<ProviderHealthResponse>;
  isLoading: boolean;
}) {
  if (isLoading) {
    return <LoadingState title="诊断" />;
  }

  return (
    <section className="page-stack">
      <header className="page-header">
        <div>
          <p className="eyebrow">Read-only diagnostics</p>
          <h2>诊断</h2>
        </div>
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

        <InfoPanel title="Provider Health">
          {providerHealth.error || !providerHealth.data ? (
            <p className="error-text">{providerHealth.error || "provider health 不可用。"}</p>
          ) : (
            <>
              <div className="status-row">
                <StatusPill status={providerHealth.data.overall_status} />
                <span>{JSON.stringify(providerHealth.data.summary)}</span>
              </div>
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
      </section>
    </section>
  );
}

function PlaceholderView({ title, text }: { title: string; text: string }) {
  return (
    <section className="placeholder-page">
      <p className="eyebrow">Phase 1 placeholder</p>
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
  if (status === "error") return "error";
  if (status === "degraded" || status === "stale") return "warn";
  if (status === "missing" || status === "not_run_yet") return "missing";
  return "unknown";
}

function LoadingState({ title }: { title: string }) {
  return (
    <section className="placeholder-page">
      <p className="eyebrow">Loading</p>
      <h2>{title}</h2>
      <p>正在读取本地只读 API。</p>
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
