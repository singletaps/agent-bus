import React, { useMemo, useState } from "react";
import { Activity, AlertTriangle, Clock3, Database, Radio } from "lucide-react";

import { EventTable } from "../components/EventTable";
import { StatusBadge } from "../components/StatusBadge";
import type { EventRow, OperationsProjection } from "../operationsApi";
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
  const generatedAt = projection.generatedAt || "";

  const protocolWarnings = useMemo(() => collectProtocolWarnings(events), [events]);
  const staleEvents = useMemo(() => collectStaleEvents(events, generatedAt), [events, generatedAt]);
  const filteredEvents = useMemo(() => filterDiagnosticsEvents(events, filter), [events, filter]);
  const eventTypes = useMemo(() => Array.from(new Set(events.map((event) => event.type))).sort(), [events]);
  const errorCount = events.filter((event) => event.tone === "bad").length;

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
              <h3>会话围栏</h3>
              <p>{projection.source}</p>
            </div>
          </header>
          <dl className="diagnosticsFacts">
            <div>
              <dt>投影时间</dt>
              <dd>{generatedAt || "无数据"}</dd>
            </div>
            <div>
              <dt>涉及 Agent</dt>
              <dd>{projection.agents.length}</dd>
            </div>
            <div>
              <dt>待处理 inbox</dt>
              <dd>{projection.metrics.pendingInbox}</dd>
            </div>
            <div>
              <dt>开放门禁</dt>
              <dd>{projection.metrics.openGateCount}</dd>
            </div>
          </dl>
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

function collectProtocolWarnings(events: EventRow[]): string[] {
  const warnings: string[] = [];

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
    const haystack = `${event.type} ${event.text} ${event.source}`.toLowerCase();
    if (filter === "warnings") {
      return event.tone === "bad" || haystack.includes("error") || haystack.includes("blocked");
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
