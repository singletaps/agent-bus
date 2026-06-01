# Agent Bus Frontend Product Restructure Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn the Agent Bus frontend from a generic monitoring backend into a runtime control console, collaboration communication console, and audit diagnostics console.

**Architecture:** Keep SQLite/FastAPI/React as the platform. Add missing projection contracts for Bus messages, run detail, gate ownership, diagnostics, and artifact manifests; split the current large `frontend/src/App.tsx` into page-focused modules; remove unverifiable UI metrics; route all operator instructions through Agent Bus. Ship in serial waves with parallel workers and QA gates between waves.

**Tech Stack:** Python 3, SQLite WAL, FastAPI, Pydantic, pytest, React 19, TypeScript, Vite, lucide-react, Playwright/browser smoke verification through the Codex in-app browser.

---

## Source Inputs

- Main review file: `C:\Users\laptopofzy\Documents\Agent bus\docs\browser-frontend-comments.md`
- Reference image: `C:\Users\laptopofzy\Documents\Agent bus\docs\assets\communication-console-reference-2026-05-29.png`
- Current frontend: `C:\Users\laptopofzy\Documents\Agent bus\frontend\src\App.tsx`
- Current frontend API normalizer: `C:\Users\laptopofzy\Documents\Agent bus\frontend\src\operationsApi.ts`
- Current frontend view model: `C:\Users\laptopofzy\Documents\Agent bus\frontend\src\operationsRoomModel.ts`
- Current labels: `C:\Users\laptopofzy\Documents\Agent bus\frontend\src\uiText.ts`
- Current CSS: `C:\Users\laptopofzy\Documents\Agent bus\frontend\src\styles.css`
- Backend projection: `C:\Users\laptopofzy\Documents\Agent bus\agent_bus\projections.py`
- Backend API: `C:\Users\laptopofzy\Documents\Agent bus\agent_bus\server.py`
- Runtime models: `C:\Users\laptopofzy\Documents\Agent bus\agent_bus\models.py`
- Event store: `C:\Users\laptopofzy\Documents\Agent bus\agent_bus\store.py`
- Task/gate/artifact stores: `C:\Users\laptopofzy\Documents\Agent bus\agent_bus\tasks.py`, `C:\Users\laptopofzy\Documents\Agent bus\agent_bus\gates.py`
- Existing tests: `C:\Users\laptopofzy\Documents\Agent bus\tests\test_server.py`, `C:\Users\laptopofzy\Documents\Agent bus\tests\test_tasks_gates_reviews.py`

## Locked Product Rules

- Home only answers: what is happening now, where it is blocked, and what the operator can do.
- MVP Home removes the global success-rate metric.
- Red means failed / blocked / rejected. Gray means not started / no data.
- Every action-required item must open an action drawer, composer, approval panel, reassignment flow, artifact view, or detail page.
- Delete the old global Inspector. Keep page-scoped right-side detail panels that show observable facts.
- Delete the old global Command Console. Keep Bus-backed page composers that create structured Bus records.
- Communication Console is not a normal chat UI and not a raw event log.
- Event Log becomes Diagnostics / Audit, not daily communication.
- Do not surface hidden Codex subagent conversation internals, trust, quality, or reliability.
- Agent `name` and `roles` are separate. `roles` is an array and can include values such as `controller`, `worker`, `qa`, `helper`, and `observer`.
- Do not duplicate the same summary UI across Home, Communication, Gates, Runs, and Artifacts.

## Coordination Model

Execution is serial by wave and parallel within each wave.

- `runtime-worker-1`: frontend shell, Home, action queue, shared page integration.
- `runtime-worker-2`: Communication Console, Bus message projection, Bus-backed composer.
- `runtime-worker-3`: Runs, Gates, Artifacts, artifact manifest API, gate owner resolution.
- `runtime-worker-4`: visual system, status colors, icons, Diagnostics, responsive layout.
- `runtime-helper-1`: Controller-style coordinator; owns wave board, file ownership log, and user feedback relay.
- `runtime-helper-2`: integration support; monitors Agent Bus, artifact fixtures, service boot, browser captures.
- `runtime-qa`: gatekeeper; validates each wave before the next wave begins.

Subagents should communicate through Agent Bus first. If Agent Bus is unavailable, append status to:

```text
C:\Users\laptopofzy\Documents\Agent bus\USER_FEEDBACK.md
C:\Users\laptopofzy\Documents\Agent bus\coordination\agent-status.md
C:\Users\laptopofzy\Documents\Agent bus\coordination\wave-gates.md
```

Every worker must announce file ownership before editing. No two workers edit the same file in the same wave unless helper1 explicitly brokers the merge.

## File Structure Target

Create these focused frontend files so workers do not fight over one giant `App.tsx`:

```text
frontend/src/
  App.tsx
  operationsApi.ts
  operationsRoomModel.ts
  uiText.ts
  statusModel.ts
  components/
    ActionDrawer.tsx
    AgentMark.tsx
    DetailRail.tsx
    EventTable.tsx
    IdChip.tsx
    Panel.tsx
    StatusBadge.tsx
  pages/
    HomePage.tsx
    CommunicationPage.tsx
    RunsPage.tsx
    GatesPage.tsx
    ArtifactsPage.tsx
    DiagnosticsPage.tsx
    SettingsPage.tsx
  styles/
    base.css
    layout.css
    pages.css
```

Create or extend these backend files:

```text
agent_bus/
  models.py
  projections.py
  server.py
  artifacts.py
tests/
  test_frontend_contracts.py
  test_artifact_manifests.py
  test_communication_projection.py
```

## Wave 0: Documentation And Conflict Guardrails

Owner: `runtime-helper-1`

**Files:**
- Modify: `docs/browser-frontend-comments.md`
- Create: `coordination/frontend-product-restructure-wave-board.md`

- [ ] **Step 1: Verify comments conflict rules are present**

Run:

```powershell
Select-String -Path 'docs\browser-frontend-comments.md' -Encoding UTF8 -Pattern 'Current conflict-resolution rules','Red: failed','Gray: not started','Delete the old global `检查器`','Delete the old global `指令台`','MVP removes global success-rate metrics'
```

Expected: each pattern returns at least one line.

- [ ] **Step 2: Create the wave board**

Create `coordination/frontend-product-restructure-wave-board.md` with this structure:

```markdown
# Frontend Product Restructure Wave Board

## Current Wave

Wave 0

## File Ownership

| File | Owner | Wave | Notes |
| --- | --- | --- | --- |

## Gate Status

| Gate | Owner | Status | Evidence |
| --- | --- | --- | --- |
| Gate 0 | runtime-qa | pending | waiting for Wave 0 checks |

## Worker Status

| Agent | Status | Current task | Last evidence |
| --- | --- | --- | --- |
```

- [ ] **Step 3: Commit or hand off Wave 0 docs**

Expected handoff note:

```text
Wave 0 docs ready. Conflict rules are in docs/browser-frontend-comments.md. Wave board created at coordination/frontend-product-restructure-wave-board.md.
```

## Wave A: Backend And Frontend Data Contracts

### Task A1: Worker1 Frontend Observable Contract Cleanup

**Assignee:** `runtime-worker-1`

**Files:**
- Modify: `frontend/src/operationsApi.ts`
- Modify: `frontend/src/operationsRoomModel.ts`
- Create: `frontend/src/statusModel.ts`
- Test: `frontend/package.json`

- [ ] **Step 1: Add observable status model**

Create `frontend/src/statusModel.ts`:

```ts
import type { Tone } from "./operationsApi";

export type RuntimeStatusColor = "green" | "yellow" | "red" | "gray" | "purple" | "blue";

export type RuntimeStatus = {
  label: string;
  tone: Tone;
  color: RuntimeStatusColor;
  isActionRequired: boolean;
};

export function statusFromState(state: string, kind: "task" | "gate" | "agent" | "run" | "message"): RuntimeStatus {
  const value = state.toLowerCase().replace(/[_-]/g, " ");
  if (["fail", "failed", "block", "blocked", "reject", "rejected", "invalid", "stuck"].some((part) => value.includes(part))) {
    return { label: state, tone: "bad", color: "red", isActionRequired: true };
  }
  if (["review", "qa"].some((part) => value.includes(part))) {
    return { label: state, tone: "info", color: "purple", isActionRequired: kind === "gate" };
  }
  if (["wait", "waiting", "pending", "queued", "assigned", "acknowledged", "working", "progress", "open", "escalated"].some((part) => value.includes(part))) {
    return { label: state, tone: "warn", color: "yellow", isActionRequired: value.includes("open") || value.includes("escalated") };
  }
  if (["done", "complete", "completed", "pass", "passed", "approved", "acked"].some((part) => value.includes(part))) {
    return { label: state, tone: "good", color: "green", isActionRequired: false };
  }
  if (["created", "not started", "unknown", "none", "no data"].some((part) => value.includes(part))) {
    return { label: state, tone: "info", color: "gray", isActionRequired: false };
  }
  return { label: state || "无数据", tone: "info", color: "gray", isActionRequired: false };
}
```

- [ ] **Step 2: Extend frontend Agent type with `name` and `roles`**

In `frontend/src/operationsApi.ts`, change `AgentRow` to include:

```ts
export type AgentRow = {
  id: string;
  name: string;
  role: string;
  roles: string[];
  sessionId: string;
  state: string;
  lastSeenAt: string;
  inboxCount: number;
  capabilities: string[];
};
```

Keep raw backend fields private to the normalizer. Do not render health, confidence, or hidden-conversation integrity values.

- [ ] **Step 3: Normalize roles without schema migration**

In `normalizeAgent`, derive `name` and `roles` from identity/display fields and existing role strings:

```ts
const displayName =
  pickString(agent, ["name", "display_name", "displayName"]) ||
  pickString(identity, ["display_name", "displayName"]) ||
  id ||
  "unknown-agent";
const roleValue =
  pickString(agent, ["role", "agent_role", "kind", "label"]) ||
  pickString(identity, ["role"]) ||
  "unassigned";
const roles = normalizeRoles(firstValue(agent, ["roles", "role_list", "roleList"]) || roleValue);
```

Add:

```ts
function normalizeRoles(raw: unknown): string[] {
  const values = Array.isArray(raw) ? raw : String(raw || "").split(/[,\s/|]+/);
  const roles = values
    .map((value) => String(value).trim().toLowerCase())
    .filter(Boolean)
    .map((value) => (value === "archive" ? "observer" : value));
  return Array.from(new Set(roles.length ? roles : ["unassigned"]));
}
```

- [ ] **Step 4: Remove Home success-rate dependency from view model**

In `operationsRoomModel.ts`, ensure no model property requires a global success rate. `taskProgress()` may continue to estimate an individual task progress from task state.

Run:

```powershell
Select-String -Path 'frontend\src\operationsRoomModel.ts','frontend\src\operationsApi.ts' -Pattern 'successRate','trustText','健康','能力','可信'
```

Expected: `successRate`, `trustText`, `健康`, `能力`, and `可信` have no matches in exported UI models.

- [ ] **Step 5: Build frontend**

Run:

```powershell
npm --prefix frontend run build
```

Expected: Vite build exits `0`.

### Task A2: Worker2 Bus Message Projection And Send API

**Assignee:** `runtime-worker-2`

**Files:**
- Modify: `agent_bus/models.py`
- Modify: `agent_bus/projections.py`
- Modify: `agent_bus/server.py`
- Test: `tests/test_communication_projection.py`

- [ ] **Step 1: Add Bus message projection models**

In `agent_bus/models.py`, add:

```python
class BusMessageLink(BaseModel):
    run_id: str | None = None
    task_ids: list[str] = Field(default_factory=list)
    gate_ids: list[str] = Field(default_factory=list)
    artifact_ids: list[str] = Field(default_factory=list)


class BusMessageProjection(BaseModel):
    message_id: str
    bus_event_id: str
    thread_id: str | None = None
    space_id: str | None = None
    sender_agent_id: str | None = None
    sender_name: str
    sender_roles: list[str] = Field(default_factory=list)
    recipient_agent_ids: list[str] = Field(default_factory=list)
    message_type: str
    delivery_state: str
    ack_state: str
    reply_state: str
    priority: str = "normal"
    body: str
    links: BusMessageLink = Field(default_factory=BusMessageLink)
    created_at: str
    updated_at: str
```

- [ ] **Step 2: Project messages from Bus events and inbox rows**

In `agent_bus/projections.py`, add a function:

```python
def build_message_projection(events: list[BusEvent], inbox: list[InboxItem]) -> list[BusMessageProjection]:
    inbox_by_event: dict[str, list[InboxItem]] = {}
    for item in inbox:
        event_id = str(item.payload.get("event_id") or item.payload.get("bus_event_id") or "")
        if event_id:
            inbox_by_event.setdefault(event_id, []).append(item)

    messages: list[BusMessageProjection] = []
    for event in events:
        event_type = str(event.type)
        if event_type not in {"user.interrupt_created", "coordination.recorded", "gate.opened", "gate.result", "review.changes_requested", "task.reassigned"}:
            continue
        payload = event.payload or {}
        recipients = sorted({item.agent_id for item in inbox_by_event.get(event.event_id, [])})
        body = str(payload.get("text") or payload.get("message") or payload.get("summary") or event_type)
        messages.append(
            BusMessageProjection(
                message_id=str(payload.get("message_id") or event.event_id),
                bus_event_id=event.event_id,
                thread_id=str(payload.get("thread_id") or event.run_id or event.task_id or ""),
                space_id=str(payload.get("space_id") or "runtime"),
                sender_agent_id=event.actor,
                sender_name=event.actor or "system",
                sender_roles=[],
                recipient_agent_ids=recipients,
                message_type=str(payload.get("message_type") or event_type),
                delivery_state="delivered" if recipients else "sent",
                ack_state="acked" if inbox_by_event.get(event.event_id) and all(item.status == "acked" for item in inbox_by_event[event.event_id]) else "waiting_ack",
                reply_state=str(payload.get("reply_state") or "not_required"),
                priority=str(payload.get("priority") or "normal"),
                body=body,
                links=BusMessageLink(
                    run_id=event.run_id,
                    task_ids=[event.task_id] if event.task_id else [],
                    gate_ids=[str(payload.get("gate_id"))] if payload.get("gate_id") else [],
                    artifact_ids=[str(payload.get("artifact_id"))] if payload.get("artifact_id") else [],
                ),
                created_at=event.ts,
                updated_at=event.ts,
            )
        )
    return messages
```

- [ ] **Step 3: Add API endpoints**

In `agent_bus/server.py`, add response/request models and endpoints:

```python
class MessagesResponse(ApiEnvelope):
    messages: list[BusMessageProjection]


class BusMessageSendRequest(BaseModel):
    actor: str = "operator"
    text: str
    recipient_agent_ids: list[str] = Field(default_factory=list)
    run_id: str | None = None
    task_id: str | None = None
    gate_id: str | None = None
    message_type: str = "instruction"
    priority: str = "normal"


class BusMessageSendResponse(ApiEnvelope):
    event: BusEvent
    affected_agents: list[str]
```

Endpoint behavior:

```python
@app.get("/api/projections/messages", response_model=MessagesResponse)
def messages_projection(request: Request, event_limit: int = Query(default=200, ge=0)) -> MessagesResponse:
    reader = ProjectionReader(_db_path(request))
    projection = reader.build_operations_projection(event_limit=event_limit)
    return MessagesResponse(messages=build_message_projection(projection.events, projection.inbox))
```

`POST /api/messages/send` should call `create_user_interrupt` for operator instructions so delivery remains Bus-backed.

- [ ] **Step 4: Add tests**

Create `tests/test_communication_projection.py`:

```python
from fastapi.testclient import TestClient

from agent_bus.server import create_app


def test_operator_message_projects_delivery_and_ack_state(tmp_path):
    db_path = tmp_path / "agent-bus.sqlite3"
    client = TestClient(create_app(db_path=db_path, frontend_dist=tmp_path / "missing-dist"))

    sent = client.post(
        "/api/messages/send",
        json={
            "actor": "operator",
            "text": "请检查失败任务。",
            "recipient_agent_ids": ["worker.one"],
            "run_id": "run-1",
            "task_id": "task-1",
            "message_type": "instruction",
            "priority": "high",
        },
    ).json()
    messages = client.get("/api/projections/messages").json()["messages"]

    assert sent["ok"] is True
    assert messages[0]["body"] == "请检查失败任务。"
    assert messages[0]["delivery_state"] in {"sent", "delivered"}
    assert messages[0]["ack_state"] == "waiting_ack"
    assert messages[0]["links"]["run_id"] == "run-1"
    assert messages[0]["links"]["task_ids"] == ["task-1"]
```

- [ ] **Step 5: Run backend tests**

Run:

```powershell
pytest tests/test_communication_projection.py tests/test_server.py -q
```

Expected: all selected tests pass.

### Task A3: Worker3 Artifact Manifest API And Gate Owner Projection

**Assignee:** `runtime-worker-3`

**Files:**
- Create: `agent_bus/artifacts.py`
- Modify: `agent_bus/server.py`
- Modify: `agent_bus/projections.py`
- Test: `tests/test_artifact_manifests.py`
- Test: `tests/test_server.py`

- [ ] **Step 1: Add artifact manifest reader**

Create `agent_bus/artifacts.py`:

```python
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field


class ArtifactManifestItem(BaseModel):
    artifact_id: str
    run_id: str | None = None
    task_id: str | None = None
    agent_id: str | None = None
    type: str
    title: str
    path: str
    created_at: str | None = None
    summary: str = ""


class ArtifactManifestResponse(BaseModel):
    root: str
    artifacts: list[ArtifactManifestItem] = Field(default_factory=list)


def read_artifact_manifests(root: str | Path) -> ArtifactManifestResponse:
    base = Path(root).expanduser().resolve()
    if not base.exists():
        return ArtifactManifestResponse(root=str(base), artifacts=[])
    artifacts: list[ArtifactManifestItem] = []
    for manifest_path in sorted(base.glob("**/manifest.json")):
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
        items: list[dict[str, Any]] = data if isinstance(data, list) else [data]
        for item in items:
            relative_path = str(item.get("path", "")).replace("\\", "/")
            resolved = (manifest_path.parent / relative_path).resolve()
            if not str(resolved).startswith(str(base)):
                continue
            artifacts.append(ArtifactManifestItem(**{**item, "path": str(resolved.relative_to(base)).replace("\\", "/")}))
    return ArtifactManifestResponse(root=str(base), artifacts=artifacts)
```

- [ ] **Step 2: Add safe artifact API**

In `agent_bus/server.py`, add:

```python
class ArtifactManifestApiResponse(ApiEnvelope):
    root: str
    artifacts: list[ArtifactManifestItem]
```

Endpoint:

```python
@app.get("/api/artifacts/manifests", response_model=ArtifactManifestApiResponse)
def artifact_manifests(request: Request) -> ArtifactManifestApiResponse:
    root = os.environ.get("AGENT_BUS_ARTIFACT_ROOT") or str(Path(_db_path(request) or ".").resolve().parent / ".agent-bus" / "artifacts")
    result = read_artifact_manifests(root)
    return ArtifactManifestApiResponse(root=result.root, artifacts=result.artifacts)
```

- [ ] **Step 3: Bind gate owner to QA role when owner is empty**

In `agent_bus/projections.py`, enrich gate projection after reading agents. If `gate.owner_agent_id` is empty and an identity has role `qa`, project that agent id as the owner for UI display without mutating the gate record.

Exact behavior:

```python
def _qa_owner(agents: list[AgentProjection]) -> str | None:
    for agent in agents:
        role = (agent.identity.role or "").lower()
        if role == "qa" or "qa" in role.split(","):
            return agent.identity.agent_id
    return None
```

Use this only in projection output. The durable gate record remains unchanged.

- [ ] **Step 4: Add tests**

Create `tests/test_artifact_manifests.py`:

```python
import json

from fastapi.testclient import TestClient

from agent_bus.artifacts import read_artifact_manifests
from agent_bus.server import create_app


def test_artifact_manifest_reader_ignores_paths_outside_root(tmp_path, monkeypatch):
    root = tmp_path / ".agent-bus" / "artifacts" / "run_1" / "task_1"
    root.mkdir(parents=True)
    (root / "manifest.json").write_text(
        json.dumps([
            {"artifact_id": "art_ok", "run_id": "run_1", "task_id": "task_1", "agent_id": "worker", "type": "screenshot", "title": "Home", "path": "home.png"},
            {"artifact_id": "art_bad", "type": "log", "title": "Bad", "path": "../../outside.log"}
        ]),
        encoding="utf-8",
    )
    (root / "home.png").write_bytes(b"png")

    result = read_artifact_manifests(tmp_path / ".agent-bus" / "artifacts")

    assert [item.artifact_id for item in result.artifacts] == ["art_ok"]
    assert result.artifacts[0].path == "run_1/task_1/home.png"


def test_artifact_manifest_api_uses_configured_root(tmp_path, monkeypatch):
    artifact_root = tmp_path / "artifacts" / "run_1" / "task_1"
    artifact_root.mkdir(parents=True)
    (artifact_root / "manifest.json").write_text(
        json.dumps({"artifact_id": "art_1", "type": "report", "title": "QA report", "path": "qa.md"}),
        encoding="utf-8",
    )
    (artifact_root / "qa.md").write_text("ok", encoding="utf-8")
    monkeypatch.setenv("AGENT_BUS_ARTIFACT_ROOT", str(tmp_path / "artifacts"))

    client = TestClient(create_app(db_path=tmp_path / "bus.sqlite3", frontend_dist=tmp_path / "missing-dist"))
    response = client.get("/api/artifacts/manifests").json()

    assert response["ok"] is True
    assert response["artifacts"][0]["artifact_id"] == "art_1"
```

- [ ] **Step 5: Run tests**

Run:

```powershell
pytest tests/test_artifact_manifests.py tests/test_tasks_gates_reviews.py tests/test_server.py -q
```

Expected: all selected tests pass.

### Task A4: Worker4 Diagnostics Projection And UI Text Cleanup

**Assignee:** `runtime-worker-4`

**Files:**
- Modify: `frontend/src/uiText.ts`
- Create: `frontend/src/components/StatusBadge.tsx`
- Create: `frontend/src/components/IdChip.tsx`
- Create: `frontend/src/components/Panel.tsx`
- Create: `frontend/src/components/EventTable.tsx`

- [ ] **Step 1: Update navigation labels**

Change `viewLabels` to:

```ts
export const viewLabels: Record<ViewName, string> = {
  Home: "控制首页",
  Communication: "通信",
  Runs: "任务流",
  Gates: "门禁",
  Artifacts: "产物",
  Diagnostics: "诊断",
  Settings: "设置",
};
```

This step depends on Worker1 or the integrator updating `ViewName`.

- [ ] **Step 2: Remove old labels from normal UI**

In `uiText`, remove labels for old global inspector, old replacement dock, old command console, hidden conversation claims, and global rate metrics. Add:

```ts
panels: {
  runtimePosture: "当前运行态势",
  workflowMap: "任务流地铁图",
  actionQueue: "行动队列",
  communication: "通信台",
  agentDetail: "智能体详情",
  messageDetail: "消息详情",
  runs: "任务流",
  gates: "审批中心",
  artifacts: "产物",
  diagnostics: "诊断",
  settings: "设置",
}
```

- [ ] **Step 3: Create shared panel and ID components**

`Panel.tsx`:

```tsx
import React from "react";

export function Panel({ title, meta, children, className = "" }: { title: string; meta?: string; children: React.ReactNode; className?: string }) {
  return (
    <section className={`panel ${className}`.trim()}>
      <header className="panelHeader">
        <h3>{title}</h3>
        {meta ? <span>{meta}</span> : null}
      </header>
      {children}
    </section>
  );
}
```

`IdChip.tsx`:

```tsx
export function IdChip({ value, label }: { value: string; label?: string }) {
  const short = value.length > 14 ? `${value.slice(0, 10)}…` : value;
  return <code className="idChip" title={value}>{label ? `${label} ` : ""}{short}</code>;
}
```

`StatusBadge.tsx`:

```tsx
import type { RuntimeStatus } from "../statusModel";

export function StatusBadge({ status }: { status: RuntimeStatus }) {
  return <span className={`statusBadge status-${status.color}`}>{status.label}</span>;
}
```

- [ ] **Step 4: Create reusable event table**

`EventTable.tsx`:

```tsx
import type { EventRow } from "../operationsApi";

export function EventTable({ events }: { events: EventRow[] }) {
  return (
    <div className="eventFrame">
      <table className="eventTable">
        <thead>
          <tr><th>时间</th><th>类型</th><th>Actor</th><th>目标</th><th>摘要</th></tr>
        </thead>
        <tbody>
          {events.map((event) => (
            <tr key={event.id}>
              <td>{event.time ? new Date(event.time).toLocaleTimeString() : "--:--:--"}</td>
              <td>{event.type}</td>
              <td>{event.source}</td>
              <td>{event.affectedAgents[0] || "无"}</td>
              <td>{event.text}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
```

- [ ] **Step 5: Build frontend**

Run:

```powershell
npm --prefix frontend run build
```

Expected: Vite build exits `0`.

## Gate A: Contract QA

**Assignee:** `runtime-qa`

- [ ] Run:

```powershell
pytest tests/test_communication_projection.py tests/test_artifact_manifests.py tests/test_server.py tests/test_tasks_gates_reviews.py -q
npm --prefix frontend run build
```

- [ ] Verify:
  - No Home global rate metric exists in frontend code.
  - Red/gray state distinction is implemented in `statusModel.ts`.
  - Communication message projection is Bus-backed.
  - Artifact manifest API cannot escape artifact root.
  - Old hidden-conversation claims are not rendered in normal UI.

Gate A passes only when every command exits `0`.

## Wave B: Page Implementation

### Task B1: Worker1 Home And App Shell

**Assignee:** `runtime-worker-1`

**Files:**
- Modify: `frontend/src/operationsApi.ts`
- Modify: `frontend/src/App.tsx`
- Create: `frontend/src/pages/HomePage.tsx`
- Create: `frontend/src/components/ActionDrawer.tsx`

- [ ] **Step 1: Replace ViewName with MVP routes**

In `operationsApi.ts`:

```ts
export type ViewName =
  | "Home"
  | "Communication"
  | "Runs"
  | "Gates"
  | "Artifacts"
  | "Diagnostics"
  | "Settings";
```

- [ ] **Step 2: Reduce App to routing shell**

In `App.tsx`, keep data loading and route state; move page bodies into `frontend/src/pages/*`.

The `views` array must be:

```ts
const views: ViewName[] = ["Home", "Communication", "Runs", "Gates", "Artifacts", "Diagnostics", "Settings"];
```

- [ ] **Step 3: Create HomePage three-section layout**

Create `HomePage.tsx` with:

```tsx
export function HomePage({ room, projection, onOpenAction, onViewChange }: HomePageProps) {
  return (
    <section className="homePage">
      <RuntimePosture room={room} projection={projection} />
      <WorkflowSubway room={room} projection={projection} onOpenAction={onOpenAction} />
      <ActionQueue room={room} projection={projection} onOpenAction={onOpenAction} onViewChange={onViewChange} />
    </section>
  );
}
```

Runtime posture must show only current Run, runtime state, action-required count, open gate count, and last sync time. It must not show success-rate-like metrics.

- [ ] **Step 4: Add action drawer**

Create `ActionDrawer.tsx`. It must support at least:

```tsx
export type ActionDrawerItem = {
  kind: "task" | "gate" | "message" | "artifact";
  id: string;
  title: string;
  runId?: string;
  taskId?: string;
  suggestedActions: Array<"message_controller" | "reassign" | "request_qa" | "open_gate" | "view_artifact" | "mark_known">;
};
```

The drawer must call a Bus-backed submit handler rather than opening a detached command field.

- [ ] **Step 5: Verify Home**

Run:

```powershell
npm --prefix frontend run build
```

Expected: build exits `0`; Home code contains no `successRate` identifier.

### Task B2: Worker2 Communication Console

**Assignee:** `runtime-worker-2`

**Files:**
- Modify: `frontend/src/operationsApi.ts`
- Create: `frontend/src/pages/CommunicationPage.tsx`
- Create: `frontend/src/components/AgentMark.tsx`
- Create: `frontend/src/components/DetailRail.tsx`

- [ ] **Step 1: Add message API client types**

In `operationsApi.ts`, add:

```ts
export type BusMessageRow = {
  messageId: string;
  busEventId: string;
  threadId: string;
  spaceId: string;
  senderAgentId: string;
  senderName: string;
  senderRoles: string[];
  recipientAgentIds: string[];
  messageType: string;
  deliveryState: string;
  ackState: string;
  replyState: string;
  priority: string;
  body: string;
  links: {
    runId?: string;
    taskIds: string[];
    gateIds: string[];
    artifactIds: string[];
  };
  createdAt: string;
  updatedAt: string;
};
```

Add `fetchBusMessages()` and `sendBusMessage()` wrappers for `/api/projections/messages` and `/api/messages/send`.

- [ ] **Step 2: Build three-zone Communication page**

`CommunicationPage.tsx` must render:

```tsx
<section className="communicationPage">
  <aside className="communicationLeftRail">...</aside>
  <section className="communicationStream">...</section>
  <DetailRail mode={selectedMessage ? "message" : "agent"} ... />
</section>
```

Left rail: spaces, thread groups, Agent list. Center rail: message cards and bottom composer. Right rail: Agent detail or message detail.

- [ ] **Step 3: Implement Bus-backed composer**

Composer submit payload:

```ts
await sendBusMessage({
  actor: "operator",
  text: message,
  recipient_agent_ids: selectedRecipients,
  run_id: linkedRunId,
  task_id: linkedTaskId,
  gate_id: linkedGateId,
  message_type: selectedMessageType,
  priority: selectedPriority,
});
```

The UI must label this as sending through Agent Bus.

- [ ] **Step 4: Verify Communication**

Run:

```powershell
npm --prefix frontend run build
```

Expected: build exits `0`; Communication page contains no raw event table and no detached command console.

### Task B3: Worker3 Runs, Gates, And Artifacts

**Assignee:** `runtime-worker-3`

**Files:**
- Create: `frontend/src/pages/RunsPage.tsx`
- Create: `frontend/src/pages/GatesPage.tsx`
- Create: `frontend/src/pages/ArtifactsPage.tsx`
- Modify: `frontend/src/operationsApi.ts`

- [ ] **Step 1: Add artifact manifest client**

In `operationsApi.ts`, add:

```ts
export type ArtifactManifestRow = {
  artifactId: string;
  runId: string;
  taskId: string;
  agentId: string;
  type: string;
  title: string;
  path: string;
  createdAt: string;
  summary: string;
};

export async function fetchArtifactManifests(signal?: AbortSignal): Promise<ArtifactManifestRow[]> {
  const response = await fetch("/api/artifacts/manifests", { headers: { Accept: "application/json" }, signal });
  if (!response.ok) throw new Error(`GET /api/artifacts/manifests returned ${response.status}`);
  const payload = await response.json();
  return (payload.artifacts || []).map((item: Record<string, unknown>) => ({
    artifactId: String(item.artifact_id || ""),
    runId: String(item.run_id || ""),
    taskId: String(item.task_id || ""),
    agentId: String(item.agent_id || ""),
    type: String(item.type || "artifact"),
    title: String(item.title || item.artifact_id || "产物"),
    path: String(item.path || ""),
    createdAt: String(item.created_at || ""),
    summary: String(item.summary || ""),
  }));
}
```

- [ ] **Step 2: Build RunsPage detail view**

`RunsPage.tsx` must show:

- Run Summary.
- Agent Assignment.
- Task Lane.
- Gate Lane.
- Artifact Lane.
- Run-scoped Event Timeline.

The page must not use static `created / queued / working / gate / review / done` labels unless derived from real task/gate/event state.

- [ ] **Step 3: Build GatesPage approval center**

`GatesPage.tsx` must focus on decision-required gates only. Each gate card must show owner, requester, decision maker, risk, state, reason, and linked run/task. If no owner exists and a QA agent exists, display the QA agent as projected owner.

- [ ] **Step 4: Build ArtifactsPage from manifests**

`ArtifactsPage.tsx` must display manifest-backed screenshots, reports, handoff documents, and logs. Empty state must tell agents where to write manifest files:

```text
.agent-bus/artifacts/<run_id>/<task_id>/manifest.json
```

- [ ] **Step 5: Verify pages**

Run:

```powershell
npm --prefix frontend run build
```

Expected: build exits `0`; `RunGraph` static stage list is gone or replaced by real run detail.

### Task B4: Worker4 Diagnostics And Visual System

**Assignee:** `runtime-worker-4`

**Files:**
- Create: `frontend/src/pages/DiagnosticsPage.tsx`
- Modify: `frontend/src/main.tsx`
- Create: `frontend/src/styles/base.css`
- Create: `frontend/src/styles/layout.css`
- Create: `frontend/src/styles/pages.css`
- Modify: `frontend/src/styles.css`

- [ ] **Step 1: Split CSS imports**

In `main.tsx`, replace:

```ts
import "./styles.css";
```

with:

```ts
import "./styles/base.css";
import "./styles/layout.css";
import "./styles/pages.css";
```

Keep `styles.css` only as a temporary compatibility file if other imports require it.

- [ ] **Step 2: Define state color tokens**

In `base.css`, add:

```css
:root {
  --status-green: #1f9d55;
  --status-yellow: #b7791f;
  --status-red: #c53030;
  --status-gray: #718096;
  --status-purple: #6b46c1;
  --action-blue: #2563eb;
  --surface-app: #f5f7fb;
  --surface-panel: #ffffff;
  --line-soft: #d9e2ef;
  --text-strong: #0f172a;
  --text-muted: #526179;
}
```

- [ ] **Step 3: Add no-overlap layout rules**

In `layout.css`, add constraints for shell, sidebar, page grids, fixed event frames, and right rails. At `max-width: 1100px`, page grids must stack rather than overflow horizontally.

- [ ] **Step 4: Build DiagnosticsPage**

`DiagnosticsPage.tsx` must show raw protocol events in a fixed-height scroll frame and should include session fencing, stale events, protocol warnings, and raw event filters. It is allowed to show advanced runtime diagnostics, but not as Home/Communication primary content.

- [ ] **Step 5: Verify visual system**

Run:

```powershell
npm --prefix frontend run build
```

Expected: build exits `0`; CSS contains one stable status color mapping; blue is used for primary actions, not generic status.

## Gate B: Page QA

**Assignee:** `runtime-qa`

- [ ] Start service:

```powershell
npm --prefix frontend run build
python -m agent_bus serve --db coordination\live-agent-bus.sqlite3 --host 127.0.0.1 --port 8787
```

- [ ] Open `http://127.0.0.1:8787/` in the in-app browser.
- [ ] Capture desktop screenshot at `1183x702`.
- [ ] Verify:
  - Sidebar routes are `控制首页`, `通信`, `任务流`, `门禁`, `产物`, `诊断`, `设置`.
  - Home has three sections and no global rate-like metric.
  - Communication has left spaces, center messages, right detail rail, and Bus-backed composer.
  - Runs page has run summary, assignments, tasks, gates, artifacts, scoped events.
  - Gates page is an approval center, not a duplicate Home.
  - Artifacts page reads manifest-backed outputs.
  - Diagnostics owns the raw event log.
  - Old global Inspector, old replacement dock, and old command console are gone from normal pages.
  - No element overlap at `1183x702`.

Gate B passes only after QA records screenshot paths and command output in `coordination/frontend-product-restructure-wave-board.md`.

## Wave C: Integration Fixes And Regression

### Task C1: Worker1 Shell Integration

**Assignee:** `runtime-worker-1`

**Files:**
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/pages/HomePage.tsx`

- [ ] Wire Home action drawer to `sendBusMessage`.
- [ ] Ensure page-specific headers replace the old global heavy header.
- [ ] Ensure Home action items navigate to the correct detail page after submit.
- [ ] Run `npm --prefix frontend run build`.

### Task C2: Worker2 Message Delivery Regression

**Assignee:** `runtime-worker-2`

**Files:**
- Modify: `agent_bus/projections.py`
- Modify: `frontend/src/pages/CommunicationPage.tsx`
- Test: `tests/test_communication_projection.py`

- [ ] Add tests for `delivered`, `acked`, and `waiting_reply`.
- [ ] Ensure Communication cards render these states from projection data.
- [ ] Run `pytest tests/test_communication_projection.py -q`.
- [ ] Run `npm --prefix frontend run build`.

### Task C3: Worker3 Run Created-State Bug Investigation

**Assignee:** `runtime-worker-3`

**Files:**
- Modify: `agent_bus/projections.py`
- Modify: `frontend/src/pages/RunsPage.tsx`
- Test: `tests/test_server.py`

- [ ] Add a test where a run has task events beyond `created`.
- [ ] Confirm projection exposes current task states and replay state.
- [ ] Fix projection or UI join so Runs page does not show all runs as `已创建` when task events progressed.
- [ ] Run `pytest tests/test_server.py -q`.

### Task C4: Worker4 Responsive And Icon Polish

**Assignee:** `runtime-worker-4`

**Files:**
- Modify: `frontend/src/components/AgentMark.tsx`
- Modify: `frontend/src/styles/base.css`
- Modify: `frontend/src/styles/layout.css`
- Modify: `frontend/src/styles/pages.css`

- [ ] Use lucide icons or compact pixel-style marks for role recognition:
  - Controller: dispatcher / command mark.
  - Worker: tool mark.
  - QA: shield / magnifier.
  - Helper: plugin / circuit mark.
  - Observer: archive / eye mark.
- [ ] Keep icons readable at `32px`.
- [ ] Run `npm --prefix frontend run build`.
- [ ] Capture desktop and narrow screenshots through browser.

## Gate C: Final QA And Handoff

**Assignee:** `runtime-qa`

- [ ] Run all backend tests:

```powershell
pytest -q
```

- [ ] Run frontend build:

```powershell
npm --prefix frontend run build
```

- [ ] Run local service:

```powershell
python -m agent_bus serve --db coordination\live-agent-bus.sqlite3 --host 127.0.0.1 --port 8787
```

- [ ] Browser verification at `http://127.0.0.1:8787/`:
  - Desktop `1183x702`.
  - Narrow width around `390px`.
  - Each route loads.
  - Main canvas is nonblank.
  - Text does not overlap.
  - Fixed event frames scroll internally.
  - Action-required items open action exits.
  - Communication composer sends through Bus API.
  - Artifact page shows manifest fixtures.

- [ ] Write final QA artifact:

```text
coordination/frontend-product-restructure-final-qa.md
```

It must include command outputs, screenshots, unresolved issues, and a pass/fail decision.

## Self-Review Checklist

- Every page has one distinct job.
- Home has no global success-rate metric.
- Red never means normal not-started state.
- Old global Inspector is removed; page-scoped detail rails remain.
- Old global Command Console is removed; Bus-backed composers remain.
- No hidden Codex conversation-internal scores appear in normal UI.
- Communication and Diagnostics are separate.
- Artifacts use manifest files under a safe root.
- Gate owners prefer QA role when derivable.
- Run details use actual task/gate/artifact/event data.
- QA gates block wave advancement.
