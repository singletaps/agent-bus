# Agent Bus Full-Stack Frontend Repair Spec

Date: 2026-05-29

## Goal

Converge the Agent Bus frontend toward the five 5-29 reference screenshots by repairing the data model, backend projection, artifact file contract, and all major frontend pages as one coherent operations room. The metro graph is the most visible symptom, but the fix must cover Home, Communication, Runs, Gates, Artifacts, Diagnostics, and Settings.

## Problem Statement

The current frontend is technically functional but still reads like an engineering prototype. It renders raw runtime tables and page-local derived state instead of a stable operations projection shaped for an operator. The Home metro map is currently a horizontal card strip, Artifacts cannot reliably preview real local files, and several pages independently infer state. This makes the UI drift away from the reference screenshots and risks inconsistency between frontend cards, backend data, and operator actions.

This is not a React/Vite limitation. The existing stack can support the target UI after adding the right data projection and a few frontend components.

## References

- `C:\Users\laptopofzy\Documents\Agent bus\5-29\Home.png` equivalent reference: `5-29` Home screenshot.
- `C:\Users\laptopofzy\Documents\Agent bus\5-29\Communication.png` equivalent reference.
- `C:\Users\laptopofzy\Documents\Agent bus\5-29\Runs.png` equivalent reference.
- `C:\Users\laptopofzy\Documents\Agent bus\5-29\Gates.png` equivalent reference.
- `C:\Users\laptopofzy\Documents\Agent bus\5-29\Artifacts.png` equivalent reference.
- Repo-specific design rules: `.agents/skills/frontend-design`.
- Operator review rules: `.agents/skills/ux-operator-review`.
- Review rubric: `.agents/skills/frontend-design-review`.

## Non-Goals

- Do not introduce fake runs, fake tasks, fake artifacts, fake agents, or fake telemetry.
- Do not hardcode the reference screenshots into the UI.
- Do not replace the FastAPI/SQLite/React architecture.
- Do not build a separate mock frontend route.
- Do not change inbox wait/ack, context invalidation, replacement approval, or gate decision semantics except where needed to expose real projection data.

## Data Contract

Extend `/api/projections/operations` as the single frontend source of truth. Existing fields remain backward compatible. Add these top-level fields:

- `artifacts`: durable artifacts from the SQLite `artifacts` table.
- `ui`: a UI-ready projection derived from durable records, event replay, inbox, contexts, agents, and gates.

The `ui` object contains:

- `active_run`: selected active or latest run summary.
- `metro`: graph-ready workflow map.
- `action_items`: prioritized operator actions.
- `agent_summaries`: workstation summaries for each agent.
- `gate_decisions`: gate queue summaries.
- `artifact_summary`: counts and latest artifact pointers.

### Metro Projection

`ui.metro.nodes` must use real records only:

- `start`: active run start marker.
- `task`: task records for the active run.
- `gate`: gates attached to active-run tasks.
- `artifact`: durable artifacts attached to active-run tasks.

`ui.metro.edges` links those nodes by real relationships. The main path follows task creation order. Gate and artifact nodes branch from their task. Each node must include `id`, `kind`, `title`, `subtitle`, `state`, `tone`, `run_id`, `task_id`, `agent_id`, and `route`.

### Action Items

`ui.action_items` must be ordered by operator impact:

1. Failed, blocked, or stale/context-lost agent work.
2. Open gates.
3. Open review findings.
4. Queued inbox work.
5. Reviewable or recent artifacts.
6. Active task/run inspection.

Each item includes `id`, `kind`, `title`, `description`, `tone`, `route`, optional `task_id`, `gate_id`, `artifact_id`, `agent_id`, and `priority`.

### Artifact Files

Enhance `/api/artifacts/manifests` to return:

- `size_bytes`
- `content_type`
- `preview_url`
- `download_url`

Add a safe file endpoint:

- `GET /api/artifacts/files/{artifact_path:path}`

The endpoint must resolve paths under the configured artifact root only. Path traversal and missing files must not expose host files.

## Frontend Contract

The frontend must consume the backend projection instead of reconstructing core state in each page.

- `frontend/src/operationsApi.ts` owns normalization and type compatibility.
- Home renders `projection.ui.metro` and `projection.ui.actionItems`.
- Artifacts renders manifest `previewUrl`/`downloadUrl` and durable `projection.artifacts`.
- Runs, Gates, Communication, Diagnostics, and Settings keep real API actions and state, but their summaries should align with `projection.ui`.
- The ActionDrawer remains the common route for operator decisions and must preserve interrupt routing semantics.

## Visual Direction

Use the repo-specific "organic trading terminal" direction:

- Dense but calm operational surfaces.
- White/pale blue-gray canvas, compact panels, 8px radius or less.
- Blue active, amber gate/waiting, red fault, purple review, green complete, gray standby.
- Long IDs are secondary; short IDs/chips in primary cards.
- No decorative filler strings. Every label must name real state or a clear action.

## Acceptance

Backend:

- `/api/projections/operations` includes durable artifacts and `ui`.
- `ui.metro` contains task/gate/artifact nodes when durable records exist.
- Run state, gate owner, stale session, inbox, context, and artifact counts remain consistent with existing tests.
- Artifact file endpoint serves files inside the artifact root and blocks traversal.

Frontend:

- `npm --prefix frontend run build` exits 0.
- TypeScript check exits 0.
- Home no longer renders the metro as a horizontal card-only scroll.
- Artifacts can preview or open real manifest files through backend URLs.
- No mock rows or fake metrics are introduced.
- Desktop and mobile browser checks show no overlapping primary text.

Testing:

- Add backend pytest coverage for UI projection and artifact file serving.
- Run the existing pytest suite or a focused subset plus the changed tests.
- Capture browser evidence for desktop and mobile after build.
