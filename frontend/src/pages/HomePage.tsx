import React from "react";
import {
  AlertTriangle,
  CheckCircle2,
  Clock3,
  FileText,
  GitBranch,
  Inbox,
  Radio,
  ShieldCheck,
} from "lucide-react";

import {
  type ActionDrawerCommand,
  type ActionDrawerItem,
} from "../components/ActionDrawer";
import { IdChip } from "../components/IdChip";
import { MetroGraph } from "../components/MetroGraph";
import { StatusBadge } from "../components/StatusBadge";
import type {
  OperationsProjection,
  Tone,
  UiActionItem,
  UiMetroNode,
  UiTaskWorkflowProjection,
  UiTone,
  ViewName,
} from "../operationsApi";
import type { DecisionLane, OperationsRoomModel } from "../operationsRoomModel";
import { statusFromState } from "../statusModel";
import { stateLabel } from "../uiText";

export type HomePageProps = {
  room: OperationsRoomModel;
  projection: OperationsProjection;
  onOpenAction: (item: ActionDrawerItem) => void;
  onViewChange: (view: ViewName) => void;
};

const laneOrder: DecisionLane[] = [
  "needsAction",
  "active",
  "waitingGate",
  "review",
  "done",
];

const laneLabels: Record<DecisionLane, string> = {
  needsAction: "需处理",
  active: "进行中",
  waitingGate: "等门禁",
  waiting: "等待",
  review: "审核中",
  done: "已完成",
};

const supportedCommands: ActionDrawerCommand[] = [
  "message_controller",
  "reassign",
  "request_qa",
  "open_gate",
  "view_artifact",
  "mark_known",
];

export function HomePage({
  room,
  projection,
  onOpenAction,
  onViewChange,
}: HomePageProps) {
  const activeRun = projection.ui.activeRun;
  const progress = activeRun.progress;
  const actionItems = projection.ui.actionItems.slice(0, 5);
  const actionableGateCount = projection.ui.actionableGates.length;
  const hiddenCounts = projection.ui.hiddenCounts;
  const hiddenTotal =
    hiddenCounts.archivedAgents +
    hiddenCounts.historicalGates +
    hiddenCounts.supersededGates +
    hiddenCounts.hiddenContextPackets +
    hiddenCounts.collapsedReplacementEvents +
    hiddenCounts.unboundArtifacts;
  const currentState = activeRun.state || projection.runs[0]?.state || "none";
  const workflowTaskIds = React.useMemo(
    () => Object.keys(projection.ui.taskWorkflows),
    [projection.ui.taskWorkflows],
  );
  const taskTitlesById = React.useMemo(
    () => new Map(projection.tasks.map((task) => [task.id, task.title || task.id])),
    [projection.tasks],
  );
  const defaultTaskId =
    projection.ui.selectedTaskId ||
    actionItems.find((item) => item.taskId)?.taskId ||
    workflowTaskIds[0] ||
    projection.ui.taskWorkflow.taskIds[0] ||
    "";
  const [selectedTaskId, setSelectedTaskId] = React.useState(defaultTaskId);

  React.useEffect(() => {
    if (!defaultTaskId) {
      setSelectedTaskId("");
      return;
    }
    if (!projection.ui.taskWorkflows[selectedTaskId]) {
      setSelectedTaskId(defaultTaskId);
    }
  }, [defaultTaskId, projection.ui.taskWorkflows, selectedTaskId]);

  const selectedWorkflow =
    workflowForTask(selectedTaskId, projection) ||
    projection.ui.selectedTaskWorkflow ||
    projection.ui.taskWorkflow;

  function openAction(item: UiActionItem) {
    if (item.taskId) {
      setSelectedTaskId(item.taskId);
    }
    onViewChange(item.route);
    const drawerItem = drawerItemFromAction(item);
    if (drawerItem) {
      onOpenAction(drawerItem);
    }
  }

  function openNode(node: UiMetroNode) {
    if (node.taskId) {
      setSelectedTaskId(node.taskId);
    }
    onViewChange(node.route);
    const drawerItem = drawerItemFromNode(node);
    if (drawerItem) {
      onOpenAction(drawerItem);
    }
  }

  return (
    <section className="homePage homeOpsPage">
      <section className="panel runtimePosturePanel">
        <header className="panelHeader">
          <h3>
            <span className="sectionNumber">1</span>
            当前运行态势
          </h3>
          <span>{projection.generatedAt ? formatDateTime(projection.generatedAt) : "等待同步"}</span>
        </header>
        <div className="homeMetricStrip">
          <MetricTile
            icon={<Radio size={16} strokeWidth={2.2} />}
            label="当前 Run"
            value={activeRun.runId ? <IdChip value={activeRun.runId} /> : "暂无"}
          />
          <MetricTile
            icon={<Clock3 size={16} strokeWidth={2.2} />}
            label="运行状态"
            value={<StatusBadge status={statusFromState(currentState, "run")} />}
          />
          <MetricTile
            icon={<GitBranch size={16} strokeWidth={2.2} />}
            label="任务进度"
            value={`${progress.completed || 0}/${progress.total || 0}`}
          />
          <MetricTile
            icon={<ShieldCheck size={16} strokeWidth={2.2} />}
            label="开放门禁"
            tone={actionableGateCount ? "warn" : "good"}
            value={actionableGateCount}
          />
          <MetricTile
            icon={<Inbox size={16} strokeWidth={2.2} />}
            label="行动队列"
            tone={actionItems.length ? toneForAction(actionItems[0].tone) : "good"}
            value={actionItems.length}
          />
        </div>
        {hiddenTotal ? (
          <div className="hiddenCountsStrip" aria-label="隐藏的历史事实计数">
            <span>Hidden historical facts</span>
            <strong>{hiddenTotal}</strong>
            <small>
              {hiddenCounts.archivedAgents} agents · {hiddenCounts.historicalGates} historical gates ·{" "}
              {hiddenCounts.supersededGates} superseded gates · {hiddenCounts.hiddenContextPackets} contexts ·{" "}
              {hiddenCounts.collapsedReplacementEvents} replacement events · {hiddenCounts.unboundArtifacts} artifacts
            </small>
          </div>
        ) : null}
      </section>

      <section className="panel workflowMapPanel">
        <header className="panelHeader">
          <h3>
            <span className="sectionNumber">2</span>
            任务工作流
          </h3>
          <span>
            {selectedTaskId ? `当前 Task · ${shortDisplayId(selectedTaskId)}` : `${selectedWorkflow.nodes.length} 个真实节点`}
          </span>
        </header>
        <div className="laneSummaryStrip" aria-label="任务状态汇总">
          {laneOrder.map((lane) => (
            <div className="laneSummary" data-lane={lane} key={lane}>
              <span>{laneLabels[lane]}</span>
              <strong>{room.decisionLanes[lane].length}</strong>
              <small>{laneSummaryText(lane, room.decisionLanes[lane][0]?.title)}</small>
            </div>
          ))}
        </div>
        {workflowTaskIds.length > 1 ? (
          <div className="workflowTaskPicker" aria-label="选择任务工作流">
            {workflowTaskIds.map((taskId) => (
              <button
                aria-pressed={taskId === selectedTaskId}
                className="workflowTaskButton"
                data-selected={taskId === selectedTaskId ? "true" : "false"}
                key={taskId}
                onClick={() => setSelectedTaskId(taskId)}
                title={taskId}
                type="button"
              >
                <span>{taskTitlesById.get(taskId) || shortDisplayId(taskId)}</span>
                <small>{shortDisplayId(taskId)}</small>
              </button>
            ))}
          </div>
        ) : null}
        <MetroGraph metro={selectedWorkflow} onNodeSelect={openNode} />
      </section>

      <section className="panel actionQueuePanel">
        <header className="panelHeader">
          <h3>
            <span className="sectionNumber">3</span>
            行动队列
          </h3>
          <span>{actionItems.length} 项</span>
        </header>
        <div className="actionQueueList">
          {actionItems.length ? (
            actionItems.map((item) => (
              <article
                className="referenceCard actionQueueCard"
                data-tone={item.tone}
                key={item.id}
              >
                <div className="actionQueueTopline">
                  <span className="actionQueueIcon">{actionIcon(item)}</span>
                  <span>{actionKindLabel(item.kind)}</span>
                  <StatusBadge status={statusFromState(actionStatus(item), item.kind === "gate" ? "gate" : "task")} />
                </div>
                <strong>{item.title}</strong>
                <p>{item.description || "查看真实运行上下文后选择下一步。"}</p>
                <div className="actionQueueMeta">
                  {item.runId ? <IdChip label="Run" value={item.runId} /> : null}
                  {item.taskId ? <IdChip label="Task" value={item.taskId} /> : null}
                  {item.agentId ? <IdChip label="Agent" value={item.agentId} /> : null}
                </div>
                <ActionWorkflowStrip
                  item={item}
                  metro={workflowForTask(item.taskId, projection) || selectedWorkflow}
                  onNodeSelect={openNode}
                />
                <button
                  className={item.tone === "bad" ? "commandButton" : "filterButton"}
                  onClick={() => openAction(item)}
                  type="button"
                >
                  {actionButtonLabel(item)}
                </button>
              </article>
            ))
          ) : (
            <div className="emptyState">
              <CheckCircle2 size={24} strokeWidth={2.2} />
              <h3>当前没有待处理行动</h3>
              <p>继续观察任务流、门禁、通信和产物更新。</p>
              <button
                className="filterButton"
                onClick={() => onViewChange("Runs")}
                type="button"
              >
                查看任务流
              </button>
            </div>
          )}
        </div>
      </section>
    </section>
  );
}

type WorkflowStep = {
  id: string;
  title: string;
  subtitle: string;
  tone: UiTone;
  node?: UiMetroNode;
};

function workflowForTask(
  taskId: string,
  projection: OperationsProjection,
): UiTaskWorkflowProjection | undefined {
  if (!taskId) {
    return undefined;
  }
  return projection.ui.taskWorkflows[taskId];
}

function shortDisplayId(value: string): string {
  return value.length > 12 ? `${value.slice(0, 10)}...` : value;
}

function ActionWorkflowStrip({
  item,
  metro,
  onNodeSelect,
}: {
  item: UiActionItem;
  metro: UiTaskWorkflowProjection;
  onNodeSelect: (node: UiMetroNode) => void;
}) {
  const steps = workflowStepsForAction(item, metro);
  if (steps.length === 0) {
    return null;
  }
  return (
    <div className="actionWorkflowStrip" aria-label={`${item.title} workflow`}>
      {steps.map((step, index) => {
        const content = (
          <>
            <span className="actionWorkflowDot" data-tone={step.tone} />
            <span className="actionWorkflowCopy">
              <strong>{step.title}</strong>
              <small>{step.subtitle}</small>
            </span>
          </>
        );
        return (
          <React.Fragment key={step.id}>
            {index > 0 ? <span className="actionWorkflowLine" /> : null}
            {step.node ? (
              <button
                className="actionWorkflowStep"
                onClick={() => onNodeSelect(step.node as UiMetroNode)}
                type="button"
              >
                {content}
              </button>
            ) : (
              <span className="actionWorkflowStep">{content}</span>
            )}
          </React.Fragment>
        );
      })}
    </div>
  );
}

function workflowStepsForAction(
  item: UiActionItem,
  metro: UiTaskWorkflowProjection,
): WorkflowStep[] {
  const nodeById = new Map(metro.nodes.map((node) => [node.id, node]));
  const start = metro.mainPathNodeIds
    .map((id) => nodeById.get(id))
    .find((node): node is UiMetroNode => Boolean(node));
  const taskNode = item.taskId ? nodeById.get(`task:${item.taskId}`) : undefined;
  const gateNode = item.gateId ? nodeById.get(`gate:${item.gateId}`) : undefined;
  const artifactNode = item.artifactId
    ? nodeById.get(`artifact:${item.artifactId}`)
    : undefined;
  const focus = gateNode || artifactNode || taskNode;

  const nodes: UiMetroNode[] = [];
  if (start) {
    nodes.push(start);
  }
  if (taskNode && taskNode.id !== start?.id) {
    nodes.push(taskNode);
  }
  if (focus && !nodes.some((node) => node.id === focus.id)) {
    nodes.push(focus);
  }

  if (!focus && metro.currentNodeId) {
    const currentNode = nodeById.get(metro.currentNodeId);
    if (currentNode && !nodes.some((node) => node.id === currentNode.id)) {
      nodes.push(currentNode);
    }
  }

  const steps: WorkflowStep[] = nodes.slice(0, 3).map((node) => ({
    id: node.id,
    title: nodeTitle(node),
    subtitle: stateLabel(node.state),
    tone: node.tone,
    node,
  }));

  steps.push({
    id: `action:${item.id}`,
    title: actionKindLabel(item.kind),
    subtitle: item.agentId || item.route,
    tone: item.tone,
  });

  return steps.slice(-4);
}

function nodeTitle(node: UiMetroNode): string {
  if (node.kind === "start") {
    return "Run";
  }
  if (node.kind === "context") {
    return "上下文";
  }
  if (node.kind === "claim") {
    return "声明";
  }
  if (node.kind === "gate") {
    return "门禁";
  }
  if (node.kind === "artifact") {
    return "产物";
  }
  if (node.kind === "replacement") {
    return "替换";
  }
  if (node.kind === "terminal") {
    return "终点";
  }
  return "任务";
}

function drawerItemFromAction(item: UiActionItem): ActionDrawerItem | null {
  const kind = drawerKind(item.kind);
  return {
    kind,
    id: item.gateId || item.artifactId || item.taskId || item.agentId || item.id,
    title: item.title,
    runId: item.runId || undefined,
    taskId: item.taskId || undefined,
    suggestedActions: normalizeCommands(item.suggestedActions, kind),
  };
}

function drawerItemFromNode(node: UiMetroNode): ActionDrawerItem | null {
  if (node.kind === "start") {
    return null;
  }
  const kind = drawerKind(node.kind);
  return {
    kind,
    id: node.gateId || node.artifactId || node.taskId || node.agentId || node.id,
    title: node.title,
    runId: node.runId || undefined,
    taskId: node.taskId || undefined,
    suggestedActions: normalizeCommands([], kind),
  };
}

function drawerKind(kind: string): ActionDrawerItem["kind"] {
  if (kind === "gate") {
    return "gate";
  }
  if (kind === "artifact") {
    return "artifact";
  }
  if (kind === "inbox" || kind === "agent_health" || kind === "message") {
    return "message";
  }
  return "task";
}

function normalizeCommands(
  actions: string[],
  kind: ActionDrawerItem["kind"],
): ActionDrawerCommand[] {
  const filtered = actions.filter((action): action is ActionDrawerCommand =>
    supportedCommands.includes(action as ActionDrawerCommand),
  );
  if (filtered.length) {
    return filtered;
  }
  if (kind === "gate") {
    return ["open_gate", "message_controller", "request_qa"];
  }
  if (kind === "artifact") {
    return ["view_artifact", "message_controller"];
  }
  if (kind === "message") {
    return ["message_controller", "mark_known"];
  }
  return ["message_controller", "reassign", "request_qa"];
}

function actionStatus(item: UiActionItem): string {
  if (item.kind === "gate") {
    return item.tone === "bad" ? "open" : "open";
  }
  if (item.kind === "artifact") {
    return "available";
  }
  if (item.kind === "agent_health") {
    return item.tone === "bad" ? "failed" : "blocked";
  }
  return item.tone === "good" ? "completed" : item.tone === "bad" ? "failed" : "working";
}

function actionKindLabel(kind: string): string {
  const labels: Record<string, string> = {
    agent_health: "Agent 健康",
    artifact: "产物",
    gate: "门禁",
    inbox: "通信",
    review: "审核",
    task: "任务",
  };
  return labels[kind] || kind;
}

function actionButtonLabel(item: UiActionItem): string {
  if (item.route === "Gates") {
    return "查看门禁";
  }
  if (item.route === "Artifacts") {
    return "查看产物";
  }
  if (item.route === "Communication") {
    return "进入通信";
  }
  if (item.route === "Diagnostics") {
    return "查看诊断";
  }
  return "查看详情";
}

function actionIcon(item: UiActionItem) {
  const props = { size: 16, strokeWidth: 2.2 };
  if (item.kind === "gate") {
    return <ShieldCheck {...props} />;
  }
  if (item.kind === "artifact") {
    return <FileText {...props} />;
  }
  if (item.kind === "inbox") {
    return <Inbox {...props} />;
  }
  if (item.tone === "bad" || item.kind === "agent_health") {
    return <AlertTriangle {...props} />;
  }
  return <GitBranch {...props} />;
}

function laneSummaryText(lane: DecisionLane, firstTitle?: string): string {
  if (firstTitle) {
    return firstTitle;
  }
  if (lane === "done") {
    return "等待新的完成记录";
  }
  return "暂无队列项";
}

function toneForAction(tone: UiTone): Tone {
  if (tone === "good" || tone === "warn" || tone === "bad" || tone === "info") {
    return tone;
  }
  return "info";
}

function formatDateTime(value: string): string {
  if (!value) {
    return "等待同步";
  }
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value.length > 16 ? `${value.slice(0, 13)}...` : value;
  }
  return date.toLocaleString();
}

function MetricTile({
  icon,
  label,
  value,
  tone = "info",
}: {
  icon: React.ReactNode;
  label: string;
  value: number | string | React.ReactNode;
  tone?: Tone;
}) {
  return (
    <div className="metricTile" data-tone={tone}>
      <span className="metricTileIcon">{icon}</span>
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}
