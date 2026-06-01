# Blue White Operations Room Refinement Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the remaining gray-green engineering prototype feel with a blue-white Agent Operations Room that follows the user's exact UI patch list.

**Architecture:** Keep backend APIs and protocol payloads unchanged. Worker1 updates the view model and labels so the UI can hide `unknown` fields, show five task lanes, and expose operator-ready summaries. Worker4 owns visual tokens, light theme, panel/card CSS, and final screenshot polish. Helper2 wires App structure and component copy. Helper1 remains controller/QA.

**Tech Stack:** React 19, TypeScript, Vite, lucide-react, existing operations projection API, live service at `http://127.0.0.1:8787/`.

---

## User-Locked Direction

Do not continue the dark/green design. This round implements the user's explicit direction:

- Main app background `#f6f8fb`
- Main panels `#ffffff`
- Sidebar `#0b1220`
- Active nav `#1d4ed8`
- Primary text `#0f172a`
- Secondary text `#64748b`
- Borders `#e2e8f0`
- Running blue `#2563eb`
- Healthy/completed green `#16a34a`
- Gate/waiting amber `#d97706`
- Error red `#dc2626`
- Review/handoff purple `#7c3aed`

## Active Agents

- `runtime-worker-1`: model, labels, source regression
- `runtime-worker-4`: CSS/theme, visual polish
- `runtime-helper-2`: App wiring
- `runtime-helper-1`: controller and QA

## Controller Amendment

At 2026-05-28T17:58:45+08:00, `runtime-worker-4` had not ACKed BW-2 after a final health ping and remained `SUSPECTED_STUCK`. Helper1 failed the original BW-2 task and created takeover task `task_24e7df61f3124e44b0ed5b805f2bec31` for `runtime-helper-2`. Helper2 must complete CSS foundation first, then continue with BW-3 App wiring.

## Controller Amendment 2

At 2026-05-28T18:18:20+08:00, the user added `用户首屏.png` and clarified that the first screen should be a lighter Home / `控制首页` page matching that reference. The current dense `总览` should move into the sidebar for on-demand use. BW-3 must add a new default `Home` view above `Operations`, then keep the dense Operations overview as `总览`.

## Files

- Modify `frontend/src/operationsApi.ts`
- Modify `frontend/src/operationsRoomModel.ts`
- Modify `frontend/src/uiText.ts`
- Modify `frontend/src/App.tsx`
- Modify `frontend/src/styles.css`
- Modify `coordination/frontend-optimization-qa-checklist.md`
- Create `coordination/blue-white-operations-room-qa-artifact.json`
- Create `coordination/blue-white-operations-room-after.png`

## Non-Goals

- Do not modify backend.
- Do not change `/api/interrupt`.
- Do not remove `routing_mode` or `include_selected_task`.
- Do not reintroduce gray-green as the dominant theme.
- Do not show `unknown` or `none` as primary UI content.
- Do not display full run/session/task IDs in primary cards.

## Batch 1

### Task 1: Worker1 Model And Label Patch

**Assignee:** `runtime-worker-1`

**Files:**
- Modify: `frontend/src/operationsRoomModel.ts`
- Modify: `frontend/src/uiText.ts`

- [ ] **Step 1: Add five lane model**

Replace or extend the existing decision lane logic with:

```ts
export type DecisionLane =
  | "needsAction"
  | "active"
  | "waitingGate"
  | "review"
  | "done";
```

Mapping:

- failed, blocked, changes requested, context lost -> `needsAction`
- working, assigned, acknowledged, in progress -> `active`
- gate, pending, waiting approval -> `waitingGate`
- review, qa, ready -> `review`
- completed, approved, passed, done -> `done`

- [ ] **Step 2: Add display helpers**

Add pure helpers:

```ts
export function shortId(value: string, head = 8): string {
  if (!value || value === "unknown" || value === "none") return "";
  if (value.length <= head + 1) return value;
  return `${value.slice(0, head)}…`;
}

export function displayOrEmpty(value: string): string {
  if (!value || value === "unknown" || value === "none") return "";
  return value;
}
```

Use these helpers in task/workstation models so primary UI can hide `unknown`.

- [ ] **Step 3: Add task progress and next action**

Extend `TaskCardModel`:

```ts
progress: number;
nextAction: string;
shortTaskId: string;
shortRunId: string;
ownerText: string;
```

Use deterministic state-based progress:

- failed/blocked: 0
- assigned/acknowledged: 30
- working/in progress: 70
- review/ready: 85
- completed/approved/passed: 100
- fallback: 0

Next action examples:

- failed: `定位、复查或重新分派`
- working: `继续执行并上传证据`
- acknowledged/assigned: `开始执行`
- review/ready: `查看证据并审查`
- completed: `归档`
- fallback: `等待更新`

- [ ] **Step 4: Add run display**

Expose `activeRunLabel` and `activeRunMeta` in `OperationsBrief` or `OperationsRoomModel`.

Use:

- label: `Live Round 1` when a run exists
- meta: `运行中 · ${active task count} tasks`
- short id available for tooltip/detail, not primary card text

- [ ] **Step 5: Update labels**

In `frontend/src/uiText.ts`, set:

```ts
viewLabels.Agents = "智能体";
viewLabels.RunGraph = "任务流";
uiText.panels.agentDock = "智能体工作台";
uiText.panels.inspector = "检查器";
uiText.panels.eventConsole = "事件控制台";
```

Decision lane labels:

```ts
needsAction: "需处理",
active: "进行中",
waitingGate: "等待门禁",
review: "审查中",
done: "已完成",
```

Alert action label:

```ts
handleIncident: "处理异常任务"
```

- [ ] **Step 6: Build**

Run:

```powershell
npm run build
```

Expected: exit code 0; lucide-react `"use client"` warnings are acceptable.

### Task 2: Worker4 Blue White Theme Foundation

**Assignee:** `runtime-worker-4`

**Files:**
- Modify: `frontend/src/styles.css`

- [ ] **Step 1: Replace global tokens**

Replace `:root` color tokens with the exact blue-white set from user feedback:

```css
--bg: #f6f8fb;
--shell: #ffffff;
--panel: #ffffff;
--panel-soft: #f8fafc;
--panel-elevated: #ffffff;
--sidebar: #0b1220;
--sidebar-soft: #111827;
--sidebar-active: #1d4ed8;
--text: #0f172a;
--text-muted: #64748b;
--text-subtle: #94a3b8;
--text-inverse: #f8fafc;
--border: #e2e8f0;
--border-strong: #cbd5e1;
--blue: #2563eb;
--blue-soft: #eff6ff;
--cyan: #0891b2;
--green: #16a34a;
--amber: #d97706;
--amber-soft: #fff7ed;
--red: #dc2626;
--red-soft: #fef2f2;
--purple: #7c3aed;
--purple-soft: #f5f3ff;
--shadow-sm: 0 1px 2px rgba(15, 23, 42, .06);
--shadow-md: 0 8px 24px rgba(15, 23, 42, .08);
```

- [ ] **Step 2: Style sidebar**

Implement:

- sidebar width 264px
- background `#0b1220`
- active nav item `#1d4ed8`
- inactive hover `#172033`
- nav icon box 32x32
- logo blue gradient, not green outline
- inverse text color in sidebar

- [ ] **Step 3: Add light panel system**

Use:

```css
.panel {
  background: #ffffff;
  border: 1px solid #e2e8f0;
  border-radius: 16px;
  box-shadow: 0 1px 2px rgba(15,23,42,.06);
  overflow: hidden;
}
```

Add `.panelHeader` equivalent rules with 52px height and white/light border.

- [ ] **Step 4: Prepare class styles**

Style these classes for Helper2 wiring:

- `.topStatusBar`
- `.alertBanner`
- `.alertPrimary`
- `.metricCard`
- `.operationsGrid`
- `.agentAvatar`
- `.taskBoard`
- `.taskCard`
- `.gateTabs`
- `.inspectorTabs`
- `.eventTable`
- `.artifactEmptyGrid`
- `.settingsCards`

- [ ] **Step 5: Responsive rules**

Use:

```css
.operationsGrid {
  display: grid;
  grid-template-columns: 360px minmax(560px, 1fr) 400px;
  gap: 16px;
  padding: 16px 20px 0;
}

@media (max-width: 1280px) {
  .operationsGrid {
    grid-template-columns: 360px 1fr;
  }
  .inspectorPanel {
    grid-column: 1 / -1;
  }
}

@media (max-width: 820px) {
  .opsShell,
  .operationsGrid,
  .topStatusBar {
    grid-template-columns: 1fr;
  }
}
```

- [ ] **Step 6: Build**

Run:

```powershell
npm run build
```

Expected: exit code 0.

## Batch 2

### Task 3: Helper2 App Structure Patch

**Assignee:** `runtime-helper-2`

**Files:**
- Modify: `frontend/src/operationsApi.ts`
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/uiText.ts` only for label fixes

- [ ] **Step 0: Add Home route**

Add `Home` to the frontend `ViewName` union in `frontend/src/operationsApi.ts`.

In `frontend/src/App.tsx`, make `Home` the default active view and put it before `Operations` in the `views` array.

Labels:

- `Home`: `控制首页`
- `Operations`: `总览`

- [ ] **Step 1: Home first screen**

Add a new Home page component inspired by `用户首屏.png`.

It must include:

- page title `总览`
- current run subtitle using real run data
- top metric cards
- large current task flow card
- primary action button
- secondary action button when a task can be stopped/interrupted or inspected
- quick cards for needs action, gates/approvals, and recent artifacts/results
- Controller suggestion card based on the current top risk

Use only real projection/model data. Do not copy the screenshot's fake Q2 campaign text.

- [ ] **Step 2: Dense Operations remains side route**

Keep the existing dense Agent Dock/task board/Inspector/Event Console under `Operations` / `总览`. The Home page is the default; `总览` is user-selected from the sidebar.

- [ ] **Step 3: Top area for dense Operations**

Replace the large dark header with:

- `.topStatusBar`, height target 72px
- `.alertBanner`, shown only when `room.brief.primaryAction.tone === "bad"` or `"warn"`
- alert title `需要处理任务异常`
- alert button text `处理异常任务`
- metrics: Agent, pending inbox, open gates, context risk, current run
- refresh button on the right, not full-width

- [ ] **Step 4: Sidebar copy**

Use labels:

- 控制首页
- 总览
- 智能体
- 门禁
- 任务流
- 产物
- 设置

Bottom card:

- 当前任务流
- Live Round 1
- 运行中 · N tasks

Do not show the long run id in the bottom card.

- [ ] **Step 5: Operations grid**

Use class `.operationsGrid`. Keep three panels:

- Agent Dock
- TaskBoard
- Inspector/Gate/Command rail as the right column

If the existing right rail stays, ensure Inspector is first and gate history is visually weaker than open gate.

- [ ] **Step 6: Agent cards**

Render each workstation as a white `agentCard` with:

- `agentAvatar` using lucide icon by role
- full agent id with ellipsis only if needed
- role
- status chip right aligned
- current work one line
- next action one line
- health and confidence progress with percentages
- short session id
- context trust text

Do not show full session id.

- [ ] **Step 7: Task board**

Render five lanes:

- 需处理
- 进行中
- 等待门禁
- 审查中
- 已完成

Each lane header has count badge and semantic color.

Task cards show:

- title
- state chip
- owner chip or `未分配`
- short task id
- progress label and bar
- next action
- short run id

Never render `unknown` or `none` as primary content.

- [ ] **Step 8: Gates**

Default gate filter to open. Add tabs:

- 开放
- 高风险
- 已处理
- 全部

Approved/rejected gates must not dominate Operations by default.

- [ ] **Step 9: Inspector**

Rename to `检查器`. Add tabs:

- 概览
- 上下文
- 事件
- 操作

Empty state:

```txt
选择一个 Agent、任务、门禁或事件，查看上下文、证据和下一步操作。
```

Do not display `none` or `unknown` as main content.

- [ ] **Step 10: Event Console**

Render a white structured table with columns:

- 时间
- 类型
- Actor
- Target
- 摘要

Use segmented filters:

- 全部
- 门禁
- 中断
- 接警
- 异常

- [ ] **Step 11: RunGraph, Artifacts, Settings**

If no real graph exists, rename RunGraph route/page title to `任务流列表`.

Artifacts page empty state cards:

- 截图
- 报告
- 日志

Settings page cards:

- 投影源
- 显示偏好
- 调试信息

Debug info should be visually weak.

- [ ] **Step 12: Preserve BUG-2**

Confirm the payload still contains:

```ts
routing_mode: taskContext ? "task-context" : "agent-only",
include_selected_task: Boolean(taskContext),
```

- [ ] **Step 13: Build**

Run:

```powershell
npm run build
```

Expected: exit code 0.

## Batch 3

### Task 4: Worker4 Visual Polish And Screenshot

**Assignee:** `runtime-worker-4`

**Files:**
- Modify: `frontend/src/styles.css`
- Modify: `coordination/frontend-optimization-qa-checklist.md`
- Create: `coordination/blue-white-worker4-polish.png`

- [ ] **Step 1: Open app**

Open:

```txt
http://127.0.0.1:8787/
```

- [ ] **Step 2: Polish only CSS**

Fix only visual issues:

- gray-green remnants
- over-tall header
- full-width refresh button
- text clipping
- equal-weight borders
- panel spacing
- mobile overflow

Do not change `App.tsx`.

- [ ] **Step 3: Capture screenshot**

Save screenshot:

```txt
coordination/blue-white-worker4-polish.png
```

- [ ] **Step 4: Build**

Run:

```powershell
npm run build
```

Expected: exit code 0.

### Task 5: Worker1 Source Regression

**Assignee:** `runtime-worker-1`

**Files:**
- Read: `frontend/src/App.tsx`
- Read: `frontend/src/operationsRoomModel.ts`
- Read: `frontend/src/uiText.ts`
- Modify: `coordination/frontend-optimization-qa-checklist.md`

- [ ] **Step 1: Check source requirements**

Confirm:

- no `unknown` or `none` is rendered as primary content
- five task lanes exist
- BUG-2 payload fields preserved
- route labels are Chinese-first
- run/session/task IDs are short in primary cards
- no fake data was introduced

- [ ] **Step 2: Build**

Run:

```powershell
npm run build
```

Expected: exit code 0.

## Final QA

### Task 6: Helper1 QA Gate

**Assignee:** `runtime-helper-1`

**Files:**
- Create: `coordination/blue-white-operations-room-after.png`
- Create: `coordination/blue-white-operations-room-qa-artifact.json`
- Modify: `coordination/frontend-optimization-qa-checklist.md`

- [ ] **Step 1: Build**

Run:

```powershell
npm run build
```

- [ ] **Step 2: Browser desktop QA**

At 1280x720 verify:

- no console errors/warnings
- no horizontal overflow
- page background is light `#f6f8fb`
- sidebar is navy `#0b1220`
- panels are white
- top alert banner is red/soft-red when abnormal
- metrics are white cards
- task lanes are five columns or controlled horizontal scroll
- no visible primary `unknown` / `none`
- BUG-2 checkbox and payload behavior remain visible/source-preserved

- [ ] **Step 3: Browser mobile QA**

At 390x844 verify:

- no horizontal body overflow
- nav/header/cards do not overlap
- alert and metrics remain readable
- command composer controls still fit

- [ ] **Step 4: UX review**

Repeat the 10-second test. Pass only if a user can identify:

- whether system is abnormal
- which task needs handling
- which Agents are working
- which gate needs attention
- where to click first

- [ ] **Step 5: Gate decision**

Approve only if the blue-white patch clearly replaces the gray-green engineering prototype and all technical regressions pass.

## Self-Review

- Covers all 12 "one-eye improvement" requirements from user feedback.
- Keeps backend and BUG-2 payload unchanged.
- Assigns only worker1, worker4, helper2 for implementation.
- Helper1 remains controller and QA.
