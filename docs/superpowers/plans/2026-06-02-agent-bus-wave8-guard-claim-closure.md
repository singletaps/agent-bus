# Agent Bus Wave8 Guard and Claim Closure Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix the remaining P0 `kernel_write_guards` leak before any main merge, then prepare the non-blocking fenced completion-claim API follow-up.

**Architecture:** Treat `kernel_write_guards` target guards as short-lived, action-scoped mutation tokens, not permanent authorization records. Authoritative direct table triggers must verify the current state transition's action and reject stale or unrelated guards; successful guarded mutations must consume the matching target guard inside the same SQLite transaction. The worker completion-claim API is a separate P1 package and must wait until the guard fix is accepted so shared kernel/API files do not conflict.

**Tech Stack:** Python, SQLite triggers, pytest, FastAPI, existing Agent Bus protocol/kernel modules.

---

## Review Triage

Adopt now:
- P0 `kernel_write_guards` leak. Verified in `agent_bus/migrations.py`: task/gate triggers check only `target_table` and `target_id`; `UnitOfWork.add_kernel_guard()` creates permanent rows with no `consumed_at` or `expires_at`. Repro: after `TaskBoard.assign_task()`, direct SQL `update tasks set status='completed'` is currently allowed.

Adopt after P0 is accepted:
- P1 real fenced worker completion-claim API. Verified in `agent_bus/server.py`: `WorkerTaskCompleteRequest` has no `fencing_token`; `/api/worker/tasks/{task_id}/complete` calls `ProtocolKernel.record_task_completion_claim()`, which intentionally records `AUDIT_ONLY` / `MISSING` / `NEEDS_FENCING`.

Defer to v2.1/backlog:
- Durable `replacement_approvals` saga table and crash recovery scan. Current runtime rollback is accepted as an MVP but not crash-durable.
- Broader command-model convergence (`approve_replacement`, `decide_gate`, `worker_claim_task`, `controller_commit_claim`).
- P2 frontend information-noise reduction beyond Wave7 accepted task-scoped workflow/operator labels.

## Gate Protocol

Wave8 is CLOSED until owners ACK. Gate8 passes only after Package J is accepted and full aggregate verification passes. Package K may begin only after `WAVE8_PACKAGE_J_ACCEPTED`.

Expected gate token:

```text
GATE_PASS wave8 kernel guard closure
```

## Package J: P0 Transaction-Scoped Kernel Guards

**Owner:** `runtime-worker-7`

**Files:**
- Modify: `agent_bus/migrations.py`
- Modify: `agent_bus/unit_of_work.py`
- Modify if needed: `agent_bus/protocol.py`
- Test: `tests/test_kernel_write_guards.py`
- Regression: `tests/test_no_direct_authoritative_mutation.py`
- Regression: `tests/test_protocol_kernel.py`
- Regression: `tests/test_task_claims.py`
- Regression: `tests/test_replacement_atomicity.py`
- Regression: `tests/test_live_protocol_simulation.py`

- [ ] **Step 1: Write failing stale-guard tests**

Create `tests/test_kernel_write_guards.py` with tests proving stale or wrong-action target guards do not authorize later direct SQL.

Required assertions:

```python
with sqlite3.connect(db_path) as conn:
    with pytest.raises(sqlite3.IntegrityError, match="active ProtocolKernel guard"):
        conn.execute("update tasks set status = 'completed' where task_id = ?", (task_id,))
```

Cover these cases:
- After a legitimate `TaskBoard.assign_task()`, direct SQL updates of the same task to `completed`, `failed`, and `reassigned` are blocked.
- After a legitimate gate approval, direct SQL update of the same gate to `rejected` is blocked.
- A guard for `task.assigned` does not authorize `task.completed`.
- A consumed `gate.approved` guard does not authorize a later `gate.rejected`.

Run:

```powershell
python -m pytest tests/test_kernel_write_guards.py -q
```

Expected before implementation: at least the task direct-SQL test fails because the stale assignment guard is accepted by the trigger.

- [ ] **Step 2: Add guard lifecycle columns**

Update `agent_bus/migrations.py` so `kernel_write_guards` includes:

```sql
operation_id text,
consumed_at text,
expires_at text
```

Add migration compatibility for existing databases with `add_column_if_missing`. Keep existing `event_id`, `target_table`, `target_id`, and `action` columns.

- [ ] **Step 3: Make UnitOfWork create short-lived target guards**

Update `UnitOfWork` so each transaction has an `operation_id` and `add_kernel_guard()` stores it. For target guards, set `expires_at` to a short future timestamp. Event guards may remain event-scoped for the event-log insert trigger.

Expected shape:

```python
insert into kernel_write_guards (
    guard_id, event_id, target_table, target_id, action,
    operation_id, expires_at
) values (?, ?, ?, ?, ?, ?, ?)
```

Invariant: target guards are useful only for the current guarded mutation, not as historical authorization.

- [ ] **Step 4: Make task trigger action-scoped and single-use**

Replace `trg_tasks_authoritative_status_guard` so it maps the status transition to the allowed action:

```sql
case new.status
  when 'completed' then 'task.completed'
  when 'failed' then 'task.failed'
  when 'reassigned' then 'task.reassigned'
end
```

Allow `replacement.reassignment_committed` as an additional action for `new.status = 'reassigned'`.

The trigger must require:
- matching `target_table = 'tasks'`
- matching `target_id = new.task_id`
- matching action for the new status
- `consumed_at is null`
- `expires_at is null or expires_at > now`

Error text should include `active ProtocolKernel guard`.

- [ ] **Step 5: Consume task target guards after successful mutation**

Add an `after update of status on tasks` trigger that sets `consumed_at` on the matching target guard used by the transition. It must consume only the matching action and target, not all guards for the task.

- [ ] **Step 6: Make gate trigger action-scoped and single-use**

Apply the same pattern to `trg_gates_authoritative_state_guard`:

```sql
case new.state
  when 'approved' then 'gate.approved'
  when 'rejected' then 'gate.rejected'
  when 'escalated' then 'gate.escalated'
end
```

Require matching target, action, unconsumed state, and unexpired state. Add an after-trigger to consume the matching gate guard.

- [ ] **Step 7: Verify Package J**

Run:

```powershell
python -m pytest tests/test_kernel_write_guards.py tests/test_no_direct_authoritative_mutation.py tests/test_protocol_kernel.py tests/test_task_claims.py tests/test_replacement_atomicity.py tests/test_live_protocol_simulation.py -q
python -m pytest -q
git diff --check -- agent_bus/migrations.py agent_bus/unit_of_work.py agent_bus/protocol.py tests/test_kernel_write_guards.py tests/test_no_direct_authoritative_mutation.py tests/test_protocol_kernel.py tests/test_task_claims.py tests/test_replacement_atomicity.py tests/test_live_protocol_simulation.py
```

READY report must include root-cause classification, invariant preserved, exact files changed, and exact test outputs.

## Package K: P1 Fenced Worker Completion-Claim API

**Owner:** `runtime-worker-5`

**Start condition:** Wait for `WAVE8_PACKAGE_J_ACCEPTED`. Do not edit shared kernel/API files before that.

**Files:**
- Modify: `agent_bus/server.py`
- Modify: `agent_bus/protocol.py`
- Modify if needed: `agent_bus/tasks.py`
- Modify if needed: `agent_bus/cli.py`
- Test: `tests/test_worker_completion_claim_api.py`
- Regression: `tests/test_worker_api.py`
- Regression: `tests/test_controller_api.py`
- Regression: `tests/test_cli_wave_c.py`

- [ ] **Step 1: Write failing fenced completion-claim API tests**

Add tests for:
- `POST /api/worker/tasks/{task_id}/completion-claim` requires `actor`, `session_id`, `session_epoch`, `fencing_token`, `context_packet_id`, and payload.
- Valid active fence plus active task context binding returns `projection_effect = COMMIT`, `fencing_result = VALID`, and `claim.status = PENDING`.
- Missing or invalid fencing token returns a stable fail-closed response and does not create a pending claim.
- Existing `/api/worker/tasks/{task_id}/complete` remains deprecated audit-only and returns `AUDIT_ONLY` / `MISSING` / `NEEDS_FENCING`.

Run:

```powershell
python -m pytest tests/test_worker_completion_claim_api.py -q
```

- [ ] **Step 2: Implement the new route and kernel path**

Add a request model with `fencing_token`. Use the existing task claim model/status where possible. The new route must not advance task state; it creates a pending worker claim for controller commit.

- [ ] **Step 3: Verify Package K**

Run:

```powershell
python -m pytest tests/test_worker_completion_claim_api.py tests/test_worker_api.py tests/test_controller_api.py tests/test_cli_wave_c.py -q
python -m pytest -q
```

READY report must explain why `/complete` remains deprecated and why `/completion-claim` is the real fenced path.

## Controller / QA Duties

**Owner:** `runtime-helper-2`

- [ ] Broadcast Wave8 package assignments and collect ACKs.
- [ ] Keep Gate8 CLOSED until Package J is accepted and aggregate verification passes.
- [ ] After Package J accepted, decide whether Package K should run before publication or be scheduled as v2.1 based on user merge intent.
- [ ] Record v2.1 backlog items: replacement durable saga, command API convergence, and frontend diagnostic-noise refinement.
- [ ] Continue broker/fallback monitoring and relay any new `USER_FEEDBACK.md` blocks.

## Acceptance Criteria

Gate8 can pass when:
- Stale/wrong-action task and gate target guards cannot authorize later direct SQL.
- Matching target guards are action-scoped and consumed after successful authoritative mutation.
- Full pytest passes.
- Existing Wave7 G/H/I accepted behavior remains intact.
