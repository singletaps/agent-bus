import React, { useMemo, useState } from "react";
import { Activity, AlertTriangle, Clock3, Database, Radio } from "lucide-react";

import { EventTable } from "../components/EventTable";
import { StatusBadge } from "../components/StatusBadge";
import type {
  EventRow,
  OperationsProjection,
  RuntimeCondition,
  UiAgentSummary,
  UiDiagnosticRecord,
} from "../operationsApi";
import { statusFromState } from "../statusModel";

type DiagnosticsFilter = "all" | "warnings" | "gate" | "interrupt" | "task" | "bus";

export type DiagnosticsPageProps = {
  projection: OperationsProjection;
};

const filterLabels: Record<DiagnosticsFilter, string> = {
  all: "全部",
  warnings: "异常",
  gate: "门禁",
  interrupt: "中断",
  task: "任务",
  bus: "总线",
};

export function DiagnosticsPage({ projection }: DiagnosticsPageProps) {
  const [filter, setFilter] = useState<DiagnosticsFilter>("all");
  const events = projection.events;
  const diagnostics = projection.ui.diagnostics;
  const generatedAt = projection.generatedAt || "";

  const protocolWarnings = useMemo(
    () => collectProtocolWarnings(events, diagnostics.protocolViolations),
    [events, diagnostics.protocolViolations],
  );
  const staleEvents = useMemo(() => collectStaleEvents(events, generatedAt), [events, generatedAt]);
  const filteredEvents = useMemo(() => filterDiagnosticsEvents(events, filter), [events, filter]);
  const eventTypes = useMemo(() => Array.from(new Set(events.map((event) => event.type))).sort(), [events]);
  const hiddenAgents = useMemo(() => collectHiddenAgents(projection.ui.agentSummaries), [projection.ui.agentSummaries]);
  const archivedAgents = projection.ui.archivedAgents;
  const diagnosticAgents = useMemo(
    () => uniqueAgentSummaries([...hiddenAgents, ...archivedAgents]),
    [archivedAgents, hiddenAgents],
  );
  const conditionAgents = useMemo(
    () => diagnosticAgents.filter((agent) => agent.conditions.length || agent.hiddenReason),
    [diagnosticAgents],
  );
  const errorCount =
    events.filter((event) => event.tone === "bad").length +
    diagnostics.protocolViolations.length +
    diagnostics.fencingRejects.length;

  return (
    <section className="diagnosticsPage pageShell referencePage">
      <header className="pageHeader">
        <div>
          <span className="eyebrow">DIAGNOSTICS / AUDIT</span>
          <h2>诊断</h2>
          <p>协议事件、会话围栏、陈旧事件和运行时警告集中在这里，不进入日常通信流。</p>
        </div>
        <div className="pageToolbar">
          <StatusBadge status={statusFromState(protocolWarnings.length ? "blocked" : "completed", "run")} />
          <span className="toolbarSync">
            <Clock3 size={14} strokeWidth={2.2} />
            投影时间：{formatTime(generatedAt)}
          </span>
        </div>
      </header>

      <div className="metricStrip diagnosticsSummaryStrip">
        <Metric icon={Database} label="原始事件" value={events.length} />
        <Metric icon={Activity} label="事件类型" value={eventTypes.length} />
        <Metric icon={AlertTriangle} label="异常事件" value={errorCount} tone={errorCount ? "bad" : "good"} />
        <Metric icon={Radio} label="陈旧事件" value={staleEvents.length} tone={staleEvents.length ? "warn" : "good"} />
        <Metric icon={AlertTriangle} label="隐藏 Agent" value={diagnosticAgents.length} tone={diagnosticAgents.length ? "warn" : "good"} />
        <Metric icon={Database} label="投影效果" value={diagnostics.projectionEffects.length} tone={diagnostics.projectionEffects.length ? "info" : "good"} />
        <Metric icon={AlertTriangle} label="协议拒绝" value={diagnostics.protocolViolations.length} tone={diagnostics.protocolViolations.length ? "bad" : "good"} />
      </div>

      <div className="diagnosticsWorkspace">
        <section className="referenceCard">
          <header className="referenceCardHeader">
            <div>
              <h3>协议警告</h3>
              <p>{protocolWarnings.length} 条</p>
            </div>
          </header>
          {protocolWarnings.length ? (
            <ul className="diagnosticsList">
              {protocolWarnings.map((warning) => (
                <li key={warning}>{warning}</li>
              ))}
            </ul>
          ) : (
            <p className="emptyNote">当前事件流没有发现协议字段缺失。</p>
          )}
        </section>

        <section className="referenceCard">
          <header className="referenceCardHeader">
            <div>
              <h3>隐藏 / 归档 Agent</h3>
              <p>{diagnosticAgents.length} 个</p>
            </div>
          </header>
          <AgentConditionList
            agents={diagnosticAgents}
            emptyText="当前没有被投影隐藏或归档的 Agent。"
          />
        </section>

        <section className="referenceCard">
          <header className="referenceCardHeader">
            <div>
              <h3>运行时条件</h3>
              <p>{conditionAgents.length} 个 Agent</p>
            </div>
          </header>
          <AgentConditionList
            agents={conditionAgents}
            emptyText="隐藏 Agent 没有额外 runtime condition。"
            showConditions
          />
        </section>

        <section className="referenceCard">
          <header className="referenceCardHeader">
            <div>
              <h3>会话围栏</h3>
              <p>{diagnostics.fencingRejects.length} 条拒绝</p>
            </div>
          </header>
          <DiagnosticRecordList
            emptyText="当前没有 fencing reject。"
            records={diagnostics.fencingRejects}
          />
        </section>

        <section className="referenceCard">
          <header className="referenceCardHeader">
            <div>
              <h3>投影效果</h3>
              <p>{diagnostics.projectionEffects.length} 条</p>
            </div>
          </header>
          <DiagnosticRecordList
            emptyText="当前没有投影效果记录。"
            records={diagnostics.projectionEffects}
          />
        </section>

        <section className="referenceCard">
          <header className="referenceCardHeader">
            <div>
              <h3>旧适配器</h3>
              <p>{diagnostics.deprecatedAdapterEvents.length} 条</p>
            </div>
          </header>
          <DiagnosticRecordList
            emptyText="当前没有 deprecated adapter usage。"
            records={diagnostics.deprecatedAdapterEvents}
          />
        </section>

        <section className="referenceCard">
          <header className="referenceCardHeader">
            <div>
              <h3>事件过滤</h3>
              <p>{filterLabels[filter]}</p>
            </div>
          </header>
          <div className="segmentedControl">
            {(Object.keys(filterLabels) as DiagnosticsFilter[]).map((key) => (
              <button
                aria-pressed={filter === key}
                className="segmentButton"
                key={key}
                onClick={() => setFilter(key)}
                type="button"
              >
                {filterLabels[key]}
              </button>
            ))}
          </div>
          <div className="diagnosticsTypeList">
            {eventTypes.slice(0, 10).map((type) => (
              <span key={type}>{type}</span>
            ))}
          </div>
        </section>

        <section className="referenceCard diagnosticsRawPanel">
          <header className="referenceCardHeader">
            <div>
              <h3>原始事件</h3>
              <p>{filteredEvents.length} 条</p>
            </div>
          </header>
          <div className="eventFrame">
            <EventTable events={filteredEvents} />
          </div>
        </section>
      </div>
    </section>
  );
}

function Metric({
  icon: Icon,
  label,
  tone = "info",
  value,
}: {
  icon: React.ComponentType<{ size?: number; strokeWidth?: number }>;
  label: string;
  tone?: "good" | "warn" | "bad" | "info";
  value: number;
}) {
  return (
    <div className="metricTile diagnosticsMetric" data-tone={tone}>
      <Icon size={21} strokeWidth={2.2} />
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function DiagnosticRecordList({
  emptyText,
  records,
}: {
  emptyText: string;
  records: UiDiagnosticRecord[];
}) {
  if (!records.length) {
    return <p className="emptyNote">{emptyText}</p>;
  }
  return (
    <ul className="diagnosticsList">
      {records.slice(0, 8).map((record, index) => (
        <li key={`${record.kind}:${record.eventId || record.attemptedEventId || index}`}>
          <strong>{record.title}</strong>
          <span>{record.detail || record.effect || record.fencingResult || "无详情"}</span>
          <small>
            {[record.taskId, record.eventId || record.attemptedEventId, record.fencingResult]
              .filter(Boolean)
              .join(" · ")}
          </small>
        </li>
      ))}
    </ul>
  );
}

function AgentConditionList({
  agents,
  emptyText,
  showConditions = false,
}: {
  agents: UiAgentSummary[];
  emptyText: string;
  showConditions?: boolean;
}) {
  if (!agents.length) {
    return <p className="emptyNote">{emptyText}</p>;
  }

  return (
    <ul className="diagnosticsList">
      {agents.slice(0, 10).map((agent) => (
        <li key={`${showConditions ? "conditions" : "hidden"}:${agent.agentId}`}>
          <strong>{agent.displayName || agent.agentId}</strong>
          <span>{agentVisibilityExplanation(agent)}</span>
          {showConditions ? (
            <small>
              {agent.conditions.length
                ? agent.conditions.map(conditionSummary).join(" · ")
                : agent.hiddenReason || "无条件详情"}
            </small>
          ) : (
            <small>
              {[
                agent.identityLifecycle,
                agent.presenceState,
                agent.workloadState,
                agent.uiVisibilityState,
                agent.hiddenReason,
              ]
                .filter(Boolean)
                .join(" · ")}
            </small>
          )}
        </li>
      ))}
    </ul>
  );
}

function collectHiddenAgents(agents: UiAgentSummary[]): UiAgentSummary[] {
  return agents.filter(
    (agent) =>
      agent.uiVisibilityState !== "main" &&
      agent.uiVisibilityState !== "needs_attention",
  );
}

function uniqueAgentSummaries(agents: UiAgentSummary[]): UiAgentSummary[] {
  const result = new Map<string, UiAgentSummary>();
  for (const agent of agents) {
    if (!result.has(agent.agentId)) {
      result.set(agent.agentId, agent);
    }
  }
  return Array.from(result.values());
}

function agentVisibilityExplanation(agent: UiAgentSummary): string {
  if (agent.displayName.toLowerCase().includes("sim2") || agent.agentId.toLowerCase().includes("sim2")) {
    return "Sim2 会话被投影为归档/诊断事实，因此不会进入主通信 roster。";
  }
  if (agent.hiddenReason) {
    return agent.hiddenReason;
  }
  if (agent.identityLifecycle !== "active") {
    return `identityLifecycle=${agent.identityLifecycle}，仅在诊断/历史中保留。`;
  }
  return `uiVisibilityState=${agent.uiVisibilityState}，未进入主 roster。`;
}

function conditionSummary(condition: RuntimeCondition): string {
  const message = condition.message || condition.reason;
  return `${condition.type}:${condition.status}${message ? ` (${message})` : ""}`;
}

function collectProtocolWarnings(
  events: EventRow[],
  protocolViolations: UiDiagnosticRecord[],
): string[] {
  const warnings: string[] = [];

  protocolViolations.forEach((violation) => {
    warnings.push(`${violation.title}: ${violation.detail || violation.effect}`);
  });

  for (const event of events) {
    if (!event.id) {
      warnings.push("事件缺少 id");
    }
    if (!event.time) {
      warnings.push(`事件 ${event.id || event.type} 缺少时间戳`);
    }
    if (!event.source) {
      warnings.push(`事件 ${event.id || event.type} 缺少 actor/source`);
    }
    if (!event.type) {
      warnings.push(`事件 ${event.id || "unknown"} 缺少 type`);
    }
  }

  return Array.from(new Set(warnings)).slice(0, 12);
}

function collectStaleEvents(events: EventRow[], generatedAt: string): EventRow[] {
  const baseline = generatedAt ? new Date(generatedAt).getTime() : Date.now();
  if (Number.isNaN(baseline)) {
    return [];
  }

  return events.filter((event) => {
    const time = new Date(event.time).getTime();
    return !Number.isNaN(time) && baseline - time > 1000 * 60 * 30;
  });
}

function filterDiagnosticsEvents(events: EventRow[], filter: DiagnosticsFilter): EventRow[] {
  if (filter === "all") {
    return events;
  }

  return events.filter((event) => {
    const haystack = `${event.type} ${event.text} ${event.source} ${event.projectionEffect} ${event.fencingResult}`.toLowerCase();
    if (filter === "warnings") {
      return (
        event.tone === "bad" ||
        haystack.includes("error") ||
        haystack.includes("blocked") ||
        haystack.includes("reject") ||
        haystack.includes("wrong_session") ||
        haystack.includes("stale_epoch") ||
        haystack.includes("missing")
      );
    }
    return haystack.includes(filter);
  });
}

function formatTime(value: string): string {
  if (!value) return "等待同步";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat("zh-CN", {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  }).format(date);
}
