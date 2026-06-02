# Gate1 Authority Remediation Plan - Runtime Helper 2

Timestamp: 2026-06-01T17:04:00+08:00

Author: `runtime-helper-2`

Assignment: `KERNEL_GATE1_AUTHORITY_PLAN_REQUEST` from `runtime-qa`

Scope: READ-ONLY architecture remediation artifact. No product-code edits were made for this artifact.

## Goal

Close Gate1 at the logical/system level by making every durable business write enter through an authenticated protocol command boundary:

```text
Adapter -> PrincipalResolver -> ProtocolKernel command -> AuthorityService -> PolicyService -> FencingService -> UnitOfWork -> internal repositories
```

The fix must remove string-based authority shortcuts, make worker actions claim-based and fenced, and downgrade legacy Board/Store/Coordinator APIs to internal mutators that cannot commit authoritative state directly.

## Current Blocking Evidence

The Wave 1 plan requires all durable state writes to flow through `ProtocolKernel -> AuthorityService -> PolicyService -> FencingService -> UnitOfWork -> repositories`, and explicitly says public business methods on Board/Coordinator classes should be removed or downgraded to internal state mutators.

Gate1 is still blocked because the current implementation remains adapter-shaped:

- `TaskBoard.create_run`, `create_task`, and `assign_task` still expose public business writes. They add guards/effects and reject some actors, but they still perform repository mutation themselves.
- `ContextStore.create_packet` and `InboxStore.enqueue` have the same public write shape.
- `trusted_compatibility=True` lets controller-shaped strings bypass the rejection shim without proving a controller principal.
- `runtime-worker-*` classification is handled by local helper functions, not a central principal/session resolver.
- Bare `actor="controller"` is denied in some untrusted paths, but controller authority is still represented as an actor string in many CLI/server/test setup paths.
- Replacement approval still combines session replacement, task reassignment, context rehydration, inbox notice, and approval recording behind a coordinator public method.

Tests can be green while the protocol model is still wrong because the public repositories are still treated as compatibility adapters instead of internal persistence helpers.

## Required Logical Model

### 1. Principal resolution is mandatory

Every write adapter must supply or derive a `Principal` before a durable business command can be evaluated.

Accepted principal sources:

- Authenticated user/controller API path: `PrincipalType.USER` or `PrincipalType.CONTROLLER`, explicit roles, explicit permissions, no worker fencing required.
- Registered runtime session path: `PrincipalType.AGENT`, `agent_id`, `session_id`, `session_epoch`, role `worker` or `qa`, worker fencing required for worker/agent actions.
- Internal bootstrap/system path: `PrincipalType.SYSTEM`, explicit call site, limited to seed/bootstrap/migration/test-fixture factories.

Rejected principal sources:

- Bare strings such as `actor="controller"`.
- Worker-shaped strings such as `worker.freeform` or `runtime-worker-1` without a registered active session fence.
- `trusted_compatibility=True` as a public authority mechanism.

### 2. Command objects replace public durable writes

Add typed protocol commands for the Wave 1 write surface:

- `CreateRunCommand`
- `CreateTaskCommand`
- `AssignTaskCommand`
- `CreateContextPacketCommand`
- `EnqueueInboxCommand`
- `WorkerClaimCommand`
- `CommitTaskClaimCommand`
- `GateDecisionCommand`
- `ReplacementApprovalCommand`
- `ReplacementReassignmentCommand`
- `CreateUserInterruptCommand`
- `InvalidateContextCommand`
- `WakeupCommand`

Each command must carry:

- `principal`
- `actor`
- `action`
- `payload`
- `run_id/task_id/agent_id/context_packet_id/gate_id` as applicable
- `session_id/session_epoch/fencing_token` when the principal is an agent
- `correlation_id/causation_id`
- required artifacts or review targets when policy checks need them

### 3. Repositories become internal mutators

Public Board/Store/Coordinator methods should no longer be the authority boundary.

Required shape:

- `TaskBoard.create_run` -> compatibility wrapper or removed; real mutator becomes `_commit_run_created_internal(...)`.
- `TaskBoard.create_task` -> `_commit_task_created_internal(...)`.
- `TaskBoard.assign_task` -> `_commit_task_assigned_internal(...)`.
- `TaskBoard.complete_task` and `fail_task` -> internal controller commit methods only.
- `ContextStore.create_packet` -> `_commit_context_created_internal(...)`.
- `ContextStore.invalidate/supersede` -> internal protocol-owned context state transitions.
- `InboxStore.enqueue` -> `_commit_inbox_enqueued_internal(...)`.
- `GateBoard.approve_gate/reject/escalate` -> protocol-owned gate decision commands.
- `ReplacementCoordinator.approve` -> split into protocol-owned approval, session replacement, reassignment, rehydration, and notice commands.

Internal mutators should accept a `UnitOfWork` or transaction handle and a preaccepted protocol event/effect record. They should not call `ProtocolKernel` themselves.

### 4. ProtocolKernel owns commit orchestration

For accepted commands, `ProtocolKernel` should perform the whole transaction:

1. Resolve and validate principal.
2. Evaluate static authority.
3. Evaluate policy.
4. Validate fencing if principal type is agent/worker/qa or command policy requires a session fence.
5. Append the protocol event.
6. Record write guards.
7. Record projection effect.
8. Invoke the internal repository mutator in the same `UnitOfWork`.
9. Return a structured `ProtocolWriteResult`.

For rejected commands, it should:

1. Record `protocol_violations`.
2. Record a `ProjectionEffect.REJECT`.
3. Not mutate business state.
4. Return a structured denial that adapters can render as CLI/API errors.

### 5. Worker writes are claims, not commits

Worker/runtime-agent principals may create fenced claims and reports:

- task acknowledgement claim
- progress report
- blocker report
- completion claim
- failure claim
- artifact produced
- handoff proposed
- context replan requested
- heartbeat

Worker principals may not commit control-plane state directly:

- create run
- create task
- assign/reassign task
- approve/reject/escalate gate
- commit task completion/failure
- approve replacement
- enqueue controller-owned inbox notices

Controller/user/system principals commit or reject worker claims through explicit claim-decision commands.

### 6. Replacement approval is a workflow, not one write

Replacement approval should become a protocol workflow with separate command results:

1. `RecordReplacementRecommendationCommand` records an audit recommendation.
2. `ApproveReplacementCommand` validates controller/user/system principal and policy.
3. `ReplaceSessionCommand` updates session state/fence role for old and replacement sessions.
4. `CommitTaskReassignmentCommand` commits the task reassignment.
5. `CreateRehydrationContextCommand` creates replacement context.
6. `EnqueueReplacementNoticeCommand` queues the notice.
7. `RecordReplacementApprovedCommand` records approval metadata.

All steps must share one correlation id. Steps that must be atomic should be in one `UnitOfWork`; steps that intentionally become follow-up effects must be recorded as pending effects with replayable causation.

## Proposed Ownership Map

Likely coordinated product files for a future implementation scope:

- `agent_bus/protocol_models.py`: command models, principal/session command fields, result shapes.
- `agent_bus/authority.py`: explicit action matrix; no string-only controller grant.
- `agent_bus/fencing.py`: session principal validation and agent/session consistency checks.
- `agent_bus/policy.py`: context binding, self-review, artifact, replacement, and user-interrupt policy checks.
- `agent_bus/protocol.py`: command handlers and accepted/rejected write orchestration.
- `agent_bus/unit_of_work.py`: transaction helpers for repository commit callbacks and multi-step effects.
- `agent_bus/tasks.py`: internal task/run mutators; public compatibility wrappers become rejection/deprecation adapters.
- `agent_bus/context.py`: internal context mutators and protocol-owned invalidation/supersession.
- `agent_bus/inbox.py`: internal enqueue mutator and wakeup effect handling.
- `agent_bus/gates.py`: internal gate decision mutators only.
- `agent_bus/replacement.py`: split approval workflow into protocol commands/effects.
- `agent_bus/router.py`: user interrupt command assembly without direct context/inbox writes.
- `agent_bus/cli.py`: resolve controller/user/system principals; render structured protocol denials.
- `agent_bus/server.py`: API principal/session resolution and protocol command entrypoints.
- `agent_bus/migrations.py`, `agent_bus/db.py`, `agent_bus/store.py`: only if command/principal persistence needs schema support; any changes should be explicitly scoped.

Likely coordinated tests:

- `tests/test_protocol_kernel.py`
- `tests/test_write_paths_kernel.py`
- `tests/test_no_direct_authoritative_mutation.py`
- `tests/test_cli_wave_c.py`
- `tests/test_server.py`
- `tests/test_tasks_gates_reviews.py`
- `tests/test_context.py`
- `tests/test_inbox.py`
- `tests/test_replacement.py`
- migration/store tests if schema changes are introduced

## Implementation Sequence For Reopened Scope

This is a proposed sequence only; it is not permission to edit product code.

- [ ] Add failing authority-boundary probes first:
  - Bare `actor="controller"` cannot commit create/assign/context/inbox/gate/replacement writes.
  - `runtime-worker-1` cannot commit control-plane writes without a registered session fence.
  - A registered worker session with a valid token can create claims/reports but cannot commit control-plane transitions.
  - A controller principal object can commit controller actions without worker fencing.
  - A system principal can seed/bootstrap only through explicit internal/bootstrap APIs.

- [ ] Add command models and a principal resolver:
  - Command constructors require `Principal` or authenticated session material.
  - String actor remains metadata, not authority.
  - Resolver rejects ambiguous actors and returns structured denial.

- [ ] Move accepted write orchestration into ProtocolKernel:
  - `ProtocolKernel.handle(command)` dispatches by command type.
  - Accepted command path appends event, guard, projection effect, and internal repository mutation in one transaction.
  - Rejected path records violation/effect and no business mutation.

- [ ] Downgrade public repositories:
  - Introduce internal `_commit_*_internal` methods.
  - Public compatibility methods either call a protocol command with an explicit system/controller principal supplied by the adapter or raise a structured deprecated-path error.
  - Remove `trusted_compatibility` as an authority bypass from public constructors.

- [ ] Convert CLI and server adapters:
  - CLI seed/demo commands use an explicit system principal.
  - CLI gate/replacement/interrupt commands resolve user/controller principal explicitly.
  - Server worker routes derive agent principal from session registration/fencing token.
  - Server controller/user routes derive controller/user principal from authenticated request context or an explicit local-controller fallback that is named as system/controller compatibility.

- [ ] Convert replacement and user interrupt workflows:
  - Replacement approval becomes a protocol workflow with correlated commands/effects.
  - User interrupt creates context/inbox/wakeups through protocol commands, not direct store calls.

- [ ] Remove legacy bypasses and scan for them:
  - No public `TaskBoard(...).create_*` or `ContextStore(...).create_packet` call should be required for authoritative writes outside protocol/bootstrap tests.
  - No `actor_role=_actor_role(actor)` should grant authority from a string.
  - No `trusted_compatibility=True` should be present in runtime adapters as an authority decision.

## Verification Plan

Focused probes:

```powershell
python -m pytest tests/test_protocol_kernel.py tests/test_write_paths_kernel.py tests/test_no_direct_authoritative_mutation.py -q
```

Adapter and workflow probes:

```powershell
python -m pytest tests/test_cli_wave_c.py tests/test_server.py tests/test_tasks_gates_reviews.py tests/test_context.py tests/test_inbox.py tests/test_replacement.py -q
```

Foundation probes:

```powershell
python -m pytest tests/test_migrations.py tests/test_store.py tests/test_agents.py -q
```

Full regression:

```powershell
python -m pytest -q
python -m agent_bus --help
```

Static scans before Gate1 READY:

```powershell
rg -n "trusted_compatibility=True|actor == \"controller\"|actor in \\{\"controller\", \"user\"\\}|startswith\\(\"runtime-worker\"\\)|startswith\\(\"worker\"\\)" agent_bus tests
rg -n "create_run\\(|create_task\\(|assign_task\\(|create_packet\\(|enqueue\\(|approve_gate\\(|ReplacementCoordinator\\(.+approve" agent_bus tests
```

Expected outcome:

- Rejected worker/bare-controller attempts create `protocol_violations` and `ProjectionEffect.REJECT`.
- Accepted controller/user/system commands create `ProjectionEffect.COMMIT`, write guards, and business-state changes.
- Accepted worker session commands create fenced worker claims/reports, not direct control-plane commits.
- No old public repository path can silently bypass `ProtocolKernel`.

## Gate1 Readiness Criteria

Gate1 should remain closed until QA can independently prove all of the following:

- `runtime-worker-*` and `worker.*` strings alone cannot commit control-plane durable writes.
- Bare `controller` string alone cannot commit controller actions.
- Controller/user/system authority requires a `Principal`.
- Worker authority requires both a principal and valid session fence for worker actions.
- Every Wave 1 durable write listed in the implementation plan has a ProtocolKernel command path.
- Internal repository mutators cannot append public events or enqueue inbox items outside `UnitOfWork`.
- Compatibility/bootstrap paths are explicitly named, principal-bound, and covered by tests.
- Full pytest and CLI smoke pass after the authority probes pass.

## No-Code Scope Evidence

For this artifact, runtime-helper-2 only read files and wrote this coordination document:

- Created: `coordination/kernel-v2-gate1-authority-remediation-plan-helper2.md`
- No product files under `agent_bus/` were modified for this request.
- No tests were modified or run as a claimed product verification for this artifact.
