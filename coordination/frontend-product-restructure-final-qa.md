# Frontend Product Restructure Final QA

Runtime QA: `runtime-qa`
Gate: `PRODUCT_RESTRUCTURE_GATE_C_PASS / GATE_WAVE_C_PASS`
Timestamp: `2026-05-29T13:01:10+08:00`

## Decision

Gate C passes.

## Independent Verification

Commands:

```powershell
pytest -q
npm --prefix frontend run build
python -m agent_bus --help
python -m agent_bus wait --agent controller --timeout 1 --json --db coordination\live-agent-bus.sqlite3
Invoke-WebRequest http://127.0.0.1:8787/api/projections/operations
Invoke-WebRequest http://127.0.0.1:8787/api/projections/messages
Invoke-WebRequest http://127.0.0.1:8787/api/artifacts/manifests
```

Results:

- `pytest -q` passed: `66 passed in 5.58s`.
- `npm --prefix frontend run build` passed: Vite built 1768 modules; lucide `"use client"` warnings only.
- Correct live API endpoints returned 200:
  - `/api/projections/operations` bytes `383966`
  - `/api/projections/messages` bytes `6786`
  - `/api/artifacts/manifests` bytes `116`
  - built asset `/assets/index-DFY2Gu7x.js` bytes `252414`
- `python -m agent_bus wait --agent controller --timeout 1 --json --db coordination\live-agent-bus.sqlite3` returned a delivered inbox item, confirming the wait runtime API path on the live SQLite DB.

## Source Scans

- C1 required App/Home submit-routing markers present:
  - `sendBusMessage`
  - `recipient_agent_ids: recipientAgentIds`
  - `resolveDrawerRecipients`
  - `viewAfterDrawerSubmit`
  - `setActiveView(nextView)`
- C1 forbidden old shell markers absent from App/Home:
  - `TopRuntimeBar`
  - `<TopRuntimeBar`
  - `topStatusBar`
  - `opsTopBar`
  - `RefreshCw`
- C4 required role/icon/style markers present:
  - `Command`, `Hammer`, `ScanEye`, `CircuitBoard`
  - `roleKeywords`
  - `agent-role-*`
  - `agentMarkIcon`
  - `pageShell`
- Legacy/prototype route scan found no old normal-route surfaces:
  - `LegacyAgentRoster`, `LegacyApprovalPanel`, `LegacyEventFeed`, `LegacyInterruptComposer`, `LegacyRunStages`, `LegacyArtifactCards`, `ReplacementDock`
  - old static stage list
  - `successRate`, `HomeDashboard`, `controllerSuggestion`, `Inspector`, `Command Console`, `trustText`, `AgentDock`, `CommandComposer`, `GateCenter`, `EventTimeline`, `RunGraph`, `ArtifactShelf`

## Browser Verification

Canonical service: `http://127.0.0.1:8787`

Browser click checks:

- Home rendered with 7 nav items and 6 action queue command buttons.
- First Home action queue button opened exactly one `.actionDrawer`.
- Drawer had 4 segment buttons and 1 textarea.
- Drawer submit called the Bus-backed path and closed the drawer.
- Communication page refresh worked.
- Communication composer selected a recipient and sent a Bus message through `/api/messages/send`.
- Runs page first run selector clicked.
- Gates page first gate selector clicked.
- Artifacts refresh clicked.
- Diagnostics all 6 segment buttons clicked.
- Settings page rendered.
- Browser log delta: `0` total new logs, `0` severe logs.

Bus message evidence from `/api/projections/messages`:

- Operator messages: `2`.
- Gate C ping messages: `1`.
- Drawer submit projected as delivered with body `è¯·å¤çä»»å¡ï¼Worker2 CLI child fail`, recipients `runtime-qa,unassigned`, type `message_controller`.
- Communication composer projected as delivered with body `Gate C browser QA ping 1780030746058`, recipient `runtime-helper-1`, type `instruction`.

Screenshots:

- `coordination/gate-c-final-home-initial-1280x720.png`
- `coordination/gate-c-final-actiondrawer-open-1280x720.png`
- `coordination/gate-c-final-actiondrawer-submitted-1280x720.png`
- `coordination/gate-c-final-communication-1280x720.png`
- `coordination/gate-c-final-communication-after-controls-1280x720.png`
- `coordination/gate-c-final-runs-1280x720.png`
- `coordination/gate-c-final-runs-after-controls-1280x720.png`
- `coordination/gate-c-final-gates-1280x720.png`
- `coordination/gate-c-final-gates-after-controls-1280x720.png`
- `coordination/gate-c-final-artifacts-1280x720.png`
- `coordination/gate-c-final-artifacts-after-controls-1280x720.png`
- `coordination/gate-c-final-diagnostics-1280x720.png`
- `coordination/gate-c-final-diagnostics-after-controls-1280x720.png`
- `coordination/gate-c-final-settings-1280x720.png`
- `coordination/gate-c-final-settings-after-controls-1280x720.png`

Screenshot nonblank check:

- All 15 screenshots were 1264/1280 x 720.
- File sizes ranged from `41957` to `142802` bytes.
- Sampled color counts ranged from `39` to `100`.

Worker4 supplied independent narrow evidence for C4:

- `coordination/product-restructure-c4-worker4-narrow.png`
- `coordination/product-restructure-c4-worker4-desktop.png`

Runtime-qa browser API in this environment did not expose viewport resizing, so runtime-qa independently verified desktop click-through and screenshot nonblank evidence, and accepts Worker4's narrow browser/CDP overflow evidence as supporting evidence for C4.

## Definition Of Done

- SQLite is the primary store. Verified package CLI and live server use `coordination\live-agent-bus.sqlite3`; README states SQLite is source of truth and NDJSON is fallback compatibility only.
- Event replay can rebuild projection. Verified `ProjectionReader`, `rebuild_event_state`, and `replay_state` are present and covered by passing tests.
- `wait` / `ack` / `context` are stable runtime APIs. Verified CLI help and live `wait`; source/tests cover `/api/inbox/wait`, `/api/inbox/ack`, and `/api/context`.
- Agent identity, session, and replacement are first-class models. Verified `AgentIdentity`, `AgentSession`, `AgentHealth`, `AgentCapability`, replacement APIs, and model diagnostics.
- Human interrupt has affected-agent propagation. Verified `InterruptRoutingTarget`, `create_user_interrupt`, `affected_agents`, `/api/interrupt`, and tests.
- Capability confidence and health degradation enter the backend projection. Verified capability confidence and stale health records in `/api/projections/operations`.
- React console uses real backend data. Verified live `/api/projections/operations`, `/api/projections/messages`, `/api/artifacts/manifests`, drawer submit, and communication composer.
- Documentation tells Codex subagents to wait through Bus. Verified `README.md` and `docs/subagent-contracts.md` worker loop: register, wait, fetch context, ack, complete, then wait again.

## Findings Summary

No blocking findings remain for Wave C or final end-to-end gate.

Non-blocking notes:

- Some live projection message bodies preserve mojibake from older events or source data; Gate C did not treat this as a blocker because current C scope was route/product restructure and the browser/API paths functioned correctly.
- The in-app browser runtime did not expose viewport resizing; final QA keeps Worker4's narrow screenshot/CDP evidence as supporting responsive evidence.
