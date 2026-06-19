import { useEffect, useMemo, useState } from "react";
import type { KeyboardEvent } from "react";
import {
  fetchAIPromptPreview,
  fetchAIResearchPreview
} from "../api/client";
import type {
  AIAnswerMode,
  AIContextCard,
  AIContextManifestResponse,
  AIDetailLevel,
  AIPromptPreviewResponse,
  AIResearchPreviewResponse,
  AIResearchValidationResult,
  ApiResult
} from "../types";
import { compactText } from "../utils/evidence";
import { ResearchIcon } from "./ResearchIcon";
import {
  BoundaryNotice,
  ErrorState,
  formatTimestamp,
  LoadingState,
  MetaStrip,
  PageHeader,
  SourceBadge,
  StatusBadge,
  humanizeKey
} from "./ResearchUI";

type LocalResearchPreviewPageProps = {
  manifest: ApiResult<AIContextManifestResponse>;
  isLoading: boolean;
};

type ResearchTab = "catalogue" | "research" | "prompt";
type CopyState = "idle" | "copied" | "error";

const researchTabs: ResearchTab[] = ["catalogue", "research", "prompt"];

const modeOptions: Array<{
  key: AIAnswerMode;
  label: string;
  description: string;
}> = [
  {
    key: "daily_brief",
    label: "每日简报",
    description: "市场状态、压力来源与观察指标"
  },
  {
    key: "risk_review",
    label: "风险复核",
    description: "普通回调、宏观压力与系统性风险边界"
  },
  {
    key: "scenario_review",
    label: "情景解释",
    description: "假设传导、受影响证据组与不确定条件"
  },
  {
    key: "portfolio_overlay",
    label: "组合暴露",
    description: "本地紧凑上下文的风险通道解释"
  },
  {
    key: "evidence_audit",
    label: "证据审计",
    description: "可用事实、模型输出与排除约束"
  },
  {
    key: "research_memo",
    label: "投研报告",
    description: "完整的中文宏观证据复核"
  }
];

const detailOptions: Array<{ key: AIDetailLevel; label: string }> = [
  { key: "brief", label: "简要" },
  { key: "standard", label: "标准" },
  { key: "deep", label: "深入" }
];

export function LocalResearchPreviewPage({
  manifest,
  isLoading
}: LocalResearchPreviewPageProps) {
  const [activeTab, setActiveTab] = useState<ResearchTab>("catalogue");
  const [answerMode, setAnswerMode] = useState<AIAnswerMode>("risk_review");
  const [detailLevel, setDetailLevel] =
    useState<AIDetailLevel>("standard");
  const [researchCache, setResearchCache] = useState<
    Record<string, ApiResult<AIResearchPreviewResponse>>
  >({});
  const [promptCache, setPromptCache] = useState<
    Record<string, ApiResult<AIPromptPreviewResponse>>
  >({});
  const [pendingKey, setPendingKey] = useState<string | null>(null);
  const [copyState, setCopyState] = useState<CopyState>("idle");

  const cacheKey = `${answerMode}:${detailLevel}`;

  useEffect(() => {
    if (activeTab === "catalogue") return;
    if (activeTab === "research" && researchCache[cacheKey]) return;
    if (activeTab === "prompt" && promptCache[cacheKey]) return;
    let cancelled = false;
    setPendingKey(`${activeTab}:${cacheKey}`);
    if (activeTab === "research") {
      fetchAIResearchPreview(answerMode, detailLevel)
        .then((result) => {
          if (cancelled) return;
          setResearchCache((current) => ({ ...current, [cacheKey]: result }));
        })
        .finally(() => {
          if (!cancelled) setPendingKey(null);
        });
    } else {
      fetchAIPromptPreview(answerMode, detailLevel)
        .then((result) => {
          if (cancelled) return;
          setPromptCache((current) => ({ ...current, [cacheKey]: result }));
        })
        .finally(() => {
          if (!cancelled) setPendingKey(null);
        });
    }
    return () => {
      cancelled = true;
    };
  }, [
    activeTab,
    answerMode,
    cacheKey,
    detailLevel,
    promptCache,
    researchCache
  ]);

  if (isLoading) {
    return <LoadingState title="正在读取本地受控投研上下文" />;
  }
  if (manifest.error || !manifest.data) {
    return (
      <ErrorState
        title="本地受控投研预览暂不可用"
        message={manifest.error}
      />
    );
  }

  const data = manifest.data;
  const catalogue = data.full_context_catalogue;
  const researchResult = researchCache[cacheKey];
  const promptResult = promptCache[cacheKey];
  const currentPending = pendingKey === `${activeTab}:${cacheKey}`;

  function handleTabKeyDown(
    event: KeyboardEvent<HTMLButtonElement>,
    currentTab: ResearchTab
  ) {
    const currentIndex = researchTabs.indexOf(currentTab);
    let nextIndex: number | null = null;
    if (event.key === "ArrowRight" || event.key === "ArrowDown") {
      nextIndex = (currentIndex + 1) % researchTabs.length;
    } else if (event.key === "ArrowLeft" || event.key === "ArrowUp") {
      nextIndex = (currentIndex - 1 + researchTabs.length) % researchTabs.length;
    } else if (event.key === "Home") {
      nextIndex = 0;
    } else if (event.key === "End") {
      nextIndex = researchTabs.length - 1;
    }
    if (nextIndex === null) return;
    event.preventDefault();
    const nextTab = researchTabs[nextIndex];
    setActiveTab(nextTab);
    window.requestAnimationFrame(() => {
      document.getElementById(`research-tab-${nextTab}`)?.focus();
    });
  }

  return (
    <section className="controlled-research-page">
      <PageHeader
        eyebrow="LOCAL CONTROLLED RESEARCH PREVIEW · READ ONLY"
        subtitle="可信证据 → Manifest → 压缩上下文 → 中文研究模板 → 分级语义校验 → 人工复核"
        title="本地受控投研预览"
      />
      <MetaStrip
        items={[
          {
            label: "CONTEXT ID",
            value: data.generated_at
              ? `CTX-${data.generated_at.replace(/\D/g, "").slice(0, 12)}`
              : "not available"
          },
          { label: "GENERATED AT", value: formatTimestamp(data.generated_at) },
          {
            label: "FULL CATALOGUE",
            value: catalogue ? `${catalogue.total_card_count} 张卡片` : "—"
          },
          {
            label: "MODEL DESTINATION",
            value: compactText(data.model_destination.destination)
          },
          {
            label: "SAFETY",
            value: <StatusBadge status="ok" />
          }
        ]}
      />
      <BoundaryNotice title="本地确定性研究预览层">
        当前页面不提供自由聊天，不调用外部模型或搜索，不保存问题、Prompt
        或回答，不读取持仓明细，也不提供交易动作、概率或收益预测。
      </BoundaryNotice>

      <div className="research-workbench-tabs" role="tablist" aria-label="投研预览视图">
        <TabButton
          active={activeTab === "catalogue"}
          icon="database"
          label="上下文清单"
          onClick={() => setActiveTab("catalogue")}
          onKeyDown={handleTabKeyDown}
          tabKey="catalogue"
        />
        <TabButton
          active={activeTab === "research"}
          icon="evidence"
          label="本地研究预览"
          onClick={() => setActiveTab("research")}
          onKeyDown={handleTabKeyDown}
          tabKey="research"
        />
        <TabButton
          active={activeTab === "prompt"}
          icon="layers"
          label="提示词预览"
          onClick={() => setActiveTab("prompt")}
          onKeyDown={handleTabKeyDown}
          tabKey="prompt"
        />
      </div>

      {activeTab !== "catalogue" && (
        <ResearchControls
          answerMode={answerMode}
          detailLevel={detailLevel}
          onAnswerModeChange={setAnswerMode}
          onDetailLevelChange={setDetailLevel}
        />
      )}

      {activeTab === "catalogue" && (
        <div
          aria-labelledby="research-tab-catalogue"
          id="research-panel-catalogue"
          role="tabpanel"
          tabIndex={0}
        >
          <CatalogueView data={data} catalogue={catalogue} />
        </div>
      )}
      {activeTab === "research" &&
        <div
          aria-labelledby="research-tab-research"
          id="research-panel-research"
          role="tabpanel"
          tabIndex={0}
        >
          {currentPending && !researchResult ? (
            <LoadingState title="正在生成本地确定性研究预览" />
          ) : (
            <ResearchPreviewView result={researchResult} />
          )}
        </div>}
      {activeTab === "prompt" &&
        <div
          aria-labelledby="research-tab-prompt"
          id="research-panel-prompt"
          role="tabpanel"
          tabIndex={0}
        >
          {currentPending && !promptResult ? (
            <LoadingState title="正在组装 Selected Prompt Context" />
          ) : (
            <PromptPreviewView
              copyState={copyState}
              fullCatalogueCount={catalogue?.total_card_count || 0}
              onCopy={async () => {
                const text = promptResult?.data?.prompt_text;
                if (!text) return;
                try {
                  await navigator.clipboard.writeText(text);
                  setCopyState("copied");
                  window.setTimeout(() => setCopyState("idle"), 1800);
                } catch {
                  setCopyState("error");
                }
              }}
              result={promptResult}
            />
          )}
        </div>}
    </section>
  );
}

function TabButton({
  active,
  icon,
  label,
  onClick,
  onKeyDown,
  tabKey
}: {
  active: boolean;
  icon: "database" | "evidence" | "layers";
  label: string;
  onClick: () => void;
  onKeyDown: (
    event: KeyboardEvent<HTMLButtonElement>,
    tab: ResearchTab
  ) => void;
  tabKey: ResearchTab;
}) {
  return (
    <button
      aria-controls={`research-panel-${tabKey}`}
      aria-selected={active}
      className={active ? "is-active" : ""}
      id={`research-tab-${tabKey}`}
      onClick={onClick}
      onKeyDown={(event) => onKeyDown(event, tabKey)}
      role="tab"
      tabIndex={active ? 0 : -1}
      type="button"
    >
      <ResearchIcon name={icon} />
      <span>{label}</span>
    </button>
  );
}

function ResearchControls({
  answerMode,
  detailLevel,
  onAnswerModeChange,
  onDetailLevelChange
}: {
  answerMode: AIAnswerMode;
  detailLevel: AIDetailLevel;
  onAnswerModeChange: (mode: AIAnswerMode) => void;
  onDetailLevelChange: (level: AIDetailLevel) => void;
}) {
  return (
    <section className="research-mode-panel" aria-label="研究模式">
      <div className="research-mode-grid">
        {modeOptions.map((option) => (
          <button
            key={option.key}
            aria-pressed={answerMode === option.key}
            className={answerMode === option.key ? "is-active" : ""}
            onClick={() => onAnswerModeChange(option.key)}
            type="button"
          >
            <strong>{option.label}</strong>
            <span>{option.description}</span>
          </button>
        ))}
      </div>
      <div className="research-detail-control" aria-label="详细程度">
        <span>详细程度</span>
        {detailOptions.map((option) => (
          <button
            key={option.key}
            aria-pressed={detailLevel === option.key}
            className={detailLevel === option.key ? "is-active" : ""}
            onClick={() => onDetailLevelChange(option.key)}
            type="button"
          >
            {option.label}
          </button>
        ))}
      </div>
    </section>
  );
}

function CatalogueView({
  data,
  catalogue
}: {
  data: AIContextManifestResponse;
  catalogue: AIContextManifestResponse["full_context_catalogue"];
}) {
  const cards = useMemo(() => {
    if (!catalogue) return [];
    return [
      ...catalogue.evidence_cards,
      ...catalogue.model_output_cards,
      ...catalogue.excluded_constraint_cards
    ].sort(
      (left, right) =>
        left.priority - right.priority ||
        left.module.localeCompare(right.module) ||
        left.metric_key.localeCompare(right.metric_key)
    );
  }, [catalogue]);

  if (!catalogue) {
    return (
      <ErrorState
        title="完整上下文目录尚未生成"
        message="请确认本地后端已升级到 AI-1 contract。"
      />
    );
  }

  return (
    <div className="catalogue-layout">
      <section className="catalogue-main-column">
        <div className="catalogue-summary-grid">
          <SummaryCell label="完整目录" value={`${catalogue.total_card_count}`} />
          <SummaryCell
            label="可用事实"
            value={`${catalogue.evidence_cards.length}`}
          />
          <SummaryCell
            label="模型输出"
            value={`${catalogue.model_output_cards.length}`}
          />
          <SummaryCell
            label="排除约束"
            value={`${catalogue.excluded_constraint_cards.length}`}
          />
        </div>
        {[1, 2, 3, 4].map((priority) => (
          <CataloguePriorityGroup
            key={priority}
            cards={cards.filter((card) => card.priority === priority)}
            defaultOpen={priority === 1}
            priority={priority}
          />
        ))}
      </section>
      <aside className="catalogue-audit-column">
        <DistributionCard
          title="P1–P4 分布"
          values={catalogue.priority_counts}
        />
        <DistributionCard
          title="来源分布"
          values={catalogue.source_badge_distribution}
        />
        <DistributionCard
          title="排除原因"
          values={catalogue.excluded_reason_distribution}
        />
        <PolicyObjectCard title="组合上下文策略" data={data.portfolio_context_policy} />
        <PolicyObjectCard title="隐私策略" data={data.privacy_policy} />
        <PolicyObjectCard title="搜索策略" data={data.search_policy} />
        <PolicyListCard title="风险边界" values={data.risk_boundaries} />
      </aside>
    </div>
  );
}

function CataloguePriorityGroup({
  cards,
  defaultOpen,
  priority
}: {
  cards: AIContextCard[];
  defaultOpen: boolean;
  priority: number;
}) {
  const [open, setOpen] = useState(defaultOpen);
  const [visible, setVisible] = useState(24);
  const shown = open ? cards.slice(0, visible) : [];
  return (
    <section className={`catalogue-priority-group priority-${priority}`}>
      <button
        aria-expanded={open}
        className="catalogue-priority-heading"
        onClick={() => setOpen((current) => !current)}
        type="button"
      >
        <div>
          <span>P{priority}</span>
          <strong>{priorityLabel(priority)}</strong>
          <small>{cards.length} 张</small>
        </div>
        <ResearchIcon
          className={open ? "is-open" : ""}
          name="chevron"
          size={18}
        />
      </button>
      {open && (
        <div className="catalogue-card-list">
          {shown.map((card) => (
            <ContextCatalogueCard
              key={`${card.card_type}:${card.module}:${card.metric_key}`}
              card={card}
            />
          ))}
          {visible < cards.length && (
            <button
              className="catalogue-load-more"
              onClick={() => setVisible((current) => current + 24)}
              type="button"
            >
              继续显示 {Math.min(24, cards.length - visible)} 张
            </button>
          )}
        </div>
      )}
    </section>
  );
}

function ContextCatalogueCard({ card }: { card: AIContextCard }) {
  return (
    <article className={`context-catalogue-card card-${card.card_type}`}>
      <header>
        <div>
          <SourceBadge sourceBadge={card.source_badge || "missing"} />
          <strong>{card.display_name}</strong>
        </div>
        <StatusBadge status={card.status || "missing"} />
      </header>
      <p>{card.value_text || card.excluded_reason_display_zh || "不可用"}</p>
      <dl>
        <div>
          <dt>模块</dt>
          <dd>{card.module_display_zh}</dd>
        </div>
        <div>
          <dt>标识</dt>
          <dd>{card.metric_key}</dd>
        </div>
        <div>
          <dt>新鲜度</dt>
          <dd>{card.freshness_display_zh || card.freshness_status || "未知"}</dd>
        </div>
        <div>
          <dt>触发资格</dt>
          <dd>{card.trigger_eligibility_display_zh || "仅作审计"}</dd>
        </div>
      </dl>
      {(card.effect_zh || card.interpretation_boundary) && (
        <small>{card.effect_zh || card.interpretation_boundary}</small>
      )}
    </article>
  );
}

function ResearchPreviewView({
  result
}: {
  result?: ApiResult<AIResearchPreviewResponse>;
}) {
  if (!result) return null;
  if (result.error || !result.data) {
    return <ErrorState title="研究预览生成失败" message={result.error} />;
  }
  const data = result.data;
  return (
    <div className="research-preview-layout">
      <section className="research-paper">
        {data.semantic_validator_result.blocked ? (
          <BlockedPreviewNotice kind="研究正文" />
        ) : (
          <>
            <header className="research-paper-header">
              <div>
                <p className="research-kicker">DETERMINISTIC RESEARCH OUTPUT</p>
                <h2>{data.title}</h2>
              </div>
              <span>{data.legacy_memo_type}</span>
            </header>
            {data.research_sections.map((section) => (
              <article key={section.key} className="research-output-section">
                <h3>{section.title}</h3>
                <p>{section.content}</p>
                <ContextReferences values={section.source_context} />
              </article>
            ))}
            <BoundaryNotice title="解释边界">
              {data.interpretation_boundary}
            </BoundaryNotice>
          </>
        )}
      </section>
      <aside className="research-review-column">
        <BudgetCard budget={data.prompt_budget} />
        <ValidationPanel result={data.semantic_validator_result} />
        <section className="selection-note-card">
          <header>
            <ResearchIcon name="layers" />
            <h3>Selected Prompt Context</h3>
          </header>
          <strong>{data.selected_prompt_context.selected_cards.length} 张</strong>
          <ul>
            {data.selected_prompt_context.selection_notes.map((note) => (
              <li key={note}>{note}</li>
            ))}
          </ul>
        </section>
      </aside>
    </div>
  );
}

function PromptPreviewView({
  copyState,
  fullCatalogueCount,
  onCopy,
  result
}: {
  copyState: CopyState;
  fullCatalogueCount: number;
  onCopy: () => Promise<void>;
  result?: ApiResult<AIPromptPreviewResponse>;
}) {
  if (!result) return null;
  if (result.error || !result.data) {
    return <ErrorState title="提示词预览生成失败" message={result.error} />;
  }
  const data = result.data;
  return (
    <div className="prompt-preview-layout">
      <section className="prompt-document">
        {data.semantic_validator_result.blocked ? (
          <BlockedPreviewNotice kind="Prompt 内容" />
        ) : (
          <>
            <header className="prompt-document-header">
              <div>
                <p className="research-kicker">PROMPT PREVIEW · NO SEND</p>
                <h2>Selected Prompt Context</h2>
              </div>
              <div className="prompt-copy-control">
                <button
                  aria-describedby="prompt-copy-status"
                  onClick={onCopy}
                  type="button"
                >
                  <ResearchIcon
                    name={copyState === "copied" ? "check" : "copy"}
                  />
                  {copyState === "copied"
                    ? "已复制"
                    : copyState === "error"
                      ? "复制失败"
                      : "复制 Prompt"}
                </button>
                <span id="prompt-copy-status" role="status">
                  {copyState === "error"
                    ? "浏览器未允许写入剪贴板，请检查权限后重试。"
                    : ""}
                </span>
              </div>
            </header>
            <PromptBlock title="System Boundary" content={data.system_boundary} />
            <PromptBlock title="Task Instruction" content={data.task_instruction} />
            <PromptBlock
              title="Selected Context Cards"
              content={data.selected_prompt_context.selected_context_text}
              mono
            />
            <PromptList title="Output Contract" values={data.output_contract} />
          </>
        )}
      </section>
      <aside className="prompt-audit-column">
        <section className="catalogue-vs-selected-card">
          <h3>完整目录 / 实际选中</h3>
          <div>
            <span>完整目录</span>
            <strong>{fullCatalogueCount}</strong>
          </div>
          <div>
            <span>本次选中</span>
            <strong>{data.prompt_budget.selected_card_count}</strong>
          </div>
          <div>
            <span>未进入 Prompt</span>
            <strong>{data.prompt_budget.omitted_card_count}</strong>
          </div>
          <div>
            <span>P4 聚合约束</span>
            <strong>
              {data.selected_prompt_context.constraint_summary.total_count}
            </strong>
          </div>
          <DisclosureBreakdown
            label="按优先级遗漏"
            values={data.prompt_budget.omitted_by_priority}
          />
          <DisclosureBreakdown
            label="按原因遗漏"
            values={data.prompt_budget.omitted_by_reason}
          />
          <p>{data.selected_prompt_context.constraint_summary.summary_zh}</p>
        </section>
        <BudgetCard budget={data.prompt_budget} />
        <PromptList title="Preflight Checklist" values={data.preflight_checklist} />
        <ValidationPanel result={data.semantic_validator_result} />
      </aside>
    </div>
  );
}

function BlockedPreviewNotice({ kind }: { kind: string }) {
  return (
    <section className="research-blocked-notice" role="alert">
      <ResearchIcon name="shield" size={22} />
      <div>
        <h2>{kind}已阻断</h2>
        <p>
          检测到 blocker。正文与选中上下文已从响应中隐藏，请先查看右侧校验结果并完成人工复核。
        </p>
      </div>
    </section>
  );
}

function DisclosureBreakdown({
  label,
  values
}: {
  label: string;
  values: Record<string, number>;
}) {
  const entries = Object.entries(values);
  if (!entries.length) return null;
  return (
    <section className="prompt-disclosure-breakdown">
      <h4>{label}</h4>
      <dl>
        {entries.map(([key, value]) => (
          <div key={key}>
            <dt>{humanizeKey(key)}</dt>
            <dd>{value}</dd>
          </div>
        ))}
      </dl>
    </section>
  );
}

function BudgetCard({
  budget
}: {
  budget: AIResearchPreviewResponse["prompt_budget"];
}) {
  return (
    <section className="prompt-budget-card">
      <header>
        <ResearchIcon name={budget.ready ? "check" : "shield"} />
        <h3>Prompt 预算</h3>
        <span className={budget.ready ? "is-ready" : "is-not-ready"}>
          {budget.ready ? "ready" : "not ready"}
        </span>
      </header>
      <dl>
        <div>
          <dt>卡片</dt>
          <dd>
            {budget.selected_card_count} / {budget.card_limit}
          </dd>
        </div>
        <div>
          <dt>字符</dt>
          <dd>
            {budget.selected_char_count.toLocaleString()} /{" "}
            {budget.char_limit.toLocaleString()}
          </dd>
        </div>
        <div>
          <dt>估算 token</dt>
          <dd>
            {budget.estimated_token_count.toLocaleString()} /{" "}
            {budget.estimated_token_limit.toLocaleString()}
          </dd>
        </div>
        <div>
          <dt>遗漏披露</dt>
          <dd>{budget.omitted_card_count}</dd>
        </div>
      </dl>
      <small>{humanizeKey(budget.status_reason)}</small>
    </section>
  );
}

function ValidationPanel({
  result
}: {
  result: AIResearchValidationResult;
}) {
  return (
    <section className="semantic-validation-card" aria-live="polite">
      <header>
        <ResearchIcon name={result.blocked ? "shield" : "check"} />
        <h3>金融语义校验</h3>
        <span>{result.max_severity || "pass"}</span>
      </header>
      {result.findings.length ? (
        <ul>
          {result.findings.map((finding, index) => (
            <li
              key={`${finding.code}-${index}`}
              className={`severity-${finding.severity}`}
            >
              <strong>
                {finding.severity.toUpperCase()} · {finding.code}
              </strong>
              <p>{finding.message_zh}</p>
              {finding.required_context.length > 0 && (
                <small>
                  需要：{finding.required_context.join(" / ")}
                </small>
              )}
            </li>
          ))}
        </ul>
      ) : (
        <p>当前本地预览未发现语言、隐私或金融语义问题。</p>
      )}
    </section>
  );
}

function PromptBlock({
  title,
  content,
  mono = false
}: {
  title: string;
  content: string;
  mono?: boolean;
}) {
  return (
    <article className={`prompt-block ${mono ? "is-mono" : ""}`}>
      <h3>{title}</h3>
      <pre>{content}</pre>
    </article>
  );
}

function PromptList({ title, values }: { title: string; values: string[] }) {
  return (
    <section className="prompt-list-card">
      <h3>{title}</h3>
      <ul>
        {values.map((value) => (
          <li key={value}>
            <ResearchIcon name="check" size={15} />
            <span>{value}</span>
          </li>
        ))}
      </ul>
    </section>
  );
}

function ContextReferences({ values }: { values: string[] }) {
  if (!values.length) return null;
  return (
    <div className="context-reference-list" aria-label="引用上下文">
      {values.map((value) => (
        <span key={value}>{value}</span>
      ))}
    </div>
  );
}

function DistributionCard({
  title,
  values
}: {
  title: string;
  values: Record<string, number>;
}) {
  return (
    <section className="distribution-card">
      <h3>{title}</h3>
      <dl>
        {Object.entries(values).map(([key, value]) => (
          <div key={key}>
            <dt>{humanizeKey(key)}</dt>
            <dd>{value}</dd>
          </div>
        ))}
      </dl>
    </section>
  );
}

function PolicyObjectCard({
  title,
  data
}: {
  title: string;
  data: Record<string, unknown>;
}) {
  return (
    <section className="controlled-policy-card">
      <h3>{title}</h3>
      <dl>
        {Object.entries(data).map(([key, value]) => (
          <div key={key}>
            <dt>{humanizeKey(key)}</dt>
            <dd>{compactText(value)}</dd>
          </div>
        ))}
      </dl>
    </section>
  );
}

function PolicyListCard({ title, values }: { title: string; values: string[] }) {
  return (
    <section className="controlled-policy-card">
      <h3>{title}</h3>
      <ul>
        {values.map((value) => (
          <li key={value}>{value}</li>
        ))}
      </ul>
    </section>
  );
}

function SummaryCell({ label, value }: { label: string; value: string }) {
  return (
    <article>
      <span>{label}</span>
      <strong>{value}</strong>
    </article>
  );
}

function priorityLabel(priority: number) {
  return {
    1: "核心宏观状态",
    2: "通胀 / 增长 / 权益",
    3: "代理 / 解释 / 组合",
    4: "排除与缺失约束"
  }[priority];
}
