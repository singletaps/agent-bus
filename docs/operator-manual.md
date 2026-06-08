# Operator Manual

This manual describes how to run Agent Bus as the local operations control plane for permanent Codex workers.

## Start The Runtime

These commands run the final runtime. Confirm the available command set with `python -m agent_bus --help`. If an older checkout is missing a command, use fallback coordination instead of stopping.

PowerShell:

```powershell
Set-Location 'C:\Users\laptopofzy\Documents\Agent bus'
$env:AGENT_BUS_DB = (Join-Path (Get-Location) '.local\agent-bus.sqlite3')

python -m agent_bus init --reset --json
python -m agent_bus seed --json
python -m agent_bus serve --host 127.0.0.1 --port 8765
```

Expected result:

- SQLite is initialized with WAL enabled.
- Seed creates default controller, observer, worker, helper, and QA identities.
- The FastAPI server exposes `/api/*`, `/docs`, and the static operations console.

## Register A Worker

```powershell
Set-Location 'C:\Users\laptopofzy\Documents\Agent bus'
$env:AGENT_BUS_DB = (Join-Path (Get-Location) '.local\agent-bus.sqlite3')

python -m agent_bus agent register runtime-worker-4 --role docs --json
python -m agent_bus wait --agent runtime-worker-4 --timeout 300 --json
```

The wait command should either deliver a minimal inbox item or return:

```json
{"item":null,"kind":"noop","noop":true,"ok":true,"session":null,"timed_out":true}
```

Timeout is not exit. Timeout means wait again.

## Live Real-Service Test Runs

When QA or a controller publishes a real-service URL and DB, use those exact values instead of the default `.local` database. In the May 28 live run the service used `http://127.0.0.1:8787/` and `coordination\live-agent-bus.sqlite3`.

```powershell
Set-Location 'C:\Users\laptopofzy\Documents\Agent bus'
$LiveDb = 'C:\Users\laptopofzy\Documents\Agent bus\coordination\live-agent-bus.sqlite3'

python -m agent_bus agent register runtime-worker-4 --role docs --state STANDBY_READY --db $LiveDb --json
python -m agent_bus wait --agent runtime-worker-4 --timeout 300 --db $LiveDb --json
```

Controller task assignment flow:

```powershell
python -m agent_bus task create 'Worker4: audit docs against real-service workflow and capture gaps' --run-title 'Live Real-Service Test Round 1' --objective 'Exercise the real service and capture feedback' --owner runtime-helper-1 --assignee runtime-worker-4 --priority 80 --db $LiveDb --json
python -m agent_bus gate create 'Real-service docs audit gate' --run-id <run_id> --task-id <task_id> --owner runtime-qa --requested-by runtime-helper-1 --risk medium --db $LiveDb --json
```

Worker handling flow for live assignments:

```powershell
python -m agent_bus wait --agent runtime-worker-4 --timeout 0 --db $LiveDb --json
python -m agent_bus ack <inbox_id> --agent runtime-worker-4 --db $LiveDb --json
python -m agent_bus task ack <task_id> --actor runtime-worker-4 --db $LiveDb --json
python -m agent_bus task progress <task_id> --actor runtime-worker-4 --db $LiveDb --json
```

Some live `task_assigned` inbox items may be self-contained and have `context_packet_id: null`. Do not invent extra context from chat history. If the title and payload are enough to act, proceed narrowly and report the missing context packet as a runtime/documentation gap. If the assignment is ambiguous, ask the controller or helpers before editing files.

## Normal Worker Loop

```powershell
python -m agent_bus wait --agent runtime-worker-4 --timeout 300 --json
python -m agent_bus context get <context_packet_id> --json
python -m agent_bus ack <inbox_id> --agent runtime-worker-4 --json
python -m agent_bus task progress <task_id> --actor runtime-worker-4 --json
python -m agent_bus task complete <task_id> --actor runtime-worker-4 --json
python -m agent_bus wait --agent runtime-worker-4 --timeout 300 --json
```

Rules:

- Fetch the context packet before acting.
- Ack only the item you are actually handling.
- Report progress through task commands, not by relying on chat history.
- After task completion, return to standby and wait again.

## Gate Workflow

Workers send exact ready tokens through the bus or final CLI, for example:

```text
WAVE_C_TASK4_READY runtime-worker-4. Changed: README.md, skills/agent-bus/SKILL.md, docs/operator-manual.md, docs/protocol.md, docs/recovery-playbook.md, docs/subagent-contracts.md. Tests: ...
```

QA owns gate pass/fail broadcasts. Workers must not start the next wave until the explicit gate pass appears.

## Fallback Coordination

If the final API or broker is unavailable, use the bootstrap broker:

```powershell
$AgentBus = 'C:\Users\laptopofzy\plugins\codex-agent-bus\scripts\agent_bus.py'
$BusFile = 'C:\Users\laptopofzy\Documents\Agent bus\coordination\agent-bus.ndjson'
$Broker = 'http://127.0.0.1:8765'

python $AgentBus send runtime-worker-4 --bus $BusFile --broker $Broker 'runtime-worker-4 standing by'
python $AgentBus status runtime-worker-4 --bus $BusFile --broker $Broker --state waiting --note 'waiting for gate'
python $AgentBus tail runtime-worker-4 --bus $BusFile --broker $Broker --once --history 80 --all
```

If even that fails, append to `coordination/messages.ndjson`:

```json
{"ts":"2026-05-28T00:00:00Z","from":"runtime-worker-4","to":"runtime-helper-1,runtime-helper-2","type":"BLOCKER","text":"cannot reach broker","files":[]}
```

Use `coordination/agent-status.md` for coarse heartbeat status and `coordination/wave-gates.md` for gate notes during broker failure.

## Operator Checks

```powershell
python -m pytest -v
python -m agent_bus models --json

Set-Location 'C:\Users\laptopofzy\Documents\Agent bus\frontend'
npm install
npm run build
```

The operations console should show agents, sessions, context integrity, pending inbox items, tasks, gates, review findings, replacement recommendations, and timeline events.

## Protocol V2 Operator Flow

Use role-scoped APIs and CLI commands for new work. Keep legacy mixed paths only for compatibility checks.

Worker claim:

```powershell
$Body = @{
    actor = 'runtime-worker-7'
    session_id = '<session_id>'
    session_epoch = 1
    context_packet_id = '<context_packet_id>'
} | ConvertTo-Json -Compress
Invoke-RestMethod "$Base/api/worker/tasks/<task_id>/complete" -Method Post -Body $Body -ContentType 'application/json'

python -m agent_bus worker task complete <task_id> `
  --actor runtime-worker-7 `
  --session-id <session_id> `
  --session-epoch 1 `
  --context-packet-id <context_packet_id> `
  --json
```

Controller decisions:

```powershell
python -m agent_bus controller gate approve <gate_id> --evidence-artifact-id <artifact_id> --json
python -m agent_bus controller gate reject <gate_id> --reason 'missing evidence' --json
python -m agent_bus controller task-claim commit <claim_id> --json
```

User interrupt:

```powershell
python -m agent_bus user interrupt create --text 'pause and replan' --task-id <task_id> --json
```

Protocol audit:

```powershell
python -m agent_bus protocol events --type adapter.deprecated_path_used --limit 20 --json
```

Expected safety behavior:

- Worker completion without a valid fence is `AUDIT_ONLY`, not a task-state commit.
- Controller/user writes fail closed when the principal cannot be resolved.
- Legacy route and CLI adapter usage records `adapter.deprecated_path_used`.
- Stable rejects include `authority_reject` or `protocol_reject` plus `projection_effect` where applicable.

## Operations Projection Checks

Use `/api/projections/operations` to confirm the UI is fed by real backend-shaped data:

```powershell
$Projection = Invoke-RestMethod "$Base/api/projections/operations"
$Projection.ui.task_workflow.nodes | Select-Object id,kind,task_id,state
$Projection.ui.metro.nodes | Select-Object id,kind,task_id,state
$Projection.ui.diagnostics.protocol_violations | Select-Object -First 5
```

The accepted v2 projection contract is:

- `ui.task_workflow` is task-scoped and may include context, gate, replacement, claim, artifact, task, start, and terminal nodes.
- `ui.metro` is legacy compatibility for old run/task/gate/artifact consumers.
- Cross-task edges should be zero or surfaced as diagnostics, never silently connected.
- Communication and Diagnostics pages consume real message and protocol metadata, not demo/mock rows.

The console currently uses in-page tab navigation for Communication and Diagnostics. A direct browser load of `/communication` or `/diagnostics` may return 404 unless a server-side SPA fallback is added; use `http://127.0.0.1:8787/` and the app tabs for operator QA.

## Post-Acceptance Publishing

After final acceptance passes, follow the user instruction to push the accepted work to GitHub. Publication scope must still be assigned by QA/controller before an agent commits, pushes, or opens a PR. After publication, keep broker/fallback listening active while external review decides follow-up changes and the next construction plan.
