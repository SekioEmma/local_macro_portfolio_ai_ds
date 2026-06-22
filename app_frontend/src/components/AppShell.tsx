import type { ReactNode } from "react";
import { ResearchIcon, type ResearchIconName } from "./ResearchIcon";

export type AppViewKey =
  | "dashboard"
  | "evidence"
  | "scenario"
  | "historical"
  | "ai-context"
  | "ai-chat"
  | "portfolio"
  | "diagnostics";

const navItems: Array<{
  key: AppViewKey;
  label: string;
  shortLabel: string;
  icon: ResearchIconName;
}> = [
  {
    key: "dashboard",
    label: "市场仪表盘",
    shortLabel: "仪表盘",
    icon: "dashboard"
  },
  {
    key: "evidence",
    label: "全量证据",
    shortLabel: "证据",
    icon: "evidence"
  },
  {
    key: "scenario",
    label: "情景压力",
    shortLabel: "情景",
    icon: "scenario"
  },
  {
    key: "historical",
    label: "历史验证",
    shortLabel: "历史",
    icon: "history"
  },
  {
    key: "ai-context",
    label: "AI 记忆（只读）",
    shortLabel: "AI 上下文",
    icon: "ai"
  },
  {
    key: "ai-chat",
    label: "AI 研究聊天",
    shortLabel: "AI 聊天",
    icon: "ai"
  },
  {
    key: "portfolio",
    label: "账户概览（只读）",
    shortLabel: "组合",
    icon: "portfolio"
  },
  {
    key: "diagnostics",
    label: "诊断",
    shortLabel: "诊断",
    icon: "diagnostics"
  }
];

export function AppShell({
  activeView,
  onNavigate,
  children
}: {
  activeView: AppViewKey;
  onNavigate: (view: AppViewKey) => void;
  children: ReactNode;
}) {
  return (
    <div className="paper-app-shell">
      <a className="skip-link" href="#main-content">
        跳至主要内容
      </a>
      <aside className="paper-sidebar">
        <div className="paper-brand">
          <span className="paper-brand-mark">LM</span>
          <div>
            <strong>本地宏观研究台</strong>
            <small>LOCAL MACRO WORKBENCH</small>
          </div>
        </div>

        <nav className="paper-nav" aria-label="主导航">
          {navItems.map((item) => (
            <button
              key={item.key}
              aria-current={activeView === item.key ? "page" : undefined}
              className={activeView === item.key ? "is-active" : ""}
              onClick={() => onNavigate(item.key)}
              type="button"
            >
              <ResearchIcon name={item.icon} />
              <span>{item.label}</span>
              <small>{item.shortLabel}</small>
            </button>
          ))}
        </nav>

        <footer className="paper-sidebar-footer">
          <div>
            <span className="system-dot" />
            <strong>本地只读</strong>
          </div>
          <small>默认本地 · AI 调用需主动发起</small>
        </footer>
      </aside>

      <main className="paper-main" id="main-content">
        {children}
      </main>
    </div>
  );
}
