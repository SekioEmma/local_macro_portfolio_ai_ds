import type {
  ApiResult,
  AgentCancelResponse,
  AgentRunRequest,
  AgentSseEvent,
  AgentStreamResult,
  AIContextManifestResponse,
  AIDeepSeekResearchResponse,
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

export function fetchDeepSeekResearch(
  answerMode: AIAnswerMode,
  detailLevel: AIDetailLevel,
  userQuestion: string,
  signal?: AbortSignal
): Promise<ApiResult<AIDeepSeekResearchResponse>> {
  return requestJson<AIDeepSeekResearchResponse>("/api/ai/research-deepseek", {
    method: "POST",
    body: {
      answer_mode: answerMode,
      detail_level: detailLevel,
      user_question: userQuestion
    },
    timeoutMs: 180_000,
    signal
  });
}

export async function streamAgentRun(
  request: AgentRunRequest,
  onEvent: (event: AgentSseEvent) => void,
  signal?: AbortSignal
): Promise<ApiResult<AgentStreamResult>> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}/api/agent/run/stream`, {
      method: "POST",
      headers: {
        Accept: "text/event-stream",
        "Content-Type": "application/json"
      },
      body: JSON.stringify(request),
      signal
    });
  } catch (error) {
    if (error instanceof Error && error.name === "AbortError") {
      return { data: null, error: "请求已取消。" };
    }
    return {
      data: null,
      error:
        error instanceof Error
          ? error.message
          : "Agent 流式运行失败，请确认本地后端已启动。"
    };
  }

  if (!response.ok) {
    const detail = await readErrorDetail(response);
    return {
      data: null,
      error: detail || `请求失败：HTTP ${response.status}`
    };
  }

  if (!response.body) {
    return {
      data: null,
      error: "当前浏览器不支持流式响应读取，请升级浏览器或使用同步接口。"
    };
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let result: AgentStreamResult = {
    session_id: request.session_id || null,
    final_status: null,
    trace_session_id: null,
    steps: null
  };

  try {
    while (true) {
      const { done, value } = await reader.read();
      buffer += decoder.decode(value, { stream: !done });
      const blocks = buffer.split(/\r?\n\r?\n/);
      buffer = blocks.pop() || "";
      for (const block of blocks) {
        const event = parseAgentSseBlock(block);
        if (!event) continue;
        result = updateAgentStreamResult(result, event);
        onEvent(event);
        if (event.type === "error") {
          return {
            data: null,
            error:
              stringFromPayload(event.payload, "detail") ||
              stringFromPayload(event.payload, "error_type") ||
              "Agent 流式运行失败。"
          };
        }
      }
      if (done) break;
    }

    const trailingEvent = parseAgentSseBlock(buffer);
    if (trailingEvent) {
      result = updateAgentStreamResult(result, trailingEvent);
      onEvent(trailingEvent);
      if (trailingEvent.type === "error") {
        return {
          data: null,
          error:
            stringFromPayload(trailingEvent.payload, "detail") ||
            stringFromPayload(trailingEvent.payload, "error_type") ||
            "Agent 流式运行失败。"
        };
      }
    }

    return { data: result, error: null };
  } catch (error) {
    if (error instanceof Error && error.name === "AbortError") {
      return { data: null, error: "请求已取消。" };
    }
    return {
      data: null,
      error:
        error instanceof Error
          ? error.message
          : "Agent 流式运行失败，请确认本地后端已启动。"
    };
  }
}

export function cancelAgentRun(
  sessionId: string
): Promise<ApiResult<AgentCancelResponse>> {
  return requestJson<AgentCancelResponse>(
    `/api/agent/run/${encodeURIComponent(sessionId)}/cancel`,
    { method: "POST" }
  );
}

function parseAgentSseBlock(block: string): AgentSseEvent | null {
  const dataLines = block
    .split(/\r?\n/)
    .filter((line) => line.startsWith("data: "))
    .map((line) => line.slice("data: ".length));
  if (!dataLines.length) return null;
  try {
    const parsed = JSON.parse(dataLines.join("\n")) as unknown;
    if (!isAgentSseEvent(parsed)) return null;
    return parsed;
  } catch {
    return null;
  }
}

function isAgentSseEvent(value: unknown): value is AgentSseEvent {
  if (!value || typeof value !== "object") return false;
  const candidate = value as Partial<AgentSseEvent>;
  return (
    typeof candidate.event_id === "string" &&
    typeof candidate.session_id === "string" &&
    typeof candidate.sequence === "number" &&
    typeof candidate.timestamp === "string" &&
    typeof candidate.type === "string" &&
    Boolean(candidate.payload) &&
    typeof candidate.payload === "object" &&
    !Array.isArray(candidate.payload)
  );
}

function updateAgentStreamResult(
  result: AgentStreamResult,
  event: AgentSseEvent
): AgentStreamResult {
  const next: AgentStreamResult = {
    ...result,
    session_id: event.session_id || result.session_id
  };
  if (event.type !== "complete") return next;
  return {
    ...next,
    final_status:
      stringFromPayload(event.payload, "final_status") || result.final_status,
    trace_session_id:
      stringFromPayload(event.payload, "trace_session_id") ||
      result.trace_session_id,
    steps: numberFromPayload(event.payload, "steps") ?? result.steps
  };
}

function stringFromPayload(
  payload: Record<string, unknown>,
  key: string
): string | null {
  const value = payload[key];
  return typeof value === "string" ? value : null;
}

function numberFromPayload(
  payload: Record<string, unknown>,
  key: string
): number | null {
  const value = payload[key];
  return typeof value === "number" && Number.isFinite(value) ? value : null;
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

type RequestOptions = {
  method?: "GET" | "PUT" | "POST";
  body?: unknown;
  timeoutMs?: number;
  signal?: AbortSignal;
};

async function requestJson<T>(
  path: string,
  options: RequestOptions = {}
): Promise<ApiResult<T>> {
  const controller = new AbortController();
  let timedOut = false;
  const abortFromCaller = () => controller.abort();
  if (options.signal?.aborted) controller.abort();
  options.signal?.addEventListener("abort", abortFromCaller, { once: true });
  const timeoutId = options.timeoutMs
    ? window.setTimeout(() => {
        timedOut = true;
        controller.abort();
      }, options.timeoutMs)
    : null;
  try {
    const response = await fetch(`${API_BASE_URL}${path}`, {
      method: options.method || "GET",
      headers: {
        Accept: "application/json",
        ...(options.body ? { "Content-Type": "application/json" } : {})
      },
      body: options.body ? JSON.stringify(options.body) : undefined,
      signal: controller.signal
    });
    if (!response.ok) {
      const detail = await readErrorDetail(response);
      return {
        data: null,
        error: detail || `请求失败：HTTP ${response.status}`
      };
    }
    return { data: (await response.json()) as T, error: null };
  } catch (error) {
    if (error instanceof Error && error.name === "AbortError") {
      return {
        data: null,
        error: timedOut
          ? `请求超过 ${Math.round((options.timeoutMs || 0) / 1000)} 秒未完成，请稍后重试或降低分析深度。`
          : "请求已取消。"
      };
    }
    return {
      data: null,
      error: error instanceof Error ? error.message : "请求失败，请确认本地后端已启动。"
    };
  } finally {
    if (timeoutId !== null) window.clearTimeout(timeoutId);
    options.signal?.removeEventListener("abort", abortFromCaller);
  }
}

async function readErrorDetail(response: Response) {
  try {
    const payload = (await response.json()) as { detail?: unknown };
    return typeof payload.detail === "string" ? payload.detail : null;
  } catch {
    return null;
  }
}
