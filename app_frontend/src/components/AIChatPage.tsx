import { useEffect, useRef, useState } from "react";
import type { FormEvent, KeyboardEvent } from "react";
import { cancelAgentRun, streamAgentRun } from "../api/client";
import type {
  AgentBriefSection,
  AgentRunRequest,
  AgentSseEvent,
  AgentStreamResult,
  ApiResult
} from "../types";
import { ResearchIcon } from "./ResearchIcon";
import {
  BoundaryNotice,
  EmptyState,
  ErrorState,
  PageHeader,
  humanizeKey
} from "./ResearchUI";

type StreamStatus =
  | "idle"
  | "running"
  | "cancel_requested"
  | "cancelled"
  | "complete"
  | "error";

type ChatCopyState = "idle" | "copied" | "error";

const MAX_QUESTION_LENGTH = 2000;

const macroBriefProductStatusLabels = [
  "研究辅助输出",
  "非自动投资决策",
  "需要用户审阅"
];

const briefSectionOrder = [
  "core_conclusion",
  "market_state",
  "confirmed_facts",
  "judgments",
  "module_table",
  "risk_assessment",
  "forward_indicators",
  "scenarios",
  "source_list",
  "boundary_notice"
];

const briefSectionTitles: Record<string, string> = {
  core_conclusion: "核心结论",
  market_state: "市场状态",
  confirmed_facts: "确认事实",
  judgments: "判断链路",
  module_table: "模块表",
  risk_assessment: "风险评估",
  forward_indicators: "前瞻指标",
  scenarios: "情景",
  source_list: "来源清单",
  boundary_notice: "边界声明"
};

export function AIChatPage() {
  const [question, setQuestion] = useState("");
  const [confirmExternalSearch, setConfirmExternalSearch] = useState(false);
  const [streamEvents, setStreamEvents] = useState<AgentSseEvent[]>([]);
  const [briefSections, setBriefSections] = useState<AgentBriefSection[]>([]);
  const [runResult, setRunResult] =
    useState<ApiResult<AgentStreamResult> | null>(null);
  const [streamStatus, setStreamStatus] = useState<StreamStatus>("idle");
  const [isStreaming, setIsStreaming] = useState(false);
  const [cancelRequested, setCancelRequested] = useState(false);
  const [cancelError, setCancelError] = useState<string | null>(null);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [elapsed, setElapsed] = useState(0);
  const [copyState, setCopyState] = useState<ChatCopyState>("idle");
  const [questionError, setQuestionError] = useState<string | null>(null);
  const activeRequest = useRef<AbortController | null>(null);
  const activeSessionId = useRef<string | null>(null);

  const trimmedQuestion = question.trim();
  const canSubmit =
    trimmedQuestion.length >= 2 &&
    trimmedQuestion.length <= MAX_QUESTION_LENGTH &&
    !isStreaming;
  const hasAgentOutput =
    isStreaming ||
    streamEvents.length > 0 ||
    briefSections.length > 0 ||
    runResult !== null;

  useEffect(() => {
    if (!isStreaming) return;
    setElapsed(0);
    const startedAt = Date.now();
    const intervalId = window.setInterval(() => {
      setElapsed(Math.floor((Date.now() - startedAt) / 1000));
    }, 1000);
    return () => window.clearInterval(intervalId);
  }, [isStreaming]);

  useEffect(
    () => () => {
      activeRequest.current?.abort();
      activeRequest.current = null;
      activeSessionId.current = null;
    },
    []
  );

  async function submitResearch(event?: FormEvent) {
    event?.preventDefault();
    if (trimmedQuestion.length < 2) {
      setQuestionError("问题至少需要 2 个字符。");
      return;
    }
    if (trimmedQuestion.length > MAX_QUESTION_LENGTH) {
      setQuestionError(`问题不能超过 ${MAX_QUESTION_LENGTH} 个字符。`);
      return;
    }

    const nextSessionId = createAgentSessionId();
    const controller = new AbortController();
    const request: AgentRunRequest = {
      user_question: trimmedQuestion,
      session_id: nextSessionId,
      include_holdings: false,
      confirm_external_search: confirmExternalSearch,
      source_visibility_mode: "public"
    };

    activeRequest.current?.abort();
    activeRequest.current = controller;
    activeSessionId.current = nextSessionId;
    setSessionId(nextSessionId);
    setQuestionError(null);
    setCancelError(null);
    setCancelRequested(false);
    setCopyState("idle");
    setRunResult(null);
    setStreamEvents([]);
    setBriefSections([]);
    setStreamStatus("running");
    setIsStreaming(true);

    try {
      const response = await streamAgentRun(
        request,
        handleAgentEvent,
        controller.signal
      );
      if (controller.signal.aborted) return;
      setRunResult(response);
      if (response.error) {
        setStreamStatus("error");
      } else if (response.data?.final_status === "cancelled") {
        setStreamStatus("cancelled");
      } else {
        setStreamStatus("complete");
      }
    } finally {
      if (activeRequest.current === controller) {
        activeRequest.current = null;
        activeSessionId.current = null;
        setIsStreaming(false);
      }
    }
  }

  function handleAgentEvent(event: AgentSseEvent) {
    setSessionId(event.session_id);
    setStreamEvents((current) => [...current, event].slice(-80));
    if (event.type === "brief_section") {
      const section = stringFromPayload(event.payload, "section");
      if (section) {
        const nextSection: AgentBriefSection = {
          section,
          content: event.payload.content,
          sequence: event.sequence
        };
        setBriefSections((current) =>
          sortBriefSections([
            ...current.filter((item) => item.section !== section),
            nextSection
          ])
        );
      }
    }
    if (event.type === "cancelled") {
      setStreamStatus("cancelled");
    } else if (event.type === "error") {
      setStreamStatus("error");
    } else if (event.type === "complete") {
      setStreamStatus(
        stringFromPayload(event.payload, "final_status") === "cancelled"
          ? "cancelled"
          : "complete"
      );
    } else {
      setStreamStatus((current) =>
        current === "cancel_requested" || current === "cancelled"
          ? current
          : "running"
      );
    }
  }

  async function cancelCurrentRun() {
    const currentSessionId = sessionId || activeSessionId.current;
    if (!currentSessionId) return;
    setCancelError(null);
    setCancelRequested(true);
    setStreamStatus("cancel_requested");
    const response = await cancelAgentRun(currentSessionId);
    if (response.error) {
      setCancelError(response.error);
      setCancelRequested(false);
      setStreamStatus(isStreaming ? "running" : "error");
    }
  }

  function handleQuestionKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === "Enter" && (event.ctrlKey || event.metaKey)) {
      event.preventDefault();
      if (canSubmit) void submitResearch();
    }
  }

  async function copyBrief() {
    if (!briefSections.length) return;
    try {
      await navigator.clipboard.writeText(serializeBriefSections(briefSections));
      setCopyState("copied");
      window.setTimeout(() => setCopyState("idle"), 1800);
    } catch {
      setCopyState("error");
    }
  }

  return (
    <section className="chat-page">
      <PageHeader
        eyebrow="PHASE F AGENT STREAM · POST-SSE"
        title="AI 宏观研究"
        subtitle="MacroBrief Agent 流式进度、取消与验证后逐节展示"
      />

      <BoundaryNotice title="外部模型、搜索与持仓边界" tone="warning">
        本页调用 Phase F Agent 流式接口。默认不注入详细持仓；外部搜索只有在勾选本次确认后才允许进入后端工具门禁。
        SSE 只展示清洗后的进度与验证后的 brief section。
      </BoundaryNotice>

      <ProductStatusStrip />

      <form className="chat-controls" onSubmit={submitResearch}>
        <label className="chat-question-field" htmlFor="ai-research-question">
          <span>宏观研究问题</span>
          <textarea
            aria-describedby="chat-question-help chat-question-error"
            aria-invalid={Boolean(questionError)}
            disabled={isStreaming}
            id="ai-research-question"
            maxLength={MAX_QUESTION_LENGTH}
            onChange={(event) => {
              setQuestion(event.target.value);
              if (questionError) setQuestionError(null);
            }}
            onKeyDown={handleQuestionKeyDown}
            placeholder="例如：当前高实际利率对信用风险意味着什么？"
            rows={5}
            value={question}
          />
        </label>

        <label className="chat-search-toggle">
          <input
            checked={confirmExternalSearch}
            disabled={isStreaming}
            onChange={(event) => setConfirmExternalSearch(event.target.checked)}
            type="checkbox"
          />
          <span>允许本次外部搜索</span>
          <small>默认关闭；开启后仍由后端工具注册表、预算和审计规则控制。</small>
        </label>

        <div className="chat-submit-row">
          <div>
            <span id="chat-question-help">Ctrl / ⌘ + Enter 发送</span>
            <span
              className={
                question.length >= MAX_QUESTION_LENGTH - 120
                  ? "chat-is-near-limit"
                  : ""
              }
            >
              {question.length} / {MAX_QUESTION_LENGTH}
            </span>
          </div>
          <div className="chat-action-row">
            {isStreaming && (
              <button
                className="chat-cancel-button"
                disabled={cancelRequested || !sessionId}
                onClick={cancelCurrentRun}
                type="button"
              >
                <ResearchIcon name="close" size={16} />
                {cancelRequested ? "取消已发送" : "取消运行"}
              </button>
            )}
            <button
              className="chat-submit-button"
              disabled={!canSubmit}
              type="submit"
            >
              {isStreaming ? (
                <>
                  <ResearchIcon name="clock" size={17} />
                  运行中 · {elapsed}s
                </>
              ) : (
                <>
                  <ResearchIcon name="ai" size={17} />
                  启动 Agent 调研
                </>
              )}
            </button>
          </div>
        </div>
        <p className="chat-field-error" id="chat-question-error" role="alert">
          {questionError || ""}
        </p>
      </form>

      <section className="chat-result-panel" aria-live="polite">
        {hasAgentOutput ? (
          <AgentStreamWorkspace
            briefSections={briefSections}
            cancelError={cancelError}
            cancelRequested={cancelRequested}
            copyState={copyState}
            elapsed={elapsed}
            events={streamEvents}
            isStreaming={isStreaming}
            onCopy={copyBrief}
            result={runResult}
            sessionId={sessionId}
            status={streamStatus}
          />
        ) : (
          <EmptyState
            icon="ai"
            title="开始一次流式 Agent 调研"
            description="输入宏观研究问题后，前端会展示后端 Agent 的清洗进度，并在 brief 验证通过后逐节呈现。"
          />
        )}
      </section>
    </section>
  );
}

function ProductStatusStrip() {
  return (
    <div className="agent-product-status" aria-label="MacroBrief 输出定位">
      {macroBriefProductStatusLabels.map((label) => (
        <span key={label}>{label}</span>
      ))}
    </div>
  );
}

function AgentStreamWorkspace({
  briefSections,
  cancelError,
  cancelRequested,
  copyState,
  elapsed,
  events,
  isStreaming,
  onCopy,
  result,
  sessionId,
  status
}: {
  briefSections: AgentBriefSection[];
  cancelError: string | null;
  cancelRequested: boolean;
  copyState: ChatCopyState;
  elapsed: number;
  events: AgentSseEvent[];
  isStreaming: boolean;
  onCopy: () => Promise<void>;
  result: ApiResult<AgentStreamResult> | null;
  sessionId: string | null;
  status: StreamStatus;
}) {
  const latestEvent = events.at(-1);
  return (
    <div className="agent-stream-workspace">
      <section className="agent-stream-ledger" role="status">
        <header className="agent-stream-status-head">
          <span className={`agent-stream-mark agent-status-${status}`}>
            <ResearchIcon
              name={
                status === "complete"
                  ? "check"
                  : status === "cancelled" || status === "cancel_requested"
                    ? "close"
                    : status === "error"
                      ? "diagnostics"
                      : "clock"
              }
              size={19}
            />
          </span>
          <div>
            <p className="chat-kicker">AGENT STREAM LEDGER</p>
            <h2>{streamStatusTitle(status, isStreaming)}</h2>
            <p>{streamStatusDescription(status, cancelRequested)}</p>
          </div>
        </header>

        <dl className="agent-stream-meta">
          <div>
            <dt>Session</dt>
            <dd>{sessionId || "等待后端分配"}</dd>
          </div>
          <div>
            <dt>最新事件</dt>
            <dd>{latestEvent ? eventTypeLabel(latestEvent.type) : "未开始"}</dd>
          </div>
          <div>
            <dt>耗时</dt>
            <dd>{elapsed}s</dd>
          </div>
          <div>
            <dt>最终状态</dt>
            <dd>{result?.data?.final_status || (isStreaming ? "running" : "pending")}</dd>
          </div>
        </dl>

        {cancelError && (
          <p className="agent-stream-error" role="alert">
            取消请求失败：{cancelError}
          </p>
        )}
        {result?.error && (
          <ErrorState title="Agent 流式运行失败" message={result.error} />
        )}
        <AgentEventTimeline events={events} />
      </section>

      <section className="agent-brief-paper">
        <header>
          <div>
            <p className="chat-kicker">VALIDATED MACROBRIEF</p>
            <h2>验证后逐节输出</h2>
          </div>
          <div className="chat-copy-control">
            <button
              aria-label="复制已生成的 MacroBrief"
              disabled={!briefSections.length}
              onClick={onCopy}
              type="button"
            >
              <ResearchIcon
                name={copyState === "copied" ? "check" : "copy"}
                size={16}
              />
              {copyState === "copied"
                ? "已复制"
                : copyState === "error"
                  ? "复制失败"
                  : "复制 brief"}
            </button>
            <span role="status">
              {copyState === "error"
                ? "浏览器未允许写入剪贴板，请检查权限。"
                : ""}
            </span>
          </div>
        </header>
        <AgentBriefSections sections={briefSections} />
      </section>
    </div>
  );
}

function AgentEventTimeline({ events }: { events: AgentSseEvent[] }) {
  const recentEvents = events.slice(-12);
  if (!recentEvents.length) {
    return (
      <div className="agent-event-empty">
        <ResearchIcon name="clock" size={18} />
        <span>等待第一条 SSE 事件。</span>
      </div>
    );
  }
  return (
    <ol className="agent-event-timeline" aria-label="Agent SSE 事件">
      {recentEvents.map((event) => (
        <li key={event.event_id}>
          <span>{event.sequence}</span>
          <div>
            <strong>{eventTypeLabel(event.type)}</strong>
            <small>{eventSummary(event)}</small>
          </div>
        </li>
      ))}
    </ol>
  );
}

function AgentBriefSections({ sections }: { sections: AgentBriefSection[] }) {
  if (!sections.length) {
    return (
      <section className="agent-brief-empty">
        <ResearchIcon name="shield" size={24} />
        <h3>等待验证后的 brief section</h3>
        <p>
          Agent 可以先发送进度事件；只有 MacroBrief 通过 schema、evidence 和 temporal
          校验后，前端才逐节展示内容。
        </p>
      </section>
    );
  }
  return (
    <div className="agent-brief-section-list">
      {sections.map((section) => (
        <article className="agent-brief-section" key={section.section}>
          <header>
            <span>{briefSectionOrder.indexOf(section.section) + 1 || "·"}</span>
            <div>
              <h3>{briefSectionTitles[section.section] || humanizeKey(section.section)}</h3>
              <small>{section.section}</small>
            </div>
          </header>
          <AgentBriefContent content={section.content} />
        </article>
      ))}
    </div>
  );
}

function AgentBriefContent({ content }: { content: unknown }) {
  if (content === null || content === undefined) {
    return <p className="agent-brief-muted">暂无内容。</p>;
  }
  if (typeof content === "string" || typeof content === "number") {
    return <p className="agent-brief-paragraph">{String(content)}</p>;
  }
  if (typeof content === "boolean") {
    return <p className="agent-brief-paragraph">{content ? "是" : "否"}</p>;
  }
  if (Array.isArray(content)) {
    return <AgentArrayContent content={content} />;
  }
  if (isRecord(content)) {
    return <AgentObjectContent content={content} />;
  }
  return <p className="agent-brief-paragraph">{String(content)}</p>;
}

function AgentArrayContent({ content }: { content: unknown[] }) {
  if (!content.length) return <p className="agent-brief-muted">暂无条目。</p>;
  if (content.every(isRecord)) {
    const columns = Array.from(
      new Set(content.flatMap((item) => Object.keys(item as Record<string, unknown>)))
    ).slice(0, 6);
    return (
      <div className="agent-brief-table-wrap">
        <table className="agent-brief-table">
          <thead>
            <tr>
              {columns.map((column) => (
                <th key={column} scope="col">
                  {humanizeKey(column)}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {content.map((item, index) => {
              const row = item as Record<string, unknown>;
              return (
                <tr key={index}>
                  {columns.map((column) => (
                    <td key={column}>
                      <AgentInlineValue value={row[column]} />
                    </td>
                  ))}
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    );
  }
  return (
    <ul className="agent-brief-list">
      {content.map((item, index) => (
        <li key={index}>
          <AgentBriefContent content={item} />
        </li>
      ))}
    </ul>
  );
}

function AgentObjectContent({ content }: { content: Record<string, unknown> }) {
  const entries = Object.entries(content);
  if (!entries.length) return <p className="agent-brief-muted">暂无字段。</p>;
  return (
    <dl className="agent-brief-object">
      {entries.map(([key, value]) => (
        <div key={key}>
          <dt>{humanizeKey(key)}</dt>
          <dd>
            <AgentBriefContent content={value} />
          </dd>
        </div>
      ))}
    </dl>
  );
}

function AgentInlineValue({ value }: { value: unknown }) {
  if (value === null || value === undefined) return <span>—</span>;
  if (typeof value === "string" || typeof value === "number") {
    return <span>{String(value)}</span>;
  }
  if (typeof value === "boolean") return <span>{value ? "是" : "否"}</span>;
  return <code>{JSON.stringify(value)}</code>;
}

function streamStatusTitle(status: StreamStatus, isStreaming: boolean) {
  if (status === "complete") return "Agent 运行完成";
  if (status === "cancel_requested") return "正在请求取消";
  if (status === "cancelled") return "Agent 运行已取消";
  if (status === "error") return "Agent 运行失败";
  if (isStreaming) return "Agent 正在调研";
  return "等待启动";
}

function streamStatusDescription(
  status: StreamStatus,
  cancelRequested: boolean
) {
  if (status === "complete") return "所有已验证 brief section 已发送完毕。";
  if (status === "cancelled") return "后端已停止后续 provider/tool 调用，并写入 cancelled trace。";
  if (status === "error") return "请检查后端、模型配置或工具门禁。";
  if (cancelRequested) return "取消请求已发送，等待当前阻塞调用返回或超时。";
  return "前端正在读取 fetch + ReadableStream SSE 事件。";
}

function eventTypeLabel(type: string) {
  const labels: Record<string, string> = {
    run_started: "运行开始",
    information_plan: "信息计划",
    phase_changed: "阶段切换",
    provider_call_started: "模型调用开始",
    provider_call_finished: "模型调用结束",
    tool_call_started: "工具调用开始",
    tool_result: "工具结果",
    evidence_registered: "证据登记",
    warning: "警告",
    brief_validated: "Brief 已验证",
    brief_section: "Brief 章节",
    cancelled: "已取消",
    complete: "完成",
    error: "错误"
  };
  return labels[type] || humanizeKey(type);
}

function eventSummary(event: AgentSseEvent) {
  const payload = event.payload;
  const direct =
    stringFromPayload(payload, "phase") ||
    stringFromPayload(payload, "tool_name") ||
    stringFromPayload(payload, "section") ||
    stringFromPayload(payload, "status") ||
    stringFromPayload(payload, "final_status") ||
    stringFromPayload(payload, "error_type") ||
    stringFromPayload(payload, "detail");
  if (direct) return direct;
  const step = numberFromPayload(payload, "step");
  return step === null ? event.timestamp : `step ${step}`;
}

function sortBriefSections(sections: AgentBriefSection[]) {
  return [...sections].sort((left, right) => {
    const leftIndex = briefSectionOrder.indexOf(left.section);
    const rightIndex = briefSectionOrder.indexOf(right.section);
    const normalizedLeft =
      leftIndex === -1 ? Number.MAX_SAFE_INTEGER : leftIndex;
    const normalizedRight =
      rightIndex === -1 ? Number.MAX_SAFE_INTEGER : rightIndex;
    return normalizedLeft - normalizedRight || left.sequence - right.sequence;
  });
}

function serializeBriefSections(sections: AgentBriefSection[]) {
  return sections
    .map((section) => {
      const title = briefSectionTitles[section.section] || humanizeKey(section.section);
      return `## ${title}\n\n${serializeBriefContent(section.content)}`;
    })
    .join("\n\n");
}

function serializeBriefContent(content: unknown): string {
  if (content === null || content === undefined) return "";
  if (
    typeof content === "string" ||
    typeof content === "number" ||
    typeof content === "boolean"
  ) {
    return String(content);
  }
  return JSON.stringify(content, null, 2);
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

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

function createAgentSessionId() {
  return `agent-ui-${Date.now().toString(36)}-${Math.random()
    .toString(36)
    .slice(2, 10)}`;
}
