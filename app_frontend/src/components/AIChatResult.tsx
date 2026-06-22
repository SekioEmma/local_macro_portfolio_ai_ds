import { useMemo, useState } from "react";
import type { AIDeepSeekResearchResponse } from "../types";
import { renderSafeMarkdown } from "../utils/safeMarkdown";
import { ResearchIcon } from "./ResearchIcon";
import { BoundaryNotice, humanizeKey } from "./ResearchUI";

export type ChatCopyState = "idle" | "copied" | "error";

export function AIChatResult({
  data,
  onCopy,
  copyState
}: {
  data: AIDeepSeekResearchResponse;
  onCopy: () => Promise<void>;
  copyState: ChatCopyState;
}) {
  if (data.response_kind === "guidance") {
    return <GuidanceResult data={data} />;
  }
  return <ResearchResult data={data} onCopy={onCopy} copyState={copyState} />;
}

function GuidanceResult({ data }: { data: AIDeepSeekResearchResponse }) {
  return (
    <section className="chat-guidance-result">
      <span className="chat-guidance-icon">
        <ResearchIcon name="ai" size={23} />
      </span>
      <div>
        <p className="chat-kicker">LOCAL INTENT ROUTER</p>
        <h2>这里更适合具体的研究问题</h2>
        <p>{data.deepseek_memo_output}</p>
        <small>本次未调用 DeepSeek，也未发送本地研究上下文。</small>
      </div>
    </section>
  );
}

function ResearchResult({
  data,
  onCopy,
  copyState
}: {
  data: AIDeepSeekResearchResponse;
  onCopy: () => Promise<void>;
  copyState: ChatCopyState;
}) {
  const renderedMemo = useMemo(
    () => renderSafeMarkdown(data.deepseek_memo_output),
    [data.deepseek_memo_output]
  );

  return (
    <div className="chat-result-content">
      <div className="chat-review-alert">
        <ResearchIcon name="shield" size={18} />
        <div>
          <strong>此分析仅供参考，需要人工复核</strong>
          <span>
            {data.not_saved_by_default
              ? "结果默认不保存"
              : "请检查本地保存策略"}
          </span>
        </div>
      </div>

      <div className="chat-status-strip">
        <StatusItem label="模型" value={data.model_provider} />
        <StatusItem
          label="耗时"
          value={
            data.elapsed_seconds === null
              ? "未提供"
              : `${data.elapsed_seconds.toFixed(1)}s`
          }
        />
        <StatusItem label="结束原因" value={data.finish_reason} />
        <StatusItem
          danger={data.output_blocked}
          label="输出状态"
          value={data.output_blocked ? "已阻断" : "已通过输出门禁"}
        />
      </div>

      {data.output_blocked && (
        <section className="chat-blocked-warning" role="alert">
          <ResearchIcon name="diagnostics" size={19} />
          <div>
            <strong>输出已被安全规则阻断</strong>
            <p>请展开“验证结果”查看具体原因，不要将该输出作为研究结论。</p>
          </div>
        </section>
      )}

      <article className="chat-memo">
        <header>
          <div>
            <p className="chat-kicker">SANITIZED DEEPSEEK MEMO</p>
            <h2>研究备忘</h2>
          </div>
          <div className="chat-copy-control">
            <button
              aria-label="复制研究备忘"
              disabled={!data.deepseek_memo_output}
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
                  : "复制"}
            </button>
            <span role="status">
              {copyState === "error"
                ? "浏览器未允许写入剪贴板，请检查权限。"
                : ""}
            </span>
          </div>
        </header>
        {data.deepseek_memo_output ? (
          <div
            className="chat-markdown"
            dangerouslySetInnerHTML={{ __html: renderedMemo }}
          />
        ) : (
          <p className="chat-no-memo">
            当前请求未生成可展示的清洗后正文，请查看验证结果。
          </p>
        )}
      </article>

      <div className="chat-disclosures">
        <details>
          <summary>
            <span>Claim 元数据</span>
            <strong>{data.claim_metadata.total_claims} 条</strong>
          </summary>
          <div className="chat-disclosure-body chat-table-grid">
            <CountTable
              title="Claim 类型"
              values={data.claim_metadata.claim_type_counts}
            />
            <CountTable
              title="阈值来源"
              values={data.claim_metadata.threshold_source_counts}
            />
          </div>
        </details>

        <details>
          <summary>
            <span>Prompt 上下文</span>
            <strong>{data.prompt_budget.selected_card_count} 张卡片</strong>
          </summary>
          <div className="chat-disclosure-body">
            <dl className="chat-fact-grid">
              <Fact
                label="选中卡片"
                value={`${data.prompt_budget.selected_card_count} / ${data.prompt_budget.card_limit}`}
              />
              <Fact
                label="估算 Token"
                value={`${data.prompt_budget.estimated_token_count.toLocaleString()} / ${data.prompt_budget.estimated_token_limit.toLocaleString()}`}
              />
              <Fact
                label="预算状态"
                value={data.prompt_budget.ready ? "Ready" : "Not ready"}
              />
              <Fact
                label="事实 / 模型输出"
                value={`${data.context_used_summary.included_fact_count} / ${data.context_used_summary.included_model_output_count}`}
              />
            </dl>
            <p className="chat-selection-note">
              实际选中 {data.selected_prompt_context.selected_cards.length} 张上下文卡片；
              未选入 {data.prompt_budget.omitted_card_count} 张。
            </p>
            <LazyPromptDetails promptText={data.prompt_text} />
          </div>
        </details>

        <details>
          <summary>
            <span>验证结果</span>
            <strong>
              {data.semantic_validator_result.passed ? "通过" : "需复核"}
            </strong>
          </summary>
          <div className="chat-disclosure-body">
            <ValidationSummary data={data} />
          </div>
        </details>

        <details>
          <summary>
            <span>隐私与安全</span>
            <strong>{data.human_review_required ? "人工复核" : "未标记"}</strong>
          </summary>
          <div className="chat-disclosure-body">
            <dl className="chat-privacy-list">
              {Object.entries(data.privacy_summary).map(([key, value]) => (
                <div key={key}>
                  <dt>{humanizeKey(key)}</dt>
                  <dd className={value ? "chat-is-true" : "chat-is-false"}>
                    {value ? "是" : "否"}
                  </dd>
                </div>
              ))}
            </dl>
            <BoundaryNotice title="解释边界">
              {data.interpretation_boundary}
            </BoundaryNotice>
          </div>
        </details>
      </div>

      <BoundaryNotice title="研究输出边界" tone="warning">
        {data.interpretation_boundary}
      </BoundaryNotice>
    </div>
  );
}

function LazyPromptDetails({ promptText }: { promptText: string }) {
  const [hasOpened, setHasOpened] = useState(false);
  return (
    <details
      className="chat-prompt-debug"
      onToggle={(event) => {
        if (event.currentTarget.open) setHasOpened(true);
      }}
    >
      <summary>完整 Prompt（调试信息，仅本地可见）</summary>
      {hasOpened && <pre>{promptText}</pre>}
    </details>
  );
}

function ValidationSummary({ data }: { data: AIDeepSeekResearchResponse }) {
  const findings = data.semantic_validator_result.findings;
  return (
    <div className="chat-validation">
      <div className="chat-validation-overview">
        <span
          className={
            data.semantic_validator_result.passed
              ? "chat-is-passed"
              : "chat-is-failed"
          }
        >
          {data.semantic_validator_result.passed ? "语义校验通过" : "语义校验未通过"}
        </span>
        <span>
          输入校验：{data.input_validation_passed ? "通过" : "未通过"}
        </span>
        <span>基础隐私校验：{data.validator_result.passed ? "通过" : "未通过"}</span>
      </div>

      {findings.length > 0 ? (
        <ul>
          {findings.map((finding, index) => (
            <li
              className={`chat-severity-${finding.severity}`}
              key={`${finding.code}-${index}`}
            >
              <strong>
                {finding.severity.toUpperCase()} · {finding.code}
              </strong>
              <p>{finding.message_zh}</p>
            </li>
          ))}
        </ul>
      ) : (
        <p>没有语义校验发现。</p>
      )}

      {data.input_validation_findings.length > 0 && (
        <section>
          <h3>输入校验发现</h3>
          <ul>
            {data.input_validation_findings.map((finding) => (
              <li key={finding}>{finding}</li>
            ))}
          </ul>
        </section>
      )}

      {(data.validator_result.blocked_terms.length > 0 ||
        data.validator_result.privacy_findings.length > 0) && (
        <section>
          <h3>基础验证发现</h3>
          <ul>
            {[
              ...data.validator_result.blocked_terms,
              ...data.validator_result.privacy_findings
            ].map((finding) => (
              <li key={finding}>{finding}</li>
            ))}
          </ul>
        </section>
      )}
    </div>
  );
}

function CountTable({
  title,
  values
}: {
  title: string;
  values: Record<string, number>;
}) {
  const entries = Object.entries(values);
  return (
    <section className="chat-count-table">
      <h3>{title}</h3>
      {entries.length ? (
        <table>
          <thead>
            <tr>
              <th scope="col">类别</th>
              <th scope="col">数量</th>
            </tr>
          </thead>
          <tbody>
            {entries.map(([key, value]) => (
              <tr key={key}>
                <td>{humanizeKey(key)}</td>
                <td>{value}</td>
              </tr>
            ))}
          </tbody>
        </table>
      ) : (
        <p>暂无数据。</p>
      )}
    </section>
  );
}

function StatusItem({
  label,
  value,
  danger = false
}: {
  label: string;
  value: string;
  danger?: boolean;
}) {
  return (
    <div className={danger ? "chat-is-danger" : ""}>
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function Fact({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <dt>{label}</dt>
      <dd>{value}</dd>
    </div>
  );
}
