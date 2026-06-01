# Agent Bus Reference Visual Layout Fix Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Restyle the Agent Bus frontend to match the five user-provided 2026-05-29 reference screenshots while preserving real Agent Bus backend data and runtime APIs.

**Architecture:** Keep the existing SQLite/FastAPI/React data contracts intact. Convert the current light-but-rough interface into a reference-matched operations console by tightening the app shell, shared design tokens, page headers, and page-specific layouts for Home, Communication, Runs, Gates, Artifacts, Diagnostics, and Settings. Work in serial QA-gated waves so shared CSS/chrome changes land before page-level redesigns.

**Tech Stack:** React 19, TypeScript, Vite, lucide-react, existing `agent_bus` FastAPI APIs, existing `/api/projections/*` and `/api/messages/send` endpoints, Codex in-app browser screenshots.

---

## User References

Reference image directory:

```text
C:\Users\laptopofzy\Documents\Agent bus\5-29
```

Files:

- `首页.png`: target Home layout with clean sidebar, top sync toolbar, numbered sections, run posture summary, task metro map, and five-card action queue.
- `通信.png`: target Communication layout with left spaces and agent list, central message feed with filters and sticky composer, and right detail rail.
- `任务流.png`: target Runs layout with left run list, top run summary, agent assignment cards, task track, gate/artifact/event lanes.
- `门禁.png`: target Gates layout with tabs, left gate queue, right decision detail, risk badges, facts, timeline/decision tabs, and four visible action buttons.
- `产物.png`: target Artifacts layout with tabs, metric strip, artifact list, selected artifact preview/detail/actions.

## Current UX Findings From Gate C Screenshots

Current screenshots:

- `coordination/gate-c-final-home-initial-1280x720.png`
- `coordination/gate-c-final-communication-after-controls-1280x720.png`
- `coordination/gate-c-final-runs-after-controls-1280x720.png`
- `coordination/gate-c-final-gates-after-controls-1280x720.png`
- `coordination/gate-c-final-artifacts-after-controls-1280x720.png`

Top operator-impact failures:

1. Home has oversized icon blocks, weak hierarchy, and a stacked lane board that reads like debug output instead of the reference task metro.
2. Several visible strings still render as `?????` or mojibake in current screenshots and source output. This must be fixed as user-facing copy, not hidden with CSS.
3. Communication currently shows a narrow list squeezed into the middle of the screen; it lacks reference-like filters, spatial grouping, and right-side message detail prominence.
4. Runs and Gates expose raw rows and large text instead of compact summary cards, structured lanes, and obvious decision hierarchy.
5. Artifacts page looks empty and unfinished when real manifests are absent. Empty states must still match the reference style without inventing fake data.

## Non-Goals

- Do not change backend storage, event replay, wait/ack/context APIs, replacement logic, or message send semantics.
- Do not add fake metrics, fake screenshots, or demo records to make the UI look populated.
- Do not embed the reference images in the app.
- Do not reintroduce hidden confidence/trust/conversation-internal scoring into normal UI.
- Do not restart the product restructure from scratch; preserve existing page split and real data adapters.

## Design Contract

All implementation tasks must obey these rules:

- App shell: white sidebar, subtle right border, `AB` gradient brand block, active nav blue pill, bottom active-run card, bottom account/controller block.
- Main canvas: `#f6f8fb` or equivalent pale blue-gray background, white panels, 8px radius, low shadow, 16-24px gutters.
- Page header: each page gets Chinese title, short explanatory subtitle, and top-right sync/refresh controls where applicable.
- Primary blue: use a single action blue close to `#2563eb`; avoid dark slate sidebar and green/brown dominant palettes.
- Status colors: green complete/healthy, blue running/active, amber waiting/gate, red failed/rejected/fault, purple review/escalation, gray inactive/not-started.
- Typography: compact, no viewport-based font scaling, no negative letter spacing, long IDs shortened in primary cards.
- Data: every count and row must come from existing projections or client-normalized real data. If data is absent, render a polished empty state with next location/instruction.
- Accessibility: visible focus ring, button labels, icon+text for non-obvious actions, no overlapping text at 1280x720 or narrow viewport.
- Browser evidence: every page in the reference set plus Diagnostics and Settings must have desktop screenshots; worker4 must also capture at least Home and Communication in a narrow viewport.

## Encoding Safety Note

Some PowerShell reads may display Chinese text from this plan as mojibake. The authoritative visible-copy requirement is clean Chinese in the browser. If an implementation tool corrupts Chinese literals, use TypeScript Unicode escape strings for these labels:

```ts
export const cleanViewLabels = {
  Home: "\u63a7\u5236\u9996\u9875",
  Communication: "\u901a\u4fe1",
  Runs: "\u4efb\u52a1\u6d41",
  Gates: "\u95e8\u7981",
  Artifacts: "\u4ea7\u7269",
  Diagnostics: "\u8bca\u65ad",
  Settings: "\u8bbe\u7f6e",
};

export const cleanToolbarLabels = {
  syncStatus: "\u540c\u6b65\u72b6\u6001",
  autoRefresh: "\u81ea\u52a8\u5237\u65b0\uff1a30\u79d2",
  lastSync: "\u4e0a\u6b21\u540c\u6b65\uff1a",
  waitingSync: "\u7b49\u5f85\u540c\u6b65",
};
```

Gate 1 fails if the browser still shows `????`, `???`, or mojibake in primary navigation, toolbar, Home summary, or the sidebar active-run card.

## File Ownership

Online implementation agents:

- `runtime-helper-1`: App shell, Home page, Chinese copy cleanup, page-header integration.
- `runtime-helper-2`: Communication and Gates page structure, DetailRail/ActionDrawer detail behavior.
- `runtime-worker-4`: Visual tokens, shared CSS, shared visual components, Runs/Artifacts/Diagnostics/Settings page polish, responsive screenshots.
- `runtime-qa`: serial gatekeeper only; writes plan/coordination artifacts, runs independent verification, opens fixback scopes only when findings are concrete.

Offline agents:

- `runtime-worker-1`, `runtime-worker-2`, and `runtime-worker-3` are not assigned implementation work in this plan. They may receive broadcast mirrors only.

## Wave Protocol

No agent may start the next wave until runtime-qa broadcasts the gate pass for the current wave.

Ready tokens:

- Wave 1:
  - `VISUAL_LAYOUT_WAVE1_SHELL_READY runtime-helper-1`
  - `VISUAL_LAYOUT_WAVE1_FOUNDATION_READY runtime-worker-4`
- Wave 2:
  - `VISUAL_LAYOUT_WAVE2_HOME_READY runtime-helper-1`
  - `VISUAL_LAYOUT_WAVE2_COMM_GATES_READY runtime-helper-2`
  - `VISUAL_LAYOUT_WAVE2_RUNS_ARTIFACTS_READY runtime-worker-4`
- Wave 3:
  - `VISUAL_LAYOUT_WAVE3_FIXBACK_READY <agent>`
- Gate broadcasts:
  - `GATE_VISUAL_LAYOUT_WAVE1_PASS` / `GATE_VISUAL_LAYOUT_WAVE1_FAIL`
  - `GATE_VISUAL_LAYOUT_WAVE2_PASS` / `GATE_VISUAL_LAYOUT_WAVE2_FAIL`
  - `GATE_VISUAL_LAYOUT_FINAL_PASS` / `GATE_VISUAL_LAYOUT_FINAL_FAIL`

Every READY message must include files changed, screenshots, commands run, and unresolved risks.

---

## Wave 1: Visual Foundation And Shell

### Task 1A: App Shell And Global Page Toolbar

Owner: `runtime-helper-1`

**Files:**

- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/uiText.ts`
- Create: `frontend/src/components/PageToolbar.tsx`
- Do not modify: backend files, `frontend/src/pages/CommunicationPage.tsx`, `frontend/src/pages/GatesPage.tsx`, `frontend/src/pages/RunsPage.tsx`, `frontend/src/pages/ArtifactsPage.tsx`, CSS files

- [ ] **Step 1: Announce ownership**

Send:

```text
VISUAL_LAYOUT_WAVE1_SHELL_SCOPE runtime-helper-1 owns App.tsx, uiText.ts, and optional PageToolbar.tsx for shell/page toolbar only.
```

- [ ] **Step 2: Normalize app shell labels**

Ensure `viewLabels` include exactly these visible nav labels:

```ts
export const viewLabels = {
  Home: "控制首页",
  Communication: "通信",
  Runs: "任务流",
  Gates: "门禁",
  Artifacts: "产物",
  Diagnostics: "诊断",
  Settings: "设置",
} as Record<ViewName, string>;
```

Expected source scan:

```powershell
Select-String -Path frontend\src\uiText.ts -Pattern '控制首页','通信','任务流','门禁','产物','诊断','设置' -SimpleMatch
```

- [ ] **Step 3: Add a reusable page toolbar if it reduces duplication**

If `PageToolbar.tsx` is created, use this API:

```tsx
import React from "react";
import { RefreshCw, Clock3 } from "lucide-react";

export type PageToolbarProps = {
  lastLoadedAt: string;
  onRefresh?: () => void;
  refreshLabel?: string;
};

export function PageToolbar({
  lastLoadedAt,
  onRefresh,
  refreshLabel = "自动刷新：30秒",
}: PageToolbarProps) {
  return (
    <div className="pageToolbar" aria-label="同步状态">
      <button className="toolbarButton" onClick={onRefresh} type="button">
        <RefreshCw size={14} strokeWidth={2.2} />
        {refreshLabel}
      </button>
      <span className="toolbarSync">
        <Clock3 size={14} strokeWidth={2.2} />
        上次同步：{lastLoadedAt || "等待同步"}
      </span>
    </div>
  );
}
```

- [ ] **Step 4: Wire toolbar without breaking data refresh**

In `App.tsx`, pass `lastLoadedAt` and `loadProjection` to page layout or render a single top-right toolbar in `.opsMain` above `ConsoleView`. The refresh button must call `loadProjection()` and must not replace existing page-local refresh buttons that fetch messages/artifacts.

Expected source scan:

```powershell
Select-String -Path frontend\src\App.tsx,frontend\src\components\PageToolbar.tsx -Pattern 'lastLoadedAt','loadProjection','pageToolbar','toolbarButton' -SimpleMatch
```

- [ ] **Step 5: Build**

Run:

```powershell
npm --prefix frontend run build
```

Expected: exit 0. Lucide `"use client"` bundle warnings are acceptable.

- [ ] **Step 6: Send READY**

Send `VISUAL_LAYOUT_WAVE1_SHELL_READY runtime-helper-1` with changed files and build result.

### Task 1B: Shared Visual Foundation

Owner: `runtime-worker-4`

**Files:**

- Modify: `frontend/src/styles/base.css`
- Modify: `frontend/src/styles/layout.css`
- Modify: `frontend/src/styles/status.css`
- Modify: `frontend/src/styles.css`
- Do not modify shared component `.tsx` files in Wave 1. Style existing component classes through CSS only.
- Do not modify: `frontend/src/App.tsx`, page `.tsx` files

- [ ] **Step 1: Announce ownership**

Send:

```text
VISUAL_LAYOUT_WAVE1_FOUNDATION_SCOPE runtime-worker-4 owns CSS foundation and shared visual components only.
```

- [ ] **Step 2: Replace dark shell remnants**

Current `styles.css` still contains dark sidebar and old console surfaces. Replace shell/sidebar tokens so the visible app matches the reference:

```css
:root {
  color-scheme: light;
  --bg: #f6f8fb;
  --shell: #ffffff;
  --panel: #ffffff;
  --panel-soft: #f8fafc;
  --border: #e2e8f0;
  --border-strong: #cbd5e1;
  --text: #0f172a;
  --text-muted: #64748b;
  --text-subtle: #94a3b8;
  --blue: #2563eb;
  --blue-soft: #eff6ff;
  --green: #16a34a;
  --amber: #d97706;
  --red: #dc2626;
  --purple: #7c3aed;
  --shadow-sm: 0 1px 2px rgba(15, 23, 42, 0.06);
  --shadow-md: 0 8px 24px rgba(15, 23, 42, 0.08);
}
```

Expected source scan after edit:

```powershell
Select-String -Path frontend\src\styles.css -Pattern 'background: #20221f','background: #20231f','color: #d7ddd4','border-color: #4a524c' -SimpleMatch
```

Expected: no shell/sidebar hits for the old dark palette.

- [ ] **Step 3: Style the reference shell**

Ensure these selectors exist and are visually reference-matched:

```css
.opsShell {
  min-height: 100vh;
  display: grid;
  grid-template-columns: 248px minmax(0, 1fr);
  background: var(--bg);
}

.sidebar {
  background: #ffffff;
  border-right: 1px solid var(--border);
  padding: 20px 16px;
}

.brandMark {
  border-radius: 8px;
  background: linear-gradient(135deg, #3b82f6, #1d4ed8);
  color: #ffffff;
}

.navItem.active {
  background: #eef4ff;
  color: var(--blue);
  border-color: #dbe7ff;
  box-shadow: inset 3px 0 0 var(--blue);
}
```

- [ ] **Step 4: Add shared reference primitives**

Add or refine CSS for:

```css
.pageToolbar
.toolbarButton
.toolbarSync
.metricStrip
.metricTile
.referenceCard
.referenceTabs
.detailPanel
.splitPage
.listDetailPage
.actionBar
```

These may be pure CSS classes first; page tasks will bind markup to them in Wave 2.

- [ ] **Step 5: Build and screenshot shell**

Run:

```powershell
npm --prefix frontend run build
```

Then capture screenshots:

- `coordination/visual-layout-wave1-shell-home.png`
- `coordination/visual-layout-wave1-shell-communication.png`

Use the live app at `http://127.0.0.1:8787`.

- [ ] **Step 6: Send READY**

Send `VISUAL_LAYOUT_WAVE1_FOUNDATION_READY runtime-worker-4` with changed files, build result, and screenshot paths.

### Gate 1: Foundation Acceptance

Owner: `runtime-qa`

QA waits for both Wave 1 READY tokens.

Verification:

```powershell
npm --prefix frontend run build
Select-String -Path frontend\src\styles.css -Pattern 'background: #20221f','background: #20231f','color: #d7ddd4','border-color: #4a524c' -SimpleMatch
```

Browser checks:

- Home loads with white sidebar and readable bottom run card.
- Active nav matches blue reference pill.
- Page toolbar refresh does not throw browser errors.
- No visible `????`, `???`, mojibake, or dark sidebar remnants in first viewport.

Pass broadcast: `GATE_VISUAL_LAYOUT_WAVE1_PASS`.

---

## Wave 2: Reference-Matched Page Layouts

### Task 2A: Home Reference Layout

Owner: `runtime-helper-1`

**Files:**

- Modify: `frontend/src/pages/HomePage.tsx`
- Modify: `frontend/src/uiText.ts`
- Do not modify: `frontend/src/operationsRoomModel.ts` unless runtime-qa opens a separate finding after Wave 2 browser QA
- Do not modify: CSS files, backend files, Communication/Gates/Runs/Artifacts pages

- [ ] **Step 1: Announce ownership**

Send:

```text
VISUAL_LAYOUT_WAVE2_HOME_SCOPE runtime-helper-1 owns HomePage.tsx and Home-only model/copy changes.
```

- [ ] **Step 2: Replace mojibake labels**

Home visible labels must be clean Chinese:

```ts
const laneLabels: Record<DecisionLane, string> = {
  needsAction: "需处理",
  active: "进行中",
  waitingGate: "等门禁",
  waiting: "等待",
  review: "审核中",
  done: "已完成",
};
```

Metric labels:

```tsx
<MetricTile label="当前任务流" ... />
<MetricTile label="运行状态" ... />
<MetricTile label="待处理" ... />
<MetricTile label="开放门禁" ... />
```

Expected screenshot: no `?????` in Home or left run card.

- [ ] **Step 3: Build numbered reference sections**

Home must render three section panels in this order:

1. `当前运行态势`
2. `任务流地铁图`
3. `行动队列`

Use small blue number badges beside section titles:

```tsx
<span className="sectionNumber">1</span>
```

- [ ] **Step 4: Convert the current lane board into a task metro**

Keep real task/gate/artifact data. Do not draw fake nodes.

Render:

- Start node.
- Up to 8 task/gate nodes from active run tasks plus urgent gates.
- Green check for completed, red X for failed/rejected, amber dots for waiting, purple diamond for gate/review, gray circle for not started.
- Secondary branches for related gates when present.

Acceptable implementation can stay in `HomePage.tsx` as pure React helpers:

```tsx
function metroTone(state: string, kind: "task" | "gate" | "artifact") {
  const value = state.toLowerCase();
  if (value.includes("fail") || value.includes("reject") || value.includes("block")) return "bad";
  if (value.includes("complete") || value.includes("done") || value.includes("approved")) return "good";
  if (kind === "gate" || value.includes("wait") || value.includes("open")) return "warn";
  return "info";
}
```

- [ ] **Step 5: Convert action queue to five reference cards**

Each card must show:

- category header color
- title
- one short line of explanation
- status/time line
- primary action button

Primary actions must still call `onOpenAction(item)` or `onViewChange(...)`; do not detach them from Bus-backed drawer behavior.

- [ ] **Step 6: Build**

Run:

```powershell
npm --prefix frontend run build
```

- [ ] **Step 7: Browser smoke**

Capture:

- `coordination/visual-layout-wave2-home.png`

Click:

- first action queue button opens `.actionDrawer`
- drawer submit still calls `/api/messages/send`
- `查看全部行动项` navigates to `Runs`; gate cards navigate/open `Gates`; pending message cards navigate/open `Communication`

- [ ] **Step 8: Send READY**

Send `VISUAL_LAYOUT_WAVE2_HOME_READY runtime-helper-1`.

### Task 2B: Communication And Gates Reference Layout

Owner: `runtime-helper-2`

**Files:**

- Modify: `frontend/src/pages/CommunicationPage.tsx`
- Modify: `frontend/src/pages/GatesPage.tsx`
- Modify: `frontend/src/components/DetailRail.tsx`
- Modify: `frontend/src/components/ActionDrawer.tsx`
- Do not modify: `frontend/src/App.tsx`, backend files, CSS files unless runtime-qa reroutes a class-name mismatch

- [ ] **Step 1: Announce ownership**

Send:

```text
VISUAL_LAYOUT_WAVE2_COMM_GATES_SCOPE runtime-helper-2 owns CommunicationPage, GatesPage, DetailRail/ActionDrawer detail behavior.
```

- [ ] **Step 2: Communication layout**

Restructure Communication to match reference:

- Left column:
  - `通信空间`
  - group buttons: `紧急异常`, `日常协作`, `发布变更`, `成本优化`
  - `Agent 列表` below, using real `projection.agents`
- Center column:
  - filter chips: `全部`, `仅我发送`, `@我的`, `关注的 Agent`
  - unread toggle
  - search input placeholder `搜索消息、Agent、Run、Gate...`
  - message cards with sender, recipient, message type, delivery badge, time, context chips
  - composer pinned at bottom
- Right column:
  - top primary button `发送指令`
  - tabs `消息详情` and `Agent 详情`
  - selected message facts and links
  - message track using delivery/ack states

The composer must still call `sendBusMessage()`.

- [ ] **Step 3: Gates layout**

Restructure Gates to match reference:

- Header title: `审批中心`
- Subtitle: `只显示需要决策的门禁`
- Tabs/counters: waiting, all, rejected, escalated
- Left queue: gate cards with run/task/owner/requester/decision owner/risk/reason
- Right detail: selected gate title, state badge, risk badge, fact strip, tabs `门禁详情`, `时间线`, `决策记录`
- Decision area: text reason box and four action buttons:
  - `通过`
  - `驳回`
  - `请求补充信息`
  - `升级给 QA/Controller`

Buttons may be visually enabled but must not perform backend gate mutation until a real API exists. They may open the Bus-backed `ActionDrawer` or show a clear local status line that says the action is routed through Agent Bus when submitted.

- [ ] **Step 4: Remove mojibake in these pages**

Run:

```powershell
Select-String -Path frontend\src\pages\CommunicationPage.tsx,frontend\src\pages\GatesPage.tsx,frontend\src\components\DetailRail.tsx -Pattern '閫','鏆','浠','娑','璇','????','???' -SimpleMatch
```

Expected: no visible-copy hits. Technical identifiers may remain only if they are not rendered.

- [ ] **Step 5: Build**

Run:

```powershell
npm --prefix frontend run build
```

- [ ] **Step 6: Browser smoke**

Capture:

- `coordination/visual-layout-wave2-communication.png`
- `coordination/visual-layout-wave2-gates.png`

Click:

- Communication refresh
- first space/group
- first agent
- first message
- composer select/fill/send
- Gates tab chips
- first gate card
- each visible decision action button opens a safe Bus-backed route/status without console errors

- [ ] **Step 7: Send READY**

Send `VISUAL_LAYOUT_WAVE2_COMM_GATES_READY runtime-helper-2`.

### Task 2C: Runs, Artifacts, Diagnostics, Settings, And Responsive Polish

Owner: `runtime-worker-4`

**Files:**

- Modify: `frontend/src/pages/RunsPage.tsx`
- Modify: `frontend/src/pages/ArtifactsPage.tsx`
- Modify: `frontend/src/pages/DiagnosticsPage.tsx`
- Do not modify: `frontend/src/App.tsx`. If Settings markup needs more than CSS polish, runtime-qa will route a separate helper1 fixback.
- Modify: CSS files already owned by worker4 from Wave 1
- Do not modify: Communication/Home/Gates pages unless runtime-qa reroutes

- [ ] **Step 1: Announce ownership**

Send:

```text
VISUAL_LAYOUT_WAVE2_RUNS_ARTIFACTS_SCOPE runtime-worker-4 owns Runs, Artifacts, Diagnostics, Settings polish, and responsive CSS support.
```

- [ ] **Step 2: Runs page reference layout**

Match `任务流.png`:

- Left run list with selected run blue border and progress bar.
- Top run summary fact strip: objective, status, owner/controller, start time, last update.
- Agent assignment cards grouped by Controller, Workers, QA, Helpers from real `projection.agents`.
- Task track row with numbered cards from real run tasks.
- Bottom lanes: gate track, artifact track, event timeline.
- Keep raw full IDs out of primary titles; use `IdChip` for short IDs.

- [ ] **Step 3: Artifacts page reference layout**

Match `产物.png`:

- Tabs: `全部`, `截图`, `报告`, `日志`, `交接`.
- Metric strip: manifest artifacts, durable records, today added.
- Left artifact list with type icon, title, run/task/agent chips, time, size if available.
- Right selected artifact panel with title, type badge, actions `下载`, `打开目录`, overflow menu, preview area when image path is available, description, links, next actions.
- If no manifests exist, show a polished empty list and a right empty-detail panel; do not fake rows.

- [ ] **Step 4: Diagnostics and Settings consistency**

Diagnostics and Settings must inherit the same reference chrome:

- page header with subtitle
- white panels
- compact metrics
- no dark sidebar remnants
- no mojibake

- [ ] **Step 5: Responsive rules**

Add CSS so:

- Desktop 1280x720 has no horizontal body overflow.
- At `max-width: 1100px`, list/detail layouts stack.
- At `max-width: 720px`, sidebar can stack above content or compress without text overlap.
- Home task metro scrolls horizontally inside its panel rather than forcing body overflow.

- [ ] **Step 6: Build**

Run:

```powershell
npm --prefix frontend run build
```

- [ ] **Step 7: Browser smoke**

Capture:

- `coordination/visual-layout-wave2-runs.png`
- `coordination/visual-layout-wave2-artifacts.png`
- `coordination/visual-layout-wave2-diagnostics.png`
- `coordination/visual-layout-wave2-settings.png`
- `coordination/visual-layout-wave2-home-narrow.png`
- `coordination/visual-layout-wave2-communication-narrow.png`

Click:

- Runs run selector
- Artifacts tabs and refresh
- Diagnostics segment buttons
- Settings visible controls

- [ ] **Step 8: Send READY**

Send `VISUAL_LAYOUT_WAVE2_RUNS_ARTIFACTS_READY runtime-worker-4`.

### Gate 2: Page-Level Acceptance

Owner: `runtime-qa`

QA waits for all Wave 2 READY tokens.

Commands:

```powershell
npm --prefix frontend run build
pytest -q
```

Browser checks on `http://127.0.0.1:8787`:

- Seven routes render without blank screens: Home, Communication, Runs, Gates, Artifacts, Diagnostics, Settings.
- Every visible functional control that can be safely clicked is clicked.
- Home action drawer opens and submits through Bus API.
- Communication composer sends through Bus API.
- Gates decision actions do not mutate unsupported backend state silently.
- Screenshots are saved as `coordination/visual-layout-gate2-*.png`.
- No browser severe logs.
- No visible `????`, `???`, or mojibake clusters.
- No document-level horizontal overflow at desktop.

Pass broadcast: `GATE_VISUAL_LAYOUT_WAVE2_PASS`.

---

## Wave 3: Fixback And Final QA

### Task 3A: QA-Routed Fixbacks

Owner: assigned by `runtime-qa` only after Gate 2 findings.

**Files:**

- Only files named in the QA finding.

- [ ] **Step 1: Receive exact finding**

Do not self-assign. Wait for a runtime-qa message containing:

- route/page
- screenshot path
- selector or visible issue
- expected behavior
- allowed file scope

- [ ] **Step 2: Fix only the allowed scope**

Run the smallest relevant verification command from the finding.

- [ ] **Step 3: Send READY**

Send:

```text
VISUAL_LAYOUT_WAVE3_FIXBACK_READY <agent> ...
```

### Final Gate

Owner: `runtime-qa`

Final verification:

```powershell
pytest -q
npm --prefix frontend run build
```

Browser:

- Capture all routes:
  - `coordination/visual-layout-final-home.png`
  - `coordination/visual-layout-final-communication.png`
  - `coordination/visual-layout-final-runs.png`
  - `coordination/visual-layout-final-gates.png`
  - `coordination/visual-layout-final-artifacts.png`
  - `coordination/visual-layout-final-diagnostics.png`
  - `coordination/visual-layout-final-settings.png`
- Capture narrow:
  - `coordination/visual-layout-final-home-narrow.png`
  - `coordination/visual-layout-final-communication-narrow.png`
- Click all safe visible controls again.
- Compare against the five reference images by page role and layout hierarchy.

Final acceptance criteria:

- App visibly follows the provided references: same light shell, sidebar hierarchy, card rhythm, blue action language, page-specific structure.
- No visible dark old-shell surfaces.
- No visible mojibake/question-mark placeholders in primary UI.
- No fake data.
- Bus-backed actions still hit `/api/messages/send`.
- Real projections still load from `/api/projections/operations`, `/api/projections/messages`, and `/api/artifacts/manifests`.
- No severe browser logs.
- Desktop and narrow screenshots are nonblank and have no incoherent overlap.

Pass broadcast:

```text
GATE_VISUAL_LAYOUT_FINAL_PASS
```

Fail broadcast:

```text
GATE_VISUAL_LAYOUT_FINAL_FAIL <findings>
```

## Runtime-QA Notes

- This plan supersedes only the visual/layout standby state after Gate C. It does not invalidate Gate C technical pass.
- If the user provides more specific layout instructions while Wave 1 or Wave 2 is running, runtime-qa must pause new assignments, record the instruction in `USER_FEEDBACK.md` / `coordination/wave-gates.md`, and decide whether to adapt the current wave or open a scoped fixback.
- If broker is unavailable, agents must use `coordination/messages.ndjson`, `coordination/agent-status.md`, and `coordination/wave-gates.md` without exiting.
