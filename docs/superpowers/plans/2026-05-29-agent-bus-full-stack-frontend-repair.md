# Agent Bus Full-Stack Frontend Repair Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Repair the Agent Bus frontend toward the five 5-29 reference screenshots by adding a real backend UI projection, safe artifact file URLs, and frontend pages that render that projection instead of page-local mock-like derivations.

**Architecture:** Keep FastAPI/SQLite as the source of truth and extend `/api/projections/operations` with durable artifacts plus a `ui` projection. Frontend normalization remains in `operationsApi.ts`; page components consume typed projection data and use shared components for the metro graph, action queue, and artifact preview. This preserves current runtime actions while making the interface converge around a single data contract.

**Tech Stack:** Python 3, FastAPI, Pydantic, SQLite, pytest, React 19, TypeScript, Vite, Radix primitives, lucide-react, optional `@xyflow/react` for future graph editors but custom SVG/CSS for the first metro pass.

---

## File Structure

- Modify `agent_bus/projections.py`: add durable artifact reading, UI projection Pydantic models, and projection builders.
- Modify `agent_bus/artifacts.py`: add artifact manifest metadata and safe path resolution helpers.
- Modify `agent_bus/server.py`: expose safe artifact file serving and preserve static frontend serving.
- Modify `tests/test_server.py`: cover operations `ui` projection and durable artifacts.
- Modify `tests/test_artifact_manifests.py`: cover manifest metadata and file endpoint safety.
- Modify `frontend/src/operationsApi.ts`: add UI projection and artifact URL types.
- Create `frontend/src/components/MetroGraph.tsx`: render real metro nodes/edges.
- Modify `frontend/src/pages/HomePage.tsx`: replace local horizontal-card metro with backend `ui.metro`.
- Modify `frontend/src/pages/ArtifactsPage.tsx`: use backend preview/download URLs.
- Modify `frontend/src/pages/RunsPage.tsx`, `frontend/src/pages/GatesPage.tsx`, `frontend/src/pages/CommunicationPage.tsx`, `frontend/src/pages/DiagnosticsPage.tsx`, and `frontend/src/pages/SettingsPage.tsx` if they need projection alignment or reference-style polish.
- Modify `frontend/src/styles.css` and focused style files as needed for stable metro/action/artifact layout.

---

## Task 1: Backend Projection Contract

- [ ] Add `ArtifactRecord` to `OperationsProjection`.
- [ ] Add `_artifacts(conn)` in `ProjectionReader`, ordered by `created_at asc, artifact_id asc`.
- [ ] Add `_row_to_artifact(row)` helper using `ArtifactRecord`.
- [ ] Add UI projection models: `UiActiveRunProjection`, `UiMetroNode`, `UiMetroEdge`, `UiMetroProjection`, `UiActionItem`, `UiAgentSummary`, `UiGateDecision`, `UiArtifactSummary`, `UiOperationsProjection`.
- [ ] Add `_build_ui_projection(...)` that uses real runs, tasks, gates, artifacts, agents, inbox, contexts, review findings, and events.
- [ ] Write a pytest that creates a run, tasks, gate, artifact, and agent, then asserts `/api/projections/operations` includes `artifacts` and `ui.metro` task/gate/artifact nodes.
- [ ] Run the new pytest and fix failures.

## Task 2: Artifact File Contract

- [ ] Add `size_bytes`, `content_type`, `preview_url`, and `download_url` to `ArtifactManifestItem`.
- [ ] Add `resolve_artifact_file(root, artifact_path)` that resolves only inside the artifact root and raises a typed error for traversal/missing files.
- [ ] Enhance `read_artifact_manifests` to compute size/content type and URL fields from the safe relative path.
- [ ] Add `GET /api/artifacts/files/{artifact_path:path}` to `server.py` using `FileResponse`.
- [ ] Add tests for manifest metadata, successful file serving, missing file, and traversal rejection.
- [ ] Run `pytest tests/test_artifact_manifests.py -q`.

## Task 3: Frontend Types And Normalization

- [ ] Add TypeScript types for `UiProjection`, `UiMetroNode`, `UiMetroEdge`, `UiActionItem`, `UiAgentSummary`, `UiGateDecision`, and `UiArtifactSummary`.
- [ ] Normalize `root.ui` with stable empty defaults.
- [ ] Normalize durable `root.artifacts` from backend `ArtifactRecord`.
- [ ] Add `previewUrl`, `downloadUrl`, `sizeBytes`, and `contentType` to `ArtifactManifestRow`.
- [ ] Run `npx tsc --noEmit` from `frontend/`.

## Task 4: Home Metro And Action Queue

- [ ] Create `MetroGraph.tsx` with SVG/CSS track, typed nodes/edges, keyboard-accessible node buttons, and no fake fallback data.
- [ ] Replace `HomePage` local `buildMetroNodes` usage with `projection.ui.metro`.
- [ ] Replace page-local action queue where possible with `projection.ui.actionItems`, mapping each item to the existing ActionDrawer and view navigation.
- [ ] Keep empty state polished but truthful when no run/task exists.
- [ ] Update CSS so the metro is a graph-like workflow surface, not just horizontally scrolling cards.

## Task 5: Page-Wide Reference Convergence

- [ ] Runs: use `projection.ui.activeRun` for default selection and connect artifacts/gates to selected run lanes.
- [ ] Gates: align queue/detail/action hierarchy with `projection.ui.gateDecisions`; do not fabricate owners.
- [ ] Artifacts: use manifest preview/download URLs and durable artifacts together.
- [ ] Communication: keep send/recipient APIs intact and make message detail/action state align with projection links.
- [ ] Diagnostics/Settings: preserve real runtime controls and make stale/degraded/fault states clear.
- [ ] Scan for mock-looking labels, fake metrics, and hardcoded runtime rows.

## Task 6: Verification

- [ ] Run focused backend tests: `pytest tests/test_server.py tests/test_artifact_manifests.py -q`.
- [ ] Run frontend typecheck: `npx tsc --noEmit` from `frontend/`.
- [ ] Run frontend build: `npm run build` from `frontend/`.
- [ ] Open `http://127.0.0.1:8787/` in Browser, verify desktop and mobile Home, Communication, Runs, Gates, Artifacts.
- [ ] Confirm console has no app errors and primary text does not overlap.
- [ ] Record any residual gaps against the spec.

## Self-Review

- Spec coverage: backend UI projection, artifact file contract, frontend data normalization, Home metro, all pages, and verification are represented.
- Placeholder scan: no `TBD`, fake data, or hardcoded row instructions.
- Type consistency: backend uses snake_case JSON from Pydantic; frontend normalization accepts snake_case and exposes camelCase.
