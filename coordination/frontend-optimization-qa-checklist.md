# Frontend Optimization QA Checklist

Controller/QA: `runtime-helper-1`

## Required Checks

- [x] `frontend npm run build` passes.
- [x] Browser desktop check at `http://127.0.0.1:8787/` has no console errors.
- [x] Browser mobile-width check has no overlapping text or clipped controls.
- [x] Chinese UI labels are visible for navigation, top metrics, task lanes, gates, inspector, event console, and command composer.
- [x] Terms `worker`, `helper`, `QA`, `Agent`, `Agent Bus`, and `RunGraph` remain understandable.
- [x] BUG-2 agent-only routing is preserved.
- [x] Stale/degraded agents do not read as healthy ready.
- [x] No mock data or placeholder cards are present.

## Worker Evidence

- [x] Worker4 UX-W2 added Agent Workstation CSS tokens and prewired classes for `.operationsBrief`, `.briefAction`, `.briefRun`, `.workstationCard`, `.stationGlyph`, `.postureLine`, `.stationCurrent`, `.stationAction`, `.stationTrust`, `.decisionLanes`, `.decisionLane`, `.decisionCard`, `.decisionMeta`, and `.decisionAction`.
- [x] Worker4 UX-W2 preserved Command Composer layout classes and added responsive no-overflow rules for workstation/decision lane surfaces. `npm run build` passed from `frontend/` with only non-fatal lucide-react `"use client"` warnings.
- [x] Worker4 F1 added operations-room CSS tokens and stable layout classes.
- [x] Worker4 F1 created this QA checklist.
- [x] Worker4 F3 added stable Agent card, mission lane, and event console polish.
- [x] Worker4 F3 reviewed `frontend/src/App.tsx` and `frontend/src/uiText.ts` copy for Chinese-first labels while preserving approved terms such as `Agent`, `worker`, `helper`, `QA`, `Agent Bus`, and `RunGraph`.
- [x] Worker4 F3 avoided Command Composer routing logic changes.
- [x] Worker4 F3 `npm run build` passed from `frontend/`; lucide-react emitted only non-fatal `"use client"` bundle warnings.
- [x] Worker4 F3 browser smoke at `http://127.0.0.1:8787/` showed Chinese labels, no mojibake marker, and zero current `127.0.0.1:8787` console errors/warnings. Screenshot: `coordination/frontend-f3-worker4-smoke.png`.
- [x] Worker4 QA fix for `finding_03687f3203aa41abbf4f999d5872398a`: at 1280px, right rail stacks below the mission surface, mission lanes are 184px wide, lane overlap is false, task card horizontal overflow count is 0, and current `127.0.0.1:8787` console errors/warnings remain 0. Screenshot: `coordination/frontend-f3-worker4-layout-fix.png`.
- [x] Worker4 second QA fix for `finding_03687f3203aa41abbf4f999d5872398a`: at 1280x720 in a fresh browser tab, mission lanes use `auto-fit minmax(220px, 1fr)`, right rail stacks below the Agent/Mission grid, min lane width is 318px, task card overflow count is 0, and max card scroll delta is 0. Screenshot: `coordination/frontend-f3-worker4-layout-fix-2.png`.
- [x] Worker4 UX-W4 screenshot polish pass kept scope to `frontend/src/styles.css`: top-bar grid now has a dedicated run column plus compact refresh action, metric labels stay single-line, and workstation role labels are ellipsis-ready.
- [x] Worker4 UX-W4 `npm run build` passed from `frontend/`; lucide-react emitted only non-fatal `"use client"` bundle warnings.
- [x] Worker4 UX-W4 browser evidence at 1280x720: `.operationsBrief=1`, `.workstationCard=7`, `.decisionLanes=1`, `.decisionCard=12`, `.commandComposer=1`, document `scrollWidth=1280`, overflow list `[]`, current `127.0.0.1:8787` console errors/warnings `0`, refresh action `92x44`, and all workstation role labels use `white-space: nowrap` with `text-overflow: ellipsis`. Screenshot: `coordination/agent-workstation-worker4-polish.png`.
- [x] Worker4 BW-2 replaced `:root` with the user-locked blue-white token set, preserved compatibility aliases for existing selectors, and added the CSS foundation for `.topStatusBar`, `.alertBanner`, `.alertPrimary`, `.metricCard`, `.operationsGrid`, `.agentAvatar`, `.taskBoard`, `.gateTabs`, `.inspectorTabs`, `.eventTable`, `.artifactEmptyGrid`, and `.settingsCards`.
- [x] Worker4 BW-2 restyled the existing sidebar, top bar, panels, workstation cards, decision lanes, task/gate/event/composer surfaces, and responsive rules in `frontend/src/styles.css` only. `npm run build` passed from `frontend/`; lucide-react emitted only non-fatal `"use client"` bundle warnings.
- [x] Worker4 BW-4 polished the released Home / `控制首页` first screen in `frontend/src/styles.css` only: white sidebar, blue active nav, low-density title/KPI row, elevated current workflow card, large quick action cards, and Controller suggestion card aligned to `用户首屏.png`.
- [x] Worker4 BW-4 `npm run build` passed from `frontend/`; lucide-react emitted only non-fatal `"use client"` bundle warnings.
- [x] Worker4 BW-4 browser evidence at 1280x720: `.homePage=1`, active nav `控制首页`, body background `rgb(246, 248, 251)`, sidebar `rgba(255, 255, 255, 0.96)`, 4 Home metrics, 4 Home action cards, document `scrollWidth=1280`, overflow list `[]`, and current `127.0.0.1:8787` console errors/warnings `0`. Screenshot: `coordination/blue-white-worker4-polish.png`.

- [x] Worker1 BW-5 source regression registered artifact `artifact_3ae21ef37d0e4460b908be32b715e089` with metadata `coordination/bw5-worker1-source-regression-artifact.json`.
- [x] Worker1 BW-5 verified Home/default source wiring: `ViewName` includes `Home`, sidebar view order starts with `Home`, `activeView` defaults to `Home`, and labels map `Home` to `控制首页` and `Operations` to `总览`.
- [x] Worker1 BW-5 verified dense `总览` remains reachable from Home/detail actions and sidebar while the first screen stays the low-density Home route.
- [x] Worker1 BW-5 verified BUG-2 interrupt payload is preserved: `routing_mode: taskContext ? "task-context" : "agent-only"` and `include_selected_task: Boolean(taskContext)`.
- [x] Worker1 BW-5 checked no fake reference copy terms (`Q2`, `营销活动`, `marketing campaign`) in frontend source, and `unknown`/`none` are limited to normalization/model fallbacks filtered by `displayOrEmpty` or non-text icon keys.
- [x] Worker1 BW-5 `npm run build` passed from `frontend/`; lucide-react emitted only non-fatal `"use client"` bundle warnings.

## Helper1 QA Findings

- [x] Blocking finding `finding_03687f3203aa41abbf4f999d5872398a`: desktop screenshot `coordination/frontend-f3-worker4-smoke.png` showed mission lanes and task cards squeezed/overlapping at desktop width. Resolved by Worker4 artifact `artifact_69eb01c0fbee4b21be7a1fdb9487f5d5` and the second layout fix screenshot `coordination/frontend-f3-worker4-layout-fix-2.png`.
- [x] Historical helper1 retest before Worker4's second fix: `npm run build` passed and Browser logs were clean, but at 1280x720 the mission lanes were about 181px wide and 16/16 `.taskCard` elements had `scrollWidth > clientWidth`. Superseded by final passing retests below.
- [x] Final helper1 desktop retest at 1280x720: Browser logs `[]`, mission lanes are about 311px wide, `overflowCount=0`, `outsideCount=0`, Chinese labels visible, BUG-2 `携带任务上下文` visible, and `runtime-qa` reads as `降级待命`.
- [x] Final helper1 mobile retest at 390x844: Browser logs `[]`, document scroll width 375, `overflowCount=0`, `outsideCount=0`, Chinese labels visible, BUG-2 `携带任务上下文` visible, and stale/degraded agents remain readable as `降级待命`.

## Helper1 Gate Recommendation

- [x] PASS: approve the frontend optimization gate after resolving the F3 layout finding.

## Blue White Home Refinement QA

- [x] Helper1 final BW-6 build retest passed: `npm run build` from `frontend/` exited 0 with only known lucide-react module-level directive warnings.
- [x] Helper1 source retest confirmed `Home` is in `ViewName`, `activeView` defaults to `Home`, labels map `Home` to `控制首页` and `Operations` to `总览`, and BUG-2 payload fields remain `routing_mode: taskContext ? "task-context" : "agent-only"` plus `include_selected_task: Boolean(taskContext)`.
- [x] Helper1 desktop Browser retest at 1280x720: Home default active nav is `控制首页`, 4 KPI metrics render, current task-flow and Controller suggestion are visible, `总览` is reachable and shows five lane labels, document horizontal overflow is false, current Browser warnings/errors are `[]`, and visible primary `unknown`/`none` are absent. Evidence: `coordination/blue-white-operations-room-desktop-qa.json`.
- [x] Helper1 mobile Browser retest at 390x844: Home remains default, 4 metrics and Home cards fit inside width, document horizontal overflow is false, current Browser warnings/errors are `[]`, and visible primary `unknown`/`none` are absent. Evidence: `coordination/blue-white-operations-room-mobile-qa.json`.
- [x] Final screenshot evidence: `coordination/blue-white-operations-room-after.png` copied from Worker4's verified screenshot because final QA Browser CDP screenshot timed out; helper1 reran DOM/browser QA fresh after that copy.
- [x] PASS: approve blue-white Home refinement gate `gate_e9202dbad45b4d8a84d93bf669a9023b`.
