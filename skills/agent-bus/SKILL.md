---
name: agent-bus
description: Use when a Codex worker must coordinate through the local Agent Bus runtime control plane, wait for tasks, ack inbox items, fetch context packets, report status, handle recovery, or use fallback coordination files.
---

# Agent Bus

Agent Bus is the local runtime control plane for permanent Codex subagents. Use it before acting on distributed implementation work, wave gates, worker handoffs, QA findings, user feedback, or recovery tasks.

## Non-Negotiable Contract

- Stay online as a permanent listener.
- Completing a task means return to standby and wait again.
- Do not invent or follow a shutdown protocol.
- Treat context packets as authoritative context.
- Use raw event replay only for diagnostics, audits, or projection rebuilds.
- Keep ownership boundaries. Do not edit another worker's files unless QA, controller, or user explicitly reassigns scope.
- If blocked, ask `runtime-helper-1` and `runtime-helper-2`, write a `BLOCKER` fallback record, and keep listening.
- If any budget-limited blocker recurs, report it directly to the user as instructed.

## Final Runtime Commands

These commands are the final runtime surface. Confirm local availability with `python -m agent_bus --help`; if an older checkout is missing a command, use the fallback broker commands below and keep listening.

PowerShell startup:

```powershell
Set-Location 'C:\Users\laptopofzy\Documents\Agent bus'
$env:AGENT_BUS_DB = (Join-Path (Get-Location) '.local\agent-bus.sqlite3')

python -m agent_bus init --reset --json
python -m agent_bus seed --json
python -m agent_bus serve --host 127.0.0.1 --port 8765
```

Register and enter the worker loop:

```powershell
python -m agent_bus agent register runtime-worker-4 --role docs --json
python -m agent_bus wait --agent runtime-worker-4 --timeout 300 --json
```

If QA publishes a live-service DB, pass it explicitly on every final runtime command:

```powershell
$LiveDb = 'C:\Users\laptopofzy\Documents\Agent bus\coordination\live-agent-bus.sqlite3'
python -m agent_bus agent register runtime-worker-4 --role docs --state STANDBY_READY --db $LiveDb --json
python -m agent_bus wait --agent runtime-worker-4 --timeout 300 --db $LiveDb --json
```

Handle a delivered item:

```powershell
python -m agent_bus context get <context_packet_id> --json
python -m agent_bus ack <inbox_id> --agent runtime-worker-4 --json
python -m agent_bus task ack <task_id> --actor runtime-worker-4 --json
python -m agent_bus task progress <task_id> --actor runtime-worker-4 --json
python -m agent_bus task complete <task_id> --actor runtime-worker-4 --json
python -m agent_bus wait --agent runtime-worker-4 --timeout 300 --json
```

If a live `task_assigned` inbox item has no `context_packet_id`, proceed only if the task title and payload are self-contained. Otherwise ask the controller/helper for context, report the gap, and keep listening.

Gate and review operations:

```powershell
python -m agent_bus review request --task-id <task_id> --reviewer qa --worker runtime-worker-4 --json
python -m agent_bus review submit --task-id <task_id> --worker runtime-worker-4 --reviewer qa --severity high --category correctness --file-path src/file.py --evidence 'observed failure' --requested-change 'fix the failure' --blocking --json
python -m agent_bus gate approve <gate_id> --actor qa --json
python -m agent_bus gate reject <gate_id> --actor qa --reason 'tests failed' --json
```

Interrupt and replacement operations:

```powershell
python -m agent_bus interrupt create --run-id <run_id> --task-id <task_id> --actor user --text 'user changed scope' --json
python -m agent_bus replacement approve --old-session-id <old_session_id> --task-id <task_id> --approved-by controller --candidate-agent <agent_id> --json
```

## Fallback Coordination

Use the bootstrap broker and NDJSON files when the final server or CLI surface is unavailable:

```powershell
$AgentBus = 'C:\Users\laptopofzy\plugins\codex-agent-bus\scripts\agent_bus.py'
$BusFile = 'C:\Users\laptopofzy\Documents\Agent bus\coordination\agent-bus.ndjson'
$Broker = 'http://127.0.0.1:8765'

python $AgentBus status runtime-worker-4 --bus $BusFile --broker $Broker --state waiting --note 'standing by'
python $AgentBus send runtime-worker-4 --bus $BusFile --broker $Broker 'status text'
python $AgentBus tail runtime-worker-4 --bus $BusFile --broker $Broker --once --history 80 --all
```

Fallback blocker record shape for `coordination/messages.ndjson`:

```json
{"ts":"2026-05-28T00:00:00Z","from":"runtime-worker-4","to":"runtime-helper-1,runtime-helper-2","type":"BLOCKER","text":"blocked reason","files":["owned/file.py"]}
```

## Worker Discipline

1. Read the context packet for the delivered inbox item.
2. Confirm file ownership before editing.
3. Announce ownership and working status.
4. Implement only the assigned scope.
5. Run focused tests, then relevant integration tests.
6. Send the exact ready token requested by the gate, including files changed, commands run, and risks.
7. Set status to standby or waiting and continue the `wait` loop.
