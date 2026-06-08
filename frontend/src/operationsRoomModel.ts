import type {
  AgentRow,
  EventRow,
  GateRow,
  OperationsProjection,
  RuntimeCondition,
  TaskRow,
  Tone,
  UiAgentSummary,
} from "./operationsApi";
import { stateLabel } from "./uiText";

export type AgentPresence = "alive" | "busy" | "degraded" | "lost";
export type MissionLane = "active" | "attention" | "backlog";
export type OperatorActionTone = "good" | "warn" | "bad" | "info";
export type OperatorActionKind =
  | "review-task"
  | "inspect-failure"
  | "approve-gate"
  | "watch-inbox"
  | "monitor";
export type WorkstationRole =
  | "controller"
  | "frontend"
  | "backend"
  | "qa"
  | "helper"
  | "observer"
  | "worker"
  | "unknown";
export type WorkstationPosture =
  | "working"
  | "standby"
  | "waiting"
  | "review"
  | "gate"
  | "degraded"
  | "fault";
export type DecisionLane =
  | "needsAction"
  | "active"
  | "waitingGate"
  | "review"
  | "done"
  | "waiting";

export type OperationsBrief = {
  headline: string;
  detail: string;
  activeRunLabel: string;
  activeRunMeta: string;
  activeRunShortId: string;
  primaryAction: {
    kind: OperatorActionKind;
    label: string;
    targetId: string;
    tone: OperatorActionTone;
  };
};

export type AgentCardModel = AgentRow & {
  identityLifecycle: string;
  presenceState: string;
  workloadState: string;
  uiVisibilityState: string;
  conditions: RuntimeCondition[];
  hiddenReason: string;
  presence: AgentPresence;
  stateText: string;
  shortSession: string;
};

export type TaskCardModel = TaskRow & {
  lane: MissionLane;
  decisionLane: DecisionLane;
  stateText: string;
  progress: number;
  nextAction: string;
  shortTaskId: string;
  shortRunId: string;
  ownerText: string;
};

export type OperationsRoomModel = {
  brief: OperationsBrief;
  workstations: WorkstationModel[];
  aliveAgents: AgentCardModel[];
  degradedAgents: AgentCardModel[];
  decisionLanes: Record<DecisionLane, TaskCardModel[]>;
  taskLanes: Record<MissionLane, TaskCardModel[]>;
  urgentGates: GateRow[];
  eventConsole: EventRow[];
  topRiskTone: Tone;
};

export type WorkstationModel = AgentCardModel & {
  roleKind: WorkstationRole;
  posture: WorkstationPosture;
  postureText: string;
  currentWork: string;
  nextAction: string;
  urgency: OperatorActionTone;
};

export function shortId(value: string, head = 8): string {
  const display = displayOrEmpty(value);
  if (!display) return "";
  if (display.length <= head + 1) return display;
  return `${display.slice(0, head)}…`;
}

export function displayOrEmpty(value: string): string {
  const trimmed = value?.trim() || "";
  const normalized = trimmed.toLowerCase();
  if (
    !trimmed ||
    normalized === "unknown" ||
    normalized === "none" ||
    normalized === "no-run" ||
    normalized === "no-session" ||
    normalized === "unassigned"
  ) {
    return "";
  }
  return trimmed;
}

export function agentPresence(agent: AgentCardModel): AgentPresence {
  const presence = agent.presenceState.toLowerCase();
  const workload = agent.workloadState.toLowerCase();
  if (presence === "offline" || workload === "blocked" || hasFaultCondition(agent.conditions)) {
    return "lost";
  }
  if (presence === "stale" || agent.uiVisibilityState === "needs_attention") {
    return "degraded";
  }
  if (["assigned", "working"].includes(workload)) {
    return "busy";
  }
  return "alive";
}

function agentCardFromSummary(
  summary: UiAgentSummary,
  fallback?: AgentRow,
): AgentCardModel {
  const role = summary.role || fallback?.role || "unassigned";
  const base: AgentRow = {
    id: summary.agentId || fallback?.id || "unknown-agent",
    name: summary.displayName || fallback?.name || summary.agentId || "unknown-agent",
    role,
    roles: fallback?.roles?.length ? fallback.roles : role ? [role] : [],
    sessionId: fallback?.sessionId || "no-session",
    state: summary.runtimeState || fallback?.state || summary.presenceState || "unknown",
    inboxCount: summary.queuedInbox,
    capabilities: fallback?.capabilities || [],
  };

  return {
    ...base,
    identityLifecycle: summary.identityLifecycle,
    presenceState: summary.presenceState,
    workloadState: summary.workloadState,
    uiVisibilityState: summary.uiVisibilityState,
    conditions: summary.conditions,
    hiddenReason: summary.hiddenReason,
    presence: "alive",
    stateText: "",
    shortSession: "",
  };
}

function runtimeStateText(agent: AgentCardModel): string {
  if (agent.uiVisibilityState === "needs_attention") {
    return "Needs attention";
  }
  const presenceLabels: Record<string, string> = {
    online: "Online",
    stale: "Stale",
    offline: "Offline",
    unknown: "Unknown",
  };
  const workloadLabels: Record<string, string> = {
    assigned: "Assigned",
    blocked: "Blocked",
    claim_pending: "Claim pending",
    free: "Free",
    historical: "Historical",
    waiting_gate: "Waiting gate",
    waiting_input: "Waiting input",
    waiting_review: "Waiting review",
    working: "Working",
  };
  return (
    presenceLabels[agent.presenceState] ||
    workloadLabels[agent.workloadState] ||
    displayOrEmpty(agent.presenceState) ||
    displayOrEmpty(agent.workloadState) ||
    "待更新"
  );
}

function hasFaultCondition(conditions: RuntimeCondition[]): boolean {
  return conditions.some((condition) => {
    const severity = condition.severity.toLowerCase();
    if (severity === "critical" || severity === "error") {
      return true;
    }
    const type = condition.type.toLowerCase();
    return (
      condition.status === "true" &&
      (type.includes("replacementrecommended") || type.includes("contextlost"))
    );
  });
}

export function taskLane(task: TaskRow): MissionLane {
  const state = task.state.toLowerCase();
  if (
    ["working", "assigned", "acknowledged", "in_progress"].some((value) =>
      state.includes(value),
    )
  ) {
    return "active";
  }
  if (
    ["blocked", "failed", "changes_requested", "reassigned"].some((value) =>
      state.includes(value),
    )
  ) {
    return "attention";
  }
  return "backlog";
}

export function decisionLane(task: TaskRow): DecisionLane {
  const state = task.state.toLowerCase().replace(/[_-]/g, " ");
  if (
    [
      "failed",
      "fail",
      "blocked",
      "changes requested",
      "context lost",
      "lost",
      "invalid",
      "rejected",
    ].some((value) => state.includes(value))
  ) {
    return "needsAction";
  }
  if (
    ["completed", "complete", "done", "approved", "passed"].some((value) =>
      state.includes(value),
    )
  ) {
    return "done";
  }
  if (
    ["review", "qa", "ready", "evidence", "validation"].some((value) =>
      state.includes(value),
    )
  ) {
    return "review";
  }
  if (
    ["gate", "pending", "waiting approval", "approval", "waiting"].some(
      (value) => state.includes(value),
    )
  ) {
    return "waitingGate";
  }
  if (
    [
      "working",
      "assigned",
      "acknowledged",
      "in progress",
      "progress",
      "created",
      "queued",
    ].some((value) => state.includes(value))
  ) {
    return "active";
  }
  return "active";
}

export function buildOperationsRoomModel(
  projection: OperationsProjection,
): OperationsRoomModel {
  const agentRowsById = new Map(projection.agents.map((agent) => [agent.id, agent]));
  const visibleSummaries = projection.ui.visibleAgents.filter(
    (agent) => agent.uiVisibilityState === "main" || agent.uiVisibilityState === "needs_attention",
  );
  const agents = visibleSummaries.map((summary) => {
    const agent = agentCardFromSummary(summary, agentRowsById.get(summary.agentId));
    return {
      ...agent,
      presence: agentPresence(agent),
      stateText: runtimeStateText(agent),
      shortSession: shortSessionId(agent.sessionId),
    };
  });

  const tasks = projection.tasks.map((task) => {
    const lane = decisionLane(task);
    return {
      ...task,
      title: displayOrEmpty(task.title) || task.id,
      lane: taskLane(task),
      decisionLane: lane,
      stateText: displayOrEmpty(stateLabel(task.state)) || "待更新",
      progress: taskProgress(task),
      nextAction: taskNextAction(task),
      shortTaskId: shortId(task.id, 10),
      shortRunId: shortId(task.runId, 10),
      ownerText: displayOrEmpty(task.owner) || "未分配",
    };
  });

  const taskLanes: Record<MissionLane, TaskCardModel[]> = {
    active: tasks.filter((task) => task.lane === "active"),
    attention: tasks.filter((task) => task.lane === "attention"),
    backlog: tasks.filter((task) => task.lane === "backlog"),
  };

  const actionableGateIds = new Set(projection.ui.actionableGates.map((gate) => gate.gateId));
  const urgentGates = projection.gates.filter((gate) => actionableGateIds.has(gate.id));

  const waitingGate = tasks.filter((task) => task.decisionLane === "waitingGate");
  const decisionLanes: Record<DecisionLane, TaskCardModel[]> = {
    needsAction: tasks.filter((task) => task.decisionLane === "needsAction"),
    active: tasks.filter((task) => task.decisionLane === "active"),
    waitingGate,
    waiting: waitingGate,
    review: tasks.filter((task) => task.decisionLane === "review"),
    done: tasks.filter((task) => task.decisionLane === "done").slice(0, 8),
  };

  const brief = buildBrief(projection, tasks, urgentGates);
  const workstations = agents.map((agent) => buildWorkstation(agent, tasks));

  const topRiskTone: Tone =
    projection.metrics.contextFaults > 0 ||
    decisionLanes.needsAction.length > 0 ||
    workstations.some(
      (agent) => agent.posture === "fault" || agent.posture === "degraded",
    )
      ? "bad"
      : urgentGates.length > 0 || decisionLanes.waitingGate.length > 0
        ? "warn"
        : "good";

  return {
    brief,
    workstations,
    aliveAgents: agents.filter(
      (agent) => agent.presence === "alive" || agent.presence === "busy",
    ),
    degradedAgents: agents.filter(
      (agent) => agent.presence === "degraded" || agent.presence === "lost",
    ),
    decisionLanes,
    taskLanes,
    urgentGates,
    eventConsole: projection.events.slice(0, 80),
    topRiskTone,
  };
}

function buildBrief(
  projection: OperationsProjection,
  tasks: TaskCardModel[],
  urgentGates: GateRow[],
): OperationsBrief {
  const activeTaskCount = tasks.filter((task) => task.decisionLane !== "done").length;
  const activeRun = projection.runs[0];
  const runFields = {
    activeRunLabel: activeRun ? "Live Round 1" : "暂无任务流",
    activeRunMeta: `运行中 · ${activeTaskCount} tasks`,
    activeRunShortId: activeRun ? shortId(activeRun.id, 10) : "",
  };

  const actionTask = tasks.find((task) => task.decisionLane === "needsAction");
  if (actionTask) {
    return {
      ...runFields,
      headline: "需要处理任务异常",
      detail: `${actionTask.title} 需要定位、复查或重新分派。`,
      primaryAction: {
        kind: "inspect-failure",
        label: "处理异常任务",
        targetId: actionTask.id,
        tone: "bad",
      },
    };
  }

  const gate = urgentGates[0];
  if (gate) {
    return {
      ...runFields,
      headline: "门禁等待决策",
      detail: `${gate.name} 等待 ${displayOrEmpty(gate.owner) || "负责人"} 处理。`,
      primaryAction: {
        kind: "approve-gate",
        label: "查看开放门禁",
        targetId: gate.id,
        tone: "warn",
      },
    };
  }

  if (projection.metrics.contextFaults > 0) {
    return {
      ...runFields,
      headline: "上下文风险需要确认",
      detail: `${projection.metrics.contextFaults} 个上下文风险需要运行方确认。`,
      primaryAction: {
        kind: "inspect-failure",
        label: "检查上下文",
        targetId: "agent-dock",
        tone: "bad",
      },
    };
  }

  if (projection.metrics.pendingInbox > 0) {
    return {
      ...runFields,
      headline: "总线有待确认消息",
      detail: `${projection.metrics.pendingInbox} 条 inbox 需要相关 Agent 消化。`,
      primaryAction: {
        kind: "watch-inbox",
        label: "查看智能体",
        targetId: "agent-dock",
        tone: "warn",
      },
    };
  }

  return {
    ...runFields,
    headline: "系统平稳运行",
    detail: "当前没有开放门禁、任务异常或上下文风险。",
    primaryAction: {
      kind: "monitor",
      label: "继续监控",
      targetId: "operations",
      tone: "good",
    },
  };
}

function buildWorkstation(
  agent: AgentCardModel,
  tasks: TaskCardModel[],
): WorkstationModel {
  const activeTask = tasks.find(
    (task) => task.owner === agent.id && task.decisionLane !== "done",
  );
  const posture = workstationPosture(agent);

  return {
    ...agent,
    roleKind: workstationRole(agent),
    posture,
    postureText: workstationPostureLabel(posture),
    currentWork:
      activeTask?.title ||
      (agent.inboxCount > 0 ? `${agent.inboxCount} 条 inbox` : "当前无任务"),
    nextAction: nextActionForAgent(agent, activeTask),
    urgency:
      posture === "fault"
        ? "bad"
        : posture === "degraded" || agent.inboxCount > 0
          ? "warn"
          : posture === "working"
            ? "info"
            : "good",
  };
}

function workstationRole(agent: AgentRow): WorkstationRole {
  const value = `${agent.id} ${agent.name} ${agent.role} ${agent.roles.join(" ")}`.toLowerCase();
  if (value.includes("helper")) return "helper";
  if (value.includes("qa")) return "qa";
  if (value.includes("controller")) return "controller";
  if (value.includes("observer") || value.includes("archive")) {
    return "observer";
  }
  if (value.includes("frontend") || value.includes("react")) return "frontend";
  if (
    value.includes("backend") ||
    value.includes("store") ||
    value.includes("fastapi") ||
    value.includes("server")
  ) {
    return "backend";
  }
  if (value.includes("worker")) return "worker";
  return "unknown";
}

function workstationPosture(agent: AgentCardModel): WorkstationPosture {
  const workload = agent.workloadState.toLowerCase();
  if (agent.presenceState === "offline" || workload === "blocked" || hasFaultCondition(agent.conditions)) {
    return "fault";
  }
  if (agent.presenceState === "stale" || agent.uiVisibilityState === "needs_attention") {
    return "degraded";
  }
  if (workload === "waiting_gate") return "gate";
  if (workload === "waiting_review") return "review";
  if (workload === "working" || workload === "assigned") return "working";
  if (["waiting_input", "claim_pending"].includes(workload)) return "waiting";
  return "standby";
}

function workstationPostureLabel(posture: WorkstationPosture): string {
  const labels: Record<WorkstationPosture, string> = {
    working: "工作中",
    standby: "待命",
    waiting: "等待中",
    review: "等待审查",
    gate: "等待门禁",
    degraded: "降级注意",
    fault: "故障处理",
  };
  return labels[posture];
}

function nextActionForAgent(
  agent: AgentCardModel,
  activeTask: TaskCardModel | undefined,
): string {
  const posture = workstationPosture(agent);
  if (posture === "fault") return "恢复上下文或接管";
  if (posture === "degraded") return "检查会话状态";
  if (posture === "gate") return "处理门禁";
  if (posture === "review") return "查看证据";
  if (activeTask && activeTask.decisionLane === "needsAction") {
    return "定位异常任务";
  }
  if (activeTask) return activeTask.nextAction;
  if (agent.inboxCount > 0) return "处理 inbox";
  if (posture === "waiting") return "等待总线";
  return "保持待命";
}

function taskProgress(task: TaskRow): number {
  const state = task.state.toLowerCase().replace(/[_-]/g, " ");
  if (
    ["failed", "fail", "blocked", "changes requested", "rejected"].some(
      (value) => state.includes(value),
    )
  ) {
    return 0;
  }
  if (
    ["completed", "complete", "approved", "passed", "done"].some((value) =>
      state.includes(value),
    )
  ) {
    return 100;
  }
  if (["review", "ready", "qa"].some((value) => state.includes(value))) {
    return 85;
  }
  if (
    ["working", "in progress", "progress"].some((value) =>
      state.includes(value),
    )
  ) {
    return 70;
  }
  if (
    ["assigned", "acknowledged", "created", "queued"].some((value) =>
      state.includes(value),
    )
  ) {
    return 30;
  }
  return 0;
}

function taskNextAction(task: TaskRow): string {
  const lane = decisionLane(task);
  const state = task.state.toLowerCase().replace(/[_-]/g, " ");
  if (lane === "needsAction") return "定位、复查或重新分派";
  if (lane === "waitingGate") return "等待门禁决策";
  if (lane === "review") return "查看证据并审查";
  if (lane === "done") return "归档";
  if (
    ["working", "in progress", "progress"].some((value) =>
      state.includes(value),
    )
  ) {
    return "继续执行并上传证据";
  }
  if (
    ["assigned", "acknowledged", "created", "queued"].some((value) =>
      state.includes(value),
    )
  ) {
    return "开始执行";
  }
  return "等待更新";
}

function shortSessionId(sessionId: string): string {
  return shortId(sessionId, 10) || "无会话";
}

function isClosedState(state: string): boolean {
  const value = state.toLowerCase();
  return ["approved", "closed", "complete", "completed", "done", "passed"].some(
    (closed) => value.includes(closed),
  );
}
