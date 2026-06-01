# BUG-2 Helper1 Independent Cross-Check

Time: 2026-05-28T16:17:00+08:00

Run: `run_baa1ce49d36e43b1ae6b22737fb91fcd`

Task: `task_48fb94c022c64afbbbfeda0473752c89`

Artifact under review: `artifact_cafcfb79284e448fa8406f3fcb4c4e62`

## Scope

Independently verify the Command Composer mixed target/task routing fix implemented by `runtime-helper-2` after `runtime-worker-3` lost contact.

## Evidence Checked

1. Source behavior in `frontend/src/App.tsx`:
   - `submitInterrupt` now receives `includeSelectedTask`.
   - `taskContext` is undefined when selected task context is not included.
   - `task_id`, `run_id`, and `task_owner` are sent only from `taskContext`.
   - Explicit target agent is placed in `additional_agents` only when it differs from task owner.
   - Payload includes `routing_mode` and `include_selected_task`.

2. UI affordance in `frontend/src/App.tsx`:
   - Command Composer shows selected task id and owner.
   - `Include task context` checkbox is disabled when no task exists.
   - When target agent differs from selected task owner, the effect defaults `includeSelectedTask` to false.
   - Status pill shows `agent only` or `task context`.

3. Live DB event evidence:
   - `event_log.seq=107`
   - `type=user.interrupt_created`
   - `actor=operations-console`
   - `task_id=null`
   - payload `routing_mode=agent-only`
   - payload `include_selected_task=false`
   - payload `selected_task_id=task_7ae9e0ac561b49c885f49d04d8016dd2`
   - payload `affected_agents=["controller","observer","runtime-helper-2","qa"]`
   - `runtime-worker-1` is not in affected agents even though the selected task belonged to Worker1.

## Result

BUG-2 independent cross-check passes for the reported failure mode: an agent-only target no longer wakes the unrelated selected-task owner by default.

## Remaining Risk

Final helper2 QA should still run browser/API checks after the live service reloads for backend BUG-1 changes and frontend build output is active.
