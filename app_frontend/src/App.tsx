import { useCallback, useEffect, useState } from "react";
import {
  fetchAIContextManifest,
  fetchDashboardEvidenceTable,
  fetchDashboardSummary,
  fetchProviderHealth,
  fetchSettings,
  fetchStatus,
  fetchStorageStatus
} from "./api/client";
import { AppShell, type AppViewKey } from "./components/AppShell";
import { AIChatPage } from "./components/AIChatPage";
import { DashboardHomepage } from "./components/DashboardHomepage";
import { DiagnosticsPage } from "./components/DiagnosticsPage";
import { EvidenceAuditPage } from "./components/EvidenceAuditPage";
import { HistoricalValidationPage } from "./components/HistoricalValidationPage";
import { LocalResearchPreviewPage } from "./components/LocalResearchPreviewPage";
import { PortfolioOverlayPage } from "./components/PortfolioOverlayPage";
import { ScenarioStressPage } from "./components/ScenarioStressPage";
import type {
  AIContextManifestResponse,
  ApiResult,
  AppSettingsResponse,
  DashboardEvidenceTableResponse,
  DashboardSummaryResponse,
  ProviderHealthResponse,
  StatusResponse,
  StorageStatusResponse
} from "./types";

const emptyResult = <T,>(): ApiResult<T> => ({ data: null, error: null });

export default function App() {
  const [activeView, setActiveView] = useState<AppViewKey>("dashboard");
  const [status, setStatus] =
    useState<ApiResult<StatusResponse>>(emptyResult);
  const [providerHealth, setProviderHealth] =
    useState<ApiResult<ProviderHealthResponse>>(emptyResult);
  const [dashboard, setDashboard] =
    useState<ApiResult<DashboardSummaryResponse>>(emptyResult);
  const [evidence, setEvidence] =
    useState<ApiResult<DashboardEvidenceTableResponse>>(emptyResult);
  const [manifest, setManifest] =
    useState<ApiResult<AIContextManifestResponse>>(emptyResult);
  const [storage, setStorage] =
    useState<ApiResult<StorageStatusResponse>>(emptyResult);
  const [settings, setSettings] =
    useState<ApiResult<AppSettingsResponse>>(emptyResult);
  const [isLoading, setIsLoading] = useState(true);

  const loadReadOnlyContext = useCallback(() => {
    setIsLoading(true);
    Promise.all([
      fetchStatus(),
      fetchProviderHealth(),
      fetchDashboardSummary(),
      fetchDashboardEvidenceTable(),
      fetchAIContextManifest(),
      fetchStorageStatus(),
      fetchSettings()
    ])
      .then(
        ([
          statusResult,
          providerResult,
          dashboardResult,
          evidenceResult,
          manifestResult,
          storageResult,
          settingsResult
        ]) => {
          setStatus(statusResult);
          setProviderHealth(providerResult);
          setDashboard(dashboardResult);
          setEvidence(evidenceResult);
          setManifest(manifestResult);
          setStorage(storageResult);
          setSettings(settingsResult);
        }
      )
      .finally(() => setIsLoading(false));
  }, []);

  useEffect(() => {
    loadReadOnlyContext();
  }, [loadReadOnlyContext]);

  return (
    <AppShell activeView={activeView} onNavigate={setActiveView}>
      {activeView === "dashboard" && (
        <DashboardHomepage
          dashboard={dashboard}
          evidence={evidence}
          isLoading={isLoading}
          onNavigate={setActiveView}
          providerHealth={providerHealth}
        />
      )}
      {activeView === "evidence" && (
        <EvidenceAuditPage
          evidence={evidence}
          isLoading={isLoading}
          manifest={manifest}
        />
      )}
      {activeView === "scenario" && (
        <ScenarioStressPage evidence={evidence} isLoading={isLoading} />
      )}
      {activeView === "historical" && (
        <HistoricalValidationPage evidence={evidence} isLoading={isLoading} />
      )}
      {activeView === "ai-context" && (
        <LocalResearchPreviewPage
          isLoading={isLoading}
          manifest={manifest}
        />
      )}
      {activeView === "ai-chat" && <AIChatPage />}
      {activeView === "portfolio" && (
        <PortfolioOverlayPage
          dashboard={dashboard}
          evidence={evidence}
          isLoading={isLoading}
        />
      )}
      {activeView === "diagnostics" && (
        <DiagnosticsPage
          dashboard={dashboard}
          evidence={evidence}
          isLoading={isLoading}
          providerHealth={providerHealth}
          settings={settings}
          status={status}
          storage={storage}
        />
      )}
    </AppShell>
  );
}
