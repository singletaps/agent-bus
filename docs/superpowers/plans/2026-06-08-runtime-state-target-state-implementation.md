# Runtime State Target State Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement the runtime-state target model from `docs/runtime-state-target-state.md` so stale temporary agents, session authority, workload responsibility, inbox relevance, gate relevance, and UI visibility are derived from explicit orthogonal policy axes instead of overloaded `runtime_state`.

**Architecture:** Keep SQLite and the append-only event log as durable truth. Add explicit model contracts and projection-only policy outputs first, then integrate them through the existing `ProjectionReader`/`derive_relevance_projection` path. The frontend must consume backend projection fields and must not infer lifecycle, freshness, authority, inbox relevance, or gate relevance locally.

**Tech Stack:** Python 3, SQLite, Pydantic, pytest, FastAPI projection API, TypeScript, React, Vite.

---

## Controller Protocol

Controller identity: `runtime-controller`.

Broker: `http://127.0.0.1:8765`.

Bus file: `coordination/agent-bus.ndjson`.

Each worker must use broker-first communication and send the exact READY signal for its assignment. Controller keeps the next wave closed until all required READY signals are independently verified.

Required signals:

- `WAVE10_A1_READY runtime-worker-5`
- `WAVE10_A2_READY runtime-worker-7`
- `WAVE10_A3_READY runtime-worker-6`
- `WAVE10_B1_READY runtime-worker-5`
- `WAVE10_B2_READY runtime-worker-7`
- `WAVE10_C1_READY runtime-worker-6`
- `WAVE10_C2_READY runtime-worker-4`

Gate broadcasts:

- `GATE_WAVE10_A_PASS` after A1/A2/A3 pass.
- `GATE_WAVE10_B_PASS` after B1/B2 pass.
- `GATE_WAVE10_C_PASS` after C1/C2 and final browser/API checks pass.

Controller verification commands:

```powershell
python -m pytest tests/test_runtime_state_contracts.py tests/test_runtime_state_policy.py tests/test_operations_relevance_api.py -q
python -m pytest tests/test_server.py tests/test_relevance_projection.py tests/test_live_protocol_simulation.py -q
python -m pytest -q
cd frontend; npm run build
git diff --check -- agent_bus frontend/src tests docs
```

Do not mark a wave passed from worker reports alone.

## Root Cause And Invariant

Root cause: state-axis collapse. The current code uses `AgentRuntimeState` as activity, lifecycle, stale-health fallback, workload label, and UI visibility input. This caused old Sim2 temporary agents to remain visible because stale or offline identities were retained by role strings, old reassigned tasks, and queued inbox counts.

Invariant to preserve:

```text
runtime_state describes session activity/health only.
identity lifecycle, session authority, presence, workload, inbox relevance,
gate relevance, and UI visibility are separate projection axes.
```

Frontend invariant:

```text
React pages render explicit backend projection fields.
They do not decide protocol state, archive eligibility, stale ownership,
inbox lease expiry, gate relevance, or replacement authority.
```

## File Responsibility Map

Modify:

- `agent_bus/models.py`: public enum/model contracts such as identity lifecycle, presence, UI visibility, inbox relevance, gate relevance, conditions, and session end reason.
- `agent_bus/migrations.py`: idempotent schema additions for identity metadata and session end reason.
- `agent_bus/agents.py`: row mapping/persistence for new identity/session fields; narrow transition helpers.
- `agent_bus/runtime_state.py`: new runtime policy module for freshness, presence, conditions, and transition validation.
- `agent_bus/relevance.py`: relevance policy for identity lifecycle, workload, inbox, gate, UI visibility, and hidden counts.
- `agent_bus/projections.py`: compose runtime policy and relevance outputs into API/operations UI projection.
- `agent_bus/inbox.py`: expose lease/revocation facts in relevance-friendly form; do not hide expired leases in read paths.
- `agent_bus/server.py`: heartbeat contract guard so heartbeat cannot move a session to `WORKING` without valid workload evidence.
- `frontend/src/operationsApi.ts`: normalize new backend projection fields.
- `frontend/src/operationsRoomModel.ts`: consume normalized visibility/workload fields.
- `frontend/src/pages/CommunicationPage.tsx`: active/archive/attention roster rendering.
- `frontend/src/pages/GatesPage.tsx`: approval center uses gate relevance and visibility.
- `frontend/src/pages/HomePage.tsx`: metrics/action items use explicit projections.
- `frontend/src/pages/DiagnosticsPage.tsx`: expose hidden/history/condition details.
- `frontend/src/styles.css`: minimal style support for new labels and attention groups.

Create:

- `tests/test_runtime_state_contracts.py`
- `tests/test_runtime_state_policy.py`
- `tests/test_inbox_relevance.py`

Update:

- `tests/test_operations_relevance_api.py`
- `tests/test_relevance_projection.py`
- `tests/test_server.py`
- `docs/runtime-state-current-state.md` if current-state notes need a short migration appendix.

## Wave 10 A: Parallel Contract And Policy Foundation

### Task A1: Model Contracts And Migrations

Owner: `runtime-worker-5`.

Write scope:

- `agent_bus/models.py`
- `agent_bus/migrations.py`
- `agent_bus/agents.py`
- `tests/test_runtime_state_contracts.py`
- `tests/test_migrations.py`

Ready signal: `WAVE10_A1_READY runtime-worker-5`.

- [ ] **Step 1: Write contract tests first**

Create `tests/test_runtime_state_contracts.py`:

```python
from agent_bus.agents import AgentDirectory
from agent_bus.models import (
    AgentIdentityLifecycle,
    IdentityOrigin,
    PresenceState,
    RuntimeCondition,
    SessionEndReason,
    UIVisibilityState,
    VisibilityPolicy,
)


def test_identity_target_metadata_defaults_and_round_trips(tmp_path):
    db_path = tmp_path / "agent-bus.sqlite3"
    directory = AgentDirectory(db_path=db_path)
    identity = directory.register_identity("sim2-qa", role="qa", display_name="Sim2 QA")

    assert identity.identity_lifecycle is AgentIdentityLifecycle.ACTIVE
    assert identity.identity_origin is IdentityOrigin.RUNTIME_DISCOVERED
    assert identity.visibility_policy is VisibilityPolicy.NORMAL
    assert identity.canonical is False
    assert identity.archive_reason is None

    reloaded = AgentDirectory(db_path=db_path).get_identity("sim2-qa")
    assert reloaded.identity_lifecycle is AgentIdentityLifecycle.ACTIVE
    assert reloaded.identity_origin is IdentityOrigin.RUNTIME_DISCOVERED
    assert reloaded.visibility_policy is VisibilityPolicy.NORMAL
    assert reloaded.canonical is False


def test_session_end_reason_round_trips(tmp_path):
    db_path = tmp_path / "agent-bus.sqlite3"
    directory = AgentDirectory(db_path=db_path)
    directory.register_identity("worker")
    session = directory.start_session("worker", session_id="session-worker")

    directory.retire_session(
        session.session_id,
        end_reason=SessionEndReason.EXPIRED,
        reason="heartbeat expired with no responsibility",
    )

    reloaded = AgentDirectory(db_path=db_path).get_session(session.session_id)
    assert reloaded.active is False
    assert reloaded.session_end_reason is SessionEndReason.EXPIRED
    assert reloaded.ended_at is not None


def test_runtime_condition_contract_is_stable():
    condition = RuntimeCondition(
        type="Reachable",
        status="false",
        reason="missing_heartbeat",
        message="last heartbeat exceeded hard timeout",
        severity="warning",
        source="runtime_state_policy",
    )

    dumped = condition.model_dump(mode="json")
    assert dumped["type"] == "Reachable"
    assert dumped["status"] == "false"
    assert dumped["severity"] == "warning"
    assert dumped["source"] == "runtime_state_policy"


def test_projection_enum_values_match_target_doc():
    assert PresenceState.ONLINE.value == "online"
    assert PresenceState.STALE.value == "stale"
    assert PresenceState.OFFLINE.value == "offline"
    assert UIVisibilityState.NEEDS_ATTENTION.value == "needs_attention"
```

- [ ] **Step 2: Verify the tests fail**

Run:

```powershell
python -m pytest tests/test_runtime_state_contracts.py -q
```

Expected: FAIL because the target enums, identity fields, and `retire_session` helper do not exist.

- [ ] **Step 3: Add model contracts**

Modify `agent_bus/models.py` by adding these enums and model near the existing model declarations:

```python
class AgentIdentityLifecycle(str, Enum):
    ACTIVE = "active"
    DORMANT = "dormant"
    ARCHIVED = "archived"
    RETIRED = "retired"


class IdentityOrigin(str, Enum):
    SYSTEM = "system"
    USER_REGISTERED = "user_registered"
    RUNTIME_DISCOVERED = "runtime_discovered"
    SIMULATION = "simulation"
    TEMPORARY = "temporary"
    IMPORTED = "imported"


class VisibilityPolicy(str, Enum):
    SYSTEM_CRITICAL = "system_critical"
    NORMAL = "normal"
    EPHEMERAL = "ephemeral"
    HIDDEN_BY_DEFAULT = "hidden_by_default"


class SessionEndReason(str, Enum):
    REPLACED = "replaced"
    RETIRED = "retired"
    EXPIRED = "expired"
    NORMAL_SHUTDOWN = "normal_shutdown"
    USER_ARCHIVED = "user_archived"
    PROTOCOL_VIOLATION = "protocol_violation"


class PresenceState(str, Enum):
    ONLINE = "online"
    STALE = "stale"
    OFFLINE = "offline"
    UNKNOWN = "unknown"


class WorkloadState(str, Enum):
    FREE = "free"
    ASSIGNED = "assigned"
    WORKING = "working"
    WAITING_INPUT = "waiting_input"
    CLAIM_PENDING = "claim_pending"
    WAITING_REVIEW = "waiting_review"
    WAITING_GATE = "waiting_gate"
    BLOCKED = "blocked"
    HISTORICAL = "historical"


class InboxRelevanceState(str, Enum):
    DELIVERABLE = "deliverable"
    DELIVERED = "delivered"
    LEASE_EXPIRED = "lease_expired"
    REVOKED = "revoked"
    REASSIGNED = "reassigned"
    ORPHANED = "orphaned"
    DIAGNOSTICS_ONLY = "diagnostics_only"


class GateRelevanceState(str, Enum):
    ACTIONABLE = "actionable"
    WAITING_EVIDENCE = "waiting_evidence"
    WAITING_OWNER = "waiting_owner"
    SUPERSEDED = "superseded"
    HISTORICAL = "historical"
    ORPHANED = "orphaned"
    DIAGNOSTICS_ONLY = "diagnostics_only"


class UIVisibilityState(str, Enum):
    MAIN = "main"
    SECONDARY = "secondary"
    NEEDS_ATTENTION = "needs_attention"
    APPROVAL_CENTER = "approval_center"
    DIAGNOSTICS = "diagnostics"
    HISTORY = "history"
    HIDDEN = "hidden"


class RuntimeCondition(BaseModel):
    type: str
    status: str
    reason: str
    message: str | None = None
    severity: str = "info"
    source: str
    last_transition_at: str = Field(default_factory=utc_now_iso)
    observed_generation: int | None = None
```

Extend `AgentIdentity`:

```python
    canonical: bool = False
    identity_origin: IdentityOrigin = IdentityOrigin.RUNTIME_DISCOVERED
    visibility_policy: VisibilityPolicy = VisibilityPolicy.NORMAL
    identity_lifecycle: AgentIdentityLifecycle = AgentIdentityLifecycle.ACTIVE
    archive_reason: str | None = None
```

Extend `AgentSession`:

```python
    session_end_reason: SessionEndReason | str | None = None
```

- [ ] **Step 4: Add migrations**

Modify `agent_bus/migrations.py`:

```python
    def _migrate_agent_identities(self) -> None:
        if not self.has_table("agent_identities"):
            return
        for definition in (
            "canonical integer not null default 0",
            "identity_origin text not null default 'runtime_discovered'",
            "visibility_policy text not null default 'normal'",
            "identity_lifecycle text not null default 'active'",
            "archive_reason text",
        ):
            self.add_column_if_missing("agent_identities", definition)
```

Call `_migrate_agent_identities()` in `run()` before `_migrate_agent_sessions()`.

Add to `_migrate_agent_sessions()`:

```python
            "session_end_reason text",
```

- [ ] **Step 5: Update AgentDirectory persistence**

Modify `agent_bus/agents.py` row loaders and inserts so new fields round-trip. Add a helper:

```python
    def retire_session(
        self,
        session_id: str,
        *,
        end_reason: SessionEndReason | str,
        reason: str | None = None,
    ) -> AgentHealth:
        session = self._require_session(session_id)
        session.active = False
        session.ended_at = utc_now_iso()
        session.session_end_reason = SessionEndReason(end_reason)
        self._persist_session(session)
        health = self._health_for(session, reason=reason or f"session {session.session_end_reason.value}")
        self._health_by_session[session_id] = health
        self._persist_health(health)
        return health
```

Update `replace_session()` and `replace_with_session()` to set `old_session.session_end_reason = SessionEndReason.REPLACED`.

- [ ] **Step 6: Verify A1 tests**

Run:

```powershell
python -m pytest tests/test_runtime_state_contracts.py tests/test_migrations.py -q
```

Expected: PASS.

### Task A2: Runtime Policy Module

Owner: `runtime-worker-7`.

Write scope:

- `agent_bus/runtime_state.py`
- `tests/test_runtime_state_policy.py`

Ready signal: `WAVE10_A2_READY runtime-worker-7`.

- [ ] **Step 1: Write policy tests first**

Create `tests/test_runtime_state_policy.py`:

```python
from datetime import datetime, timedelta, timezone

from agent_bus.models import AgentRuntimeState, PresenceState
from agent_bus.runtime_state import (
    FreshnessThresholds,
    RuntimeFacts,
    derive_presence_state,
    derive_runtime_activity,
    validate_heartbeat_runtime_transition,
)


def iso_age(seconds: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(seconds=seconds)).isoformat().replace("+00:00", "Z")


def test_rehydrating_times_out_to_suspected_stuck():
    facts = RuntimeFacts(
        runtime_state=AgentRuntimeState.REHYDRATING,
        last_seen_at=iso_age(900),
        active=True,
        ended_at=None,
        has_active_responsibility=True,
    )

    result = derive_runtime_activity(facts, FreshnessThresholds(stale_seconds=300, archive_seconds=3600))

    assert result.runtime_state is AgentRuntimeState.SUSPECTED_STUCK
    assert result.presence_state is PresenceState.STALE
    assert result.conditions["Reachable"].status == "false"
    assert result.conditions["ReplacementRecommended"].status == "true"


def test_stale_standby_without_responsibility_is_offline_not_main_roster_health():
    facts = RuntimeFacts(
        runtime_state=AgentRuntimeState.STANDBY_READY,
        last_seen_at=iso_age(7200),
        active=True,
        ended_at=None,
        has_active_responsibility=False,
    )

    result = derive_runtime_activity(facts, FreshnessThresholds(stale_seconds=300, archive_seconds=3600))

    assert result.runtime_state is AgentRuntimeState.STANDBY_DEGRADED
    assert result.presence_state is PresenceState.OFFLINE
    assert result.conditions["HasActiveWork"].status == "false"


def test_heartbeat_cannot_unilaterally_set_working_without_binding():
    ok, reason = validate_heartbeat_runtime_transition(
        current=AgentRuntimeState.STANDBY_READY,
        requested=AgentRuntimeState.WORKING,
        has_valid_work_binding=False,
        has_progress_evidence=False,
    )

    assert ok is False
    assert reason == "working_requires_valid_work_binding"
```

- [ ] **Step 2: Verify tests fail**

Run:

```powershell
python -m pytest tests/test_runtime_state_policy.py -q
```

Expected: FAIL because `agent_bus.runtime_state` does not exist.

- [ ] **Step 3: Implement policy module**

Create `agent_bus/runtime_state.py`:

```python
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from .models import AgentRuntimeState, PresenceState, RuntimeCondition, utc_now_iso


@dataclass(frozen=True)
class FreshnessThresholds:
    stale_seconds: float = 300.0
    archive_seconds: float = 3600.0


@dataclass(frozen=True)
class RuntimeFacts:
    runtime_state: AgentRuntimeState
    last_seen_at: str | None
    active: bool
    ended_at: str | None
    has_active_responsibility: bool


@dataclass(frozen=True)
class RuntimeActivityProjection:
    runtime_state: AgentRuntimeState
    presence_state: PresenceState
    stale: bool
    reason: str
    health_score: float
    conditions: dict[str, RuntimeCondition]


ACTIVE_TIMEOUT_STATES = {
    AgentRuntimeState.DELIVERED_NOT_ACKED,
    AgentRuntimeState.WORKING,
    AgentRuntimeState.REHYDRATING,
    AgentRuntimeState.WAITING_FOR_COMMIT,
    AgentRuntimeState.WAITING_FOR_REVIEW,
    AgentRuntimeState.WAITING_FOR_GATE,
}

STANDBY_TIMEOUT_STATES = {
    AgentRuntimeState.STANDBY_READY,
    AgentRuntimeState.WAITING_ON_BUS,
    AgentRuntimeState.WAIT_RETURNED_NOOP,
}


def derive_presence_state(last_seen_at: str | None, thresholds: FreshnessThresholds) -> PresenceState:
    age = age_seconds(last_seen_at)
    if age is None:
        return PresenceState.UNKNOWN
    if age <= thresholds.stale_seconds:
        return PresenceState.ONLINE
    if age <= thresholds.archive_seconds:
        return PresenceState.STALE
    return PresenceState.OFFLINE


def derive_runtime_activity(facts: RuntimeFacts, thresholds: FreshnessThresholds) -> RuntimeActivityProjection:
    presence = PresenceState.OFFLINE if not facts.active or facts.ended_at else derive_presence_state(facts.last_seen_at, thresholds)
    state = facts.runtime_state
    stale = presence in {PresenceState.STALE, PresenceState.OFFLINE}
    reason = "fresh"

    if stale and facts.has_active_responsibility and state in ACTIVE_TIMEOUT_STATES:
        state = AgentRuntimeState.SUSPECTED_STUCK
        reason = "active_responsibility_missing_heartbeat"
    elif stale and not facts.has_active_responsibility and state in STANDBY_TIMEOUT_STATES:
        state = AgentRuntimeState.STANDBY_DEGRADED
        reason = "standby_missing_heartbeat"
    elif stale:
        reason = "missing_heartbeat"

    health_score = _health_score(state, stale)
    conditions = _conditions(
        presence_state=presence,
        runtime_state=state,
        has_active_responsibility=facts.has_active_responsibility,
        reason=reason,
    )
    return RuntimeActivityProjection(
        runtime_state=state,
        presence_state=presence,
        stale=stale,
        reason=reason,
        health_score=health_score,
        conditions=conditions,
    )


def validate_heartbeat_runtime_transition(
    *,
    current: AgentRuntimeState,
    requested: AgentRuntimeState | None,
    has_valid_work_binding: bool,
    has_progress_evidence: bool,
) -> tuple[bool, str]:
    if requested is None or requested is current:
        return True, "heartbeat_refresh"
    if requested is AgentRuntimeState.WORKING and not (has_valid_work_binding or has_progress_evidence):
        return False, "working_requires_valid_work_binding"
    return True, "heartbeat_state_refresh"


def age_seconds(value: str | None) -> float | None:
    if value is None:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return max(0.0, (datetime.now(timezone.utc) - parsed).total_seconds())


def _condition(type: str, status: str, reason: str, severity: str, message: str | None = None) -> RuntimeCondition:
    return RuntimeCondition(
        type=type,
        status=status,
        reason=reason,
        message=message,
        severity=severity,
        source="runtime_state_policy",
        last_transition_at=utc_now_iso(),
    )


def _conditions(
    *,
    presence_state: PresenceState,
    runtime_state: AgentRuntimeState,
    has_active_responsibility: bool,
    reason: str,
) -> dict[str, RuntimeCondition]:
    reachable = "true" if presence_state is PresenceState.ONLINE else "false"
    stuck = runtime_state is AgentRuntimeState.SUSPECTED_STUCK
    return {
        "Ready": _condition("Ready", "false" if stuck else "true", reason, "warning" if stuck else "info"),
        "Reachable": _condition("Reachable", reachable, reason, "warning" if reachable == "false" else "info"),
        "HasActiveWork": _condition("HasActiveWork", "true" if has_active_responsibility else "false", reason, "info"),
        "ReplacementRecommended": _condition(
            "ReplacementRecommended",
            "true" if stuck else "false",
            reason,
            "warning" if stuck else "info",
        ),
    }


def _health_score(runtime_state: AgentRuntimeState, stale: bool) -> float:
    if runtime_state is AgentRuntimeState.SUSPECTED_STUCK:
        return 0.30
    if runtime_state is AgentRuntimeState.STANDBY_DEGRADED:
        return 0.55
    if stale:
        return 0.50
    return 1.00
```

- [ ] **Step 4: Verify A2 tests**

Run:

```powershell
python -m pytest tests/test_runtime_state_policy.py -q
```

Expected: PASS.

### Task A3: Frontend Contract Preparation

Owner: `runtime-worker-6`.

Write scope:

- `frontend/src/operationsApi.ts`
- no page behavior changes until `GATE_WAVE10_B_PASS`

Ready signal: `WAVE10_A3_READY runtime-worker-6`.

- [ ] **Step 1: Add TypeScript types for target projection fields**

Modify `frontend/src/operationsApi.ts` with these target shape types:

```ts
export type RuntimeCondition = {
  type: string;
  status: "true" | "false" | "unknown" | string;
  reason: string;
  message: string | null;
  severity: "info" | "warning" | "error" | "critical" | string;
  source: string;
  lastTransitionAt: string;
  observedGeneration: number | null;
};

export type RuntimePresenceState = "online" | "stale" | "offline" | "unknown" | string;
export type RuntimeWorkloadState =
  | "free"
  | "assigned"
  | "working"
  | "waiting_input"
  | "claim_pending"
  | "waiting_review"
  | "waiting_gate"
  | "blocked"
  | "historical"
  | string;
export type RuntimeUiVisibilityState =
  | "main"
  | "secondary"
  | "needs_attention"
  | "approval_center"
  | "diagnostics"
  | "history"
  | "hidden"
  | string;
```

Extend `UiAgentSummary`:

```ts
  identityLifecycle: string;
  presenceState: RuntimePresenceState;
  workloadState: RuntimeWorkloadState;
  uiVisibilityState: RuntimeUiVisibilityState;
  conditions: RuntimeCondition[];
  hiddenReason: string;
```

Extend gate projection normalization with:

```ts
  relevanceState: string;
  uiVisibilityState: RuntimeUiVisibilityState;
  relevanceReason: string;
```

- [ ] **Step 2: Normalize missing fields safely**

Add helpers:

```ts
function normalizeRuntimeCondition(condition: UnknownRecord): RuntimeCondition {
  return {
    type: pickString(condition, ["type"]) || "Unknown",
    status: pickString(condition, ["status"]) || "unknown",
    reason: pickString(condition, ["reason"]) || "unspecified",
    message: pickString(condition, ["message"]) || null,
    severity: pickString(condition, ["severity"]) || "info",
    source: pickString(condition, ["source"]) || "projection",
    lastTransitionAt:
      pickString(condition, ["last_transition_at", "lastTransitionAt"]) || "",
    observedGeneration:
      pickNumber(condition, ["observed_generation", "observedGeneration"]) ?? null,
  };
}
```

Use empty strings or `unknown` only as compatibility defaults. Do not infer lifecycle from role or runtime state in the frontend.

- [ ] **Step 3: Build**

Run:

```powershell
npm run build
```

Expected: PASS. This task should not require backend fields to exist yet.

## Gate A Verification

Controller runs:

```powershell
python -m pytest tests/test_runtime_state_contracts.py tests/test_runtime_state_policy.py tests/test_migrations.py -q
cd frontend; npm run build
git diff --check -- agent_bus frontend/src tests
```

If all pass, broadcast `GATE_WAVE10_A_PASS`.

## Wave 10 B: Backend Projection And Reconciler Integration

### Task B1: Runtime Activity, Presence, Identity Lifecycle Projection

Owner: `runtime-worker-5`.

Dependency: `GATE_WAVE10_A_PASS`.

Write scope:

- `agent_bus/projections.py`
- `agent_bus/relevance.py`
- `tests/test_operations_relevance_api.py`
- `tests/test_relevance_projection.py`
- `tests/test_server.py`

Ready signal: `WAVE10_B1_READY runtime-worker-5`.

- [ ] **Step 1: Add Sim2 reproduction test**

Add to `tests/test_operations_relevance_api.py`:

```python
from datetime import datetime, timedelta, timezone

from agent_bus.agents import AgentDirectory
from agent_bus.models import AgentRuntimeState
from agent_bus.projections import build_operations_projection
from agent_bus.tasks import TaskBoard


def _old_iso(seconds: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(seconds=seconds)).isoformat().replace("+00:00", "Z")


def test_temporary_sim2_agents_archive_or_attention_by_responsibility(tmp_path):
    db_path = tmp_path / "agent-bus.sqlite3"
    directory = AgentDirectory(db_path=db_path)
    directory.register_identity("sim2-controller", role="controller")
    directory.register_identity("sim2-qa", role="qa")
    directory.register_identity("sim2-backend", role="worker")
    directory.register_identity("sim2-frontend", role="worker")
    controller_session = directory.start_session("sim2-controller", session_id="sim2-controller-session")
    qa_session = directory.start_session("sim2-qa", session_id="sim2-qa-session")
    backend_session = directory.start_session(
        "sim2-backend",
        session_id="sim2-backend-session",
        runtime_state=AgentRuntimeState.REHYDRATING,
    )
    frontend_session = directory.start_session("sim2-frontend", session_id="sim2-frontend-session")
    directory.retire_session(frontend_session.session_id, end_reason="replaced", reason="replaced by backend")

    with directory.conn:
        for session in (controller_session, qa_session, backend_session):
            directory.conn.execute(
                "update agent_sessions set last_seen_at = ? where session_id = ?",
                (_old_iso(7200), session.session_id),
            )

    board = TaskBoard(db_path=db_path)
    run = board.create_run("runtime target", objective="status lifecycle", created_by="controller")
    task = board.create_task(
        "stale backend work",
        run_id=run.run_id,
        owner_agent_id="sim2-controller",
    )
    task = board.assign_task(task.task_id, "sim2-backend", actor="controller")
    board.start_task(task.task_id, actor="sim2-backend")

    projection = build_operations_projection(db_path)
    visible_ids = {agent.agent_id for agent in projection.ui.visible_agents}
    archived_ids = {agent.agent_id for agent in projection.ui.archived_agents}
    backend = next(agent for agent in projection.ui.visible_agents if agent.agent_id == "sim2-backend")

    assert "sim2-controller" not in visible_ids
    assert "sim2-qa" not in visible_ids
    assert {"sim2-controller", "sim2-qa", "sim2-frontend"} <= archived_ids
    assert backend.presence_state == "stale"
    assert backend.runtime_state == "suspected_stuck"
    assert backend.ui_visibility_state == "needs_attention"
```

- [ ] **Step 2: Verify test fails**

Run:

```powershell
python -m pytest tests/test_operations_relevance_api.py::test_temporary_sim2_agents_archive_or_attention_by_responsibility -q
```

Expected: FAIL because Sim2 controller/qa remain visible and `REHYDRATING` is not timed out.

- [ ] **Step 3: Integrate runtime policy into projection**

Replace `_FRESHNESS_DERIVED_STATES` use in `agent_bus/projections.py` with `derive_runtime_activity()` from `agent_bus.runtime_state`.

When building `AgentProjection`, compute:

```python
has_active_responsibility = _agent_has_active_responsibility(identity.agent_id, tasks, gates, inbox)
runtime = derive_runtime_activity(
    RuntimeFacts(
        runtime_state=session.runtime_state,
        last_seen_at=session.last_seen_at,
        active=session.active,
        ended_at=session.ended_at,
        has_active_responsibility=has_active_responsibility,
    ),
    self.freshness_thresholds,
)
```

Set projected session runtime state and projected health from the runtime policy. Preserve durable session fields.

- [ ] **Step 4: Extend UI agent summary contract**

In `agent_bus/projections.py`, extend `UiAgentSummary`:

```python
    identity_lifecycle: str = ""
    presence_state: str = ""
    workload_state: str = ""
    ui_visibility_state: str = ""
    conditions: list[RuntimeCondition] = Field(default_factory=list)
    hidden_reason: str = ""
```

Populate these from `RelevanceProjection.agents[agent_id]`.

- [ ] **Step 5: Replace role-only system relevance**

In `agent_bus/relevance.py`, replace:

```python
if role_value in {"controller", "qa"}:
    return True
```

with policy based on identity metadata:

```python
def _is_system_relevant(agent: AgentProjection) -> bool:
    identity = agent.identity
    return bool(identity.canonical) or identity.visibility_policy == VisibilityPolicy.SYSTEM_CRITICAL
```

Only `runtime-controller`, `runtime-qa`, `controller`, and `user` may be treated as compatibility-canonical when the DB lacks new metadata.

- [ ] **Step 6: Verify B1 tests**

Run:

```powershell
python -m pytest tests/test_operations_relevance_api.py tests/test_relevance_projection.py tests/test_server.py -q
```

Expected: PASS.

### Task B2: Inbox, Gate Relevance, And Action Items

Owner: `runtime-worker-7`.

Dependency: `GATE_WAVE10_A_PASS`.

Write scope:

- `agent_bus/relevance.py`
- `agent_bus/inbox.py`
- `tests/test_inbox_relevance.py`
- `tests/test_relevance_projection.py`
- `tests/test_operations_relevance_api.py`

Ready signal: `WAVE10_B2_READY runtime-worker-7`.

- [ ] **Step 1: Add inbox relevance tests**

Create `tests/test_inbox_relevance.py`:

```python
from datetime import datetime, timedelta, timezone

from agent_bus.inbox import InboxStore
from agent_bus.models import InboxRelevanceState
from agent_bus.relevance import derive_inbox_relevance


def old_iso(seconds: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(seconds=seconds)).isoformat().replace("+00:00", "Z")


def test_replaced_session_queued_inbox_is_diagnostics_only(tmp_path):
    db_path = tmp_path / "agent-bus.sqlite3"
    inbox = InboxStore(db_path=db_path)
    item = inbox.enqueue("sim2-frontend", "replacement_notice", {"task_id": "task-1"})

    result = derive_inbox_relevance(
        inbox=[item],
        owner_authority_valid_by_agent={"sim2-frontend": False},
        now_iso=old_iso(0),
    )

    assert result[item.inbox_id].relevance_state is InboxRelevanceState.DIAGNOSTICS_ONLY
    assert result[item.inbox_id].blocks_identity_archive is False


def test_delivered_item_with_expired_lease_is_lease_expired(tmp_path):
    db_path = tmp_path / "agent-bus.sqlite3"
    inbox = InboxStore(db_path=db_path)
    item = inbox.enqueue("worker", "task_assigned", {"task_id": "task-1"})
    inbox.wait("worker", timeout=0, session_id="session-worker", session_epoch=1, visibility_timeout=1)
    delivered = inbox.list_items("worker")[0]
    delivered.lease_expires_at = old_iso(60)

    result = derive_inbox_relevance(
        inbox=[delivered],
        owner_authority_valid_by_agent={"worker": True},
        now_iso=old_iso(0),
    )

    assert result[delivered.inbox_id].relevance_state is InboxRelevanceState.LEASE_EXPIRED
    assert result[delivered.inbox_id].blocks_identity_archive is True
```

- [ ] **Step 2: Verify tests fail**

Run:

```powershell
python -m pytest tests/test_inbox_relevance.py -q
```

Expected: FAIL because `derive_inbox_relevance()` does not exist.

- [ ] **Step 3: Implement inbox relevance projection**

Add to `agent_bus/relevance.py`:

```python
class InboxRelevanceProjection(BaseModel):
    inbox_id: str
    agent_id: str
    relevance_state: InboxRelevanceState
    visibility: Visibility
    reason: str
    blocks_identity_archive: bool = False
```

Add:

```python
def derive_inbox_relevance(
    *,
    inbox: list[InboxItem],
    owner_authority_valid_by_agent: dict[str, bool],
    now_iso: str | None = None,
) -> dict[str, InboxRelevanceProjection]:
    now = _parse_iso(now_iso or utc_now_iso())
    result: dict[str, InboxRelevanceProjection] = {}
    for item in inbox:
        status = _normalize(item.status)
        owner_valid = owner_authority_valid_by_agent.get(item.agent_id, False)
        if item.revoked_at:
            state = InboxRelevanceState.REVOKED
            reason = "inbox_revoked"
            blocks = False
        elif status == "acked":
            state = InboxRelevanceState.DIAGNOSTICS_ONLY
            reason = "inbox_acked"
            blocks = False
        elif status == "delivered" and _iso_before(item.lease_expires_at, now):
            state = InboxRelevanceState.LEASE_EXPIRED
            reason = "lease_expired"
            blocks = owner_valid
        elif owner_valid and status in OPEN_INBOX_STATUSES:
            state = InboxRelevanceState.DELIVERABLE if status == "queued" else InboxRelevanceState.DELIVERED
            reason = "owner_authority_valid"
            blocks = True
        else:
            state = InboxRelevanceState.DIAGNOSTICS_ONLY
            reason = "owner_authority_invalid"
            blocks = False
        result[item.inbox_id] = InboxRelevanceProjection(
            inbox_id=item.inbox_id,
            agent_id=item.agent_id,
            relevance_state=state,
            visibility=Visibility.DIAGNOSTICS if not blocks else Visibility.SECONDARY,
            reason=reason,
            blocks_identity_archive=blocks,
        )
    return result
```

- [ ] **Step 4: Expand gate relevance states**

Update `GateRelevanceProjection.relevance_state` to include `waiting_evidence`, `waiting_owner`, and `diagnostics_only`. Add test cases:

```python
def test_gate_waiting_owner_when_decision_owner_stale(tmp_path):
    # Build open gate with active task and owner agent projected as stale/offline.
    # Expected: relevance_state == "waiting_owner"; visibility == "needs_attention";
    # visible_in_approval_center is False.
```

Use the existing gate/task factories in `tests/test_relevance_projection.py`.

- [ ] **Step 5: Verify B2 tests**

Run:

```powershell
python -m pytest tests/test_inbox_relevance.py tests/test_relevance_projection.py tests/test_operations_relevance_api.py -q
```

Expected: PASS.

## Gate B Verification

Controller runs:

```powershell
python -m pytest tests/test_runtime_state_contracts.py tests/test_runtime_state_policy.py tests/test_inbox_relevance.py tests/test_operations_relevance_api.py tests/test_relevance_projection.py tests/test_server.py -q
python -m pytest tests/test_live_protocol_simulation.py -q
```

If pass, broadcast `GATE_WAVE10_B_PASS`.

## Wave 10 C: Frontend Consumption And End-To-End Validation

### Task C1: Frontend Runtime Visibility Consumption

Owner: `runtime-worker-6`.

Dependency: `GATE_WAVE10_B_PASS`.

Write scope:

- `frontend/src/operationsApi.ts`
- `frontend/src/operationsRoomModel.ts`
- `frontend/src/pages/CommunicationPage.tsx`
- `frontend/src/pages/GatesPage.tsx`
- `frontend/src/pages/HomePage.tsx`
- `frontend/src/pages/DiagnosticsPage.tsx`
- `frontend/src/styles.css`

Ready signal: `WAVE10_C1_READY runtime-worker-6`.

- [ ] **Step 1: Consume explicit projection fields**

In `operationsApi.ts`, normalize backend fields exactly:

```ts
identityLifecycle: pickString(agent, ["identity_lifecycle", "identityLifecycle"]) || "active",
presenceState: pickString(agent, ["presence_state", "presenceState"]) || "unknown",
workloadState: pickString(agent, ["workload_state", "workloadState"]) || "historical",
uiVisibilityState: pickString(agent, ["ui_visibility_state", "uiVisibilityState"]) || "hidden",
conditions: toArray(firstValue(agent, ["conditions"])).map(normalizeRuntimeCondition),
hiddenReason: pickString(agent, ["hidden_reason", "hiddenReason"]) || "",
```

Do not infer `identityLifecycle` from `role`, `runtimeState`, or `stale`.

- [ ] **Step 2: Update communication roster**

`CommunicationPage.tsx` must use:

```ts
const activeAgents = projection.ui.visibleAgents.filter(
  (agent) => agent.uiVisibilityState === "main" || agent.uiVisibilityState === "needs_attention",
);
const archivedAgents = projection.ui.archivedAgents;
```

Add labels:

- `Online` for `presenceState=online`.
- `Stale` for `presenceState=stale`.
- `Offline` for `presenceState=offline`.
- `Needs attention` for `uiVisibilityState=needs_attention`.

- [ ] **Step 3: Update gates page**

`GatesPage.tsx` must show approval center records from `projection.ui.actionableGates` only. Waiting-owner gates should appear in a separate attention group, not in the default approval queue.

- [ ] **Step 4: Update diagnostics**

`DiagnosticsPage.tsx` should list hidden/archived agents and condition reasons. It must include enough text to explain why Sim2 agents are no longer in the main roster.

- [ ] **Step 5: Build**

Run:

```powershell
npm run build
```

Expected: PASS.

### Task C2: End-To-End Regression And Documentation

Owner: `runtime-worker-4`.

Dependency: `GATE_WAVE10_B_PASS`.

Write scope:

- `tests/test_live_protocol_simulation.py`
- `docs/runtime-state-target-state.md`
- `docs/runtime-state-current-state.md`
- no frontend/product code unless explicitly reassigned

Ready signal: `WAVE10_C2_READY runtime-worker-4`.

- [ ] **Step 1: Add live regression assertions**

Extend `tests/test_live_protocol_simulation.py` to assert:

```python
projection = build_operations_projection(db_path)
assert projection.replay_state is not None
assert all(agent.agent_id != "sim2-controller" for agent in projection.ui.visible_agents)
assert all(gate.relevance_state != "actionable" for gate in projection.ui.historical_gates)
```

Use the test's local IDs. Do not hardcode live DB IDs.

- [ ] **Step 2: Add documentation appendix**

Append a short implementation appendix to `docs/runtime-state-target-state.md`:

```markdown
## Implementation Notes

The implementation is staged through Wave10:

- Contract fields are added first.
- Runtime freshness and presence policy are projection-owned.
- Inbox and gate relevance are projection-owned.
- Frontend consumes explicit visibility fields and does not infer protocol state.
```

- [ ] **Step 3: Run validation**

Run:

```powershell
python -m pytest tests/test_live_protocol_simulation.py tests/test_operations_relevance_api.py -q
```

Expected: PASS.

## Final Controller Verification

After C1 and C2 READY:

1. Restart/verify the repo service on 8787 if needed.

```powershell
$conn = Get-NetTCPConnection -LocalPort 8787 -State Listen -ErrorAction SilentlyContinue
$conn | Select-Object LocalAddress,LocalPort,OwningProcess
```

2. Run API validation:

```powershell
$env:PYTHONIOENCODING='utf-8'
python -c "import json,urllib.request; d=json.load(urllib.request.urlopen('http://127.0.0.1:8787/api/projections/operations?event_limit=50', timeout=30)); ui=d['ui']; print(len(ui['visible_agents']), len(ui['archived_agents'])); print([a['agent_id'] for a in ui['visible_agents'] if a['agent_id'].startswith('sim2-')])"
```

Expected:

```text
[]
```

for visible Sim2 IDs, except a stale worker with active responsibility may appear only with `ui_visibility_state=needs_attention` and `runtime_state=suspected_stuck`.

3. Run full tests:

```powershell
python -m pytest -q
cd frontend
npm run build
```

4. Browser checks:

- Home page must not show stale temporary Sim2 controller/qa as active agents.
- Communication roster must separate main/needs-attention/archive.
- Gates approval queue must contain only actionable gates.
- Diagnostics/history must still expose archived Sim2 facts.
- No console errors.
- No horizontal overflow on desktop and mobile.

5. Broadcast:

```text
GATE_WAVE10_C_PASS runtime-controller
```

## Failure Routing

If a worker hits a blocker, it must send:

```text
BLOCKER_WAVE10_<TASK> <agent-id>: <specific failed invariant, command, output summary, suspected owner>
```

Controller response:

- Backend contract/test failure: route to `runtime-worker-5`.
- Runtime policy/relevance failure: route to `runtime-worker-7`.
- Frontend display/normalization failure: route to `runtime-worker-6`.
- E2E/documentation mismatch: route to `runtime-worker-4`.

Do not bypass a failed wave by changing frontend filters. A stale/status bug must be fixed in runtime policy or relevance projection.

## Acceptance Coverage Matrix

The target document acceptance criteria are covered by these tasks:

- Criteria 1, 3, 4, 16, 17: B1 identity lifecycle/relevance tests.
- Criteria 2, 9, 10, 25: A2/B1 runtime freshness and heartbeat policy tests.
- Criteria 5, 6, 7, 14, 15, 20, 27: B2 gate relevance tests and C1 UI consumption.
- Criteria 8, 26: B2 inbox relevance tests.
- Criteria 11: B2 action item and claim timeout routing if claim timeout support exists; otherwise document as follow-up blocker before Gate C.
- Criteria 12: A2/server heartbeat validation; admin override remains explicit follow-up if no admin API exists.
- Criteria 13, 22, 23, 28: B1/B2 projection output and replay tests.
- Criteria 18, 19: C1 UI label and workload/input distinction.
- Criteria 21, 24: A1 session-end contract and existing fencing/session-role tests.

## Commit Guidance

Workers should not commit unless explicitly instructed by controller. Keep changes in scoped files only. Controller will review dirty worktree before any commit/PR step.
