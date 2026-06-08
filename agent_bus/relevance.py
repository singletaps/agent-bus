from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import TYPE_CHECKING, Literal

from pydantic import BaseModel, Field

from .models import (
    AgentIdentityLifecycle,
    AgentRuntimeState,
    ArtifactRecord,
    ContextPacket,
    GateRecord,
    GateRelevanceState,
    InboxRelevanceState,
    InboxItem,
    PresenceState,
    RuntimeCondition,
    RunRecord,
    TaskRecord,
    UIVisibilityState,
    VisibilityPolicy,
    WorkloadState,
)

if TYPE_CHECKING:
    from .projections import AgentProjection


TERMINAL_TASK_STATES = {"completed", "failed", "superseded"}
TERMINAL_RUN_STATES = {"completed", "failed"}
ACTIONABLE_GATE_STATES = {"open", "escalated"}
OPEN_INBOX_STATUSES = {"queued", "delivered"}


class Visibility(str, Enum):
    MAIN = "main"
    SECONDARY = "secondary"
    NEEDS_ATTENTION = "needs_attention"
    DIAGNOSTICS = "diagnostics"
    HIDDEN = "hidden"


class AgentIdentityState(str, Enum):
    ACTIVE = "active"
    ARCHIVED = "archived"
    RETIRED = "retired"


class AgentOnlineState(str, Enum):
    ONLINE = "online"
    IDLE = "idle"
    OFFLINE = "offline"
    STALE = "stale"
    UNKNOWN = "unknown"


class AgentAuthorityState(str, Enum):
    PRIMARY = "primary"
    STANDBY = "standby"
    REPLACED = "replaced"
    QUARANTINED = "quarantined"
    RETIRED = "retired"
    NONE = "none"


class AgentWorkState(str, Enum):
    WORKING = "working"
    WAITING_INPUT = "waiting_input"
    WAITING_GATE = "waiting_gate"
    BLOCKED = "blocked"
    FREE = "free"
    HISTORICAL = "historical"


class AgentPresenceProjection(BaseModel):
    agent_id: str
    display_name: str
    role: str = ""
    identity_state: AgentIdentityState
    online_state: AgentOnlineState
    authority_state: AgentAuthorityState
    work_state: AgentWorkState
    current_task_id: str | None = None
    current_gate_id: str | None = None
    queued_inbox: int = 0
    last_seen_at: str | None = None
    last_effective_activity_at: str | None = None
    visible_in_main: bool = False
    hidden_reason: str | None = None
    identity_lifecycle: AgentIdentityLifecycle = AgentIdentityLifecycle.ACTIVE
    presence_state: PresenceState = PresenceState.UNKNOWN
    workload_state: WorkloadState = WorkloadState.FREE
    ui_visibility_state: UIVisibilityState = UIVisibilityState.HIDDEN
    conditions: list[RuntimeCondition] = Field(default_factory=list)


class GateRelevanceProjection(BaseModel):
    gate_id: str
    gate_state: str
    relevance_state: Literal[
        "actionable",
        "waiting",
        "waiting_evidence",
        "waiting_owner",
        "superseded",
        "historical",
        "orphaned",
        "expired",
        "diagnostics_only",
    ]
    visibility: Visibility
    reason: str
    run_id: str | None = None
    task_id: str | None = None
    context_packet_id: str | None = None
    superseded_by_gate_id: str | None = None
    superseded_by_event_id: str | None = None
    visible_in_approval_center: bool = False


class InboxRelevanceProjection(BaseModel):
    inbox_id: str
    agent_id: str
    relevance_state: InboxRelevanceState
    visibility: Visibility
    reason: str
    blocks_identity_archive: bool = False


class TaskRelevanceProjection(BaseModel):
    task_id: str
    lifecycle_state: Literal["active", "terminal", "superseded", "historical", "orphaned"]
    actionability: Literal["needs_action", "working", "waiting_gate", "waiting_review", "none"]
    visible_in_home: bool = False
    visible_in_rungraph: bool = False
    hidden_reason: str | None = None


class ArtifactRelevanceProjection(BaseModel):
    artifact_id: str
    visibility: Literal["current_task", "run", "legacy_unbound", "diagnostics"]
    visible_in_default_list: bool = False
    reason: str
    run_id: str | None = None
    task_id: str | None = None


class WorkflowClusterProjection(BaseModel):
    cluster_id: str
    task_id: str
    kind: Literal["replacement", "context_history", "protocol_diagnostics", "artifacts"]
    title: str
    count: int
    latest_state: str = ""
    latest_ref_id: str | None = None
    tone: str = "info"
    node_ids: list[str] = Field(default_factory=list)


class UiHiddenCounts(BaseModel):
    archived_agents: int = 0
    stale_sessions: int = 0
    historical_gates: int = 0
    superseded_gates: int = 0
    hidden_context_packets: int = 0
    collapsed_replacement_events: int = 0
    unbound_artifacts: int = 0


class RelevanceProjection(BaseModel):
    agents: dict[str, AgentPresenceProjection] = Field(default_factory=dict)
    gates: dict[str, GateRelevanceProjection] = Field(default_factory=dict)
    tasks: dict[str, TaskRelevanceProjection] = Field(default_factory=dict)
    artifacts: dict[str, ArtifactRelevanceProjection] = Field(default_factory=dict)
    workflow_clusters: dict[str, list[WorkflowClusterProjection]] = Field(default_factory=dict)
    hidden_counts: UiHiddenCounts = Field(default_factory=UiHiddenCounts)


def derive_relevance_projection(
    *,
    active_run: RunRecord | None,
    runs: list[RunRecord],
    tasks: list[TaskRecord],
    gates: list[GateRecord],
    artifacts: list[ArtifactRecord],
    agents: list[AgentProjection],
    contexts: list[ContextPacket],
    inbox: list[InboxItem],
) -> RelevanceProjection:
    """Return one composed relevance projection from durable facts."""

    owner_authority_valid_by_agent = _owner_authority_valid_by_agent(agents)
    inbox_relevance = derive_inbox_relevance(
        inbox=inbox,
        owner_authority_valid_by_agent=owner_authority_valid_by_agent,
    )
    gate_relevance = derive_gate_relevance(
        active_run=active_run,
        runs=runs,
        tasks=tasks,
        gates=gates,
        artifacts=artifacts,
        agents=agents,
        contexts=contexts,
    )
    task_relevance = derive_task_relevance(
        active_run=active_run,
        runs=runs,
        tasks=tasks,
        gates=gate_relevance,
    )
    agent_relevance = derive_agent_relevance(
        agents=agents,
        tasks=tasks,
        gates=gates,
        gate_relevance=gate_relevance,
        inbox=inbox,
        inbox_relevance=inbox_relevance,
    )
    artifact_relevance = derive_artifact_relevance(
        active_run=active_run,
        runs=runs,
        tasks=tasks,
        artifacts=artifacts,
        task_relevance=task_relevance,
    )
    hidden_contexts = _hidden_context_packets(contexts)
    workflow_clusters = derive_workflow_clusters(
        contexts=contexts,
        artifacts=artifacts,
        artifact_relevance=artifact_relevance,
        hidden_context_packet_ids={packet.packet_id for packet in hidden_contexts},
    )

    hidden_counts = UiHiddenCounts(
        archived_agents=sum(
            1 for agent in agent_relevance.values() if agent.identity_state is AgentIdentityState.ARCHIVED
        ),
        stale_sessions=sum(1 for agent in agent_relevance.values() if agent.online_state is AgentOnlineState.STALE),
        historical_gates=sum(
            1 for gate in gate_relevance.values() if gate.relevance_state in {"historical", "expired", "orphaned"}
        ),
        superseded_gates=sum(1 for gate in gate_relevance.values() if gate.relevance_state == "superseded"),
        hidden_context_packets=len(hidden_contexts),
        unbound_artifacts=sum(
            1 for artifact in artifact_relevance.values() if artifact.visibility == "legacy_unbound"
        ),
    )

    return RelevanceProjection(
        agents=agent_relevance,
        gates=gate_relevance,
        tasks=task_relevance,
        artifacts=artifact_relevance,
        workflow_clusters=workflow_clusters,
        hidden_counts=hidden_counts,
    )


def derive_gate_relevance(
    *,
    active_run: RunRecord | None,
    runs: list[RunRecord],
    tasks: list[TaskRecord],
    gates: list[GateRecord],
    artifacts: list[ArtifactRecord],
    agents: list[AgentProjection],
    contexts: list[ContextPacket],
) -> dict[str, GateRelevanceProjection]:
    tasks_by_id = {task.task_id: task for task in tasks}
    runs_by_id = {run.run_id: run for run in runs}
    artifact_ids = {artifact.artifact_id for artifact in artifacts}
    agents_by_id = {agent.identity.agent_id: agent for agent in agents}
    latest_gate = _latest_gate_by_scope(gates)
    latest_context = _latest_context_by_task(contexts)

    relevance: dict[str, GateRelevanceProjection] = {}
    for gate in gates:
        state = _normalize(gate.state)
        task = tasks_by_id.get(gate.task_id or "")
        effective_run_id = gate.run_id or (task.run_id if task else None)
        run = runs_by_id.get(effective_run_id or "")
        latest_for_scope = latest_gate.get(_gate_scope(gate))
        base = {
            "gate_id": gate.gate_id,
            "gate_state": state,
            "run_id": gate.run_id,
            "task_id": gate.task_id,
        }

        if state not in ACTIONABLE_GATE_STATES:
            relevance[gate.gate_id] = GateRelevanceProjection(
                **base,
                relevance_state="historical",
                visibility=Visibility.DIAGNOSTICS,
                reason="gate_resolved",
            )
            continue

        if task is None and gate.task_id:
            relevance[gate.gate_id] = GateRelevanceProjection(
                **base,
                relevance_state="orphaned",
                visibility=Visibility.DIAGNOSTICS,
                reason="task_missing",
            )
            continue

        if task is not None and _normalize(task.status) in TERMINAL_TASK_STATES:
            relevance[gate.gate_id] = GateRelevanceProjection(
                **base,
                relevance_state="historical",
                visibility=Visibility.DIAGNOSTICS,
                reason="task_terminal",
            )
            continue

        if effective_run_id and not _run_is_active(effective_run_id, active_run, run):
            reason = "run_terminal" if run is not None and _normalize(run.status) in TERMINAL_RUN_STATES else "run_not_active"
            relevance[gate.gate_id] = GateRelevanceProjection(
                **base,
                relevance_state="historical",
                visibility=Visibility.DIAGNOSTICS,
                reason=reason,
            )
            continue

        context = latest_context.get(gate.task_id or "")
        if context is not None and _normalize(context.status) != "active":
            relevance[gate.gate_id] = GateRelevanceProjection(
                **base,
                context_packet_id=context.packet_id,
                relevance_state="superseded",
                visibility=Visibility.DIAGNOSTICS,
                reason="context_inactive",
            )
            continue

        if latest_for_scope is not None and latest_for_scope.gate_id != gate.gate_id:
            relevance[gate.gate_id] = GateRelevanceProjection(
                **base,
                relevance_state="superseded",
                visibility=Visibility.DIAGNOSTICS,
                reason="newer_gate_exists",
                superseded_by_gate_id=latest_for_scope.gate_id,
            )
            continue

        if _gate_owner_unavailable(gate, agents_by_id):
            relevance[gate.gate_id] = GateRelevanceProjection(
                **base,
                relevance_state=GateRelevanceState.WAITING_OWNER.value,
                visibility=Visibility.NEEDS_ATTENTION,
                reason="decision_owner_unavailable",
            )
            continue

        missing_evidence = sorted(set(gate.required_evidence) - artifact_ids)
        if missing_evidence:
            relevance[gate.gate_id] = GateRelevanceProjection(
                **base,
                relevance_state=GateRelevanceState.WAITING_EVIDENCE.value,
                visibility=Visibility.SECONDARY,
                reason="required_evidence_missing",
            )
            continue

        relevance[gate.gate_id] = GateRelevanceProjection(
            **base,
            relevance_state="actionable",
            visibility=Visibility.MAIN,
            reason="current_actionable_gate",
            visible_in_approval_center=True,
        )

    return relevance


def derive_inbox_relevance(
    *,
    inbox: list[InboxItem],
    owner_authority_valid_by_agent: dict[str, bool],
    now_iso: str | None = None,
) -> dict[str, InboxRelevanceProjection]:
    now = _parse_iso(now_iso or _now_iso())
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
        elif not owner_valid:
            state = InboxRelevanceState.DIAGNOSTICS_ONLY
            reason = "owner_authority_invalid"
            blocks = False
        elif status == "delivered" and _iso_before(item.lease_expires_at, now):
            state = InboxRelevanceState.LEASE_EXPIRED
            reason = "lease_expired"
            blocks = True
        elif status in OPEN_INBOX_STATUSES:
            state = InboxRelevanceState.DELIVERABLE if status == "queued" else InboxRelevanceState.DELIVERED
            reason = "owner_authority_valid"
            blocks = True
        else:
            state = InboxRelevanceState.DIAGNOSTICS_ONLY
            reason = "inbox_not_open"
            blocks = False
        result[item.inbox_id] = InboxRelevanceProjection(
            inbox_id=item.inbox_id,
            agent_id=item.agent_id,
            relevance_state=state,
            visibility=Visibility.SECONDARY if blocks else Visibility.DIAGNOSTICS,
            reason=reason,
            blocks_identity_archive=blocks,
        )
    return result


def derive_task_relevance(
    *,
    active_run: RunRecord | None,
    runs: list[RunRecord],
    tasks: list[TaskRecord],
    gates: dict[str, GateRelevanceProjection],
) -> dict[str, TaskRelevanceProjection]:
    runs_by_id = {run.run_id: run for run in runs}
    actionable_gate_by_task: dict[str, GateRelevanceProjection] = {}
    for gate in gates.values():
        if gate.task_id and gate.visible_in_approval_center:
            actionable_gate_by_task.setdefault(gate.task_id, gate)

    relevance: dict[str, TaskRelevanceProjection] = {}
    for task in tasks:
        status = _normalize(task.status)
        run = runs_by_id.get(task.run_id or "")
        run_active = _run_is_active(task.run_id, active_run, run) if task.run_id else True

        if status == "superseded":
            lifecycle = "superseded"
            hidden_reason = "task_superseded"
        elif status in TERMINAL_TASK_STATES:
            lifecycle = "terminal"
            hidden_reason = "task_terminal"
        elif task.run_id and not run_active:
            lifecycle = "historical" if run is not None else "orphaned"
            hidden_reason = "run_not_active" if run is not None else "run_missing"
        else:
            lifecycle = "active"
            hidden_reason = None

        has_actionable_gate = task.task_id in actionable_gate_by_task
        if lifecycle != "active":
            actionability = "none"
        elif status == "blocked":
            actionability = "needs_action"
        elif has_actionable_gate:
            actionability = "waiting_gate"
        elif status in {"created", "assigned", "acknowledged", "working", "reassigned"}:
            actionability = "working"
        else:
            actionability = "none"

        visible = lifecycle == "active" and (actionability != "none" or status not in TERMINAL_TASK_STATES)
        relevance[task.task_id] = TaskRelevanceProjection(
            task_id=task.task_id,
            lifecycle_state=lifecycle,
            actionability=actionability,
            visible_in_home=visible,
            visible_in_rungraph=visible,
            hidden_reason=None if visible else hidden_reason,
        )

    return relevance


def derive_agent_relevance(
    *,
    agents: list[AgentProjection],
    tasks: list[TaskRecord],
    gates: list[GateRecord],
    gate_relevance: dict[str, GateRelevanceProjection],
    inbox: list[InboxItem],
    inbox_relevance: dict[str, InboxRelevanceProjection] | None = None,
) -> dict[str, AgentPresenceProjection]:
    active_task_by_agent: dict[str, TaskRecord] = {}
    blocked_task_by_agent: dict[str, TaskRecord] = {}
    for task in tasks:
        if _normalize(task.status) in TERMINAL_TASK_STATES:
            continue
        for agent_id in _task_workload_agent_ids(task):
            active_task_by_agent.setdefault(agent_id, task)
            if _normalize(task.status) == "blocked":
                blocked_task_by_agent.setdefault(agent_id, task)

    gates_by_id = {gate.gate_id: gate for gate in gates}
    gate_by_agent: dict[str, GateRecord] = {}
    for gate_projection in gate_relevance.values():
        if not gate_projection.visible_in_approval_center:
            continue
        gate = gates_by_id.get(gate_projection.gate_id)
        if gate is None:
            continue
        for agent_id in _gate_agent_ids(gate):
            gate_by_agent.setdefault(agent_id, gate)

    inbox_counts = _open_inbox_counts(inbox, inbox_relevance)
    has_explicit_inbox = bool(inbox)

    relevance: dict[str, AgentPresenceProjection] = {}
    for agent in agents:
        identity = agent.identity
        agent_id = identity.agent_id
        active_session = agent.active_session
        health = agent.health
        current_task = blocked_task_by_agent.get(agent_id) or active_task_by_agent.get(agent_id)
        current_gate = gate_by_agent.get(agent_id)
        queued_inbox = inbox_counts.get(agent_id, 0) if has_explicit_inbox else _projection_open_inbox_count(agent)
        online_state = _agent_online_state(active_session, health)
        authority_state = _agent_authority_state(active_session)

        if current_task is not None and _normalize(current_task.status) == "blocked":
            work_state = AgentWorkState.BLOCKED
        elif queued_inbox:
            work_state = AgentWorkState.WAITING_INPUT
        elif current_gate is not None:
            work_state = AgentWorkState.WAITING_GATE
        elif current_task is not None:
            work_state = AgentWorkState.WORKING
        elif active_session is None:
            work_state = AgentWorkState.HISTORICAL
        else:
            work_state = AgentWorkState.FREE

        has_responsibility = current_task is not None or current_gate is not None or queued_inbox > 0
        primary_online = authority_state is AgentAuthorityState.PRIMARY and online_state in {
            AgentOnlineState.ONLINE,
            AgentOnlineState.IDLE,
        }
        system_relevant = _is_system_relevant(agent)
        visible = system_relevant or has_responsibility or primary_online

        if _normalize(getattr(identity, "identity_lifecycle", "")) == AgentIdentityLifecycle.RETIRED.value:
            identity_state = AgentIdentityState.RETIRED
        elif visible:
            identity_state = AgentIdentityState.ACTIVE
        else:
            identity_state = AgentIdentityState.ARCHIVED

        hidden_reason = None
        if not visible:
            hidden_reason = "stale_without_responsibility" if online_state is AgentOnlineState.STALE else "no_current_responsibility"

        last_seen = active_session.last_seen_at if active_session else None
        identity_lifecycle = _target_identity_lifecycle(identity_state)
        workload_state = _target_workload_state(work_state)
        presence_state = _target_presence_state(online_state)
        ui_visibility_state = _target_ui_visibility_state(
            visible=visible,
            online_state=online_state,
            work_state=work_state,
            authority_state=authority_state,
        )
        relevance[agent_id] = AgentPresenceProjection(
            agent_id=agent_id,
            display_name=identity.display_name or agent_id,
            role=identity.role or "",
            identity_state=identity_state,
            online_state=online_state,
            authority_state=authority_state,
            work_state=work_state,
            current_task_id=current_task.task_id if current_task is not None else None,
            current_gate_id=current_gate.gate_id if current_gate is not None else None,
            queued_inbox=queued_inbox,
            last_seen_at=last_seen,
            last_effective_activity_at=last_seen,
            visible_in_main=visible,
            hidden_reason=hidden_reason,
            identity_lifecycle=identity_lifecycle,
            presence_state=presence_state,
            workload_state=workload_state,
            ui_visibility_state=ui_visibility_state,
            conditions=list(getattr(agent, "conditions", []) or []),
        )

    return relevance


def derive_artifact_relevance(
    *,
    active_run: RunRecord | None,
    runs: list[RunRecord],
    tasks: list[TaskRecord],
    artifacts: list[ArtifactRecord],
    task_relevance: dict[str, TaskRelevanceProjection],
) -> dict[str, ArtifactRelevanceProjection]:
    runs_by_id = {run.run_id: run for run in runs}
    relevance: dict[str, ArtifactRelevanceProjection] = {}

    for artifact in artifacts:
        task_projection = task_relevance.get(artifact.task_id or "")
        run = runs_by_id.get(artifact.run_id or "")
        if task_projection is not None and task_projection.lifecycle_state == "active":
            visibility = "current_task"
            visible = True
            reason = "active_task_artifact"
        elif artifact.run_id and _run_is_active(artifact.run_id, active_run, run):
            visibility = "run"
            visible = True
            reason = "active_run_artifact"
        elif not artifact.run_id and not artifact.task_id:
            visibility = "legacy_unbound"
            visible = False
            reason = "unbound_artifact"
        else:
            visibility = "diagnostics"
            visible = False
            reason = "historical_binding"

        relevance[artifact.artifact_id] = ArtifactRelevanceProjection(
            artifact_id=artifact.artifact_id,
            visibility=visibility,
            visible_in_default_list=visible,
            reason=reason,
            run_id=artifact.run_id,
            task_id=artifact.task_id,
        )

    return relevance


def derive_workflow_clusters(
    *,
    contexts: list[ContextPacket],
    artifacts: list[ArtifactRecord],
    artifact_relevance: dict[str, ArtifactRelevanceProjection],
    hidden_context_packet_ids: set[str],
) -> dict[str, list[WorkflowClusterProjection]]:
    clusters: dict[str, list[WorkflowClusterProjection]] = {}

    hidden_contexts_by_task: dict[str, list[ContextPacket]] = {}
    for packet in contexts:
        if packet.task_id and packet.packet_id in hidden_context_packet_ids:
            hidden_contexts_by_task.setdefault(packet.task_id, []).append(packet)
    for task_id, packets in hidden_contexts_by_task.items():
        latest = max(packets, key=lambda packet: (packet.created_at, packet.packet_id))
        clusters.setdefault(task_id, []).append(
            WorkflowClusterProjection(
                cluster_id=f"cluster:context_history:{task_id}",
                task_id=task_id,
                kind="context_history",
                title="Context history",
                count=len(packets),
                latest_state=_normalize(latest.status),
                latest_ref_id=latest.packet_id,
                tone="info",
                node_ids=[packet.packet_id for packet in packets],
            )
        )

    hidden_artifacts_by_task: dict[str, list[ArtifactRecord]] = {}
    for artifact in artifacts:
        projection = artifact_relevance.get(artifact.artifact_id)
        if artifact.task_id and projection is not None and not projection.visible_in_default_list:
            hidden_artifacts_by_task.setdefault(artifact.task_id, []).append(artifact)
    for task_id, task_artifacts in hidden_artifacts_by_task.items():
        latest = max(task_artifacts, key=lambda artifact: (artifact.created_at, artifact.artifact_id))
        clusters.setdefault(task_id, []).append(
            WorkflowClusterProjection(
                cluster_id=f"cluster:artifacts:{task_id}",
                task_id=task_id,
                kind="artifacts",
                title="Artifact history",
                count=len(task_artifacts),
                latest_state="historical",
                latest_ref_id=latest.artifact_id,
                tone="info",
                node_ids=[artifact.artifact_id for artifact in task_artifacts],
            )
        )

    return clusters


def _normalize(value: object) -> str:
    if hasattr(value, "value"):
        return str(value.value).lower()
    return str(value or "").lower()


def _latest_gate_by_scope(gates: list[GateRecord]) -> dict[tuple[str, str], GateRecord]:
    latest: dict[tuple[str, str], GateRecord] = {}
    for gate in gates:
        scope = _gate_scope(gate)
        current = latest.get(scope)
        if current is None or (gate.created_at, gate.gate_id) > (current.created_at, current.gate_id):
            latest[scope] = gate
    return latest


def _gate_scope(gate: GateRecord) -> tuple[str, str]:
    return (gate.task_id or gate.run_id or "", gate.gate_kind or "approval")


def _latest_context_by_task(contexts: list[ContextPacket]) -> dict[str, ContextPacket]:
    latest: dict[str, ContextPacket] = {}
    for packet in contexts:
        if not packet.task_id:
            continue
        current = latest.get(packet.task_id)
        if current is None or (packet.created_at, packet.packet_id) > (current.created_at, current.packet_id):
            latest[packet.task_id] = packet
    return latest


def _hidden_context_packets(contexts: list[ContextPacket]) -> list[ContextPacket]:
    latest_active_by_scope: dict[tuple[str, str, str], ContextPacket] = {}
    for packet in contexts:
        if _normalize(packet.status) != "active":
            continue
        scope = _context_scope(packet)
        current = latest_active_by_scope.get(scope)
        if current is None or (packet.created_at, packet.packet_id) > (current.created_at, current.packet_id):
            latest_active_by_scope[scope] = packet

    hidden: list[ContextPacket] = []
    latest_active_ids = {packet.packet_id for packet in latest_active_by_scope.values()}
    for packet in contexts:
        if _normalize(packet.status) != "active" or packet.packet_id not in latest_active_ids:
            hidden.append(packet)
    return hidden


def _context_scope(packet: ContextPacket) -> tuple[str, str, str]:
    return (packet.task_id or "", packet.run_id or "", packet.agent_id)


def _run_is_active(run_id: str | None, active_run: RunRecord | None, run: RunRecord | None) -> bool:
    if not run_id:
        return True
    if run is not None and _normalize(run.status) in TERMINAL_RUN_STATES:
        return False
    if active_run is None:
        return run is not None
    if active_run.run_id != run_id:
        return False
    return _normalize(active_run.status) not in TERMINAL_RUN_STATES


def _task_agent_ids(task: TaskRecord) -> set[str]:
    return {agent_id for agent_id in {task.assignee_agent_id, task.owner_agent_id} if agent_id}


def _task_workload_agent_ids(task: TaskRecord) -> set[str]:
    return {task.assignee_agent_id} if task.assignee_agent_id else set()


def _gate_agent_ids(gate: GateRecord) -> set[str]:
    return {agent_id for agent_id in {gate.owner_agent_id, gate.requested_by} if agent_id}


def _open_inbox_counts(
    inbox: list[InboxItem],
    inbox_relevance: dict[str, InboxRelevanceProjection] | None = None,
) -> dict[str, int]:
    counts: dict[str, int] = {}
    for item in inbox:
        projection = inbox_relevance.get(item.inbox_id) if inbox_relevance is not None else None
        if projection is not None:
            if not projection.blocks_identity_archive:
                continue
            counts[item.agent_id] = counts.get(item.agent_id, 0) + 1
        elif _normalize(item.status) in OPEN_INBOX_STATUSES:
            counts[item.agent_id] = counts.get(item.agent_id, 0) + 1
    return counts


def _projection_open_inbox_count(agent: AgentProjection) -> int:
    return sum(
        count
        for status, count in (agent.inbox_counts or {}).items()
        if _normalize(status) in OPEN_INBOX_STATUSES
    )


def _agent_online_state(active_session: object | None, health: object | None) -> AgentOnlineState:
    if active_session is None:
        return AgentOnlineState.OFFLINE
    runtime_state = _normalize(getattr(active_session, "runtime_state", ""))
    if getattr(health, "stale", False) or runtime_state in {"standby_degraded", "suspected_stuck"}:
        return AgentOnlineState.STALE
    if runtime_state in {"standby_ready", "waiting_on_bus", "wait_returned_noop"}:
        return AgentOnlineState.IDLE
    if runtime_state:
        return AgentOnlineState.ONLINE
    return AgentOnlineState.UNKNOWN


def _agent_authority_state(active_session: object | None) -> AgentAuthorityState:
    if active_session is None:
        return AgentAuthorityState.NONE
    runtime_state = _normalize(getattr(active_session, "runtime_state", ""))
    if getattr(active_session, "quarantined", False):
        return AgentAuthorityState.QUARANTINED
    if getattr(active_session, "replaced_by_session_id", None) or runtime_state == _normalize(AgentRuntimeState.REPLACED):
        return AgentAuthorityState.REPLACED
    if not getattr(active_session, "active", True) or getattr(active_session, "ended_at", None):
        return AgentAuthorityState.RETIRED
    if _normalize(getattr(active_session, "session_role", "")) == "primary":
        return AgentAuthorityState.PRIMARY
    return AgentAuthorityState.STANDBY


def _target_identity_lifecycle(identity_state: AgentIdentityState) -> AgentIdentityLifecycle:
    if identity_state is AgentIdentityState.RETIRED:
        return AgentIdentityLifecycle.RETIRED
    if identity_state is AgentIdentityState.ARCHIVED:
        return AgentIdentityLifecycle.ARCHIVED
    return AgentIdentityLifecycle.ACTIVE


def _target_presence_state(online_state: AgentOnlineState) -> PresenceState:
    if online_state in {AgentOnlineState.ONLINE, AgentOnlineState.IDLE}:
        return PresenceState.ONLINE
    if online_state is AgentOnlineState.STALE:
        return PresenceState.STALE
    if online_state is AgentOnlineState.OFFLINE:
        return PresenceState.OFFLINE
    return PresenceState.UNKNOWN


def _target_workload_state(work_state: AgentWorkState) -> WorkloadState:
    return {
        AgentWorkState.WORKING: WorkloadState.WORKING,
        AgentWorkState.WAITING_INPUT: WorkloadState.WAITING_INPUT,
        AgentWorkState.WAITING_GATE: WorkloadState.WAITING_GATE,
        AgentWorkState.BLOCKED: WorkloadState.BLOCKED,
        AgentWorkState.FREE: WorkloadState.FREE,
        AgentWorkState.HISTORICAL: WorkloadState.HISTORICAL,
    }[work_state]


def _target_ui_visibility_state(
    *,
    visible: bool,
    online_state: AgentOnlineState,
    work_state: AgentWorkState,
    authority_state: AgentAuthorityState,
) -> UIVisibilityState:
    if not visible:
        return UIVisibilityState.HIDDEN
    if authority_state in {AgentAuthorityState.REPLACED, AgentAuthorityState.QUARANTINED, AgentAuthorityState.RETIRED}:
        return UIVisibilityState.DIAGNOSTICS
    if online_state is AgentOnlineState.STALE or work_state in {
        AgentWorkState.BLOCKED,
        AgentWorkState.WAITING_INPUT,
        AgentWorkState.WAITING_GATE,
    }:
        return UIVisibilityState.NEEDS_ATTENTION
    return UIVisibilityState.MAIN


def _owner_authority_valid_by_agent(agents: list[AgentProjection]) -> dict[str, bool]:
    result: dict[str, bool] = {}
    for agent in agents:
        authority = _agent_authority_state(agent.active_session)
        result[agent.identity.agent_id] = authority is AgentAuthorityState.PRIMARY
    return result


def _gate_owner_unavailable(gate: GateRecord, agents_by_id: dict[str, AgentProjection]) -> bool:
    if not gate.owner_agent_id:
        return False
    owner = agents_by_id.get(gate.owner_agent_id)
    if owner is None:
        return True
    authority = _agent_authority_state(owner.active_session)
    online = _agent_online_state(owner.active_session, owner.health)
    return authority is not AgentAuthorityState.PRIMARY or online in {
        AgentOnlineState.OFFLINE,
        AgentOnlineState.STALE,
        AgentOnlineState.UNKNOWN,
    }


def _parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _iso_before(value: str | None, now: datetime | None) -> bool:
    parsed = _parse_iso(value)
    if parsed is None or now is None:
        return False
    return parsed < now


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _is_system_relevant(agent: AgentProjection) -> bool:
    identity = agent.identity
    if bool(getattr(identity, "canonical", False)):
        return True
    if getattr(identity, "visibility_policy", None) == VisibilityPolicy.SYSTEM_CRITICAL:
        return True
    return identity.agent_id in {"controller", "runtime-controller", "runtime-qa", "user"}
