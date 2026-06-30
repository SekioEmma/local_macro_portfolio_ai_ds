import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { cancelAgentRun, streamAgentRun } from "../api/client";
import type { AgentSseEvent, AgentStreamResult, ApiResult } from "../types";
import { AIChatPage } from "./AIChatPage";

vi.mock("../api/client", () => ({
  cancelAgentRun: vi.fn(),
  streamAgentRun: vi.fn()
}));

const mockedCancelAgentRun = vi.mocked(cancelAgentRun);
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
            section: "core_conclusion",
            content: "Macro environment remains balanced."
          },
          2,
          capturedSessionId
        )
      );
      emit?.(
        agentEvent(
          "complete",
          { final_status: "ok", trace_session_id: "trace-ui", steps: 2 },
          3,
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

    expect(await screen.findByText("核心结论")).toBeInTheDocument();
    expect(
      screen.getByText("Macro environment remains balanced.")
    ).toBeInTheDocument();
    expect(mockedStreamAgentRun).toHaveBeenCalledWith(
      expect.objectContaining({
        user_question: "当前高实际利率对信用风险意味着什么？",
        include_holdings: false,
        confirm_external_search: false,
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
