# Subagent Contracts

This document is the operating contract for Codex workers, helpers, QA, and controller agents using Agent Bus.

## All Agents

- Agent Bus is the runtime control plane.
- Stay online and keep listening.
- There is no shutdown command or shutdown phase.
- Treat context packets as authoritative.
- Do not use raw event replay as normal working context.
- Respect wave gates.
- Respect file ownership.
- Report exact files changed, commands run, and unresolved risks.
- Return to standby after each task.

## Worker Contract

1. Register identity and session.
2. Wait for inbox item.
3. Fetch context packet.
4. Ack the delivered inbox item.
5. Announce ownership before edits.
6. Implement only owned scope.
7. Verify with focused and relevant integration checks.
8. Send exact ready token.
9. Set status to waiting or standby.
10. Wait again.

PowerShell loop:

```powershell
python -m agent_bus agent register runtime-worker-4 --role docs --json
python -m agent_bus wait --agent runtime-worker-4 --timeout 300 --json
python -m agent_bus context get <context_packet_id> --json
python -m agent_bus ack <inbox_id> --agent runtime-worker-4 --json
python -m agent_bus task complete <task_id> --actor runtime-worker-4 --json
python -m agent_bus wait --agent runtime-worker-4 --timeout 300 --json
```

## Helper Contract

Helpers diagnose, unblock, and coordinate. They do not take product ownership unless QA, controller, or user assigns a rescue.

Helper duties:

- Monitor bus and `USER_FEEDBACK.md`.
- Forward user feedback in clean text when mojibake appears.
- Acknowledge blockers.
- Provide read-only diagnosis first.
- Coordinate handoff or rescue only when authorized.

When the user assigns a helper to act as controller for a live real-service test, that helper should create the run, assign tasks with clear titles, create gates where useful, record user feedback, and keep the fallback bus updated. Workers should wait for their concrete task assignment instead of taking over controller duties.

## QA Contract

QA owns gates and independent verification.

QA duties:

- Require exact ready tokens.
- Run focused and integration tests.
- Inspect for fake, shallow, placeholder, hardcoded, patchy, or mojibake-prone implementation.
- Broadcast explicit `GATE_*_PASS` or `GATE_*_FAIL`.
- Never infer readiness from files alone.

## Controller Contract

The controller approves ordinary replacement and high-risk reassignment. User approval is required for user-directed overrides and high-risk cases where policy requires it.

Controller duties:

- Create and assign tasks.
- Approve replacement recommendations.
- Resolve high-risk gate action items.
- Preserve task IDs through replacement.
- Ensure replacement agents receive rehydration packets.

Live test task assignments may arrive as `task_assigned` inbox items without context packets. Controllers should attach context packets for complex work. For simple audit tasks, the task title and payload may be enough, but the worker should record that the missing packet is a workflow gap.

## Blocker Contract

When blocked:

```powershell
$AgentBus = 'C:\Users\laptopofzy\plugins\codex-agent-bus\scripts\agent_bus.py'
$BusFile = 'C:\Users\laptopofzy\Documents\Agent bus\coordination\agent-bus.ndjson'
$Broker = 'http://127.0.0.1:8765'

python $AgentBus send runtime-worker-4 --bus $BusFile --broker $Broker --to runtime-helper-1 'BLOCKER_HELP ...'
python $AgentBus send runtime-worker-4 --bus $BusFile --broker $Broker --to runtime-helper-2 'BLOCKER_HELP ...'
```

Also append fallback:

```json
{"ts":"2026-05-28T00:00:00Z","from":"runtime-worker-4","to":"runtime-helper-1,runtime-helper-2","type":"BLOCKER","text":"blocked reason","files":["owned/file"]}
```

Do not silently stop.
