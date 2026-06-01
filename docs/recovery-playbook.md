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
