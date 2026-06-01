# Agent Operations Room Frontend Optimization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn the current English debug-style Operations Console into a Chinese-first Agent Operations Room for long-running Agent Bus supervision.

**Architecture:** Keep the existing React/Vite API contract and real backend data. Add a small view-model and Chinese copy layer, then reshape the UI around a permanent operations-room layout: health bar, Agent dock, mission surface, inspector, event console, gates, RunGraph, artifacts, and command composer. Avoid mock data, fake states, decorative landing-page patterns, and frontend redesign work outside the assigned files.

**Tech Stack:** React 19, Vite 7, TypeScript, CSS modules by file convention through imported CSS, existing `/api/projections/operations`, `lucide-react` icons added through `frontend/package.json`.

---

## Current State From Browser Inspection

- URL checked: `http://127.0.0.1:8787/`
- Browser title: `Agent Bus Operations`
- Console errors/warnings: none during inspection.
- Current UI is usable but still reads as an English engineering dashboard: left nav, task board, gates, Agent list, and status chips.
- `runtime-qa`, `runtime-worker-2`, and `runtime-worker-3` now render as `STANDBY_DEGRADED`, proving Round2 freshness work is visible.
- The page does not yet communicate the user's desired feeling: Chinese operations room, industrial mission-control discipline, IDE-like trace console, and persistent Agent supervision.

## User Constraints

- Start only after Round2 bugfix gate approval. Gate `gate_cdfd1244f34b4592a982fc0e5a9c23b6` is approved.
- Available implementation agents: `runtime-worker-1`, `runtime-worker-4`, `runtime-helper-2`.
- `runtime-helper-1` is Controller and QA for this frontend optimization wave.
- Do not assign implementation to `runtime-worker-2`, `runtime-worker-3`, or `runtime-qa`.
- Chinese interface is required. Terms that may remain English: `worker`, `helper`, `QA`, `Agent`, `Agent Bus`, `RunGraph`.
- No frontend work may use mock data or hardcoded test-only states.
- Keep BUG-2 Command Composer routing behavior intact: mismatched explicit target defaults to agent-only routing unless task context is explicitly included.

## Target Experience

The first viewport should feel like a permanent operations room:

- A compact top health bar answers "is the runtime healthy right now?"
- A left Agent dock shows alive, degraded, lost, and busy identities without implying closed agents are healthy.
- A mission surface shows active work, attention items, gates, and next required action.
- A right inspector shows the selected Agent/task/gate context without forcing the user to scan raw cards.
- A bottom or side event console supports trace-like scanning of interrupts, gates, replacement, errors, and lifecycle events.
- UI text is Chinese-first, dense, and operational; it should not read like marketing copy or a tutorial.

## File Structure

Create or modify these files only unless the Controller expands scope:

- Create: `frontend/src/uiText.ts`
  - Chinese labels, state labels, tone labels, and navigation labels.
- Create: `frontend/src/operationsRoomModel.ts`
  - Derived view model for Agent presence, task lanes, gate urgency, event groups, and top-bar metrics.
- Modify: `frontend/src/App.tsx`
  - Compose the operations-room layout and keep command routing behavior.
- Modify: `frontend/src/styles.css`
  - Replace prototype styling with an industrial operations-room visual system.
- Modify: `frontend/package.json`
  - Add `lucide-react` for navigation and command icons.
- Modify: `frontend/package-lock.json`
  - Updated by `npm install lucide-react`.
- Create: `coordination/frontend-optimization-qa-checklist.md`
  - QA checklist and Browser evidence log owned by helper1/worker4.

## Ownership

- `runtime-worker-1`: data/view-model foundation and state labeling.
- `runtime-helper-2`: React layout/component implementation and command composer preservation.
- `runtime-worker-4`: visual system CSS, Chinese copy review, docs/checklist, and accessibility/responsive polish.
- `runtime-helper-1`: Controller, QA, final Browser validation, gate decision.

## Wave Plan

### Wave F0: Controller Kickoff

Owner: `runtime-helper-1`

Dependencies: Round2 bugfix gate approved.

- [ ] **Step 1: Create live run and gate for frontend optimization**

Run title:

```text
Frontend Optimization: Agent Operations Room
```

Gate name:

```text
Frontend Optimization QA Gate
```

Gate pass condition:

```text
Chinese-first operations-room UI implemented with real backend data, no mock fallback, npm build passing, Browser desktop/mobile checks passing, no console errors, BUG-2 routing preserved.
```

- [ ] **Step 2: Assign only alive implementation agents**

Assignments:

```text
runtime-worker-1 -> Wave F1 view model and state language
runtime-helper-2 -> Wave F2/F3 React layout and interactions
runtime-worker-4 -> Wave F2/F3 visual system, Chinese copy, QA checklist
runtime-helper-1 -> QA only
```

Expected Controller broadcast:

```text
FRONTEND_OPTIMIZATION_KICKOFF
Use docs/superpowers/plans/2026-05-28-agent-operations-room-frontend-optimization.md.
Do not assign work to runtime-worker-2, runtime-worker-3, or runtime-qa.
Preserve real API data and BUG-2 Command Composer routing.
```

### Task 1: View Model And Chinese State Foundation

Owner: `runtime-worker-1`

Can run in parallel with Task 2 copy review, but must finish before Task 3 layout wiring.

**Files:**

- Create: `frontend/src/uiText.ts`
- Create: `frontend/src/operationsRoomModel.ts`
- No changes to `frontend/src/operationsApi.ts` in this task.

- [ ] **Step 1: Create Chinese label map**

Create `frontend/src/uiText.ts` with this structure:

```ts
import type { Tone, ViewName } from "./operationsApi";

export const viewLabels: Record<ViewName, string> = {
  Operations: "总览",
  Agents: "Agent",
  Gates: "门禁",
  RunGraph: "RunGraph",
  Artifacts: "产物",
  Settings: "设置",
};

export const uiText = {
  appTitle: "Agent Bus",
  appSubtitle: "运行控制台",
  roomEyebrow: "AGENT OPERATIONS ROOM",
  roomTitle: "运行态势",
  refresh: "刷新",
  metrics: {
    agents: "Agent",
    pendingInbox: "待处理 inbox",
    openGates: "开放门禁",
    contextFaults: "上下文风险",
  },
  panels: {
    agentDock: "Agent Dock",
    missionSurface: "任务态势",
    gates: "门禁中心",
    inspector: "Inspector",
    eventConsole: "事件控制台",
    replacementDock: "接管席位",
    commandComposer: "指令台",
    runGraph: "RunGraph",
    artifacts: "产物",
    settings: "设置",
  },
  taskLanes: {
    active: "执行中",
    attention: "需处理",
    backlog: "待排队",
  },
  routing: {
    selectedTask: "选中任务",
    includeTaskContext: "携带任务上下文",
    agentOnly: "仅 Agent",
    taskContext: "任务上下文",
    targetAgent: "目标 Agent",
    interruptMessage: "中断内容",
    send: "发送",
  },
} as const;

const stateLabels: Record<string, string> = {
  WAITING_ON_BUS: "等待总线",
  WAIT_RETURNED_NOOP: "空轮询",
  DELIVERED_NOT_ACKED: "已投递待确认",
  WORKING: "工作中",
  SUSPECTED_STUCK: "疑似卡住",
  INPUT_UNAVAILABLE: "输入不可用",
  CONTEXT_LOST: "上下文丢失",
  NEEDS_REHYDRATION: "需要复水",
  REHYDRATING: "复水中",
  STANDBY_READY: "待命就绪",
  STANDBY_DEGRADED: "降级待命",
  REPLACED: "已接管",
};

const toneLabels: Record<Tone, string> = {
  good: "正常",
  warn: "注意",
  bad: "异常",
  info: "信息",
};

export function stateLabel(state: string): string {
  return stateLabels[state] ?? state;
}

export function toneLabel(tone: Tone): string {
  return toneLabels[tone];
}
```

- [ ] **Step 2: Create operations-room view model**

Create `frontend/src/operationsRoomModel.ts` with these exports:

```ts
import type {
  AgentRow,
  EventRow,
  GateRow,
  OperationsProjection,
  TaskRow,
  Tone,
} from "./operationsApi";
import { stateLabel } from "./uiText";

export type AgentPresence = "alive" | "busy" | "degraded" | "lost";
export type MissionLane = "active" | "attention" | "backlog";

export type AgentCardModel = AgentRow & {
  presence: AgentPresence;
  stateText: string;
  shortSession: string;
};

export type TaskCardModel = TaskRow & {
  lane: MissionLane;
  stateText: string;
};

export type OperationsRoomModel = {
  aliveAgents: AgentCardModel[];
  degradedAgents: AgentCardModel[];
  taskLanes: Record<MissionLane, TaskCardModel[]>;
  urgentGates: GateRow[];
  eventConsole: EventRow[];
  topRiskTone: Tone;
};

export function agentPresence(agent: AgentRow): AgentPresence {
  const state = agent.state.toUpperCase();
  if (state.includes("WORKING")) return "busy";
  if (state.includes("DEGRADED") || state.includes("STUCK")) return "degraded";
  if (state.includes("LOST") || state.includes("UNAVAILABLE") || state.includes("REPLACED")) return "lost";
  return "alive";
}

export function taskLane(task: TaskRow): MissionLane {
  const state = task.state.toLowerCase();
  if (["working", "assigned", "acknowledged", "in_progress"].some((value) => state.includes(value))) {
    return "active";
  }
  if (["blocked", "failed", "changes_requested", "reassigned"].some((value) => state.includes(value))) {
    return "attention";
  }
  return "backlog";
}

export function buildOperationsRoomModel(projection: OperationsProjection): OperationsRoomModel {
  const agents = projection.agents.map((agent) => ({
    ...agent,
    presence: agentPresence(agent),
    stateText: stateLabel(agent.state),
    shortSession: agent.sessionId === "no-session" ? "no-session" : agent.sessionId.slice(0, 12),
  }));

  const tasks = projection.tasks.map((task) => ({
    ...task,
    lane: taskLane(task),
    stateText: stateLabel(task.state),
  }));

  const taskLanes: Record<MissionLane, TaskCardModel[]> = {
    active: tasks.filter((task) => task.lane === "active"),
    attention: tasks.filter((task) => task.lane === "attention"),
    backlog: tasks.filter((task) => task.lane === "backlog"),
  };

  const urgentGates = projection.gates.filter((gate) => {
    const state = gate.state.toLowerCase();
    return !["approved", "closed", "complete", "completed", "done", "passed"].some((closed) =>
      state.includes(closed),
    );
  });

  const topRiskTone: Tone =
    projection.metrics.contextFaults > 0 || taskLanes.attention.length > 0
      ? "bad"
      : urgentGates.length > 0
        ? "warn"
        : "good";

  return {
    aliveAgents: agents.filter((agent) => agent.presence === "alive" || agent.presence === "busy"),
    degradedAgents: agents.filter((agent) => agent.presence === "degraded" || agent.presence === "lost"),
    taskLanes,
    urgentGates,
    eventConsole: projection.events.slice(0, 80),
    topRiskTone,
  };
}
```

- [ ] **Step 3: Confirm `operationsApi.ts` compatibility**

Do not edit `frontend/src/operationsApi.ts` in Task 1. Confirm the view model compiles against existing exported types:

```ts
import type { AgentRow, OperationsProjection, TaskRow } from "./operationsApi";
```

If this import fails during build, stop and report a BLOCKER rather than renaming API fields.

- [ ] **Step 4: Verify**

Run:

```powershell
Set-Location 'C:\Users\laptopofzy\Documents\Agent bus\frontend'
npm run build
```

Expected:

```text
vite build
built in
```

- [ ] **Step 5: Report**

Post to the fallback bus:

```text
FRONTEND_F1_WORKER1_READY
Files changed: frontend/src/uiText.ts, frontend/src/operationsRoomModel.ts, optional frontend/src/operationsApi.ts
Verification: npm run build passed
```

### Task 2: Chinese Copy Review And Visual Tokens

Owner: `runtime-worker-4`

Can run in parallel with Task 1, but must not rewrite `App.tsx`.

**Files:**

- Modify: `frontend/src/styles.css`
- Create: `coordination/frontend-optimization-qa-checklist.md`
- Review only: `frontend/src/uiText.ts`

- [ ] **Step 1: Add operations-room CSS tokens**

At the top of `frontend/src/styles.css`, replace the current color token block with this palette:

```css
:root {
  color-scheme: dark;
  --bg: #111411;
  --surface: #181d19;
  --surface-2: #20261f;
  --surface-3: #293029;
  --line: #364035;
  --line-strong: #52604f;
  --text: #f3f6ef;
  --muted: #aeb9ad;
  --quiet: #778173;
  --accent: #64d2b4;
  --accent-2: #88b7ff;
  --warn: #e7bd61;
  --bad: #ee7f7a;
  --good: #82d897;
  --shadow: rgba(0, 0, 0, 0.28);
}
```

Do not introduce gradient orbs, bokeh, hero sections, marketing cards, or decorative SVG illustrations.

- [ ] **Step 2: Add stable layout classes**

Ensure these classes exist in `styles.css` for helper2 to wire:

```css
.opsShell {
  min-height: 100vh;
  display: grid;
  grid-template-columns: 248px minmax(0, 1fr);
  background: var(--bg);
  color: var(--text);
}

.opsMain {
  min-width: 0;
  display: grid;
  grid-template-rows: auto minmax(0, 1fr);
}

.opsTopBar {
  min-height: 86px;
  display: grid;
  grid-template-columns: minmax(220px, 1fr) repeat(4, minmax(120px, 160px)) auto;
  gap: 10px;
  align-items: center;
  border-bottom: 1px solid var(--line);
  padding: 16px;
}

.opsGrid {
  min-height: 0;
  display: grid;
  grid-template-columns: minmax(250px, 320px) minmax(420px, 1fr) minmax(300px, 380px);
  gap: 12px;
  padding: 12px 16px 16px;
}

.missionSurface,
.agentDock,
.inspectorPanel,
.eventConsole,
.gateCenter,
.artifactShelf,
.runGraphPanel {
  min-width: 0;
  border: 1px solid var(--line);
  border-radius: 8px;
  background: var(--surface);
  box-shadow: 0 12px 32px var(--shadow);
}
```

- [ ] **Step 3: Add responsive behavior**

Add:

```css
@media (max-width: 980px) {
  .opsShell {
    grid-template-columns: 1fr;
  }

  .sidebar {
    position: static;
    min-height: auto;
  }

  .opsTopBar,
  .opsGrid {
    grid-template-columns: 1fr;
  }

  .composerForm,
  .composerContext {
    grid-template-columns: 1fr;
  }
}
```

- [ ] **Step 4: Create QA checklist**

Create `coordination/frontend-optimization-qa-checklist.md`:

```md
# Frontend Optimization QA Checklist

Controller/QA: `runtime-helper-1`

## Required Checks

- [ ] `frontend npm run build` passes.
- [ ] Browser desktop check at `http://127.0.0.1:8787/` has no console errors.
- [ ] Browser mobile-width check has no overlapping text or clipped controls.
- [ ] Chinese UI labels are visible for navigation, top metrics, task lanes, gates, inspector, event console, and command composer.
- [ ] Terms `worker`, `helper`, `QA`, `Agent`, `Agent Bus`, and `RunGraph` remain understandable.
- [ ] BUG-2 agent-only routing is preserved.
- [ ] Stale/degraded agents do not read as healthy ready.
- [ ] No mock data or placeholder cards are present.
```

- [ ] **Step 5: Report**

Post:

```text
FRONTEND_F1_WORKER4_READY
Files changed: frontend/src/styles.css, coordination/frontend-optimization-qa-checklist.md
Verification: npm run build passed or waiting for helper2 App wiring if classes are unused
```

### Task 3: Operations Room Layout Wiring

Owner: `runtime-helper-2`

Depends on Task 1. Coordinate with Worker4 before broad CSS edits.

**Files:**

- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/styles.css` only for component-specific gaps.
- Modify: `frontend/package.json` and `frontend/package-lock.json`

- [ ] **Step 1: Install icon dependency**

Run:

```powershell
Set-Location 'C:\Users\laptopofzy\Documents\Agent bus\frontend'
npm install lucide-react
```

Expected file changes:

```text
frontend/package.json
frontend/package-lock.json
```

Allowed imports:

```ts
import {
  Activity,
  Boxes,
  GitBranch,
  ListChecks,
  Radio,
  RefreshCw,
  Send,
  ShieldCheck,
  TerminalSquare,
} from "lucide-react";
```

- [ ] **Step 2: Wire view model and Chinese labels**

Modify the top of `frontend/src/App.tsx`:

```ts
import { buildOperationsRoomModel } from "./operationsRoomModel";
import { stateLabel, uiText, viewLabels } from "./uiText";
```

Inside `App()` after filters:

```ts
const room = useMemo(
  () => buildOperationsRoomModel(projection),
  [projection],
);
```

Keep the existing `submitInterrupt(message, targetAgent, includeSelectedTask)` behavior from Round2.

- [ ] **Step 3: Replace shell class names and labels**

Change:

```tsx
<main className="shell">
```

to:

```tsx
<main className="opsShell">
```

Change sidebar copy to:

```tsx
<h1>{uiText.appTitle}</h1>
<p>{uiText.appSubtitle}</p>
```

Render nav labels with:

```tsx
{viewLabels[view]}
```

- [ ] **Step 4: Reframe top health bar**

Update `TopHealthBar` display text:

```tsx
<span>{uiText.roomEyebrow}</span>
<h2>{uiText.roomTitle}</h2>
<p>同步 {lastLoadedAt || "等待中"}</p>
```

Metric labels:

```tsx
<Metric label={uiText.metrics.agents} value={metrics.agentCount} tone="good" />
<Metric label={uiText.metrics.pendingInbox} value={metrics.pendingInbox} tone="warn" />
<Metric label={uiText.metrics.openGates} value={metrics.openGateCount} tone="warn" />
<Metric label={uiText.metrics.contextFaults} value={metrics.contextFaults} tone="bad" />
```

- [ ] **Step 5: Rework main layout into Agent Dock, Mission Surface, Inspector**

Use these props in `ConsoleView`:

```ts
room: OperationsRoomModel;
```

The Operations view should render:

```tsx
<section className="opsGrid">
  <AgentDock agents={[...room.aliveAgents, ...room.degradedAgents]} onSelectAgent={onSelectAgent} />
  <MissionSurface
    gates={filteredGates}
    onSelectTask={onSelectTask}
    tasks={room.taskLanes}
  />
  <section className="rightRail">
    <Inspector agent={selectedAgent} task={selectedTask} />
    <CommandComposer
      agents={projection.agents}
      commandStatus={commandStatus}
      onSubmit={onSubmitInterrupt}
      selectedTask={selectedTask}
    />
  </section>
</section>
```

Use `TaskBoard` as the initial `MissionSurface` implementation if a rename would create too much churn. The visible labels must be Chinese.

- [ ] **Step 6: Preserve Command Composer BUG-2 behavior**

Keep these conditions:

```ts
const targetDiffersFromTask = Boolean(
  targetAgent && selectedTask?.owner && targetAgent !== selectedTask.owner,
);

useEffect(() => {
  setIncludeSelectedTask(!targetDiffersFromTask);
}, [selectedTask?.id, targetDiffersFromTask]);
```

The outgoing payload must keep:

```ts
payload: {
  source: "operations-console",
  routing_mode: taskContext ? "task-context" : "agent-only",
  selected_task_id: selectedTask?.id,
  include_selected_task: Boolean(taskContext),
}
```

- [ ] **Step 7: Verify**

Run:

```powershell
Set-Location 'C:\Users\laptopofzy\Documents\Agent bus\frontend'
npm run build
```

Expected:

```text
vite build
built in
```

- [ ] **Step 8: Report**

Post:

```text
FRONTEND_F2_HELPER2_READY
Files changed: frontend/src/App.tsx, optional frontend/src/styles.css, optional package files
Verification: npm run build passed
BUG-2 routing: preserved
```

### Task 4: Visual Polish, Chinese Copy, And Responsive Pass

Owner: `runtime-worker-4`

Depends on Task 3 App wiring.

**Files:**

- Modify: `frontend/src/styles.css`
- Review: `frontend/src/App.tsx`
- Review: `frontend/src/uiText.ts`
- Modify: `coordination/frontend-optimization-qa-checklist.md`

- [ ] **Step 1: Polish Agent Dock**

Add CSS that keeps Agent cards stable:

```css
.agentCard {
  min-height: 104px;
  display: grid;
  gap: 8px;
  border: 1px solid var(--line);
  border-radius: 8px;
  padding: 12px;
  background: var(--surface-2);
}

.agentCard[data-presence="degraded"],
.agentCard[data-presence="lost"] {
  border-color: rgba(238, 127, 122, 0.5);
}
```

- [ ] **Step 2: Polish Mission Surface**

Add:

```css
.missionLanes {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 10px;
}

.missionLane {
  min-height: 240px;
  border: 1px solid var(--line);
  border-radius: 8px;
  background: var(--surface-2);
}
```

- [ ] **Step 3: Polish Event Console**

The event console should feel trace-like:

```css
.eventConsoleList {
  max-height: 360px;
  overflow: auto;
  font-family: "Cascadia Mono", "SFMono-Regular", Consolas, monospace;
}
```

- [ ] **Step 4: Check Chinese copy**

Scan visible strings in `frontend/src/App.tsx` and `frontend/src/uiText.ts`. Replace user-facing English labels with Chinese except approved terms. Examples:

```text
Runtime overview -> 运行态势
Pending inbox -> 待处理 inbox
Open gates -> 开放门禁
Context faults -> 上下文风险
No tasks. -> 暂无任务
No replacement recommendations. -> 暂无接管建议
Interrupt message -> 中断内容
```

- [ ] **Step 5: Verify build**

Run:

```powershell
Set-Location 'C:\Users\laptopofzy\Documents\Agent bus\frontend'
npm run build
```

- [ ] **Step 6: Report**

Post:

```text
FRONTEND_F3_WORKER4_READY
Files changed: frontend/src/styles.css, coordination/frontend-optimization-qa-checklist.md
Verification: npm run build passed
Copy check: Chinese-first UI reviewed
```

### Task 5: Controller QA Gate

Owner: `runtime-helper-1`

Depends on Tasks 1-4.

**Files:**

- Modify: `coordination/frontend-optimization-qa-checklist.md`
- No product-code edits unless a blocking issue is explicitly assigned to helper1.

- [ ] **Step 1: Run build**

Run:

```powershell
Set-Location 'C:\Users\laptopofzy\Documents\Agent bus\frontend'
npm run build
```

Expected exit code: `0`.

- [ ] **Step 2: Restart or refresh live service if static output or backend route changed**

If the service is already serving updated `frontend/dist`, refresh the Browser page. If not, restart the service on `127.0.0.1:8787` using the existing live DB.

Expected live URL:

```text
http://127.0.0.1:8787/
```

- [ ] **Step 3: Browser desktop QA**

Use Browser at 1280x720:

Checks:

```text
No console errors.
Top health bar visible.
Navigation labels are Chinese-first.
Agent Dock separates ready and degraded states clearly.
runtime-qa does not appear healthy ready.
Mission Surface has active/attention/backlog lanes.
Command Composer shows selected task, include task context, routing mode, target Agent, and send action.
```

- [ ] **Step 4: Browser mobile-width QA**

Use Browser viewport around 390x844:

Checks:

```text
No horizontal incoherent overlap.
Buttons and chips do not clip text.
Agent cards remain readable.
Command Composer controls stack.
Mission lanes stack vertically.
```

- [ ] **Step 5: BUG-2 regression smoke**

Create an agent-only interrupt with a selected task whose owner differs from the target Agent.

Expected event payload:

```json
{
  "task_id": null,
  "routing_mode": "agent-only",
  "include_selected_task": false
}
```

Expected affected agents:

```text
controller, observer, explicit target, qa
```

The unrelated selected-task owner must not receive the interrupt.

- [ ] **Step 6: Gate decision**

Approve the frontend gate only when:

```text
npm run build passes.
Browser desktop passes.
Browser mobile passes.
No console errors.
Chinese-first copy is present.
No mock data or placeholder-only UI.
BUG-2 routing regression passes.
```

Reject or hold the gate if any item fails, and assign the fix back to the owner of the touched file.

## Serial And Parallel Order

```text
F0 helper1 kickoff
  |
  +-- F1A worker1: uiText + operationsRoomModel
  +-- F1B worker4: CSS tokens + QA checklist
  |
F2 helper2: App layout wiring, depends on F1A and uses F1B classes
  |
F3 worker4: visual/copy/responsive polish, depends on F2
  |
F4 helper1: QA gate and Browser checks
```

## Risk Controls

- `frontend/src/App.tsx` is owned by `runtime-helper-2` during implementation to avoid merge churn.
- `frontend/src/styles.css` is owned by `runtime-worker-4`, except helper2 may add small component-specific selectors and must announce them.
- `frontend/src/operationsRoomModel.ts` and `frontend/src/uiText.ts` are owned by `runtime-worker-1` until Task 1 completion.
- Any change to Command Composer routing requires explicit QA regression because it previously caused real misrouting.
- Any new dependency must be justified by visible UI value and verified through `npm run build`.

## Completion Evidence Required

Each worker report must include:

```text
Task id:
Files changed:
Commands run:
Result:
Screenshots or artifact paths if visual:
Known risks:
```

Final helper1 QA report must include:

```text
Build result:
Desktop Browser result:
Mobile Browser result:
Console logs:
BUG-2 regression result:
Gate decision:
```
