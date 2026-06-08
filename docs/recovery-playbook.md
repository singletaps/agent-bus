# Recovery Playbook

Use this playbook when Agent Bus detects runtime degradation or when coordination files show stalled work.

## Broker Or Server Unavailable

1. Keep the worker alive.
2. Try final CLI commands first if available.
3. Fall back to the bootstrap broker:

```powershell
$AgentBus = 'C:\Users\laptopofzy\plugins\codex-agent-bus\scripts\agent_bus.py'
$BusFile = 'C:\Users\laptopofzy\Documents\Agent bus\coordination\agent-bus.ndjson'
$Broker = 'http://127.0.0.1:8765'

python $AgentBus status runtime-worker-4 --bus $BusFile --broker $Broker --state waiting --note 'broker fallback active'
python $AgentBus tail runtime-worker-4 --bus $BusFile --broker $Broker --once --history 80 --all
```

4. If broker writes fail, append a `BLOCKER` line to `coordination/messages.ndjson`.
5. Continue polling `USER_FEEDBACK.md`, `coordination/agent-status.md`, and `coordination/wave-gates.md`.

## Context Lost

Symptoms:

- Worker reports compression failure.
- The active context packet is invalidated.
- Session state becomes `CONTEXT_LOST` or `NEEDS_REHYDRATION`.

Actions:

```powershell
python -m agent_bus task progress <task_id> --actor <agent_id> --json
python -m agent_bus wait --agent <agent_id> --timeout 300 --json
```

Do not reconstruct context from chat memory. Wait for a context packet or replacement notice.

## Input Unavailable

Symptoms:

- Terminal session no longer accepts input.
- Agent is marked `INPUT_UNAVAILABLE`.

Actions:

- Mark health degraded.
- Ask helpers for diagnosis.
- Recommend replacement if the session cannot continue.
- Preserve task ID for replacement.

## Closed Session Still Shows Standby

Symptoms:

- The user closes a QA or worker window.
- The operations console still shows that agent as `STANDBY_READY`.
- The active session row has `active=1`, `ended_at` empty, and an old `last_seen_at`.

Diagnosis:

1. Check the projection and SQLite session row.
2. Check the event log for a later session-ended, input-unavailable, replacement, or state-update event.
3. Check the effective projected health from `/api/agents` and `/api/sessions`.
4. After the configured freshness window, a stale ready session should project as `STANDBY_DEGRADED` with `stale: true` and a `missing heartbeat` reason. A stale working session should project as `SUSPECTED_STUCK`.

Recovery actions:

```powershell
$Base = 'http://127.0.0.1:8787'
Invoke-RestMethod "$Base/api/agents" | ConvertTo-Json -Depth 8
Invoke-RestMethod "$Base/api/sessions" | ConvertTo-Json -Depth 8
```

- If the agent is still incorrectly projected as healthy `STANDBY_READY` after the freshness window, verify that the running server has the freshness projection code and check `AGENT_BUS_SESSION_FRESHNESS_SECONDS`.
- If the agent is alive and should be refreshed, send a heartbeat:

```powershell
$Body = @{ reason = 'poll alive' } | ConvertTo-Json -Compress
Invoke-RestMethod "$Base/api/agents/runtime-worker-4/heartbeat" -Method Post -Body $Body -ContentType 'application/json'
```

- If the agent is gone and its task must continue, use replacement flow and preserve the task ID.

Longer-term fix area:

- Add explicit session end/state commands or API endpoints for clean local-window shutdown.
- Keep operations console stale, degraded, ended, and replaced states visually distinct.

## Stale Or Stuck Session

Triggers:

- Missing heartbeat.
- Delivered inbox item not acked.
- Reported context loss.
- Input unavailable.
- Manual controller mark.

Actions:

```powershell
python -m agent_bus replacement approve --old-session-id <old_session_id> --task-id <task_id> --approved-by controller --candidate-agent <agent_id> --json
```

Approval should activate or create a replacement session, mark the old session replaced or degraded, create a rehydration packet, and enqueue `replacement_notice`.

## Malformed CLI JSON Metadata

Symptoms:

- A scripted `artifact create --metadata-json ... --json` command exits with code `2`.
- Structured stderr says `--metadata-json must be valid JSON`.
- The command came from PowerShell, nested PowerShell, or another shell with fragile quote escaping.

Actions:

1. Keep the original structured stderr as evidence.
2. Move metadata into a JSON file and pass `--metadata-json "@$MetadataPath"`.
3. Rerun the exact artifact command with `--json`.

Known-good PowerShell pattern:

```powershell
$MetadataPath = Join-Path $PWD 'artifact-metadata.json'
[ordered]@{
    passed = $true
    commands = @('wait', 'ack', 'artifact')
} | ConvertTo-Json -Compress | Set-Content -Encoding UTF8 $MetadataPath

python -m agent_bus artifact create live-test-report agent-bus://live/runtime-worker-2/cli-smoke --metadata-json "@$MetadataPath" --json
```

## Gate Failure

Gate failure is not permission to start the next wave. Required response:

1. Read QA findings.
2. Owners fix only their assigned files.
3. Helpers provide diagnosis or take over only when reassigned.
4. Rerun focused tests and integration tests.
5. Send the exact ready token again.
6. Wait for the next explicit gate pass.

## Budget-Limited Blocker

The user instructed that recurring budget-limited blockers must be reported directly. If this happens:

1. Send a bus message to the user or controller with the exact blocker.
2. Ask `runtime-helper-1` and `runtime-helper-2` for support.
3. Append a `BLOCKER` entry to `coordination/messages.ndjson`.
4. Keep listening.

Fallback record:

```json
{"ts":"2026-05-28T00:00:00Z","from":"runtime-worker-4","to":"user,runtime-helper-1,runtime-helper-2","type":"BLOCKER","text":"budget_limited while implementing C4 docs","files":["README.md"]}
```

## Human Interrupt

On interrupt, affected agents receive high-priority wakeups. Affected context packets are invalidated.

Worker response:

```powershell
python -m agent_bus wait --agent <agent_id> --timeout 300 --json
python -m agent_bus context get <new_context_packet_id> --json
```

Stop acting from old context immediately.

## Authority Or Fencing Reject

Symptoms:

- HTTP response contains `authority_reject` or `protocol_reject`.
- CLI JSON/stderr contains `projection_effect: REJECT`.
- A worker completion claim shows `projection_effect: AUDIT_ONLY` and `fencing_result: MISSING`, `INVALID`, `STALE_EPOCH`, or `WRONG_SESSION`.
- A free-form worker actor attempted a controller route.

Actions:

1. Do not retry by changing `actor` to look like a controller.
2. Identify the correct principal and route group: worker, controller, or user.
3. If the event is a worker completion, treat it as a claim and ask the controller to commit the claim.
4. If the fence is missing, fetch the active session/context packet and rerun only when the assignment is still valid.
5. Preserve the reject event as diagnostic evidence.

Useful probes:

```powershell
python -m agent_bus protocol events --limit 20 --json
python -m agent_bus protocol events --type adapter.deprecated_path_used --limit 20 --json
```

## Deprecated Adapter Warning

Symptoms:

- Diagnostics show `adapter.deprecated_path_used`.
- A legacy CLI command or old mixed HTTP route was used.

Actions:

1. Confirm the adapter emitted an audit event with `projection_effect=AUDIT_ONLY`.
2. Confirm the adapter did not bypass authority or fencing.
3. Prefer the canonical command next time:

```powershell
python -m agent_bus worker task complete <task_id> --actor <worker> --session-id <session_id> --session-epoch <epoch> --context-packet-id <packet_id> --json
python -m agent_bus controller gate approve <gate_id> --json
python -m agent_bus user interrupt create --text '...' --json
```

## Projection Or Frontend Drift

Symptoms:

- `ui.metro` no longer preserves old run/task/gate/artifact branch semantics.
- `ui.task_workflow` contains cross-task edges.
- Home, Communication, or Diagnostics shows demo/mock/fake data.
- Communication filters do not change the real message list.
- Diagnostics is missing protocol effects, fencing rejects, protocol violations, or deprecated adapter events.

Actions:

1. Query `/api/projections/operations` and compare `ui.task_workflow`, `ui.metro`, and `ui.diagnostics`.
2. Check whether taskless/global events are leaking into task workflow.
3. Keep raw event replay as diagnostic evidence only; normal UI state should come from projections.
4. Run focused projection/server tests and frontend build before reporting READY.

Useful checks:

```powershell
python -m pytest tests/test_protocol_projection.py tests/test_communication_projection.py tests/test_artifact_manifests.py tests/test_server.py -q

Set-Location 'C:\Users\laptopofzy\Documents\Agent bus\frontend'
npm run build
```

## Replacement Contract Break

Symptoms:

- Replacement loses the original `task_id`.
- Rehydration packet is missing or not bound to the replacement session.
- Old context bindings for unrelated tasks or sessions are invalidated.
- Old session fence still lets stale claims through.

Actions:

1. Check the replacement event chain:

```text
replacement.recommended
replacement.approval_requested
replacement.approved
replacement.reassignment_committed
```

2. Confirm the old task + old agent + old session binding only was invalidated.
3. Confirm the replacement packet has kind `REHYDRATION`.
4. Confirm old-session claims fail closed after replacement.
5. Preserve `task.reassigned` only as compatibility projection; use `replacement.reassignment_committed` as the root commit event.

## Post-Acceptance GitHub Push

The user instructed that accepted work should be pushed to GitHub after acceptance, then agents should keep listening on Agent Bus. Recovery rule:

1. Do not push before the explicit gate acceptance and publication assignment.
2. Confirm changed files and ownership boundaries.
3. Commit/push only under the assigned publishing owner.
4. Keep broker/fallback monitoring active after the push.
5. Let external review decide further modifications and the next construction plan.
