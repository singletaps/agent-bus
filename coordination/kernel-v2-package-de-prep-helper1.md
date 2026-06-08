# Kernel v2 Package D/E Prep - runtime-helper-1

Agent: `runtime-helper-1`
Assignment: `KERNEL_PACKAGE_DE_PREP_ASSIGN`
Scope: read-only analysis artifact only.
Owned file: `coordination/kernel-v2-package-de-prep-helper1.md`

## Inputs

- Plan: `docs/superpowers/plans/2026-06-01-agent-bus-protocol-kernel-v2.md`
- Package D target: API and CLI role split.
- Package E target: protocol projections and frontend task-workflow convergence.
- Current roster update: `runtime-worker-4` is excluded from active implementation until recovery; active implementation pool is `runtime-worker-1`, `runtime-helper-1`, `runtime-helper-2`, and `runtime-qa`.

## Current API Map

Current `agent_bus/server.py` exposes mixed authority routes:

- Read/projection: `GET /api/agents`, `/api/sessions`, `/api/runs`, `/api/tasks`, `/api/projections/messages`, `/api/projections/operations`, `/api/artifacts/manifests`, `/api/artifacts/files/{path}`.
- Compatibility writes: `POST /api/messages/send`, `/api/inbox/wait`, `/api/inbox/ack`, `/api/interrupt`, `/api/replacement/approve`.
- These routes call old domain services directly: `create_user_interrupt`, `InboxStore`, `ReplacementCoordinator`, `EventStore`, `ContextStore`, `ProjectionReader`.

Package D implication:

- New `/api/worker/*`, `/api/controller/*`, `/api/user/*`, and `/api/projections/*` groups should be added beside the compatibility routes first.
- Compatibility routes should become thin adapters that resolve a `Principal`, call `ProtocolKernel`, and emit deprecation/audit events.
- Stable error bodies should be centralized so FastAPI handlers return `error`, `message`, `projection_effect`, and optional `violation_id` consistently.
- Fencing/session fields cannot be bolted on per route; route models should share request helpers once Package A provides protocol/fencing models.

## Current CLI Map

Current `agent_bus/cli.py` exposes old top-level commands:

- Worker-like commands: `wait`, `ack`, `task ack`, `task progress`, `task complete`, `task fail`, `artifact create`.
- Controller/user-like commands: `task create`, `gate create/approve/reject/escalate`, `interrupt create`, `replacement approve`, review commands.
- Old authoritative bypasses remain visible: `_handle_task_complete` calls `TaskBoard.complete_task`, gate commands call `GateBoard`, and replacement approval calls `ReplacementCoordinator.approve`.

Package D implication:

- Add command groups `worker`, `controller`, `user`, and `protocol` before removing deprecated aliases.
- Deprecated `task complete --actor worker.*` must become audit-only completion claim creation when fencing is missing.
- Explicit controller compatibility should require `--as-controller` or a controller principal path; free-form `--actor controller` should not grant authority.
- CLI output should use the same JSON error shape as the API for rejects and audit-only adapter paths.

## Current Projection Map

Current `agent_bus/projections.py` builds one run-shaped UI metro:

- `UiOperationsProjection.metro` is a single `UiMetroProjection`.
- `_build_metro_projection` starts from the active run, chains all run tasks in one main path, then attaches gates and artifacts under each task.
- Unlinked artifacts are attached to the run start node.
- `OperationsProjection` has no `task_workflows` map, no protocol diagnostics object, and no explicit projection-effect or protocol-violation collections.

Package E implication:

- Replace the single global metro with `task_workflows: dict[task_id, UiTaskWorkflowProjection]`.
- Add a selected/default task workflow contract for frontend compatibility while `HomePage` is migrated.
- Cross-task edges should be rejected or dropped in the projection builder and should record a protocol violation once Package A exposes violation/effect writes.
- Taskless/global events should route to run timeline, communication, or diagnostics, not task workflow nodes, unless a durable binding attaches them to a task.

## Current Frontend Map

Current frontend coupling:

- `frontend/src/operationsApi.ts` defines `UiMetroProjection`, `UiMetroNode`, `UiMetroEdge`, and normalizes `projection.ui.metro`.
- `frontend/src/pages/HomePage.tsx` reads `projection.ui.metro` directly, renders `MetroGraph`, and shows small action workflow strips by searching the same global metro.
- `frontend/src/components/MetroGraph.tsx` renders any passed metro shape and does not enforce task id boundaries.
- `frontend/src/pages/CommunicationPage.tsx` implements client-side filters over the current `messages` array; filters are not yet backed by projection metadata/viewer semantics.
- `frontend/src/pages/DiagnosticsPage.tsx` filters generic event rows and heuristic protocol warnings; it does not yet display structured `projection_effects`, fencing rejects, protocol violations, or deprecated adapter usage.

Package E implication:

- Introduce `UiTaskWorkflowProjection` and normalize legacy `ui.metro` only at the API boundary.
- `HomePage` should select a workflow by action item `taskId`; if no action is selected, use the highest-priority workflow supplied by the backend.
- `ActionWorkflowStrip` should use the selected task workflow rather than scanning a global metro.
- `MetroGraph` can remain reusable but should receive task-scoped nodes/edges only; optional dev/runtime assertions can guard against cross-task edges.
- Communication filters need server-provided `viewer` and visibility metadata to prove filtering is not only local string matching.
- Diagnostics needs structured protocol sections for `projection_effects`, `fencing_result`, `protocol_violations`, and adapter deprecation events.

## Package D Dependencies

Package D should wait for these Package A/B/C handoffs before full implementation:

- Package A: `ProtocolKernel`, `UnitOfWork`, protocol enums, principal/authority/fencing services, protocol violation model, and stable migration runner.
- Package B: task claim and context binding service contracts for worker task ack/progress/completion/failure routes.
- Package C: gate/review/replacement service contracts for controller/user gate decisions and replacement approvals.

Early Package D work that can be prepared without mutation:

- Define route grouping plan and request/response model inventory.
- Add tests as pending/skipped only if QA allows; otherwise wait for Package A/B/C contracts.
- Inventory all compatibility aliases that must emit audit/deprecation events.

## Package E Dependencies

Package E should wait for these handoffs:

- Package A: protocol event envelope fields, `projection_effect`, `fencing_result`, and protocol violation records.
- Package B: task claim/context binding semantics.
- Package C: gate and replacement phases.
- Package D: final `/api/projections/*` response shape, especially task workflow and protocol diagnostics endpoints.

Early Package E work that can be prepared without mutation:

- Draft backend projection shape for `task_workflows`.
- Draft frontend normalization migration: keep legacy `ui.metro` fallback until backend delivers `task_workflows`.
- Define browser QA checks around selecting different task workflows and preventing global metro stitching.

## Browser QA Hooks

Recommended checks for Package E and final gate:

- API shape: `GET /api/projections/operations` includes `task_workflows`, `selectedTaskWorkflow`, `protocol`, and no frontend-invented demo workflow data.
- Graph invariant: every edge source/target resolves to nodes with the same `task_id`, except explicitly task-bound global events.
- Home behavior: selecting an action item changes the rendered `MetroGraph` to that item's task workflow.
- Home invariant: action queue stays a queue; it must not create workflow edges.
- Communication behavior: each scope filter changes visible messages based on backend visibility metadata.
- Diagnostics behavior: a rejected fencing write appears with `projection_effect=REJECT`, concrete `fencing_result`, and a protocol violation id.
- Legacy adapter behavior: using a deprecated compatibility route creates an audit/deprecation entry visible in Diagnostics.
- Visual basics: no mojibake in graph node labels, no body overflow, no button overflow, and node labels fit.

## Risks

- Package D and E both depend on shared protocol models; they should not edit Package A-owned files without a broker handoff.
- Existing tests such as `tests/test_server.py` assert `projection["ui"]["metro"]`; Package E will need compatibility assertions during migration, then v2 assertions for task workflows.
- Existing Home UX is tightly coupled to one global `projection.ui.metro`; changing backend shape without a temporary compatibility normalizer will break the frontend.
- Existing CLI authoritative handlers are direct bypass points. Package D should add failing tests before changing behavior so old direct completion/gate/replacement paths cannot silently remain authoritative.
- `runtime-worker-4` is unavailable per user feedback, so Package E implementation should not be assigned to worker4 until QA confirms recovery.

## Suggested Assignment Sequencing

1. `runtime-worker-1`: Package A Kernel foundation.
2. `runtime-helper-2`: Package B/C prep or implementation after Package A handoff.
3. `runtime-helper-1`: Package D API/CLI after Package A and enough B/C contracts land; or Package E projection/frontend if QA prefers helper1 to cover worker4's unavailable area.
4. `runtime-qa`: Package F docs/simulation and serial gates.

## Verification For This Prep Artifact

- No product code was edited.
- This artifact intentionally records dependencies and risks only.
