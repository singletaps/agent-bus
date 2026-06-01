# Reference Visual Layout Wave Board

Runtime owner: `runtime-qa`
Plan: `docs/superpowers/plans/2026-05-29-agent-bus-reference-visual-layout-fix.md`
Reference directory: `C:\Users\laptopofzy\Documents\Agent bus\5-29`
Created: `2026-05-29T13:23:00+08:00`

## User Directive

User told runtime-helper-1 at `2026-05-29T13:21:36+08:00`:

> 现在的问题是前端还是有一些难看，我在C:\Users\laptopofzy\Documents\Agent bus\5-29放置了5个参考图片，你们参考这个样式进行修正，qa编写具体的实施方案以及分工。

Runtime-qa interpretation:

- Gate C technical pass remains recorded.
- Visual/layout acceptance is reopened as a new improvement wave.
- The five screenshots are the visual target.
- Runtime-qa owns plan, assignment, serial gates, and final QA.

## Online Roster

- `runtime-helper-1`: online, assigned App shell and Home/copy work.
- `runtime-helper-2`: online, assigned Communication/Gates/detail work.
- `runtime-worker-4`: online, assigned visual foundation, shared CSS/components, Runs/Artifacts/Diagnostics/Settings polish.
- `runtime-qa`: online, QA gatekeeper and serial controller.

Offline / not assigned:

- `runtime-worker-1`
- `runtime-worker-2`
- `runtime-worker-3`

## Wave 1 Assignments

Gate state: `passed at 2026-05-29T13:56:30+08:00`

Status:

- `2026-05-29T13:35:07+08:00`: `runtime-helper-1` acknowledged Task 1A scope for App shell/PageToolbar and promised no CSS/backend/page redesign edits.
- `2026-05-29T13:47:21+08:00`: `runtime-helper-1` sent `VISUAL_LAYOUT_WAVE1_SHELL_READY`.
- `2026-05-29T13:50:19+08:00`: `runtime-worker-4` sent `VISUAL_LAYOUT_WAVE1_FOUNDATION_READY`.
- `2026-05-29T13:56:30+08:00`: runtime-qa passed Gate 1 after independent build, source scan, API-origin, and browser screenshot checks.

Required READY tokens:

- `VISUAL_LAYOUT_WAVE1_SHELL_READY runtime-helper-1`
- `VISUAL_LAYOUT_WAVE1_FOUNDATION_READY runtime-worker-4`

Assignments:

- `runtime-helper-1`
  - Scope: `frontend/src/App.tsx`, `frontend/src/uiText.ts`, optional `frontend/src/components/PageToolbar.tsx`
  - Goal: app shell labels, page toolbar, refresh wiring, clean visible copy.
  - Forbidden: CSS files, backend files, page redesign except Home in Wave 2.
- `runtime-worker-4`
  - Scope: `frontend/src/styles/base.css`, `frontend/src/styles/layout.css`, `frontend/src/styles/status.css`, `frontend/src/styles.css`.
  - Goal: reference-matched light shell, visual tokens, shared CSS primitives, remove dark old-shell remnants.
  - Forbidden: App, page `.tsx`, and shared component `.tsx` files in Wave 1.
- `runtime-helper-2`
  - Standby in Wave 1. May inspect plan and reference images but must not edit product code until Wave 2 starts.

Gate 1 QA:

- Evidence file: `coordination/reference-visual-layout-gate1-qa.md`
- `npm --prefix frontend run build`: passed.
- Source scan for dark shell remnants and mojibake: no matches.
- Browser screenshots on real backend origin:
  - `coordination/gate1-wave1-home-real-backend.png`
  - `coordination/gate1-wave1-communication-real-backend.png`
- Broadcast: `GATE_VISUAL_LAYOUT_WAVE1_PASS`

## Wave 2 Assignments

Gate state: `passed at 2026-05-29T14:31:59+08:00`

Required READY tokens:

- `VISUAL_LAYOUT_WAVE2_HOME_READY runtime-helper-1`
- `VISUAL_LAYOUT_WAVE2_COMM_GATES_READY runtime-helper-2`
- `VISUAL_LAYOUT_WAVE2_RUNS_ARTIFACTS_READY runtime-worker-4`

Assignments after Gate 1 pass:

- `runtime-helper-1`
  - Scope: `frontend/src/pages/HomePage.tsx`, Home-only `frontend/src/uiText.ts`.
  - Goal: reference Home with numbered sections, run posture, task metro, action queue.
- `runtime-helper-2`
  - Scope: `frontend/src/pages/CommunicationPage.tsx`, `frontend/src/pages/GatesPage.tsx`, `frontend/src/components/DetailRail.tsx`, `frontend/src/components/ActionDrawer.tsx`.
  - Goal: reference Communication and Gates list/detail workspaces.
- `runtime-worker-4`
  - Scope: `frontend/src/pages/RunsPage.tsx`, `frontend/src/pages/ArtifactsPage.tsx`, `frontend/src/pages/DiagnosticsPage.tsx`, and CSS support. Settings gets CSS-only polish unless runtime-qa routes an App fixback.
  - Goal: reference Runs and Artifacts pages, consistent Diagnostics/Settings, desktop and narrow screenshots.

Gate 2 QA:

- Evidence file: `coordination/reference-visual-layout-gate2-qa.md`
- `npm --prefix frontend run build`: passed.
- `pytest -q`: passed, `66 passed`.
- Canonical API checks passed for operations, messages, and artifact manifests.
- Browser screenshots captured for all seven routes:
  - `coordination/gate2-wave2-home-qa.png`
  - `coordination/gate2-wave2-communication-qa.png`
  - `coordination/gate2-wave2-runs-qa.png`
  - `coordination/gate2-wave2-gates-qa.png`
  - `coordination/gate2-wave2-artifacts-qa.png`
  - `coordination/gate2-wave2-diagnostics-qa.png`
  - `coordination/gate2-wave2-settings-qa.png`
- Safe visible controls clicked on Home, Communication, Runs, Gates, Artifacts, Diagnostics, and Settings.
- Fresh-tab current browser error count: 0.
- Broadcast: `GATE_VISUAL_LAYOUT_WAVE2_PASS`

## Wave 3 Fixback

Gate state: `passed at 2026-05-29T14:34:48+08:00`

Runtime-qa found no blocking Wave 2 defects. Final acceptance completed with independent narrow-screen spot checks for Home and Communication.

## Final Acceptance

Gate state: `passed at 2026-05-29T14:34:48+08:00`

Required final evidence:

- `pytest -q`: passed, `66 passed`.
- `npm --prefix frontend run build`: passed.
- Desktop screenshots for Home, Communication, Runs, Gates, Artifacts, Diagnostics, Settings: captured.
- Narrow screenshots for Home and Communication: captured.
- No current browser errors in fresh-tab checks.
- No visible mojibake or placeholder question marks in primary UI.
- Real API endpoints remain live:
  - `/api/projections/operations`
  - `/api/projections/messages`
  - `/api/artifacts/manifests`
- Safe controls were clicked across all primary pages.

Final evidence file:

- `coordination/reference-visual-layout-final-qa.md`

Final broadcast:

- `GATE_VISUAL_LAYOUT_FINAL_PASS`
