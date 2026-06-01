# Live Test Bugfix Round 2

Controller: `runtime-helper-1`

Ordering directive: fix bugs found in real-service Round 1 before any frontend redesign or Chinese UI implementation.

Live service: http://127.0.0.1:8787/

Live DB: `coordination/live-agent-bus.sqlite3`

Fallback bus: `coordination/agent-bus.ndjson`

## Objective

Close the defects surfaced during live real-service testing, then ask QA to verify the fixes against the real service before the frontend redesign wave starts.

## Run And Gate

- Run: `run_baa1ce49d36e43b1ae6b22737fb91fcd`
- Gate: `gate_cdfd1244f34b4592a982fc0e5a9c23b6`
- Gate owner: `runtime-helper-1`
- Gate pass condition: BUG-1, BUG-2, and BUG-3 are fixed or explicitly escalated with QA-approved evidence, and no frontend redesign implementation has started before this gate.

## Hard Gate

Frontend redesign implementation is blocked until this bugfix gate passes.

Allowed before the gate passes:

- Bugfix code and tests for Round 1 defects.
- Documentation updates that explain the fixed behavior.
- A written frontend redesign implementation plan, if needed, without frontend code changes.

Not allowed before the gate passes:

- Beautification refactors.
- Chinese UI text migration.
- Visual redesign component rewrites.

## Known Bugs From Round 1

### BUG-1: Closed QA Session Still Appears Active

User-visible symptom:

- User closed `runtime-qa`, but the Operations Console continued to show QA as `STANDBY_READY`.

Evidence recorded in Round 1:

- Worker 1 found no explicit heartbeat, session close, or session end path.
- Projection currently renders the last persisted active `AgentHealth`.

Root-cause hypothesis to verify:

- Agent identities are durable, but active session freshness is not modeled beyond `last_seen_at`.
- Closed agents stop producing signals, yet the projection does not derive stale or inactive state from missing heartbeats.

Acceptance criteria:

- A session that stops heartbeating no longer appears as healthy active `STANDBY_READY` after the configured freshness window.
- The API projection exposes enough state for UI to distinguish healthy, stale, degraded, and replaced sessions.
- Tests cover: fresh active session, stale session after missed heartbeat, explicit state update, and projection output.
- Real-service verification includes temporarily stopping or simulating a stopped `runtime-qa` session and confirming the UI/API no longer reports it as healthy ready.

### BUG-2: Command Composer Routes To Both Selected Task Owner And Target Agent

User-visible symptom:

- Worker 3 sent an interrupt with target `runtime-worker-3`, but the default selected task belonged to `runtime-worker-1`, causing affected agents to include both workers.

Evidence recorded in Round 1:

- `frontend/src/App.tsx` sends `task_id: selectedTask?.id`, `task_owner: selectedTask?.owner`, and `additional_agents: [targetAgent]` even when the target agent differs from the selected task owner.

Root-cause hypothesis to verify:

- The composer silently combines two targeting modes: selected task context and explicit target agent.
- The UI does not show or require confirmation for the mixed-target case.

Acceptance criteria:

- The composer makes the selected task explicit before sending.
- If a target agent differs from selected task owner or assignee, the UI either requires confirmation or sends an agent-only interrupt without unrelated task owner routing.
- Tests cover same-owner routing, target-agent-only routing, and mismatched target/task owner behavior.
- Real-service verification confirms a target `runtime-worker-3` interrupt does not wake `runtime-worker-1` unless the user explicitly chooses a task that requires both.

### BUG-3: Nested PowerShell `--metadata-json` Is Too Easy To Misuse

User-visible symptom:

- Worker 2 observed that malformed nested PowerShell metadata JSON returns a structured error, but the correct quoting path is not obvious.

Evidence recorded in Round 1:

- CLI error behavior is structured, but docs and examples need a safe PowerShell pattern.

Acceptance criteria:

- Docs include a known-good PowerShell example for `--metadata-json`.
- Tests or smoke commands verify the documented example succeeds.
- The CLI keeps returning structured errors for malformed metadata JSON.

## Worker Assignments

### Worker 1: Agent Lifecycle Freshness Fix

- Task: `task_550bf5a93cec478b859a9315497798dc`

Scope:

- Backend agent/session model, CLI/API status paths, projection freshness.

Files likely involved:

- `agent_bus/agents.py`
- `agent_bus/models.py`
- `agent_bus/projections.py`
- `agent_bus/cli.py`
- `agent_bus/server.py`
- `tests/test_agents.py`
- `tests/test_server.py`
- `tests/test_cli_wave_c.py`

Expected deliverable:

- Root-cause note.
- Tests first.
- Minimal backend/API/CLI fix for BUG-1.
- Verification command output summary.

### Worker 2: CLI Metadata And Runtime Contract Fix

- Task: `task_10c3c1835b964f348fad88decda104ac`

Scope:

- CLI contract around metadata JSON and any status/heartbeat command added by Worker 1.
- Ensure commands remain scriptable from PowerShell.

Files likely involved:

- `agent_bus/cli.py`
- `tests/test_cli_wave_c.py`
- `README.md`
- `docs/protocol.md`
- `docs/recovery-playbook.md`

Expected deliverable:

- Known-good command examples.
- Tests for structured metadata errors and successful metadata create path.
- Review of new lifecycle CLI command, if Worker 1 adds one.

### Worker 3: Command Composer Targeting Fix

- Task: `task_48fb94c022c64afbbbfeda0473752c89`
- Current assignee: `runtime-helper-2`
- Original assignee: `runtime-worker-3`
- Reassignment reason: user reported Worker3 context compression failed and lost contact.

Scope:

- Operations Console interrupt composer behavior.

Files likely involved:

- `frontend/src/App.tsx`
- `frontend/src/operationsApi.ts`
- `frontend/src/styles.css`
- `tests/test_server.py` if API expectations need tightening.

Expected deliverable:

- Reproduction note for the mixed-target bug.
- Frontend change that makes target/task routing explicit and prevents accidental dual wakeups.
- `npm run build` result.
- Browser smoke result against the live service.

### Worker 4: Docs And Regression Checklist

- Task: `task_f5d9855fb490482ba7ea0ff3f72f6b48`

Scope:

- User-facing docs, protocol docs, QA checklist, and Round2 evidence.

Files likely involved:

- `README.md`
- `docs/protocol.md`
- `docs/recovery-playbook.md`
- `coordination/live-test-bugfix-round-2.md`

Expected deliverable:

- Docs updates after Workers 1-3 land.
- A concise regression checklist for QA.
- Confirmation that docs do not claim stale sessions are healthy ready.

### QA: Bugfix Gate Verification

Active QA identity for this round: `runtime-helper-2`.

Task: `task_5821dfcbe78643798d0b5c1b05a55773`

Reason:

- User confirmed `runtime-qa` has been closed.
- `runtime-helper-2` is now responsible for QA duties for this bugfix round.

Scope:

- Review all fixes after worker completion.
- Run backend tests, frontend build, and real-service browser/API checks.

Required checks:

- `python -m pytest -q`
- `cd frontend; npm run build`
- Live API check: `GET /api/agents`, `GET /api/sessions`, `GET /api/events/stream`
- Browser check at http://127.0.0.1:8787/
- Confirm BUG-1, BUG-2, and BUG-3 are closed or clearly escalated.

Conflict handling:

- Because `runtime-helper-2` also owns the reassigned BUG-2 implementation task, BUG-2 must receive an independent cross-check from `runtime-helper-1` or `runtime-worker-4` before the gate is approved.

## Worker 4 QA Regression Checklist

Status: owner evidence recorded for BUG-1, BUG-2, and BUG-3. Worker 4 has independently cross-checked BUG-2 because `runtime-helper-2` owns both the replacement implementation and final QA role; final gate approval still belongs to helper2/controller review.

### Pre-Verification Guardrails

- [x] Confirm the Round2 gate `gate_cdfd1244f34b4592a982fc0e5a9c23b6` is still open before frontend redesign work starts.
- [x] Confirm no Chinese UI migration, visual beautification, or frontend redesign component rewrite was merged before the bugfix gate.
- [x] Confirm `runtime-helper-2` is the active QA verifier because the user closed `runtime-qa`.
- [x] Confirm Worker 1, Worker 2, and `runtime-helper-2` as Worker 3 replacement have either completed their tasks or explicitly escalated with evidence.

### BUG-1 Closed Or Stale Session Projection

- [x] Backend/API tests cover fresh active sessions, stale sessions after missed heartbeat or freshness expiry, explicit state update, and projection output.
- [x] Live API check shows a stopped or simulated stopped QA session does not remain healthy active `STANDBY_READY` after the configured freshness window.
- [x] UI/API exposes enough state to distinguish healthy, stale/degraded, ended, and replaced sessions.
- [x] Docs do not describe a closed or stale session as healthy ready; any caveat states that old behavior was a bug or legacy limitation.

Evidence to record after verification:

```text
BUG-1 owner evidence: runtime-worker-1 completed task_550bf5a93cec478b859a9315497798dc with artifact artifact_8c41655d61fb43b6913e1ccfc971bdaa. Root cause: operations projection trusted persisted STANDBY_READY health and ignored last_seen_at freshness. Fix: ProjectionReader derives stale READY sessions as STANDBY_DEGRADED, stale WORKING sessions as SUSPECTED_STUCK, AgentDirectory.heartbeat_session added, POST /api/agents/{agent_id}/heartbeat emits agent.status_changed. Evidence: python -m pytest -q => 58 passed; live DB check projects closed runtime-qa as STANDBY_DEGRADED stale=true with missing heartbeat reason.
BUG-1 helper2 QA evidence: after restarting the live service on port 8787 to PID 11728, GET /api/agents showed runtime-qa as STANDBY_DEGRADED with stale=true and missing heartbeat reason, not healthy STANDBY_READY. Browser reload at http://127.0.0.1:8787/ also showed runtime-qa as STANDBY_DEGRADED with zero console errors. POST /api/agents/runtime-worker-1/heartbeat returned 200, refreshed last_seen_at, and emitted agent.status_changed visible through /api/events/stream.
BUG-1 remaining risk: explicit session end/close semantics are still not modeled; the Round2 fix correctly prevents stale closed agents from remaining healthy-ready in projections.
```

### BUG-2 Command Composer Routing

- [x] Same-owner or same-assignee task routing still sends the intended task context.
- [x] Agent-only routing sends the selected target agent without waking an unrelated selected-task owner.
- [x] Mismatched target/task owner behavior is explicit: the UI clears task context, requires confirmation, or otherwise prevents accidental dual wakeups.
- [x] Real-service browser/API check confirms a replacement target-agent interrupt does not wake `runtime-worker-1` unless the user explicitly chooses a task that requires both.

Evidence to record after verification:

```text
BUG-2 owner evidence: runtime-helper-2 completed task_48fb94c022c64afbbbfeda0473752c89 with artifact artifact_cafcfb79284e448fa8406f3fcb4c4e62. Files changed: frontend/src/App.tsx, frontend/src/styles.css. Evidence reported: npm run build passed; live browser smoke at http://127.0.0.1:8787/ showed Include task context unchecked and AGENT ONLY when target runtime-helper-2 differed from selected task owner runtime-worker-1; live event seq107 had task_id null, routing_mode agent-only, include_selected_task false, affected_agents [controller, observer, runtime-helper-2, qa], and no runtime-worker-1.
BUG-2 Worker4 independent cross-check evidence: runtime-worker-4 verified the live Command Composer in the browser on 2026-05-28. With selected task task_7ae9e0ac561b49c885f49d04d8016dd2 owned by runtime-worker-1 and explicit target runtime-helper-2, the composer showed Include task context unchecked and agent only. Screenshot evidence: coordination/bug2-worker4-browser-crosscheck.png. Live DB event_log seq107 confirmed task_id null, routing_mode agent-only, include_selected_task false, selected_task_id task_7ae9e0ac561b49c885f49d04d8016dd2, affected_agents [controller, observer, runtime-helper-2, qa]. inbox_items text search for the seq107 smoke found 12 records only for controller, observer, runtime-helper-2, and qa; runtime-worker-1 had zero matching inbox items.
BUG-2 helper2 QA evidence: npm run build passed. Browser smoke verified the mismatch path: selected task owner runtime-worker-1 plus explicit target runtime-helper-2 automatically unchecked Include task context and showed AGENT ONLY; sending the smoke interrupt produced live event seq107 with task_id null, routing_mode agent-only, include_selected_task false, affected_agents [controller, observer, runtime-helper-2, qa], and no runtime-worker-1. After service restart, browser reload still showed Command Composer and Include task context with zero console errors. Same-owner/default task-context routing remains visible as checked task context before selecting a mismatched target.
BUG-2 remaining risk: helper2 implemented BUG-2 and QA'd the round, so independent Worker4/browser/DB evidence is required and present; no remaining blocking risk found.
```

### BUG-3 PowerShell Metadata JSON Contract

- [x] Docs include a known-good PowerShell `--metadata-json` example that succeeds from the repository root.
- [x] Smoke command creates an artifact or equivalent metadata-bearing object with parsed JSON metadata.
- [x] Malformed metadata JSON still returns structured JSON error output and a nonzero exit.
- [x] Examples avoid fragile nested quote patterns where a hashtable-to-JSON variable is safer.

Evidence to record after verification:

```text
BUG-3 owner evidence: runtime-worker-2 completed task_10c3c1835b964f348fad88decda104ac with artifact artifact_6de5d84f346f4f219c015d663e1e8bea. Files changed: agent_bus/cli.py, tests/test_cli_wave_c.py, README.md, docs/protocol.md, docs/recovery-playbook.md. Evidence: focused CLI tests 6 passed, full python -m pytest -q 55 passed, py_compile passed, PowerShell @file artifact --metadata-json smoke passed, malformed metadata JSON still returns structured --json stderr with exit 2.
BUG-3 helper2 QA evidence: python -m agent_bus artifact create with --metadata-json @coordination/bug2-helper2-artifact.json succeeded against a temp DB and returned ok true with parsed metadata. Malformed --metadata-json '{bad' returned structured JSON error and PowerShell LASTEXITCODE=2 when captured immediately after the command. Full python -m pytest -q passed with 58 tests.
BUG-3 Worker4 verification evidence: runtime-worker-4 reran the documented PowerShell-safe @path metadata flow on 2026-05-28 against a temp DB. The valid command returned ok true and parsed metadata {round: round2, owner: runtime-worker-4, ok: true}; the malformed inline JSON command exited 2 with structured JSON error message "--metadata-json must be valid JSON: Expecting property name enclosed in double quotes".
BUG-3 remaining risk: none blocking.
```

### Worker 4 Verification Snapshot

Commands run by `runtime-worker-4` on 2026-05-28 before completing task_f5d9855fb490482ba7ea0ff3f72f6b48:

- `python -m pytest -q` => 58 passed.
- `npm run build` from `frontend/` => vite build succeeded.
- Browser check at http://127.0.0.1:8787/ => BUG-2 mismatched target/task-owner state showed Include task context unchecked and agent only.
- Live DB check against `coordination/live-agent-bus.sqlite3` => event_log seq107 was agent-only with no runtime-worker-1 inbox matches.
- PowerShell metadata smoke => valid `--metadata-json @$MetaPath` artifact create succeeded; malformed inline JSON exited 2 with structured JSON error.

### Final Gate Evidence

Required before helper2 recommends gate approval:

- [x] `python -m pytest -q`
- [x] `Set-Location frontend; npm run build`
- [x] `GET /api/agents` reviewed for stale/closed session state.
- [x] `GET /api/sessions` reviewed for active, stale/degraded, ended, or replaced session fields.
- [x] `GET /api/events/stream` opens and emits events or snapshots without console/server errors.
- [x] Browser check at http://127.0.0.1:8787/ confirms BUG-1 and BUG-2 behavior with real service data.
- [x] README/protocol/recovery docs match the implemented behavior and do not preserve obsolete warnings as current truth.

Suggested PowerShell command block for helper2:

```powershell
Set-Location 'C:\Users\laptopofzy\Documents\Agent bus'
$Base = 'http://127.0.0.1:8787'
$LiveDb = 'C:\Users\laptopofzy\Documents\Agent bus\coordination\live-agent-bus.sqlite3'

python -m pytest -q

Push-Location frontend
npm run build
Pop-Location

Invoke-RestMethod "$Base/api/agents" | ConvertTo-Json -Depth 8
Invoke-RestMethod "$Base/api/sessions" | ConvertTo-Json -Depth 8
curl.exe -N --max-time 5 "$Base/api/events/stream"
```

Suggested PowerShell metadata smoke for BUG-3:

```powershell
Set-Location 'C:\Users\laptopofzy\Documents\Agent bus'
$TmpDb = Join-Path $env:TEMP 'agent-bus-metadata-smoke.sqlite3'
$MetaPath = Join-Path $env:TEMP 'agent-bus-meta-smoke.json'

Remove-Item -LiteralPath $TmpDb -ErrorAction SilentlyContinue
Remove-Item -LiteralPath $MetaPath -ErrorAction SilentlyContinue
python -m agent_bus init --reset --db $TmpDb --json

@{ round = 'round2'; owner = 'helper2'; ok = $true } | ConvertTo-Json -Compress | Set-Content -LiteralPath $MetaPath -Encoding UTF8
$MetaArg = '@' + $MetaPath
python -m agent_bus artifact create qa-check agent-bus://smoke/metadata-json --created-by runtime-helper-2 --metadata-json $MetaArg --db $TmpDb --json
python -m agent_bus artifact create qa-check agent-bus://smoke/bad-json --created-by runtime-helper-2 --metadata-json '{bad' --db $TmpDb --json
```

Expected BUG-3 results:

- The `@path` metadata command returns `ok: true` and parsed metadata fields.
- The malformed `'{bad'` command returns nonzero with structured JSON error output.

Final helper2 QA result:

```text
Gate recommendation: PASS from helper2 QA. Controller should close gate only after accepting Worker4's docs/checklist artifact and task state.
Commands run: python -m pytest -q => 58 passed; frontend npm run build => vite build succeeded; BUG-3 @path metadata smoke succeeded; malformed metadata JSON returned structured error with LASTEXITCODE=2.
Live-service checks: service restarted on port 8787 as PID 11728; GET /api/agents showed runtime-qa STANDBY_DEGRADED stale=true and runtime-worker-1 STANDBY_READY stale=false after heartbeat; POST /api/agents/runtime-worker-1/heartbeat returned 200 and emitted agent.status_changed; /api/events/stream emitted an operations snapshot; browser reload showed runtime-qa STANDBY_DEGRADED and no console errors.
Docs reviewed: README.md, docs/protocol.md, docs/recovery-playbook.md, and this Round2 document describe stale sessions and metadata-json behavior consistently.
Open risks: explicit session end/close semantics remain future work; current bugfix prevents stale sessions from appearing healthy-ready. BUG-2 was implemented by helper2, but Worker4 independent cross-check evidence is present.
```

## Controller Rules

- Any frontend redesign code remains blocked until the bugfix gate passes.
- If a worker needs cross-file ownership, it must announce write scope before editing.
- If Worker 1 and Worker 3 both need `frontend/src/App.tsx`, Worker 3 owns UI edits and Worker 1 must coordinate through Worker 3.
- QA may reject the gate if any fix is fake, shallow, placeholder-based, hardcoded to current test data, or only documented without behavior change where behavior change is required.
