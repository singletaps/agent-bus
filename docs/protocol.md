# Protocol

Agent Bus protocol is event-sourced. SQLite is the source of truth; projections, inboxes, context packets, and UI views are derived runtime surfaces.

## Event Log

Every durable action appends an event with this envelope:

```text
seq
event_id
type
ts
actor
run_id
task_id
agent_id
correlation_id
causation_id
payload_json
```

Replay order is `seq` ascending. Agents do not normally read replay output as context. Replay is for diagnostics, auditing, and rebuilding projections.

## Identity And Session

Identity is stable:

```text
agent_id
role
capability history
created_at
updated_at
```

Session is replaceable:

```text
session_id
agent_id
run_id
active
runtime_state
last_seen_at
ended_at
replaced_by_session_id
```

An identity can have many sessions, but only one active session should drive current work.

Session freshness is derived by projections. Active sessions in ready, waiting, noop, or working states are compared with `last_seen_at`; after the configured freshness window, the projection reports a degraded effective state instead of preserving a healthy ready state. By default the freshness window is 300 seconds and can be overridden with `AGENT_BUS_SESSION_FRESHNESS_SECONDS`.

Missing heartbeat projection rules:

- Stale `STANDBY_READY`, `WAITING_ON_BUS`, and `WAIT_RETURNED_NOOP` sessions project as `STANDBY_DEGRADED`.
- Stale `WORKING` sessions project as `SUSPECTED_STUCK`.
- Projected health includes `stale: true`, a lower health score, and a `missing heartbeat` reason.

Heartbeat refresh is available through the API:

```powershell
$Body = @{ reason = 'poll alive' } | ConvertTo-Json -Compress
Invoke-RestMethod 'http://127.0.0.1:8787/api/agents/runtime-worker-4/heartbeat' -Method Post -Body $Body -ContentType 'application/json'
```

The heartbeat response contains the refreshed session, refreshed health, and an `agent.status_changed` event for SSE/projection refresh. Closing a local Codex or QA window may still leave an active session row in SQLite until an explicit end-state exists, but it should not remain projected as healthy `STANDBY_READY` after heartbeat freshness expires.

## Inbox Wait And Ack

Workers wait through per-agent inboxes:

```powershell
python -m agent_bus wait --agent worker.frontend --timeout 300 --json
```

The response is either a minimal actionable item or noop. Delivered items must be acked:

```powershell
python -m agent_bus ack <inbox_id> --agent worker.frontend --json
```

Unacked delivered items can become visible again after their visibility timeout. Busy workers receive only urgent control items such as user interrupts, context invalidation, gate results, replan notices, and replacement notices.

## Context Packets

Context packets are authoritative. A packet contains the role contract, current task, summary, instructions, artifacts, open inbox item IDs, required artifacts, next action, and invalidated packet IDs when rehydrating.

Normal worker flow:

```powershell
python -m agent_bus wait --agent worker.frontend --timeout 300 --json
python -m agent_bus context get <context_packet_id> --json
```

If a packet is invalidated, the worker must stop using it and wait for a replan or rehydration packet.

If a live assignment has no `context_packet_id`, the worker may act only when the inbox payload and task title are sufficient and self-contained. The worker should ack the inbox item, ack/progress the task, and report the missing packet as a gap to the controller. Ambiguous assignments without context must be clarified before implementation.

## Runs And Tasks

Task commands are part of the final CLI surface. If an older checkout does not expose them yet, agents still follow the same task protocol through inbox items, context packets, and fallback bus messages.

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

Expected task flow:

```powershell
python -m agent_bus task create 'Implement API' --run-id <run_id> --assignee worker.backend --json
python -m agent_bus task ack <task_id> --actor worker.backend --json
python -m agent_bus task progress <task_id> --actor worker.backend --json
python -m agent_bus task complete <task_id> --actor worker.backend --json
```

Completing a task returns the active worker session to `STANDBY_READY`. If that session later stops heartbeating, projections degrade it according to the session freshness rules above.

Lease and intent records are coordination records. They explain ownership and planned action, but they are not a security or permission enforcement layer.

## Artifacts And JSON Metadata

Artifacts attach evidence to runs and tasks:

```powershell
python -m agent_bus artifact create test-log file://test.log --run-id <run_id> --task-id <task_id> --json
```

`--metadata-json` must be a JSON object. It can be inline JSON or `@path` to a UTF-8 JSON file. The `@path` form is the recommended PowerShell-safe contract:

```powershell
$MetadataPath = Join-Path $PWD 'artifact-metadata.json'
[ordered]@{
    passed = $true
    commands = @('wait', 'ack', 'artifact')
} | ConvertTo-Json -Compress | Set-Content -Encoding UTF8 $MetadataPath

python -m agent_bus artifact create live-test-report agent-bus://live/runtime-worker-2/cli-smoke --metadata-json "@$MetadataPath" --json
```

Malformed metadata JSON is a usage error. With `--json`, the CLI writes structured JSON to stderr and exits with code `2`.

## Gates

Gate states:

```text
open
approved
rejected
escalated
expired
```

High-risk gates are not auto-approved. They create a controller or user action item:

```powershell
python -m agent_bus gate approve <gate_id> --actor qa --json
```

If the gate is high risk and QA is not allowed to approve it directly, the gate is escalated and a controller action item is enqueued.

## Reviews

Structured finding fields:

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

`changes_requested` creates a worker inbox item with finding IDs. Findings are resolved one by one, not as an all-or-nothing blob.

## Human Interrupts

A user interrupt creates `user.interrupt_created`, computes affected agents, invalidates affected context packets, and enqueues high-priority wakeups:

```text
user_interrupt
context_invalidated
agent_replan_required
```

Unrelated standby agents should not be woken.

## Replacement

Replacement is recommendation plus approval:

1. Health rules mark a session stale or suspect.
2. The bus scores candidates by capability confidence, freshness, standby readiness, failure history, role compatibility, and user preference.
3. Controller or user approval keeps the original `task_id` stable.
4. The old session is marked `REPLACED` or degraded.
5. The replacement receives a rehydration packet and continues the same task.

## Protocol Kernel V2 Authority

Every durable write resolves to an explicit `Principal`. Free-form `actor` strings are descriptive metadata, not authority. The accepted principal types are:

```text
system
controller
user
agent
```

Controller and user principals can make control-plane decisions such as gate decisions, task-claim commits, replacement approval, and user interrupts. Agent principals can claim work and submit evidence, but they cannot directly mutate controller-owned task state. Unauthorized writes fail closed with `authority_reject` or `protocol_reject` and record `ProjectionEffect.REJECT` when the protocol path can record it.

Protocol writes carry:

```text
projection_effect = COMMIT | AUDIT_ONLY | REJECT
fencing_result = VALID | MISSING | INVALID | STALE_EPOCH | WRONG_SESSION | NOT_REQUIRED
```

`COMMIT` means the write mutated durable business state. `AUDIT_ONLY` means the event is preserved for audit/diagnostics without mutating the authoritative state. `REJECT` means the requested write was refused.

## Worker Claims And Session Fencing

Worker completion is a claim, not an automatic controller commit. The canonical worker API and CLI are:

```powershell
Invoke-RestMethod "$Base/api/worker/tasks/<task_id>/complete" -Method Post -Body ($Body | ConvertTo-Json) -ContentType 'application/json'
python -m agent_bus worker task complete <task_id> --actor <worker_agent_id> --session-id <session_id> --session-epoch <epoch> --context-packet-id <packet_id> --json
```

When session fencing is missing, stale, or bound to the wrong session, the worker claim stays audit-only. The expected missing-fence result is:

```text
projection_effect = AUDIT_ONLY
fencing_result = MISSING
```

Controller commit is a separate control-plane decision:

```powershell
Invoke-RestMethod "$Base/api/controller/task-claims/<claim_id>/commit" -Method Post -Body (@{actor='controller'} | ConvertTo-Json) -ContentType 'application/json'
python -m agent_bus controller task-claim commit <claim_id> --json
```

This separation preserves the invariant that workers provide evidence and intent while controllers or users decide durable control-plane state.

## Canonical And Legacy Adapters

The canonical HTTP write groups are:

```text
/api/worker/*
/api/controller/*
/api/user/*
/api/projections/*
```

The canonical CLI groups mirror those roles:

```powershell
python -m agent_bus worker ...
python -m agent_bus controller ...
python -m agent_bus user ...
python -m agent_bus protocol events --type adapter.deprecated_path_used --json
```

Legacy mixed routes and CLI aliases remain compatibility adapters. They must emit `adapter.deprecated_path_used` audit events and must not bypass authority, fencing, or protocol enforcement. A compatibility adapter can be convenient for old consumers, but the canonical role-scoped path is the contract new agents should use.

## Replacement Event Chain

Replacement uses correlated protocol events rather than one opaque reassignment:

```text
replacement.recommended
replacement.approval_requested
replacement.approved
replacement.reassignment_committed
```

The original `task_id` is preserved. The replacement path creates a `REHYDRATION` context packet for the replacement session, invalidates only the old task + old agent + old session active binding, and marks the old session fence inactive/replaced. Existing adapters may still expose `task.reassigned` as a compatibility projection, but `replacement.reassignment_committed` is the root replacement commit event.

## UI Projections And Diagnostics

Operations projections separate task workflow from compatibility metro:

- `ui.task_workflow` is the task-scoped workflow projection. It can include context, claim, gate, artifact, replacement, terminal, start, and task nodes.
- `ui.metro` is a legacy compatibility projection for old run/task/gate/artifact consumers. It preserves the old gate/artifact branch semantics.
- Cross-task workflow edges are rejected or dropped and surfaced as diagnostics instead of silently connecting unrelated tasks.
- Taskless or global events belong in timeline, communication, or diagnostics views, not in a task workflow unless an explicit task binding exists.

Diagnostics expose real protocol records:

```text
projection_effects
fencing_rejects
protocol_violations
deprecated_adapter_events
```

Raw replay remains an audit and diagnostics tool. Normal agents should work from inbox items and context packets, not from raw replay.
