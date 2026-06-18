import type {
  ApiResult,
  DashboardEvidenceRow,
  DashboardEvidenceTableResponse
} from "../types";
import {
  asRecord,
  asRecordArray,
  compactText,
  rowsForModule,
  stringList
} from "../utils/evidence";
import { ResearchIcon } from "./ResearchIcon";
import {
  BoundaryNotice,
  EmptyState,
  ErrorState,
  formatTimestamp,
  LoadingState,
  MetaStrip,
  PageHeader,
  StatusBadge,
  humanizeKey
} from "./ResearchUI";

export function HistoricalValidationPage({
  evidence,
  isLoading
}: {
  evidence: ApiResult<DashboardEvidenceTableResponse>;
  isLoading: boolean;
}) {
  if (isLoading) return <LoadingState title="正在组织历史验证回放" />;
  if (evidence.error || !evidence.data) {
    return <ErrorState title="历史验证暂不可用" message={evidence.error} />;
  }

  const rows = rowsForModule(evidence.data.rows, "historical_validation");
  const statusRow = findRow(rows, "historical_validation_status");
  const contributions = asRecord(statusRow?.component_contributions);
  const replayRows = asRecordArray(contributions?.d19_v1_replay_rows);
  const replaySummary = asRecord(contributions?.d19_v1_replay_summary);
  const eventCount = rowValue(rows, "historical_validation_event_count");
  const availableCount = rowValue(
    rows,
    "historical_validation_available_event_count"
  );
  const insufficientCount = rowValue(
    rows,
    "historical_validation_insufficient_history_event_count"
  );
  const violationCount = rowValue(
    rows,
    "historical_validation_boundary_violation_count"
  );

  return (
    <section className="model-review-page">
      <PageHeader
        eyebrow="LOCAL MACRO RISK RESEARCH WORKBENCH · READ ONLY"
        subtitle="Historical Validation = coverage and boundary validation, not backtest."
        title="历史验证 / Historical Validation Replay"
      />
      <MetaStrip
        items={[
          {
            label: "AS OF",
            value:
              findRow(rows, "historical_validation_as_of_date")?.value_text ||
              formatTimestamp(evidence.data.generated_at)
          },
          { label: "EVENTS", value: eventCount },
          { label: "AVAILABLE", value: availableCount },
          { label: "INSUFFICIENT", value: insufficientCount },
          { label: "BOUNDARY ITEMS", value: violationCount },
          {
            label: "REPLAY VERSION",
            value:
              findRow(rows, "historical_validation_replay_version")
                ?.value_text || "not available"
          }
        ]}
      />

      <BoundaryNotice title="固定边界">
        Not backtest · not prediction accuracy · not strategy evaluation · no
        ROC/AUC · no trading performance · no return curve.
      </BoundaryNotice>

      <section className="historical-coverage-grid">
        <CoverageCard
          label="Available"
          tone="available"
          value={availableCount}
        />
        <CoverageCard
          label="Limited / Reference"
          tone="limited"
          value={summaryValue(replaySummary, "limited_replay_event_count")}
        />
        <CoverageCard
          label="Insufficient"
          tone="insufficient"
          value={insufficientCount}
        />
        <CoverageCard
          label="Boundary items"
          tone="boundary"
          value={violationCount}
        />
      </section>

      <section className="model-section-stack">
        <ModelSectionHeader
          description="时间线展示历史窗口内系统能看到的证据与覆盖状态，不展示收益曲线或策略表现。"
          index="I · EVENT TIMELINE"
          title="历史事件窗口"
        />
        {replayRows.length ? (
          <div className="historical-timeline">
            {replayRows.map((event, index) => (
              <HistoricalEventCard
                key={String(event.event_id || `event-${index}`)}
                event={event}
              />
            ))}
          </div>
        ) : (
          <EmptyState
            description="当前状态行没有公开结构化 d19_v1_replay_rows；页面不会从摘要文本伪造事件。"
            icon="history"
            title="结构化历史事件暂不可用"
          />
        )}
      </section>

      <section className="historical-audit-grid">
        <AuditSummaryCard
          data={contributions?.coverage_summary}
          icon="database"
          title="Coverage Summary"
        />
        <AuditSummaryCard
          data={contributions?.module_consistency_summary}
          icon="layers"
          title="Module Consistency"
        />
        <AuditSummaryCard
          data={contributions?.proxy_constraint_summary}
          icon="evidence"
          title="Proxy Constraints"
        />
        <AuditSummaryCard
          data={contributions?.missing_data_summary}
          icon="diagnostics"
          title="Missing Data"
        />
      </section>

      <BoundaryNotice title="验证边界" tone="warning">
        {findRow(rows, "historical_validation_validation_boundary")
          ?.interpretation_boundary ||
          findRow(rows, "historical_validation_validation_boundary")
            ?.value_text ||
          "Read-only event-window replay and boundary validation."}
      </BoundaryNotice>
    </section>
  );
}

function HistoricalEventCard({ event }: { event: Record<string, unknown> }) {
  const window = asRecord(event.window);
  const pressureGroups = stringList(event.expected_pressure_groups);
  const missing = stringList(event.missing_or_limited_inputs);
  const boundaries = stringList(event.interpretation_boundary);
  const validationNotes = stringList(event.validation_notes);
  const boundaryFlags = stringList(event.boundary_violation_flags);
  return (
    <article className="historical-event-card">
      <span className="timeline-marker" />
      <header>
        <div>
          <p className="research-kicker">
            {String(event.event_type || "HISTORICAL WINDOW")}
          </p>
          <h3>{String(event.event_name || event.event_id || "未命名事件")}</h3>
          <small>{String(event.event_id || "")}</small>
        </div>
        <StatusBadge
          status={String(event.validation_status || "unknown")}
        />
      </header>
      <div className="event-window">
        <ResearchIcon name="clock" size={16} />
        <span>
          {String(window?.start || "not available")} →{" "}
          {String(window?.end || "not available")}
        </span>
      </div>
      <dl className="event-stat-grid">
        <div>
          <dt>Available days</dt>
          <dd>{String(event.available_day_count ?? "not available")}</dd>
        </div>
        <div>
          <dt>History-limited days</dt>
          <dd>
            {String(event.insufficient_history_day_count ?? "not available")}
          </dd>
        </div>
        <div>
          <dt>Boundary items</dt>
          <dd>{String(event.boundary_violation_count ?? 0)}</dd>
        </div>
      </dl>
      <ChipList title="Expected pressure groups" values={pressureGroups} />
      <EventList title="Missing / limited inputs" values={missing} />
      <EventList
        title="Validation notes"
        values={[...validationNotes, ...boundaryFlags]}
      />
      <EventList title="Interpretation boundary" values={boundaries} />
    </article>
  );
}

function CoverageCard({
  label,
  value,
  tone
}: {
  label: string;
  value: string;
  tone: string;
}) {
  return (
    <article className={`coverage-card coverage-${tone}`}>
      <span>{label}</span>
      <strong>{value}</strong>
    </article>
  );
}

function AuditSummaryCard({
  title,
  icon,
  data
}: {
  title: string;
  icon: "database" | "layers" | "evidence" | "diagnostics";
  data: unknown;
}) {
  const record = asRecord(data);
  return (
    <article className="audit-summary-card">
      <header>
        <ResearchIcon name={icon} size={18} />
        <h3>{title}</h3>
      </header>
      {record && Object.keys(record).length ? (
        <dl>
          {Object.entries(record)
            .slice(0, 10)
            .map(([key, value]) => (
              <div key={key}>
                <dt>{humanizeKey(key)}</dt>
                <dd>{compactText(value)}</dd>
              </div>
            ))}
        </dl>
      ) : (
        <p>{compactText(data)}</p>
      )}
    </article>
  );
}

function ChipList({ title, values }: { title: string; values: string[] }) {
  if (!values.length) return null;
  return (
    <section className="event-detail-section">
      <strong>{title}</strong>
      <div className="event-chip-row">
        {values.map((value) => (
          <span key={value}>{humanizeKey(value)}</span>
        ))}
      </div>
    </section>
  );
}

function EventList({ title, values }: { title: string; values: string[] }) {
  if (!values.length) return null;
  return (
    <section className="event-detail-section">
      <strong>{title}</strong>
      <ul>
        {values.slice(0, 8).map((value) => (
          <li key={value}>{value}</li>
        ))}
      </ul>
    </section>
  );
}

function ModelSectionHeader({
  index,
  title,
  description
}: {
  index: string;
  title: string;
  description: string;
}) {
  return (
    <header className="model-section-header">
      <div>
        <p className="research-kicker">{index}</p>
        <h2>{title}</h2>
      </div>
      <p>{description}</p>
    </header>
  );
}

function findRow(rows: DashboardEvidenceRow[], key: string) {
  return rows.find((row) => row.metric_key === key);
}

function rowValue(rows: DashboardEvidenceRow[], key: string) {
  return findRow(rows, key)?.value_text || "not available";
}

function summaryValue(
  summary: Record<string, unknown> | null,
  key: string
) {
  return summary && summary[key] !== undefined
    ? String(summary[key])
    : "not available";
}
