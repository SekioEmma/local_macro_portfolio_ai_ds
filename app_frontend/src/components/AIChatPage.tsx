import { useEffect, useRef, useState } from "react";
import type { FormEvent, KeyboardEvent } from "react";
import { fetchDeepSeekResearch } from "../api/client";
import type {
  AIAnswerMode,
  AIDeepSeekResearchResponse,
  AIDetailLevel,
  ApiResult
} from "../types";
import { AIChatResult, type ChatCopyState } from "./AIChatResult";
import { ResearchIcon } from "./ResearchIcon";
import {
  BoundaryNotice,
  EmptyState,
  ErrorState,
  PageHeader
} from "./ResearchUI";

const modeOptions: Array<{ key: AIAnswerMode; label: string }> = [
  { key: "daily_brief", label: "每日简报" },
  { key: "risk_review", label: "风险复核" },
  { key: "scenario_review", label: "情景解释" },
  { key: "portfolio_overlay", label: "组合暴露" },
  { key: "evidence_audit", label: "证据审计" },
  { key: "research_memo", label: "研究备忘" }
];

const detailOptions: Array<{ key: AIDetailLevel; label: string }> = [
  { key: "brief", label: "简要" },
  { key: "standard", label: "标准" },
  { key: "deep", label: "深度" }
];

export function AIChatPage() {
  const [answerMode, setAnswerMode] = useState<AIAnswerMode>("risk_review");
  const [detailLevel, setDetailLevel] =
    useState<AIDetailLevel>("standard");
  const [question, setQuestion] = useState("");
  const [result, setResult] =
    useState<ApiResult<AIDeepSeekResearchResponse> | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [elapsed, setElapsed] = useState(0);
  const [copyState, setCopyState] = useState<ChatCopyState>("idle");
  const [questionError, setQuestionError] = useState<string | null>(null);
  const activeRequest = useRef<AbortController | null>(null);

  const trimmedQuestion = question.trim();
  const canSubmit =
    trimmedQuestion.length >= 2 &&
    trimmedQuestion.length <= 500 &&
    !isLoading;

  useEffect(() => {
    if (!isLoading) return;
    setElapsed(0);
    const startedAt = Date.now();
    const intervalId = window.setInterval(() => {
      setElapsed(Math.floor((Date.now() - startedAt) / 1000));
    }, 1000);
    return () => window.clearInterval(intervalId);
  }, [isLoading]);

  useEffect(
    () => () => {
      activeRequest.current?.abort();
      activeRequest.current = null;
    },
    []
  );

  async function submitResearch(event?: FormEvent) {
    event?.preventDefault();
    if (trimmedQuestion.length < 2) {
      setQuestionError("问题至少需要 2 个字符。");
      return;
    }
    if (trimmedQuestion.length > 500) {
      setQuestionError("问题不能超过 500 个字符。");
      return;
    }

    setQuestionError(null);
    setCopyState("idle");
    setResult(null);
    setIsLoading(true);
    activeRequest.current?.abort();
    const controller = new AbortController();
    activeRequest.current = controller;

    try {
      const response = await fetchDeepSeekResearch(
        answerMode,
        detailLevel,
        trimmedQuestion,
        controller.signal
      );
      if (!controller.signal.aborted) setResult(response);
    } finally {
      if (activeRequest.current === controller) {
        activeRequest.current = null;
        setIsLoading(false);
      }
    }
  }

  function handleQuestionKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === "Enter" && (event.ctrlKey || event.metaKey)) {
      event.preventDefault();
      if (canSubmit) void submitResearch();
    }
  }

  async function copyMemo() {
    const memo = result?.data?.deepseek_memo_output;
    if (!memo) return;
    try {
      await navigator.clipboard.writeText(memo);
      setCopyState("copied");
      window.setTimeout(() => setCopyState("idle"), 1800);
    } catch {
      setCopyState("error");
    }
  }

  return (
    <section className="chat-page">
      <PageHeader
        eyebrow="DEEPSEEK SINGLE-TURN RESEARCH · EXPLICIT SEND"
        title="AI 宏观研究"
        subtitle="基于本地证据的 DeepSeek 单轮分析"
      />

      <BoundaryNotice title="外部模型调用与人工复核" tone="warning">
        只有点击“发送分析”后，经过筛选的本地证据上下文和当前问题才会发送至
        DeepSeek。简短问候由本地直接回应；研究回答默认不保存、不搜索，并需要人工复核。
      </BoundaryNotice>

      <form className="chat-controls" onSubmit={submitResearch}>
        <div className="chat-control-row">
          <label className="chat-field">
            <span>分析模式</span>
            <select
              disabled={isLoading}
              onChange={(event) =>
                setAnswerMode(event.target.value as AIAnswerMode)
              }
              value={answerMode}
            >
              {modeOptions.map((option) => (
                <option key={option.key} value={option.key}>
                  {option.label}
                </option>
              ))}
            </select>
          </label>
          <label className="chat-field">
            <span>详细程度</span>
            <select
              disabled={isLoading}
              onChange={(event) =>
                setDetailLevel(event.target.value as AIDetailLevel)
              }
              value={detailLevel}
            >
              {detailOptions.map((option) => (
                <option key={option.key} value={option.key}>
                  {option.label}
                </option>
              ))}
            </select>
          </label>
        </div>

        <label className="chat-question-field" htmlFor="ai-research-question">
          <span>宏观研究问题</span>
          <textarea
            aria-describedby="chat-question-help chat-question-error"
            aria-invalid={Boolean(questionError)}
            disabled={isLoading}
            id="ai-research-question"
            maxLength={500}
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

        <div className="chat-submit-row">
          <div>
            <span id="chat-question-help">Ctrl / ⌘ + Enter 发送</span>
            <span
              className={question.length >= 480 ? "chat-is-near-limit" : ""}
            >
              {question.length} / 500
            </span>
          </div>
          <button
            className="chat-submit-button"
            disabled={!canSubmit}
            type="submit"
          >
            {isLoading ? (
              <>
                <span className="chat-spinner" aria-hidden="true" />
                分析中 · {elapsed}s
              </>
            ) : (
              <>
                <ResearchIcon name="ai" size={17} />
                发送分析
              </>
            )}
          </button>
        </div>
        <p className="chat-field-error" id="chat-question-error" role="alert">
          {questionError || ""}
        </p>
      </form>

      <section className="chat-result-panel" aria-live="polite">
        {isLoading ? (
          <ChatLoadingState elapsed={elapsed} />
        ) : result?.error || (result && !result.data) ? (
          <ErrorState
            title="AI 研究请求失败"
            message={
              result?.error ||
              "后端未返回可用结果，请检查本地服务和 DeepSeek 配置后重试。"
            }
          />
        ) : result?.data ? (
          <AIChatResult
            data={result.data}
            onCopy={copyMemo}
            copyState={copyState}
          />
        ) : (
          <EmptyState
            icon="ai"
            title="开始一次单轮研究"
            description="选择分析模式，输入宏观研究问题，AI 将基于本地证据库进行单轮分析。"
          />
        )}
      </section>
    </section>
  );
}

function ChatLoadingState({ elapsed }: { elapsed: number }) {
  return (
    <section className="chat-loading-state" role="status">
      <span className="chat-loading-mark">
        <ResearchIcon name="ai" size={24} />
      </span>
      <div>
        <h2>DeepSeek 正在分析相关证据</h2>
        <p>系统会按问题和详细程度控制上下文与输出长度。</p>
      </div>
      <strong>{elapsed}s</strong>
    </section>
  );
}
