# Kernel v2 Gate1 Fail Fixback Diagnostic - runtime-helper-2

Created: 2026-06-01
Owner: runtime-helper-2
Scope: read-only diagnostic artifact only. No product-code or test edits.

## Assignment

Runtime-qa assigned helper2 to analyze the Gate1 fail after the user reported runtime-worker-1 and runtime-helper-1 are unable to reply. Requested output: classify Gate1 failures as Package A-only fix, B/C/D handoff need, or incompatible gate expectation; include proposed minimum file ownership and risks.

## Evidence Collected

QA Gate1 report:

- Package A focused verification passed:
  - `python -m pytest tests/test_protocol_kernel.py tests/test_migrations.py tests/test_no_direct_authoritative_mutation.py tests/test_store.py tests/test_agents.py -q` -> 29 passed.
  - `python -m agent_bus --help` -> exit 0.
- Full regression failed:
  - `python -m pytest -q` -> 7 failed, 75 passed.

Helper2 read-only reproduction command:

```powershell
python -m pytest tests/test_cli_wave_c.py::test_cli_operational_flow_persists_json_outputs_and_exit_codes tests/test_server.py::test_replacement_recommendation_and_approval_api_rehydrates_candidate tests/test_tasks_gates_reviews.py tests/test_context.py::test_create_and_get_packet_round_trips_structured_context tests/test_replacement.py::test_controller_approval_switches_replacement_and_rehydrates_same_task -q --tb=short
```

Result: 7 failed, 2 passed.

Failures reproduced:

- `tests/test_cli_wave_c.py::test_cli_operational_flow_persists_json_outputs_and_exit_codes`
- `tests/test_server.py::test_replacement_recommendation_and_approval_api_rehydrates_candidate`
- `tests/test_tasks_gates_reviews.py::test_task_state_machine_completion_returns_agent_to_standby_and_records_events`
- `tests/test_tasks_gates_reviews.py::test_high_risk_gate_escalates_and_enqueues_controller_action_instead_of_auto_approving`
- `tests/test_tasks_gates_reviews.py::test_lease_and_intent_are_coordination_records_not_permission_enforcement`
- `tests/test_context.py::test_create_and_get_packet_round_trips_structured_context`
- `tests/test_replacement.py::test_controller_approval_switches_replacement_and_rehydrates_same_task`

## Root Cause Summary

### P0: Compatibility/runtime direct paths hit raw SQLite guard triggers

Package A added SQLite guard triggers in `agent_bus/migrations.py`:

- `trg_tasks_authoritative_status_guard`
- `trg_gates_authoritative_state_guard`
- `trg_event_log_authoritative_kernel_guard`

These triggers correctly block direct authoritative mutation when there is no `kernel_write_guards` row. However, legacy runtime surfaces still call old board/coordinator APIs directly:

- CLI `task complete` -> `agent_bus/cli.py::_handle_task_complete` -> `TaskBoard.complete_task`
- API replacement approve -> `agent_bus/server.py::replacement_approve` -> `ReplacementCoordinator.approve` -> `_reassign_task_to_replacement` -> `TaskBoard.assign_task`
- Direct tests -> `TaskBoard.complete_task` and `GateBoard.approve_gate`

Result: old public flows raise raw `sqlite3.IntegrityError` instead of returning stable adapter behavior, audit-only protocol effects, or updated v2 expectations.

### P1: ContextPacket `updated_at` round-trip drift

Package A added `ContextPacket.updated_at` in `agent_bus/models.py` with `Field(default_factory=utc_now_iso)` and migration column `updated_at text`.

Current `agent_bus/context.py` is still old persistence code:

- `ContextStore.create_packet` constructs a `ContextPacket`, so returned packet gets `updated_at=T1`.
- `packet_to_row` does not persist `updated_at`.
- `row_to_packet` does not load `updated_at`.
- Loaded packet gets a fresh model default `updated_at=T2`.

Result: `store.get_packet(packet.packet_id) == packet` fails, and replacement rehydration context equality fails for the same reason.

## Classification

### Failure 1: CLI deprecated worker `task complete`

Classification: B/D handoff needed, plus QA test expectation decision.

Why:

- The concrete failing caller is `agent_bus/cli.py` (Package D/API+CLI surface).
- The domain behavior belongs to Package B task-claim compatibility: deprecated worker completion should not commit `TaskState.COMPLETED`; it should create an audit-only or pending completion claim with `fencing_result=MISSING`.
- Current `tests/test_cli_wave_c.py` still expects `task.status == "completed"`, which conflicts with the v2 plan if the actor is a worker without fencing.

Minimum ownership options:

- Preferred v2 path:
  - `agent_bus/cli.py`
  - `agent_bus/protocol.py`
  - `agent_bus/protocol_models.py`
  - `agent_bus/unit_of_work.py`
  - `tests/test_cli_wave_c.py` or a new compatibility test
  - Later Package B service file(s) once task claims exist
- Short-term Gate1 compatibility path:
  - `agent_bus/cli.py`
  - Package A protocol files only if `ProtocolKernel.record_direct_mutation_attempt` must expose an adapter-friendly result
  - Update test expectation away from completed task state

Risk:

- A Package A-only code fix that makes CLI `task complete` complete the task would weaken the direct-mutator guard and violate the plan.

### Failure 2: API replacement approve reassigns task through old TaskBoard

Classification: C/D handoff needed, with Package B dependency for task reassignment semantics.

Why:

- `agent_bus/server.py::replacement_approve` is Package D/API surface.
- `agent_bus/replacement.py::ReplacementCoordinator.approve` is Package C.
- `_reassign_task_to_replacement` calls `TaskBoard.assign_task`, which is a guarded authoritative task mutation.
- Proper v2 behavior is split: recommendation, approval, rehydration packet, and reassignment commit through ProtocolKernel/UnitOfWork.

Minimum ownership:

- `agent_bus/replacement.py`
- `agent_bus/server.py`
- `agent_bus/tasks.py` only if Package B task reassignment/claim service is introduced now
- `tests/test_replacement_protocol.py` or `tests/test_replacement.py`
- `tests/test_server.py`

Risk:

- A Package A-only fix would require weakening the task status trigger or adding broad kernel guards around old replacement internals. That would preserve old coupling Package C is supposed to split.

### Failure 3: direct `TaskBoard.complete_task` tests

Classification: incompatible gate expectation unless QA explicitly opens B/test compatibility scope.

Why:

- `tests/test_no_direct_authoritative_mutation.py::test_legacy_taskboard_complete_task_cannot_commit_authoritative_state` expects `TaskBoard.complete_task` to raise `sqlite3.IntegrityError` and leave the task `WORKING`.
- `tests/test_tasks_gates_reviews.py::test_task_state_machine_completion_returns_agent_to_standby_and_records_events` expects the same public mutator to complete the task and emit `task.completed`.
- Both expectations cannot be true for the same direct public API.

Minimum ownership:

- If preserving v2 guard: `tests/test_tasks_gates_reviews.py` should be updated/converted by QA/F or Package B tests to expect claim/adapter behavior, not direct completion.
- If supporting legacy direct mutator: `agent_bus/tasks.py`, `agent_bus/migrations.py`, and tests, but this conflicts with the plan and new direct-mutation tests.

Risk:

- Passing old direct lifecycle tests by loosening triggers would undercut the non-negotiable "all writes pass through ProtocolKernel/UnitOfWork" direction.

### Failure 4: high-risk gate direct approval/escalation test

Classification: incompatible gate expectation plus Package C handoff.

Why:

- `tests/test_no_direct_authoritative_mutation.py::test_legacy_gateboard_approve_gate_cannot_commit_authoritative_state` expects direct `GateBoard.approve_gate` to be blocked.
- `tests/test_tasks_gates_reviews.py::test_high_risk_gate_escalates_and_enqueues_controller_action_instead_of_auto_approving` expects direct `GateBoard.approve_gate` to mutate state to `ESCALATED` and later `APPROVED`.
- Package C plan says gate decision should become a gate contract/decision service with no self-approval and controller/user policy.

Minimum ownership:

- `agent_bus/gates.py`
- `tests/test_gate_contracts.py` and/or converted `tests/test_tasks_gates_reviews.py`
- Potentially `agent_bus/inbox.py` if gate approval request inbox delivery changes

Risk:

- Direct `GateBoard` compatibility is not the same as a stable API adapter. Gate tests should move to ProtocolKernel-backed gate services.

### Failure 5: lease/intent direct completion test

Classification: same as Failure 3; incompatible direct-mutator expectation.

Why:

- Test exists to prove coordination records are not permission enforcement, but it now uses guarded direct completion as its final assertion.
- The coordination-record behavior can remain valid while task completion assertion is converted to a claim/controller-commit flow.

Minimum ownership:

- `tests/test_tasks_gates_reviews.py`
- Later `agent_bus/tasks.py` / Package B task claim service if replacing direct completion with real v2 flow.

### Failure 6: ContextPacket create/get equality

Classification: Package A-only compatibility fix is possible; Package B owns the full target persistence contract later.

Why:

- The regression was introduced by Package A adding `ContextPacket.updated_at` default in `agent_bus/models.py`.
- Existing Package B-owned `agent_bus/context.py` does not persist/load `updated_at` yet.
- A minimal A-only compatibility fix can make `updated_at` optional/default `None` until Package B wires it into context persistence. Then returned and loaded packets both compare equal under current context storage.

Minimum ownership:

- Gate1 minimal: `agent_bus/models.py` only.
- Full target: `agent_bus/context.py`, context migration, and `tests/test_context_contracts.py` in Package B.

Risk:

- If Package A instead edits `context.py`, it crosses into Package B ownership. If Package A keeps non-null `updated_at`, it must also update context persistence, which is not in current Package A scope.

### Failure 7: replacement rehydration packet equality

Classification: same P1 root cause as Failure 6, plus later Package C replacement split.

Why:

- The failed equality is `context_sink.get_packet(approval.context_packet.packet_id) == approval.context_packet`.
- The packet mismatch is caused by `updated_at`, not by the replacement algorithm itself in this assertion.

Minimum ownership:

- Gate1 minimal: `agent_bus/models.py` only.
- Later target: Package C replacement protocol plus Package B context binding/rehydration persistence.

## Recommended Fixback Split

### Gate1 narrow fixback that can be done without opening B/C/D product scope

Only if QA accepts that old direct runtime tests are stale/incompatible:

- Package A:
  - `agent_bus/models.py`: make `ContextPacket.updated_at` compatible with current `context.py` persistence, likely optional/default `None`.
  - Optionally add/adjust Package A test coverage so event envelope and ContextPacket model compatibility are explicit.
- QA/F test decision:
  - Mark or convert direct `TaskBoard` / `GateBoard` old expectations so full pytest does not require both direct mutation success and direct mutation rejection.

This does not solve CLI/server replacement compatibility; it only avoids weakening guard invariants.

### Minimum actual runtime compatibility fixback

If QA requires full pytest to pass without marking old expectations stale, scope must expand beyond Package A:

- Package D:
  - `agent_bus/cli.py`
  - `agent_bus/server.py`
  - CLI/server tests
- Package B:
  - `agent_bus/tasks.py`
  - possibly `agent_bus/context.py`
  - task claim/context tests
- Package C:
  - `agent_bus/gates.py`
  - `agent_bus/replacement.py`
  - gate/replacement tests
- Package A:
  - `agent_bus/protocol.py`
  - `agent_bus/unit_of_work.py`
  - `agent_bus/protocol_models.py`
  - only if adapter result types or audit-only claim helpers are missing

### Suggested sequencing after worker1/helper1 outage

1. Runtime-qa decides whether Gate1 can pass with old direct-flow tests converted/xfail-deferred, or whether Gate1 requires a broader compatibility adapter fixback now.
2. If broader fixback is required, QA should assign helper2 a scoped implementation bundle explicitly. Helper2 should then broadcast OWNERSHIP before touching any product code.
3. Do not loosen SQLite triggers as the first fix. The triggers are currently the only durable prevention against direct authoritative mutation.
4. Preserve `tests/test_no_direct_authoritative_mutation.py` semantics unless QA explicitly changes the kernel gate contract.

## Open Risks

- Full pytest currently mixes old v1 direct board expectations with new v2 guard expectations. Without a QA test-contract decision, the suite contains contradictory requirements.
- Trigger-level `raise(abort, ...)` is intentionally strong but leaks raw `sqlite3.IntegrityError` through CLI/API where stable JSON/error or audit-only behavior is expected.
- Replacement approval remains too coupled: approval, reassignment, rehydration, inbox notice, and event append happen in one method.
- Context `updated_at` is an example of target-schema ahead of persistence code. Future Package B changes should avoid adding model fields without packet-to-row/row-to-packet coverage.

## Diagnostic Conclusion

The P1 ContextPacket failures have a low-risk Package A compatibility fix in `agent_bus/models.py`.

The P0 failures are not clean Package A-only bugs. They expose a boundary decision: either Gate1 updates/deconflicts stale direct-mutator tests, or QA must open a broader B/C/D compatibility adapter fixback. Weakening the Package A guard triggers to satisfy old direct tests would violate the kernel-v2 direction.
