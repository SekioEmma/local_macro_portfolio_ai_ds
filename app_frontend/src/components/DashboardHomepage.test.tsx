import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { DashboardHomepage } from "./DashboardHomepage";
import type {
  DashboardEvidenceTableResponse,
  DashboardSummaryResponse,
  ProviderHealthResponse
} from "../types";

/**
 * Minimal valid response fixtures. These don't have to look like real
 * dashboard data — only enough shape that the component can render without
 * throwing. The component reads modules off of `dashboard.data.modules`,
 * iterates `evidence.data.rows`, and reads `providerHealth.data.overall_status`.
 */
const emptyDashboard: DashboardSummaryResponse = {
  generated_at: "2026-06-24T00:00:00Z",
  overall_status: "ok",
  overall_risk_level: "calm",
  modules: {},
  provider_health: {
    generated_at: "2026-06-24T00:00:00Z",
    overall_status: "ok",
    summary: { ok: 1 },
    next_action: null,
    error_summary: null
  },
  missing_data: [],
  data_freshness: {},
  next_actions: []
};

const emptyEvidence: DashboardEvidenceTableResponse = {
  generated_at: "2026-06-24T00:00:00Z",
  overall_status: "ok",
  row_count: 0,
  modules: [],
  rows: [],
  filters: { available: {}, applied: {} },
  next_actions: []
};

const okProviderHealth: ProviderHealthResponse = {
  generated_at: "2026-06-24T00:00:00Z",
  overall_status: "ok",
  summary: { ok: 1 },
  checks: [],
  next_action: null,
  error_summary: null
};

describe("DashboardHomepage smoke", () => {
  it("renders the page header in the happy path", () => {
    render(
      <DashboardHomepage
        dashboard={{ data: emptyDashboard, error: null }}
        evidence={{ data: emptyEvidence, error: null }}
        providerHealth={{ data: okProviderHealth, error: null }}
        isLoading={false}
        onNavigate={vi.fn()}
      />
    );

    // The page title text from PageHeader is "今日市场状态".
    expect(screen.getByText("今日市场状态")).toBeInTheDocument();
  });

  it("renders a loading state when isLoading is true", () => {
    render(
      <DashboardHomepage
        dashboard={{ data: null, error: null }}
        evidence={{ data: null, error: null }}
        providerHealth={{ data: null, error: null }}
        isLoading={true}
        onNavigate={vi.fn()}
      />
    );

    expect(screen.getByText("正在整理今日市场状态")).toBeInTheDocument();
  });

  it("renders an error panel when the dashboard request errored", () => {
    render(
      <DashboardHomepage
        dashboard={{ data: null, error: "backend offline" }}
        evidence={{ data: null, error: null }}
        providerHealth={{ data: null, error: null }}
        isLoading={false}
        onNavigate={vi.fn()}
      />
    );

    expect(screen.getByText("首页证据暂不可用")).toBeInTheDocument();
    expect(screen.getByText(/backend offline/)).toBeInTheDocument();
  });
});
