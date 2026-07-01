import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import {
  cancelAgentRun,
  fetchAgentCapabilities,
  requestHoldingsConsent,
  streamAgentRun
} from "../api/client";
import type { AgentSseEvent, AgentStreamResult, ApiResult } from "../types";
import { AIChatPage } from "./AIChatPage";

vi.mock("../api/client", () => ({
  cancelAgentRun: vi.fn(),
  fetchAgentCapabilities: vi.fn(),
  requestHoldingsConsent: vi.fn(),
  streamAgentRun: vi.fn()
}));

const mockedCancelAgentRun = vi.mocked(cancelAgentRun);
const mockedFetchAgentCapabilities = vi.mocked(fetchAgentCapabilities);
const mockedRequestHoldingsConsent = vi.mocked(requestHoldingsConsent);
const mockedStreamAgentRun = vi.mocked(streamAgentRun);

describe("AIChatPage Agent SSE", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockedCancelAgentRun.mockResolvedValue({
      data: {
        session_id: "agent-ui-test",
        cancelled: true,
        already_cancelled: false
      },
      error: null
    });
    mockedRequestHoldingsConsent.mockResolvedValue({
      data: {
        session_id: "agent-ui-test",
        holdings_consent_token: "token_1234567890123456",
        expires_at: "2026-06-30T00:10:00Z",
        ttl_seconds: 600
      },
      error: null
    });
    mockedFetchAgentCapabilities.mockResolvedValue({
      data: {
        holdings_external_context: {
          enabled: false,
          reason_code: "holdings_snapshot_backend_not_wired"
        }
      },
      error: null
    });
  });

  it("shows fixed MacroBrief product status labels", async () => {
    render(<AIChatPage />);

    expect(screen.getByLabelText("MacroBrief 输出定位")).toBeInTheDocument();
    expect(screen.getByText("研究辅助输出")).toBeInTheDocument();
    expect(screen.getByText("非自动投资决策")).toBeInTheDocument();
    expect(screen.getByText("需要用户审阅")).toBeInTheDocument();
    expect(
      await screen.findByText("详细持仓上下文：暂未启用")
    ).toBeInTheDocument();
  });

  it("streams validated brief sections into the paper result panel", async () => {
    let emit: ((event: AgentSseEvent) => void) | undefined;
    let resolveRun:
      | ((value: ApiResult<AgentStreamResult>) => void)
      | undefined;
    let capturedSessionId = "";
    mockedStreamAgentRun.mockImplementation((request, onEvent) => {
      capturedSessionId = request.session_id || "agent-ui-test";
      emit = onEvent;
      return new Promise((resolve) => {
        resolveRun = resolve;
      });
    });

    const user = userEvent.setup();
    render(<AIChatPage />);

    await act(async () => {
      await user.type(
        screen.getByLabelText("宏观研究问题"),
        "当前高实际利率对信用风险意味着什么？"
      );
      await user.click(screen.getByRole("button", { name: /启动 Agent 调研/ }));
    });

    await act(async () => {
      emit?.(agentEvent("run_started", {}, 1, capturedSessionId));
      emit?.(
        agentEvent(
          "brief_section",
          {
            section: "temporal_envelope",
            content: {
              report_generated_at: "2026-06-30T14:00:00+00:00",
              market_data_cutoff: "2026-06-29",
              policy_data_cutoff: "2026-06-18",
              macro_data_cutoff: "2026-06-15",
              public_news_cutoff: "2026-06-30",
              max_market_data_age_working_days_approx: 2,
              asynchronous_inputs: false
            }
          },
          2,
          capturedSessionId
        )
      );
      emit?.(
        agentEvent(
          "brief_section",
          {
            section: "core_conclusion",
            content: "Macro environment remains balanced."
          },
          3,
          capturedSessionId
        )
      );
      emit?.(
        agentEvent(
          "complete",
          { final_status: "ok", trace_session_id: "trace-ui", steps: 2 },
          4,
          capturedSessionId
        )
      );
      resolveRun?.(
        streamResult({
          session_id: capturedSessionId,
          final_status: "ok",
          trace_session_id: "trace-ui",
          steps: 2
        })
      );
    });

    expect(await screen.findByText("时间对齐")).toBeInTheDocument();
    expect(screen.getByText("市场数据截止")).toBeInTheDocument();
    expect(screen.getByText("2026-06-29")).toBeInTheDocument();
    expect(await screen.findByText("核心结论")).toBeInTheDocument();
    expect(
      screen.getByText("Macro environment remains balanced.")
    ).toBeInTheDocument();
    expect(mockedStreamAgentRun).toHaveBeenCalledWith(
      expect.objectContaining({
        user_question: "当前高实际利率对信用风险意味着什么？",
        include_holdings: false,
        holdings_consent_token: null,
        confirm_external_search: false,
        source_visibility_mode: "public"
      }),
      expect.any(Function),
      expect.any(AbortSignal)
    );
    expect(mockedRequestHoldingsConsent).not.toHaveBeenCalled();
  });

  it("disables detailed holdings activation while the backend snapshot provider is unwired", async () => {
    mockedStreamAgentRun.mockResolvedValue(
      streamResult({
        session_id: "agent-no-holdings-ui",
        final_status: "ok",
        trace_session_id: "trace-no-holdings-ui",
        steps: 1
      })
    );

    const user = userEvent.setup();
    render(<AIChatPage />);

    expect(
      await screen.findByText("详细持仓上下文：暂未启用")
    ).toBeInTheDocument();
    expect(screen.getByLabelText("允许本次详细持仓上下文")).toBeDisabled();

    await act(async () => {
      await user.type(screen.getByLabelText("宏观研究问题"), "结合我的组合风险看宏观环境");
      await user.click(screen.getByRole("button", { name: /启动 Agent 调研/ }));
    });

    expect(mockedRequestHoldingsConsent).not.toHaveBeenCalled();
    expect(mockedStreamAgentRun).toHaveBeenCalledWith(
      expect.objectContaining({
        user_question: "结合我的组合风险看宏观环境",
        include_holdings: false,
        holdings_consent_token: null,
        source_visibility_mode: "public"
      }),
      expect.any(Function),
      expect.any(AbortSignal)
    );
  });

  it("requests per-run holdings consent before streaming when capability is wired and explicitly enabled", async () => {
    mockedFetchAgentCapabilities.mockResolvedValue({
      data: {
        holdings_external_context: {
          enabled: true,
          reason_code: null
        }
      },
      error: null
    });
    mockedStreamAgentRun.mockResolvedValue(
      streamResult({
        session_id: "agent-holdings-ui",
        final_status: "ok",
        trace_session_id: "trace-holdings-ui",
        steps: 1
      })
    );

    const user = userEvent.setup();
    render(<AIChatPage />);

    expect(
      await screen.findByLabelText("允许本次详细持仓上下文")
    ).not.toBeDisabled();

    await act(async () => {
      await user.type(screen.getByLabelText("宏观研究问题"), "结合我的组合风险看宏观环境");
      await user.click(screen.getByLabelText("允许本次详细持仓上下文"));
      await user.click(screen.getByRole("button", { name: /启动 Agent 调研/ }));
    });

    expect(mockedRequestHoldingsConsent).toHaveBeenCalledWith(
      {
        session_id: expect.stringMatching(/^agent-ui-/),
        confirm_holdings_external_context: true
      },
      expect.any(AbortSignal)
    );
    expect(mockedStreamAgentRun).toHaveBeenCalledWith(
      expect.objectContaining({
        user_question: "结合我的组合风险看宏观环境",
        include_holdings: true,
        holdings_consent_token: "token_1234567890123456",
        source_visibility_mode: "public"
      }),
      expect.any(Function),
      expect.any(AbortSignal)
    );
  });

  it("sends a cancel request for the active generated session id", async () => {
    let resolveRun:
      | ((value: ApiResult<AgentStreamResult>) => void)
      | undefined;
    let capturedSessionId = "";
    mockedStreamAgentRun.mockImplementation((request) => {
      capturedSessionId = request.session_id || "agent-ui-test";
      return new Promise((resolve) => {
        resolveRun = resolve;
      });
    });

    const user = userEvent.setup();
    render(<AIChatPage />);

    await act(async () => {
      await user.type(screen.getByLabelText("宏观研究问题"), "请生成可取消的宏观 brief");
      await user.click(screen.getByRole("button", { name: /启动 Agent 调研/ }));
    });
    await act(async () => {
      await user.click(await screen.findByRole("button", { name: /取消运行/ }));
    });

    expect(mockedCancelAgentRun).toHaveBeenCalledWith(capturedSessionId);
    await act(async () => {
      resolveRun?.(
        streamResult({
          session_id: capturedSessionId,
          final_status: "cancelled",
          trace_session_id: "trace-cancel",
          steps: 1
        })
      );
    });
    await waitFor(() =>
      expect(screen.getByText("Agent 运行已取消")).toBeInTheDocument()
    );
  });
});

function agentEvent(
  type: string,
  payload: Record<string, unknown> = {},
  sequence = 1,
  sessionId = "agent-ui-test"
): AgentSseEvent {
  return {
    event_id: `${sessionId}:${sequence}`,
    session_id: sessionId,
    sequence,
    timestamp: "2026-06-30T00:00:00+00:00",
    type,
    payload
  };
}

function streamResult(
  data: AgentStreamResult
): ApiResult<AgentStreamResult> {
  return { data, error: null };
}
