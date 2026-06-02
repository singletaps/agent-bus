# Kernel v2 Package B/C Prep - runtime-helper-2

Created: 2026-06-01
Owner: runtime-helper-2
Scope: read-only prep artifact only. No product code or test edits.

## Assignment

QA assigned helper2 to prepare future Package B/C implementation. This artifact maps dependencies on Package A, proposes service contracts, identifies risky old public mutators, and lists tests to preserve or convert.

Relevant plan scope:

- Package B owns task/context/inbox/artifact behavior.
- Package C owns gates/reviews/replacement behavior.
- Package B/C implementation must wait for Package A handoff before product-code edits.

## Package A Handoff Dependencies

Package B/C should not start implementation until Package A publishes the kernel contract below.

- `ProtocolKernel` entry points and command/result models for worker claims, controller commits, context binding, inbox delivery/ack, artifact production, gate decisions, review findings, and replacement phases.
- `UnitOfWork` transaction boundary and how internal board/repository mutations are allowed to run inside it.
- Principal creation/resolution for `user`, `controller`, `agent`, and `system`, including how legacy string actors map to non-authoritative principals.
- Authority and policy method names for static permissions, task ownership, active context checks, required artifact checks, no-self-review checks, replacement eligibility, and candidate capability.
- Fencing API for `session_id`, `session_epoch`, token hash validation, and result values: `VALID`, `MISSING`, `INVALID`, `STALE_EPOCH`, `WRONG_SESSION`, `NOT_REQUIRED`.
- Event envelope fields on `BusEvent`: `actor_role`, `session_id`, `session_epoch`, `context_packet_id`, `gate_id`, `artifact_id`, `correlation_id`, `causation_id`, `projection_effect`, and `fencing_result`.
- Projection effect/violation persistence rules for `COMMIT`, `AUDIT_ONLY`, and `REJECT`.
- Migration ownership for new tables and columns used by B/C:
  - `task_claims`
  - `task_context_bindings`
  - inbox fencing columns
  - artifact evidence columns
  - gate acceptance contract fields
  - review actor identity fields if not included in Package A
  - replacement approval/reassignment diagnostics if not included in Package A
- Compatibility adapter rule: deprecated public paths may emit audit/violation records, but must not commit authoritative task, gate, review, replacement, or session state.

## Package B Proposed Service Contracts

The current `TaskBoard`, `ContextStore`, `InboxStore`, and artifact helpers should become storage/projection helpers behind kernel-owned services. Suggested service surfaces:

### Task Claim Service

Purpose: workers report claims; controllers commit or reject them.

- `create_ack_claim(principal, task_id, session_id, session_epoch, context_packet_id, token, payload) -> ProtocolResult`
- `create_progress_claim(...) -> ProtocolResult`
- `create_blocker_claim(reason, ...) -> ProtocolResult`
- `create_completion_claim(required_artifact_ids, ...) -> ProtocolResult`
- `create_failure_claim(reason, ...) -> ProtocolResult`
- `commit_claim(controller_principal, claim_id, decision, reason=None) -> ProtocolResult`

Expected behavior:

- Worker claims are durable but not task-state commits.
- Deprecated worker `task complete` creates a completion claim plus audit/protocol effect, not `TaskState.COMPLETED`.
- Completion claim moves the agent/session to a waiting state such as `WAITING_FOR_COMMIT`, `WAITING_FOR_REVIEW`, or `WAITING_FOR_GATE`, not automatically to `STANDBY_READY`.
- Controller commit validates active context, required artifacts, fencing, and pending gates/reviews before changing task state.

### Task Context Binding Service

Purpose: context packets are reusable contracts; session possession is stored in bindings.

- `create_assignment_packet(controller_principal, task_id, assignee_session_id, objective, constraints, expected_outputs, required_artifacts, acceptance_gates) -> ProtocolResult`
- `bind_packet_to_session(principal, task_id, agent_id, session_id, session_epoch, context_packet_id, binding_kind) -> ProtocolResult`
- `supersede_binding(principal, binding_id, replacement_context_packet_id, reason) -> ProtocolResult`
- `invalidate_task_contexts(principal, task_id=None, run_id=None, agent_id=None, session_id=None, reason) -> ProtocolResult`

Expected behavior:

- Assignment creates or requires an `assignment` packet.
- Handoff, rehydration, review, gate resolution, replan, and user interrupt create/supersede/invalidate bindings through policy.
- User interrupt invalidates affected task/run contexts only.
- Replacement invalidates only old agent + old task + old session active binding.

### Inbox Delivery Service

Purpose: worker wait/ack is fenced and session-bound.

- `enqueue_assignment(controller_principal, agent_id, task_id, run_id, context_packet_id, context_packet_version, priority) -> ProtocolResult`
- `wait(agent_principal, session_id, session_epoch, token, busy=False, timeout=...) -> ProtocolResult`
- `ack(agent_principal, inbox_id, session_id, session_epoch, token) -> ProtocolResult`
- `revoke_delivery(controller_principal, inbox_id, reason) -> ProtocolResult`

Expected behavior:

- Wait binds delivery to `delivered_to_session_id` and `delivery_epoch`.
- Ack from any different session or stale epoch is rejected.
- Ack after replacement/quarantine revocation is rejected and item can be redelivered.
- Standby sessions cannot consume primary-session items unless policy explicitly promotes them.

### Artifact Evidence Service

Purpose: artifacts become evidence bound to task context and claims.

- `produce_artifact(agent_principal, task_id, session_id, session_epoch, context_packet_id, claim_id, kind, uri, content_hash=None, metadata=None) -> ProtocolResult`
- `attach_gate_evidence(controller_principal, gate_id, artifact_id, cross_task_allowed=False, reason=None) -> ProtocolResult`

Expected behavior:

- Worker artifacts must match active task context.
- Gate evidence rejects unrelated task artifacts unless controller/user policy explicitly allows cross-task evidence.
- Required gate artifacts cannot be satisfied by unrelated task artifacts.

## Package C Proposed Service Contracts

The current `GateBoard`, `ReviewBoard`, and `ReplacementCoordinator` should stop being public authority gates. They can keep internal persistence helpers after Package A defines the kernel path.

### Gate Contract Service

- `open_gate(principal, task_id, gate_kind, checklist, required_evidence, risk_policy, owner_agent_id=None) -> ProtocolResult`
- `request_gate_approval(principal, gate_id, action_agent_id) -> ProtocolResult`
- `decide_gate(principal, gate_id, decision, reason=None, evidence_artifact_ids=None) -> ProtocolResult`
- `escalate_gate(principal, gate_id, reason) -> ProtocolResult`
- `expire_gate(system_principal, gate_id, reason) -> ProtocolResult`

Expected behavior:

- Gate model includes acceptance contract fields: `gate_kind`, checklist, required evidence, risk policy, and decision actor.
- High-risk gate approval requires controller/user authority. Do not rely on string checks such as `actor == "controller"`.
- Gate decision validates no self-approval, active context, required artifacts, and evidence/task relationship.
- Use event names `gate.opened`, `gate.approval_requested`, `gate.approved`, `gate.rejected`, `gate.escalated`, and `gate.expired`; do not use broad `gate.result` for v2 projection logic.

### Review Policy Service

- `create_finding(reviewer_principal, task_id, severity, category, evidence, requested_change, blocking=False, file_path=None) -> ProtocolResult`
- `request_changes(reviewer_principal, task_id, worker_agent_id, findings) -> ProtocolResult`
- `resolve_finding(resolver_principal, finding_id, status, reason=None) -> ProtocolResult`

Expected behavior:

- Prevent self-review when reviewer, worker, and decision actor resolve to the same identity.
- QA can request changes without completing or failing the task directly.
- Review findings remain separate from task completion authority; controller/policy commits task state after review/gate conditions pass.

### Replacement Protocol Service

- `recommend_replacement(system_or_controller_principal, old_agent_id, task_id, reason, candidates) -> ProtocolResult`
- `request_replacement_approval(principal, recommendation_id, required_artifacts=None) -> ProtocolResult`
- `approve_replacement(controller_principal, recommendation_id, replacement_session_id=None) -> ProtocolResult`
- `reject_replacement(controller_principal, recommendation_id, reason) -> ProtocolResult`
- `commit_reassignment(controller_principal, recommendation_id, replacement_session_id, rehydration_packet_id) -> ProtocolResult`

Expected behavior:

- Split recommendation, approval, and committed reassignment into separate events.
- Preserve original `task_id`.
- Replacement approval creates a `rehydration` context packet and binds it to replacement session.
- Old session is replaced/quarantined through session policy and old task binding is invalidated narrowly.
- Delivered but unacked inbox items for the old session are revoked/redeliverable through inbox fencing.

## Risky Old Public Mutators

These are the legacy paths most likely to bypass Package A unless converted to internal helpers or guarded adapters.

### Task/context/inbox/artifact

- `TaskBoard.assign_task`: directly changes task state and enqueues inbox work.
- `TaskBoard.acknowledge_task`: directly commits acknowledgement.
- `TaskBoard.start_task`: directly commits working state and active session state.
- `TaskBoard.block_task`: directly commits blocked state.
- `TaskBoard.complete_task`: directly commits completion and moves session to `STANDBY_READY`.
- `TaskBoard.fail_task`: directly commits failure.
- `TaskBoard.supersede_task`: directly commits supersession.
- `TaskBoard.create_artifact`: directly writes evidence without active context/session/claim binding.
- `ContextStore.create_packet`, `supersede_packet`, `invalidate_packet`, `create_rehydration_packet`, `invalidate_agent_contexts`: operate on packets directly and can be too broad without task/session binding policy.
- `InboxStore.enqueue`, `wait`, `ack`, `enqueue_interrupt_wakeups`: no session delivery binding or ack fencing yet.
- Module-level wrappers in `tasks.py`, `context.py`, and `inbox.py` expose the same direct paths.

### Gate/review/replacement

- `GateBoard.create_gate`: opens gates directly without acceptance contract validation.
- `GateBoard.approve_gate`: can commit approval directly and currently relies on actor strings for high-risk exceptions.
- `GateBoard.reject_gate`, `expire_gate`, `escalate_gate`: direct authoritative state changes.
- `GateBoard._resolve_gate`: emits broad `EventType.GATE_RESULT` and enqueues `gate_result`.
- `ReviewBoard.create_finding` and `request_changes`: create authoritative review findings without self-review/policy enforcement.
- `ReviewBoard.resolve_finding`: closes findings directly.
- `ReplacementCoordinator.approve`: currently combines approval, session replacement, task reassignment, rehydration packet creation, inbox notice, and approval event.
- `ReplacementCoordinator._reassign_task_to_replacement`: calls `TaskBoard.assign_task` directly.

### Compatibility callers to audit later

- `agent_bus/cli.py` calls direct task, gate, replacement, and artifact mutators.
- `agent_bus/server.py` exposes routes that currently mix worker/controller/user write authority.
- Existing tests may accidentally normalize direct public mutation as acceptable behavior.

## Tests To Preserve Or Convert

Preserve the intent of these tests while changing their expected authority path.

- `tests/test_tasks_gates_reviews.py`
  - Keep task lifecycle coverage, but invert worker completion into claim + controller commit.
  - Keep gate high-risk escalation behavior, but assert principal-based authority and no direct string trust.
  - Keep review finding/request-changes durability, but add no-self-review coverage.
  - Keep artifact persistence checks, but bind artifacts to active task context.
- `tests/test_replacement.py`
  - Preserve replacement recommendation scoring.
  - Convert approval assertions to separate approval, rehydration, reassignment commit, and context-binding invalidation checks.
- `tests/test_server.py`
  - Preserve context invalidation, replacement API, and operation projection flows.
  - Convert write route assertions to split worker/controller/user authority surfaces after Package D.
- `tests/test_agents.py`
  - Preserve replacement session persistence and runtime state expectations.
  - Add epoch/token/session-role expectations after Package A handoff.
- `tests/test_inbox.py`
  - Preserve durable enqueue/wait/ack behavior.
  - Add session-bound delivery, wrong-session ack rejection, stale-epoch ack rejection, revoked item redelivery.
- `tests/test_artifact_manifests.py`
  - Preserve manifest path safety.
  - Keep projection behavior non-mutating.

New Package B/C focused tests from the plan:

- `tests/test_task_claims.py`
- `tests/test_context_contracts.py`
- `tests/test_artifact_authority.py`
- `tests/test_gate_contracts.py`
- `tests/test_replacement_protocol.py`
- `tests/test_reviews.py`

## Suggested Sequencing

1. Wait for `HANDOFF kernel` from Package A with ProtocolKernel/UnitOfWork method names, migration contract, event envelope fields, and direct mutation prevention expectations.
2. Package B should land task claim/context binding tests first, then inbox fencing, then artifact evidence.
3. Package C should start implementation only after context packet/binding shape is stable enough to support gate evidence and replacement rehydration.
4. Package C can prepare red tests for gate/review/replacement authority immediately after Package A handoff, but should avoid final replacement implementation until Package B context binding APIs exist.
5. Package D should not expose API/CLI request models until Package B publishes service contracts for claims/context/inbox/artifacts and Package C publishes gate/replacement command models.

## Open Questions For Package A / QA

- What are the exact `ProtocolKernel` command names and result type names for B/C to call?
- Does Package A own all B/C-specific migration columns, or should B/C add migrations after the kernel runner lands?
- Can internal board methods remain public in Python but protected by no-direct-authoritative-mutation tests, or should they be renamed/private?
- How should deprecated CLI calls behave during transition: reject, audit-only claim, or compatibility claim requiring controller commit?
- What principal bootstrap exists for local QA/controller commands in tests?
- Is artifact `content_hash` required only for file upload/copy paths, or also for local URI references when bytes are readable?
- Which service owns runtime state after completion claim when review and gate are both pending?

## Prep Conclusion

Package B/C should treat old boards/coordinators as persistence helpers only. The public business API should be ProtocolKernel-backed services that record worker claims separately from controller commits, bind every worker operation to active context/session/fencing, and split gate/review/replacement authority into explicit phases.
