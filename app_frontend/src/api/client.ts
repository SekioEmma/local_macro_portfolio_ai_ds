import type {
  ApiResult,
  AIContextManifestResponse,
  AIAnswerMode,
  AIDetailLevel,
  AIPromptPreviewResponse,
  AIResearchPreviewResponse,
  AppSettings,
  AppSettingsResponse,
  DashboardEvidenceFilters,
  DashboardEvidenceTableResponse,
  DashboardSummaryResponse,
  FavoriteAnswer,
  ProviderHealthResponse,
  RefreshRun,
  StatusResponse,
  StorageStatusResponse
} from "../types";

const API_BASE_URL = (
  import.meta.env.VITE_API_BASE_URL || "http://127.0.0.1:8765"
).replace(/\/$/, "");

export function fetchStatus(): Promise<ApiResult<StatusResponse>> {
  return requestJson<StatusResponse>("/api/status");
}

export function fetchProviderHealth(): Promise<ApiResult<ProviderHealthResponse>> {
  return requestJson<ProviderHealthResponse>("/api/provider-health");
}

export function fetchDashboardSummary(): Promise<ApiResult<DashboardSummaryResponse>> {
  return requestJson<DashboardSummaryResponse>("/api/dashboard/summary");
}

export function fetchDashboardEvidenceTable(
  filters: DashboardEvidenceFilters = {}
): Promise<
  ApiResult<DashboardEvidenceTableResponse>
> {
  const query = new URLSearchParams();
  if (filters.module) query.set("module", filters.module);
  if (filters.status) query.set("status", filters.status);
  if (filters.source_badge) query.set("source_badge", filters.source_badge);
  if (filters.ai_context_allowed !== undefined) {
    query.set("ai_context_allowed", String(filters.ai_context_allowed));
  }
  const suffix = query.toString() ? `?${query.toString()}` : "";
  return requestJson<DashboardEvidenceTableResponse>(
    `/api/dashboard/evidence-table${suffix}`
  );
}

export function fetchAIContextManifest(): Promise<
  ApiResult<AIContextManifestResponse>
> {
  return requestJson<AIContextManifestResponse>("/api/ai/context-preview");
}

export function fetchAIResearchPreview(
  answerMode: AIAnswerMode,
  detailLevel: AIDetailLevel
): Promise<ApiResult<AIResearchPreviewResponse>> {
  return requestJson<AIResearchPreviewResponse>("/api/ai/research-preview", {
    method: "POST",
    body: {
      answer_mode: answerMode,
      detail_level: detailLevel
    }
  });
}

export function fetchAIPromptPreview(
  answerMode: AIAnswerMode,
  detailLevel: AIDetailLevel
): Promise<ApiResult<AIPromptPreviewResponse>> {
  return requestJson<AIPromptPreviewResponse>("/api/ai/prompt-preview", {
    method: "POST",
    body: {
      answer_mode: answerMode,
      detail_level: detailLevel
    }
  });
}

export function fetchStorageStatus(): Promise<ApiResult<StorageStatusResponse>> {
  return requestJson<StorageStatusResponse>("/api/app/storage");
}

export function fetchSettings(): Promise<ApiResult<AppSettingsResponse>> {
  return requestJson<AppSettingsResponse>("/api/app/settings");
}

export function updateSettings(
  settings: AppSettings
): Promise<ApiResult<AppSettingsResponse>> {
  return requestJson<AppSettingsResponse>("/api/app/settings", {
    method: "PUT",
    body: { settings }
  });
}

export function fetchRefreshRuns(): Promise<ApiResult<RefreshRun[]>> {
  return requestJson<RefreshRun[]>("/api/app/refresh-runs");
}

export function createRefreshRun(): Promise<ApiResult<RefreshRun>> {
  const startedAt = new Date().toISOString();
  return requestJson<RefreshRun>("/api/app/refresh-runs", {
    method: "POST",
    body: {
      kind: "ui_placeholder",
      status: "ok",
      started_at: startedAt,
      finished_at: startedAt,
      summary: { source: "local placeholder" }
    }
  });
}

export function fetchFavorites(): Promise<ApiResult<FavoriteAnswer[]>> {
  return requestJson<FavoriteAnswer[]>("/api/app/favorites");
}

export function createFavorite(): Promise<ApiResult<FavoriteAnswer>> {
  return requestJson<FavoriteAnswer>("/api/app/favorites", {
    method: "POST",
    body: {
      title: "Placeholder favorite",
      question: "Fake sanitized question for future chat favorites.",
      answer: "Fake sanitized answer metadata only. No model call is made.",
      model: "mock",
      context_snapshot: { phase: "sqlite_app_state_foundation" }
    }
  });
}

async function requestJson<T>(
  path: string,
  options: { method?: "GET" | "PUT" | "POST"; body?: unknown } = {}
): Promise<ApiResult<T>> {
  try {
    const response = await fetch(`${API_BASE_URL}${path}`, {
      method: options.method || "GET",
      headers: {
        Accept: "application/json",
        ...(options.body ? { "Content-Type": "application/json" } : {})
      },
      body: options.body ? JSON.stringify(options.body) : undefined
    });
    if (!response.ok) {
      return { data: null, error: `请求失败：HTTP ${response.status}` };
    }
    return { data: (await response.json()) as T, error: null };
  } catch (error) {
    return {
      data: null,
      error: error instanceof Error ? error.message : "请求失败，请确认本地后端已启动。"
    };
  }
}
