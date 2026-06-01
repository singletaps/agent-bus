# Agent Workstation Operations Room Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Redesign only the Operations first screen so Agent Bus reads as an operator workstation rather than a debug/database console.

**Architecture:** Keep backend APIs unchanged. Add a richer frontend view model that converts existing projection data into an Operations Brief, Agent Workstation cards, and decision-oriented task lanes, then wire those model objects into existing React components and CSS. Preserve Command Composer BUG-2 routing fields and all existing routes.

**Tech Stack:** React 19, TypeScript, Vite, lucide-react, existing `frontend/src/operationsApi.ts`, existing live service at `http://127.0.0.1:8787/`.

---

## Required Context

- Use repo skill `.agents/skills/ux-operator-review`.
- Use repo skill `.agents/skills/frontend-design`.
- Use repo skill `.agents/skills/frontend-design-review`.
- Read `coordination/ux-operator-review-round1.md`.
- Read `coordination/marvis-agent-workstation-research.md`.
- Read `coordination/frontend-skill-discovery.md`.
- Current baseline screenshot: `coordination/ux-operator-review-before.png`.

## File Structure

- Modify `frontend/src/operationsRoomModel.ts`: convert API projection rows into operator-first model objects.
- Modify `frontend/src/uiText.ts`: add Chinese-first labels for Operations Brief, workstation cards, action states, and decision lanes.
- Modify `frontend/src/App.tsx`: render Operations Brief, Agent Workstation cards, decision lanes, stronger Inspector, and structured event digest using existing data.
- Modify `frontend/src/styles.css`: implement the Agent Workstation visual system, responsive layout, and no-overflow rules.
- Modify `coordination/frontend-optimization-qa-checklist.md`: append this new wave's QA evidence.
- Create `coordination/agent-workstation-redesign-qa-artifact.json`: final helper1 QA evidence.

## Non-Goals

- Do not touch backend APIs or database projections.
- Do not change `/api/interrupt` payload shape.
- Do not remove `routing_mode` or `include_selected_task`.
- Do not use worker2, worker3, or runtime-qa for implementation.
- Do not introduce cute companion or pet UI.
- Do not generate fake data.

## Parallel Batch 1

### Task 1: Worker1 Operations View Model

**Assignee:** `runtime-worker-1`

**Files:**
- Modify: `frontend/src/operationsRoomModel.ts`
- Modify: `frontend/src/uiText.ts`

- [ ] **Step 1: Read UX references**

Read:

```powershell
Get-Content .agents\skills\ux-operator-review\SKILL.md
Get-Content .agents\skills\ux-operator-review\references\walkthrough.md
Get-Content coordination\ux-operator-review-round1.md
```

- [ ] **Step 2: Add model types**

In `frontend/src/operationsRoomModel.ts`, add these types near the existing exports:

```ts
export type OperatorActionTone = "good" | "warn" | "bad" | "info";
export type OperatorActionKind =
  | "review-task"
  | "inspect-failure"
  | "approve-gate"
  | "watch-inbox"
  | "monitor";

export type OperationsBrief = {
  headline: string;
  detail: string;
  primaryAction: {
    kind: OperatorActionKind;
    label: string;
    targetId: string;
    tone: OperatorActionTone;
  };
};

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

export type WorkstationModel = AgentCardModel & {
  roleKind: WorkstationRole;
  posture: WorkstationPosture;
  postureText: string;
  trustText: string;
  currentWork: string;
  nextAction: string;
  urgency: OperatorActionTone;
};

export type DecisionLane = "needsAction" | "active" | "waiting" | "done";
```

- [ ] **Step 3: Extend `OperationsRoomModel`**

Change the model shape to include the new objects while keeping existing properties for compatibility:

```ts
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
```

- [ ] **Step 4: Implement helpers**

Add pure helpers below `taskLane()`:

```ts
export function decisionLane(task: TaskRow): DecisionLane {
  const state = task.state.toLowerCase();
  if (["blocked", "failed", "changes_requested", "reassigned"].some((value) => state.includes(value))) {
    return "needsAction";
  }
  if (["working", "assigned", "acknowledged", "in_progress"].some((value) => state.includes(value))) {
    return "active";
  }
  if (["completed", "complete", "done", "approved", "passed"].some((value) => state.includes(value))) {
    return "done";
  }
  return "waiting";
}

function workstationRole(agent: AgentRow): WorkstationRole {
  const value = `${agent.id} ${agent.role}`.toLowerCase();
  if (value.includes("helper")) return "helper";
  if (value.includes("qa")) return "qa";
  if (value.includes("controller")) return "controller";
  if (value.includes("observer") || value.includes("archive")) return "observer";
  if (value.includes("frontend") || value.includes("react")) return "frontend";
  if (value.includes("backend") || value.includes("store") || value.includes("fastapi")) return "backend";
  if (value.includes("worker")) return "worker";
  return "unknown";
}

function workstationPosture(agent: AgentRow): WorkstationPosture {
  const state = agent.state.toUpperCase();
  if (state.includes("CONTEXT") || state.includes("LOST") || state.includes("UNAVAILABLE")) return "fault";
  if (state.includes("DEGRADED") || state.includes("STUCK")) return "degraded";
  if (state.includes("GATE")) return "gate";
  if (state.includes("REVIEW")) return "review";
  if (state.includes("WORKING")) return "working";
  if (state.includes("WAIT")) return "waiting";
  return "standby";
}
```

- [ ] **Step 5: Add brief and workstation builders**

Add helpers that use real projection data only:

```ts
function buildBrief(
  projection: OperationsProjection,
  tasks: TaskCardModel[],
  urgentGates: GateRow[],
): OperationsBrief {
  const actionTask = tasks.find((task) => decisionLane(task) === "needsAction");
  if (actionTask) {
    return {
      headline: "需要处理任务异常",
      detail: `${actionTask.title} 需要定位或重新分派。`,
      primaryAction: {
        kind: "inspect-failure",
        label: "查看异常任务",
        targetId: actionTask.id,
        tone: "bad",
      },
    };
  }
  const gate = urgentGates[0];
  if (gate) {
    return {
      headline: "门禁等待决策",
      detail: `${gate.name} 等待 ${gate.owner || "负责人"} 处理。`,
      primaryAction: {
        kind: "approve-gate",
        label: "查看门禁",
        targetId: gate.id,
        tone: "warn",
      },
    };
  }
  if (projection.metrics.pendingInbox > 0) {
    return {
      headline: "总线有待确认消息",
      detail: `${projection.metrics.pendingInbox} 条 inbox 需要相关 Agent 消化。`,
      primaryAction: {
        kind: "watch-inbox",
        label: "查看 Agent",
        targetId: "agent-dock",
        tone: "warn",
      },
    };
  }
  return {
    headline: "系统平稳运行",
    detail: "当前没有开放门禁或上下文风险。",
    primaryAction: {
      kind: "monitor",
      label: "继续监控",
      targetId: "operations",
      tone: "good",
    },
  };
}

function buildWorkstation(agent: AgentCardModel, tasks: TaskCardModel[]): WorkstationModel {
  const activeTask = tasks.find((task) => task.owner === agent.id && decisionLane(task) !== "done");
  const posture = workstationPosture(agent);
  return {
    ...agent,
    roleKind: workstationRole(agent),
    posture,
    postureText: workstationPostureLabel(posture),
    trustText: agent.contextIntegrity === "valid" ? "上下文可信" : "上下文需确认",
    currentWork: activeTask?.title || (agent.inboxCount > 0 ? `${agent.inboxCount} 条 inbox` : "当前无任务"),
    nextAction: nextActionForAgent(agent, activeTask),
    urgency: posture === "fault" ? "bad" : posture === "degraded" || agent.inboxCount > 0 ? "warn" : posture === "working" ? "info" : "good",
  };
}
```

Also add `workstationPostureLabel()` and `nextActionForAgent()` with explicit Chinese labels; keep labels short enough for cards.

- [ ] **Step 6: Return new model fields**

Inside `buildOperationsRoomModel()`, create `decisionLanes`, `urgentGates`, `brief`, and `workstations`, then return them with the existing fields:

```ts
const decisionLanes: Record<DecisionLane, TaskCardModel[]> = {
  needsAction: tasks.filter((task) => decisionLane(task) === "needsAction"),
  active: tasks.filter((task) => decisionLane(task) === "active"),
  waiting: tasks.filter((task) => decisionLane(task) === "waiting"),
  done: tasks.filter((task) => decisionLane(task) === "done").slice(0, 8),
};

const urgentGates = projection.gates.filter((gate) => !isClosedState(gate.state));
const brief = buildBrief(projection, tasks, urgentGates);
const workstations = agents.map((agent) => buildWorkstation(agent, tasks));
```

- [ ] **Step 7: Add labels**

In `frontend/src/uiText.ts`, add:

```ts
  brief: {
    primaryAction: "优先动作",
    activeRun: "当前任务流",
  },
  workstation: {
    currentWork: "当前工作",
    nextAction: "下一步",
    trust: "可信度",
  },
  decisionLanes: {
    needsAction: "需要处理",
    active: "进行中",
    waiting: "等待/待命",
    done: "已完成",
  },
```

- [ ] **Step 8: Verify TypeScript**

Run:

```powershell
npm run build
```

Expected: exit code 0. The lucide-react `"use client"` warnings are acceptable.

### Task 2: Worker4 Visual Tokens And Workstation CSS

**Assignee:** `runtime-worker-4`

**Files:**
- Modify: `frontend/src/styles.css`
- Read: `.agents/skills/frontend-design/SKILL.md`
- Read: `.agents/skills/frontend-design/references/agent-workstation-visual-direction.md`

- [ ] **Step 1: Add workstation tokens**

Add semantic role and posture tokens near `:root`:

```css
  --role-controller: #88b7ff;
  --role-worker: #64d2b4;
  --role-helper: #c7a8ff;
  --role-qa: #e7bd61;
  --role-observer: #9fb0a0;
  --posture-working: #68a8ff;
  --posture-standby: #8aa08a;
  --posture-waiting: #d7b35f;
  --posture-review: #b99cff;
  --posture-degraded: #f0a45d;
  --posture-fault: #ee7f7a;
```

- [ ] **Step 2: Add Operations Brief classes**

Create CSS for `.operationsBrief`, `.briefCopy`, `.briefAction`, and `.briefRun` that works inside `.opsTopBar` without changing the grid wider than 1280px.

- [ ] **Step 3: Add workstation card classes**

Create CSS for:

```css
.workstationCard
.workstationIdentity
.workstationMark
.stationGlyph
.postureLine
.stationCurrent
.stationAction
.stationTrust
```

Rules:

- `min-width: 0` on text containers.
- Use 8px radius or less.
- Use compact role/posture lights, not large avatars.
- Do not use gradient orbs or decorative blobs.
- Long IDs must ellipsize.

- [ ] **Step 4: Add decision lane classes**

Create CSS for `.decisionLanes`, `.decisionLane`, `.decisionCard`, `.decisionMeta`, and `.decisionAction`.

Rules:

- Desktop: lanes cannot be narrower than 220px.
- At `max-width: 1380px`, allow 2-column or stacked lanes.
- At `max-width: 820px`, use a single column.
- No horizontal scrolling from cards.

- [ ] **Step 5: Preserve existing controls**

Confirm `.commandComposer`, `.composerForm`, `.composerContext`, and `.routingMode` styles still wrap correctly on mobile.

- [ ] **Step 6: Build smoke**

Run:

```powershell
npm run build
```

Expected: exit code 0.

## Serial Batch 2

### Task 3: Helper2 App Wiring

**Assignee:** `runtime-helper-2`

**Files:**
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/uiText.ts` only if labels from Task 1 need a small correction
- Do not modify: `frontend/src/operationsApi.ts`

- [ ] **Step 1: Read plan and UX review**

Read:

```powershell
Get-Content docs\superpowers\plans\2026-05-28-agent-workstation-operations-room-redesign.md
Get-Content coordination\ux-operator-review-round1.md
```

- [ ] **Step 2: Update TopHealthBar**

Pass `room.brief` and active run id into `TopHealthBar`.

Render:

- headline
- detail
- primary action label
- active run short id
- existing metrics
- refresh button

Keep `Metric` components and current load error behavior.

- [ ] **Step 3: Update AgentDock**

Change `AgentDock` to accept `workstations={room.workstations}`. Render `workstationCard` buttons with:

- role marker
- agent id
- role
- postureText
- currentWork
- nextAction
- trustText
- shortSession
- health and confidence bars

Keep `onSelectAgent(agent.id)`.

- [ ] **Step 4: Update MissionSurface**

Change `MissionSurface` to use `room.decisionLanes`. Render four lanes:

```ts
const lanes: DecisionLane[] = ["needsAction", "active", "waiting", "done"];
```

Use `uiText.decisionLanes[lane]` for labels. In task cards, prioritize title, stateText, owner, short id, and context integrity. Do not show full context packet id in the primary line.

- [ ] **Step 5: Strengthen Inspector empty/current state**

When no selected task exists, show an empty state that says the operator should select a task, gate, or Agent to inspect evidence. When a task exists, keep visible:

- title
- owner
- state
- run id short form
- context integrity
- context packet short form

- [ ] **Step 6: Keep Command Composer unchanged except layout**

Confirm this payload still exists exactly:

```ts
payload: {
  source: "operations-console",
  routing_mode: taskContext ? "task-context" : "agent-only",
  selected_task_id: selectedTask?.id,
  include_selected_task: Boolean(taskContext),
},
```

- [ ] **Step 7: Build smoke**

Run:

```powershell
npm run build
```

Expected: exit code 0.

## Parallel Batch 3

### Task 4: Worker4 Screenshot Polish Pass

**Assignee:** `runtime-worker-4`

**Files:**
- Modify: `frontend/src/styles.css`
- Modify: `coordination/frontend-optimization-qa-checklist.md`

- [ ] **Step 1: Open current app after Task 3**

Use Browser at:

```txt
http://127.0.0.1:8787/
```

Capture a screenshot to:

```txt
coordination/agent-workstation-worker4-polish.png
```

- [ ] **Step 2: Fix only visual craft issues**

Limit changes to CSS polish:

- first-screen hierarchy
- text wrapping
- card density
- state color consistency
- desktop/mobile no-overflow

Do not change React logic or Command Composer payload.

- [ ] **Step 3: Verify**

Run:

```powershell
npm run build
```

Expected: exit code 0.

Record screenshot and notes in `coordination/frontend-optimization-qa-checklist.md`.

### Task 5: Worker1 Source-Level Regression Check

**Assignee:** `runtime-worker-1`

**Files:**
- Read: `frontend/src/App.tsx`
- Read: `frontend/src/operationsRoomModel.ts`
- Modify: `coordination/frontend-optimization-qa-checklist.md`

- [ ] **Step 1: Verify model invariants**

Confirm:

- no fake data is introduced
- `urgentGates` still filters only non-closed gates
- degraded/stuck/context-lost states cannot be mapped to healthy green ready
- completed tasks in `done` lane are capped or visually demoted

- [ ] **Step 2: Verify BUG-2 source**

Confirm `frontend/src/App.tsx` still contains:

```ts
routing_mode: taskContext ? "task-context" : "agent-only",
include_selected_task: Boolean(taskContext),
```

- [ ] **Step 3: Build**

Run:

```powershell
npm run build
```

Expected: exit code 0.

Record findings in `coordination/frontend-optimization-qa-checklist.md`.

## Final QA

### Task 6: Helper1 QA Gate

**Assignee:** `runtime-helper-1`

**Files:**
- Modify: `coordination/frontend-optimization-qa-checklist.md`
- Create: `coordination/agent-workstation-redesign-qa-artifact.json`
- Create: `coordination/ux-operator-review-after.png`

- [ ] **Step 1: Build**

Run:

```powershell
npm run build
```

Expected: exit code 0.

- [ ] **Step 2: Browser desktop QA**

Open:

```txt
http://127.0.0.1:8787/
```

Verify:

- console errors/warnings: none
- no outside viewport elements
- no tracked card overflow
- Chinese labels visible
- BUG-2 `携带任务上下文` visible
- stale/degraded agents visible as attention/degraded, not healthy

- [ ] **Step 3: Browser mobile QA**

Set viewport to 390x844 and repeat the same checks. Reset viewport afterward.

- [ ] **Step 4: Repeat UX Operator Review**

Use `.agents/skills/ux-operator-review` and compare against `coordination/ux-operator-review-round1.md`.

Pass only if:

- first-time user can state system health within 10 seconds
- daily operator can scan working/waiting/stuck/standby agents
- incident responder sees the first action
- QA reviewer can find evidence path
- tired user can identify one urgent thing

- [ ] **Step 5: Gate decision**

If all checks pass:

- resolve any review findings
- complete Task 6
- approve the high-risk frontend gate
- notify `runtime-worker-1`, `runtime-worker-4`, and `runtime-helper-2`

If any check fails:

- create a blocking review finding with screenshot/DOM evidence
- assign the fix to Worker4 for visual issues, Worker1 for model issues, or Helper2 for App wiring issues

## Self-Review

- Spec coverage: covers skill discovery, Marvis research, UX review, repo skills, Operations first-screen redesign, worker1/worker4/helper2 assignment, helper1 QA, browser QA, and pixel/sprite availability.
- Placeholder scan: no TODO/TBD placeholders.
- Type consistency: new model types are consumed by App wiring tasks and styled by CSS tasks.
- Regression coverage: BUG-2 payload preservation, stale/degraded state readability, no fake data, build, desktop browser, and mobile browser.
