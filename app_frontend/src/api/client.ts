import type {
  ApiResult,
  DashboardSummaryResponse,
  ProviderHealthResponse,
  StatusResponse
} from "../types";

const API_BASE_URL = (
  import.meta.env.VITE_API_BASE_URL || "http://127.0.0.1:8765"
).replace(/\/$/, "");

export function fetchStatus(): Promise<ApiResult<StatusResponse>> {
  return fetchJson<StatusResponse>("/api/status");
}

export function fetchProviderHealth(): Promise<ApiResult<ProviderHealthResponse>> {
  return fetchJson<ProviderHealthResponse>("/api/provider-health");
}

export function fetchDashboardSummary(): Promise<ApiResult<DashboardSummaryResponse>> {
  return fetchJson<DashboardSummaryResponse>("/api/dashboard/summary");
}

async function fetchJson<T>(path: string): Promise<ApiResult<T>> {
  try {
    const response = await fetch(`${API_BASE_URL}${path}`, {
      method: "GET",
      headers: { Accept: "application/json" }
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
