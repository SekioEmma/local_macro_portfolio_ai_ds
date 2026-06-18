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
  SourceBadge,
  StatusBadge,
  humanizeKey
} from "./ResearchUI";

export function ScenarioStressPage({
  evidence,
  isLoading
}: {
  evidence: ApiResult<DashboardEvidenceTableResponse>;
  isLoading: boolean;
}) {
  if (isLoading) return <LoadingState title="正在组织情景压力证据" />;
  if (evidence.error || !evidence.data) {
    return <ErrorState title="情景压力暂不可用" message={evidence.error} />;
  }

  const rows = rowsForModule(evidence.data.rows, "scenario_stress");
  const statusRow = findRow(rows, "scenario_stress_status");
  const contributions = asRecord(statusRow?.component_contributions);
  const scenarios = asRecordArray(contributions?.scenarios);
  const affectedGroups = rowStringList(
    rows,
    "scenario_stress_affected_groups"
  );
  const channels = rowStringList(
    rows,
    "scenario_stress_transmission_channels"
  );
  const missingInputs = uniqueStrings([
    ...rowStringList(rows, "scenario_stress_missing_inputs"),
    ...(statusRow?.missing_inputs || [])
  ]);

  return (
    <section className="model-review-page">
      <PageHeader
        eyebrow="LOCAL MACRO RISK RESEARCH WORKBENCH · READ ONLY"
        subtitle="情景压力矩阵是对假设冲击与当前证据传导的复核，不是未来预测。"
        title="情景压力 / Scenario Stress Matrix"
      />
      <MetaStrip
        items={[
          {
            label: "AS OF",
            value: findRow(rows, "scenario_stress_as_of_date")?.value_text ||
              formatTimestamp(evidence.data.generated_at)
          },
          {
            label: "SCENARIOS",
            value:
              findRow(rows, "scenario_stress_scenario_count")?.value_text ||
              scenarios.length ||
              "not available"
          },
          {
            label: "PRIMARY SCENARIO",
            value:
              findRow(rows, "scenario_stress_primary_scenario")?.value_text ||
              "not available"
          },
          {
            label: "SEVERITY",
            value: (
              <StatusBadge
                status={
                  findRow(rows, "scenario_stress_severity_band")?.value_text ||
                  statusRow?.status ||
                  "unknown"
                }
              />
            )
          },
          {
            label: "UNCERTAINTY",
            value:
              findRow(rows, "scenario_stress_uncertainty_band")?.value_text ||
              "not available"
          }
        ]}
      />

      <BoundaryNotice title="固定边界">
        Scenario is not forecast · no event odds · no return path · no trading
        action · no allocation advice.
      </BoundaryNotice>

      <section className="model-overview-grid">
        <ModelOverviewCard
          icon="scenario"
          label="当前状态"
          value={statusRow?.value_text || "not available"}
        />
        <ModelOverviewCard
          icon="layers"
          label="受影响证据组"
          value={affectedGroups.length ? affectedGroups.join(" / ") : "not available"}
        />
        <ModelOverviewCard
          icon="evidence"
          label="传导通道"
          value={channels.length ? channels.join(" → ") : "not available"}
        />
        <ModelOverviewCard
          icon="diagnostics"
          label="缺失约束"
          value={missingInputs.length ? `${missingInputs.length} 项` : "无公开缺失项"}
        />
      </section>

      <section className="model-section-stack">
        <ModelSectionHeader
          description="每张卡片展示当前证据对预设情景的支持、传导路径、严重度与不确定性；不展示发生概率。"
          index="I · SCENARIO CARDS"
          title="情景传导复核"
        />
        {scenarios.length ? (
          <div className="scenario-card-grid">
            {scenarios.map((scenario, index) => (
              <ScenarioCard key={scenarioKey(scenario, index)} scenario={scenario} />
            ))}
          </div>
        ) : (
          <EmptyState
            description="后端当前未公开结构化 scenarios 数组；页面不会从摘要字符串伪造情景。"
            icon="scenario"
            title="结构化情景暂不可用"
          />
        )}
      </section>

      <section className="model-section-stack">
        <ModelSectionHeader
          description="矩阵只表达情景与风险证据组的关联，不表示价格方向或结果确定性。"
          index="II · TRANSMISSION MATRIX"
          title="受影响组与传导通道"
        />
        <TransmissionMatrix
          affectedGroups={affectedGroups}
          channels={channels}
          scenarios={scenarios}
        />
      </section>

      <section className="model-two-column">
        <ConstraintPanel
          items={missingInputs}
          title="Missing Constraints"
          empty="没有公开的 missing inputs。"
        />
        <ConstraintPanel
          items={scenarioConstraintList(scenarios)}
          title="Uncertainty / Proxy Constraints"
          empty="没有公开的 uncertainty 或 proxy constraints。"
        />
      </section>

      <BoundaryNotice title="解释边界" tone="warning">
        {findRow(rows, "scenario_stress_interpretation_boundary")
          ?.interpretation_boundary ||
          findRow(rows, "scenario_stress_interpretation_boundary")?.value_text ||
          "Hypothetical transmission review only."}
      </BoundaryNotice>
    </section>
  );
}

function ScenarioCard({ scenario }: { scenario: Record<string, unknown> }) {
  const name = stringValue(
    scenario.scenario_label || scenario.scenario_name || scenario.name
  );
  const affected = stringList(
    scenario.affected_groups || scenario.evidence_groups
  );
  const channels = stringList(scenario.transmission_channels);
  const supporting = stringList(scenario.supporting_evidence);
  const missing = stringList(
    scenario.missing_inputs || scenario.missing_constraints
  );
  return (
    <article className="scenario-review-card">
      <header>
        <div>
          <p className="research-kicker">HYPOTHETICAL SCENARIO</p>
          <h3>{name || "未命名情景"}</h3>
        </div>
        <StatusBadge
          status={stringValue(scenario.severity_band) || "unknown"}
        />
      </header>
      <dl className="scenario-band-grid">
        <div>
          <dt>Support</dt>
          <dd>{stringValue(scenario.support_band) || "not available"}</dd>
        </div>
        <div>
          <dt>Severity</dt>
          <dd>{stringValue(scenario.severity_band) || "not available"}</dd>
        </div>
        <div>
          <dt>Uncertainty</dt>
          <dd>{stringValue(scenario.uncertainty_band) || "not available"}</dd>
        </div>
      </dl>
      <FlowChips title="传导路径" values={channels} />
      <FlowChips title="受影响组" values={affected} />
      <ScenarioList title="Supporting evidence" values={supporting} />
      <ScenarioList title="Missing / constraints" values={missing} />
    </article>
  );
}

function TransmissionMatrix({
  scenarios,
  affectedGroups,
  channels
}: {
  scenarios: Array<Record<string, unknown>>;
  affectedGroups: string[];
  channels: string[];
}) {
  const groups = uniqueStrings([
    ...affectedGroups,
    ...scenarios.flatMap((item) =>
      stringList(item.affected_groups || item.evidence_groups)
    )
  ]);
  if (!scenarios.length || !groups.length) {
    return (
      <EmptyState
        description="当前证据没有足够结构化关系来绘制矩阵。"
        icon="layers"
        title="传导矩阵暂不可用"
      />
    );
  }
  return (
    <div className="transmission-matrix-wrap">
      <table className="transmission-matrix">
        <thead>
          <tr>
            <th>Scenario</th>
            {groups.map((group) => (
              <th key={group}>{humanizeKey(group)}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {scenarios.map((scenario, index) => {
            const scenarioGroups = new Set(
              stringList(scenario.affected_groups || scenario.evidence_groups)
            );
            return (
              <tr key={scenarioKey(scenario, index)}>
                <th>
                  {stringValue(
                    scenario.scenario_label ||
                      scenario.scenario_name ||
                      scenario.name
                  ) || `Scenario ${index + 1}`}
                </th>
                {groups.map((group) => (
                  <td key={group}>
                    {scenarioGroups.has(group) ? (
                      <span className="matrix-active">受影响</span>
                    ) : (
                      <span className="matrix-muted">—</span>
                    )}
                  </td>
                ))}
              </tr>
            );
          })}
        </tbody>
      </table>
      {channels.length > 0 && (
        <div className="matrix-channel-note">
          <strong>当前聚合传导：</strong>
          {channels.join(" → ")}
        </div>
      )}
    </div>
  );
}

function ModelOverviewCard({
  icon,
  label,
  value
}: {
  icon: "scenario" | "layers" | "evidence" | "diagnostics";
  label: string;
  value: string;
}) {
  return (
    <article>
      <ResearchIcon name={icon} size={21} />
      <span>{label}</span>
      <strong>{value}</strong>
    </article>
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

function FlowChips({ title, values }: { title: string; values: string[] }) {
  return (
    <section className="scenario-card-section">
      <strong>{title}</strong>
      {values.length ? (
        <div className="flow-chip-row">
          {values.map((value, index) => (
            <span key={`${value}-${index}`}>
              {humanizeKey(value)}
              {index < values.length - 1 && (
                <ResearchIcon name="chevron" size={11} />
              )}
            </span>
          ))}
        </div>
      ) : (
        <p>not available</p>
      )}
    </section>
  );
}

function ScenarioList({ title, values }: { title: string; values: string[] }) {
  return (
    <section className="scenario-card-section">
      <strong>{title}</strong>
      {values.length ? (
        <ul>
          {values.slice(0, 6).map((value) => (
            <li key={value}>{value}</li>
          ))}
        </ul>
      ) : (
        <p>not available</p>
      )}
    </section>
  );
}

function ConstraintPanel({
  title,
  items,
  empty
}: {
  title: string;
  items: string[];
  empty: string;
}) {
  return (
    <article className="constraint-panel">
      <header>
        <ResearchIcon name="shield" size={18} />
        <h3>{title}</h3>
      </header>
      {items.length ? (
        <ul>
          {items.map((item) => (
            <li key={item}>{item}</li>
          ))}
        </ul>
      ) : (
        <p>{empty}</p>
      )}
    </article>
  );
}

function findRow(rows: DashboardEvidenceRow[], key: string) {
  return rows.find((row) => row.metric_key === key);
}

function rowStringList(rows: DashboardEvidenceRow[], key: string) {
  const row = findRow(rows, key);
  return stringList(row?.value);
}

function scenarioConstraintList(scenarios: Array<Record<string, unknown>>) {
  return uniqueStrings(
    scenarios.flatMap((scenario) => [
      ...stringList(scenario.uncertainty_drivers),
      ...stringList(scenario.proxy_constraints),
      ...stringList(scenario.source_gate_constraints)
    ])
  );
}

function scenarioKey(scenario: Record<string, unknown>, index: number) {
  return (
    stringValue(
      scenario.scenario_name || scenario.scenario_label || scenario.name
    ) || `scenario-${index}`
  );
}

function uniqueStrings(values: string[]) {
  return Array.from(new Set(values.filter(Boolean)));
}

function stringValue(value: unknown) {
  if (value === null || value === undefined) return "";
  return typeof value === "string" ? value : compactText(value);
}
