# Page By Page QA And Overview Density Fixback Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Respond to post-gate user feedback by auditing every page with screenshots and click tests, then fix the dense `总览` page and any interaction errors found.

**Architecture:** Treat the approved blue-white Home work as a baseline, not final acceptance. Helper1 performs an evidence-first page audit across all sidebar routes and primary controls; implementation agents only edit product code after the audit identifies concrete issues. Worker4 owns visual density/CSS fixes, Helper2 owns App interaction or structure fixes, Worker1 owns source regression, and Helper1 owns the final gate.

**Tech Stack:** React 19, TypeScript, Vite, lucide-react, in-app Browser QA, existing live service at `http://127.0.0.1:8787/`.

---

## User Feedback

Source: Agent Bus message `841e1eb6-0d85-460d-b2f8-5ae78a217cdb` at 2026-05-28T18:57:24+08:00.

> 总览页有大量的元素堆积。最终审核的时候可以每一页逐个截图判断，对于每个功能都可以去尝试点击一下，查看是否有错误。

## Files

- Create: `coordination/page-by-page-qa-audit.json`
- Create: `coordination/page-by-page-qa-*.png`
- Modify if needed: `frontend/src/styles.css`
- Modify if needed: `frontend/src/App.tsx`
- Modify if needed: `frontend/src/uiText.ts`
- Modify: `coordination/frontend-optimization-qa-checklist.md`
- Create: `coordination/page-by-page-qa-final-artifact.json`

## Non-Goals

- Do not change backend APIs.
- Do not change `/api/interrupt`.
- Do not remove or rename BUG-2 payload fields.
- Do not redesign Home again unless the audit finds a concrete defect.
- Do not hide real operational risk to make screenshots look cleaner.

## Task 1: Helper1 Page Audit

**Assignee:** `runtime-helper-1`

**Files:**
- Create: `coordination/page-by-page-qa-audit.json`
- Create: `coordination/page-by-page-qa-home.png`
- Create: `coordination/page-by-page-qa-overview.png`
- Create: `coordination/page-by-page-qa-agents.png`
- Create: `coordination/page-by-page-qa-gates.png`
- Create: `coordination/page-by-page-qa-rungraph.png`
- Create: `coordination/page-by-page-qa-artifacts.png`
- Create: `coordination/page-by-page-qa-settings.png`

- [ ] **Step 1: Build**

Run:

```powershell
npm run build
```

Expected: exit code 0; lucide-react module directive warnings are acceptable.

- [ ] **Step 2: Audit every sidebar route**

Open `http://127.0.0.1:8787/` at 1280x720. For each route below, click the sidebar item, capture a screenshot, collect DOM facts, and record any console warning/error:

- `控制首页`
- `总览`
- `智能体`
- `门禁`
- `任务流`
- `产物`
- `设置`

For each route record:

- active nav text
- page heading
- body horizontal overflow
- visible `unknown` / `none`
- fake reference copy terms (`Q2`, `营销活动`, `marketing campaign`)
- offscreen or overlapping primary surfaces
- screenshot path
- console warning/error count

- [ ] **Step 3: Click primary controls**

On the relevant route, attempt these controls when present:

- `刷新`
- `继续运行`
- `查看总览`
- `查看并处理`
- `查看审批`
- `查看成果`
- `应用建议`
- gate tabs
- inspector tabs
- event filters
- settings cards
- command composer context toggle

Record whether the click changed view/state as expected or produced console errors.

- [ ] **Step 4: Decide fix scope**

If only `总览` is dense but interaction is stable, create a Worker4 CSS density fix task. If clicks fail or route structure causes pileup, create a Helper2 App structure task. If no blocking issues are found, document the audit and ask the user whether they want visual density reduced further.

## Task 2: Worker4 Overview Density Fix

**Assignee:** `runtime-worker-4`

**Start Condition:** Helper1 audit identifies CSS/layout density problems in `总览`.

**Files:**
- Modify: `frontend/src/styles.css`
- Create: `coordination/overview-density-worker4-artifact.json`
- Create: `coordination/overview-density-worker4-after.png`

- [ ] **Step 1: Fix visual density only**

Use CSS to reduce the sense of pileup in `总览`:

- add clearer vertical spacing between sections
- make dense panes scroll within their own containers instead of visually stacking
- ensure lane/card widths do not compress text
- reduce decorative gradients or heavy shadows if they compete with data
- preserve Home visual direction and all route labels

- [ ] **Step 2: Verify**

Run `npm run build` and Browser smoke at 1280x720. Expected: build exit 0, no body horizontal overflow, `总览` readable at first viewport, no console warning/error, BUG-2 controls still reachable.

## Task 3: Helper2 Interaction Fix

**Assignee:** `runtime-helper-2`

**Start Condition:** Helper1 audit finds route/click behavior problems that CSS cannot solve.

**Files:**
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/uiText.ts` only if labels are wrong
- Create: `coordination/page-click-helper2-artifact.json`

- [ ] **Step 1: Fix the specific interaction**

Only change the route/control behavior that failed in the audit. Do not make broad visual redesigns.

- [ ] **Step 2: Preserve BUG-2**

Confirm:

```ts
routing_mode: taskContext ? "task-context" : "agent-only",
include_selected_task: Boolean(taskContext),
```

- [ ] **Step 3: Verify**

Run `npm run build` and repeat the failing click path.

## Task 4: Worker1 Regression

**Assignee:** `runtime-worker-1`

**Start Condition:** Any Worker4 or Helper2 product-code fix lands.

**Files:**
- Read: `frontend/src/App.tsx`
- Read: `frontend/src/operationsRoomModel.ts`
- Read: `frontend/src/uiText.ts`
- Read: `frontend/src/styles.css`
- Create: `coordination/page-by-page-worker1-regression.json`

- [ ] **Step 1: Source check**

Verify Home/default wiring, `总览` route, BUG-2 payload, labels, and absence of fake reference copy.

- [ ] **Step 2: Build**

Run `npm run build`; expected exit code 0.

## Task 5: Helper1 Final Page QA Gate

**Assignee:** `runtime-helper-1`

**Files:**
- Create: `coordination/page-by-page-qa-final-artifact.json`
- Modify: `coordination/frontend-optimization-qa-checklist.md`

- [ ] **Step 1: Re-run page audit**

Repeat Task 1 for all pages and controls after any fixes.

- [ ] **Step 2: Gate decision**

Approve only if page screenshots and click tests show no blocking errors, `总览` density is materially improved or explicitly documented as acceptable, and technical regressions pass.

## Self-Review

- Covers the user's new `总览` density complaint.
- Adds the requested page-by-page screenshot/click final audit.
- Keeps implementation agents scoped and prevents unplanned product-code edits.
- Keeps helper1 as controller/QA.
