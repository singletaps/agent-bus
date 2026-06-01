# Live Real-Service Test Round 1

Controller: `runtime-helper-1`

Live service: http://127.0.0.1:8787/

Live DB: `coordination/live-agent-bus.sqlite3`

Fallback bus: `coordination/agent-bus.ndjson`

## Objective

Exercise the real Agent Bus service with all runtime agents logged in, capture user-visible issues, and report actionable feedback through the live service and fallback bus.

## Run And Gate

- Run: `run_58a1172913424831922f7942ee0cf51c`
- Gate: `gate_66e3413ede3e4fbab5aa0cb8021785e0`
- Gate owner: `runtime-helper-1`
- Gate pass condition: workers 1-4 each complete the assigned live task or report a precise blocker, and helper-1 records the issues and final recommendation.

## Current Known Issue

Live feedback `seq=31`: user closed QA, but the UI still shows QA as `STANDBY_READY`.

Current read-only triage suggests the backend has no explicit session close/end or heartbeat-expiry projection, so the UI is rendering the last durable active session state.

## Assignments

### Worker 1

- Task: `task_7ae9e0ac561b49c885f49d04d8016dd2`
- Title: verify QA close/session lifecycle and backend projection behavior.
- Focus: backend agent lifecycle, session health, projection state, and whether a server/API fix is needed.
- Report: root cause, proposed owner split, and any minimal safe fix proposal.

### Worker 2

- Task: `task_9d3ed4235bdd4be6a360a0a53af17010`
- Title: exercise CLI wait/ack/task/gate/review commands on live DB.
- Focus: CLI behavior against `coordination/live-agent-bus.sqlite3`, including task state changes, wait/ack, review/gate commands, and JSON output quality.
- Report: command transcript summary, broken commands, missing commands, or confusing schema.

### Worker 3

- Task: `task_0112dd2aa06c4e5ca5257dabdedf4d24`
- Title: exercise Operations Console UI flows with real backend data.
- Focus: Operations, Agents, Gates, RunGraph, Artifacts, Settings, Replacement Dock, Inspector, Command Composer, refresh behavior, and live event visibility.
- Report: UI issues, stale data, console errors, and whether user feedback appears in the right place.

### Worker 4

- Task: `task_f97d109f674d42c9a72353ea47e9d59a`
- Title: audit docs against real-service workflow and capture gaps.
- Focus: whether current docs explain live startup, agent login, fallback bus use, live feedback capture, and test-task workflow.
- Report: doc gaps and proposed documentation changes.

## Reporting Protocol

Each worker should:

1. Use the live service and live DB for the assigned test.
2. Post a fallback-bus status when starting and when ready/blocked.
3. Record findings as concrete issue notes with evidence, affected file/module if known, and suggested owner.
4. Avoid product-code edits unless explicitly assigned after triage.
5. Leave the current fallback bus active for recovery and user feedback forwarding.

## Helper-1 Duties

- Keep appending user feedback to `USER_FEEDBACK.md`.
- Forward live `operations-console` feedback to workers and QA.
- Coordinate task ownership and blockers.
- Close or escalate `gate_66e3413ede3e4fbab5aa0cb8021785e0` after worker reports are in.

## Results

Status: all four primary worker tasks completed.

### Worker 1 Result

- Task `task_7ae9e0ac561b49c885f49d04d8016dd2`: completed.
- Artifact: `artifact_fd812b69db784ea887840872df37e20e`.
- Finding: QA remained `STANDBY_READY` because the live runtime has no explicit heartbeat/session-close/session-end event path, and the projection faithfully renders the last persisted active `AgentHealth`.
- Recommended owner split: backend lifecycle/API/CLI should add heartbeat or explicit session close/end-state; projection should surface stale/ended state; UI should display stale/ended once backend emits it.

### Worker 2 Result

- Task `task_9d3ed4235bdd4be6a360a0a53af17010`: completed.
- Artifact: `artifact_61d1708dfc4c4ce5bef061ca7293afc7`.
- Coverage: CLI task ack/progress/complete, review request/submit/resolve, child task create/progress/complete/fail, gate create/approve/reject/escalate, artifact create, wait/ack behavior.
- Finding: malformed `--metadata-json` in nested PowerShell automation returned structured JSON error; artifact creation succeeded when metadata was omitted. No blocker.

### Worker 3 Result

- Task `task_0112dd2aa06c4e5ca5257dabdedf4d24`: completed.
- Artifact: `artifact_4e9f7a7abdd045b49651221608883073`.
- Coverage: live console loaded real data; Agents, Gates, RunGraph, Artifacts, Settings, Command Composer, and Replacement Dock were exercised; no browser console errors or mock tokens.
- Finding: Command Composer used the current default selected task `task_7ae9e0ac561b49c885f49d04d8016dd2` while the target was `runtime-worker-3`, causing affected agents to include both `runtime-worker-1` and `runtime-worker-3`.
- Recommendation: make selected task display/selection explicit and require confirmation when target agent and selected task owner/assignee differ.

### Worker 4 Result

- Task `task_f97d109f674d42c9a72353ea47e9d59a`: completed.
- Artifact: `artifact_5b425ce0`.
- Coverage: docs audited against live DB/port override, task assignment without context packet, task ack flow, and QA close/lifecycle gap.
- Finding: docs needed live workflow clarifications; Worker 4 reported docs patches and test verification (`python -m pytest -q` => 51 passed).

## Gate Decision

Gate `gate_66e3413ede3e4fbab5aa0cb8021785e0` can be approved for Round 1 because all assigned test tasks completed and findings are documented. Follow-up product work should be split into separate tasks rather than folded into this test gate.
