# Agent Bus Protocol Kernel v2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rebuild Agent Bus around an authoritative collaboration protocol: session fencing, worker-claim/controller-commit separation, context-packet task contracts, gate/review/replacement authority, and task-level workflow projections.

**Architecture:** SQLite remains the durable source of truth. All writes pass through a protocol kernel that validates actor authority, session epoch, fencing, task context, and projection effect before appending events or mutating state. Frontend screens become protocol projections instead of hand-assembled demo surfaces; the metro graph is scoped to one task workflow, not a global action queue.

**Tech Stack:** Python, SQLite, FastAPI, Pydantic, pytest, React 19, Vite, TypeScript, Radix UI, lucide-react, @xyflow/react, Playwright, Codex Agent Bus fallback broker.

---

## 0. Non-Negotiable Direction

This is a large refactor, not a minimum patch. The baseline breaker/fallback Agent Bus remains available for subAgent coordination while the product runtime is being rebuilt.

Required outcomes:

- Workers can report facts and claims, but cannot commit authoritative task, gate, review, replacement, or session state.
- Controllers, users, or explicit policy services commit authoritative state.
- Every worker write is fenced by `session_id`, `session_epoch`, and token validation.
- Context packets become task contracts, not optional blobs.
- The UI renders real protocol projections only. No fake workflow nodes, no hardcoded happy path, no frontend-only state invention.
- The metro graph correction is explicit: each task owns one workflow graph. Action queues list actionable items and may show tiny previews, but they do not connect unrelated tasks into one graph.
- Durable writes have exactly one business entry point: `ProtocolKernel` through `UnitOfWork`. Board, repository, coordinator, and projection classes cannot remain public authority gates.

## 1. Current Problems To Remove

Observed current-state issues that the refactor must eliminate:

- `agent_bus.tasks.TaskBoard.complete_task()` lets worker actors complete tasks directly.
- `docs/subagent-contracts.md` still documents the old `task complete` worker flow.
- `BusEvent` lacks session, epoch, context, gate, artifact, and fencing effect fields.
- `AgentSession` lacks explicit `session_epoch`, `session_role`, and fencing token hash.
- `ContextPacket.instructions` is too blob-like to enforce task contracts.
- Replacement currently combines approval, reassignment, and rehydration too tightly.
- API routes are role-mixed: worker, controller, user, and projection writes live side by side.
- Frontend `UiMetroProjection` is global/run-shaped and currently encourages cross-task graph composition.
- `TaskBoard`, `GateBoard`, and `ReplacementCoordinator` currently mix business authority, state mutation, event append, and inbox enqueue. v2 must split authority decisions from internal state mutation.

## 2. SubAgent Coordination Contract

All implementation agents use the fallback breaker bus during the refactor.

PowerShell setup:

```powershell
$AgentBus = "$HOME\plugins\codex-agent-bus\scripts\agent-bus.ps1"
$BusFile = "C:\Users\laptopofzy\Documents\Agent bus\coordination\agent-bus.ndjson"
$Broker = "http://127.0.0.1:8765"
& $AgentBus init --bus $BusFile
& $AgentBus serve --bus $BusFile --host 127.0.0.1 --port 8765
```

Every subAgent announces ownership before edits:

```powershell
& $AgentBus send kernel-agent --bus $BusFile --broker $Broker --to "*" "OWNERSHIP kernel: agent_bus/models.py agent_bus/db.py agent_bus/protocol.py tests/test_protocol_kernel.py"
& $AgentBus status kernel-agent --bus $BusFile --broker $Broker --state working --note "protocol schema and fencing"
```

Every subAgent uses these message prefixes:

- `OWNERSHIP <agent>: <files>` before editing.
- `READY <agent>: <tests> <files>` after focused verification.
- `BLOCKER <agent>: <reason> <needed-owner>` when blocked.
- `HANDOFF <agent>: <contract> <remaining-risk>` when another owner must continue.
- `GATE_PASS <qa-agent>: <scope> <evidence>` after independent QA.
- `GATE_FAIL <qa-agent>: <scope> <evidence>` for failed verification.

File ownership is exclusive within one wave. If two agents need the same file, the second agent waits for a `HANDOFF`.

## 3. Target Data Contracts

### 3.1 Event Envelope

`BusEvent` must carry these durable fields:

```text
seq
event_id
type
ts
actor
actor_role
run_id
task_id
agent_id
session_id
session_epoch
context_packet_id
gate_id
artifact_id
correlation_id
causation_id
projection_effect
fencing_result
payload_json
```

Allowed `projection_effect` values:

```text
COMMIT
AUDIT_ONLY
REJECT
```

Allowed `fencing_result` values:

```text
VALID
MISSING
INVALID
STALE_EPOCH
WRONG_SESSION
NOT_REQUIRED
```

Raw fencing tokens must never be written to `event_log`. Persist only token hash, validation result, and audit metadata.

`BusEvent.projection_effect` is a fast summary only. The `projection_effects` table is the authoritative diagnostics record because one event can be committed into diagnostics while remaining audit-only or rejected for task projections. Rejected writes may skip the main `event_log`, but they must create `protocol_violations` and `projection_effects` records.

### 3.1.1 Event Naming Convention

Normalize event names once during v2 so projections can distinguish worker claims from controller commits.

Worker claim/report events:

```text
task.ack_claimed
task.progress_reported
task.blocker_reported
task.completion_claimed
task.failure_claimed
artifact.produced
handoff.proposed
context.replan_requested
```

Controller commit events:

```text
task.acknowledged
task.started
task.blocked
task.completed
task.failed
task.reassigned
context.invalidated
```

Gate events:

```text
gate.opened
gate.approval_requested
gate.approved
gate.rejected
gate.escalated
gate.expired
```

Replacement events:

```text
replacement.recommended
replacement.approval_requested
replacement.approved
replacement.rejected
replacement.reassignment_committed
```

Protocol events:

```text
protocol.violation_recorded
projection.effect_recorded
session.stale_event
session.fencing_failed
adapter.deprecated_path_used
```

Do not keep broad names such as `gate.result` for v2 projection logic.

### 3.2 Identity, Session, Authority

`AgentIdentity` remains the stable identity:

```text
agent_id
role
display_name
created_at
updated_at
```

`AgentSession` becomes the fenced execution lease:

```text
session_id
agent_id
run_id
active
session_epoch
session_role
runtime_state
fencing_token_hash
max_concurrent_tasks
accepts_new_work
started_at
last_seen_at
ended_at
replaced_by_session_id
```

Allowed `session_role` values:

```text
primary
standby
replaced
quarantined
retired
```

Runtime state remains separate from authority:

```text
STANDBY_READY
WAITING_ON_BUS
DELIVERED_NOT_ACKED
WORKING
WAITING_FOR_COMMIT
WAITING_FOR_REVIEW
WAITING_FOR_GATE
STANDBY_DEGRADED
SUSPECTED_STUCK
INPUT_UNAVAILABLE
CONTEXT_LOST
NEEDS_REHYDRATION
REHYDRATING
REPLACED
```

`current_task_ids` is derived in an `AgentWorkloadProjection`, not stored as a mutable session field. `accepts_new_work` and `max_concurrent_tasks` determine whether an agent may receive more work while a claim, review, or gate is pending.

### 3.2.1 Principals, Authority, And Policy

Controller, user, system, and agent actors must be represented as principals, not trusted strings.

```text
principal_id
principal_type: user | controller | agent | system
agent_id
session_id
roles_json
permissions_json
created_at
updated_at
```

Authority is two-layered:

- `AuthorityService` checks static permission: principal type, role, and action.
- `PolicyService` checks contextual permission: task ownership, active context, no self-review, required artifacts, replacement eligibility, and candidate capability.

Examples:

```text
AuthorityService.allow("qa", "gate.approve")
PolicyService.validate_no_self_review(gate_id, actor_principal)
PolicyService.validate_required_artifacts(gate_id)
PolicyService.validate_context_active(context_packet_id)
PolicyService.validate_replacement_candidate(task_id, old_session_id, candidate_session_id)
```

Never implement v2 checks as string comparisons such as `actor == "controller"`. A worker that passes `--actor controller` must not gain controller authority.

### 3.2.2 Fencing Token Lifecycle

Token lifecycle is part of the protocol, not an implementation detail:

- Worker session registration generates one raw fencing token.
- The raw token is returned only in the registration response.
- SQLite stores only `fencing_token_hash`.
- Tokens are never emitted in event logs, projections, diagnostics, screenshots, or frontend state.
- Token rotation increments `session_epoch`.
- Replacement, quarantine, retire, and explicit revocation invalidate old tokens.
- Standby sessions may have tokens, but standby tokens cannot commit worker claims unless policy allows work for that session role.
- Deprecated worker adapters without token cannot synthesize one.

Deprecated worker writes with no token must produce `fencing_result=MISSING`. They may create an audit-only claim for diagnostics, but they cannot commit authoritative state.

### 3.3 Context Packet As Task Contract

`ContextPacket` must expose structured contract fields:

```text
packet_id
version
packet_kind
agent_id
task_id
run_id
status
role_contract_json
objective
constraints_json
next_action
expected_outputs_json
required_artifacts_json
acceptance_gates_json
artifact_refs_json
created_from_event_id
supersedes
superseded
invalidated_at
invalidated_by_event_id
created_at
updated_at
```

Allowed `packet_kind` values:

```text
assignment
handoff
rehydration
review
replan
gate_resolution
user_interrupt
```

`ContextPacket` is the reusable contract content and is not forcibly bound to one session. Session possession lives in `TaskContextBinding`.

### 3.4 New Tables

Add idempotent migrations for:

```text
task_claims
task_context_bindings
actor_permissions
protocol_violations
projection_effects
agent_session_epochs
principals
agent_workload_snapshots
```

Minimum table responsibilities:

- `task_claims`: durable worker claims waiting for controller/policy commit.
- `task_context_bindings`: active and historical context packet links per task/session.
- `actor_permissions`: role and action allowlist for protocol authority checks.
- `protocol_violations`: rejected or audit-only writes with reason, actor, session, and event metadata.
- `projection_effects`: normalized `COMMIT`, `AUDIT_ONLY`, `REJECT` records for UI diagnostics.
- `agent_session_epochs`: monotonic epoch ledger per agent identity.
- `principals`: durable identity for controller, user, system, and agent authority checks.
- `agent_workload_snapshots`: optional projection cache for capacity and current task load.

`TaskContextBinding` must include:

```text
binding_id
task_id
agent_id
session_id
session_epoch
context_packet_id
binding_kind
status
created_from_event_id
created_at
ended_at
```

This split keeps packet content reusable while preserving who held it under which session and epoch.

### 3.5 Inbox Fencing

Inbox delivery and ack are worker writes and must be fenced.

Add fields to inbox items:

```text
delivered_to_session_id
delivery_epoch
lease_expires_at
delivery_attempts
acked_by_session_id
ack_fencing_result
revoked_at
revoked_reason
```

Rules:

- `worker wait` requires `session_id`, `session_epoch`, and fencing token.
- Delivered items bind to `delivered_to_session_id` and `delivery_epoch`.
- `ack` must come from the same primary session that received the item.
- Replacement or quarantine revokes old delivered-but-unacked items and makes them eligible for redelivery.
- Standby sessions cannot consume primary inbox items unless controller policy explicitly promotes them.

### 3.6 Artifact Evidence Chain

Artifacts are evidence and must be authority-checked.

Add fields to artifact records:

```text
agent_id
session_id
context_packet_id
claim_id
produced_by_event_id
content_hash
```

Rules:

- A worker can produce artifacts only for the task bound to its active context.
- Gate evidence must belong to the same task or be explicitly attached by controller/user policy.
- Required gate artifacts cannot be satisfied by unrelated task artifacts.
- `content_hash` is optional for local URIs but required for file uploads or copied evidence when bytes are available.

### 3.7 Migration Runner

Do not reset local databases as the migration strategy.

Add a migration runner with:

```text
has_table(table)
has_column(table, column)
add_column_if_missing(table, column_definition)
create_table_if_missing(sql)
record_schema_version(version)
```

Current `create table if not exists` is insufficient because existing tables need `ALTER TABLE` columns. SQLite migrations must use `PRAGMA table_info` checks before adding columns.

### 3.8 Unique Write Path

All durable state writes must flow through:

```text
ProtocolKernel -> AuthorityService -> PolicyService -> FencingService -> UnitOfWork -> repositories
```

Rules:

- Public business methods on Board/Coordinator classes are removed or downgraded to internal repository/state-mutator methods.
- `TaskBoard.complete_task()` becomes an internal commit method such as `_commit_task_completed_internal()` and is callable only from kernel-controlled services.
- `GateBoard.approve_gate()` becomes an internal gate decision mutator.
- `ReplacementCoordinator.approve()` splits into recommendation recording, approval request, and kernel-owned reassignment commit.
- State mutators cannot append public events or enqueue inbox items outside a `UnitOfWork`.
- Tests must fail if old public methods can still commit authoritative state directly.

## 4. Target API Contracts

Split writes by actor boundary.

Worker routes:

```text
POST /api/worker/sessions/register
POST /api/worker/sessions/{session_id}/heartbeat
POST /api/worker/inbox/wait
POST /api/worker/inbox/ack
POST /api/worker/tasks/{task_id}/ack-claim
POST /api/worker/tasks/{task_id}/progress
POST /api/worker/tasks/{task_id}/completion-claim
POST /api/worker/tasks/{task_id}/failure-claim
POST /api/worker/artifacts
POST /api/worker/handoff-proposals
```

Controller routes:

```text
POST /api/controller/tasks
POST /api/controller/tasks/{task_id}/assign
POST /api/controller/task-claims/{claim_id}/commit
POST /api/controller/task-claims/{claim_id}/reject
POST /api/controller/gates
POST /api/controller/gates/{gate_id}/approve
POST /api/controller/gates/{gate_id}/reject
POST /api/controller/replacements/{recommendation_id}/approve
POST /api/controller/replacements/{recommendation_id}/reject
POST /api/controller/context-packets
```

User routes:

```text
POST /api/user/interrupts
POST /api/user/messages
POST /api/user/gates/{gate_id}/decision
```

Read routes:

```text
GET /api/projections/operations
GET /api/projections/messages
GET /api/projections/tasks/{task_id}/workflow
GET /api/projections/protocol
GET /api/projections/agents
GET /api/projections/runs
```

Compatibility adapters remain temporarily:

```text
POST /api/messages/send
POST /api/inbox/wait
POST /api/inbox/ack
POST /api/replacement/approve
POST /api/interrupt
```

Each adapter must emit a deprecation audit event and call the new role-specific service. Adapters cannot bypass authority checks.

Compatibility policy:

- Controller compatibility is allowed only when the caller explicitly selects controller/user authority, such as `--as-controller` or a controller route principal.
- Worker compatibility without `session_id`, `session_epoch`, and token cannot produce `COMMIT`.
- Deprecated worker writes create `AUDIT_ONLY` records with `fencing_result=MISSING` unless they are mapped to a fenced v2 worker route.
- Deprecated `task complete --actor worker.*` creates a `task.completion_claimed` audit record with status `needs_fencing`; it does not complete the task.
- Deprecated `task complete --as-controller` may commit only after `AuthorityService` and `PolicyService` accept the controller principal.

## 5. Target CLI Contracts

New CLI command groups:

```powershell
python -m agent_bus worker session register <agent_id> --role worker --json
python -m agent_bus worker wait --agent <agent_id> --session-id <session_id> --fencing-token <token> --json
python -m agent_bus worker task ack-claim <task_id> --session-id <session_id> --fencing-token <token> --json
python -m agent_bus worker task complete-claim <task_id> --session-id <session_id> --fencing-token <token> --artifact <uri> --json

python -m agent_bus controller task create "<title>" --run-id <run_id> --json
python -m agent_bus controller task assign <task_id> --agent <agent_id> --context-packet <packet_id> --json
python -m agent_bus controller claim commit <claim_id> --json
python -m agent_bus controller gate approve <gate_id> --actor controller --json

python -m agent_bus user interrupt --message "<message>" --task-id <task_id> --json
python -m agent_bus protocol violations --json
```

Deprecated aliases:

```powershell
python -m agent_bus task complete <task_id> --actor worker.backend --json
python -m agent_bus task complete <task_id> --actor controller --as-controller --json
```

The deprecated worker completion alias must create a `task.completion_claimed` audit record with `fencing_result=MISSING` and `claim.status=needs_fencing`, not complete the task. The explicit controller compatibility alias may commit only through `ProtocolKernel`.

## 6. Projection And Frontend Contracts

### 6.1 Task-Level Workflow Projection

Replace global metro assumptions with task-scoped workflow projection.

New backend projection shape:

```json
{
  "task_id": "task_123",
  "run_id": "run_abc",
  "title": "Implement protocol kernel",
  "current_node_id": "claim:claim_1",
  "nodes": [
    {
      "id": "context:packet_1",
      "kind": "context",
      "title": "Assignment packet",
      "state": "active",
      "tone": "info",
      "context_packet_id": "packet_1"
    },
    {
      "id": "claim:claim_1",
      "kind": "claim",
      "title": "Completion claimed",
      "state": "pending_controller_commit",
      "tone": "warn",
      "claim_id": "claim_1"
    },
    {
      "id": "gate:gate_1",
      "kind": "gate",
      "title": "QA acceptance",
      "state": "open",
      "tone": "warn",
      "gate_id": "gate_1"
    }
  ],
  "edges": [
    { "id": "edge_1", "source": "context:packet_1", "target": "claim:claim_1", "kind": "main", "tone": "info" },
    { "id": "edge_2", "source": "claim:claim_1", "target": "gate:gate_1", "kind": "gate", "tone": "warn" }
  ],
  "main_path_node_ids": ["context:packet_1", "claim:claim_1", "gate:gate_1"],
  "branch_groups": {}
}
```

Frontend rule:

- `HomePage` action queue shows actionable items.
- Selecting an action item resolves `task_id`.
- `MetroGraph` renders only that task's workflow.
- If no task is selected, show the highest-priority task workflow, not a stitched global graph.
- No edge may connect nodes from two different `task_id` values.
- Global or taskless events are not workflow nodes. Agent heartbeat, run-level events, user messages without `task_id`, and system diagnostics appear in Run Timeline, Communication, or Diagnostics, not in a task metro graph.
- A task workflow may include a global event only when a durable `task_context_binding` or controller attachment explicitly links it to that task.

### 6.2 Operations Projection

`GET /api/projections/operations` should include:

```text
active_run
agents
tasks
task_workflows
gates
task_claims
context_packets
replacement_recommendations
messages
protocol_violations
projection_effects
artifacts
```

Frontend `OperationsProjection` normalizes this into:

```text
tasks: TaskRow[]
taskWorkflows: Record<string, UiTaskWorkflowProjection>
selectedTaskWorkflow: UiTaskWorkflowProjection | null
protocol: ProtocolDiagnostics
```

### 6.3 Communication Projection

Communication filters must be backed by real data:

- `全部`: all messages visible to the current operator projection.
- `仅我可见`: direct messages where current viewer is sender or recipient.
- `@ 我的`: events/messages mentioning current agent/user id.
- `关注的 Agent`: messages involving pinned or selected agent ids.

If no authenticated user exists yet, define current viewer as `operator` and expose it in projection metadata:

```json
{ "viewer": { "id": "operator", "role": "user" } }
```

## 7. SubAgent Work Packages

Shared model rule:

- Package A owns all shared protocol enums, common Pydantic models, schema migrations, and public write-path abstractions.
- After Package A publishes `HANDOFF kernel`, other packages must not edit `agent_bus/models.py`, `agent_bus/protocol_models.py`, `agent_bus/db.py`, or migration helpers without a breaker-bus request to Package A.
- Domain-specific request/response models should live near their owning service or API module when they do not need to be shared.

### Package A: Kernel Agent

**Owned files:**

- `agent_bus/models.py`
- `agent_bus/protocol_models.py`
- `agent_bus/db.py`
- `agent_bus/migrations.py`
- `agent_bus/protocol.py`
- `agent_bus/authority.py`
- `agent_bus/policy.py`
- `agent_bus/fencing.py`
- `agent_bus/unit_of_work.py`
- `tests/test_protocol_kernel.py`
- `tests/test_migrations.py`
- `tests/test_no_direct_authoritative_mutation.py`

**Tasks:**

- [ ] Add protocol enums: `ProjectionEffect`, `FencingResult`, `SessionRole`, `PacketKind`, `TaskClaimKind`, `PrincipalType`, `ClaimStatus`, `BindingStatus`.
- [ ] Extend Pydantic models without removing existing JSON compatibility keys until API adapters are migrated.
- [ ] Add `MigrationRunner` with idempotent `ALTER TABLE` support and no database reset requirement.
- [ ] Add idempotent migration for new columns and tables, including event envelope fields, session fields, inbox fencing fields, artifact evidence fields, principals, claims, bindings, violations, effects, and epochs.
- [ ] Implement `ProtocolKernel` as the only public write path.
- [ ] Implement `UnitOfWork` so event append, state mutation, inbox enqueue, context binding, projection effect, and protocol violation writes commit atomically.
- [ ] Implement `FencingService.validate(session_id, session_epoch, token, required=True)`.
- [ ] Implement `AuthorityService.evaluate(actor, actor_role, action, session)`.
- [ ] Implement `PolicyService` for contextual checks: active context, no self-review, required artifacts, claim-context validity, replacement eligibility, and candidate capability.
- [ ] Downgrade old public Board/Coordinator authority methods to internal mutators or add failing tests before package owners remove them.
- [ ] Write tests for valid token, missing token, stale epoch, replaced session, quarantined session, controller principal, migration from old schema, and direct mutation bypass prevention.

**Focused verification:**

```powershell
python -m pytest tests/test_protocol_kernel.py tests/test_migrations.py tests/test_no_direct_authoritative_mutation.py tests/test_store.py tests/test_agents.py -q
```

### Package B: Task And Context Agent

**Owned files:**

- `agent_bus/tasks.py`
- `agent_bus/context.py`
- `agent_bus/inbox.py`
- `agent_bus/artifacts.py`
- `tests/test_task_claims.py`
- `tests/test_context_contracts.py`
- `tests/test_artifact_authority.py`

**Tasks:**

- [ ] Change assignment so it creates or requires an `assignment` context packet.
- [ ] Add `task_context_bindings` writes for assignment, handoff, rehydration, review, gate resolution, user interrupt, and replan.
- [ ] Replace worker direct task completion with `TaskClaim` creation.
- [ ] Add controller claim commit/reject service methods.
- [ ] Ensure inbox assignment payload always includes `context_packet_id`, `context_packet_version`, `task_id`, and `run_id`.
- [ ] Fence inbox wait/ack using delivered session, delivery epoch, lease, ack session, and ack fencing result.
- [ ] Update runtime state transitions: completion claim moves the worker to `WAITING_FOR_COMMIT`, `WAITING_FOR_REVIEW`, or `WAITING_FOR_GATE` according to pending blockers. It does not automatically become `STANDBY_READY`.
- [ ] Use `accepts_new_work` and `max_concurrent_tasks` to decide whether an agent may receive another assignment while waiting for commit, review, or gate.
- [ ] Bind worker-produced artifacts to agent, session, context packet, claim, producing event, and optional content hash.
- [ ] Enforce artifact evidence rules so unrelated task artifacts cannot satisfy gate evidence.
- [ ] Write regression tests proving worker completion cannot directly complete a task.

**Focused verification:**

```powershell
python -m pytest tests/test_task_claims.py tests/test_context_contracts.py tests/test_artifact_authority.py tests/test_tasks_gates_reviews.py -q
```

### Package C: Gate Review Replacement Agent

**Owned files:**

- `agent_bus/gates.py`
- `agent_bus/reviews.py`
- `agent_bus/replacement.py`
- `tests/test_gate_contracts.py`
- `tests/test_replacement_protocol.py`
- `tests/test_reviews.py`

**Tasks:**

- [ ] Upgrade gate model to acceptance contract with `gate_kind`, checklist, required evidence, risk policy, and decision actor.
- [ ] Prevent self-review and self-approval when worker, reviewer, and gate decision actor resolve to the same identity.
- [ ] Require controller/user approval for high-risk gates.
- [ ] Split replacement into recommendation, approval, and committed reassignment events.
- [ ] Ensure replacement preserves original `task_id` and creates a `rehydration` context packet.
- [ ] Invalidate only the old agent + old task + old session active context binding during replacement. Do not invalidate all packets for the old agent.
- [ ] Invalidate affected context packets when user interrupt changes task authority, using task/run filters instead of broad agent-wide invalidation.
- [ ] Write tests for ordinary gate, high-risk gate, self-review rejection, replacement approval, and replacement rejection.

**Focused verification:**

```powershell
python -m pytest tests/test_gate_contracts.py tests/test_replacement_protocol.py tests/test_reviews.py tests/test_replacement.py -q
```

### Package D: API And CLI Agent

**Owned files:**

- `agent_bus/server.py`
- `agent_bus/cli.py`
- `tests/test_worker_api.py`
- `tests/test_controller_api.py`
- `tests/test_cli_protocol_v2.py`

**Tasks:**

- [ ] Add `/api/worker/*`, `/api/controller/*`, `/api/user/*`, and `/api/projections/*` route groups.
- [ ] Convert old mixed routes into adapters that call new services and emit deprecation audit events.
- [ ] Add CLI groups: `worker`, `controller`, `user`, `protocol`.
- [ ] Convert deprecated `task complete` worker alias into audit-only completion claim creation when fencing is missing.
- [ ] Add explicit controller compatibility mode, such as `--as-controller`, for local operator commits.
- [ ] Ensure all write requests accept and validate session fencing fields where required.
- [ ] Resolve every write request into a `Principal`; do not trust free-form `actor` strings for authority.
- [ ] Return stable JSON error bodies with `error`, `message`, `projection_effect`, and optional `violation_id`.
- [ ] Write API and CLI tests covering success, reject, audit-only, and adapter paths.

**Focused verification:**

```powershell
python -m pytest tests/test_worker_api.py tests/test_controller_api.py tests/test_cli_protocol_v2.py tests/test_server.py tests/test_cli_wave_c.py -q
```

### Package E: Projection Frontend Agent

**Owned files:**

- `agent_bus/projections.py`
- `frontend/src/operationsApi.ts`
- `frontend/src/operationsRoomModel.ts`
- `frontend/src/components/MetroGraph.tsx`
- `frontend/src/pages/HomePage.tsx`
- `frontend/src/pages/CommunicationPage.tsx`
- `frontend/src/pages/DiagnosticsPage.tsx`
- `tests/test_protocol_projection.py`

**Tasks:**

- [ ] Add task workflow projection builder keyed by `task_id`.
- [ ] Ensure projection builder refuses or drops edges across different task ids and records a protocol violation for malformed cross-task edges.
- [ ] Keep taskless/global events out of task workflow graphs unless a durable task binding explicitly attaches them.
- [ ] Route run/global/system events to Run Timeline, Communication, or Diagnostics projections.
- [ ] Change `UiMetroProjection` into `UiTaskWorkflowProjection`, with compatibility normalization only at API boundary.
- [ ] Update `HomePage` so action queues select a task workflow instead of owning a workflow.
- [ ] Update `MetroGraph` labels to valid UTF-8 Chinese and render context, claim, gate, artifact, replacement, and terminal nodes.
- [ ] Implement communication filter behavior against projection metadata and real message recipients.
- [ ] Add diagnostics panels for projection effects, fencing rejects, protocol violations, and deprecated adapter usage.
- [ ] Build the frontend with no hardcoded demo records.

**Focused verification:**

```powershell
python -m pytest tests/test_protocol_projection.py tests/test_communication_projection.py tests/test_artifact_manifests.py -q
cd frontend
npm run build
```

### Package F: QA Docs Agent

**Owned files:**

- `docs/protocol.md`
- `docs/subagent-contracts.md`
- `docs/operator-manual.md`
- `docs/recovery-playbook.md`
- `README.md`
- `tests/test_live_protocol_simulation.py`

**Tasks:**

- [ ] Update worker contract so workers submit claims rather than direct completion.
- [ ] Document v2 session fencing and token handling.
- [ ] Document controller/user authority boundaries.
- [ ] Document task-level workflow graph semantics.
- [ ] Add a live 4-agent simulation test using controller, frontend worker, backend worker, and runtime QA.
- [ ] Run browser QA against `http://127.0.0.1:8787/` and record screenshots or findings.
- [ ] Verify README describes states, communication, fallback breaker, and task workflow correctly.

**Focused verification:**

```powershell
python -m pytest tests/test_live_protocol_simulation.py -q
python -m pytest -q
cd frontend
npm run build
```

## 8. Execution Waves

### Wave 0: Branch, Baseline, And Bus

- [ ] Create branch `codex/protocol-kernel-v2`.
- [ ] Confirm `git status --short --branch` is clean or record unrelated dirty files.
- [ ] Start breaker broker on `http://127.0.0.1:8765`.
- [ ] Each subAgent posts `OWNERSHIP`.
- [ ] Baseline commands:

```powershell
python -m pytest -q
cd frontend
npm run build
```

### Wave 1: Kernel Before Features

- [ ] Package A lands schema, migration runner, principals, authority, policy, fencing, protocol kernel, and unit-of-work foundation.
- [ ] Wave 1 is not complete if `UnitOfWork` exists but business writes still bypass it.
- [ ] Before Wave 2 starts, these paths must be connected to `ProtocolKernel` and `UnitOfWork`: create task, assign task, context packet creation, inbox enqueue, worker claim creation, controller claim commit, gate decision, replacement approval, reassignment, rehydration, user interrupt, context invalidation, and wakeups.
- [ ] QA verifies no old tests silently bypass protocol enforcement.
- [ ] Other packages can read but not mutate kernel-owned files until `HANDOFF kernel`.

Gate token:

```text
GATE_PASS wave1 kernel protocol foundation
```

### Wave 2: Task Claims And Context Contracts

- [ ] Package B lands task claim and context binding behavior.
- [ ] Package C starts gate/replacement changes only after context packet shape stabilizes.
- [ ] Package D starts API request/response models after Package B publishes service contracts.

Gate token:

```text
GATE_PASS wave2 worker claims and context contracts
```

### Wave 3: Gates, Reviews, Replacement

- [ ] Package C lands gate contract, self-review prevention, and replacement phases.
- [ ] Package B reconciles task status transitions with gate/replacement events.
- [ ] Package D exposes controller routes for gate and replacement decisions.

Gate token:

```text
GATE_PASS wave3 gate review replacement authority
```

### Wave 4: API, CLI, Projections

- [ ] Package D lands split API and CLI adapters.
- [ ] Package E lands projection builders and frontend type normalization.
- [ ] Compatibility adapters emit deprecation audit events and do not bypass enforcement.

Gate token:

```text
GATE_PASS wave4 api cli projection split
```

### Wave 5: Frontend Convergence

- [ ] Package E corrects metro graph to task-level workflow.
- [ ] Home action queues no longer generate global metro edges.
- [ ] Communication filters are functional.
- [ ] Diagnostics page exposes real protocol effects.

Gate token:

```text
GATE_PASS wave5 frontend task workflow convergence
```

### Wave 6: Live Simulation And Docs

- [ ] Package F runs the 4-agent live protocol simulation.
- [ ] QA verifies task creation, assignment, claims, controller commit, gate approval, replacement, communication, and role transfer.
- [ ] Docs are updated after behavior is verified.

Gate token:

```text
GATE_PASS wave6 live simulation and docs
```

## 9. Required Test Scenarios

Backend protocol:

- [ ] Worker with missing token gets `REJECT` and `protocol_violations` row.
- [ ] Worker with stale epoch gets `REJECT`.
- [ ] Replaced session cannot submit progress or completion claim.
- [ ] Quarantined session can heartbeat but cannot mutate task claims.
- [ ] Controller can commit a valid worker claim.
- [ ] Controller cannot commit a claim bound to invalidated context.
- [ ] Deprecated worker `task complete` creates claim and audit event, not completed task.
- [ ] `TaskBoard.complete_task`, `GateBoard.approve_gate`, and `ReplacementCoordinator.approve` cannot be used as public authoritative write paths.
- [ ] State mutation without `UnitOfWork` cannot append durable authority events.
- [ ] Free-form `actor="controller"` does not grant controller authority without a controller/user principal.

Context:

- [ ] Assignment creates `assignment` packet and task binding.
- [ ] Handoff creates new packet version and supersedes prior active packet.
- [ ] Replacement creates `rehydration` packet.
- [ ] User interrupt invalidates affected task contexts only.
- [ ] Replacement invalidates only old agent + old task + old session active binding.
- [ ] Context packet content is reusable; session ownership is recorded in `task_context_bindings`.

Inbox:

- [ ] Wait binds delivery to session id and epoch.
- [ ] Ack from a different session is rejected.
- [ ] Ack after replacement revocation is rejected and item can be redelivered.
- [ ] Standby session cannot consume primary session inbox items.

Artifacts:

- [ ] Worker artifact must match active task context.
- [ ] Gate evidence rejects unrelated task artifact.
- [ ] Controller can explicitly attach cross-task evidence when policy allows it.

Capacity:

- [ ] Completion claim moves agent to a waiting state, not automatic `STANDBY_READY`.
- [ ] Agent with `accepts_new_work=false` receives no new ordinary task.
- [ ] Agent below `max_concurrent_tasks` may receive new work when policy allows it.

Gates/reviews:

- [ ] High-risk gate escalates to controller/user.
- [ ] Worker cannot approve own gate.
- [ ] QA can request changes without completing or failing the task directly.
- [ ] Required artifact absence blocks gate approval.

Projection/frontend:

- [ ] Operations projection includes `task_workflows` keyed by task id.
- [ ] Workflow projection contains no cross-task edges.
- [ ] Selecting an action item renders only that task's metro graph.
- [ ] Communication filters change visible message set.
- [ ] Diagnostics shows rejected fencing event with reason.

Live simulation:

- [ ] Four simulated agents register sessions and heartbeat.
- [ ] User creates run and task.
- [ ] Controller assigns task with context packet.
- [ ] Worker claims ack, progress, artifact, and completion.
- [ ] QA opens or evaluates gate.
- [ ] Controller commits completion.
- [ ] Replacement path preserves task id and rehydrates replacement session.
- [ ] Message visibility and ack state are readable from UI.

## 10. Browser QA Checklist

Use Codex browser against:

```text
http://127.0.0.1:8787/
```

Check desktop and narrow viewport:

- [ ] Sidebar does not overlap main content.
- [ ] Home action queue remains a queue, not a workflow graph.
- [ ] Task metro graph changes when selecting a different task.
- [ ] No metro edge connects two different task ids.
- [ ] Node labels fit in their buttons.
- [ ] Communication scope controls are clickable and change results.
- [ ] Message detail panel shows sender, recipients, ack state, context ids, and timeline.
- [ ] Gate decisions cannot be clicked into a false success when backend rejects them.
- [ ] Diagnostics page displays protocol violations from rejected test writes.
- [ ] No mojibake text appears in MetroGraph empty state or node labels.

## 11. Final Merge Criteria

The refactor is not complete until all of these are true:

- [ ] `python -m pytest -q` passes.
- [ ] `cd frontend; npm run build` passes.
- [ ] Browser QA checklist passes on `http://127.0.0.1:8787/`.
- [ ] 4-agent live simulation passes.
- [ ] README and protocol docs match implemented behavior.
- [ ] No worker route or CLI can directly commit authoritative task completion.
- [ ] No public Board/Coordinator method can bypass `ProtocolKernel`.
- [ ] All required durable write paths use `UnitOfWork`.
- [ ] Existing SQLite databases migrate without reset.
- [ ] Fencing tokens never appear in event log, projection, diagnostics, frontend JSON, or screenshots.
- [ ] No frontend view depends on hardcoded demo workflow data.
- [ ] Every deprecated adapter emits an audit/projection effect.
- [ ] Git diff contains no unrelated formatting churn outside owned files.

## 12. Recommended Commit Sequence

Use commits at gate boundaries:

```text
feat(protocol): add fenced session authority kernel
feat(tasks): split worker claims from controller commits
feat(gates): enforce gate review and replacement contracts
feat(api): split worker controller user protocol surfaces
feat(frontend): render task-scoped workflow projections
test(runtime): add live multi-agent protocol simulation
docs(protocol): document v2 agent communication model
```
