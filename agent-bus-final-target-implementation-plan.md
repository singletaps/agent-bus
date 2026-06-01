# Agent Bus Final Target Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the final-target Agent Bus as a durable local operations control plane for permanent Codex subagents.

**Architecture:** Replace the current NDJSON-first chat broker with a SQLite event-sourced runtime, per-agent inboxes, long-blocking wait/ack APIs, context packets, identity/session separation, health and capability degradation, replacement workflows, FastAPI APIs, and a React operations console. Keep the old personal plugin implementation as reference and compatibility source, but treat this current workspace as the handoff location for subagents.

**Tech Stack:** Python 3, SQLite WAL, FastAPI, Pydantic, pytest, Vite, React, TypeScript, Tailwind/shadcn-style UI, Server-Sent Events.

---

## Source Context

Important facts from that thread:

- The original lightweight plugin was created as `codex-agent-bus`.
- Existing implementation reference is currently at `C:\Users\laptopofzy\plugins\codex-agent-bus`.
- Existing shape is a single Python broker/CLI with NDJSON persistence, SSE delivery, static web UI, tests, and plugin metadata.
- Current requested handoff directory is `C:\Users\laptopofzy\Documents\Agent bus`.
- Do not assume the previous WSL LobeHub path is the active project path.
- Final target is not a hard security sandbox. Lease, intent, gate, and review states are coordination contracts and visualization primitives.
- Agents are permanent listeners. No shutdown/closing protocol should be designed. After a task, an agent returns to standby and keeps listening.
- Codex context compression can fail. Capability discovery, session health, input availability, rehydration, and replacement are first-class requirements.

## Locked Product Decisions

- Replacement policy: Bus recommends candidates; controller approves ordinary replacement; user can override or approve high-risk reassignment.
- Capability source: hybrid confidence from declared, probed, observed, QA-confirmed, and user-assigned evidence.
- Health checks: long blocking wait where possible, sparse probes only when stale, high-priority, or recovery-sensitive.
- Wait model: longest feasible blocking wait plus timeout noop, not true infinite blocking.
- Storage model: SQLite event log is the source of truth. NDJSON remains optional import/fallback compatibility only.
- Context model: agents receive minimal actionable context packets, not raw event-log replay by default.
- Human interrupt: user interruption invalidates affected context packets and notifies all affected agents.

## Target Repository Layout

Subagents should create or migrate toward this layout in the active implementation workspace:

```text
.
├── agent_bus/
│   ├── __init__.py
│   ├── __main__.py
│   ├── agents.py
│   ├── cli.py
│   ├── context.py
│   ├── db.py
│   ├── gates.py
│   ├── inbox.py
│   ├── models.py
│   ├── projections.py
│   ├── replacement.py
│   ├── reviews.py
│   ├── router.py
│   ├── server.py
│   ├── store.py
│   └── tasks.py
├── frontend/
│   ├── index.html
│   ├── package.json
│   ├── src/
│   └── vite.config.ts
├── scripts/
│   ├── agent-bus
│   ├── agent-bus.ps1
│   └── agent_bus.py
├── skills/
│   └── agent-bus/
│       └── SKILL.md
├── tests/
│   ├── test_agents.py
│   ├── test_context.py
│   ├── test_inbox.py
│   ├── test_replacement.py
│   ├── test_server.py
│   ├── test_store.py
│   └── test_tasks_gates_reviews.py
├── docs/
│   ├── operator-manual.md
│   ├── protocol.md
│   ├── recovery-playbook.md
│   └── subagent-contracts.md
├── README.md
└── pyproject.toml
```

`C:\Users\laptopofzy\plugins\codex-agent-bus` should be treated as reference material. If the implementation happens in this current repo, copy/migrate only the useful behavior, not the old one-file structure.

## Coordination Rules For Subagents

- Each subagent must announce its ownership files before editing.
- No two subagents should edit the same file in the same wave unless the integrator explicitly assigns that merge.
- Every subagent writes a short completion note with changed files, tests run, and unresolved risks.
- Use the existing Agent Bus if available for coordination:

```powershell
$AgentBus = "$HOME\plugins\codex-agent-bus\scripts\agent-bus.ps1"
& $AgentBus serve --host 127.0.0.1 --port 8765
& $AgentBus join lead-architect
```

- If the existing Agent Bus is unavailable, use file fallback:

```text
coordination/messages.ndjson
coordination/agent-status.md
coordination/wave-gates.md
```

- Fallback message shape:

```json
{"ts":"2026-05-28T00:00:00Z","from":"backend-store","to":"integrator","type":"status","text":"Wave A store tests pass","files":["agent_bus/db.py","agent_bus/store.py"]}
```

## Wave Overview

Execution should be serial at gates and parallel inside waves:

1. Serial Wave 0: architecture and skeleton freeze.
2. Parallel Wave A: core foundation.
3. Serial Gate 1: foundation integration.
4. Parallel Wave B: runtime semantics.
5. Serial Gate 2: runtime integration.
6. Parallel Wave C: API, CLI, frontend, docs.
7. Serial Gate 3: end-to-end acceptance.

## Wave 0: Architecture Freeze

Owner: `lead-architect`.

**Files:**
- Create: `pyproject.toml`
- Create: `agent_bus/__init__.py`
- Create: `agent_bus/__main__.py`
- Create: `agent_bus/models.py`
- Create: `scripts/agent_bus.py`
- Create: `scripts/agent-bus.ps1`
- Create: `scripts/agent-bus`
- Create: `README.md`

- [ ] Step 1: Define the package skeleton and command entrypoint.

Expected command:

```powershell
python -m agent_bus --help
```

Expected result:

```text
usage: agent-bus ...
```

- [ ] Step 2: Create the first shared Pydantic models in `agent_bus/models.py`.

Required model names:

```text
BusEvent
EventType
AgentIdentity
AgentSession
AgentRuntimeState
AgentHealth
AgentCapability
InboxItem
ContextPacket
TaskRecord
GateRecord
ReviewFinding
ArtifactRecord
```

- [ ] Step 3: Add wrappers so old calling style still works.

PowerShell wrapper must call:

```powershell
python -m agent_bus @args
```

POSIX wrapper must call:

```bash
python -m agent_bus "$@"
```

- [ ] Step 4: Commit or hand off skeleton before parallel work begins.

Acceptance:

- `python -m agent_bus --help` works.
- Wrappers call the package entrypoint.
- Every planned module imports without side effects.
- Subagents can work in separate ownership files.

## Wave A: Core Foundation

### Task A1: SQLite And Event Store

Owner: `backend-store`.

**Files:**
- Create: `agent_bus/db.py`
- Create: `agent_bus/store.py`
- Modify: `agent_bus/models.py`
- Test: `tests/test_store.py`

- [ ] Step 1: Implement SQLite connection helpers.

Required behavior:

- Default DB path: `~/.codex-agent-bus/agent-bus.sqlite3`.
- Override with `--db PATH` or `AGENT_BUS_DB`.
- Enable WAL mode.
- Create `schema_migrations` and `event_log`.

- [ ] Step 2: Implement append-only event store.

`event_log` must contain:

```text
seq integer primary key autoincrement
event_id text unique not null
type text not null
ts text not null
actor text
run_id text
task_id text
agent_id text
correlation_id text
causation_id text
payload_json text not null
```

- [ ] Step 3: Implement replay/query APIs.

Required functions:

```text
append_event(event)
get_event(event_id)
query_events(after_seq=None, event_type=None, run_id=None, task_id=None, agent_id=None, limit=None)
replay_all()
```

- [ ] Step 4: Write tests for migration, append, ordering, and filtering.

Acceptance:

- Concurrent append produces stable increasing `seq`.
- Replay order is deterministic.
- Event payload round-trips without losing correlation/causation.

### Task A2: Agent Identity, Session, Health, Capability

Owner: `backend-agent-model`.

**Files:**
- Create: `agent_bus/agents.py`
- Modify: `agent_bus/models.py`
- Test: `tests/test_agents.py`

- [ ] Step 1: Implement durable `AgentIdentity`.

Identity survives session loss and replacement.

- [ ] Step 2: Implement replaceable `AgentSession`.

A single identity can have multiple sessions, with one active session.

- [ ] Step 3: Implement health states.

Required runtime states:

```text
WAITING_ON_BUS
WAIT_RETURNED_NOOP
DELIVERED_NOT_ACKED
WORKING
SUSPECTED_STUCK
INPUT_UNAVAILABLE
CONTEXT_LOST
NEEDS_REHYDRATION
REHYDRATING
STANDBY_READY
STANDBY_DEGRADED
REPLACED
```

- [ ] Step 4: Implement capability confidence.

Capability evidence sources:

```text
declared
probed
observed
qa_confirmed
user_assigned
```

Acceptance:

- Same identity can create multiple sessions.
- Active session can switch without deleting identity.
- Context loss degrades session health but does not erase capability history.
- Capability confidence and freshness update from evidence.

### Task A3: Per-Agent Inbox, Wait, Ack

Owner: `backend-inbox-wait`.

**Files:**
- Create: `agent_bus/inbox.py`
- Modify: `agent_bus/models.py`
- Test: `tests/test_inbox.py`

- [ ] Step 1: Add `inbox_items` table migration.

Required columns:

```text
inbox_id text primary key
agent_id text not null
priority integer not null
kind text not null
status text not null
payload_json text not null
context_packet_id text
dedupe_key text
visible_at text not null
delivered_at text
acked_at text
expires_at text
created_at text not null
```

- [ ] Step 2: Implement enqueue, wait, ack, and redelivery.

Required behavior:

- `wait(agent, timeout)` blocks until an item is visible or timeout expires.
- Timeout returns noop.
- Highest priority item wins.
- Delivered but unacked item becomes visible after visibility timeout.
- `dedupe_key` prevents duplicate wakeups.

- [ ] Step 3: Implement busy-agent filtering.

Busy agents should receive only high-priority items:

```text
user_interrupt
context_invalidated
agent_replan_required
gate_result
replacement_notice
```

Acceptance:

- No item: wait blocks until timeout and returns noop.
- Multiple items: highest priority item is delivered first.
- Unacked delivered item is redelivered.
- Dedupe prevents repeated equivalent wakeups.

### Task A4: Frontend Mock Shell

Owner: `frontend-shell`.

**Files:**
- Create: `frontend/package.json`
- Create: `frontend/index.html`
- Create: `frontend/src/main.tsx`
- Create: `frontend/src/App.tsx`
- Create: `frontend/src/styles.css`

- [ ] Step 1: Create Vite React TypeScript app shell.

- [ ] Step 2: Build mock operations console pages.

Required views:

```text
Operations
Agents
Gates
Timeline
Inspector
Replacement Dock
```

- [ ] Step 3: Use mock data only in Wave A.

Acceptance:

- `npm run build` succeeds.
- UI can render without backend.
- Layout shows agent dock, task board, gate center, timeline, and inspector.
- UI is dense, operational, and not a marketing page.

## Gate 1: Core Foundation Integration

Owner: `integrator` plus `qa-gatekeeper`.

- [ ] Step 1: Run Python tests for Wave A.

```powershell
pytest tests/test_store.py tests/test_agents.py tests/test_inbox.py -v
```

- [ ] Step 2: Verify package CLI.

```powershell
python -m agent_bus init --reset
python -m agent_bus agent register controller --role controller --json
python -m agent_bus wait --agent controller --timeout 1 --json
```

Expected:

- DB initializes.
- Controller identity/session is created.
- Wait returns noop after timeout.

- [ ] Step 3: Verify frontend mock build.

```powershell
cd frontend
npm run build
```

Gate pass criteria:

- Wave A tests pass.
- DB can initialize and reset.
- `event_log -> inbox -> wait -> ack` path works.
- Frontend mock build succeeds.

## Wave B: Runtime Semantics

### Task B1: Context Packet

Owner: `context-packet`.

**Files:**
- Create: `agent_bus/context.py`
- Modify: `agent_bus/models.py`
- Test: `tests/test_context.py`

- [ ] Step 1: Add `context_packets` table migration.

Required fields:

```text
packet_id
version
agent_id
task_id
run_id
status
summary
instructions_json
artifact_refs_json
created_from_event_id
supersedes_packet_id
superseded_by_packet_id
invalidated_by_event_id
created_at
invalidated_at
```

- [ ] Step 2: Implement create/get/invalidate/supersede.

- [ ] Step 3: Implement rehydration packet creation.

Rehydration packet must include:

```text
role contract
current task
last known summary
open inbox item ids
required artifacts
next action
invalidated packet ids
```

Acceptance:

- Wait item can reference a context packet.
- Invalidated packet returns a structured invalidated error.
- Superseded packet points to the replacement packet.

### Task B2: Human Interrupt Propagation

Owner: `human-interrupt`.

**Files:**
- Create: `agent_bus/router.py`
- Modify: `agent_bus/inbox.py`
- Modify: `agent_bus/context.py`
- Test: `tests/test_context.py`
- Test: `tests/test_inbox.py`

- [ ] Step 1: Implement `user.interrupt_created` event.

- [ ] Step 2: Compute affected agents.

Affected agents:

```text
controller
observer
task owner
task assignee
helper agents
QA agent
gate owner
downstream dependent task owners
```

- [ ] Step 3: Enqueue high-priority items.

Required items:

```text
context_invalidated
agent_replan_required
user_interrupt
```

Acceptance:

- Interrupting a running task wakes owner/helper/QA/controller/observer.
- Unrelated standby agents are not woken.
- Active context packets for affected agents are invalidated.

### Task B3: Replacement And Rehydration

Owner: `replacement-health`.

**Files:**
- Create: `agent_bus/replacement.py`
- Modify: `agent_bus/agents.py`
- Modify: `agent_bus/context.py`
- Test: `tests/test_replacement.py`

- [ ] Step 1: Implement stale/session-suspect rules.

Triggers:

```text
missing heartbeat
wait item delivered but not acked
reported context loss
input unavailable
manual controller mark
```

- [ ] Step 2: Score replacement candidates.

Inputs:

```text
capability confidence
freshness
standby readiness
recent failure history
role compatibility
user assigned preference
```

- [ ] Step 3: Implement controller approval.

Approval must:

- keep `task_id` stable
- create replacement session or activate standby session
- create rehydration packet
- mark old session `REPLACED` or `STANDBY_DEGRADED`

Acceptance:

- Stale session produces replacement recommendation.
- Controller approval switches active session.
- Replacement agent receives rehydration packet with the same task.

### Task B4: Run, Task, Gate, Review

Owner: `task-gate-review`.

**Files:**
- Create: `agent_bus/tasks.py`
- Create: `agent_bus/gates.py`
- Create: `agent_bus/reviews.py`
- Modify: `agent_bus/models.py`
- Test: `tests/test_tasks_gates_reviews.py`

- [ ] Step 1: Implement run/task state machines.

Task states:

```text
created
assigned
acknowledged
working
blocked
completed
failed
superseded
reassigned
```

- [ ] Step 2: Implement gates.

Gate states:

```text
open
approved
rejected
escalated
expired
```

- [ ] Step 3: Implement structured review findings.

Finding fields:

```text
finding_id
severity
category
file_path
evidence
requested_change
blocking
resolved_by
status
```

- [ ] Step 4: Keep lease/intent as coordination records.

Do not enforce permissions through lease/intent.

Acceptance:

- Completed task returns agent to `STANDBY_READY`.
- `changes_requested` creates worker inbox items.
- High-risk gate creates user/controller action item and is not auto-approved.
- Findings can be resolved one by one.

## Gate 2: Runtime Integration Acceptance

Owner: `integrator` plus `qa-gatekeeper`.

Run this scenario end to end:

- [ ] Register six default agents.
- [ ] Create a run.
- [ ] Wake controller with plan item.
- [ ] Controller creates frontend/backend tasks.
- [ ] Workers wait and receive `task_assigned`.
- [ ] Worker acknowledges and fetches context packet.
- [ ] Worker reports progress.
- [ ] User interrupt is created.
- [ ] Affected agents receive `agent_replan_required`.
- [ ] `worker.frontend` becomes stale.
- [ ] Bus recommends replacement.
- [ ] Controller approves replacement.
- [ ] Replacement session receives rehydration packet and continues same task.

Gate pass criteria:

- All events replay in order.
- Projection can rebuild from event log.
- Agents do not read raw log as default context.
- Wait returns a minimal actionable item, not an entire transcript.

## Wave C: API, CLI, Frontend, Docs

### Task C1: FastAPI Server

Owner: `fastapi-server`.

**Files:**
- Create: `agent_bus/server.py`
- Modify: `agent_bus/projections.py`
- Test: `tests/test_server.py`

- [ ] Step 1: Implement API app.

Required endpoints:

```text
GET  /api/events/stream
GET  /api/agents
GET  /api/sessions
GET  /api/runs
GET  /api/tasks
POST /api/inbox/wait
POST /api/inbox/ack
GET  /api/context/{id}
POST /api/interrupt
GET  /api/replacement/recommendations
POST /api/replacement/approve
GET  /api/projections/operations
```

- [ ] Step 2: Serve frontend static build.

- [ ] Step 3: Ensure every API returns Pydantic-shaped JSON.

Acceptance:

- SSE dashboard updates when events append.
- Wait API supports long timeout and client cancel.
- OpenAPI schema is available.
- Static frontend is served by backend.

### Task C2: CLI

Owner: `cli-worker`.

**Files:**
- Create: `agent_bus/cli.py`
- Modify: `agent_bus/__main__.py`
- Modify: `scripts/agent_bus.py`
- Test: relevant CLI tests in `tests/`

- [ ] Step 1: Implement operational commands.

Required commands:

```text
serve
init --reset
seed
agent register
wait
ack
context get
task create
task progress
task complete
task fail
review request
review submit
gate approve
gate reject
gate escalate
interrupt create
replacement approve
artifact create
```

- [ ] Step 2: Add `--json` to every command.

- [ ] Step 3: Add clear exit codes.

Acceptance:

- Every command supports `--json`.
- Windows PowerShell wrapper works.
- `wait --timeout 300` can long block.
- Errors return nonzero exit and structured JSON when `--json` is set.

### Task C3: React Operations Console

Owner: `react-console`.

**Files:**
- Modify: `frontend/src/`

- [ ] Step 1: Replace mock data with real `/api/projections/operations`.

- [ ] Step 2: Implement required pages.

Required pages:

```text
Operations
Agents
Gates
RunGraph
Artifacts
Settings
```

- [ ] Step 3: Implement required components.

Required components:

```text
TopHealthBar
AgentDock
ReplacementDock
TaskBoard
GateCenter
EventTimeline
Inspector
CommandComposer
```

Acceptance:

- UI shows identity vs session.
- UI shows health, context integrity, capability confidence.
- UI shows affected interrupt propagation.
- UI shows replacement recommendation and approval path.
- UI filters gate/review/task/timeline events.
- `npm run build` succeeds.

### Task C4: Prompt, Skill, Docs

Owner: `docs-prompts`.

**Files:**
- Modify: `README.md`
- Modify: `skills/agent-bus/SKILL.md`
- Create: `docs/operator-manual.md`
- Create: `docs/protocol.md`
- Create: `docs/recovery-playbook.md`
- Create: `docs/subagent-contracts.md`

- [ ] Step 1: Document startup and seed flow.

- [ ] Step 2: Document the subagent contract.

Must state:

- Bus is the runtime control plane.
- Agents keep listening after task completion.
- No shutdown protocol.
- Context packets are authoritative.
- Raw event replay is for diagnostics, not normal context.

- [ ] Step 3: Document replacement and recovery playbook.

Acceptance:

- A new Codex subagent can follow docs to register, wait, ack, fetch context, act, and return standby.
- Docs include exact commands for PowerShell.
- Docs explain fallback coordination while the bus itself is under construction.

## Gate 3: End-To-End Acceptance

Owner: `integrator`, `qa-gatekeeper`, and `controller`.

Run:

```powershell
python -m agent_bus init --reset
python -m agent_bus seed
python -m agent_bus serve --host 127.0.0.1 --port 8765
```

Then run at least three simulated agent loops:

```powershell
python -m agent_bus wait --agent controller --timeout 300 --json
python -m agent_bus wait --agent worker.frontend --timeout 300 --json
python -m agent_bus wait --agent qa --timeout 300 --json
```

Final acceptance scenario:

- [ ] Create run.
- [ ] Controller wakes and creates tasks.
- [ ] Worker receives task.
- [ ] Worker fetches context packet.
- [ ] Worker ack/progress works.
- [ ] User interrupt wakes affected agents.
- [ ] Stale worker session becomes `SUSPECTED_STUCK`.
- [ ] Replacement recommendation appears.
- [ ] Controller approves replacement.
- [ ] Standby agent takes over the same task.
- [ ] React UI shows active run, agent health, context integrity, capability confidence, pending inbox, task board, gate center, replacement dock, and timeline.

Final Definition of Done:

- SQLite is the primary source of truth.
- Event replay rebuilds projections.
- Wait/ack/context are stable runtime APIs.
- Agent identity/session/replacement are first-class models.
- Human interrupt has affected-agent propagation.
- Capability confidence and health degradation appear in UI.
- React console uses real backend data.
- Old wrapper/plugin entrypoints still work.
- Core flows have unit, integration, and simulated end-to-end tests.
- Documentation can guide a new Codex subagent to operate only through Agent Bus.

## Suggested Subagent Assignment

Serial roles:

- `lead-architect`: Wave 0 skeleton, naming, event envelope, ownership map.
- `qa-gatekeeper`: gate scripts, acceptance scenarios, regression checklist.
- `integrator`: merge waves, resolve interface drift, run full test suite.

Parallel Wave A:

- `backend-store`: SQLite and event store.
- `backend-agent-model`: identity/session/health/capability.
- `backend-inbox-wait`: inbox/wait/ack.
- `frontend-shell`: mock operations console.

Parallel Wave B:

- `context-packet`: context packet lifecycle.
- `human-interrupt`: affected-agent routing and invalidation.
- `replacement-health`: health degradation and replacement.
- `task-gate-review`: run/task/gate/review coordination.

Parallel Wave C:

- `fastapi-server`: API and SSE.
- `cli-worker`: CLI commands and wrappers.
- `react-console`: real frontend integration.
- `docs-prompts`: docs, skill, prompt contracts.

## Risk Register

- Interface drift risk: resolved by serial gates after each wave.
- Too much parallel editing risk: resolved by strict file ownership.
- Frontend mock diverges from backend risk: Wave C must replace mock data with real projection only.
- Context packet overgrowth risk: keep packets minimal and actionable.
- Replacement false positives: controller approval required before task handoff.
- Codex input failure: model as `INPUT_UNAVAILABLE` or `CONTEXT_LOST`, then rehydrate replacement session.

## First Commands For The Next Lead Agent

```powershell
Get-Location
git status --short
Test-Path 'C:\Users\laptopofzy\plugins\codex-agent-bus'
rg --files
```

Then decide whether to migrate reference files from `C:\Users\laptopofzy\plugins\codex-agent-bus` into this repo or implement fresh from the target layout. Do not keep the final code as a single-file Python broker.
