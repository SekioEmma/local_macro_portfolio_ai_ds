import { useEffect, useRef, useState, type ReactNode } from "react";
import type { DashboardEvidenceRow } from "../types";
import {
  formatCompactHint,
  getMissingReasonLabel,
  getModuleLabel
} from "../utils/displayLabels";
import { compactText, recordEntries } from "../utils/evidence";
import { getModuleBoundary } from "../utils/moduleRegistry";
import { useBodyScrollLock } from "../utils/useBodyScrollLock";
import { ResearchIcon } from "./ResearchIcon";
import {
  AIContextBadge,
  BoundaryNotice,
  formatTimestamp,
  FreshnessBadge,
  MetricValue,
  SourceBadge,
  StatusBadge,
  humanizeKey
} from "./ResearchUI";

type EvidenceDrawerTab = "overview" | "provenance" | "inputs" | "boundaries";

const tabs: Array<{ key: EvidenceDrawerTab; label: string }> = [
  { key: "overview", label: "概览" },
  { key: "provenance", label: "来源" },
  { key: "inputs", label: "输入 / 贡献" },
  { key: "boundaries", label: "边界" }
];

export function EvidenceRowDrawer({
  row,
  onClose
}: {
  row: DashboardEvidenceRow;
  onClose: () => void;
}) {
  useBodyScrollLock();
  const [activeTab, setActiveTab] =
    useState<EvidenceDrawerTab>("overview");
  const [copyStatus, setCopyStatus] = useState<string | null>(null);
  const closeRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    const previous = document.activeElement as HTMLElement | null;
    closeRef.current?.focus();
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => {
      window.removeEventListener("keydown", handleKeyDown);
      previous?.focus();
    };
  }, [onClose]);

  const copyText = async (label: string, text: string) => {
    try {
      await navigator.clipboard.writeText(text);
      setCopyStatus(`${label}已复制`);
    } catch {
      setCopyStatus("复制不可用，请手动选择文本。");
    }
  };

  return (
    <div className="drawer-backdrop" onMouseDown={onClose} role="presentation">
      <aside
        aria-label={`${row.display_name} 证据详情`}
        aria-modal="true"
        className="evidence-row-drawer"
        onMouseDown={(event) => event.stopPropagation()}
        role="dialog"
      >
        <header className="module-audit-header">
          <div>
            <p className="research-kicker">EVIDENCE LINEAGE</p>
            <h2>{row.display_name}</h2>
            <p>{row.metric_key}</p>
          </div>
          <button
            ref={closeRef}
            aria-label="关闭证据详情"
            className="drawer-close-button"
            onClick={onClose}
            type="button"
          >
            <ResearchIcon name="close" size={20} />
          </button>
        </header>

        <div className="module-audit-meta">
          <StatusBadge status={row.status} />
          <SourceBadge sourceBadge={row.source_badge} />
          <FreshnessBadge freshness={row.freshness_status} />
          <AIContextBadge
            allowed={row.ai_context_allowed}
            reason={row.blocked_reason}
          />
        </div>

        <div className="evidence-copy-bar">
          <button
            onClick={() => copyText("metric key", row.metric_key)}
            type="button"
          >
            <ResearchIcon name="copy" size={14} /> 复制 metric key
          </button>
          <button
            onClick={() => copyText("事实摘要", factSummary(row))}
            type="button"
          >
            <ResearchIcon name="copy" size={14} /> 复制事实摘要
          </button>
          <button
            onClick={() =>
              copyText("row JSON", JSON.stringify(row, null, 2))
            }
            type="button"
          >
            <ResearchIcon name="copy" size={14} /> 复制 row JSON
          </button>
          {copyStatus && <span aria-live="polite">{copyStatus}</span>}
        </div>

        <div className="drawer-tabs" role="tablist" aria-label="证据详情分组">
          {tabs.map((tab) => (
            <button
              key={tab.key}
              aria-selected={activeTab === tab.key}
              className={activeTab === tab.key ? "is-active" : ""}
              onClick={() => setActiveTab(tab.key)}
              role="tab"
              type="button"
            >
              {tab.label}
            </button>
          ))}
        </div>

        <div className="drawer-tab-panel" role="tabpanel">
          {activeTab === "overview" && <OverviewTab row={row} />}
          {activeTab === "provenance" && <ProvenanceTab row={row} />}
          {activeTab === "inputs" && <InputsTab row={row} />}
          {activeTab === "boundaries" && <BoundariesTab row={row} />}
        </div>
      </aside>
    </div>
  );
}

function OverviewTab({ row }: { row: DashboardEvidenceRow }) {
  return (
    <div className="drawer-tab-stack">
      <section className="evidence-reading-card">
        <div>
          <span>当前值</span>
          <MetricValue
            status={row.status}
            unit={row.unit}
            valueText={row.value_text}
          />
        </div>
        <StatusBadge status={row.status} />
      </section>
      <DetailGrid
        items={[
          ["Row ID", row.row_id],
          ["模块", `${getModuleLabel(row.module)} / ${row.module}`],
          ["生成时间", formatTimestamp(row.generated_at)],
          ["观测日期", row.observation_date || "not available"],
          ["AI tier", row.ai_context_tier || "not available"],
          ["Trigger eligibility", row.trigger_eligibility || "not available"],
          ["频率", row.frequency_class || "not available"],
          ["变换", row.transform_class || "not available"]
        ]}
      />
      {(row.interpretation_hint || row.missing_reason || row.blocked_reason) && (
        <DrawerSection title="解释与约束">
          <p>
            {getMissingReasonLabel(row.missing_reason) ||
              formatCompactHint(row.interpretation_hint) ||
              row.blocked_reason}
          </p>
        </DrawerSection>
      )}
      <NormalizationPanel row={row} />
    </div>
  );
}

function ProvenanceTab({ row }: { row: DashboardEvidenceRow }) {
  return (
    <div className="drawer-tab-stack">
      <DetailGrid
        items={[
          ["Source", row.source || "not available"],
          ["Source class", row.source_badge],
          ["Source series", row.source_series || "not available"],
          ["Observation date", row.observation_date || "not available"],
          ["Generated at", formatTimestamp(row.generated_at)],
          ["Freshness", row.freshness_status],
          ["Lookback", row.lookback_window || "not available"],
          [
            "Lookback range",
            `${row.lookback_start || "not available"} → ${
              row.lookback_end || "not available"
            }`
          ],
          [
            "Observation count",
            row.observation_count === null ||
            row.observation_count === undefined
              ? "not available"
              : String(row.observation_count)
          ],
          [
            "Minimum count",
            row.minimum_observation_count === null ||
            row.minimum_observation_count === undefined
              ? "not available"
              : String(row.minimum_observation_count)
          ],
          ["History quality", row.history_quality_status || "not available"]
        ]}
      />
      <BoundaryNotice title="AI factual context">
        {row.ai_context_allowed
          ? "该证据行当前可进入 AI factual context；仍受来源、新鲜度与解释边界约束。"
          : `该证据行不进入 AI factual context。原因：${
              row.blocked_reason || row.status
            }。`}
      </BoundaryNotice>
    </div>
  );
}

function InputsTab({ row }: { row: DashboardEvidenceRow }) {
  return (
    <div className="drawer-tab-stack">
      <DrawerSection title="Input evidence">
        {row.input_evidence?.length ? (
          <div className="evidence-input-list">
            {row.input_evidence.map((item, index) => (
              <RecordCard
                key={`${String(item.metric_key || "input")}-${index}`}
                data={item}
              />
            ))}
          </div>
        ) : (
          <p className="drawer-muted">没有公开的 input evidence。</p>
        )}
      </DrawerSection>

      <DrawerSection title="Component contributions">
        {row.component_contributions &&
        recordEntries(row.component_contributions).length ? (
          <div className="evidence-record-grid">
            {recordEntries(row.component_contributions).map(([key, value]) => (
              <article key={key}>
                <strong>{humanizeKey(key)}</strong>
                <p>{compactText(value)}</p>
              </article>
            ))}
          </div>
        ) : (
          <p className="drawer-muted">没有公开的 component contributions。</p>
        )}
      </DrawerSection>

      <DrawerSection title="Missing inputs">
        {row.missing_inputs?.length ? (
          <ul className="drawer-boundary-list">
            {row.missing_inputs.map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
        ) : (
          <p className="drawer-muted">没有公开的 missing inputs。</p>
        )}
      </DrawerSection>
    </div>
  );
}

function BoundariesTab({ row }: { row: DashboardEvidenceRow }) {
  return (
    <div className="drawer-tab-stack">
      <BoundaryNotice title="模块边界">
        {getModuleBoundary(row.module)}
      </BoundaryNotice>
      <BoundaryNotice title="证据行边界" tone="warning">
        {row.interpretation_boundary ||
          row.interpretation_hint ||
          "当前证据行没有额外公开边界；仍遵循模块边界与全局只读研究约束。"}
      </BoundaryNotice>
      <DetailGrid
        items={[
          ["Missing reason", row.missing_reason || "not available"],
          ["Blocked reason", row.blocked_reason || "not available"],
          ["Trigger eligibility", row.trigger_eligibility || "not available"],
          ["AI context tier", row.ai_context_tier || "not available"]
        ]}
      />
    </div>
  );
}

function NormalizationPanel({ row }: { row: DashboardEvidenceRow }) {
  const items = [
    ["Percentile", row.percentile, row.percentile_band],
    ["Z-score", row.zscore, row.zscore_band],
    ["Robust z-score", row.robust_zscore, row.robust_zscore_band]
  ].filter(([, value]) => value !== null && value !== undefined);
  if (!items.length) return null;
  return (
    <DrawerSection title="历史标准化">
      <div className="normalization-grid">
        {items.map(([label, value, band]) => (
          <div key={String(label)}>
            <span>{label}</span>
            <strong>{String(value)}</strong>
            <small>{String(band || "not available")}</small>
          </div>
        ))}
      </div>
    </DrawerSection>
  );
}

function DetailGrid({
  items
}: {
  items: Array<[string, string]>;
}) {
  return (
    <dl className="evidence-detail-grid">
      {items.map(([label, value]) => (
        <div key={label}>
          <dt>{label}</dt>
          <dd>{value}</dd>
        </div>
      ))}
    </dl>
  );
}

function RecordCard({ data }: { data: Record<string, unknown> }) {
  return (
    <article>
      {Object.entries(data).map(([key, value]) => (
        <div key={key}>
          <span>{humanizeKey(key)}</span>
          <strong>{compactText(value)}</strong>
        </div>
      ))}
    </article>
  );
}

function DrawerSection({
  title,
  children
}: {
  title: string;
  children: ReactNode;
}) {
  return (
    <section className="drawer-audit-section">
      <h3>{title}</h3>
      {children}
    </section>
  );
}

function factSummary(row: DashboardEvidenceRow) {
  return [
    `${getModuleLabel(row.module)} / ${row.display_name}`,
    `metric_key=${row.metric_key}`,
    `value=${row.value_text}`,
    `status=${row.status}`,
    `source=${row.source || row.source_badge}`,
    `observation_date=${row.observation_date || "not available"}`,
    `freshness=${row.freshness_status}`,
    `ai_context_allowed=${row.ai_context_allowed}`,
    row.blocked_reason ? `blocked_reason=${row.blocked_reason}` : null,
    row.interpretation_boundary
      ? `boundary=${row.interpretation_boundary}`
      : null
  ]
    .filter(Boolean)
    .join("\n");
}
