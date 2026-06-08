export type ViewName =
  | "Home"
  | "Communication"
  | "Runs"
  | "Gates"
  | "Artifacts"
  | "Diagnostics"
  | "Settings";

export type Tone = "good" | "warn" | "bad" | "info";

export type AgentRow = {
  id: string;
  name: string;
  role: string;
  roles: string[];
  sessionId: string;
  state: string;
  inboxCount: number;
  capabilities: string[];
};

export type TaskRow = {
  id: string;
  title: string;
  owner: string;
  state: string;
  priority: string;
  contextPacketId: string;
  contextIntegrity: string;
  runId: string;
};

export type GateRow = {
  id: string;
  name: string;
  state: string;
  owner: string;
  risk: string;
  runId: string;
  taskId: string;
  requestedBy: string;
  decisionBy: string;
  reason: string;
};

export type EventRow = {
  id: string;
  time: string;
  source: string;
  type: string;
  text: string;
  tone: Tone;
  affectedAgents: string[];
  runId: string;
  taskId: string;
  projectionEffect: string;
  fencingResult: string;
};

export type ReplacementRow = {
  id: string;
  targetAgent: string;
  targetSession: string;
  candidateAgent: string;
  candidateSession: string;
  taskId: string;
  score: number;
  reason: string;
  state: string;
};

export type ArtifactRow = {
  id: string;
  kind: string;
  owner: string;
  taskId: string;
  runId: string;
  state: string;
  path: string;
  createdAt: string;
  summary: string;
};

export type RunRow = {
  id: string;
  title: string;
  objective: string;
  state: string;
  owner: string;
  startedAt: string;
};

export type BusMessageRow = {
  messageId: string;
  busEventId: string;
  threadId: string;
  spaceId: string;
  senderAgentId: string;
  senderName: string;
  senderRoles: string[];
  recipientAgentIds: string[];
  messageType: string;
  deliveryState: string;
  ackState: string;
  replyState: string;
  priority: string;
  body: string;
  links: {
    runId?: string;
    taskIds: string[];
    gateIds: string[];
    artifactIds: string[];
  };
  createdAt: string;
  updatedAt: string;
};

export type SendBusMessageRequest = {
  actor?: string;
  text: string;
  recipient_agent_ids: string[];
  run_id?: string;
  task_id?: string;
  gate_id?: string;
  message_type?: string;
  priority?: string;
};

export type SendBusMessageResult = {
  ok: boolean;
  event: unknown;
  affectedAgents: string[];
};

export type ArtifactManifestRow = {
  artifactId: string;
  runId: string;
  taskId: string;
  agentId: string;
  type: string;
  title: string;
  path: string;
  createdAt: string;
  summary: string;
  sizeBytes: number | null;
  contentType: string;
  previewUrl: string;
  downloadUrl: string;
};

export type UiTone = Tone | "neutral";

export type RuntimeCondition = {
  type: string;
  status: "true" | "false" | "unknown" | string;
  reason: string;
  message: string | null;
  severity: "info" | "warning" | "error" | "critical" | string;
  source: string;
  lastTransitionAt: string;
  observedGeneration: number | null;
};

export type RuntimePresenceState = "online" | "stale" | "offline" | "unknown" | string;

export type RuntimeWorkloadState =
  | "free"
  | "assigned"
  | "working"
  | "waiting_input"
  | "claim_pending"
  | "waiting_review"
  | "waiting_gate"
  | "blocked"
  | "historical"
  | string;

export type RuntimeUiVisibilityState =
  | "main"
  | "secondary"
  | "needs_attention"
  | "approval_center"
  | "diagnostics"
  | "history"
  | "hidden"
  | string;

export type UiActiveRunProjection = {
  runId: string;
  title: string;
  objective: string;
  state: string;
  createdAt: string;
  updatedAt: string;
  progress: Record<string, number>;
};

export type UiMetroNode = {
  id: string;
  kind: "start" | "task" | "context" | "claim" | "gate" | "artifact" | "replacement" | "terminal" | string;
  title: string;
  subtitle: string;
  state: string;
  tone: UiTone;
  runId: string;
  taskId: string;
  gateId: string;
  artifactId: string;
  contextPacketId: string;
  claimId: string;
  recommendationId: string;
  agentId: string;
  route: ViewName;
  priority: number;
};

export type UiMetroEdge = {
  id: string;
  source: string;
  target: string;
  kind: "main" | "context" | "claim" | "gate" | "artifact" | "replacement" | "terminal" | string;
  tone: UiTone;
  taskId: string;
};

export type UiWorkflowDiagnostic = {
  kind: string;
  title: string;
  detail: string;
  tone: UiTone;
  eventId: string;
  runId: string;
  taskId: string;
};

export type UiMetroProjection = {
  nodes: UiMetroNode[];
  edges: UiMetroEdge[];
  mainPathNodeIds: string[];
  currentNodeId: string;
  branchGroups: Record<string, string[]>;
  taskIds: string[];
  diagnostics: UiWorkflowDiagnostic[];
};

export type UiTaskWorkflowProjection = UiMetroProjection;

export type UiDiagnosticRecord = {
  kind: string;
  title: string;
  detail: string;
  tone: UiTone;
  effect: string;
  fencingResult: string;
  eventId: string;
  attemptedEventId: string;
  runId: string;
  taskId: string;
  createdAt: string;
};

export type UiDiagnosticsProjection = {
  projectionEffects: UiDiagnosticRecord[];
  fencingRejects: UiDiagnosticRecord[];
  protocolViolations: UiDiagnosticRecord[];
  deprecatedAdapterEvents: UiDiagnosticRecord[];
};

export type UiActionItem = {
  id: string;
  kind: string;
  title: string;
  description: string;
  tone: UiTone;
  route: ViewName;
  priority: number;
  runId: string;
  taskId: string;
  gateId: string;
  artifactId: string;
  agentId: string;
  createdAt: string;
  suggestedActions: string[];
};

export type UiAgentSummary = {
  agentId: string;
  displayName: string;
  role: string;
  runtimeState: string;
  identityLifecycle: string;
  presenceState: RuntimePresenceState;
  workloadState: RuntimeWorkloadState;
  uiVisibilityState: RuntimeUiVisibilityState;
  conditions: RuntimeCondition[];
  hiddenReason: string;
  tone: UiTone;
  healthScore: number | null;
  stale: boolean;
  currentTaskId: string;
  currentTaskTitle: string;
  openGateId: string;
  queuedInbox: number;
  nextAction: string;
};

export type UiGateDecision = {
  gateId: string;
  name: string;
  state: string;
  risk: string;
  tone: UiTone;
  runId: string;
  taskId: string;
  ownerAgentId: string;
  requestedBy: string;
  reason: string;
  priority: number;
  relevanceState: string;
  uiVisibilityState: RuntimeUiVisibilityState;
  relevanceReason: string;
};

export type UiArtifactSummary = {
  total: number;
  byKind: Record<string, number>;
  latestArtifactId: string;
  latestTitle: string;
  latestUri: string;
  latestCreatedAt: string;
};

export type UiHiddenCounts = {
  archivedAgents: number;
  staleSessions: number;
  historicalGates: number;
  supersededGates: number;
  hiddenContextPackets: number;
  collapsedReplacementEvents: number;
  unboundArtifacts: number;
};

export type UiOperationsProjection = {
  activeRun: UiActiveRunProjection;
  taskWorkflows: Record<string, UiTaskWorkflowProjection>;
  selectedTaskId: string;
  selectedTaskWorkflow: UiTaskWorkflowProjection;
  taskWorkflow: UiTaskWorkflowProjection;
  metro: UiTaskWorkflowProjection;
  actionItems: UiActionItem[];
  agentSummaries: UiAgentSummary[];
  visibleAgents: UiAgentSummary[];
  archivedAgents: UiAgentSummary[];
  gateDecisions: UiGateDecision[];
  actionableGates: UiGateDecision[];
  historicalGates: UiGateDecision[];
  artifactSummary: UiArtifactSummary;
  currentTaskArtifacts: string[];
  runArtifacts: string[];
  legacyUnboundArtifacts: string[];
  hiddenCounts: UiHiddenCounts;
  diagnostics: UiDiagnosticsProjection;
};

export type OperationsMetrics = {
  agentCount: number;
  pendingInbox: number;
  openGateCount: number;
  contextFaults: number;
  artifactCount: number;
};

export type OperationsProjection = {
  generatedAt: string;
  source: string;
  agents: AgentRow[];
  tasks: TaskRow[];
  gates: GateRow[];
  events: EventRow[];
  replacements: ReplacementRow[];
  artifacts: ArtifactRow[];
  runs: RunRow[];
  interruptAffectedAgents: string[];
  metrics: OperationsMetrics;
  ui: UiOperationsProjection;
};

type UnknownRecord = Record<string, unknown>;

export function emptyOperationsProjection(): OperationsProjection {
  return {
    generatedAt: "",
    source: "/api/projections/operations",
    agents: [],
    tasks: [],
    gates: [],
    events: [],
    replacements: [],
    artifacts: [],
    runs: [],
    interruptAffectedAgents: [],
    metrics: {
      agentCount: 0,
      pendingInbox: 0,
      openGateCount: 0,
      contextFaults: 0,
      artifactCount: 0,
    },
    ui: emptyUiProjection(),
  };
}

export function emptyUiProjection(): UiOperationsProjection {
  const emptyWorkflow = emptyUiTaskWorkflow();
  return {
    activeRun: {
      runId: "",
      title: "",
      objective: "",
      state: "none",
      createdAt: "",
      updatedAt: "",
      progress: {},
    },
    taskWorkflows: {},
    selectedTaskId: "",
    selectedTaskWorkflow: emptyUiTaskWorkflow(),
    taskWorkflow: emptyWorkflow,
    metro: emptyUiTaskWorkflow(),
    actionItems: [],
    agentSummaries: [],
    visibleAgents: [],
    archivedAgents: [],
    gateDecisions: [],
    actionableGates: [],
    historicalGates: [],
    artifactSummary: {
      total: 0,
      byKind: {},
      latestArtifactId: "",
      latestTitle: "",
      latestUri: "",
      latestCreatedAt: "",
    },
    currentTaskArtifacts: [],
    runArtifacts: [],
    legacyUnboundArtifacts: [],
    hiddenCounts: {
      archivedAgents: 0,
      staleSessions: 0,
      historicalGates: 0,
      supersededGates: 0,
      hiddenContextPackets: 0,
      collapsedReplacementEvents: 0,
      unboundArtifacts: 0,
    },
    diagnostics: {
      projectionEffects: [],
      fencingRejects: [],
      protocolViolations: [],
      deprecatedAdapterEvents: [],
    },
  };
}

function emptyUiTaskWorkflow(): UiTaskWorkflowProjection {
  return {
    nodes: [],
    edges: [],
    mainPathNodeIds: [],
    currentNodeId: "",
    branchGroups: {},
    taskIds: [],
    diagnostics: [],
  };
}

export async function fetchOperationsProjection(
  signal?: AbortSignal,
): Promise<OperationsProjection> {
  const response = await fetch("/api/projections/operations", {
    headers: { Accept: "application/json" },
    signal,
  });

  if (!response.ok) {
    throw new Error(
      `GET /api/projections/operations returned ${response.status}`,
    );
  }

  return normalizeOperationsProjection(await response.json());
}

export async function fetchBusMessages(signal?: AbortSignal): Promise<BusMessageRow[]> {
  const response = await fetch("/api/projections/messages", {
    headers: { Accept: "application/json" },
    signal,
  });

  if (!response.ok) {
    throw new Error(`GET /api/projections/messages returned ${response.status}`);
  }

  const root = unwrapPayload(await response.json());
  return toArray(root.messages).map(normalizeBusMessage);
}

export async function sendBusMessage(
  payload: SendBusMessageRequest,
): Promise<SendBusMessageResult> {
  const response = await fetch("/api/messages/send", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });

  if (!response.ok) {
    throw new Error(`POST /api/messages/send returned ${response.status}`);
  }

  const root = unwrapPayload(await response.json());
  return {
    ok: root.ok !== false,
    event: root.event,
    affectedAgents: toStringArray(firstValue(root, ["affected_agents", "affectedAgents"])),
  };
}

export async function fetchArtifactManifests(
  signal?: AbortSignal,
): Promise<ArtifactManifestRow[]> {
  const response = await fetch("/api/artifacts/manifests", {
    headers: { Accept: "application/json" },
    signal,
  });

  if (!response.ok) {
    throw new Error(`GET /api/artifacts/manifests returned ${response.status}`);
  }

  const root = unwrapPayload(await response.json());
  return toArray(root.artifacts).map(normalizeArtifactManifest);
}

export function normalizeOperationsProjection(
  payload: unknown,
): OperationsProjection {
  const root = unwrapPayload(payload);
  const sessions = toArray(root.sessions);
  const sessionByAgent = new Map<string, UnknownRecord>();
  sessions.forEach((session) => {
    const agentId = pickString(session, [
      "agent_id",
      "agentId",
      "identity_id",
      "identityId",
      "owner",
    ]);
    if (agentId && !sessionByAgent.has(agentId)) {
      sessionByAgent.set(agentId, session);
    }
  });

  const agents = toArray(root.agents).map((agent) =>
    normalizeAgent(agent, sessionByAgent),
  );
  const contextByTask = new Map<string, UnknownRecord>();
  toArray(root.contexts).forEach((context) => {
    const taskId = pickString(context, ["task_id", "taskId"]);
    if (taskId && !contextByTask.has(taskId)) {
      contextByTask.set(taskId, context);
    }
  });
  const tasks = toArray(root.tasks).map((task) =>
    normalizeTask(task, contextByTask),
  );
  const gates = toArray(root.gates).map(normalizeGate);
  const events = collectEvents(root).map(normalizeEvent);
  const replacements = collectReplacements(root).map(normalizeReplacement);
  const artifacts = toArray(root.artifacts).map(normalizeArtifact);
  const runs = toArray(root.runs).map(normalizeRun);
  const interruptAffectedAgents = collectInterruptAffectedAgents(root, events);
  const ui = normalizeUiProjection(firstRecord(root.ui), { agents, artifacts, gates });

  return {
    generatedAt:
      pickString(root, ["generated_at", "generatedAt", "updated_at"]) ||
      new Date().toISOString(),
    source:
      pickString(root, ["source", "projection", "endpoint"]) ||
      "/api/projections/operations",
    agents,
    tasks,
    gates,
    events,
    replacements,
    artifacts,
    runs,
    interruptAffectedAgents,
    metrics: normalizeMetrics(root, agents, gates, tasks),
    ui,
  };
}

function unwrapPayload(payload: unknown): UnknownRecord {
  if (!isRecord(payload)) {
    return {};
  }
  const data = payload.data;
  const projection = payload.projection;
  if (isRecord(data)) {
    return data;
  }
  if (isRecord(projection)) {
    return projection;
  }
  return payload;
}

function normalizeAgent(
  agent: UnknownRecord,
  sessionByAgent: Map<string, UnknownRecord>,
): AgentRow {
  const identity = firstRecord(agent.identity);
  const activeSession = firstRecord(agent.active_session, agent.activeSession);
  const id =
    pickString(agent, ["id", "agent_id", "agentId", "identity_id"]) ||
    pickString(identity, ["id", "agent_id", "agentId", "identity_id"]);
  const session = id ? sessionByAgent.get(id) : undefined;
  const sessionRecord = firstRecord(agent.session, activeSession, session);
  const inboxCounts = firstRecord(agent.inbox_counts, agent.inboxCounts);
  const capabilities = collectCapabilities(agent);
  const displayName =
    pickString(agent, ["name", "display_name", "displayName"]) ||
    pickString(identity, ["display_name", "displayName"]) ||
    id ||
    "unknown-agent";
  const roleValue =
    pickString(agent, ["role", "agent_role", "kind", "label"]) ||
    pickString(identity, ["role"]) ||
    "unassigned";
  const roles = normalizeRoles(
    firstValue(agent, ["roles", "role_list", "roleList"]) || roleValue,
  );

  return {
    id: id || "unknown-agent",
    name: displayName,
    role: roleValue,
    roles,
    sessionId:
      pickString(agent, [
        "session_id",
        "sessionId",
        "active_session_id",
        "activeSessionId",
      ]) ||
      pickString(sessionRecord, ["id", "session_id", "sessionId"]) ||
      "no-session",
    state:
      pickString(agent, ["state", "runtime_state", "runtimeState", "status"]) ||
      pickString(sessionRecord, ["state", "runtime_state", "status"]) ||
      "unknown",
    inboxCount: Math.max(
      0,
      Math.round(
        pickNumber(agent, [
          "inbox",
          "inbox_count",
          "inboxCount",
        "pending_inbox",
        "pendingInbox",
      ]) ??
        sumRecordNumbers(inboxCounts) ??
        0,
      ),
    ),
    capabilities,
  };
}

function normalizeTask(
  task: UnknownRecord,
  contextByTask: Map<string, UnknownRecord>,
): TaskRow {
  const id = pickString(task, ["id", "task_id", "taskId"]) || "unknown-task";
  const context = contextByTask.get(id) || {};
  return {
    id,
    title:
      pickString(task, ["title", "name", "summary", "description"]) ||
      pickString(task, ["id", "task_id", "taskId"]) ||
      "Untitled task",
    owner:
      pickString(task, [
        "owner",
        "agent_id",
        "agentId",
        "assignee",
        "assignee_agent_id",
        "assigneeAgentId",
        "owner_agent_id",
        "ownerAgentId",
        "assigned_agent",
        "assignedAgent",
      ]) || "unassigned",
    state: pickString(task, ["state", "status"]) || "unknown",
    priority: pickString(task, ["priority", "risk"]) || "normal",
    contextPacketId:
      pickString(task, [
        "context_packet_id",
        "contextPacketId",
        "context_id",
        "contextId",
        "context",
      ]) ||
      pickString(context, ["packet_id", "packetId"]) ||
      "none",
    contextIntegrity: normalizeIntegrity(
      pickString(task, [
        "context_integrity",
        "contextIntegrity",
        "context_status",
        "contextStatus",
      ]),
      pickBoolean(task, ["context_valid", "contextValid"]) ??
        (pickString(context, ["status"]) === "active" ? true : undefined),
    ),
    runId: pickString(task, ["run_id", "runId"]) || "no-run",
  };
}

function normalizeGate(gate: UnknownRecord): GateRow {
  return {
    id: pickString(gate, ["id", "gate_id", "gateId"]) || "unknown-gate",
    name:
      pickString(gate, ["name", "title", "label"]) ||
      pickString(gate, ["id", "gate_id", "gateId"]) ||
      "Unnamed gate",
    state: pickString(gate, ["state", "status", "decision"]) || "unknown",
    owner:
      pickString(gate, [
        "owner",
        "owner_agent_id",
        "ownerAgentId",
        "reviewer",
        "approver",
        "agent_id",
      ]) ||
      "unassigned",
    risk:
      pickString(gate, ["risk", "risk_level", "riskLevel", "severity"]) ||
      "normal",
    runId: pickString(gate, ["run_id", "runId"]) || "",
    taskId: pickString(gate, ["task_id", "taskId"]) || "",
    requestedBy:
      pickString(gate, ["requested_by", "requestedBy", "requester"]) || "",
    decisionBy:
      pickString(gate, ["decision_by", "decisionBy", "decision_maker"]) || "",
    reason: pickString(gate, ["reason", "summary", "description"]) || "",
  };
}

function normalizeEvent(event: UnknownRecord): EventRow {
  const payload = firstRecord(event.payload);
  const type = pickString(event, ["type", "event_type", "eventType"]) || "event";
  const text =
    pickString(event, ["text", "message", "summary", "detail", "description"]) ||
    pickString(payload, ["text", "message", "summary", "detail", "description"]) ||
    type;
  return {
    id:
      pickString(event, ["id", "event_id", "eventId", "seq"]) ||
      `${pickString(event, ["ts", "timestamp", "created_at"]) || "event"}-${text}`,
    time:
      pickString(event, [
        "time",
        "ts",
        "timestamp",
        "created_at",
        "occurred_at",
      ]) || "",
    source:
      pickString(event, ["source", "actor", "from", "agent_id", "agentId"]) ||
      "runtime",
    type,
    text,
    tone: deriveTone(
      type,
      text,
      pickString(event, ["state", "status"]) ||
        pickString(event, ["projection_effect", "projectionEffect"]) ||
        pickString(event, ["fencing_result", "fencingResult"]),
    ),
    affectedAgents: toStringArray(
      firstValue(event, [
        "affected_agents",
        "affectedAgents",
        "targets",
        "target_agents",
      ]) ||
        firstValue(payload, [
          "affected_agents",
          "affectedAgents",
          "targets",
          "target_agents",
        ]),
    ),
    runId:
      pickString(event, ["run_id", "runId"]) ||
      pickString(payload, ["run_id", "runId"]) ||
      "",
    taskId:
      pickString(event, ["task_id", "taskId"]) ||
      pickString(payload, ["task_id", "taskId"]) ||
      "",
    projectionEffect:
      pickString(event, ["projection_effect", "projectionEffect"]) ||
      pickString(payload, ["projection_effect", "projectionEffect"]) ||
      "",
    fencingResult:
      pickString(event, ["fencing_result", "fencingResult"]) ||
      pickString(payload, ["fencing_result", "fencingResult"]) ||
      "",
  };
}

function normalizeReplacement(replacement: UnknownRecord): ReplacementRow {
  const candidate = firstRecord(replacement.candidate);
  return {
    id:
      pickString(replacement, [
        "id",
        "recommendation_id",
        "recommendationId",
        "replacement_id",
      ]) || "replacement-recommendation",
    targetAgent:
      pickString(replacement, [
        "target_agent",
        "targetAgent",
        "agent_id",
        "agentId",
        "old_agent_id",
      ]) || "unknown-agent",
    targetSession:
      pickString(replacement, [
        "target_session",
        "targetSession",
        "old_session_id",
        "oldSessionId",
        "session_id",
      ]) || "unknown-session",
    candidateAgent:
      pickString(replacement, [
        "candidate_agent",
        "candidateAgent",
        "replacement_agent",
        "replacementAgent",
        "replacement_agent_id",
      ]) ||
      pickString(candidate, ["agent_id", "agentId"]) ||
      "no-candidate",
    candidateSession:
      pickString(replacement, [
        "candidate_session",
        "candidateSession",
        "replacement_session",
        "replacementSession",
        "replacement_session_id",
      ]) ||
      pickString(candidate, ["session_id", "sessionId"]) ||
      "no-session",
    taskId:
      pickString(replacement, ["task_id", "taskId", "task"]) || "same-task",
    score: asPercent(
      pickNumber(replacement, ["score", "candidate_score"]) ??
        pickNumber(candidate, ["score"]) ??
        0,
    ),
    reason:
      pickString(replacement, ["reason", "trigger", "summary"]) ||
      toStringArray(replacement.reasons).join(", ") ||
      "replacement recommended",
    state: pickString(replacement, ["state", "status"]) || "recommended",
  };
}

function normalizeArtifact(artifact: UnknownRecord): ArtifactRow {
  return {
    id:
      pickString(artifact, ["id", "artifact_id", "artifactId"]) ||
      "unknown-artifact",
    kind: pickString(artifact, ["kind", "type", "artifact_type"]) || "artifact",
    owner:
      pickString(artifact, ["owner", "agent_id", "agentId", "created_by"]) ||
      "unassigned",
    taskId: pickString(artifact, ["task_id", "taskId"]) || "no-task",
    runId: pickString(artifact, ["run_id", "runId"]) || "no-run",
    state: pickString(artifact, ["state", "status"]) || "available",
    path: pickString(artifact, ["path", "uri", "url"]) || "",
    createdAt: pickString(artifact, ["created_at", "createdAt"]) || "",
    summary: pickString(firstRecord(artifact.metadata), ["summary", "description"]) || "",
  };
}

function normalizeRun(run: UnknownRecord): RunRow {
  return {
    id: pickString(run, ["id", "run_id", "runId"]) || "unknown-run",
    title:
      pickString(run, ["title", "name"]) ||
      pickString(run, ["id", "run_id", "runId"]) ||
      "unknown-run",
    objective: pickString(run, ["objective", "summary", "description"]) || "",
    state: pickString(run, ["state", "status"]) || "unknown",
    owner:
      pickString(run, ["owner", "controller", "created_by", "createdBy"]) ||
      "controller",
    startedAt:
      pickString(run, ["started_at", "startedAt", "created_at", "createdAt"]) ||
      "",
  };
}

function normalizeBusMessage(message: UnknownRecord): BusMessageRow {
  const links = firstRecord(message.links);
  return {
    messageId:
      pickString(message, ["message_id", "messageId", "id"]) ||
      "unknown-message",
    busEventId:
      pickString(message, ["bus_event_id", "busEventId", "event_id", "eventId"]) ||
      "",
    threadId: pickString(message, ["thread_id", "threadId"]) || "",
    spaceId: pickString(message, ["space_id", "spaceId"]) || "runtime",
    senderAgentId:
      pickString(message, ["sender_agent_id", "senderAgentId", "actor"]) || "",
    senderName:
      pickString(message, ["sender_name", "senderName", "actor"]) ||
      "system",
    senderRoles: toStringArray(firstValue(message, ["sender_roles", "senderRoles"])),
    recipientAgentIds: toStringArray(
      firstValue(message, ["recipient_agent_ids", "recipientAgentIds"]),
    ),
    messageType:
      pickString(message, ["message_type", "messageType", "type"]) ||
      "message",
    deliveryState:
      pickString(message, ["delivery_state", "deliveryState"]) || "sent",
    ackState: pickString(message, ["ack_state", "ackState"]) || "not_required",
    replyState:
      pickString(message, ["reply_state", "replyState"]) || "not_required",
    priority: pickString(message, ["priority"]) || "normal",
    body: pickString(message, ["body", "text", "message"]) || "",
    links: {
      runId: pickString(links, ["run_id", "runId"]) || undefined,
      taskIds: toStringArray(firstValue(links, ["task_ids", "taskIds"])),
      gateIds: toStringArray(firstValue(links, ["gate_ids", "gateIds"])),
      artifactIds: toStringArray(firstValue(links, ["artifact_ids", "artifactIds"])),
    },
    createdAt:
      pickString(message, ["created_at", "createdAt", "ts", "time"]) || "",
    updatedAt:
      pickString(message, ["updated_at", "updatedAt", "created_at", "createdAt"]) ||
      "",
  };
}

function normalizeArtifactManifest(artifact: UnknownRecord): ArtifactManifestRow {
  return {
    artifactId:
      pickString(artifact, ["artifact_id", "artifactId", "id"]) ||
      "unknown-artifact",
    runId: pickString(artifact, ["run_id", "runId"]) || "",
    taskId: pickString(artifact, ["task_id", "taskId"]) || "",
    agentId: pickString(artifact, ["agent_id", "agentId", "created_by"]) || "",
    type: pickString(artifact, ["type", "kind"]) || "artifact",
    title:
      pickString(artifact, ["title", "name"]) ||
      pickString(artifact, ["artifact_id", "artifactId"]) ||
      "artifact",
    path: pickString(artifact, ["path", "uri", "url"]) || "",
    createdAt: pickString(artifact, ["created_at", "createdAt"]) || "",
    summary: pickString(artifact, ["summary", "description"]) || "",
    sizeBytes:
      pickNumber(artifact, ["size_bytes", "sizeBytes", "size"]) ?? null,
    contentType:
      pickString(artifact, ["content_type", "contentType", "mime_type"]) || "",
    previewUrl:
      pickString(artifact, ["preview_url", "previewUrl"]) ||
      pickString(artifact, ["path"]) ||
      "",
    downloadUrl:
      pickString(artifact, ["download_url", "downloadUrl"]) ||
      pickString(artifact, ["preview_url", "previewUrl"]) ||
      "",
  };
}

function normalizeUiProjection(
  ui: UnknownRecord,
  fallbacks: {
    agents?: AgentRow[];
    artifacts?: ArtifactRow[];
    gates?: GateRow[];
  } = {},
): UiOperationsProjection {
  if (!Object.keys(ui).length) {
    return emptyUiProjection();
  }
  const selectedTaskWorkflow = normalizeUiTaskWorkflow(
    firstRecord(
      ui.selected_task_workflow,
      ui.selectedTaskWorkflow,
      ui.task_workflow,
      ui.taskWorkflow,
      ui.metro,
    ),
  );
  const selectedTaskId =
    pickString(ui, ["selected_task_id", "selectedTaskId"]) ||
    selectedTaskWorkflow.taskIds[0] ||
    "";
  const taskWorkflow = normalizeUiTaskWorkflow(
    firstRecord(ui.task_workflow, ui.taskWorkflow, ui.selected_task_workflow, ui.selectedTaskWorkflow, ui.metro),
  );
  const taskWorkflows = normalizeUiTaskWorkflowMap(
    firstValue(ui, ["task_workflows", "taskWorkflows"]),
    selectedTaskId,
    selectedTaskWorkflow,
  );
  const agentSummaries = toArray(
    firstValue(ui, ["agent_summaries", "agentSummaries"]),
  ).map(normalizeUiAgentSummary);
  const fallbackAgentSummaries = (fallbacks.agents || []).map(agentRowToUiAgentSummary);
  const gateDecisions = toArray(
    firstValue(ui, ["gate_decisions", "gateDecisions"]),
  ).map(normalizeUiGateDecision);
  const fallbackGateDecisions = (fallbacks.gates || []).map(gateRowToUiGateDecision);
  const allGateDecisions = gateDecisions.length ? gateDecisions : fallbackGateDecisions;
  return {
    activeRun: normalizeUiActiveRun(firstRecord(ui.active_run, ui.activeRun)),
    taskWorkflows,
    selectedTaskId,
    selectedTaskWorkflow,
    taskWorkflow,
    metro: normalizeUiTaskWorkflow(firstRecord(ui.metro, ui.task_workflow, ui.taskWorkflow)),
    actionItems: toArray(firstValue(ui, ["action_items", "actionItems"])).map(
      normalizeUiActionItem,
    ),
    agentSummaries,
    visibleAgents: normalizeUiAgentSummaryList(
      firstValue(ui, ["visible_agents", "visibleAgents"]),
      agentSummaries.length ? agentSummaries : fallbackAgentSummaries,
    ),
    archivedAgents: normalizeUiAgentSummaryList(
      firstValue(ui, ["archived_agents", "archivedAgents"]),
    ),
    gateDecisions,
    actionableGates: normalizeUiGateDecisionList(
      firstValue(ui, ["actionable_gates", "actionableGates"]),
      allGateDecisions.filter((gate) => ["open", "escalated"].includes(gate.state.toLowerCase())),
    ),
    historicalGates: normalizeUiGateDecisionList(
      firstValue(ui, ["historical_gates", "historicalGates"]),
      allGateDecisions.filter((gate) => !["open", "escalated"].includes(gate.state.toLowerCase())),
    ),
    artifactSummary: normalizeUiArtifactSummary(
      firstRecord(ui.artifact_summary, ui.artifactSummary),
    ),
    currentTaskArtifacts: normalizeStringList(
      firstValue(ui, ["current_task_artifacts", "currentTaskArtifacts"]),
      (fallbacks.artifacts || [])
        .filter((artifact) => artifact.taskId && artifact.taskId !== "no-task")
        .map((artifact) => artifact.id),
    ),
    runArtifacts: normalizeStringList(
      firstValue(ui, ["run_artifacts", "runArtifacts"]),
      (fallbacks.artifacts || [])
        .filter((artifact) => artifact.runId && artifact.runId !== "no-run")
        .map((artifact) => artifact.id),
    ),
    legacyUnboundArtifacts: normalizeStringList(
      firstValue(ui, ["legacy_unbound_artifacts", "legacyUnboundArtifacts"]),
      (fallbacks.artifacts || [])
        .filter(
          (artifact) =>
            (!artifact.taskId || artifact.taskId === "no-task") &&
            (!artifact.runId || artifact.runId === "no-run"),
        )
        .map((artifact) => artifact.id),
    ),
    hiddenCounts: normalizeUiHiddenCounts(
      firstRecord(ui.hidden_counts, ui.hiddenCounts),
    ),
    diagnostics: normalizeUiDiagnostics(
      firstRecord(ui.diagnostics, ui.diagnostic_summary, ui.diagnosticSummary),
    ),
  };
}

function normalizeUiActiveRun(run: UnknownRecord): UiActiveRunProjection {
  return {
    runId: pickString(run, ["run_id", "runId"]) || "",
    title: pickString(run, ["title"]) || "",
    objective: pickString(run, ["objective"]) || "",
    state: pickString(run, ["state", "status"]) || "none",
    createdAt: pickString(run, ["created_at", "createdAt"]) || "",
    updatedAt: pickString(run, ["updated_at", "updatedAt"]) || "",
    progress: normalizeNumberRecord(firstRecord(run.progress)),
  };
}

function normalizeUiMetro(metro: UnknownRecord): UiMetroProjection {
  return normalizeUiTaskWorkflow(metro);
}

function normalizeUiTaskWorkflowMap(
  value: unknown,
  selectedTaskId: string,
  selectedWorkflow: UiTaskWorkflowProjection,
): Record<string, UiTaskWorkflowProjection> {
  const workflows: Record<string, UiTaskWorkflowProjection> = {};
  if (isRecord(value)) {
    Object.entries(value).forEach(([taskId, workflow]) => {
      workflows[taskId] = normalizeUiTaskWorkflow(firstRecord(workflow));
    });
  }
  if (selectedTaskId && !workflows[selectedTaskId]) {
    workflows[selectedTaskId] = selectedWorkflow;
  }
  return workflows;
}

function normalizeUiTaskWorkflow(metro: UnknownRecord): UiTaskWorkflowProjection {
  const branchRecord = firstRecord(
    firstValue(metro, ["branch_groups", "branchGroups"]),
  );
  return {
    nodes: toArray(metro.nodes).map(normalizeUiMetroNode),
    edges: toArray(metro.edges).map(normalizeUiMetroEdge),
    mainPathNodeIds: toStringArray(
      firstValue(metro, ["main_path_node_ids", "mainPathNodeIds"]),
    ),
    currentNodeId:
      pickString(metro, ["current_node_id", "currentNodeId"]) || "",
    branchGroups: Object.fromEntries(
      Object.entries(branchRecord).map(([key, value]) => [
        key,
        toStringArray(value),
      ]),
    ),
    taskIds: toStringArray(firstValue(metro, ["task_ids", "taskIds"])),
    diagnostics: toArray(metro.diagnostics).map(normalizeUiWorkflowDiagnostic),
  };
}

function normalizeUiMetroNode(node: UnknownRecord): UiMetroNode {
  return {
    id: pickString(node, ["id"]) || "unknown-node",
    kind: pickString(node, ["kind"]) || "task",
    title: pickString(node, ["title"]) || "Untitled",
    subtitle: pickString(node, ["subtitle"]) || "",
    state: pickString(node, ["state", "status"]) || "",
    tone: normalizeUiTone(pickString(node, ["tone"])),
    runId: pickString(node, ["run_id", "runId"]) || "",
    taskId: pickString(node, ["task_id", "taskId"]) || "",
    gateId: pickString(node, ["gate_id", "gateId"]) || "",
    artifactId: pickString(node, ["artifact_id", "artifactId"]) || "",
    contextPacketId:
      pickString(node, ["context_packet_id", "contextPacketId"]) || "",
    claimId: pickString(node, ["claim_id", "claimId"]) || "",
    recommendationId:
      pickString(node, ["recommendation_id", "recommendationId"]) || "",
    agentId: pickString(node, ["agent_id", "agentId"]) || "",
    route: normalizeViewName(pickString(node, ["route"])),
    priority: Math.round(pickNumber(node, ["priority"]) ?? 0),
  };
}

function normalizeUiMetroEdge(edge: UnknownRecord): UiMetroEdge {
  return {
    id: pickString(edge, ["id"]) || `${pickString(edge, ["source"]) || ""}->${pickString(edge, ["target"]) || ""}`,
    source: pickString(edge, ["source"]) || "",
    target: pickString(edge, ["target"]) || "",
    kind: pickString(edge, ["kind"]) || "main",
    tone: normalizeUiTone(pickString(edge, ["tone"])),
    taskId: pickString(edge, ["task_id", "taskId"]) || "",
  };
}

function normalizeUiWorkflowDiagnostic(item: UnknownRecord): UiWorkflowDiagnostic {
  return {
    kind: pickString(item, ["kind"]) || "diagnostic",
    title: pickString(item, ["title"]) || "诊断",
    detail: pickString(item, ["detail", "reason"]) || "",
    tone: normalizeUiTone(pickString(item, ["tone"])),
    eventId: pickString(item, ["event_id", "eventId"]) || "",
    runId: pickString(item, ["run_id", "runId"]) || "",
    taskId: pickString(item, ["task_id", "taskId"]) || "",
  };
}

function normalizeUiDiagnostics(diagnostics: UnknownRecord): UiDiagnosticsProjection {
  return {
    projectionEffects: toArray(
      firstValue(diagnostics, ["projection_effects", "projectionEffects"]),
    ).map(normalizeUiDiagnosticRecord),
    fencingRejects: toArray(
      firstValue(diagnostics, ["fencing_rejects", "fencingRejects"]),
    ).map(normalizeUiDiagnosticRecord),
    protocolViolations: toArray(
      firstValue(diagnostics, ["protocol_violations", "protocolViolations"]),
    ).map(normalizeUiDiagnosticRecord),
    deprecatedAdapterEvents: toArray(
      firstValue(diagnostics, [
        "deprecated_adapter_events",
        "deprecatedAdapterEvents",
      ]),
    ).map(normalizeUiDiagnosticRecord),
  };
}

function normalizeUiDiagnosticRecord(item: UnknownRecord): UiDiagnosticRecord {
  return {
    kind: pickString(item, ["kind"]) || "diagnostic",
    title: pickString(item, ["title", "action", "effect"]) || "诊断",
    detail: pickString(item, ["detail", "reason", "summary"]) || "",
    tone: normalizeUiTone(pickString(item, ["tone"])),
    effect: pickString(item, ["effect", "projection_effect", "projectionEffect"]) || "",
    fencingResult:
      pickString(item, ["fencing_result", "fencingResult"]) || "",
    eventId: pickString(item, ["event_id", "eventId"]) || "",
    attemptedEventId:
      pickString(item, ["attempted_event_id", "attemptedEventId"]) || "",
    runId: pickString(item, ["run_id", "runId"]) || "",
    taskId: pickString(item, ["task_id", "taskId"]) || "",
    createdAt: pickString(item, ["created_at", "createdAt"]) || "",
  };
}

function normalizeUiActionItem(item: UnknownRecord): UiActionItem {
  return {
    id: pickString(item, ["id"]) || "action",
    kind: pickString(item, ["kind"]) || "task",
    title: pickString(item, ["title"]) || "Action",
    description: pickString(item, ["description", "summary"]) || "",
    tone: normalizeUiTone(pickString(item, ["tone"])),
    route: normalizeViewName(pickString(item, ["route"])),
    priority: Math.round(pickNumber(item, ["priority"]) ?? 0),
    runId: pickString(item, ["run_id", "runId"]) || "",
    taskId: pickString(item, ["task_id", "taskId"]) || "",
    gateId: pickString(item, ["gate_id", "gateId"]) || "",
    artifactId: pickString(item, ["artifact_id", "artifactId"]) || "",
    agentId: pickString(item, ["agent_id", "agentId"]) || "",
    createdAt: pickString(item, ["created_at", "createdAt"]) || "",
    suggestedActions: toStringArray(
      firstValue(item, ["suggested_actions", "suggestedActions"]),
    ),
  };
}

function normalizeUiAgentSummaryList(
  value: unknown,
  fallback: UiAgentSummary[] = [],
): UiAgentSummary[] {
  if (value == null) {
    return fallback;
  }
  const items = toArray(value).map(normalizeUiAgentSummary);
  return items;
}

function normalizeUiGateDecisionList(
  value: unknown,
  fallback: UiGateDecision[] = [],
): UiGateDecision[] {
  if (value == null) {
    return fallback;
  }
  const items = toArray(value).map(normalizeUiGateDecision);
  return items;
}

function normalizeStringList(value: unknown, fallback: string[] = []): string[] {
  if (value == null) {
    return fallback;
  }
  const items = toStringArray(value).filter(Boolean);
  return items;
}

function agentRowToUiAgentSummary(agent: AgentRow): UiAgentSummary {
  return {
    agentId: agent.id,
    displayName: agent.name || agent.id,
    role: agent.role,
    runtimeState: agent.state,
    identityLifecycle: "active",
    presenceState: "unknown",
    workloadState: "historical",
    uiVisibilityState: "hidden",
    conditions: [],
    hiddenReason: "",
    tone: normalizeUiTone(agent.state),
    healthScore: null,
    stale: /stale|offline/i.test(agent.state),
    currentTaskId: "",
    currentTaskTitle: "",
    openGateId: "",
    queuedInbox: agent.inboxCount,
    nextAction: agent.inboxCount ? "inbox" : "",
  };
}

function normalizeUiAgentSummary(agent: UnknownRecord): UiAgentSummary {
  return {
    agentId: pickString(agent, ["agent_id", "agentId"]) || "",
    displayName:
      pickString(agent, ["display_name", "displayName", "name"]) || "",
    role: pickString(agent, ["role"]) || "",
    runtimeState:
      pickString(agent, ["runtime_state", "runtimeState", "state"]) || "",
    identityLifecycle:
      pickString(agent, ["identity_lifecycle", "identityLifecycle"]) || "active",
    presenceState:
      pickString(agent, ["presence_state", "presenceState"]) || "unknown",
    workloadState:
      pickString(agent, ["workload_state", "workloadState"]) || "historical",
    uiVisibilityState:
      pickString(agent, ["ui_visibility_state", "uiVisibilityState"]) || "hidden",
    conditions: toArray(firstValue(agent, ["conditions"])).map(normalizeRuntimeCondition),
    hiddenReason: pickString(agent, ["hidden_reason", "hiddenReason"]) || "",
    tone: normalizeUiTone(pickString(agent, ["tone"])),
    healthScore: pickNumber(agent, ["health_score", "healthScore"]) ?? null,
    stale: pickBoolean(agent, ["stale"]) ?? false,
    currentTaskId:
      pickString(agent, ["current_task_id", "currentTaskId"]) || "",
    currentTaskTitle:
      pickString(agent, ["current_task_title", "currentTaskTitle"]) || "",
    openGateId: pickString(agent, ["open_gate_id", "openGateId"]) || "",
    queuedInbox: Math.max(
      0,
      Math.round(pickNumber(agent, ["queued_inbox", "queuedInbox"]) ?? 0),
    ),
    nextAction: pickString(agent, ["next_action", "nextAction"]) || "",
  };
}

function gateRowToUiGateDecision(gate: GateRow): UiGateDecision {
  return {
    gateId: gate.id,
    name: gate.name,
    state: gate.state,
    risk: gate.risk,
    tone: normalizeUiTone(gate.state),
    runId: gate.runId,
    taskId: gate.taskId,
    ownerAgentId: gate.owner,
    requestedBy: gate.requestedBy,
    reason: gate.reason,
    priority: 0,
    relevanceState: "",
    uiVisibilityState: "hidden",
    relevanceReason: "",
  };
}

function normalizeUiGateDecision(gate: UnknownRecord): UiGateDecision {
  return {
    gateId: pickString(gate, ["gate_id", "gateId"]) || "",
    name: pickString(gate, ["name", "title"]) || "",
    state: pickString(gate, ["state", "status"]) || "",
    risk: pickString(gate, ["risk"]) || "normal",
    tone: normalizeUiTone(pickString(gate, ["tone"])),
    runId: pickString(gate, ["run_id", "runId"]) || "",
    taskId: pickString(gate, ["task_id", "taskId"]) || "",
    ownerAgentId:
      pickString(gate, ["owner_agent_id", "ownerAgentId"]) || "",
    requestedBy: pickString(gate, ["requested_by", "requestedBy"]) || "",
    reason: pickString(gate, ["reason"]) || "",
    priority: Math.round(pickNumber(gate, ["priority"]) ?? 0),
    relevanceState:
      pickString(gate, ["relevance_state", "relevanceState"]) || "",
    uiVisibilityState:
      pickString(gate, ["ui_visibility_state", "uiVisibilityState"]) || "hidden",
    relevanceReason:
      pickString(gate, ["relevance_reason", "relevanceReason"]) || "",
  };
}

function normalizeRuntimeCondition(condition: UnknownRecord): RuntimeCondition {
  return {
    type: pickString(condition, ["type"]) || "Unknown",
    status: pickString(condition, ["status"]) || "unknown",
    reason: pickString(condition, ["reason"]) || "unspecified",
    message: pickString(condition, ["message"]) || null,
    severity: pickString(condition, ["severity"]) || "info",
    source: pickString(condition, ["source"]) || "projection",
    lastTransitionAt:
      pickString(condition, ["last_transition_at", "lastTransitionAt"]) || "",
    observedGeneration:
      pickNumber(condition, ["observed_generation", "observedGeneration"]) ?? null,
  };
}

function normalizeUiHiddenCounts(counts: UnknownRecord): UiHiddenCounts {
  return {
    archivedAgents: Math.max(
      0,
      Math.round(pickNumber(counts, ["archived_agents", "archivedAgents"]) ?? 0),
    ),
    staleSessions: Math.max(
      0,
      Math.round(pickNumber(counts, ["stale_sessions", "staleSessions"]) ?? 0),
    ),
    historicalGates: Math.max(
      0,
      Math.round(pickNumber(counts, ["historical_gates", "historicalGates"]) ?? 0),
    ),
    supersededGates: Math.max(
      0,
      Math.round(pickNumber(counts, ["superseded_gates", "supersededGates"]) ?? 0),
    ),
    hiddenContextPackets: Math.max(
      0,
      Math.round(
        pickNumber(counts, ["hidden_context_packets", "hiddenContextPackets"]) ?? 0,
      ),
    ),
    collapsedReplacementEvents: Math.max(
      0,
      Math.round(
        pickNumber(counts, [
          "collapsed_replacement_events",
          "collapsedReplacementEvents",
        ]) ?? 0,
      ),
    ),
    unboundArtifacts: Math.max(
      0,
      Math.round(pickNumber(counts, ["unbound_artifacts", "unboundArtifacts"]) ?? 0),
    ),
  };
}

function normalizeUiArtifactSummary(summary: UnknownRecord): UiArtifactSummary {
  return {
    total: Math.max(0, Math.round(pickNumber(summary, ["total"]) ?? 0)),
    byKind: normalizeNumberRecord(firstRecord(summary.by_kind, summary.byKind)),
    latestArtifactId:
      pickString(summary, ["latest_artifact_id", "latestArtifactId"]) || "",
    latestTitle: pickString(summary, ["latest_title", "latestTitle"]) || "",
    latestUri: pickString(summary, ["latest_uri", "latestUri"]) || "",
    latestCreatedAt:
      pickString(summary, ["latest_created_at", "latestCreatedAt"]) || "",
  };
}

function normalizeMetrics(
  root: UnknownRecord,
  agents: AgentRow[],
  gates: GateRow[],
  tasks: TaskRow[],
): OperationsMetrics {
  const rawMetrics = firstRecord(root.metrics, root.summary);
  const agentCount =
    pickNumber(rawMetrics, ["agent_count", "agentCount", "agents"]) ??
    agents.length;
  const pendingInbox =
    pickNumber(rawMetrics, [
      "pending_inbox",
      "pendingInbox",
      "inbox_count",
      "inboxCount",
      "queued_inbox",
      "queuedInbox",
    ]) ?? agents.reduce((sum, agent) => sum + agent.inboxCount, 0);
  const openGateCount =
    pickNumber(rawMetrics, ["open_gates", "openGates", "gate_count"]) ??
    gates.filter((gate) => !isClosedState(gate.state)).length;
  const contextFaults =
    pickNumber(rawMetrics, ["context_faults", "contextFaults"]) ??
    tasks.filter((task) => isBadIntegrity(task.contextIntegrity)).length;
  const artifactCount =
    pickNumber(rawMetrics, ["artifacts", "artifact_count", "artifactCount"]) ??
    0;

  return {
    agentCount: Math.max(0, Math.round(agentCount)),
    pendingInbox: Math.max(0, Math.round(pendingInbox)),
    openGateCount: Math.max(0, Math.round(openGateCount)),
    contextFaults: Math.max(0, Math.round(contextFaults)),
    artifactCount: Math.max(0, Math.round(artifactCount)),
  };
}

function collectEvents(root: UnknownRecord): UnknownRecord[] {
  return [
    ...toArray(root.events),
    ...toArray(root.timeline),
    ...toArray(root.recent_events),
    ...toArray(root.event_log),
  ];
}

function collectReplacements(root: UnknownRecord): UnknownRecord[] {
  return [
    ...toArray(root.replacements),
    ...toArray(root.replacement_recommendations),
    ...toArray(root.recommendations),
  ];
}

function collectInterruptAffectedAgents(
  root: UnknownRecord,
  events: EventRow[],
): string[] {
  const fromRoot = toStringArray(
    firstValue(root, [
      "interrupt_affected_agents",
      "interruptAffectedAgents",
      "affected_agents",
      "affectedAgents",
    ]),
  );
  const fromEvents = events.flatMap((event) =>
    event.type.toLowerCase().includes("interrupt") ||
    event.text.toLowerCase().includes("interrupt")
      ? event.affectedAgents
      : [],
  );
  return Array.from(new Set([...fromRoot, ...fromEvents])).sort();
}

function collectCapabilities(agent: UnknownRecord): string[] {
  const raw = firstValue(agent, [
    "capabilities",
    "declared_capabilities",
    "declaredCapabilities",
  ]);
  if (Array.isArray(raw)) {
    return raw
      .map((item) =>
        isRecord(item)
          ? pickString(item, ["name", "capability", "id"])
          : String(item),
      )
      .filter((item): item is string => Boolean(item))
      .slice(0, 4);
  }
  return [];
}

function normalizeIntegrity(status: string | undefined, valid?: boolean): string {
  if (typeof valid === "boolean") {
    return valid ? "valid" : "invalid";
  }
  return status || "unknown";
}

function deriveTone(type: string, text: string, state?: string): Tone {
  const haystack = `${type} ${text} ${state || ""}`.toLowerCase();
  if (
    haystack.includes("fail") ||
    haystack.includes("error") ||
    haystack.includes("blocked") ||
    haystack.includes("invalid") ||
    haystack.includes("reject") ||
    haystack.includes("wrong_session") ||
    haystack.includes("stale_epoch") ||
    haystack.includes("missing")
  ) {
    return "bad";
  }
  if (
    haystack.includes("warn") ||
    haystack.includes("interrupt") ||
    haystack.includes("stale") ||
    haystack.includes("replacement") ||
    haystack.includes("gate")
  ) {
    return "warn";
  }
  if (haystack.includes("pass") || haystack.includes("approved")) {
    return "good";
  }
  return "info";
}

function isClosedState(state: string): boolean {
  return ["approved", "closed", "complete", "completed", "done", "passed"].some(
    (closed) => state.toLowerCase().includes(closed),
  );
}

function isBadIntegrity(integrity: string): boolean {
  const value = integrity.toLowerCase();
  return value.includes("invalid") || value.includes("suspect");
}

function firstRecord(...values: unknown[]): UnknownRecord {
  return values.find(isRecord) || {};
}

function firstValue(record: UnknownRecord, keys: string[]): unknown {
  for (const key of keys) {
    if (key in record) {
      return record[key];
    }
  }
  return undefined;
}

function pickString(record: UnknownRecord, keys: string[]): string | undefined {
  const value = firstValue(record, keys);
  if (typeof value === "string") {
    return value;
  }
  if (typeof value === "number") {
    return String(value);
  }
  return undefined;
}

function pickNumber(
  record: UnknownRecord,
  keys: string[],
  fallback?: number,
): number | undefined {
  const value = firstValue(record, keys);
  if (typeof value === "number" && Number.isFinite(value)) {
    return value;
  }
  if (typeof value === "string" && value.trim()) {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : fallback;
  }
  return fallback;
}

function pickBoolean(record: UnknownRecord, keys: string[]): boolean | undefined {
  const value = firstValue(record, keys);
  return typeof value === "boolean" ? value : undefined;
}

function sumRecordNumbers(record: UnknownRecord): number | undefined {
  const values = Object.values(record).filter(
    (value): value is number => typeof value === "number" && Number.isFinite(value),
  );
  return values.length ? values.reduce((sum, value) => sum + value, 0) : undefined;
}

function asPercent(value: number): number {
  const scaled = value <= 1 ? value * 100 : value;
  return Math.max(0, Math.min(100, Math.round(scaled)));
}

function toArray(value: unknown): UnknownRecord[] {
  if (Array.isArray(value)) {
    return value.filter(isRecord);
  }
  if (isRecord(value)) {
    return Object.values(value).filter(isRecord);
  }
  return [];
}

function toStringArray(value: unknown): string[] {
  if (!Array.isArray(value)) {
    return [];
  }
  return value
    .map((item) =>
      typeof item === "string" || typeof item === "number" ? String(item) : "",
    )
    .filter(Boolean);
}

function normalizeRoles(raw: unknown): string[] {
  const values = Array.isArray(raw) ? raw : String(raw || "").split(/[,\s/|]+/);
  const roles = values
    .map((value) => String(value).trim().toLowerCase())
    .filter(Boolean)
    .map((value) => (value === "archive" ? "observer" : value));
  return Array.from(new Set(roles.length ? roles : ["unassigned"]));
}

function normalizeNumberRecord(record: UnknownRecord): Record<string, number> {
  return Object.fromEntries(
    Object.entries(record)
      .map(([key, value]) => {
        if (typeof value === "number" && Number.isFinite(value)) {
          return [key, value] as const;
        }
        if (typeof value === "string" && value.trim()) {
          const parsed = Number(value);
          if (Number.isFinite(parsed)) {
            return [key, parsed] as const;
          }
        }
        return null;
      })
      .filter((item): item is readonly [string, number] => item !== null),
  );
}

function normalizeUiTone(value: string | undefined): UiTone {
  if (value === "good" || value === "warn" || value === "bad" || value === "info") {
    return value;
  }
  return "neutral";
}

function normalizeViewName(value: string | undefined): ViewName {
  if (
    value === "Home" ||
    value === "Communication" ||
    value === "Runs" ||
    value === "Gates" ||
    value === "Artifacts" ||
    value === "Diagnostics" ||
    value === "Settings"
  ) {
    return value;
  }
  return "Runs";
}

function isRecord(value: unknown): value is UnknownRecord {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}
