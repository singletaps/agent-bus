import React, { useEffect, useMemo, useState } from "react";
import {
  Archive,
  Boxes,
  CheckCircle2,
  Clock3,
  GitBranch,
  ShieldCheck,
  Users,
} from "lucide-react";

import { EventTable } from "../components/EventTable";
import { IdChip } from "../components/IdChip";
import { StatusBadge } from "../components/StatusBadge";
import type {
  AgentRow,
  ArtifactManifestRow,
  EventRow,
  GateRow,
  OperationsProjection,
  RunRow,
  TaskRow,
} from "../operationsApi";
import { fetchArtifactManifests } from "../operationsApi";
import { statusFromState } from "../statusModel";

type RunsPageProps = {
  projection: OperationsProjection;
};

type AgentGroup = {
  key: "controller" | "workers" | "qa" | "helpers";
  label: string;
  icon: React.ComponentType<{ size?: number; strokeWidth?: number }>;
  agents: AgentRow[];
};

export function RunsPage({ projection }: RunsPageProps) {
  const [artifacts, setArtifacts] = useState<ArtifactManifestRow[]>([]);
  const activeRunId = projection.ui.activeRun.runId || projection.runs[0]?.id || "";
  const [selectedRunId, setSelectedRunId] = useState(activeRunId);

  useEffect(() => {
    if (!projection.runs.length) {
      setSelectedRunId("");
      return;
    }
    if (!projection.runs.some((run) => run.id === selectedRunId)) {
      setSelectedRunId(activeRunId);
    }
  }, [activeRunId, projection.runs, selectedRunId]);

  useEffect(() => {
    const controller = new AbortController();
    void fetchArtifactManifests(controller.signal)
      .then(setArtifacts)
      .catch(() => setArtifacts([]));
    return () => controller.abort();
  }, []);

  const selectedRun =
    projection.runs.find((run) => run.id === selectedRunId) || projection.runs[0];
  const runTasks = useMemo(
    () => projection.tasks.filter((task) => task.runId === selectedRun?.id),
    [projection.tasks, selectedRun?.id],
  );
  const runGates = useMemo(
    () => projection.gates.filter((gate) => gate.runId === selectedRun?.id),
    [projection.gates, selectedRun?.id],
  );
  const runArtifacts = useMemo(
    () => artifacts.filter((artifact) => artifact.runId === selectedRun?.id),
    [artifacts, selectedRun?.id],
  );
  const runEvents = useMemo(
    () => projection.events.filter((event) => event.runId === selectedRun?.id),
    [projection.events, selectedRun?.id],
  );
  const groups = useMemo(() => buildAgentGroups(projection.agents), [projection.agents]);
  const progress = taskProgress(runTasks);
  const pendingTasks = runTasks.filter((task) => !isDoneState(task.state));
  const actionTasks = runTasks.filter((task) => isActionState(task.state));

  return (
    <section className="runsPage pageShell referencePage">
      <header className="pageHeader">
        <div>
          <span className="eyebrow">RUNGRAPH</span>
          <h2>任务流</h2>
          <p>按真实 Run、任务、门禁、产物和事件拼接运行上下文。</p>
        </div>
        {selectedRun ? (
          <div className="pageToolbar">
            <span className="toolbarSync">
              <Clock3 size={14} strokeWidth={2.2} />
              最近更新：{formatTime(projection.generatedAt)}
            </span>
          </div>
        ) : null}
      </header>

      <div className="runsWorkspace">
        <aside className="referenceCard runListPanel">
          <header className="referenceCardHeader">
            <div>
              <h3>运行列表</h3>
              <p>{projection.runs.length} runs</p>
            </div>
          </header>
          <div className="runList">
            {projection.runs.length ? (
              projection.runs.map((run) => {
                const tasks = projection.tasks.filter((task) => task.runId === run.id);
                const runProgress = taskProgress(tasks);
                const selected = run.id === selectedRun?.id;
                return (
                  <button
                    className="runListItem"
                    data-selected={selected ? "true" : "false"}
                    key={run.id}
                    onClick={() => setSelectedRunId(run.id)}
                    type="button"
                  >
                    <div className="runListTitle">
                      <strong>{run.title || run.id}</strong>
                      <IdChip value={run.id} />
                    </div>
                    <StatusBadge status={statusFromState(run.state, "run")} />
                    <div className="runProgress">
                      <span>进度 {completedCount(tasks)} / {tasks.length}</span>
                      <div>
                        <i style={{ width: `${runProgress}%` }} />
                      </div>
                      <small>{runProgress}%</small>
                    </div>
                    <span>最后更新 {formatTime(projection.generatedAt)}</span>
                  </button>
                );
              })
            ) : (
              <div className="referenceEmpty">
                <strong>暂无运行</strong>
                <span>当 Agent Bus 记录 Run 后会显示在这里。</span>
              </div>
            )}
          </div>
        </aside>

        <div className="runDetailStack">
          <section className="referenceCard runSummaryPanel">
            <header className="referenceCardHeader">
              <div>
                <h3>运行摘要</h3>
                <p>{selectedRun?.objective || "当前 Run 未记录目标描述。"}</p>
              </div>
              {selectedRun ? (
                <StatusBadge status={statusFromState(selectedRun.state, "run")} />
              ) : null}
            </header>
            <div className="factStrip">
              <Fact label="目标" value={selectedRun?.objective || selectedRun?.title || "未记录"} />
              <Fact label="当前状态" value={selectedRun?.state || "无数据"} />
              <Fact label="所有者/控制器" value={selectedRun?.owner || "controller"} />
              <Fact label="开始时间" value={formatTime(selectedRun?.startedAt)} />
              <Fact label="最后更新" value={formatTime(projection.generatedAt)} />
            </div>
            <div className="metricStrip runMetricStrip">
              <Metric label="已完成任务" value={`${completedCount(runTasks)} / ${runTasks.length}`} tone="good" />
              <Metric label="待处理任务" value={pendingTasks.length} tone={pendingTasks.length ? "warn" : "good"} />
              <Metric label="动作待处理" value={actionTasks.length} tone={actionTasks.length ? "bad" : "good"} />
              <Metric label="门禁数" value={runGates.length} tone={runGates.length ? "warn" : "info"} />
              <Metric label="产物数" value={runArtifacts.length} tone="info" />
            </div>
          </section>

          <section className="referenceCard">
            <header className="referenceCardHeader">
              <div>
                <h3>Agent 分配</h3>
                <p>按角色从当前投影分组。</p>
              </div>
            </header>
            <div className="agentAssignmentGrid">
              {groups.map((group) => (
                <AgentGroupCard group={group} key={group.key} />
              ))}
            </div>
          </section>

          <section className="referenceCard">
            <header className="referenceCardHeader">
              <div>
                <h3>任务跑道</h3>
                <p>{runTasks.length} 个任务，{completedCount(runTasks)} 个已完成</p>
              </div>
            </header>
            {runTasks.length ? (
              <div className="taskTrack" role="list">
                {runTasks.map((task, index) => (
                  <article className="taskTrackCard" data-tone={stateTone(task.state)} key={task.id} role="listitem">
                    <span className="trackIndex">{index + 1}</span>
                    <strong>{task.title}</strong>
                    <span>{task.owner || "unassigned"}</span>
                    <StatusBadge status={statusFromState(task.state, "task")} />
                    <IdChip value={task.id} />
                  </article>
                ))}
              </div>
            ) : (
              <div className="referenceEmpty">
                <strong>暂无任务</strong>
                <span>该 Run 还没有关联任务。</span>
              </div>
            )}
          </section>

          <div className="runLaneGrid">
            <LanePanel
              emptyText="该 Run 暂无门禁。"
              icon={ShieldCheck}
              items={runGates}
              meta={`${runGates.length} gates`}
              renderItem={(gate) => (
                <>
                  <strong>{gate.name}</strong>
                  <span>{gate.owner || gate.decisionBy || "未指定决策人"}</span>
                  <StatusBadge status={statusFromState(gate.state, "gate")} />
                  {gate.taskId ? <IdChip value={gate.taskId} label="Task" /> : null}
                </>
              )}
              title="门禁跑道"
            />
            <LanePanel
              emptyText="暂无 manifest-backed 产物。"
              icon={Boxes}
              items={runArtifacts}
              meta={`${runArtifacts.length} manifests`}
              renderItem={(artifact) => (
                <>
                  <strong>{artifact.title}</strong>
                  <span>{artifact.type} · {formatTime(artifact.createdAt)}</span>
                  <IdChip value={artifact.taskId || artifact.artifactId} />
                </>
              )}
              title="产物跑道"
            />
            <LanePanel
              emptyText="该 Run 暂无事件。"
              icon={Archive}
              items={runEvents.slice(0, 6)}
              meta={`${runEvents.length} events`}
              renderItem={(event) => (
                <>
                  <strong>{event.type}</strong>
                  <span>{event.text}</span>
                  <small>{formatTime(event.time)}</small>
                </>
              )}
              title="事件时间线"
            />
          </div>

          <section className="referenceCard">
            <header className="referenceCardHeader">
              <div>
                <h3>事件明细</h3>
                <p>当前 Run 的原始事件流。</p>
              </div>
            </header>
            <div className="eventFrame">
              <EventTable events={runEvents} />
            </div>
          </section>
        </div>
      </div>
    </section>
  );
}

function Fact({ label, value }: { label: string; value: string }) {
  return (
    <div className="factItem">
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function Metric({
  label,
  tone,
  value,
}: {
  label: string;
  tone: "good" | "warn" | "bad" | "info";
  value: number | string;
}) {
  return (
    <div className="metricTile" data-tone={tone}>
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function AgentGroupCard({ group }: { group: AgentGroup }) {
  const Icon = group.icon;
  return (
    <article className="agentGroupCard" data-group={group.key}>
      <div className="agentGroupIcon">
        <Icon size={19} strokeWidth={2.2} />
      </div>
      <div>
        <strong>
          {group.label} {group.agents.length ? `(${group.agents.length})` : ""}
        </strong>
        {group.agents.length ? (
          <ul>
            {group.agents.slice(0, 5).map((agent) => (
              <li key={agent.id}>
                <span>{agent.name || agent.id}</span>
                <StatusBadge status={statusFromState(agent.state, "agent")} />
              </li>
            ))}
          </ul>
        ) : (
          <span>未发现在线 Agent</span>
        )}
      </div>
    </article>
  );
}

function LanePanel<T>({
  emptyText,
  icon: Icon,
  items,
  meta,
  renderItem,
  title,
}: {
  emptyText: string;
  icon: React.ComponentType<{ size?: number; strokeWidth?: number }>;
  items: T[];
  meta: string;
  renderItem: (item: T) => React.ReactNode;
  title: string;
}) {
  return (
    <section className="referenceCard lanePanel">
      <header className="referenceCardHeader">
        <div>
          <h3>
            <Icon size={16} strokeWidth={2.2} />
            {title}
          </h3>
          <p>{meta}</p>
        </div>
      </header>
      {items.length ? (
        <div className="laneList">
          {items.map((item, index) => (
            <article className="laneItem" key={itemKey(item, index)}>
              {renderItem(item)}
            </article>
          ))}
        </div>
      ) : (
        <p className="emptyBlock">{emptyText}</p>
      )}
    </section>
  );
}

function buildAgentGroups(agents: AgentRow[]): AgentGroup[] {
  return [
    {
      key: "controller",
      label: "Controller",
      icon: GitBranch,
      agents: agents.filter((agent) => hasRole(agent, "controller")),
    },
    {
      key: "workers",
      label: "Workers",
      icon: Users,
      agents: agents.filter((agent) => hasRole(agent, "worker")),
    },
    {
      key: "qa",
      label: "QA",
      icon: ShieldCheck,
      agents: agents.filter((agent) => hasRole(agent, "qa") || hasRole(agent, "gate")),
    },
    {
      key: "helpers",
      label: "Helpers",
      icon: CheckCircle2,
      agents: agents.filter((agent) => hasRole(agent, "helper")),
    },
  ];
}

function hasRole(agent: AgentRow, role: string): boolean {
  const haystack = `${agent.role} ${agent.roles.join(" ")} ${agent.id}`.toLowerCase();
  return haystack.includes(role);
}

function completedCount(tasks: TaskRow[]): number {
  return tasks.filter((task) => isDoneState(task.state)).length;
}

function taskProgress(tasks: TaskRow[]): number {
  if (!tasks.length) return 0;
  return Math.round((completedCount(tasks) / tasks.length) * 100);
}

function isDoneState(state: string): boolean {
  return /done|complete|completed|pass|passed|approved/i.test(state);
}

function isActionState(state: string): boolean {
  return /fail|block|reject|stuck|invalid|open|escalat/i.test(state);
}

function stateTone(state: string): "good" | "warn" | "bad" | "info" {
  if (/fail|block|reject|stuck|invalid/i.test(state)) return "bad";
  if (/done|complete|pass|approved/i.test(state)) return "good";
  if (/wait|pending|queued|open|working|assigned/i.test(state)) return "warn";
  return "info";
}

function itemKey(item: unknown, index: number): string {
  if (item && typeof item === "object" && "id" in item) {
    return String((item as { id?: string }).id || index);
  }
  if (item && typeof item === "object" && "artifactId" in item) {
    return String((item as { artifactId?: string }).artifactId || index);
  }
  return String(index);
}

function formatTime(value?: string): string {
  if (!value) return "未记录";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat("zh-CN", {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  }).format(date);
}
