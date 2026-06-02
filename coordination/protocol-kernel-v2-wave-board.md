# Protocol Kernel v2 Wave Board

Runtime owner: `runtime-qa`
Plan: `docs/superpowers/plans/2026-06-01-agent-bus-protocol-kernel-v2.md`
Branch: `codex/protocol-kernel-v2`
Broker: `http://127.0.0.1:8765`
Primary bus: `coordination/agent-bus.ndjson`
Fallback files: `coordination/messages.ndjson`, `coordination/agent-status.md`, `coordination/wave-gates.md`, `USER_FEEDBACK.md`
Created: `2026-06-01T15:08:00+08:00`

## User Directive

User resumed after restart and announced the next phase will be Agent Bus kernel refactor. Communication must use broker first and fallback files second.

## Gate Discipline

- Runtime-qa owns serial gates.
- No implementation package may edit code before a runtime-qa package assignment.
- Every implementation agent must broadcast availability and intended ownership before edits.
- File ownership is exclusive within a wave.
- A package that needs another package's owned file must request handoff through broker.
- Broker is primary; fallback records must stay current if broker degrades.

## Wave 0: Branch, Baseline, And Bus

Gate state: `open`

Completed:

- Broker restored on `http://127.0.0.1:8765`.
- Branch created: `codex/protocol-kernel-v2`.
- Dirty worktree recorded:
  - `USER_FEEDBACK.md`
  - `coordination/agent-status.md`
  - `coordination/runtime-helper-1-monitor.state.json`
  - `coordination/wave-gates.md`
  - untracked `docs/superpowers/plans/2026-06-01-agent-bus-protocol-kernel-v2.md`

Pending:

- Agents report online/capacity and wait for runtime-qa package assignments.

Baseline evidence:

- `python -m pytest -q`: passed, `67 passed in 10.81s`.
- `npm --prefix frontend run build`: passed, Vite built 1775 modules.

Required Wave 0 close condition:

- Baseline evidence recorded.
- At least Package A owner is assigned and ACKed.
- No agent has started unassigned implementation edits.

## Package Map Draft

Active roster after user/controller update:

- `runtime-helper-2`
- `runtime-qa`

Excluded for this wave:

- `runtime-worker-4`: user reported worker4 cannot respond; no implementation scope.
- `runtime-worker-1`: user reported context compaction failure/unreliable after Gate1 fail; no new write scope until restored.
- `runtime-helper-1`: user reported context compaction failure/unreliable after Gate1 fail; no new write scope until restored.
- `runtime-worker-2` and `runtime-worker-3`: context only unless user later re-adds them.

Immediate assignments:

- Package A Kernel: `runtime-worker-1`
  - Status: GATE1 FAILED; original owner now unavailable per user, waiting for reassignment/handoff path.
  - Scope: `agent_bus/models.py`, `agent_bus/protocol_models.py`, `agent_bus/db.py`, `agent_bus/migrations.py`, `agent_bus/protocol.py`, `agent_bus/authority.py`, `agent_bus/policy.py`, `agent_bus/fencing.py`, `agent_bus/unit_of_work.py`, `tests/test_protocol_kernel.py`, `tests/test_migrations.py`, `tests/test_no_direct_authoritative_mutation.py`.
  - Scope extension: `agent_bus/store.py` is accepted only for EventStore persistence/replay of Package A protocol envelope fields and `ProjectionEffect` / `FencingResult` enum serialization/parsing. Runtime-qa reviewed the current diff and found it within this narrow extension.
  - Gate1 fail evidence: focused Package A pytest passed (`29 passed`), CLI help passed, but `python -m pytest -q` failed (`7 failed, 75 passed`). Blockers are public compatibility/runtime paths surfacing raw `sqlite3.IntegrityError` from authority triggers and `ContextPacket` round-trip `updated_at` mismatch.
- Package B/C prep: `runtime-helper-2`
  - Status: READY accepted; artifact `coordination/kernel-v2-package-bc-prep-helper2.md`.
  - Output: service contract/risk prep for tasks/context/gates/reviews/replacement.
- Gate1 failure diagnostic: `runtime-helper-2`
  - Status: READY accepted; artifact `coordination/kernel-v2-gate1-fixback-diagnostic-helper2.md`.
  - Scope: own/create `coordination/kernel-v2-gate1-fixback-diagnostic-helper2.md` only; no product-code edits yet.
  - QA decision: P1 `ContextPacket.updated_at` drift is a narrow Package A compatibility fix; P0 raw SQLite guard errors are not Package A-only and remain Gate1 blockers requiring B/C/D adapter/test-contract handoff. SQLite guard triggers must not be weakened to satisfy old direct-mutator tests.
- Gate1 P1 fixback: `runtime-helper-2`
  - Status: READY accepted after independent QA verification.
  - Scope: `agent_bus/models.py` only; `tests/test_context.py` may be touched only if a minimal regression assertion is necessary.
  - Forbidden: `agent_bus/context.py`, `agent_bus/tasks.py`, `agent_bus/gates.py`, `agent_bus/replacement.py`, `agent_bus/cli.py`, `agent_bus/server.py`, `agent_bus/migrations.py`, `agent_bus/protocol*.py`, `agent_bus/unit_of_work.py`, `agent_bus/store.py`, `frontend`.
  - Verification: `python -m pytest tests/test_context.py::test_create_and_get_packet_round_trips_structured_context tests/test_replacement.py::test_controller_approval_switches_replacement_and_rehydrates_same_task tests/test_protocol_kernel.py tests/test_migrations.py tests/test_no_direct_authoritative_mutation.py tests/test_store.py tests/test_agents.py -q` passed with `31 passed in 2.34s`.
  - Full suite after P1: `python -m pytest -q` failed with `5 failed, 77 passed in 13.16s`; remaining failures are P0 compatibility/direct-mutator adapter failures only.
- Gate1 P0 adapter handoff: `runtime-helper-2`
  - Status: READY received; independent QA verified tests but Gate1 remains failed/closed on Wave1 write-path completeness.
  - Scope: `agent_bus/tasks.py`, `agent_bus/gates.py`, `agent_bus/replacement.py`, `agent_bus/cli.py`, `agent_bus/server.py`, `agent_bus/protocol.py`, `agent_bus/unit_of_work.py`, `agent_bus/protocol_models.py`, and tests limited to `tests/test_cli_wave_c.py`, `tests/test_tasks_gates_reviews.py`, `tests/test_server.py`, `tests/test_replacement.py`, plus new focused tests if useful.
  - Goal: clear the remaining 5 P0 failures without weakening SQLite guard triggers or allowing public Board/Coordinator authority bypass.
  - Required behavior: deprecated worker `task complete` becomes audit-only completion claim with `fencing_result=MISSING` / `claim.status=needs_fencing` and does not set task completed; direct TaskBoard/GateBoard mutation expectations align with v2 guards; CLI/API compatibility routes do not leak raw `sqlite3.IntegrityError`; replacement approval does not call unguarded `TaskBoard.assign_task`.
  - Forbidden: migration trigger loosening, frontend, `agent_bus/store.py`, `agent_bus/db.py`, and further `agent_bus/models.py` changes unless BLOCKER/SCOPE_REQUEST is accepted.
  - Independent QA verification: focused P0 command passed with `7 passed in 3.88s`; Package A foundation/guard command passed with `29 passed in 2.12s`; full `python -m pytest -q` passed with `82 passed in 13.21s`; `python -m agent_bus --help` exited 0.
  - Blocking finding: plan lines 878-883 require Wave1 to prevent business writes from bypassing `ProtocolKernel` / `UnitOfWork` before Wave2. Current `TaskBoard.create_run`, `TaskBoard.create_task`, `TaskBoard.assign_task`, `ContextStore.create_packet`, `InboxStore.enqueue`, and parts of `ReplacementCoordinator.approve` still write state/events/inbox/context directly outside the kernel. One-off QA proof showed a free-form worker actor can direct-call create/assign and persist `run.created`, `task.created`, and `task.assigned` events with no `kernel_write_guards` and no `projection_effects`.
  - Gate decision: do not release Wave2 until these public write paths are downgraded to internal repository mutators or routed through ProtocolKernel-owned services. This is broader than the P0 adapter cleanup and needs an explicit scoped fixback/handoff.
- Package D/E prep: `runtime-helper-1`
  - Status: READY accepted; artifact `coordination/kernel-v2-package-de-prep-helper1.md`.
  - Output: API/CLI/projection/frontend contract prep and dependency map.
- Package F QA/Docs/Simulation: `runtime-qa` until later scoped helper handoff.

## Current State

Runtime-qa completed Wave 0 baseline checks and assigned Wave 1 Package A to `runtime-worker-1`; helpers completed read-only prep. Gate 1 is closed after independent QA failure.

Helper prep status: B/C prep, D/E prep, Gate1 diagnostic, P1 fixback, and P0 adapter/test-contract cleanup are accepted as partial progress. Gate1 remains closed because Wave1 still has public durable write paths bypassing `ProtocolKernel` / `UnitOfWork`; runtime-helper-2 has been sent a new scoped fixback request.
