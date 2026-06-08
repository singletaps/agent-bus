# Wave4 Compatibility Guard - runtime-helper-2

Timestamp: 2026-06-02T15:01:22+08:00
Owner: runtime-helper-2
Scope: read-only compatibility guard and fallback notes only. No product-code edits.

## Current Assignment Map

- runtime-worker-7 owns Package D API/CLI split: `agent_bus/server.py`, `agent_bus/cli.py`, `tests/test_worker_api.py`, `tests/test_controller_api.py`, `tests/test_cli_protocol_v2.py`, with adapter-regression compatibility allowed in existing `tests/test_server.py` and `tests/test_cli_wave_c.py`.
- Package D target: split `/api/worker/*`, `/api/controller/*`, `/api/user/*`, and `/api/projections/*`; keep old mixed routes and CLI aliases as compatibility adapters; emit deprecation audit events; preserve explicit controller compatibility mode; avoid free-form actor principals; keep stable JSON reject envelopes.
- runtime-worker-5 owns Package E projection/frontend normalization: `agent_bus/projections.py`, `tests/test_protocol_projection.py`, `frontend/src/operationsApi.ts`, `frontend/src/operationsRoomModel.ts`, `frontend/src/components/MetroGraph.tsx`, `frontend/src/pages/HomePage.tsx`, `frontend/src/pages/CommunicationPage.tsx`, `frontend/src/pages/DiagnosticsPage.tsx`, with existing `tests/test_communication_projection.py` and `tests/test_artifact_manifests.py` allowed for adjacent coverage.
- Package E target: task workflow projection keyed by `task_id`; cross-task projection edges rejected or dropped with protocol-violation/diagnostic evidence; taskless or global events routed to timeline/communication/diagnostics; normalize `UiMetroProjection` to `UiTaskWorkflowProjection` at the API boundary; remove demo/hardcoded frontend data.

## Guard Invariants

1. No-bypass authority invariant: every write path must resolve an explicit `Principal`. Compatibility adapters must not mint controller authority from arbitrary `actor` input. Non-controller/user write attempts should fail closed with `ProjectionEffect.REJECT` and a protocol violation where available.
2. Deprecated adapter invariant: old mixed routes and CLI aliases are compatibility adapters only. They should emit `adapter.deprecated_path_used` audit events and must never bypass protocol, authority, fencing, or projection-effect enforcement. Worker task-complete aliases without fencing remain audit-only or `needs_fencing`, not task state commits.
3. Projection effect and fencing coverage: READY evidence should show reject envelopes include `error`, `message`, `projection_effect`, `violation_id`, and `fencing_result` where available. Static scans or focused tests should show no new write event with `projection_effect=None` or `fencing_result=None`.
4. D/E boundary: Package D owns route and CLI split plus adapter reject/deprecation behavior. Package E owns projection shapes and frontend normalization. D should not mutate `projections.py` or frontend files; E should not change server, CLI, authority, protocol, policy, tasks, replacement, context, gates, reviews, or models without a new scope decision.
5. Task workflow edge risk: task workflow projection must be keyed by `task_id`. Cross-task edges should be rejected or dropped and recorded as a violation/diagnostic, never silently connected. Taskless/global events should not appear in task workflow unless an explicit binding exists.
6. API-boundary normalization only: frontend compatibility normalization may happen in `operationsApi.ts`; page-local implicit shape repair and hardcoded demo rows should be avoided.
7. Event log/projection separation: projection builders may replay/query events, but UI pages should consume canonical projection state rather than inferring durable state from raw event logs differently from the backend projection.

## Recommended QA Checks

- Package D focused: worker actor attempts against controller routes fail closed with HTTP 403 or equivalent `authority_reject`, `projection_effect=REJECT`, and `violation_id` where available.
- Package D focused: allowed controller/user/worker paths still work through the new split routes; deprecated route and CLI alias calls emit `adapter.deprecated_path_used`; CLI help exits cleanly.
- Package E focused: malformed cross-task edge events are rejected or dropped with violation/diagnostic evidence; taskless/global events are absent from task workflow and present in communication/timeline/diagnostics.
- Package E focused: frontend build passes; frontend has no hardcoded demo records; Chinese/operator-facing labels are sourced from real projection metadata or stable UI copy, not fabricated rows.
- Combined: run focused API/CLI tests, Package E projection/frontend tests, full pytest, frontend build, CLI help, and static scans for `projection_effect=None`, `fencing_result=None`, arbitrary actor-to-controller authority, and page-local demo data.

## Open Risks To Watch

- `EventType.ADAPTER_DEPRECATED_PATH_USED` exists, but workers still need to prove old routes/aliases record the audit event through the protocol/event path and do not bypass enforcement.
- `ProjectionReader.replacement_recommendations()` appears capable of invoking replacement recommendation logic while building projections. If wired with a persistent `db_path`, projection reads may append recommendation events. Package E/QA should check that projection reads are side-effect free or explicitly isolated.
- `OperationsProjection.events` still exposes raw event history. Frontend pages should not use it as the primary task workflow source once the normalized workflow projection exists.
- The worktree is concurrently dirty from previous waves and active workers. Do not revert unrelated changes while reviewing Wave4 output.

## Fallback Note

If broker delivery fails during Wave4, helper2 should append relay summaries to `coordination/messages.ndjson`, `coordination/agent-status.md`, and this file as needed, then replay missed broker messages after recovery.
