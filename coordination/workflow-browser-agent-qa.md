# Workflow Browser And Agent Simulation QA

Date: 2026-05-29

## Scope

This QA pass covers:

- Home action queue workflow behavior: each action item should own a workflow/metro context instead of sharing only one global Home map.
- Communication page controls: range filters, unread toggle, agent follow selection, composer recipients, send behavior, and detail rail.
- Layout stability: desktop and mobile screenshots, no horizontal overflow, no clipped primary controls.
- Runtime simulation: four local simulated agents register against the live SQLite-backed Agent Bus server, heartbeat, receive messages/tasks, and expose role/state changes through `/api/projections/operations`.
- User simulation: browser acts as the operator and creates/sends work through the UI or API, then checks workflow/state/message projections.

## Design Decision

Action queue items will keep the large Home map as the active run overview, but each action card will also render its own compact workflow strip derived from the same backend `ui.metro`. This keeps Home globally understandable while making every action item carry the concrete workflow path that justifies the action.

Communication filters will become observable state changes:

- Range `all`: all messages in the active communication space.
- Range `sent`: messages sent by `operator`, `controller`, or another local console actor.
- Range `mine`: messages addressed to selected operator-like agents, or if none exist, messages involving `operator`/`controller`.
- Range `followed`: if an agent is selected, only messages involving that agent; if no agent is selected, show an empty state telling the user to select an agent.
- Unread only: messages whose ack state is not `acked`, `delivered`, or `not_required`.

## Running Notes

### Initial Hypotheses

1. Home has one global metro graph; action queue cards do not show their own workflow context.
2. Communication range filters likely click visually but do not change message rows enough, especially `mine` and `followed`.
3. Simulated agents can register through the CLI using the same live DB, while the browser and API observe their state through the running 8787 server.

### Evidence Log

- Browser reproduction before fixes:
  - Screenshot: `coordination/workflow-qa-communication-repro.png`.
  - Range buttons changed selected visual state, but the page lacked a stable message-list boundary for QA and `followed` without selected agent behaved like a broad list instead of a clear empty state.
  - Message detail could remain attached to an old message after range changes.
- Implemented:
  - Home action cards now render their own compact workflow strip from backend `ui.metro`.
  - Communication message cards now have stable `.communicationMessageCard` / `.communicationMessageList` selectors.
  - Communication detail selection follows filtered results.
  - `sent`, `mine`, `followed`, and unread space counts now use explicit filter semantics.
- Browser verification after fixes:
  - Home screenshot: `coordination/workflow-qa-home-action-workflows-v2.png`.
  - Home rendered 5 action cards, 5 per-action workflow strips, and 15 compact workflow steps; no horizontal overflow at 1460 px.
  - Communication screenshot: `coordination/workflow-qa-communication-filter-semantics.png`.
  - Range filters now produce distinct observable states: `all` = 3 daily cards, `sent` = 3, `@ mine` = 0 with an empty state, `followed` = 0 until an Agent is selected, then Runtime QA follow scope = 3.
  - Empty message scopes now switch the right rail to Agent detail instead of preserving an unrelated old message.
- Four-agent live simulation:
  - Registered `sim-controller-20260529163859`, `sim-frontend-20260529163859`, `sim-backend-20260529163859`, and `sim-qa-20260529163859` against `coordination/live-agent-bus.sqlite3`.
  - Started four hidden wait processes, one per agent, writing logs to `coordination/sim-agent-20260529163859-*.log`.
  - Browser/user assignment created `run_b80a7e1c2086444aa58b050c06126d62` and `task_bc7d744bede0453895f4e082069ec18e`; frontend received `task_assigned` and user instruction inbox items.
  - Replacement approval delivered `replacement_notice` to backend and changed the old frontend session to `REPLACED`, but initial live evidence showed the task assignee still pointed at old frontend.
- Backend fix:
  - Replacement approval now reassigns the canonical task to the replacement agent, emitting `task.reassigned` and a replacement assignee inbox item.
  - Live verification after server restart used `run_c7cd510fcffe49a28ffc359f0f3a2705` and `task_cc7c58cb0cf34edabf115be769cdaa2e`.
  - Fixed evidence: old frontend session = `REPLACED`, replacement backend session = `REHYDRATING`, task state = `reassigned`, task assignee = `sim2-backend-20260529164452`.
- Final browser verification:
  - Desktop Home: `coordination/workflow-qa-final-home-desktop.png`; 5 action cards, 5 per-action workflow strips, 16 compact workflow steps, no horizontal overflow.
  - Communication UI send: `coordination/workflow-qa-final-communication-ui-send.png`; browser submitted a real instruction to `sim2-backend-20260529164452`, API projected `msg_4bd4ba29465d49bfb5ac3abf22e9aeef` with `waiting_ack`.
  - Runs: `coordination/workflow-qa-final-runs-assignee.png`; reassigned task shows backend assignee.
  - Gates: `coordination/workflow-qa-final-gates.png`; QA gate is visible with owner `sim2-qa-20260529164452`.
  - Mobile Home: `coordination/workflow-qa-final-home-mobile.png`; 5 action cards, 5 workflow strips, no horizontal overflow at 390 x 844.
- Final commands:
  - `pytest -q`: 67 passed.
  - `npx tsc --noEmit`: passed.
  - `npx vite build`: passed.
  - 8787 was restarted after the backend fix; current server process is listening on port 8787.

## Residual Notes

- The first four-agent run intentionally left delivered-but-unacked inbox items so the UI could expose real waiting/attention states.
- Replacement approval now reassigns active/non-terminal tasks. Terminal tasks keep their completed/failed/superseded state while still allowing historical replacement context approval.
