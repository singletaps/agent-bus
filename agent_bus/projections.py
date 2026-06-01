from __future__ import annotations

import os
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from .agents import AgentDirectory, AgentDirectoryError, migrate as migrate_agents
from .context import ContextPacketInvalidated, ContextPacketNotFound, migrate as migrate_context, row_to_packet
from .db import connect, initialize_database
from .gates import _row_to_gate
from .inbox import migrate as migrate_inbox, row_to_item
from .models import (
    AgentCapability,
    AgentHealth,
    AgentIdentity,
    AgentRuntimeState,
    AgentSession,
    ArtifactRecord,
    BusEvent,
    BusMessageLink,
    BusMessageProjection,
    ContextPacket,
    GateRecord,
    InboxItem,
    ReviewFinding,
    RunRecord,
    RunState,
    TaskRecord,
    utc_now_iso,
)
from .replacement import InMemoryRehydrationContext, ReplacementCoordinator, ReplacementRecommendation
from .reviews import _row_to_finding
from .store import EventStore
from .tasks import _row_to_run, _row_to_task, migrate_runtime_schema


ACTIVE_TASK_STATES = {"created", "assigned", "acknowledged", "working", "blocked", "reassigned"}
MESSAGE_EVENT_TYPES = {
    "user.interrupt_created",
    "coordination.recorded",
    "gate.opened",
    "gate.result",
    "review.changes_requested",
    "task.reassigned",
}
DEFAULT_SESSION_FRESHNESS_SECONDS = 300.0
SESSION_FRESHNESS_ENV = "AGENT_BUS_SESSION_FRESHNESS_SECONDS"
_FRESHNESS_DERIVED_STATES: dict[AgentRuntimeState, AgentRuntimeState] = {
    AgentRuntimeState.STANDBY_READY: AgentRuntimeState.STANDBY_DEGRADED,
    AgentRuntimeState.WAITING_ON_BUS: AgentRuntimeState.STANDBY_DEGRADED,
    AgentRuntimeState.WAIT_RETURNED_NOOP: AgentRuntimeState.STANDBY_DEGRADED,
    AgentRuntimeState.WORKING: AgentRuntimeState.SUSPECTED_STUCK,
}
_FRESHNESS_HEALTH_SCORES: dict[AgentRuntimeState, float] = {
    AgentRuntimeState.STANDBY_DEGRADED: 0.55,
    AgentRuntimeState.SUSPECTED_STUCK: 0.30,
}


class AgentProjection(BaseModel):
    identity: AgentIdentity
    active_session: AgentSession | None = None
    health: AgentHealth | None = None
    capabilities: list[AgentCapability] = Field(default_factory=list)
    inbox_counts: dict[str, int] = Field(default_factory=dict)


class SessionProjection(BaseModel):
    session: AgentSession
    health: AgentHealth | None = None


class ReplacementTriggerProjection(BaseModel):
    name: str
    reason: str
    weight: float


class ReplacementCandidateProjection(BaseModel):
    agent_id: str
    session_id: str | None
    score: float
    capability_score: float
    readiness_score: float
    role_score: float
    freshness_score: float
    failure_penalty: float


class ReplacementRecommendationProjection(BaseModel):
    recommendation_id: str
    task_id: str
    old_session_id: str
    old_agent_id: str
    candidate: ReplacementCandidateProjection
    triggers: list[ReplacementTriggerProjection]
    reason: str
    run_id: str | None = None
    required_capabilities: list[str] = Field(default_factory=list)
    role: str | None = None
    created_at: str


class UiActiveRunProjection(BaseModel):
    run_id: str | None = None
    title: str = ""
    objective: str = ""
    state: str = "none"
    created_at: str | None = None
    updated_at: str | None = None
    progress: dict[str, int] = Field(default_factory=dict)


class UiMetroNode(BaseModel):
    id: str
    kind: str
    title: str
    subtitle: str = ""
    state: str = ""
    tone: str = "info"
    run_id: str | None = None
    task_id: str | None = None
    gate_id: str | None = None
    artifact_id: str | None = None
    agent_id: str | None = None
    route: str = "Runs"
    priority: int = 0


class UiMetroEdge(BaseModel):
    id: str
    source: str
    target: str
    kind: str = "main"
    tone: str = "neutral"


class UiMetroProjection(BaseModel):
    nodes: list[UiMetroNode] = Field(default_factory=list)
    edges: list[UiMetroEdge] = Field(default_factory=list)
    main_path_node_ids: list[str] = Field(default_factory=list)
    current_node_id: str | None = None
    branch_groups: dict[str, list[str]] = Field(default_factory=dict)


class UiActionItem(BaseModel):
    id: str
    kind: str
    title: str
    description: str = ""
    tone: str = "info"
    route: str = "Runs"
    priority: int = 0
    run_id: str | None = None
    task_id: str | None = None
    gate_id: str | None = None
    artifact_id: str | None = None
    agent_id: str | None = None
    created_at: str | None = None
    suggested_actions: list[str] = Field(default_factory=list)


class UiAgentSummary(BaseModel):
    agent_id: str
    display_name: str
    role: str = ""
    runtime_state: str = ""
    tone: str = "info"
    health_score: float | None = None
    stale: bool = False
    current_task_id: str | None = None
    current_task_title: str | None = None
    open_gate_id: str | None = None
    queued_inbox: int = 0
    next_action: str = ""


class UiGateDecision(BaseModel):
    gate_id: str
    name: str
    state: str
    risk: str = "normal"
    tone: str = "warn"
    run_id: str | None = None
    task_id: str | None = None
    owner_agent_id: str | None = None
    requested_by: str | None = None
    reason: str = ""
    priority: int = 0


class UiArtifactSummary(BaseModel):
    total: int = 0
    by_kind: dict[str, int] = Field(default_factory=dict)
    latest_artifact_id: str | None = None
    latest_title: str = ""
    latest_uri: str = ""
    latest_created_at: str | None = None


class UiOperationsProjection(BaseModel):
    active_run: UiActiveRunProjection = Field(default_factory=UiActiveRunProjection)
    metro: UiMetroProjection = Field(default_factory=UiMetroProjection)
    action_items: list[UiActionItem] = Field(default_factory=list)
    agent_summaries: list[UiAgentSummary] = Field(default_factory=list)
    gate_decisions: list[UiGateDecision] = Field(default_factory=list)
    artifact_summary: UiArtifactSummary = Field(default_factory=UiArtifactSummary)


class EventReplayState(BaseModel):
    runs: dict[str, dict[str, Any]] = Field(default_factory=dict)
    tasks: dict[str, dict[str, Any]] = Field(default_factory=dict)
    gates: dict[str, dict[str, Any]] = Field(default_factory=dict)
    contexts: dict[str, dict[str, Any]] = Field(default_factory=dict)
    replacements: dict[str, dict[str, Any]] = Field(default_factory=dict)


class OperationsProjection(BaseModel):
    last_seq: int = 0
    agents: list[AgentProjection] = Field(default_factory=list)
    sessions: list[SessionProjection] = Field(default_factory=list)
    runs: list[RunRecord] = Field(default_factory=list)
    tasks: list[TaskRecord] = Field(default_factory=list)
    gates: list[GateRecord] = Field(default_factory=list)
    review_findings: list[ReviewFinding] = Field(default_factory=list)
    contexts: list[ContextPacket] = Field(default_factory=list)
    inbox: list[InboxItem] = Field(default_factory=list)
    artifacts: list[ArtifactRecord] = Field(default_factory=list)
    replacement_recommendations: list[ReplacementRecommendationProjection] = Field(default_factory=list)
    events: list[BusEvent] = Field(default_factory=list)
    replay_state: EventReplayState = Field(default_factory=EventReplayState)
    metrics: dict[str, int] = Field(default_factory=dict)
    ui: UiOperationsProjection = Field(default_factory=UiOperationsProjection)


class ProjectionReader:
    def __init__(
        self,
        db_path: str | os.PathLike[str] | None = None,
        *,
        session_freshness_seconds: float | None = None,
    ) -> None:
        self.db_path = db_path
        self.session_freshness_seconds = (
            _configured_session_freshness_seconds()
            if session_freshness_seconds is None
            else session_freshness_seconds
        )

    def build_operations_projection(self, *, event_limit: int = 200) -> OperationsProjection:
        conn = self._connect()
        try:
            events = EventStore(self.db_path).replay_all()
            limited_events = events[-event_limit:] if event_limit > 0 else []
            runs = self._runs(conn)
            tasks = self._tasks(conn)
            runs = _with_projected_run_states(runs, tasks)
            gates = self._gates(conn)
            findings = self._review_findings(conn)
            contexts = self._contexts(conn)
            inbox = self._inbox(conn)
            artifacts = self._artifacts(conn)
            agents = self._agents(conn, inbox)
            gates = _with_projected_gate_owners(gates, agents)
            sessions = self._sessions(conn)
            recommendations = self.replacement_recommendations(tasks=tasks)
            last_seq = max((event.seq or 0 for event in events), default=0)
            ui = _build_ui_projection(
                runs=runs,
                tasks=tasks,
                gates=gates,
                artifacts=artifacts,
                agents=agents,
                contexts=contexts,
                inbox=inbox,
                review_findings=findings,
            )
            return OperationsProjection(
                last_seq=last_seq,
                agents=agents,
                sessions=sessions,
                runs=runs,
                tasks=tasks,
                gates=gates,
                review_findings=findings,
                contexts=contexts,
                inbox=inbox,
                artifacts=artifacts,
                replacement_recommendations=recommendations,
                events=limited_events,
                replay_state=rebuild_event_state(events),
                metrics={
                    "agents": len(agents),
                    "sessions": len(sessions),
                    "runs": len(runs),
                    "tasks": len(tasks),
                    "open_gates": sum(1 for gate in gates if gate.state == "open"),
                    "open_findings": sum(1 for finding in findings if finding.status == "open"),
                    "active_contexts": sum(1 for packet in contexts if packet.status == "active"),
                    "queued_inbox": sum(1 for item in inbox if item.status == "queued"),
                    "artifacts": len(artifacts),
                    "events": len(events),
                },
                ui=ui,
            )
        finally:
            conn.close()

    def events_after(self, after_seq: int | None = None, *, limit: int = 200) -> list[BusEvent]:
        return EventStore(self.db_path).query_events(after_seq=after_seq, limit=limit)

    def get_context_packet(self, packet_id: str, *, include_inactive: bool = False) -> ContextPacket:
        conn = self._connect()
        try:
            row = conn.execute("select * from context_packets where packet_id = ?", (packet_id,)).fetchone()
            if row is None:
                raise ContextPacketNotFound(f"unknown context packet: {packet_id}")
            packet = row_to_packet(row)
            if packet.status == "invalidated" and not include_inactive:
                raise ContextPacketInvalidated(packet)
            return packet
        finally:
            conn.close()

    def replacement_recommendations(
        self,
        *,
        session_id: str | None = None,
        task_id: str | None = None,
        run_id: str | None = None,
        required_capabilities: list[str] | None = None,
        role: str | None = None,
        tasks: list[TaskRecord] | None = None,
    ) -> list[ReplacementRecommendationProjection]:
        directory = AgentDirectory(db_path=self.db_path)
        try:
            coordinator = ReplacementCoordinator(
                directory=directory,
                context_sink=InMemoryRehydrationContext(),
                db_path=self.db_path,
            )
            sessions = [directory.get_session(session_id)] if session_id else directory.list_all_sessions()
            known_tasks = tasks if tasks is not None else self._read_tasks_for_recommendations()
            recommendations: list[ReplacementRecommendationProjection] = []
            for session in sessions:
                effective_task_id = task_id or _task_for_agent(known_tasks, session.agent_id)
                if effective_task_id is None:
                    continue
                recommendation = coordinator.recommend_for_session(
                    session.session_id,
                    task_id=effective_task_id,
                    run_id=run_id or session.run_id,
                    required_capabilities=tuple(required_capabilities or ()),
                    role=role,
                )
                if recommendation is not None:
                    recommendations.append(recommendation_to_projection(recommendation))
            return recommendations
        except AgentDirectoryError:
            return []
        finally:
            directory.close()

    def _connect(self) -> sqlite3.Connection:
        initialize_database(self.db_path)
        conn = connect(self.db_path)
        migrate_agents(conn)
        migrate_inbox(conn)
        migrate_context(conn)
        migrate_runtime_schema(conn)
        return conn

    def _agents(self, conn: sqlite3.Connection, inbox: list[InboxItem]) -> list[AgentProjection]:
        directory = AgentDirectory(conn=conn)
        inbox_counts: dict[str, dict[str, int]] = {}
        for item in inbox:
            counts = inbox_counts.setdefault(item.agent_id, {})
            counts[item.status] = counts.get(item.status, 0) + 1
        projections: list[AgentProjection] = []
        for identity in directory.list_identities():
            active = directory.get_active_session(identity.agent_id)
            health = directory.get_health(active.session_id) if active is not None else None
            if active is not None:
                active, health = self._with_freshness(active, health)
            projections.append(
                AgentProjection(
                    identity=identity,
                    active_session=active,
                    health=health,
                    capabilities=directory.list_capabilities(identity.agent_id),
                    inbox_counts=inbox_counts.get(identity.agent_id, {}),
                )
            )
        return projections

    def _sessions(self, conn: sqlite3.Connection) -> list[SessionProjection]:
        directory = AgentDirectory(conn=conn)
        projections: list[SessionProjection] = []
        for session in directory.list_all_sessions():
            try:
                health = directory.get_health(session.session_id)
            except AgentDirectoryError:
                health = None
            session, health = self._with_freshness(session, health)
            projections.append(SessionProjection(session=session, health=health))
        return projections

    def _with_freshness(
        self,
        session: AgentSession,
        health: AgentHealth | None,
    ) -> tuple[AgentSession, AgentHealth | None]:
        derived_state = _derive_stale_state(session, self.session_freshness_seconds)
        if derived_state is None:
            return session, health

        age = _age_seconds(session.last_seen_at)
        reason = "missing heartbeat"
        if age is not None:
            reason = f"missing heartbeat: last seen {int(age)}s ago"
        projected_session = session.model_copy(update={"runtime_state": derived_state})
        base_health = health or AgentHealth(
            agent_id=session.agent_id,
            session_id=session.session_id,
            runtime_state=session.runtime_state,
        )
        projected_health = base_health.model_copy(
            update={
                "runtime_state": derived_state,
                "health_score": min(
                    base_health.health_score,
                    _FRESHNESS_HEALTH_SCORES.get(derived_state, base_health.health_score),
                ),
                "stale": True,
                "reason": reason,
                "checked_at": utc_now_iso(),
            }
        )
        return projected_session, projected_health

    def _runs(self, conn: sqlite3.Connection) -> list[RunRecord]:
        rows = conn.execute("select * from runs order by created_at asc, run_id asc").fetchall()
        return [_row_to_run(row) for row in rows]

    def _tasks(self, conn: sqlite3.Connection) -> list[TaskRecord]:
        rows = conn.execute("select * from tasks order by created_at asc, task_id asc").fetchall()
        return [_row_to_task(row) for row in rows]

    def _read_tasks_for_recommendations(self) -> list[TaskRecord]:
        conn = self._connect()
        try:
            return self._tasks(conn)
        finally:
            conn.close()

    def _gates(self, conn: sqlite3.Connection) -> list[GateRecord]:
        rows = conn.execute("select * from gates order by created_at asc, gate_id asc").fetchall()
        return [_row_to_gate(row) for row in rows]

    def _review_findings(self, conn: sqlite3.Connection) -> list[ReviewFinding]:
        rows = conn.execute("select * from review_findings order by created_at asc, finding_id asc").fetchall()
        return [_row_to_finding(row) for row in rows]

    def _contexts(self, conn: sqlite3.Connection) -> list[ContextPacket]:
        rows = conn.execute("select * from context_packets order by created_at asc, packet_id asc").fetchall()
        return [row_to_packet(row) for row in rows]

    def _inbox(self, conn: sqlite3.Connection) -> list[InboxItem]:
        rows = conn.execute("select * from inbox_items order by created_at asc, inbox_id asc").fetchall()
        return [row_to_item(row) for row in rows]

    def _artifacts(self, conn: sqlite3.Connection) -> list[ArtifactRecord]:
        rows = conn.execute("select * from artifacts order by created_at asc, artifact_id asc").fetchall()
        return [_row_to_artifact(row) for row in rows]


def build_operations_projection(
    db_path: str | os.PathLike[str] | None = None,
    *,
    event_limit: int = 200,
    session_freshness_seconds: float | None = None,
) -> OperationsProjection:
    return ProjectionReader(
        db_path,
        session_freshness_seconds=session_freshness_seconds,
    ).build_operations_projection(event_limit=event_limit)


def _build_ui_projection(
    *,
    runs: list[RunRecord],
    tasks: list[TaskRecord],
    gates: list[GateRecord],
    artifacts: list[ArtifactRecord],
    agents: list[AgentProjection],
    contexts: list[ContextPacket],
    inbox: list[InboxItem],
    review_findings: list[ReviewFinding],
) -> UiOperationsProjection:
    active_run = _select_active_run(runs)
    active_run_id = active_run.run_id if active_run else None
    run_tasks = [task for task in tasks if task.run_id == active_run_id] if active_run_id else []
    run_gates = [gate for gate in gates if gate.run_id == active_run_id] if active_run_id else []
    run_artifacts = [
        artifact for artifact in artifacts if artifact.run_id == active_run_id
    ] if active_run_id else []
    return UiOperationsProjection(
        active_run=_build_active_run_projection(active_run, run_tasks),
        metro=_build_metro_projection(active_run, run_tasks, run_gates, run_artifacts),
        action_items=_build_action_items(
            runs=runs,
            tasks=tasks,
            gates=gates,
            artifacts=artifacts,
            agents=agents,
            contexts=contexts,
            inbox=inbox,
            review_findings=review_findings,
        ),
        agent_summaries=_build_agent_summaries(
            agents=agents,
            tasks=tasks,
            gates=gates,
            inbox=inbox,
        ),
        gate_decisions=_build_gate_decisions(gates),
        artifact_summary=_build_artifact_summary(artifacts),
    )


def _select_active_run(runs: list[RunRecord]) -> RunRecord | None:
    if not runs:
        return None
    candidates = [
        run
        for run in runs
        if _normalize_state(run.status) not in {RunState.COMPLETED.value, RunState.FAILED.value}
    ]
    return max(candidates or runs, key=lambda run: (run.updated_at or "", run.created_at or "", run.run_id))


def _build_active_run_projection(
    run: RunRecord | None,
    tasks: list[TaskRecord],
) -> UiActiveRunProjection:
    if run is None:
        return UiActiveRunProjection(progress=_task_progress(tasks))
    return UiActiveRunProjection(
        run_id=run.run_id,
        title=run.title,
        objective=run.objective,
        state=_normalize_state(run.status),
        created_at=run.created_at,
        updated_at=run.updated_at,
        progress=_task_progress(tasks),
    )


def _build_metro_projection(
    run: RunRecord | None,
    tasks: list[TaskRecord],
    gates: list[GateRecord],
    artifacts: list[ArtifactRecord],
) -> UiMetroProjection:
    if run is None:
        return UiMetroProjection()

    nodes: list[UiMetroNode] = []
    edges: list[UiMetroEdge] = []
    main_path: list[str] = []
    branch_groups: dict[str, list[str]] = {}
    current_node_id: str | None = None
    start_node_id = f"run:{run.run_id}:start"
    nodes.append(
        UiMetroNode(
            id=start_node_id,
            kind="start",
            title=run.title,
            subtitle=run.objective or run.run_id,
            state=_normalize_state(run.status),
            tone=_tone_for_state(_normalize_state(run.status), kind="run"),
            run_id=run.run_id,
            route="Runs",
        )
    )
    main_path.append(start_node_id)

    gates_by_task: dict[str, list[GateRecord]] = {}
    for gate in gates:
        if gate.task_id:
            gates_by_task.setdefault(gate.task_id, []).append(gate)

    artifacts_by_task: dict[str, list[ArtifactRecord]] = {}
    unlinked_artifacts: list[ArtifactRecord] = []
    for artifact in artifacts:
        if artifact.task_id:
            artifacts_by_task.setdefault(artifact.task_id, []).append(artifact)
        else:
            unlinked_artifacts.append(artifact)

    previous = start_node_id
    ordered_tasks = sorted(tasks, key=lambda task: (task.created_at, task.task_id))
    for index, task in enumerate(ordered_tasks, start=1):
        task_state = _normalize_state(task.status)
        task_node_id = f"task:{task.task_id}"
        nodes.append(
            UiMetroNode(
                id=task_node_id,
                kind="task",
                title=task.title,
                subtitle=task.task_id,
                state=task_state,
                tone=_tone_for_state(task_state, kind="task"),
                run_id=task.run_id,
                task_id=task.task_id,
                agent_id=task.assignee_agent_id or task.owner_agent_id,
                route="Runs",
                priority=task.priority,
            )
        )
        edges.append(
            UiMetroEdge(
                id=f"edge:{previous}->{task_node_id}",
                source=previous,
                target=task_node_id,
                kind="main",
                tone=_tone_for_state(task_state, kind="task"),
            )
        )
        main_path.append(task_node_id)
        previous = task_node_id
        if current_node_id is None and task_state not in {"completed", "superseded", "failed"}:
            current_node_id = task_node_id

        branch_groups.setdefault(task_node_id, [])
        for gate in sorted(gates_by_task.get(task.task_id, []), key=lambda item: (item.created_at, item.gate_id)):
            gate_state = _normalize_state(gate.state)
            gate_node_id = f"gate:{gate.gate_id}"
            nodes.append(
                UiMetroNode(
                    id=gate_node_id,
                    kind="gate",
                    title=gate.name,
                    subtitle=gate.reason or gate.risk,
                    state=gate_state,
                    tone=_tone_for_state(gate_state, kind="gate"),
                    run_id=gate.run_id,
                    task_id=gate.task_id,
                    gate_id=gate.gate_id,
                    agent_id=gate.owner_agent_id or gate.requested_by,
                    route="Gates",
                    priority=_gate_priority(gate),
                )
            )
            edges.append(
                UiMetroEdge(
                    id=f"edge:{task_node_id}->{gate_node_id}",
                    source=task_node_id,
                    target=gate_node_id,
                    kind="gate",
                    tone=_tone_for_state(gate_state, kind="gate"),
                )
            )
            branch_groups[task_node_id].append(gate_node_id)
            if gate_state in {"open", "escalated"}:
                current_node_id = gate_node_id

        for artifact in sorted(
            artifacts_by_task.get(task.task_id, []),
            key=lambda item: (item.created_at, item.artifact_id),
        ):
            artifact_node_id = f"artifact:{artifact.artifact_id}"
            nodes.append(_artifact_node(artifact, source_task_id=task.task_id))
            edges.append(
                UiMetroEdge(
                    id=f"edge:{task_node_id}->{artifact_node_id}",
                    source=task_node_id,
                    target=artifact_node_id,
                    kind="artifact",
                    tone="good",
                )
            )
            branch_groups[task_node_id].append(artifact_node_id)

    if unlinked_artifacts:
        branch_groups.setdefault(start_node_id, [])
    for artifact in sorted(unlinked_artifacts, key=lambda item: (item.created_at, item.artifact_id)):
        artifact_node = _artifact_node(artifact)
        nodes.append(artifact_node)
        edges.append(
            UiMetroEdge(
                id=f"edge:{start_node_id}->{artifact_node.id}",
                source=start_node_id,
                target=artifact_node.id,
                kind="artifact",
                tone="good",
            )
        )
        branch_groups[start_node_id].append(artifact_node.id)

    if current_node_id is None:
        current_node_id = main_path[-1] if main_path else start_node_id

    return UiMetroProjection(
        nodes=nodes,
        edges=edges,
        main_path_node_ids=main_path,
        current_node_id=current_node_id,
        branch_groups={key: value for key, value in branch_groups.items() if value},
    )


def _artifact_node(artifact: ArtifactRecord, *, source_task_id: str | None = None) -> UiMetroNode:
    title = str(artifact.metadata.get("title") or artifact.metadata.get("summary") or artifact.kind)
    return UiMetroNode(
        id=f"artifact:{artifact.artifact_id}",
        kind="artifact",
        title=title,
        subtitle=artifact.uri,
        state="available",
        tone="good",
        run_id=artifact.run_id,
        task_id=artifact.task_id or source_task_id,
        artifact_id=artifact.artifact_id,
        agent_id=artifact.created_by,
        route="Artifacts",
    )


def _build_action_items(
    *,
    runs: list[RunRecord],
    tasks: list[TaskRecord],
    gates: list[GateRecord],
    artifacts: list[ArtifactRecord],
    agents: list[AgentProjection],
    contexts: list[ContextPacket],
    inbox: list[InboxItem],
    review_findings: list[ReviewFinding],
) -> list[UiActionItem]:
    items: list[UiActionItem] = []

    task_by_id = {task.task_id: task for task in tasks}
    for agent in agents:
        session = agent.active_session
        health = agent.health
        runtime_state = _normalize_state(session.runtime_state) if session else ""
        if runtime_state in {"context_lost", "needs_rehydration", "suspected_stuck", "standby_degraded"} or (
            health and (health.stale or not health.context_valid)
        ):
            active_task = _active_task_for_agent(tasks, agent.identity.agent_id)
            reason = (health.reason if health else None) or runtime_state or "agent health needs review"
            items.append(
                UiActionItem(
                    id=f"agent:{agent.identity.agent_id}",
                    kind="agent_health",
                    title=f"{_agent_display_name(agent)} needs attention",
                    description=reason,
                    tone="bad" if runtime_state in {"context_lost", "needs_rehydration"} else "warn",
                    route="Diagnostics",
                    priority=120,
                    agent_id=agent.identity.agent_id,
                    task_id=active_task.task_id if active_task else None,
                    run_id=active_task.run_id if active_task else session.run_id if session else None,
                    suggested_actions=["probe_agent", "rehydrate", "replace"],
                )
            )

    for task in tasks:
        state = _normalize_state(task.status)
        if state in {"failed", "blocked"}:
            items.append(
                UiActionItem(
                    id=f"task:{task.task_id}",
                    kind="task",
                    title=task.title,
                    description=task.blocked_reason or state,
                    tone="bad" if state == "failed" else "warn",
                    route="Runs",
                    priority=110 if state == "failed" else 100,
                    run_id=task.run_id,
                    task_id=task.task_id,
                    agent_id=task.assignee_agent_id or task.owner_agent_id,
                    created_at=task.updated_at,
                    suggested_actions=["message_controller", "reassign", "request_qa"],
                )
            )

    for gate in gates:
        state = _normalize_state(gate.state)
        if state in {"open", "escalated"}:
            items.append(
                UiActionItem(
                    id=f"gate:{gate.gate_id}",
                    kind="gate",
                    title=gate.name,
                    description=gate.reason or f"{gate.risk} risk gate awaiting decision",
                    tone="bad" if gate.risk == "high" else "warn",
                    route="Gates",
                    priority=95 + _gate_priority(gate),
                    run_id=gate.run_id,
                    task_id=gate.task_id,
                    gate_id=gate.gate_id,
                    agent_id=gate.owner_agent_id or gate.requested_by,
                    created_at=gate.created_at,
                    suggested_actions=["open_gate", "message_controller", "request_qa"],
                )
            )

    for finding in review_findings:
        if _normalize_state(finding.status) == "open":
            items.append(
                UiActionItem(
                    id=f"finding:{finding.finding_id}",
                    kind="review",
                    title=finding.requested_change or finding.category,
                    description=finding.evidence,
                    tone="bad" if finding.blocking else "warn",
                    route="Gates",
                    priority=85 if finding.blocking else 75,
                    run_id=finding.run_id,
                    task_id=finding.task_id,
                    created_at=finding.created_at,
                    suggested_actions=["request_qa", "message_controller"],
                )
            )

    queued_inbox = [item for item in inbox if item.status in {"queued", "delivered"}]
    for item in queued_inbox[:8]:
        task_id = str(item.payload.get("task_id") or "") or None
        task = task_by_id.get(task_id or "")
        items.append(
            UiActionItem(
                id=f"inbox:{item.inbox_id}",
                kind="inbox",
                title=f"{item.kind} for {item.agent_id}",
                description=str(item.payload.get("reason") or item.payload.get("state") or "message waiting"),
                tone="warn",
                route="Communication",
                priority=70 + min(item.priority, 20),
                run_id=str(item.payload.get("run_id") or (task.run_id if task else "") or "") or None,
                task_id=task_id,
                agent_id=item.agent_id,
                created_at=item.created_at,
                suggested_actions=["message_controller", "mark_known"],
            )
        )

    latest_artifact = max(artifacts, key=lambda item: (item.created_at, item.artifact_id), default=None)
    if latest_artifact is not None:
        items.append(
            UiActionItem(
                id=f"artifact:{latest_artifact.artifact_id}",
                kind="artifact",
                title=str(latest_artifact.metadata.get("title") or latest_artifact.kind),
                description=latest_artifact.uri,
                tone="good",
                route="Artifacts",
                priority=40,
                run_id=latest_artifact.run_id,
                task_id=latest_artifact.task_id,
                artifact_id=latest_artifact.artifact_id,
                agent_id=latest_artifact.created_by,
                created_at=latest_artifact.created_at,
                suggested_actions=["view_artifact", "message_controller"],
            )
        )

    active_run = _select_active_run(runs)
    if active_run is not None:
        active_task = next(
            (task for task in tasks if task.run_id == active_run.run_id and _normalize_state(task.status) == "working"),
            None,
        )
        if active_task is not None:
            items.append(
                UiActionItem(
                    id=f"active-task:{active_task.task_id}",
                    kind="task",
                    title=active_task.title,
                    description="Active task is in progress",
                    tone="info",
                    route="Runs",
                    priority=30,
                    run_id=active_task.run_id,
                    task_id=active_task.task_id,
                    agent_id=active_task.assignee_agent_id,
                    created_at=active_task.updated_at,
                    suggested_actions=["message_controller", "request_qa"],
                )
            )

    return sorted(
        items,
        key=lambda item: (item.priority, item.created_at or "", item.id),
        reverse=True,
    )[:20]


def _build_agent_summaries(
    *,
    agents: list[AgentProjection],
    tasks: list[TaskRecord],
    gates: list[GateRecord],
    inbox: list[InboxItem],
) -> list[UiAgentSummary]:
    summaries: list[UiAgentSummary] = []
    for agent in agents:
        session = agent.active_session
        health = agent.health
        runtime_state = _normalize_state(session.runtime_state) if session else "offline"
        task = _active_task_for_agent(tasks, agent.identity.agent_id)
        gate = next(
            (
                gate
                for gate in gates
                if (gate.owner_agent_id == agent.identity.agent_id or gate.requested_by == agent.identity.agent_id)
                and _normalize_state(gate.state) in {"open", "escalated"}
            ),
            None,
        )
        queued = sum(1 for item in inbox if item.agent_id == agent.identity.agent_id and item.status == "queued")
        summaries.append(
            UiAgentSummary(
                agent_id=agent.identity.agent_id,
                display_name=_agent_display_name(agent),
                role=agent.identity.role or "",
                runtime_state=runtime_state,
                tone=_agent_tone(runtime_state, health),
                health_score=health.health_score if health else None,
                stale=bool(health.stale) if health else False,
                current_task_id=task.task_id if task else None,
                current_task_title=task.title if task else None,
                open_gate_id=gate.gate_id if gate else None,
                queued_inbox=queued,
                next_action=_agent_next_action(runtime_state, task, gate, queued, health),
            )
        )
    return summaries


def _build_gate_decisions(gates: list[GateRecord]) -> list[UiGateDecision]:
    decisions = [
        UiGateDecision(
            gate_id=gate.gate_id,
            name=gate.name,
            state=_normalize_state(gate.state),
            risk=gate.risk,
            tone=_tone_for_state(_normalize_state(gate.state), kind="gate"),
            run_id=gate.run_id,
            task_id=gate.task_id,
            owner_agent_id=gate.owner_agent_id,
            requested_by=gate.requested_by,
            reason=gate.reason or "",
            priority=_gate_priority(gate),
        )
        for gate in gates
    ]
    return sorted(decisions, key=lambda item: (item.state not in {"open", "escalated"}, -item.priority, item.gate_id))


def _build_artifact_summary(artifacts: list[ArtifactRecord]) -> UiArtifactSummary:
    by_kind: dict[str, int] = {}
    for artifact in artifacts:
        by_kind[artifact.kind] = by_kind.get(artifact.kind, 0) + 1
    latest = max(artifacts, key=lambda item: (item.created_at, item.artifact_id), default=None)
    return UiArtifactSummary(
        total=len(artifacts),
        by_kind=by_kind,
        latest_artifact_id=latest.artifact_id if latest else None,
        latest_title=str(latest.metadata.get("title") or latest.kind) if latest else "",
        latest_uri=latest.uri if latest else "",
        latest_created_at=latest.created_at if latest else None,
    )


def _task_progress(tasks: list[TaskRecord]) -> dict[str, int]:
    progress = {
        "total": len(tasks),
        "active": 0,
        "blocked": 0,
        "completed": 0,
        "failed": 0,
        "waiting": 0,
    }
    for task in tasks:
        state = _normalize_state(task.status)
        if state in {"assigned", "acknowledged", "working", "reassigned"}:
            progress["active"] += 1
        elif state == "blocked":
            progress["blocked"] += 1
        elif state in {"completed", "superseded"}:
            progress["completed"] += 1
        elif state == "failed":
            progress["failed"] += 1
        else:
            progress["waiting"] += 1
    return progress


def _active_task_for_agent(tasks: list[TaskRecord], agent_id: str) -> TaskRecord | None:
    for task in tasks:
        if task.assignee_agent_id == agent_id and _normalize_state(task.status) in ACTIVE_TASK_STATES:
            return task
    return None


def _agent_display_name(agent: AgentProjection) -> str:
    return agent.identity.display_name or agent.identity.agent_id


def _agent_tone(runtime_state: str, health: AgentHealth | None) -> str:
    if runtime_state in {"context_lost", "needs_rehydration", "suspected_stuck"}:
        return "bad"
    if runtime_state in {"standby_degraded", "input_unavailable"} or (health and health.stale):
        return "warn"
    if runtime_state == "working":
        return "info"
    if runtime_state in {"standby_ready", "waiting_on_bus"}:
        return "good"
    return "neutral"


def _agent_next_action(
    runtime_state: str,
    task: TaskRecord | None,
    gate: GateRecord | None,
    queued: int,
    health: AgentHealth | None,
) -> str:
    if health and health.stale:
        return "probe heartbeat or rehydrate"
    if runtime_state in {"context_lost", "needs_rehydration"}:
        return "rehydrate or replace"
    if gate is not None:
        return "review gate"
    if task is not None:
        return "watch active task"
    if queued:
        return "consume inbox"
    return "standby"


def _gate_priority(gate: GateRecord) -> int:
    risk_weight = {"high": 30, "elevated": 15, "normal": 0}.get((gate.risk or "normal").lower(), 5)
    state_weight = 20 if _normalize_state(gate.state) == "escalated" else 10 if _normalize_state(gate.state) == "open" else 0
    return risk_weight + state_weight


def _tone_for_state(state: str, *, kind: str) -> str:
    value = state.lower()
    if value in {"failed", "rejected", "blocked", "context_lost", "needs_rehydration"}:
        return "bad"
    if value in {"completed", "approved", "resolved", "available", "standby_ready"}:
        return "good"
    if kind == "gate" and value in {"open", "escalated"}:
        return "warn"
    if value in {"created", "assigned", "acknowledged", "working", "active", "reassigned"}:
        return "info"
    if value in {"standby_degraded", "suspected_stuck", "waiting_on_bus", "wait_returned_noop"}:
        return "warn"
    return "neutral"


def _row_to_artifact(row: sqlite3.Row) -> ArtifactRecord:
    return ArtifactRecord(
        artifact_id=row["artifact_id"],
        run_id=row["run_id"],
        task_id=row["task_id"],
        kind=row["kind"],
        uri=row["uri"],
        metadata=json.loads(row["metadata_json"] or "{}"),
        created_by=row["created_by"],
        created_at=row["created_at"],
    )


def build_message_projection(events: list[BusEvent], inbox: list[InboxItem]) -> list[BusMessageProjection]:
    inbox_by_event: dict[str, list[InboxItem]] = {}
    for item in inbox:
        for key in ("event_id", "bus_event_id", "interrupt_event_id"):
            event_id = str(item.payload.get(key) or "")
            if event_id:
                inbox_by_event.setdefault(event_id, []).append(item)

    messages: list[BusMessageProjection] = []
    for event in events:
        event_type = _event_type_value(event)
        if event_type not in MESSAGE_EVENT_TYPES:
            continue

        payload = event.payload or {}
        related_inbox = inbox_by_event.get(event.event_id, [])
        recipients = _message_recipients(payload, related_inbox)
        body = str(payload.get("text") or payload.get("message") or payload.get("summary") or event_type)
        run_id = str(payload.get("run_id") or event.run_id or "") or None
        task_id = str(payload.get("task_id") or event.task_id or "") or None
        gate_id = str(payload.get("gate_id") or "") or None
        artifact_id = str(payload.get("artifact_id") or "") or None
        delivery_state = _message_delivery_state(recipients, related_inbox)
        ack_state = _message_ack_state(recipients, related_inbox)
        message_type = str(payload.get("message_type") or event_type)

        messages.append(
            BusMessageProjection(
                message_id=str(payload.get("message_id") or event.event_id),
                bus_event_id=event.event_id,
                thread_id=str(payload.get("thread_id") or run_id or task_id or "") or None,
                space_id=str(payload.get("space_id") or "runtime"),
                sender_agent_id=event.actor,
                sender_name=event.actor or "system",
                sender_roles=[],
                recipient_agent_ids=recipients,
                message_type=message_type,
                delivery_state=delivery_state,
                ack_state=ack_state,
                reply_state=_message_reply_state(message_type, payload),
                priority=str(payload.get("priority") or "normal"),
                body=body,
                links=BusMessageLink(
                    run_id=run_id,
                    task_ids=[task_id] if task_id else [],
                    gate_ids=[gate_id] if gate_id else [],
                    artifact_ids=[artifact_id] if artifact_id else [],
                ),
                created_at=event.ts,
                updated_at=event.ts,
            )
        )
    return messages


def rebuild_event_state(events: list[BusEvent]) -> EventReplayState:
    state = EventReplayState()
    for event in events:
        payload = dict(event.payload)
        event_type = _event_type_value(event)
        if event_type == "run.created" and "run_id" in payload:
            state.runs[str(payload["run_id"])] = payload
        elif event_type.startswith("task.") and "task_id" in payload:
            state.tasks[str(payload["task_id"])] = payload
            _refresh_replay_run_state(state, payload)
        elif event_type.startswith("gate.") and "gate_id" in payload:
            state.gates[str(payload["gate_id"])] = payload
        elif event_type.startswith("context.") and "packet_id" in payload:
            state.contexts[str(payload["packet_id"])] = payload
            superseded_id = payload.get("supersedes_packet_id")
            if event_type == "context.superseded" and superseded_id and superseded_id in state.contexts:
                state.contexts[str(superseded_id)] = {
                    **state.contexts[str(superseded_id)],
                    "status": "superseded",
                    "superseded_by_packet_id": payload["packet_id"],
                }
        elif event_type.startswith("replacement.") and "recommendation_id" in payload:
            state.replacements[str(payload["recommendation_id"])] = payload
    return state


def recommendation_to_projection(recommendation: ReplacementRecommendation) -> ReplacementRecommendationProjection:
    return ReplacementRecommendationProjection(
        recommendation_id=recommendation.recommendation_id,
        task_id=recommendation.task_id,
        old_session_id=recommendation.old_session_id,
        old_agent_id=recommendation.old_agent_id,
        candidate=ReplacementCandidateProjection(**recommendation.candidate.__dict__),
        triggers=[ReplacementTriggerProjection(**trigger.__dict__) for trigger in recommendation.triggers],
        reason=recommendation.reason,
        run_id=recommendation.run_id,
        required_capabilities=list(recommendation.required_capabilities),
        role=recommendation.role,
        created_at=recommendation.created_at,
    )


def _task_for_agent(tasks: list[TaskRecord], agent_id: str) -> str | None:
    for task in tasks:
        status = task.status.value if hasattr(task.status, "value") else str(task.status)
        if task.assignee_agent_id == agent_id and status in ACTIVE_TASK_STATES:
            return task.task_id
    return None


def _with_projected_gate_owners(gates: list[GateRecord], agents: list[AgentProjection]) -> list[GateRecord]:
    qa_agent_id = _qa_agent_id(agents)
    if qa_agent_id is None:
        return gates
    return [
        gate if gate.owner_agent_id else gate.model_copy(update={"owner_agent_id": qa_agent_id})
        for gate in gates
    ]


def _qa_agent_id(agents: list[AgentProjection]) -> str | None:
    for agent in agents:
        role = (agent.identity.role or "").lower()
        roles = [
            value.strip()
            for value in role.replace("/", ",").replace("|", ",").split(",")
            if value.strip()
        ]
        if role == "qa" or "qa" in roles:
            return agent.identity.agent_id
    return None


def _with_projected_run_states(runs: list[RunRecord], tasks: list[TaskRecord]) -> list[RunRecord]:
    tasks_by_run: dict[str, list[TaskRecord]] = {}
    for task in tasks:
        if task.run_id:
            tasks_by_run.setdefault(task.run_id, []).append(task)

    projected: list[RunRecord] = []
    for run in runs:
        run_tasks = tasks_by_run.get(run.run_id, [])
        next_status = _project_run_state_value(_state_value(run.status), [_state_value(task.status) for task in run_tasks])
        if next_status == _state_value(run.status):
            projected.append(run)
            continue
        updated_at = max([run.updated_at, *(task.updated_at for task in run_tasks if task.updated_at)])
        projected.append(run.model_copy(update={"status": RunState(next_status), "updated_at": updated_at}))
    return projected


def _refresh_replay_run_state(state: EventReplayState, task_payload: dict[str, Any]) -> None:
    run_id = str(task_payload.get("run_id") or "")
    if not run_id:
        return
    run_payload = dict(state.runs.get(run_id) or {"run_id": run_id, "status": RunState.CREATED.value})
    task_payloads = [
        payload
        for payload in state.tasks.values()
        if str(payload.get("run_id") or "") == run_id
    ]
    next_status = _project_run_state_value(
        str(run_payload.get("status") or RunState.CREATED.value),
        [str(payload.get("status") or "") for payload in task_payloads],
    )
    updated_values = [
        str(value)
        for value in [run_payload.get("updated_at"), *(payload.get("updated_at") for payload in task_payloads)]
        if value
    ]
    run_payload["status"] = next_status
    if updated_values:
        run_payload["updated_at"] = max(updated_values)
    state.runs[run_id] = run_payload


def _project_run_state_value(current_status: str, task_statuses: list[str]) -> str:
    normalized = [status for status in (_normalize_state(status) for status in task_statuses) if status]
    current = _normalize_state(current_status) or RunState.CREATED.value
    if current in {RunState.COMPLETED.value, RunState.FAILED.value}:
        return current
    if not normalized:
        return current
    if any(status == "failed" for status in normalized):
        return RunState.FAILED.value
    if all(status in {"completed", "superseded"} for status in normalized):
        return RunState.COMPLETED.value
    if any(status != "created" for status in normalized):
        return RunState.ACTIVE.value
    return current


def _message_recipients(payload: dict[str, Any], related_inbox: list[InboxItem]) -> list[str]:
    recipients = {item.agent_id for item in related_inbox}
    for key in ("recipient_agent_ids", "affected_agents"):
        value = payload.get(key)
        if isinstance(value, str):
            recipients.add(value)
        elif isinstance(value, list):
            recipients.update(str(item) for item in value if item)
    return sorted(recipients)


def _message_delivery_state(recipients: list[str], related_inbox: list[InboxItem]) -> str:
    if any(item.status in {"delivered", "acked"} for item in related_inbox):
        return "delivered"
    return "sent" if recipients else "sent"


def _message_ack_state(recipients: list[str], related_inbox: list[InboxItem]) -> str:
    if related_inbox and all(item.status == "acked" for item in related_inbox):
        return "acked"
    return "waiting_ack" if recipients else "not_required"


def _message_reply_state(message_type: str, payload: dict[str, Any]) -> str:
    explicit = str(payload.get("reply_state") or "")
    if explicit and explicit != "not_required":
        return explicit
    if message_type.lower() in {"question", "request", "request_qa"}:
        return "waiting_reply"
    return explicit or "not_required"


def _event_type_value(event: BusEvent) -> str:
    event_type = event.type.value if hasattr(event.type, "value") else str(event.type)
    if event_type.startswith("EventType."):
        event_type = event_type.split(".", 1)[1]
    return event_type


def _state_value(value: Any) -> str:
    return value.value if hasattr(value, "value") else str(value)


def _normalize_state(value: Any) -> str:
    state = _state_value(value).lower()
    if state.startswith("taskstate.") or state.startswith("runstate."):
        state = state.split(".", 1)[1]
    return state


def _configured_session_freshness_seconds() -> float:
    configured = os.environ.get(SESSION_FRESHNESS_ENV)
    if configured is None:
        return DEFAULT_SESSION_FRESHNESS_SECONDS
    try:
        value = float(configured)
    except ValueError:
        return DEFAULT_SESSION_FRESHNESS_SECONDS
    return value if value > 0 else DEFAULT_SESSION_FRESHNESS_SECONDS


def _derive_stale_state(
    session: AgentSession,
    freshness_seconds: float,
    *,
    now: datetime | None = None,
) -> AgentRuntimeState | None:
    if not session.active or session.ended_at is not None:
        return None
    derived_state = _FRESHNESS_DERIVED_STATES.get(session.runtime_state)
    if derived_state is None:
        return None
    age = _age_seconds(session.last_seen_at, now=now)
    if age is None or age <= freshness_seconds:
        return None
    return derived_state


def _age_seconds(value: str | None, *, now: datetime | None = None) -> float | None:
    if value is None:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    now = now or datetime.now(timezone.utc)
    return max(0.0, (now - parsed).total_seconds())
