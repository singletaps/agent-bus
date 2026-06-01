import React, { useCallback, useEffect, useMemo, useState } from "react";
import {
  Activity,
  Boxes,
  Command,
  GitBranch,
  House,
  Layout,
  ListChecks,
  Radio,
  Radar,
  Send,
  Server,
  ShieldCheck,
  Wrench,
} from "lucide-react";
import {
  DecisionLane,
  OperationsRoomModel,
  TaskCardModel,
  WorkstationRole,
  WorkstationModel,
  buildOperationsRoomModel,
  displayOrEmpty,
} from "./operationsRoomModel";
import {
  ActionDrawer,
  type ActionDrawerItem,
  type ActionDrawerSubmitPayload,
} from "./components/ActionDrawer";
import { PageToolbar } from "./components/PageToolbar";
import { ArtifactsPage } from "./pages/ArtifactsPage";
import { CommunicationPage } from "./pages/CommunicationPage";
import { DiagnosticsPage } from "./pages/DiagnosticsPage";
import { GatesPage } from "./pages/GatesPage";
import { HomePage } from "./pages/HomePage";
import { RunsPage } from "./pages/RunsPage";
import {
  AgentRow,
  ArtifactRow,
  EventRow,
  GateRow,
  OperationsProjection,
  ReplacementRow,
  TaskRow,
  Tone,
  ViewName,
  emptyOperationsProjection,
  fetchOperationsProjection,
  sendBusMessage,
} from "./operationsApi";
import { uiText, viewLabels } from "./uiText";
import { stateLabel } from "./uiText";

const views: ViewName[] = [
  "Home",
  "Communication",
  "Runs",
  "Gates",
  "Artifacts",
  "Diagnostics",
  "Settings",
];

const viewIcons: Record<
  ViewName,
  React.ComponentType<{ size?: number; strokeWidth?: number }>
> = {
  Home: House,
  Communication: Send,
  Runs: GitBranch,
  Gates: ShieldCheck,
  Artifacts: Boxes,
  Diagnostics: Activity,
  Settings: ListChecks,
};

type LoadState = "loading" | "ready" | "error";
type EventFilter = "all" | "gate" | "interrupt" | "replacement" | "error";
type GateFilter = "open" | "high" | "handled" | "all";

const decisionLaneOrder: DecisionLane[] = [
  "needsAction",
  "active",
  "waitingGate",
  "review",
  "done",
];
const focusLaneOrder: DecisionLane[] = [
  "needsAction",
  "active",
  "waitingGate",
  "review",
];
const laneCardLimit: Record<DecisionLane, number> = {
  needsAction: 3,
  active: 2,
  waitingGate: 2,
  waiting: 2,
  review: 2,
  done: 4,
};
const gateFilterOrder: GateFilter[] = ["open", "high", "handled", "all"];
const eventFilterOrder: EventFilter[] = [
  "all",
  "gate",
  "interrupt",
  "replacement",
  "error",
];

const loadStateLabels: Record<LoadState, string> = {
  loading: "同步中",
  ready: "已同步",
  error: "异常",
};

const eventFilterLabels: Record<EventFilter, string> = {
  all: uiText.eventFilters.all,
  gate: uiText.eventFilters.gate,
  interrupt: uiText.eventFilters.interrupt,
  replacement: uiText.eventFilters.replacement,
  error: uiText.eventFilters.error,
};

const gateFilterLabels: Record<GateFilter, string> = {
  open: uiText.gateTabs.open,
  high: uiText.gateTabs.high,
  handled: uiText.gateTabs.handled,
  all: uiText.gateTabs.all,
};

function App() {
  const [activeView, setActiveView] = useState<ViewName>("Home");
  const [projection, setProjection] = useState<OperationsProjection>(
    emptyOperationsProjection,
  );
  const [loadState, setLoadState] = useState<LoadState>("loading");
  const [loadError, setLoadError] = useState("");
  const [lastLoadedAt, setLastLoadedAt] = useState("");
  const [selectedTaskId, setSelectedTaskId] = useState("");
  const [selectedAgentId, setSelectedAgentId] = useState("");
  const [eventFilter, setEventFilter] = useState<EventFilter>("all");
  const [gateFilter, setGateFilter] = useState<GateFilter>("open");
  const [commandStatus, setCommandStatus] = useState("");
  const [drawerItem, setDrawerItem] = useState<ActionDrawerItem | null>(null);

  const loadProjection = useCallback(async (signal?: AbortSignal) => {
    try {
      setLoadState((state) => (state === "ready" ? "ready" : "loading"));
      const nextProjection = await fetchOperationsProjection(signal);
      setProjection(nextProjection);
      setLoadState("ready");
      setLoadError("");
      setLastLoadedAt(new Date().toLocaleTimeString());
    } catch (error) {
      if (signal?.aborted) {
        return;
      }
      setLoadState("error");
      setLoadError(error instanceof Error ? error.message : "数据加载失败");
    }
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    void loadProjection(controller.signal);
    const intervalId = window.setInterval(() => {
      void loadProjection();
    }, 5000);

    return () => {
      controller.abort();
      window.clearInterval(intervalId);
    };
  }, [loadProjection]);

  const room = useMemo(
    () => buildOperationsRoomModel(projection),
    [projection],
  );
  const roomTasks = useMemo(
    () => decisionLaneOrder.flatMap((lane) => room.decisionLanes[lane]),
    [room],
  );
  const selectedTask = roomTasks.find((task) => task.id === selectedTaskId);
  const selectedAgent =
    room.workstations.find((agent) => agent.id === selectedAgentId) ||
    room.workstations.find((agent) => agent.id === selectedTask?.owner);

  const filteredEvents = useMemo(
    () => filterEvents(projection.events, eventFilter),
    [projection.events, eventFilter],
  );
  const filteredGates = useMemo(
    () => filterGates(projection.gates, gateFilter),
    [projection.gates, gateFilter],
  );
  const handleSelectAgent = useCallback((agentId: string) => {
    setSelectedAgentId(agentId);
    setSelectedTaskId("");
  }, []);
  const handleSelectTask = useCallback((taskId: string) => {
    setSelectedTaskId(taskId);
    setSelectedAgentId("");
  }, []);

  async function approveReplacement(replacement: ReplacementRow) {
    setCommandStatus("正在批准接管...");
    try {
      const response = await fetch("/api/replacement/approve", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          recommendation_id: replacement.id,
          old_agent_id: replacement.targetAgent,
          old_session_id: replacement.targetSession,
          candidate_agent_id: replacement.candidateAgent,
          candidate_session_id: replacement.candidateSession,
          task_id: replacement.taskId,
        }),
      });
      if (!response.ok) {
        throw new Error(`approval returned ${response.status}`);
      }
      setCommandStatus("接管已批准");
      await loadProjection();
    } catch (error) {
      setCommandStatus(
        error instanceof Error ? error.message : "接管审批失败",
      );
    }
  }

  async function submitInterrupt(
    message: string,
    targetAgent: string,
    includeSelectedTask: boolean,
  ) {
    const taskContext = includeSelectedTask ? selectedTask : undefined;
    const taskOwner = taskContext?.owner;
    const explicitTarget = targetAgent || "";
    const taskAssignee = explicitTarget || taskOwner;
    const additionalAgents =
      explicitTarget && explicitTarget !== taskOwner ? [explicitTarget] : [];

    setCommandStatus("正在发送中断...");
    try {
      const response = await fetch("/api/interrupt", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          actor: "operations-console",
          text: message,
          run_id: taskContext?.runId || undefined,
          task_id: taskContext?.id || undefined,
          payload: {
            source: "operations-console",
            routing_mode: taskContext ? "task-context" : "agent-only",
            selected_task_id: selectedTask?.id,
            include_selected_task: Boolean(taskContext),
          },
          target: {
            controller: "controller",
            observer: "observer",
            task_owner: taskOwner,
            task_assignee: taskAssignee,
            helper_agents: [],
            qa_agent: "qa",
            gate_owner: null,
            downstream_task_owners: [],
            additional_agents: additionalAgents,
          },
        }),
      });
      if (!response.ok) {
        throw new Error(`interrupt returned ${response.status}`);
      }
      setCommandStatus("中断已发送");
      await loadProjection();
    } catch (error) {
      setCommandStatus(error instanceof Error ? error.message : "中断发送失败");
    }
  }

  async function submitDrawerAction(payload: ActionDrawerSubmitPayload) {
    const message = payload.message.trim();
    if (!message) {
      return;
    }

    const recipientAgentIds = resolveDrawerRecipients(payload, projection);
    const nextView = viewAfterDrawerSubmit(payload);

    setCommandStatus("正在发送到 Agent Bus...");
    try {
      await sendBusMessage({
        actor: "operator",
        text: message,
        recipient_agent_ids: recipientAgentIds,
        run_id: payload.item.runId,
        task_id: payload.item.taskId,
        gate_id: payload.item.kind === "gate" ? payload.item.id : undefined,
        message_type: payload.action,
        priority:
          payload.action === "reassign" || payload.item.kind === "gate"
            ? "high"
            : "normal",
      });
      setCommandStatus("已发送到 Agent Bus");
      setDrawerItem(null);
      setActiveView(nextView);
      await loadProjection();
    } catch (error) {
      setCommandStatus(error instanceof Error ? error.message : "发送失败");
    }
  }

  return (
    <>
      <main className="opsShell">
        <aside className="sidebar" aria-label="主导航">
        <div className="brand">
          <span className="brandMark">AB</span>
          <div>
            <h1>{uiText.appTitle}</h1>
            <p>{uiText.appSubtitle}</p>
          </div>
        </div>

        <nav className="navList">
          {views.map((view) => {
            const Icon = viewIcons[view];
            return (
              <button
                className={view === activeView ? "navItem active" : "navItem"}
                key={view}
                onClick={() => setActiveView(view)}
                type="button"
              >
                <span className="navIcon">
                  <Icon size={14} strokeWidth={2.2} />
                </span>
                {viewLabels[view]}
              </button>
            );
          })}
        </nav>

        <section className="miniPanel">
          <div className="labelRow">
            <span>当前运行</span>
            <strong>{room.brief.activeRunLabel}</strong>
          </div>
          <div className="labelRow">
            <span>阶段</span>
            <strong>{room.brief.activeRunMeta}</strong>
          </div>
          <div className="labelRow">
            <span>同步</span>
            <strong>{loadStateLabels[loadState]}</strong>
          </div>
        </section>
      </aside>

      <section className="opsMain">
        <div className="appToolbarRow">
          <PageToolbar
            lastLoadedAt={lastLoadedAt}
            onRefresh={() => void loadProjection()}
          />
        </div>
        {loadState === "error" && projection.agents.length === 0 ? (
          <EmptyState
            title="无法加载运行数据"
            detail={loadError || "请检查 /api/projections/operations 服务。"}
          />
        ) : (
          <ConsoleView
            activeView={activeView}
            onOpenAction={setDrawerItem}
            onViewChange={setActiveView}
            projection={projection}
            room={room}
          />
        )}
        </section>
      </main>
      <ActionDrawer
        agents={projection.agents}
        item={drawerItem}
        onClose={() => setDrawerItem(null)}
        onSubmit={(payload) => void submitDrawerAction(payload)}
        status={commandStatus}
      />
    </>
  );
}

function resolveDrawerRecipients(
  payload: ActionDrawerSubmitPayload,
  projection: OperationsProjection,
): string[] {
  if (payload.targetAgentId) {
    return [payload.targetAgentId];
  }

  const itemTaskId = payload.item.taskId || (payload.item.kind === "task" ? payload.item.id : "");
  const task = projection.tasks.find((candidate) => candidate.id === itemTaskId);
  const gate =
    projection.gates.find((candidate) => candidate.id === payload.item.id) ||
    projection.gates.find((candidate) => candidate.taskId === itemTaskId);
  const controllerId =
    findAgentByRole(projection.agents, "controller") ||
    findAgentByRole(projection.agents, "qa") ||
    "runtime-qa";
  const qaId = findAgentByRole(projection.agents, "qa") || gate?.owner || "runtime-qa";

  if (payload.action === "open_gate" || payload.item.kind === "gate") {
    return compactIds([gate?.owner, qaId]);
  }

  if (payload.action === "request_qa") {
    return compactIds([qaId, task?.owner]);
  }

  if (payload.action === "message_controller" || payload.action === "reassign") {
    return compactIds([controllerId, task?.owner]);
  }

  if (payload.item.kind === "task") {
    return compactIds([task?.owner, controllerId]);
  }

  return compactIds([controllerId]);
}

function viewAfterDrawerSubmit(payload: ActionDrawerSubmitPayload): ViewName {
  if (payload.action === "open_gate" || payload.item.kind === "gate") {
    return "Gates";
  }
  if (payload.action === "view_artifact" || payload.item.kind === "artifact") {
    return "Artifacts";
  }
  if (payload.item.kind === "message" || payload.action === "message_controller") {
    return "Communication";
  }
  if (payload.item.kind === "task" || payload.item.runId) {
    return "Runs";
  }
  return "Home";
}

function findAgentByRole(agents: AgentRow[], role: string): string {
  return (
    agents.find((agent) => agent.roles.includes(role))?.id ||
    agents.find((agent) => agent.role === role)?.id ||
    ""
  );
}

function compactIds(ids: Array<string | undefined>): string[] {
  return Array.from(new Set(ids.map((id) => id?.trim() || "").filter(Boolean)));
}

function ConsoleView({
  activeView,
  onOpenAction,
  onViewChange,
  projection,
  room,
}: {
  activeView: ViewName;
  onOpenAction: (item: ActionDrawerItem) => void;
  onViewChange: (view: ViewName) => void;
  projection: OperationsProjection;
  room: OperationsRoomModel;
}) {
  if (activeView === "Home") {
    return (
      <HomePage
        onOpenAction={onOpenAction}
        onViewChange={onViewChange}
        projection={projection}
        room={room}
      />
    );
  }

  if (activeView === "Communication") {
    return <CommunicationPage projection={projection} />;
  }

  if (activeView === "Gates") {
    return <GatesPage projection={projection} />;
  }

  if (activeView === "Runs") {
    return <RunsPage projection={projection} />;
  }

  if (activeView === "Artifacts") {
    return <ArtifactsPage projection={projection} />;
  }

  if (activeView === "Diagnostics") {
    return <DiagnosticsPage projection={projection} />;
  }

  if (activeView === "Settings") {
    return <SettingsPanel projection={projection} />;
  }

  return (
    <HomePage
      onOpenAction={onOpenAction}
      onViewChange={onViewChange}
      projection={projection}
      room={room}
    />
  );
}

function MissionSurface({
  gates,
  tasks,
  onSelectTask,
}: {
  gates: GateRow[];
  tasks: Record<DecisionLane, TaskCardModel[]>;
  onSelectTask: (taskId: string) => void;
}) {
  const focusLanes = focusLaneOrder.filter((lane) =>
    lane === "needsAction" || lane === "active" || tasks[lane].length > 0,
  );
  const secondaryLanes = decisionLaneOrder.filter(
    (lane) => !focusLanes.includes(lane),
  );
  const secondaryLabel = secondaryLanes
    .map((lane) => `${uiText.decisionLanes[lane]} ${tasks[lane].length}`)
    .join(" / ");

  return (
    <section className="panel missionSurface">
      <PanelHeader
        title={uiText.panels.missionSurface}
        meta={`${gates.length} ${uiText.panels.gates}`}
      />
      <div className="laneSummaryStrip" aria-label="Task lane summary">
        {decisionLaneOrder.map((lane) => (
          <div
            className="laneSummary"
            data-empty={tasks[lane].length === 0 ? "true" : "false"}
            data-lane={lane}
            key={lane}
          >
            <span>{uiText.decisionLanes[lane]}</span>
            <strong>{tasks[lane].length}</strong>
            <small>{laneSummaryText(lane, tasks[lane], gates.length)}</small>
          </div>
        ))}
      </div>
      <div className="decisionLanes decisionLanes--focus">
        {focusLanes.map((lane) => (
          <DecisionLaneColumn
            key={lane}
            lane={lane}
            limit={laneCardLimit[lane]}
            onSelectTask={onSelectTask}
            tasks={tasks[lane]}
          />
        ))}
      </div>
      {secondaryLanes.length ? (
        <details className="secondaryLaneShelf">
          <summary>展开其他队列：{secondaryLabel}</summary>
          <div className="secondaryLaneGrid">
            {secondaryLanes.map((lane) => (
              <DecisionLaneColumn
                compact
                key={lane}
                lane={lane}
                limit={laneCardLimit[lane]}
                onSelectTask={onSelectTask}
                tasks={tasks[lane]}
              />
            ))}
          </div>
        </details>
      ) : null}
    </section>
  );
}

function laneSummaryText(
  lane: DecisionLane,
  tasks: TaskCardModel[],
  gateCount: number,
): string {
  if (tasks[0]) return tasks[0].nextAction;
  if (lane === "waitingGate" && gateCount > 0) return `${gateCount} 个待决门禁`;
  if (lane === "done") return "全部完成，等待新的任务";
  return "暂无待处理项";
}

function DecisionLaneColumn({
  compact = false,
  lane,
  limit,
  onSelectTask,
  tasks,
}: {
  compact?: boolean;
  lane: DecisionLane;
  limit?: number;
  onSelectTask: (taskId: string) => void;
  tasks: TaskCardModel[];
}) {
  const contextText = (task: TaskCardModel) => displayOrEmpty(task.contextIntegrity);
  const visibleTasks = typeof limit === "number" ? tasks.slice(0, limit) : tasks;
  const overflowTasks = typeof limit === "number" ? tasks.slice(limit) : [];
  const renderTask = (task: TaskCardModel) => (
    <button
      className="decisionCard"
      data-tone={taskTone(task.state)}
      key={task.id}
      onClick={() => onSelectTask(task.id)}
      type="button"
    >
      <strong>{task.title}</strong>
      <div className="decisionMeta">
        <span>{task.stateText}</span>
        <span>{task.ownerText}</span>
        {task.shortTaskId ? <code>{task.shortTaskId}</code> : null}
      </div>
      {contextText(task) ? <p>上下文：{contextText(task)}</p> : null}
      <Progress label={`进度 ${task.progress}%`} value={task.progress} />
      <p>{task.nextAction}</p>
      <div className="decisionAction">
        <span>{task.shortRunId || "未关联"}</span>
        <StatusPill tone={priorityTone(task.priority)}>
          {task.priority}
        </StatusPill>
      </div>
    </button>
  );

  return (
    <section
      className="decisionLane"
      data-compact={compact ? "true" : "false"}
      data-empty={tasks.length === 0 ? "true" : "false"}
      data-lane={lane}
    >
      <h4>
        {uiText.decisionLanes[lane]}
        <span>{tasks.length}</span>
      </h4>
      {visibleTasks.length ? (
        visibleTasks.map(renderTask)
      ) : (
        <EmptyBlock>暂无任务</EmptyBlock>
      )}
      {overflowTasks.length ? (
        <details className="laneOverflow">
          <summary>另有 {overflowTasks.length} 个任务</summary>
          <div className="laneOverflowList">{overflowTasks.map(renderTask)}</div>
        </details>
      ) : null}
    </section>
  );
}

function SelectionDetailPanel({
  agent,
  task,
}: {
  agent?: WorkstationModel;
  task?: TaskCardModel;
}) {
  const hasSelection = Boolean(agent || task);
  const roleText = agent?.roles.length ? agent.roles.join(" / ") : agent?.role;

  return (
    <section className="panel selectionDetailPanel">
      <PanelHeader title="选择详情" meta={hasSelection ? "运行事实" : "等待选择"} />
      {!hasSelection ? (
        <EmptyBlock>选择 Agent 或任务后查看详情。</EmptyBlock>
      ) : null}
      {hasSelection ? (
        <dl className="detailGrid">
          {task ? (
            <>
              <dt>任务</dt>
              <dd>{task.title}</dd>
              <dt>Owner</dt>
              <dd>{task.ownerText}</dd>
              <dt>Status</dt>
              <dd>{task.stateText}</dd>
              <dt>进度</dt>
              <dd>{task.progress}%</dd>
              <dt>Next action</dt>
              <dd>{task.nextAction}</dd>
              <dt>Run</dt>
              <dd>{task.shortRunId || "未关联"}</dd>
            </>
          ) : null}
          {agent ? (
            <>
              <dt>Agent</dt>
              <dd>{agent.name || agent.id}</dd>
              <dt>角色</dt>
              <dd>{roleText || "未标注"}</dd>
              <dt>Status</dt>
              <dd>{agent.stateText}</dd>
              <dt>会话</dt>
              <dd>{agent.shortSession}</dd>
              <dt>当前工作</dt>
              <dd>{agent.currentWork}</dd>
              <dt>Next action</dt>
              <dd>{agent.nextAction}</dd>
            </>
          ) : null}
        </dl>
      ) : null}
    </section>
  );
}

function SettingsPanel({ projection }: { projection: OperationsProjection }) {
  return (
    <section className="settingsPage pageShell">
      <header className="pageHeader">
        <div>
          <span className="eyebrow">SETTINGS</span>
          <h2>{uiText.panels.settings}</h2>
          <p>查看投影来源、同步节奏和本地控制台偏好。</p>
        </div>
      </header>
      <div className="settingsCards">
        <article className="settingsCard">
          <strong>数据源</strong>
          <span>Endpoint: {projection.source}</span>
          <span>Refresh: 5s</span>
          <span>Last generated: {projection.generatedAt || "等待生成"}</span>
        </article>
        <article className="settingsCard">
          <strong>控制台偏好</strong>
          <span>浅色运行台</span>
          <span>自动同步开启</span>
          <span>操作通过 Agent Bus 发送</span>
        </article>
        <article className="settingsCard">
          <strong>投影统计</strong>
          <span>active run count: {projection.runs.length}</span>
          <span>agent count: {projection.agents.length}</span>
          <span>projection version: live</span>
        </article>
      </div>
    </section>
  );
}

function PanelHeader({ title, meta }: { title: string; meta: string }) {
  return (
    <header className="panelHeader">
      <h3>{title}</h3>
      <span>{meta}</span>
    </header>
  );
}

function Progress({ label, value }: { label: string; value: number }) {
  return (
    <div className="progress">
      <span>{label}</span>
      <div>
        <i style={{ width: `${value}%` }} />
      </div>
    </div>
  );
}

function StatusPill({
  children,
  tone,
}: {
  children: string | number;
  tone: Tone;
}) {
  return <span className={`pill ${tone}`}>{children}</span>;
}

function EmptyState({ detail, title }: { detail: string; title: string }) {
  return (
    <section className="emptyState">
      <h3>{title}</h3>
      <p>{detail}</p>
    </section>
  );
}

function EmptyBlock({ children }: { children: React.ReactNode }) {
  return <p className="emptyBlock">{children}</p>;
}

function filterEvents(events: EventRow[], filter: EventFilter): EventRow[] {
  if (filter === "all") {
    return events;
  }
  return events.filter((event) => {
    const haystack = `${event.type} ${event.text} ${event.tone}`.toLowerCase();
    return filter === "error"
      ? event.tone === "bad"
      : haystack.includes(filter);
  });
}

function filterGates(gates: GateRow[], filter: GateFilter): GateRow[] {
  if (filter === "all") {
    return gates;
  }
  if (filter === "high") {
    return gates.filter(
      (gate) =>
        !taskTone(gate.state).includes("good") &&
        gate.risk.toLowerCase().includes("high"),
    );
  }
  if (filter === "handled") {
    return gates.filter((gate) => taskTone(gate.state).includes("good"));
  }
  return gates.filter((gate) => !taskTone(gate.state).includes("good"));
}

function formatEventTime(value: string): string {
  if (!value) {
    return "--:--:--";
  }
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value.slice(0, 8) : date.toLocaleTimeString();
}

function shortId(value: string): string {
  const display = displayOrEmpty(value);
  if (!display) {
    return "";
  }
  if (display.length <= 16) {
    return display;
  }
  return `${display.slice(0, 12)}...`;
}

function priorityTone(priority: string): Tone {
  const value = priority.toLowerCase();
  if (value.includes("high") || value.includes("critical")) {
    return "bad";
  }
  if (value.includes("normal") || value.includes("medium")) {
    return "warn";
  }
  return "info";
}

function taskTone(state: string): Tone {
  const value = state.toLowerCase();
  if (
    value.includes("fail") ||
    value.includes("block") ||
    value.includes("reject") ||
    value.includes("invalid")
  ) {
    return "bad";
  }
  if (
    value.includes("done") ||
    value.includes("pass") ||
    value.includes("complete") ||
    value.includes("approved")
  ) {
    return "good";
  }
  if (
    value.includes("wait") ||
    value.includes("created") ||
    value.includes("queued")
  ) {
    return "warn";
  }
  return "info";
}

export default App;
