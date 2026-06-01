# Browser Frontend Comments

This document records user browser comments for the Agent Bus frontend review.

Important constraint: record comments here first. Do not implement these notes immediately. Later changes should be planned and applied in a unified frontend modification wave.

Current conflict-resolution rules. These supersede any earlier conflicting wording in the recorded comments:

- Status colors:
  - Green: completed / passed.
  - Yellow: in progress / waiting for confirmation.
  - Red: failed / blocked / rejected.
  - Gray: not started / no data.
  - Purple: QA / review.
- Delete the old global `检查器`, but keep page-scoped right-side detail panels where they show observable task, gate, message, artifact, or Agent facts.
- Delete the old global `指令台` / Command Console, but keep page-scoped Bus-backed composers that create structured Bus records such as `message`, `instruction`, `gate_request`, and `handoff`.
- Do not display claims about hidden Codex subagent conversation internals, trust, quality, or reliability. The frontend cannot inspect those internals.
- MVP removes global success-rate metrics from Home. Rate-like metrics may only appear in Diagnostics after the formula, denominator, sample window, and source events are documented.

## Comment 1 - Home Overview Workflow Diagram And Icon Redraw

Date: 2026-05-29

Source:

- Browser URL: `http://127.0.0.1:8787/`
- Page area: `总览 / 控制首页` first screen
- Selected target text: overview header and current workflow summary. Page evidence included a global rate-like metric that is superseded by the conflict-resolution rules above.
- Target selector: `div#root > main.opsShell > section.opsMain > section.homePage`
- Viewport: `1183x702`
- Marker screenshot: attached in browser comment thread as Comment 1 evidence

User comment:

> 总览界面，当前工作流下面应该能显示任务与门禁，类似于地铁的运行图，小绿点(已通过)，小黄点（正在进行），小红点（未开始或未通过）。同时这一屏的图标都要重新绘制，可以导入绘制像素画或设计前端图标的skill插件来完成。注意，这条注释以及接下来的注释你都要记录在一个md文档中而不是立刻修改，我们后续统一修改。

Recorded requirements:

- On the overview/home screen, the area under the current workflow should show tasks and gates.
- The workflow visualization should feel like a subway operation map.
- Status markers should use:
  - Green dot: passed/completed.
  - Yellow dot: currently in progress or waiting for confirmation.
  - Red dot: failed, blocked, or rejected.
  - Gray dot: not started or no data.
  - Purple dot: QA/review, when review state must be distinct.
- All icons on this screen should be redrawn instead of keeping the current placeholder/generic icons.
- Possible implementation route: use a pixel-art drawing skill/plugin or a frontend icon design skill/plugin to create or guide the new icon set.
- No frontend code changes should be made from this comment yet. This is input for a later unified modification plan.

Open planning questions for later:

- Should the subway-style workflow map live only on the Home screen, or also replace/augment the `任务流` route?
- Should task and gate nodes share one line, or use parallel lanes for tasks, gates, reviews, and artifacts?
- Should icons be pixel-art raster assets, CSS/HTML primitives, lucide-based custom compositions, or generated bitmap assets?

## Comment 2 - Event Console Fixed Scroll Frame

Date: 2026-05-29

Source:

- Browser URL: `http://127.0.0.1:8787/`
- Page area: `事件控制台 / 事件流`
- Selected target text: `事件控制台 事件流`
- Target selector: `section.operationsGrid:nth-of-type(2) > section.centerRail:nth-of-type(2) > section.panel.timeline:nth-of-type(2) > header.panelHeader`
- Viewport: `1183x702`
- Marker screenshot: attached in browser comment thread as Comment 1 evidence for this browser batch

User comment:

> 事件控制台放到一个固定的框内，日志可以下滑查看，而不是像现在全量显示。

Recorded requirements:

- The event console should live inside a fixed-height frame/container.
- The log list should scroll internally within that frame.
- The page should not expand vertically to show the full event log by default.
- This should reduce page height, avoid overwhelming the overview, and make nearby panels easier to compare.
- No frontend code changes should be made from this comment yet. This is input for a later unified modification plan.

Open planning questions for later:

- What is the default event console height on desktop and mobile?
- Should the event console keep sticky filters/header while the log body scrolls?
- Should there be a "view all / expand" affordance for full audit mode?

## Comment 3 - Global Layout Overlap And Spacing Audit

Date: 2026-05-29

Source:

- Browser URL: `http://127.0.0.1:8787/`
- Page area: top status bar / operations room shell
- Selected target text: `AGENT OPERATIONS ROOM Agent Operations Room Live Round 1 / 运行中 · 7 tasks 同步 09:2`
- Target selector: `div#root > main.opsShell > section.opsMain > header.topStatusBar.opsTopBar`
- Viewport: `1183x702`
- Marker screenshot: attached in browser comment thread as Comment 1 evidence for this browser batch

User comment:

> 基本所有页面都出现了元素堆叠覆盖的情况，优化一下所有的排版吧

Recorded requirements:

- Treat layout overlap/stacking as a global frontend issue, not a single-page tweak.
- Audit all major pages/routes for elements covering each other, clipped text, horizontal overflow, and cramped spacing.
- Fix the top status bar where KPI cards and title/run metadata visually crowd or overlap.
- Review responsive behavior at the current browser viewport (`1183x702`) and likely smaller widths.
- Establish safer layout constraints for cards, headers, panels, sidebars, and tables so content wraps or scrolls predictably.
- No frontend code changes should be made from this comment yet. This is input for a later unified modification plan.

Open planning questions for later:

- Should the next implementation wave start with a page-by-page layout audit before any visual redesign work?
- Which breakpoints should be considered acceptance targets: desktop only, current in-app browser size, tablet, and/or mobile?
- Should the top status bar collapse KPI cards into a second row or compact summary at narrower widths?

## Comment 4 - Action Window For Tasks That Need User Handling

Date: 2026-05-29

Source:

- Browser URL: `http://127.0.0.1:8787/`
- Page area: `总览 / 任务态势 / 需处理`
- Selected target text: `需处理 6 Worker2 CLI child fail 失败 未分配 task_7472c… 进度 0% 定位、复查或重新分派 run_58a117… 0 U`
- Target selector: `section.centerRail:nth-of-type(2) > section.panel.missionSurface:nth-of-type(1) > div.decisionLanes > section.decisionLane:nth-of-type(1)`
- Viewport: `1183x702`
- Marker screenshot: attached in browser comment thread as Comment 1 evidence for this browser batch

User comment:

> 对于需处理，点击任务要加一个user给Controller发送消息的窗口，不然不是只能看着需处理什么也做不了么。

Recorded requirements:

- Tasks in the `需处理` lane must be actionable, not read-only.
- Clicking a task that needs handling should open a user-to-Controller message window or action composer.
- The window should let the user send a targeted instruction/message to Controller about the selected task.
- The selected task metadata should be carried into the composer, including task title, task id, run id, current status, and suggested action.
- This interaction should make the `需处理` lane a real operations queue rather than a passive display.
- No frontend code changes should be made from this comment yet. This is input for a later unified modification plan.

Open planning questions for later:

- Should the composer create a `user.interrupt_created` event, a direct Controller inbox message, or both?
- Should the task click open an inline panel, modal, right-side action drawer, or Bus-backed composer prefilled with task metadata?
- Should this flow support common quick actions such as `重新分派`, `请求复查`, `标记已知`, and `升级门禁`?

## Comment 5 - Agent Avatar Style And Remove Unknowable Runtime Scores

Date: 2026-05-29

Source:

- Browser URL: `http://127.0.0.1:8787/`
- Page area: `智能体工作台 / Agent Dock`
- Selected target text: `降级注意 runtime-helper-1 helper-bootstrapper 健康 30% 能力 35% 疑似卡住 ses_6cfddf… 当前 UX-W`
- Target selector: `section.opsMain > section.operationsGrid:nth-of-type(2) > section.panel.agentDock:nth-of-type(1) > div.agentList`
- Viewport: `1183x702`
- Marker screenshot: attached in browser comment thread as Comment 1 evidence for this browser batch

User comment:

> 这个只能徒头像也换成像素风或其他的画风。同时删去健康，能力这些，因为我们根本没法得知一个对话的健康与能力。

Recorded requirements:

- Agent avatars should be redesigned with a deliberate visual style, such as pixel art or another cohesive art direction.
- The current generic/placeholder agent avatar treatment should not remain as-is.
- Remove `健康` and `能力` metrics from the agent card UI.
- Also remove or rethink these fields where they appear in related panels, because the product cannot truly know a conversation's hidden runtime quality.
- Avoid presenting inferred or unreliable metrics as factual percentages.
- Replace these metrics with observable, defensible runtime facts if needed, such as connection recency, last activity, current task, inbox count, session state, or user/controller annotations.
- No frontend code changes should be made from this comment yet. This is input for a later unified modification plan.

Open planning questions for later:

- Should avatar generation use pixel-art bitmap assets, CSS-generated icons, or a consistent icon set?
- What observable fields should replace `健康/能力`: `最近活动`, `连接状态`, `当前任务`, `会话状态`, `待处理 inbox`, or something else?
- Should backend projection names also change, or should only the frontend label/usage be removed while keeping data for diagnostics?

## Comment 6 - Remove Old Global Inspector And Unobservable Conversation Claims

Date: 2026-05-29

Source:

- Browser URL: `http://127.0.0.1:8787/`
- Page area: `检查器 / 旧全局详情面板`
- Selected target text: `检查器 旧全局详情面板`
- Target selector: `section.operationsGrid:nth-of-type(2) > section.rightRail:nth-of-type(3) > section.panel.inspector:nth-of-type(1) > header.panelHeader`
- Viewport: `1183x702`
- Marker screenshot: attached in browser comment thread as Comment 1 evidence for this browser batch

User comment:

> 检查器可以直接删除，智能体工作台里那些不可观测的会话内部状态也可以删除，意义不明确。我们无法感知 Codex 子 Agent 的实际对话内部状态。

Recorded requirements:

- The old global `检查器` panel can be removed from the main UI.
- Remove agent-workstation displays that claim to measure conversation reliability or hidden conversation internals.
- Do not show conversation trust, quality, or similar claims as user-facing facts.
- The current meaning of the old inspector panel is unclear to the user.
- The product cannot reliably inspect the actual Codex subagent conversation state, so the UI should not present it as measurable truth.
- This deletion applies to the old global inspector only; it does not ban page-scoped right-side detail panels that show observable task, gate, message, artifact, or Agent facts.
- No frontend code changes should be made from this comment yet. This is input for a later unified modification plan.

Open planning questions for later:

- Which pages should keep page-scoped right rails for observable details and actions?
- Which current inspector actions, if any, must survive elsewhere before deleting the panel?

## Comment 7 - Gate Owner Should Bind To QA Role

Date: 2026-05-29

Source:

- Browser URL: `http://127.0.0.1:8787/`
- Page area: `门禁 / 审批中心`
- Selected target text: `Worker2 CLI reject gate gate_0447082... normal 已拒绝 负责人待确认`
- Target selector: `section.rightRail:nth-of-type(3) > section.panel.gateCenter:nth-of-type(2) > div.gateStack:nth-of-type(2) > article.gateItem:nth-of-type(1)`
- Viewport: `1183x702`
- Marker screenshot: attached in browser comment thread as Comment 1 evidence for this browser batch

User comment:

> 门禁的负责人为什么都是待确认，不应该是直接绑定到有qa role的Agent上面去么。

Recorded requirements:

- Gate items should not default to `负责人待确认` when there is an available agent with QA responsibility.
- Gate owner assignment should bind directly to an Agent with `qa` role or current QA responsibility.
- The UI should show the actual responsible QA agent when one can be derived.
- If the original QA agent is closed or replaced, the owner should reflect the active QA replacement or delegated QA owner.
- `负责人待确认` should be reserved for truly unresolved ownership, not a common/default state.
- No frontend code changes should be made from this comment yet. This is input for a later unified modification plan.

Open planning questions for later:

- Should owner binding happen in backend projection, frontend derivation, or both?
- If multiple QA-role agents exist, what priority should select the gate owner: active session, latest heartbeat, explicit assignment, or controller decision?
- Should rejected/handled gate history keep the original QA owner, while open gates show the current active QA owner?

## Comment 8 - Remove Replacement Dock And Old Global Command Console From Main UI

Date: 2026-05-29

Source:

- Browser URL: `http://127.0.0.1:8787/`
- Page area: `接管席位 / 指令台`
- Selected target text: `接管席位 候选评分`
- Target selector: `section.operationsGrid:nth-of-type(2) > section.rightRail:nth-of-type(3) > section.panel.replacementDock:nth-of-type(3) > header.panelHeader`
- Viewport: `1183x702`
- Marker screenshot: attached in browser comment thread as Comment 1 evidence for this browser batch

User comment:

> 接管席位与指令台也可以删除，意义不明确。Controller可以直接调度接管，对于指令相关的部分单独开一个新页面，后续我会补充。

Recorded requirements:

- Remove `接管席位` from the main operations UI.
- Remove the old global `指令台` / Command Console from the main operations UI.
- The current meaning/value of these panels is unclear in the main screen.
- Controller can directly handle replacement/takeover scheduling, so a visible replacement candidate panel is not needed here.
- This deletion does not remove page-scoped Bus-backed composers inside Communication, Home action drawers, Runs, or Gates.
- A composer may create structured Bus `message`, `instruction`, `gate_request`, or `handoff` records, but it must not become a free-form side channel that bypasses Agent Bus.
- Old command-console features should move to a dedicated Bus-backed communication/control page later if they still matter.
- Keep this as a planning note only; the user will provide more instruction-page requirements later.
- No frontend code changes should be made from this comment yet. This is input for a later unified modification plan.

Open planning questions for later:

- Should replacement/takeover information disappear entirely from normal UI, or remain as a small status badge controlled by Controller state?
- What navigation label should the future instruction page use: `指令`, `调度`, `Controller`, or another term?
- Which current old command-console functions, if any, must be rebuilt as structured Bus message actions?

## Comment 9 - Do Not Show Global Header And Alert Banner On Every Page

Date: 2026-05-29

Source:

- Browser URL: `http://127.0.0.1:8787/`
- Page area: global top header and abnormal task alert banner
- Selected target text: `需要处理任务异常 Worker2 CLI child fail 需要定位、复查或重新分派。 处理异常任务`
- Target selector: `div#root > main.opsShell > section.opsMain > section.alertBanner:nth-of-type(1)`
- Viewport: `1183x702`
- Marker screenshot: attached in browser comment thread as Comment 1 evidence for this browser batch

User comment:

> 这个异常任务提示与上面的Agent operations Room不需要每屏都显示。

Recorded requirements:

- The abnormal-task alert banner should not appear on every page.
- The `Agent Operations Room` top header should not be repeated as a heavy first-screen element on every page.
- Page-specific content should get more vertical priority, especially pages such as `产物`.
- Global status may need to become a compact shell/nav element or only show on the home/overview page.
- Critical alerts should be scoped, collapsible, or routed to an appropriate page/queue rather than occupying the top of every route.
- No frontend code changes should be made from this comment yet. This is input for a later unified modification plan.

Open planning questions for later:

- Which pages should retain the global run header: Home only, Overview only, or all pages in compact form?
- Should abnormal task alerts become a sidebar badge, toast, notification center item, or home-only banner?
- What severity threshold should justify a cross-page banner?

## Comment 10 - Artifacts Page Should Show Real Local Outputs

Date: 2026-05-29

Source:

- Browser URL: `http://127.0.0.1:8787/`
- Page area: `产物`
- Selected target text: `截图 等待 screenshot artifact 报告 等待 summary/report artifact 日志 等待 trace/log artifact`
- Target selector: `main.opsShell > section.opsMain > section.panel.fullPanel:nth-of-type(2) > div.artifactGrid`
- Viewport: `1183x702`
- Marker screenshot: attached in browser comment thread as Comment 1 evidence for this browser batch

User comment:

> 产物应该有实际内容，具体的可以读取本地固定目录的文件，Agent也会将handoff，log或截图等都存到固定目录。或者你有没有其他的方法，我是决定上传服务器有点麻烦，你可以思考一下。

Recorded requirements:

- The `产物` page should show real artifact content, not only placeholder rows.
- A practical approach is to read files from a fixed local directory.
- Agents can write handoff notes, logs, screenshots, reports, and related evidence into that fixed directory.
- Avoid requiring upload to an external server if a local workspace-backed flow is enough.
- The UI should expose actual artifact files such as screenshots, summaries/reports, logs/traces, and handoff documents.
- No frontend code changes should be made from this comment yet. This is input for a later unified modification plan.

Possible design directions for later:

- Fixed local artifact root: e.g. `coordination/artifacts/` or `.agent-bus/artifacts/`, grouped by run/task/agent.
- Manifest-based artifact index: agents write a small JSON manifest next to files so the UI can show title, type, owner, task, timestamp, and preview path without scanning everything blindly.
- Backend local-file API: FastAPI lists allowed artifact files under the configured root and serves previews/downloads only from that root.
- SQLite-backed artifact records: keep DB artifact metadata, but store file payloads locally and reference them by safe relative path.
- Hybrid fallback: if DB records are missing, scan the fixed directory and infer basic artifact type from extension/name.

Open planning questions for later:

- What should the fixed artifact directory be named, and should it live under `coordination/` or a runtime data directory?
- Should screenshots render inline thumbnails, while logs/reports open in a preview drawer?
- What file safety rules are needed so the local file API cannot expose arbitrary paths?
- Should agents be required to create artifact metadata manifests, or should the system infer metadata automatically?

## Comment 11 - Task Flow Details Page Needs Richer Run Data

Date: 2026-05-29

Source:

- Browser URL: `http://127.0.0.1:8787/`
- Page area: `任务流 / 任务流列表`
- Selected target text: `run_58a11729... 已创建 created queued working gate review done task_7ae9e0a... task`
- Target selector: `main.opsShell > section.opsMain > section.panel.fullPanel:nth-of-type(2) > div.runGraph`
- Viewport: `1183x702`
- Marker screenshot: attached in browser comment thread as Comment 1 evidence for this browser batch

User comment:

> 目前的任务流太简陋了，在任务流详情页至少要能看到一些详细的数据。包括Agent分工，进度，门禁等东西，至少比首页的要详细。另外这些全都是已创建没有其他消息，是bug还是本来就没执行，后续可以确认一下。

Recorded requirements:

- The current task-flow page is too simple.
- The task-flow detail page should show richer data than the home page.
- Required detail categories include:
  - Agent assignments and division of labor.
  - Task progress.
  - Gates and gate status.
  - Relevant task/run state changes.
- The page should help users understand what happened inside a run, not only show run/task ids and generic stage labels.
- The current display where all runs appear as `已创建` / `created` needs investigation.
- It is unclear whether the runs truly never executed or whether the UI/projection has a bug that fails to surface later state changes.
- No frontend code changes should be made from this comment yet. This is input for a later unified modification plan.

Open planning questions for later:

- Should the task-flow page have a selectable run detail view with timeline, agent lanes, task list, gates, artifacts, and events?
- Should `created/queued/working/gate/review/done` be real status-derived stages rather than static labels?
- What backend/projection checks are needed to confirm whether `已创建` everywhere is data truth or UI bug?
- Should this page include a subway-style run diagram from Comment 1, but with more detail than the home screen?

## Comment 12 - De-Duplicate Agent/Gate Pages And Separate Agent Name From Roles

Date: 2026-05-29

Source:

- Browser URL: `http://127.0.0.1:8787/`
- Page area: sidebar navigation / `智能体`
- Selected target text: `智能体`
- Target selector: `main.opsShell > aside.sidebar > nav.navList > button.navItem:nth-of-type(3)`
- Viewport: `1183x702`
- Marker screenshot: attached in browser comment thread as Comment 1 evidence for this browser batch

User comment:

> 智能体与门禁界面与总览的内容完全一致，你考虑是精简总览还是把这两个直接删掉，另外Agent的name和role要分清楚，role就是系统固定的qa/worker等，一个Agent可以有多个role。

Recorded requirements:

- The `智能体` and `门禁` pages currently duplicate content already shown on `总览`.
- The information architecture should be simplified:
  - Either make `总览` lighter and keep dedicated `智能体` / `门禁` pages for details.
  - Or remove the duplicate `智能体` / `门禁` pages if they do not provide distinct value.
- Avoid maintaining multiple pages with identical content and interaction patterns.
- Agent `name` and `role` must be clearly separated.
- `name` is the agent identity/display name.
- `role` is a system-defined responsibility such as `qa`, `worker`, `helper`, or `controller`.
- One Agent can have multiple roles.
- UI labels, cards, filters, and backend/projection data should not conflate agent name with a single role string.
- No frontend code changes should be made from this comment yet. This is input for a later unified modification plan.

Open planning questions for later:

- Should `总览` become a lightweight summary while `智能体` and `门禁` become deeper detail pages?
- If `智能体` / `门禁` pages remain, what unique actions or data should each page provide?
- Should the role model change from single `role` to `roles: string[]` in the backend projection, frontend model, or both?
- How should multiple roles render compactly on agent cards and in gate ownership assignment?

## Comment 13 - Reset Agents Page Into Communication Console

Date: 2026-05-29

Source:

- User-provided design direction in the conversation after Comment 12.
- Target page: `智能体`
- Intended new page name: `Communication Console`
- Local reference image: [communication-console-reference-2026-05-29.png](assets/communication-console-reference-2026-05-29.png)
- Absolute reference image path: `C:\Users\laptopofzy\Documents\Agent bus\docs\assets\communication-console-reference-2026-05-29.png`

User comment:

> 重置智能体页面吧，给出一个格式参考，核心内容如下，记在comments里面，这张图你也可以存到本地供子Agent施工参考。

Recorded positioning:

- `Communication Console` is the Agent Bus page for observing communication between Agents, sending runtime instructions to Agents, and tracking instruction delivery and response status.
- It is not a normal chat application.
- It is not a raw event-log viewer.
- The page should make high-value Agent communication visible without dumping every low-level event.
- The page should keep `Agent Bus` as the only runtime control plane, so users do not bypass Bus by messaging Codex subagent entry points directly.

Core goals:

- Let users see high-value communication between Agents.
- Let users send instructions through Bus to one or more Agents.
- Let users confirm whether a message was delivered, acknowledged, and whether it produced follow-up tasks or gates.
- Let users click an Agent avatar to inspect that Agent's current status.
- Give communication from `controller`, `worker`, `qa`, `helper`, and `observer-archivist` clear thread/run ownership instead of scattering it in a global message stream.

Reference layout requirements:

- Replace the current duplicated `智能体` page with a communication workspace.
- Use a three-zone layout:
  - Left rail: communication spaces, thread groups, and Agent list.
  - Center rail: filtered message stream with linked message cards and bottom composer.
  - Right rail: selected Agent details and selected message details.
- The left rail should support:
  - Spaces such as urgent task exceptions, daily collaboration, release/change, and performance/cost optimization.
  - Thread groups such as unread, mentions, gate-related, exception/warning, and user-attention-needed.
  - Agent list with name, role badges, and observable online/running/idle status.
- The center rail should support:
  - Scope filter, unread toggle, auto-scroll toggle, search/filter controls, and overflow actions.
  - Date separators.
  - Message cards from Operator, Controller Agent, workers, helpers, QA, and observer/archive roles.
  - Delivery and response states such as `已送达`, `已确认`, and `等待回复`.
  - Structured chips for linked task, run, gate, report, artifact, risk, priority, and message type.
  - Cards that show whether the message is a broadcast, direct message, status update, gate request, verification result, or observer reminder.
- The bottom composer should support:
  - Sending to a selected Agent, multiple Agents, a space, or a thread.
  - Choosing message type, such as direct instruction, broadcast, gate request, or task handoff.
  - Mentioning Agents.
  - Adding or linking gates, tasks, artifacts, and files.
  - A clear send action routed through Bus.
- The right rail should support:
  - Tabs for Agent detail and message detail.
  - Agent detail fields based only on observable data, such as session id, conversation id, validity/completeness if the system can actually know it, current task, inbox count, and status.
  - Recent operations linked to task/gate/artifact events.
  - Quick actions such as send message, request gate, assign task, view artifact, and expanded actions.

Data and behavior requirements:

- Messages should be connected to Bus records rather than being a separate chat backend.
- Communication items should preserve record links to tasks, gates, runs, artifacts, and reports.
- Delivery tracking should distinguish at least sent, delivered, acknowledged, waiting for reply, failed, and superseded/interrupted if the Bus can expose those states.
- Clicking Agent avatars or names should select the Agent and show current observable status in the right rail.
- Clicking a message should select message details in the right rail.
- Controller-to-Agent, Agent-to-Agent, QA-to-worker, helper-to-worker, and observer-to-controller messages should retain their role attribution.
- The UI should avoid displaying invented quality, confidence, or scoring values.
- No frontend code changes should be made from this comment yet. This is input for a later unified modification plan.

Open planning questions for later:

- Should `智能体` be renamed to `通信` / `Communication Console` in the sidebar, or keep the Chinese label with an English page title?
- What Bus event/message schema fields are available for delivery, ack, reply, and produced task/gate linkage?
- Should high-value communication be filtered from raw event logs by explicit message type, by actor role, or by an operator-curated projection?
- Should the existing `事件控制台` become a lower-level diagnostics page after this communication page is introduced?

## Comment 14 - Product Principles, Information Architecture, And Data Contracts

Date: 2026-05-29

Source:

- User-provided overall frontend review after Comment 13.
- Scope: whole Agent Bus frontend product structure, not one isolated page.

User comment:

> Agent Bus 前端不应该继续像一个“监控后台”，而应该是一个“运行控制台 + 协作通信台 + 审计诊断台”。目前最大问题不是单个页面丑，而是信息架构和操作闭环还没建立起来。

Adoptable product principles:

- Agent Bus should be positioned as:
  - A runtime control console.
  - A collaboration communication console.
  - An audit and diagnostics console.
- It should not feel like a generic monitoring backend.
- The primary product problem to solve is information architecture and action closure, not only visual polish.

Frontend Product Principles / 前端产品原则:

- Home only answers: what is happening now, where is it blocked, and what can I do.
- Home should not show deep details. It should focus on current Run / task-flow state, blockers, exceptions, user-action items, Controller recommendations, and quick entry points into detail or instruction flows.
- Every user-visible metric must be observable.
- Prefer facts the system can actually know, such as `last_seen_at`, `current_task_id`, `inbox_count`, `session_state`, `ack_state`, `gate_state`, and `artifact_count`.
- Do not display model capability scores, conversation reliability scores, health scores, or global success-rate metrics in MVP.
- Global success-rate metrics may only appear in Diagnostics after the formula, denominator, sample window, and source events are documented.
- Every `需处理`, `开放门禁`, `异常`, or `等待用户` item must have an action exit.
- Clicking an action-required item should open an action drawer, composer, approval panel, reassignment flow, artifact view, or detail page. A warning without a next action is not a control console.
- `Communication Console` and `Event Log` must be separate concepts.
- Communication shows high-value `message`, `instruction`, `gate_request`, `handoff`, and `verification_result` items.
- Raw protocol events belong in a `Diagnostics` / `Audit` page, not the daily communication UI.
- Home should show only summary events related to the current blocker.

Recommended MVP information architecture:

| Page | Decision | Core responsibility |
| --- | --- | --- |
| `控制首页` / Home | Keep as default page | Current run, task/gate subway map, action queue, Controller recommendation |
| `通信` / Communication | Replace current `智能体` page | High-value Agent messages, user instructions through Bus, delivery/ack state |
| `任务流` / Runs | Keep and strengthen | Run details, Agent division of labor, task progress, gates, artifacts, scoped timeline |
| `门禁` / Gates | Keep only if it becomes an approval center | Decision-focused gate list; no duplicate of Home |
| `产物` / Artifacts | Keep and strengthen | Read local artifact root; show screenshots, reports, handoff docs, logs |
| `诊断` / Diagnostics | Add or hide under Settings | Raw event stream, session fencing, stale events, protocol warnings |
| `设置` | Keep | Artifact root, refresh interval, display density, theme |

Navigation cleanup:

- `总览` and `控制首页` currently overlap semantically; MVP should keep one default page named `控制首页` and remove or merge the other.
- `智能体` should not continue as a plain Agent list page; it should become `通信` / `Communication Console`.
- `门禁` should be removed if it only duplicates Home, or kept only as a real approval center.
- Global heavy header and abnormal-task banner should not consume every page. Each page should have scoped, compact status affordances.

Home page design direction:

- Use three fixed sections:
  - Current runtime posture.
  - Task-flow subway map.
  - Action Queue.
- Current runtime posture should show only a few high-signal facts:
  - Current Run, such as `Live Round 1`.
  - Runtime state, such as running, blocked, or waiting for user.
  - Action-required count.
  - Open gate count.
  - Last sync time.
- Avoid large KPI card clusters on Home.

Home task-flow subway map requirements:

- Home subway map should show the main path only, not every detail.
- Clicking any node should open the richer run/task detail page.
- Node types:
  - Circle: task.
  - Diamond: gate.
  - File icon: artifact.
  - Agent avatar: assignment.
- State colors:
  - Green: completed / passed.
  - Yellow: in progress / waiting confirmation.
  - Red: failed / blocked.
  - Gray: not started / no data.
  - Purple: QA / review, if review state must be distinguished.
- Line semantics:
  - Dotted line: unmet dependency.
  - Bold line: current main path.

Home Action Queue requirements:

- Home should prioritize action queues over decorative metrics.
- Required buckets:
  - Needs user handling.
  - Needs Controller handling.
  - Open gates.
  - Abnormal tasks.
  - Recently completed.
- Each item should provide specific actions, such as:
  - Send message to Controller.
  - Reassign.
  - Request QA.
  - Open gate.
  - View artifact.
  - Mark as known.

Runs / task-flow page requirements:

- The current run list with run ids and static stage labels is not enough.
- A run detail view should contain:
  - Run Summary: run id, title/objective, created/started/updated/finished timestamps, current stage, blocking reason, Controller owner.
  - Agent Assignment: Controller, workers, QA agents, helpers, and each Agent's current task.
  - Task Lane: task status, progress, owner, dependencies, latest scoped event.
  - Gate Lane: gate type, state, owner, requester, decision maker, approval/rejection reason.
  - Artifact Lane: related screenshots, reports, logs, handoff documents.
  - Event Timeline: events scoped to this run only, not the global event stream.

Bug investigation to track separately:

- The issue where all runs show `已创建` / `created` should be investigated as a possible data/projection/UI bug.
- Check whether:
  - Backend never updates the projection.
  - Frontend renders static stage labels.
  - Run and task state are not joined correctly.
  - Events exist but the projection consumer does not process them.
  - Projection has correct state but UI does not read it.

Communication Console protocol requirements:

- Communication messages are Bus command/message projections, not ordinary chat messages.
- Minimum UI-facing message model should include fields like:

```json
{
  "message_id": "msg_...",
  "bus_event_id": "evt_...",
  "thread_id": "thread_...",
  "space_id": "space_exception",
  "sender": {
    "agent_id": "controller-agent",
    "name": "Controller Agent",
    "roles": ["controller"]
  },
  "recipients": [
    {
      "agent_id": "runtime-worker-2",
      "name": "runtime-worker-2",
      "roles": ["worker"]
    }
  ],
  "message_type": "instruction",
  "delivery_state": "sent",
  "ack_state": "waiting_ack",
  "reply_state": "waiting_reply",
  "priority": "high",
  "body": "请优先处理 Worker2 CLI child fail。",
  "links": {
    "run_id": "run_58a11729",
    "task_ids": ["task_7472c79"],
    "gate_ids": ["gate_66e3413e"],
    "artifact_ids": []
  },
  "created_at": "2026-05-29T10:12:00+08:00",
  "updated_at": "2026-05-29T10:13:00+08:00"
}
```

- UI states such as `已送达`, `已确认`, and `等待回复` should come from this projection or equivalent Bus data, not from fabricated local UI state.
- Communication should preserve record links to run/task/gate/artifact/report.

Artifacts page requirements:

- Reading a fixed local artifact directory is appropriate, but bare filename scanning is not enough.
- Prefer a manifest-based artifact layout:

```text
.agent-bus/
  artifacts/
    run_58a11729/
      task_7472c79/
        manifest.json
        screenshot-home.png
        qa-report.md
        trace.log
        handoff.md
```

- Example `manifest.json`:

```json
{
  "artifact_id": "art_001",
  "run_id": "run_58a11729",
  "task_id": "task_7472c79",
  "agent_id": "worker2",
  "type": "screenshot",
  "title": "Home overview screenshot",
  "path": "screenshot-home.png",
  "created_at": "2026-05-29T10:12:00+08:00",
  "summary": "Screenshot evidence for overview layout issue"
}
```

- Frontend should read artifacts through a backend API that resolves paths only under the configured artifact root.
- The backend should expose relative paths safely and prevent arbitrary filesystem reads.
- This approach is simpler than upload-to-server and safer than unstructured directory scanning.

Visual and interaction design requirements:

- Reduce large generic white cards.
- Use a controlled console panel system: light gray app background, fewer high-priority white panels, and compact control surfaces.
- Critical exceptions should use narrow red indicators or focused panels instead of oversized red blocks that dominate every page.
- Establish a stable state color language:
  - Green: completed / passed.
  - Yellow: in progress / waiting.
  - Red: blocked / failed.
  - Purple: QA / review.
  - Gray: not started / no data.
  - Blue: primary action only.
- IDs should be secondary visual information.
- Default to short ids; expose full ids on hover, click, copy, or detail view.
- Human-readable task/run titles should be the primary card title when available.
- Language rules:
  - Page titles should use Chinese.
  - Object types may remain English, such as `Run`, `Task`, `Gate`, `Artifact`, and `Agent`.
  - Status and action buttons should use Chinese.
- Avatars and icons should improve recognition, not exist only for style.
- Suggested role silhouettes:
  - Controller: command tower / dispatcher.
  - Worker: tool / wrench / robot.
  - QA: shield / magnifier.
  - Helper: plugin / circuit.
  - Observer: archive / eye.
- Pixel style is acceptable only if readability remains strong.

Implementation guardrails:

- Do not build a generic monitoring dashboard.
- Do not add fake telemetry to make the UI look complete.
- Do not duplicate the same summary cards across Home, Communication, Gates, and Runs.
- Do not allow user instructions to bypass Agent Bus.
- No frontend code changes should be made from this comment yet. This is input for a later unified modification plan.

## Comment 15 - Conflict Resolution And Next Implementation Plan

Date: 2026-05-29

Source:

- User-provided correction request after Comment 14.
- Scope: comments consistency, MVP implementation guardrails, and next multi-agent implementation plan.

Resolved conflicts:

- Status colors are unified:
  - Green: completed / passed.
  - Yellow: in progress / waiting for confirmation.
  - Red: failed / blocked / rejected.
  - Gray: not started / no data.
  - Purple: QA / review.
- The old global `检查器` should be deleted, but page-scoped right-side detail panels remain valid when they show observable task, gate, message, artifact, or Agent facts.
- The old global `指令台` / Command Console should be deleted, but page-scoped Bus-backed composers remain valid when they create structured Bus records.
- The normal product UI must not show hidden Codex subagent conversation-internal trust, quality, or reliability claims.
- MVP Home removes global success-rate metrics. Rate-like metrics belong only in Diagnostics after formula, denominator, sample window, and source events are documented.

Implementation plan:

- Detailed next-phase plan: [2026-05-29-agent-bus-frontend-product-restructure.md](superpowers/plans/2026-05-29-agent-bus-frontend-product-restructure.md)
- Absolute plan path: `C:\Users\laptopofzy\Documents\Agent bus\docs\superpowers\plans\2026-05-29-agent-bus-frontend-product-restructure.md`
- The plan uses serial QA gates with parallel worker execution:
  - `runtime-worker-1`: app shell, Home, action queue.
  - `runtime-worker-2`: Communication Console and Bus message projection.
  - `runtime-worker-3`: Runs, Gates, Artifacts, manifest API.
  - `runtime-worker-4`: Diagnostics, visual system, icons, responsive layout.
  - `runtime-helper-1`: coordination and wave board.
  - `runtime-helper-2`: service/browser/artifact support.
  - `runtime-qa`: gate validation between waves.
- No frontend code changes should be made from this comment itself. It records the plan and guardrails for the next implementation wave.
