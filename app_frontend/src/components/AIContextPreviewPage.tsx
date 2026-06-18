import type {
  AIContextManifestResponse,
  ApiResult,
  DashboardEvidenceTableResponse,
  DashboardSummaryResponse
} from "../types";
import { getModuleLabel } from "../utils/displayLabels";
import { compactText } from "../utils/evidence";
import { ResearchIcon } from "./ResearchIcon";
import {
  BoundaryNotice,
  DisabledSurfaceNotice,
  ErrorState,
  formatTimestamp,
  LoadingState,
  MetaStrip,
  PageHeader,
  SourceBadge,
  StatusBadge,
  humanizeKey
} from "./ResearchUI";

type AIContextPreviewPageProps = {
  manifest: ApiResult<AIContextManifestResponse>;
  dashboard: ApiResult<DashboardSummaryResponse>;
  evidence: ApiResult<DashboardEvidenceTableResponse>;
  isLoading: boolean;
};

export function AIContextPreviewPage({
  manifest,
  dashboard,
  evidence,
  isLoading
}: AIContextPreviewPageProps) {
  if (isLoading) return <LoadingState title="正在读取 AI Context Manifest" />;
  if (manifest.error || !manifest.data) {
    return (
      <ErrorState
        title="AI Context Preview 暂不可用"
        message={manifest.error}
      />
    );
  }

  const data = manifest.data;
  const sourceSummary = data.source_summary;
  const pressureModules = Object.values(dashboard.data?.modules || {}).filter(
    (module) => ["watch", "pressure", "stress"].includes(module.status)
  );
  const blockedRows = (evidence.data?.rows || []).filter(
    (row) => !row.ai_context_allowed
  );

  return (
    <section className="ai-context-page">
      <PageHeader
        eyebrow="LOCAL MACRO RISK RESEARCH WORKBENCH · READ ONLY"
        subtitle="AI Context Preview 展示未来研究模型被允许消费什么、禁止消费什么；当前不调用外部模型。"
        title="AI 记忆（只读） / AI Context Preview"
      />
      <MetaStrip
        items={[
          {
            label: "CONTEXT ID",
            value: data.generated_at
              ? `CTX-${data.generated_at.replace(/\D/g, "").slice(0, 12)}`
              : "not available"
          },
          { label: "CREATED AT", value: formatTimestamp(data.generated_at) },
          {
            label: "MODEL DESTINATION",
            value: policyValue(data.model_destination, "destination")
          },
          {
            label: "DATA SNAPSHOT",
            value: formatTimestamp(dashboard.data?.generated_at)
          },
          {
            label: "SAFETY",
            value: <StatusBadge status="ok" />
          }
        ]}
      />

      <BoundaryNotice title="本模式为本地优先、只读研究环境">
        不提供交易动作、事件概率或市场方向判断；不调用外部搜索；不暴露完整账户或持仓明细；不保存对话。
      </BoundaryNotice>

      <div className="ai-context-layout">
        <section className="ai-preview-column">
          <article className="context-summary-card">
            <header>
              <p className="research-kicker">CURRENT CONTEXT SUMMARY</p>
              <h2>当前上下文摘要</h2>
              <span>只读</span>
            </header>
            <div className="context-summary-grid">
              <div>
                <span>宏观情境</span>
                <strong>
                  {dashboard.data?.overall_risk_level || "not available"}
                </strong>
              </div>
              <div>
                <span>主要压力</span>
                <strong>
                  {pressureModules.length
                    ? pressureModules
                        .map((module) => getModuleLabel(module.key))
                        .join(" / ")
                    : "未形成明确压力排序"}
                </strong>
              </div>
              <div>
                <span>数据质量</span>
                <strong>
                  included{" "}
                  {summaryNumber(sourceSummary, "included_facts_count")} ·
                  blocked {blockedRows.length}
                </strong>
              </div>
            </div>
          </article>

          <article className="research-thread-card">
            <header>
              <p className="research-kicker">RESEARCH THREAD · READ ONLY</p>
              <h2>研究对话预览</h2>
            </header>
            <div className="research-message system-message">
              <div>
                <strong>SYSTEM</strong>
                <small>{formatTimestamp(data.generated_at)}</small>
              </div>
              <p>
                仅使用 AI Context Manifest 中已纳入的事实与模型输出。缺失、过期、需研究、历史不足或被阻断的证据不作为 factual context。
              </p>
            </div>
            <div className="research-message assistant-message">
              <div>
                <strong>LOCAL PREVIEW</strong>
                <small>未调用外部模型</small>
              </div>
              <h3>当前宏观风险上下文</h3>
              <p>
                当前上下文包含 {data.included_facts.length} 条事实和{" "}
                {data.included_model_outputs.length} 条模型输出。主要压力与数据质量仅基于当前本地证据摘要；任何被排除项仍在右侧清单中可审计。
              </p>
              <ul>
                <li>压力来源：以 Dashboard module status 与模型输出为依据。</li>
                <li>数据约束：{blockedRows.length} 行证据未进入 factual context。</li>
                <li>组合上下文：仅允许 sanitized compact context。</li>
              </ul>
            </div>
            <DisabledSurfaceNotice
              description="此页面没有可发送输入，不调用 DeepSeek、Tavily 或其他外部模型，也不保存 prompt 或对话历史。"
              title="真实 AI 对话未启用"
            />
          </article>
        </section>

        <section className="manifest-column">
          <ManifestListCard
            items={data.included_facts}
            title="已纳入事实"
            tone="included"
          />
          <ManifestListCard
            items={data.excluded_facts}
            title="已排除事实"
            tone="excluded"
          />
          <ManifestListCard
            items={data.included_model_outputs}
            title="已纳入模型输出"
            tone="model"
          />
          <ManifestListCard
            items={data.excluded_model_outputs}
            title="已排除模型输出"
            tone="excluded"
          />
          <PolicyCard title="风险边界" values={data.risk_boundaries} />
          <PolicyObjectCard title="隐私与持仓策略" data={data.privacy_policy} />
          <PolicyObjectCard
            title="组合上下文策略"
            data={data.portfolio_context_policy}
          />
          <PolicyObjectCard title="搜索策略" data={data.search_policy} />
          <PolicyObjectCard
            title="模型目的地"
            data={data.model_destination}
          />
          <PolicyObjectCard
            title="持久化策略"
            data={data.persistence_policy}
          />
        </section>
      </div>
    </section>
  );
}

function ManifestListCard({
  title,
  items,
  tone
}: {
  title: string;
  items: Array<Record<string, unknown>>;
  tone: "included" | "excluded" | "model";
}) {
  return (
    <article className={`manifest-list-card manifest-${tone}`}>
      <header>
        <h3>{title}</h3>
        <strong>{items.length}</strong>
      </header>
      {items.length ? (
        <ul>
          {items.slice(0, 6).map((item, index) => (
            <li key={`${String(item.row_id || item.metric_key)}-${index}`}>
              <div>
                <SourceBadge sourceBadge={String(item.source_badge || "missing")} />
                <strong>
                  {String(item.display_name || item.metric_key || "evidence")}
                </strong>
              </div>
              <span>
                {String(
                  item.excluded_reason ||
                    item.value_text ||
                    item.status ||
                    "not available"
                )}
              </span>
            </li>
          ))}
        </ul>
      ) : (
        <p>当前没有公开条目。</p>
      )}
      {items.length > 6 && <footer>另有 {items.length - 6} 条</footer>}
    </article>
  );
}

function PolicyCard({ title, values }: { title: string; values: string[] }) {
  return (
    <article className="policy-card">
      <header>
        <ResearchIcon name="shield" size={18} />
        <h3>{title}</h3>
      </header>
      <ul>
        {values.map((value) => (
          <li key={value}>{value}</li>
        ))}
      </ul>
    </article>
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
    <article className="policy-card">
      <header>
        <ResearchIcon name="check" size={18} />
        <h3>{title}</h3>
      </header>
      <dl>
        {Object.entries(data).map(([key, value]) => (
          <div key={key}>
            <dt>{humanizeKey(key)}</dt>
            <dd>{compactText(value)}</dd>
          </div>
        ))}
      </dl>
    </article>
  );
}

function policyValue(data: Record<string, unknown>, key: string) {
  return compactText(data[key]);
}

function summaryNumber(data: Record<string, unknown>, key: string) {
  return typeof data[key] === "number" ? String(data[key]) : "not available";
}
