import { useMemo, useState } from "react";
import type {
  AIContextManifestResponse,
  ApiResult,
  DashboardEvidenceRow,
  DashboardEvidenceTableResponse
} from "../types";
import {
  formatCompactHint,
  formatEvidenceValueText,
  getMissingReasonLabel,
  getModuleLabel
} from "../utils/displayLabels";
import { blockedStatuses, uniqueValues } from "../utils/evidence";
import { EvidenceRowDrawer } from "./EvidenceRowDrawer";
import { ResearchIcon } from "./ResearchIcon";
import {
  AIContextBadge,
  EmptyState,
  ErrorState,
  formatTimestamp,
  FreshnessBadge,
  LoadingState,
  MetaStrip,
  PageHeader,
  SourceBadge,
  StatusBadge
} from "./ResearchUI";

type EvidenceAuditPageProps = {
  evidence: ApiResult<DashboardEvidenceTableResponse>;
  manifest: ApiResult<AIContextManifestResponse>;
  isLoading: boolean;
};

type FilterState = {
  module: string;
  status: string;
  source: string;
  freshness: string;
  aiAllowed: string;
  trigger: string;
  query: string;
};

const initialFilters: FilterState = {
  module: "all",
  status: "all",
  source: "all",
  freshness: "all",
  aiAllowed: "all",
  trigger: "all",
  query: ""
};

export function EvidenceAuditPage({
  evidence,
  manifest,
  isLoading
}: EvidenceAuditPageProps) {
  const [filters, setFilters] = useState<FilterState>(initialFilters);
  const [selectedRow, setSelectedRow] =
    useState<DashboardEvidenceRow | null>(null);

  const rows = evidence.data?.rows || [];
  const filteredRows = useMemo(
    () => rows.filter((row) => matchesFilters(row, filters)),
    [rows, filters]
  );
  const moduleCounts = useMemo(() => countBy(rows, (row) => row.module), [rows]);

  if (isLoading) return <LoadingState title="正在建立证据审计索引" />;
  if (evidence.error || !evidence.data) {
    return (
      <ErrorState title="全量证据暂不可用" message={evidence.error} />
    );
  }

  const sourceSummary = manifest.data?.source_summary || {};
  const blockedCount = rows.filter(
    (row) =>
      blockedStatuses.has(row.status) ||
      ["stale", "unknown", "missing", "insufficient_history"].includes(
        row.freshness_status
      )
  ).length;
  const aiAllowedCount = rows.filter((row) => row.ai_context_allowed).length;

  return (
    <section className="evidence-audit-page">
      <PageHeader
        eyebrow="LOCAL MACRO RISK RESEARCH WORKBENCH · READ ONLY"
        subtitle="审计所有证据行、来源与边界，确保风险判断可解释、可追溯、可复现。"
        title="全量证据 / Evidence Audit"
      />

      <MetaStrip
        items={[
          {
            label: "DATA AS OF",
            value: formatTimestamp(evidence.data.generated_at)
          },
          { label: "EVIDENCE ROWS", value: evidence.data.row_count },
          {
            label: "INCLUDED FACTS",
            value: summaryNumber(sourceSummary, "included_facts_count")
          },
          {
            label: "EXCLUDED FACTS",
            value: summaryNumber(sourceSummary, "excluded_facts_count")
          },
          {
            label: "MODEL OUTPUTS",
            value: `${summaryNumber(
              sourceSummary,
              "included_model_outputs_count"
            )} / ${summaryNumber(
              sourceSummary,
              "excluded_model_outputs_count"
            )}`
          },
          { label: "BLOCKED / LIMITED", value: blockedCount },
          { label: "AI ALLOWED", value: aiAllowedCount }
        ]}
      />

      <section className="evidence-filter-panel">
        <div className="evidence-filter-grid">
          <FilterSelect
            label="模块"
            options={uniqueValues(rows.map((row) => row.module)).sort()}
            value={filters.module}
            onChange={(value) => setFilters({ ...filters, module: value })}
            formatOption={getModuleLabel}
          />
          <FilterSelect
            label="状态"
            options={uniqueValues(rows.map((row) => row.status)).sort()}
            value={filters.status}
            onChange={(value) => setFilters({ ...filters, status: value })}
          />
          <FilterSelect
            label="来源类型"
            options={uniqueValues(rows.map((row) => row.source_badge)).sort()}
            value={filters.source}
            onChange={(value) => setFilters({ ...filters, source: value })}
          />
          <FilterSelect
            label="新鲜度"
            options={uniqueValues(
              rows.map((row) => row.freshness_status)
            ).sort()}
            value={filters.freshness}
            onChange={(value) => setFilters({ ...filters, freshness: value })}
          />
          <FilterSelect
            label="AI 可用"
            options={["true", "false"]}
            value={filters.aiAllowed}
            onChange={(value) => setFilters({ ...filters, aiAllowed: value })}
            formatOption={(value) => (value === "true" ? "允许" : "阻断")}
          />
          <FilterSelect
            label="触发资格"
            options={uniqueValues(
              rows
                .map((row) => row.trigger_eligibility)
                .filter((value): value is string => Boolean(value))
            ).sort()}
            value={filters.trigger}
            onChange={(value) => setFilters({ ...filters, trigger: value })}
          />
          <label className="evidence-search-control">
            <span>搜索 metric key / 指标 / 来源</span>
            <div>
              <ResearchIcon name="search" size={16} />
              <input
                onChange={(event) =>
                  setFilters({ ...filters, query: event.target.value })
                }
                placeholder="搜索证据..."
                type="search"
                value={filters.query}
              />
            </div>
          </label>
          <button
            className="clear-filter-button"
            onClick={() => setFilters(initialFilters)}
            type="button"
          >
            重置筛选
          </button>
        </div>

        <div className="module-quick-filters" aria-label="模块快速筛选">
          <button
            className={filters.module === "all" ? "is-active" : ""}
            onClick={() => setFilters({ ...filters, module: "all" })}
            type="button"
          >
            全部 <span>{rows.length}</span>
          </button>
          {Object.entries(moduleCounts)
            .sort(([, left], [, right]) => right - left)
            .slice(0, 10)
            .map(([moduleKey, count]) => (
              <button
                key={moduleKey}
                className={filters.module === moduleKey ? "is-active" : ""}
                onClick={() => setFilters({ ...filters, module: moduleKey })}
                type="button"
              >
                {getModuleLabel(moduleKey)} <span>{count}</span>
              </button>
            ))}
        </div>
      </section>

      <div className="evidence-results-caption">
        <span>显示 {filteredRows.length} 行</span>
        <span>被阻断与缺失行不会隐藏</span>
      </div>

      {filteredRows.length ? (
        <section className="evidence-audit-table-wrap">
          <table className="evidence-audit-table">
            <thead>
              <tr>
                <th>模块</th>
                <th>指标</th>
                <th>数值</th>
                <th>状态</th>
                <th>来源</th>
                <th>新鲜度</th>
                <th>AI 可用</th>
                <th>更新时间</th>
                <th>边界 / 缺失摘要</th>
                <th aria-label="查看详情" />
              </tr>
            </thead>
            <tbody>
              {filteredRows.map((row) => (
                <tr key={row.row_id}>
                  <td>
                    <strong>{getModuleLabel(row.module)}</strong>
                    <small>{row.module}</small>
                  </td>
                  <td>
                    <strong>{row.display_name}</strong>
                    <small>{row.metric_key}</small>
                  </td>
                  <td className="evidence-value-cell">
                    {formatEvidenceValueText(row.value_text, row.status)}
                    {row.unit && <small>{row.unit}</small>}
                  </td>
                  <td>
                    <StatusBadge status={row.status} />
                  </td>
                  <td>
                    <SourceBadge sourceBadge={row.source_badge} />
                    <small>{row.source || "not available"}</small>
                  </td>
                  <td>
                    <FreshnessBadge freshness={row.freshness_status} />
                  </td>
                  <td>
                    <AIContextBadge
                      allowed={row.ai_context_allowed}
                      reason={row.blocked_reason}
                    />
                  </td>
                  <td>
                    {row.observation_date ||
                      formatTimestamp(row.generated_at)}
                  </td>
                  <td className="evidence-boundary-cell">
                    {getMissingReasonLabel(row.missing_reason) ||
                      formatCompactHint(
                        row.blocked_reason ||
                          row.interpretation_boundary ||
                          row.interpretation_hint
                      ) ||
                      "—"}
                  </td>
                  <td>
                    <button
                      aria-label={`查看 ${row.display_name} 详情`}
                      className="evidence-row-button"
                      onClick={() => setSelectedRow(row)}
                      type="button"
                    >
                      <ResearchIcon name="chevron" size={15} />
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      ) : (
        <EmptyState
          description="请调整模块、状态、来源、新鲜度、AI 资格或搜索条件。"
          icon="search"
          title="当前筛选条件下没有证据行"
        />
      )}

      {selectedRow && (
        <EvidenceRowDrawer
          onClose={() => setSelectedRow(null)}
          row={selectedRow}
        />
      )}
    </section>
  );
}

function FilterSelect({
  label,
  value,
  options,
  onChange,
  formatOption
}: {
  label: string;
  value: string;
  options: string[];
  onChange: (value: string) => void;
  formatOption?: (value: string) => string;
}) {
  return (
    <label className="evidence-filter-control">
      <span>{label}</span>
      <select
        onChange={(event) => onChange(event.target.value)}
        value={value}
      >
        <option value="all">全部</option>
        {options.map((option) => (
          <option key={option} value={option}>
            {formatOption ? formatOption(option) : option}
          </option>
        ))}
      </select>
    </label>
  );
}

function matchesFilters(row: DashboardEvidenceRow, filters: FilterState) {
  if (filters.module !== "all" && row.module !== filters.module) return false;
  if (filters.status !== "all" && row.status !== filters.status) return false;
  if (filters.source !== "all" && row.source_badge !== filters.source) {
    return false;
  }
  if (
    filters.freshness !== "all" &&
    row.freshness_status !== filters.freshness
  ) {
    return false;
  }
  if (
    filters.aiAllowed !== "all" &&
    row.ai_context_allowed !== (filters.aiAllowed === "true")
  ) {
    return false;
  }
  if (
    filters.trigger !== "all" &&
    row.trigger_eligibility !== filters.trigger
  ) {
    return false;
  }
  const query = filters.query.trim().toLowerCase();
  if (!query) return true;
  return [
    row.module,
    getModuleLabel(row.module),
    row.metric_key,
    row.display_name,
    row.source,
    row.source_series,
    row.missing_reason,
    row.blocked_reason,
    row.interpretation_hint,
    row.interpretation_boundary
  ].some((value) => value?.toLowerCase().includes(query));
}

function countBy<T>(values: T[], key: (value: T) => string) {
  return values.reduce<Record<string, number>>((counts, value) => {
    const itemKey = key(value);
    counts[itemKey] = (counts[itemKey] || 0) + 1;
    return counts;
  }, {});
}

function summaryNumber(data: Record<string, unknown>, key: string) {
  const value = data[key];
  return typeof value === "number" ? value : "not available";
}
