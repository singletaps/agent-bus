from __future__ import annotations

import os
import json
import sqlite3
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
    AgentSession,
    ArtifactRecord,
    BusEvent,
    BusMessageLink,
    BusMessageProjection,
    ContextPacket,
    EventType,
    GateRecord,
    InboxItem,
    ReviewFinding,
    RuntimeCondition,
    RunRecord,
    RunState,
    TaskRecord,
    utc_now_iso,
)
from .replacement import InMemoryRehydrationContext, ReplacementCoordinator, ReplacementRecommendation
from .relevance import RelevanceProjection, UiHiddenCounts, derive_relevance_projection
from .reviews import _row_to_finding
from .runtime_state import FreshnessThresholds, RuntimeFacts, derive_runtime_activity
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


class AgentProjection(BaseModel):
    identity: AgentIdentity
    active_session: AgentSession | None = None
    health: AgentHealth | None = None
    capabilities: list[AgentCapability] = Field(default_factory=list)
    inbox_counts: dict[str, int] = Field(default_factory=dict)
    conditions: list[RuntimeCondition] = Field(default_factory=list)


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
    context_packet_id: str | None = None
    claim_id: str | None = None
    recommendation_id: str | None = None
    agent_id: str | None = None
    route: str = "Runs"
    priority: int = 0


class UiMetroEdge(BaseModel):
    id: str
    source: str
    target: str
    kind: str = "main"
    tone: str = "neutral"
    task_id: str | None = None


class UiWorkflowDiagnostic(BaseModel):
    kind: str
    title: str
    detail: str = ""
    tone: str = "warn"
    event_id: str | None = None
    run_id: str | None = None
    task_id: str | None = None


class UiMetroProjection(BaseModel):
    nodes: list[UiMetroNode] = Field(default_factory=list)
    edges: list[UiMetroEdge] = Field(default_factory=list)
    main_path_node_ids: list[str] = Field(default_factory=list)
    current_node_id: str | None = None
    branch_groups: dict[str, list[str]] = Field(default_factory=dict)
    task_ids: list[str] = Field(default_factory=list)
    diagnostics: list[UiWorkflowDiagnostic] = Field(default_factory=list)


class UiTaskWorkflowProjection(UiMetroProjection):
    pass


class UiDiagnosticRecord(BaseModel):
    kind: str
    title: str
    detail: str = ""
    tone: str = "info"
    effect: str = ""
    fencing_result: str = ""
    event_id: str | None = None
    attempted_event_id: str | None = None
    run_id: str | None = None
    task_id: str | None = None
    created_at: str | None = None


class UiDiagnosticsProjection(BaseModel):
    projection_effects: list[UiDiagnosticRecord] = Field(default_factory=list)
    fencing_rejects: list[UiDiagnosticRecord] = Field(default_factory=list)
    protocol_violations: list[UiDiagnosticRecord] = Field(default_factory=list)
    deprecated_adapter_events: list[UiDiagnosticRecord] = Field(default_factory=list)


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
    identity_lifecycle: str = ""
    presence_state: str = ""
    workload_state: str = ""
    ui_visibility_state: str = ""
    conditions: list[RuntimeCondition] = Field(default_factory=list)
    hidden_reason: str = ""


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
    task_workflows: dict[str, UiTaskWorkflowProjection] = Field(default_factory=dict)
    selected_task_id: str | None = None
    selected_task_workflow: UiTaskWorkflowProjection = Field(default_factory=UiTaskWorkflowProjection)
    task_workflow: UiTaskWorkflowProjection = Field(default_factory=UiTaskWorkflowProjection)
    metro: UiTaskWorkflowProjection = Field(default_factory=UiTaskWorkflowProjection)
    action_items: list[UiActionItem] = Field(default_factory=list)
    agent_summaries: list[UiAgentSummary] = Field(default_factory=list)
    visible_agents: list[UiAgentSummary] = Field(default_factory=list)
    archived_agents: list[UiAgentSummary] = Field(default_factory=list)
    gate_decisions: list[UiGateDecision] = Field(default_factory=list)
    actionable_gates: list[UiGateDecision] = Field(default_factory=list)
    historical_gates: list[UiGateDecision] = Field(default_factory=list)
    artifact_summary: UiArtifactSummary = Field(default_factory=UiArtifactSummary)
    current_task_artifacts: list[str] = Field(default_factory=list)
    run_artifacts: list[str] = Field(default_factory=list)
    legacy_unbound_artifacts: list[str] = Field(default_factory=list)
    hidden_counts: UiHiddenCounts = Field(default_factory=UiHiddenCounts)
    diagnostics: UiDiagnosticsProjection = Field(default_factory=UiDiagnosticsProjection)


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
        self.freshness_thresholds = FreshnessThresholds(
            stale_seconds=self.session_freshness_seconds,
            archive_seconds=max(self.session_freshness_seconds * 24, self.session_freshness_seconds + 1),
        )

    def build_operations_projection(self, *, event_limit: int = 200) -> OperationsProjection:
        conn = self._connect()
        try:
            events = EventStore(self.db_path).replay_all()
            limited_events = events[-event_limit:] if event_limit > 0 else []
            runs = self._runs(conn)
            tasks = self._tasks(conn)
            runs = _with_projected_run_states(runs, tasks)
            durable_gates = self._gates(conn)
            findings = self._review_findings(conn)
            contexts = self._contexts(conn)
            inbox = self._inbox(conn)
            artifacts = self._artifacts(conn)
            protocol_violations = self._protocol_violations(conn)
            projection_effects = self._projection_effects(conn)
            agents = self._agents(conn, inbox, tasks=tasks, gates=durable_gates)
            gates = _with_projected_gate_owners(durable_gates, agents)
            sessions = self._sessions(conn, tasks=tasks, gates=durable_gates, inbox=inbox)
            recommendations = self.replacement_recommendations(tasks=tasks)
            last_seq = max((event.seq or 0 for event in events), default=0)
            active_run = _select_active_run(runs)
            # Relevance consumes durable gate ownership. The projected QA owner is display-only.
            relevance = derive_relevance_projection(
                active_run=active_run,
                runs=runs,
                tasks=tasks,
                gates=durable_gates,
                artifacts=artifacts,
                agents=agents,
                contexts=contexts,
                inbox=inbox,
            )
            ui = _build_ui_projection(
                active_run=active_run,
                relevance=relevance,
                runs=runs,
                tasks=tasks,
                gates=gates,
                artifacts=artifacts,
                agents=agents,
                contexts=contexts,
                inbox=inbox,
                review_findings=findings,
                events=events,
                protocol_violations=protocol_violations,
                projection_effects=projection_effects,
            )
            visible_agent_ids = {
                agent_id for agent_id, projection in relevance.agents.items() if projection.visible_in_main
            }
            visible_artifact_count = sum(
                1
                for projection in relevance.artifacts.values()
                if projection.visible_in_default_list and projection.visibility in {"current_task", "run"}
            )
            visible_queued_inbox = sum(
                1
                for item in inbox
                if item.status == "queued" and (item.agent_id in visible_agent_ids or item.agent_id not in relevance.agents)
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
                    "agents": len(visible_agent_ids),
                    "sessions": len(sessions),
                    "runs": len(runs),
                    "tasks": len(tasks),
                    "open_gates": sum(1 for gate in relevance.gates.values() if gate.visible_in_approval_center),
                    "open_findings": sum(1 for finding in findings if finding.status == "open"),
                    "active_contexts": sum(1 for packet in contexts if packet.status == "active"),
                    "context_faults": relevance.hidden_counts.hidden_context_packets,
                    "pending_inbox": visible_queued_inbox,
                    "queued_inbox": visible_queued_inbox,
                    "artifacts": visible_artifact_count,
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

    def _agents(
        self,
        conn: sqlite3.Connection,
        inbox: list[InboxItem],
        *,
        tasks: list[TaskRecord],
        gates: list[GateRecord],
    ) -> list[AgentProjection]:
        directory = AgentDirectory(conn=conn)
        inbox_counts: dict[str, dict[str, int]] = {}
        for item in inbox:
            counts = inbox_counts.setdefault(item.agent_id, {})
            counts[item.status] = counts.get(item.status, 0) + 1
        projections: list[AgentProjection] = []
        for identity in directory.list_identities():
            active = directory.get_active_session(identity.agent_id)
            health = directory.get_health(active.session_id) if active is not None else None
            conditions: list[RuntimeCondition] = []
            if active is not None:
                active, health, conditions = self._with_freshness(
                    active,
                    health,
                    has_active_responsibility=_agent_has_active_responsibility(identity.agent_id, tasks, gates, inbox),
                )
            projections.append(
                AgentProjection(
                    identity=identity,
                    active_session=active,
                    health=health,
                    capabilities=directory.list_capabilities(identity.agent_id),
                    inbox_counts=inbox_counts.get(identity.agent_id, {}),
                    conditions=conditions,
                )
            )
        return projections

    def _sessions(
        self,
        conn: sqlite3.Connection,
        *,
        tasks: list[TaskRecord],
        gates: list[GateRecord],
        inbox: list[InboxItem],
    ) -> list[SessionProjection]:
        directory = AgentDirectory(conn=conn)
        projections: list[SessionProjection] = []
        for session in directory.list_all_sessions():
            try:
                health = directory.get_health(session.session_id)
            except AgentDirectoryError:
                health = None
            session, health, _conditions = self._with_freshness(
                session,
                health,
                has_active_responsibility=_agent_has_active_responsibility(session.agent_id, tasks, gates, inbox),
            )
            projections.append(SessionProjection(session=session, health=health))
        return projections

    def _with_freshness(
        self,
        session: AgentSession,
        health: AgentHealth | None,
        *,
        has_active_responsibility: bool,
    ) -> tuple[AgentSession, AgentHealth | None, list[RuntimeCondition]]:
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
        projected_session = session.model_copy(update={"runtime_state": runtime.runtime_state})
        base_health = health or AgentHealth(
            agent_id=session.agent_id,
            session_id=session.session_id,
            runtime_state=session.runtime_state,
        )
        reason = base_health.reason
        if runtime.stale and "heartbeat" in runtime.reason:
            reason = f"missing heartbeat: {runtime.reason}"
        elif runtime.reason != "fresh":
            reason = runtime.reason
        projected_health = base_health.model_copy(
            update={
                "runtime_state": runtime.runtime_state,
                "health_score": min(base_health.health_score, runtime.health_score),
                "stale": runtime.stale,
                "reason": reason,
                "checked_at": utc_now_iso(),
            }
        )
        return projected_session, projected_health, list(runtime.conditions.values())

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

    def _protocol_violations(self, conn: sqlite3.Connection) -> list[sqlite3.Row]:
        if not _has_table(conn, "protocol_violations"):
            return []
        return conn.execute(
            """
            select * from protocol_violations
            order by created_at desc, violation_id desc
            limit 80
            """
        ).fetchall()

    def _projection_effects(self, conn: sqlite3.Connection) -> list[sqlite3.Row]:
        if not _has_table(conn, "projection_effects"):
            return []
        return conn.execute(
            """
            select * from projection_effects
            order by created_at desc, effect_id desc
            limit 120
            """
        ).fetchall()


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
    active_run: RunRecord | None,
    relevance: RelevanceProjection,
    runs: list[RunRecord],
    tasks: list[TaskRecord],
    gates: list[GateRecord],
    artifacts: list[ArtifactRecord],
    agents: list[AgentProjection],
    contexts: list[ContextPacket],
    inbox: list[InboxItem],
    review_findings: list[ReviewFinding],
    events: list[BusEvent],
    protocol_violations: list[sqlite3.Row],
    projection_effects: list[sqlite3.Row],
) -> UiOperationsProjection:
    active_run_id = active_run.run_id if active_run else None
    run_tasks = [task for task in tasks if task.run_id == active_run_id] if active_run_id else []
    run_gates = [gate for gate in gates if gate.run_id == active_run_id] if active_run_id else []
    run_artifacts = [
        artifact for artifact in artifacts if artifact.run_id == active_run_id
    ] if active_run_id else []
    task_workflows = _build_task_workflow_map(
        active_run,
        run_tasks,
        run_gates,
        run_artifacts,
        contexts,
        events,
    )
    selected_task_id = _select_selected_workflow_task_id(run_tasks, run_gates, task_workflows)
    selected_task_workflow = (
        task_workflows.get(selected_task_id)
        if selected_task_id is not None
        else None
    ) or UiTaskWorkflowProjection()
    legacy_metro = _build_task_workflow_projection(
        active_run,
        run_tasks,
        run_gates,
        run_artifacts,
        contexts,
        events,
    )
    agent_summaries = _build_agent_summaries(
        agents=agents,
        tasks=tasks,
        gates=gates,
        inbox=inbox,
        relevance=relevance,
    )
    agent_summaries_by_id = {agent.agent_id: agent for agent in agent_summaries}
    visible_agents = [
        agent_summaries_by_id[agent_id]
        for agent_id, projection in relevance.agents.items()
        if projection.visible_in_main and agent_id in agent_summaries_by_id
    ]
    archived_agents = [
        agent_summaries_by_id[agent_id]
        for agent_id, projection in relevance.agents.items()
        if not projection.visible_in_main and agent_id in agent_summaries_by_id
    ]
    gate_decisions = _build_gate_decisions(gates)
    actionable_gate_ids = {
        gate_id for gate_id, projection in relevance.gates.items() if projection.visible_in_approval_center
    }
    actionable_gates = [gate for gate in gate_decisions if gate.gate_id in actionable_gate_ids]
    historical_gates = [gate for gate in gate_decisions if gate.gate_id not in actionable_gate_ids]
    current_task_artifacts = _artifact_ids_for_visibility(relevance, "current_task")
    run_artifacts_for_ui = _artifact_ids_for_visibility(relevance, "run")
    legacy_unbound_artifacts = _artifact_ids_for_visibility(relevance, "legacy_unbound")
    return UiOperationsProjection(
        active_run=_build_active_run_projection(active_run, run_tasks),
        task_workflows=task_workflows,
        selected_task_id=selected_task_id,
        selected_task_workflow=selected_task_workflow,
        task_workflow=legacy_metro,
        metro=legacy_metro,
        action_items=_build_action_items(
            runs=runs,
            tasks=tasks,
            gates=gates,
            artifacts=artifacts,
            agents=agents,
            contexts=contexts,
            inbox=inbox,
            review_findings=review_findings,
            relevance=relevance,
        ),
        agent_summaries=agent_summaries,
        visible_agents=visible_agents,
        archived_agents=archived_agents,
        gate_decisions=gate_decisions,
        actionable_gates=actionable_gates,
        historical_gates=historical_gates,
        artifact_summary=_build_artifact_summary(artifacts),
        current_task_artifacts=current_task_artifacts,
        run_artifacts=run_artifacts_for_ui,
        legacy_unbound_artifacts=legacy_unbound_artifacts,
        hidden_counts=relevance.hidden_counts,
        diagnostics=_build_diagnostics_projection(
            events=events,
            workflow_diagnostics=_unique_workflow_diagnostics(
                [legacy_metro, *task_workflows.values()]
            ),
            protocol_violations=protocol_violations,
            projection_effects=projection_effects,
        ),
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


def _build_task_workflow_map(
    run: RunRecord | None,
    tasks: list[TaskRecord],
    gates: list[GateRecord],
    artifacts: list[ArtifactRecord],
    contexts: list[ContextPacket],
    events: list[BusEvent],
) -> dict[str, UiTaskWorkflowProjection]:
    if run is None:
        return {}

    workflows: dict[str, UiTaskWorkflowProjection] = {}
    ordered_tasks = sorted(tasks, key=lambda task: (task.created_at, task.task_id))
    for task in ordered_tasks:
        workflows[task.task_id] = _build_task_workflow_projection(
            run,
            [task],
            [gate for gate in gates if gate.task_id == task.task_id],
            [artifact for artifact in artifacts if artifact.task_id == task.task_id],
            contexts,
            _events_for_task_workflow(events, task.task_id),
        )
    return workflows


def _unique_workflow_diagnostics(
    workflows: list[UiTaskWorkflowProjection],
) -> list[UiWorkflowDiagnostic]:
    diagnostics: list[UiWorkflowDiagnostic] = []
    seen: set[tuple[str, str, str, str]] = set()
    for workflow in workflows:
        for diagnostic in workflow.diagnostics:
            key = (
                diagnostic.kind,
                diagnostic.detail,
                diagnostic.event_id or "",
                diagnostic.task_id or "",
            )
            if key in seen:
                continue
            seen.add(key)
            diagnostics.append(diagnostic)
    return diagnostics


def _events_for_task_workflow(events: list[BusEvent], task_id: str) -> list[BusEvent]:
    scoped: list[BusEvent] = []
    for event in events:
        if _workflow_event_kind(event) is None:
            continue
        payload_task_id = str((event.payload or {}).get("task_id") or "")
        event_task_id = str(event.task_id or "")
        if task_id in {payload_task_id, event_task_id}:
            scoped.append(event)
    return scoped


def _select_selected_workflow_task_id(
    tasks: list[TaskRecord],
    gates: list[GateRecord],
    task_workflows: dict[str, UiTaskWorkflowProjection],
) -> str | None:
    if not task_workflows:
        return None

    open_gate = next(
        (
            gate
            for gate in sorted(gates, key=lambda item: (_gate_priority(item), item.created_at, item.gate_id), reverse=True)
            if gate.task_id in task_workflows and _normalize_state(gate.state) in {"open", "escalated"}
        ),
        None,
    )
    if open_gate is not None:
        return open_gate.task_id

    active_task = next(
        (
            task
            for task in sorted(tasks, key=lambda item: (item.updated_at, item.created_at, item.task_id), reverse=True)
            if task.task_id in task_workflows
            and _normalize_state(task.status) in {"blocked", "working", "assigned", "acknowledged", "reassigned"}
        ),
        None,
    )
    if active_task is not None:
        return active_task.task_id

    return next(iter(task_workflows))


def _build_task_workflow_projection(
    run: RunRecord | None,
    tasks: list[TaskRecord],
    gates: list[GateRecord],
    artifacts: list[ArtifactRecord],
    contexts: list[ContextPacket],
    events: list[BusEvent],
) -> UiTaskWorkflowProjection:
    if run is None:
        return UiTaskWorkflowProjection()

    nodes: list[UiMetroNode] = []
    edges: list[UiMetroEdge] = []
    main_path: list[str] = []
    branch_groups: dict[str, list[str]] = {}
    current_node_id: str | None = None
    task_ids = [task.task_id for task in sorted(tasks, key=lambda item: (item.created_at, item.task_id))]
    task_id_set = set(task_ids)
    event_branches, diagnostics = _task_bound_workflow_events(events, task_id_set)
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

    contexts_by_task: dict[str, list[ContextPacket]] = {}
    for packet in contexts:
        if packet.task_id in task_id_set:
            contexts_by_task.setdefault(str(packet.task_id), []).append(packet)

    artifacts_by_task: dict[str, list[ArtifactRecord]] = {}
    unlinked_artifacts: list[ArtifactRecord] = []
    for artifact in artifacts:
        if artifact.task_id in task_id_set:
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
                task_id=task.task_id,
            )
        )
        main_path.append(task_node_id)
        previous = task_node_id
        if current_node_id is None and task_state not in {"completed", "superseded", "failed"}:
            current_node_id = task_node_id

        branch_groups.setdefault(task_node_id, [])
        task_contexts = sorted(
            contexts_by_task.get(task.task_id, []),
            key=lambda item: (item.created_at, item.packet_id),
        )
        active_contexts = [packet for packet in task_contexts if _normalize_state(packet.status) == "active"]
        latest_active_context = active_contexts[-1] if active_contexts else None
        hidden_contexts = [
            packet for packet in task_contexts if latest_active_context is None or packet.packet_id != latest_active_context.packet_id
        ]
        if latest_active_context is not None:
            packet = latest_active_context
            context_node_id = f"context:{packet.packet_id}"
            nodes.append(
                UiMetroNode(
                    id=context_node_id,
                    kind="context",
                    title="上下文",
                    subtitle=packet.summary or packet.packet_id,
                    state=packet.status,
                    tone=_tone_for_state(packet.status, kind="context"),
                    run_id=packet.run_id,
                    task_id=packet.task_id,
                    context_packet_id=packet.packet_id,
                    agent_id=packet.agent_id,
                    route="Diagnostics",
                    priority=35,
                )
            )
            edges.append(
                UiMetroEdge(
                    id=f"edge:{task_node_id}->{context_node_id}",
                    source=task_node_id,
                    target=context_node_id,
                    kind="context",
                    tone=_tone_for_state(packet.status, kind="context"),
                    task_id=task.task_id,
                )
            )
            branch_groups[task_node_id].append(context_node_id)

        if hidden_contexts:
            latest_context = hidden_contexts[-1]
            context_cluster_id = f"cluster:context_history:{task.task_id}"
            nodes.append(
                _cluster_node(
                    id=context_cluster_id,
                    kind="cluster:context_history",
                    title="Context history",
                    count=len(hidden_contexts),
                    state=_normalize_state(latest_context.status),
                    subtitle=f"{len(hidden_contexts)} context packets collapsed",
                    tone=_tone_for_state(latest_context.status, kind="context"),
                    run_id=latest_context.run_id,
                    task_id=task.task_id,
                    context_packet_id=latest_context.packet_id,
                    agent_id=latest_context.agent_id,
                    route="Diagnostics",
                    priority=34,
                )
            )
            edges.append(
                UiMetroEdge(
                    id=f"edge:{task_node_id}->{context_cluster_id}",
                    source=task_node_id,
                    target=context_cluster_id,
                    kind="context",
                    tone=_tone_for_state(latest_context.status, kind="context"),
                    task_id=task.task_id,
                )
            )
            branch_groups[task_node_id].append(context_cluster_id)

        task_events = event_branches.get(task.task_id, [])
        replacement_events = [event for event in task_events if _workflow_event_kind(event) == "replacement"]
        non_replacement_events = [event for event in task_events if _workflow_event_kind(event) != "replacement"]
        if replacement_events:
            latest_replacement_node = _event_workflow_node(replacement_events[-1])
            replacement_cluster_id = f"cluster:replacement:{task.task_id}"
            nodes.append(
                _cluster_node(
                    id=replacement_cluster_id,
                    kind="cluster:replacement",
                    title="Replacement & Recovery",
                    count=len(replacement_events),
                    state=latest_replacement_node.state,
                    subtitle=f"{len(replacement_events)} replacement events collapsed",
                    tone=latest_replacement_node.tone,
                    run_id=latest_replacement_node.run_id,
                    task_id=task.task_id,
                    recommendation_id=latest_replacement_node.recommendation_id,
                    agent_id=latest_replacement_node.agent_id,
                    route="Diagnostics",
                    priority=latest_replacement_node.priority,
                )
            )
            edges.append(
                UiMetroEdge(
                    id=f"edge:{task_node_id}->{replacement_cluster_id}",
                    source=task_node_id,
                    target=replacement_cluster_id,
                    kind="replacement",
                    tone=latest_replacement_node.tone,
                    task_id=task.task_id,
                )
            )
            branch_groups[task_node_id].append(replacement_cluster_id)

        task_diagnostics = [diagnostic for diagnostic in diagnostics if diagnostic.task_id == task.task_id]
        if task_diagnostics:
            latest_diagnostic = task_diagnostics[-1]
            diagnostics_cluster_id = f"cluster:protocol_diagnostics:{task.task_id}"
            nodes.append(
                _cluster_node(
                    id=diagnostics_cluster_id,
                    kind="cluster:protocol_diagnostics",
                    title="Protocol diagnostics",
                    count=len(task_diagnostics),
                    state=latest_diagnostic.kind,
                    subtitle=f"{len(task_diagnostics)} diagnostics collapsed",
                    tone=latest_diagnostic.tone,
                    run_id=latest_diagnostic.run_id,
                    task_id=task.task_id,
                    route="Diagnostics",
                    priority=30,
                )
            )
            edges.append(
                UiMetroEdge(
                    id=f"edge:{task_node_id}->{diagnostics_cluster_id}",
                    source=task_node_id,
                    target=diagnostics_cluster_id,
                    kind="diagnostics",
                    tone=latest_diagnostic.tone,
                    task_id=task.task_id,
                )
            )
            branch_groups[task_node_id].append(diagnostics_cluster_id)

        for event in non_replacement_events:
            event_node = _event_workflow_node(event)
            nodes.append(event_node)
            edges.append(
                UiMetroEdge(
                    id=f"edge:{task_node_id}->{event_node.id}",
                    source=task_node_id,
                    target=event_node.id,
                    kind=event_node.kind,
                    tone=event_node.tone,
                    task_id=task.task_id,
                )
            )
            branch_groups[task_node_id].append(event_node.id)

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
                    task_id=task.task_id,
                )
            )
            branch_groups[task_node_id].append(gate_node_id)
            if gate_state in {"open", "escalated"}:
                current_node_id = gate_node_id

        task_artifacts = sorted(
            artifacts_by_task.get(task.task_id, []),
            key=lambda item: (item.created_at, item.artifact_id),
        )
        latest_task_artifact = task_artifacts[-1] if task_artifacts else None
        if latest_task_artifact is not None:
            artifact = latest_task_artifact
            artifact_node_id = f"artifact:{artifact.artifact_id}"
            nodes.append(_artifact_node(artifact, source_task_id=task.task_id))
            edges.append(
                UiMetroEdge(
                    id=f"edge:{task_node_id}->{artifact_node_id}",
                    source=task_node_id,
                    target=artifact_node_id,
                    kind="artifact",
                    tone="good",
                    task_id=task.task_id,
                )
            )
            branch_groups[task_node_id].append(artifact_node_id)

        hidden_artifacts = task_artifacts[:-1]
        if hidden_artifacts:
            latest_hidden_artifact = hidden_artifacts[-1]
            artifact_cluster_id = f"cluster:artifacts:{task.task_id}"
            nodes.append(
                _cluster_node(
                    id=artifact_cluster_id,
                    kind="cluster:artifacts",
                    title="Artifact history",
                    count=len(hidden_artifacts),
                    state="available",
                    subtitle=f"{len(hidden_artifacts)} artifacts collapsed",
                    tone="good",
                    run_id=latest_hidden_artifact.run_id,
                    task_id=task.task_id,
                    artifact_id=latest_hidden_artifact.artifact_id,
                    agent_id=latest_hidden_artifact.created_by,
                    route="Artifacts",
                    priority=24,
                )
            )
            edges.append(
                UiMetroEdge(
                    id=f"edge:{task_node_id}->{artifact_cluster_id}",
                    source=task_node_id,
                    target=artifact_cluster_id,
                    kind="artifact",
                    tone="good",
                    task_id=task.task_id,
                )
            )
            branch_groups[task_node_id].append(artifact_cluster_id)

        if task_state in {"completed", "failed", "superseded"}:
            terminal_node_id = f"terminal:{task.task_id}:{task_state}"
            nodes.append(
                UiMetroNode(
                    id=terminal_node_id,
                    kind="terminal",
                    title=_terminal_title(task_state),
                    subtitle=task.updated_at,
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
                    id=f"edge:{task_node_id}->{terminal_node_id}",
                    source=task_node_id,
                    target=terminal_node_id,
                    kind="terminal",
                    tone=_tone_for_state(task_state, kind="task"),
                    task_id=task.task_id,
                )
            )
            branch_groups[task_node_id].append(terminal_node_id)

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
                task_id=artifact_node.task_id,
            )
        )
        branch_groups[start_node_id].append(artifact_node.id)

    if current_node_id is None:
        current_node_id = main_path[-1] if main_path else start_node_id

    return UiTaskWorkflowProjection(
        nodes=nodes,
        edges=edges,
        main_path_node_ids=main_path,
        current_node_id=current_node_id,
        branch_groups={key: value for key, value in branch_groups.items() if value},
        task_ids=task_ids,
        diagnostics=diagnostics,
    )


def _cluster_node(
    *,
    id: str,
    kind: str,
    title: str,
    count: int,
    state: str,
    subtitle: str,
    tone: str,
    route: str,
    priority: int,
    run_id: str | None = None,
    task_id: str | None = None,
    gate_id: str | None = None,
    artifact_id: str | None = None,
    context_packet_id: str | None = None,
    recommendation_id: str | None = None,
    agent_id: str | None = None,
) -> UiMetroNode:
    return UiMetroNode(
        id=id,
        kind=kind,
        title=f"{title} x {count}",
        subtitle=subtitle,
        state=state,
        tone=tone,
        run_id=run_id,
        task_id=task_id,
        gate_id=gate_id,
        artifact_id=artifact_id,
        context_packet_id=context_packet_id,
        recommendation_id=recommendation_id,
        agent_id=agent_id,
        route=route,
        priority=priority,
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


def _task_bound_workflow_events(
    events: list[BusEvent],
    task_ids: set[str],
) -> tuple[dict[str, list[BusEvent]], list[UiWorkflowDiagnostic]]:
    branches: dict[str, list[BusEvent]] = {}
    diagnostics: list[UiWorkflowDiagnostic] = []

    for event in events:
        kind = _workflow_event_kind(event)
        if kind is None:
            continue

        payload = event.payload or {}
        event_task_id = str(event.task_id or "")
        payload_task_id = str(payload.get("task_id") or "")
        if event_task_id and payload_task_id and event_task_id != payload_task_id:
            diagnostics.append(
                UiWorkflowDiagnostic(
                    kind="protocol_violation",
                    title="跨任务边已丢弃",
                    detail=(
                        "cross-task workflow edge dropped: "
                        f"event task_id={event_task_id}, payload task_id={payload_task_id}"
                    ),
                    event_id=event.event_id,
                    run_id=event.run_id,
                    task_id=event_task_id,
                )
            )
            continue

        task_id = event_task_id or payload_task_id
        if not task_id:
            continue
        if task_id not in task_ids:
            diagnostics.append(
                UiWorkflowDiagnostic(
                    kind="protocol_violation",
                    title="未知任务边已丢弃",
                    detail=f"workflow event {event.event_id} references unknown task_id={task_id}",
                    event_id=event.event_id,
                    run_id=event.run_id,
                    task_id=task_id,
                )
            )
            continue
        branches.setdefault(task_id, []).append(event)

    for task_events in branches.values():
        task_events.sort(key=lambda item: (item.ts or "", item.seq or 0, item.event_id))
    return branches, diagnostics


def _workflow_event_kind(event: BusEvent) -> str | None:
    event_type = _event_type_value(event)
    if event_type in {
        EventType.TASK_ACK_CLAIMED.value,
        EventType.TASK_PROGRESS_REPORTED.value,
        EventType.TASK_BLOCKER_REPORTED.value,
        EventType.TASK_COMPLETION_CLAIMED.value,
        EventType.TASK_FAILURE_CLAIMED.value,
        EventType.ARTIFACT_PRODUCED.value,
    }:
        return "claim"
    if event_type.startswith("replacement."):
        return "replacement"
    if event_type in {
        EventType.TASK_COMPLETED.value,
        EventType.TASK_FAILED.value,
        EventType.TASK_SUPERSEDED.value,
    }:
        return "terminal"
    return None


def _event_workflow_node(event: BusEvent) -> UiMetroNode:
    kind = _workflow_event_kind(event) or "claim"
    event_type = _event_type_value(event)
    payload = event.payload or {}
    state = str(payload.get("status") or payload.get("state") or event_type.rsplit(".", 1)[-1])
    task_id = str(event.task_id or payload.get("task_id") or "") or None
    recommendation_id = str(payload.get("recommendation_id") or "") or None
    return UiMetroNode(
        id=f"event:{event.event_id}",
        kind=kind,
        title=_workflow_event_title(event_type, kind),
        subtitle=str(payload.get("summary") or payload.get("reason") or event.actor or event_type),
        state=state,
        tone=_workflow_event_tone(kind, state, event_type),
        run_id=event.run_id or str(payload.get("run_id") or "") or None,
        task_id=task_id,
        artifact_id=event.artifact_id or str(payload.get("artifact_id") or "") or None,
        claim_id=str(payload.get("claim_id") or payload.get("created_from_event_id") or "") or None,
        recommendation_id=recommendation_id,
        agent_id=event.agent_id or event.actor,
        route="Runs" if kind == "terminal" else "Diagnostics",
        priority=45 if kind == "replacement" else 40,
    )


def _workflow_event_title(event_type: str, kind: str) -> str:
    labels = {
        EventType.TASK_ACK_CLAIMED.value: "认领声明",
        EventType.TASK_PROGRESS_REPORTED.value: "进展声明",
        EventType.TASK_BLOCKER_REPORTED.value: "阻塞声明",
        EventType.TASK_COMPLETION_CLAIMED.value: "完成声明",
        EventType.TASK_FAILURE_CLAIMED.value: "失败声明",
        EventType.ARTIFACT_PRODUCED.value: "产物声明",
        EventType.TASK_COMPLETED.value: "完成终点",
        EventType.TASK_FAILED.value: "失败终点",
        EventType.TASK_SUPERSEDED.value: "替换终点",
    }
    if event_type in labels:
        return labels[event_type]
    if kind == "replacement":
        return "替换"
    if kind == "terminal":
        return "终点"
    return "声明"


def _workflow_event_tone(kind: str, state: str, event_type: str) -> str:
    if kind == "terminal":
        return _tone_for_state(state, kind="task")
    if event_type in {EventType.TASK_BLOCKER_REPORTED.value, EventType.TASK_FAILURE_CLAIMED.value}:
        return "bad"
    if event_type == EventType.TASK_COMPLETION_CLAIMED.value:
        return "warn"
    if kind == "replacement":
        return "warn"
    return "info"


def _terminal_title(task_state: str) -> str:
    if task_state == "failed":
        return "失败终点"
    if task_state == "superseded":
        return "替换终点"
    return "完成终点"


def _build_diagnostics_projection(
    *,
    events: list[BusEvent],
    workflow_diagnostics: list[UiWorkflowDiagnostic],
    protocol_violations: list[sqlite3.Row],
    projection_effects: list[sqlite3.Row],
) -> UiDiagnosticsProjection:
    protocol_records = [_diagnostic_from_protocol_violation(row) for row in protocol_violations]
    protocol_records.extend(_diagnostic_from_workflow(item) for item in workflow_diagnostics)

    effect_records = [_diagnostic_from_projection_effect(row) for row in projection_effects]
    fencing_rejects = [
        item
        for item in protocol_records
        if _is_fencing_reject(item.fencing_result)
    ]
    fencing_rejects.extend(
        _diagnostic_from_fenced_event(event)
        for event in events
        if _is_fencing_reject(_string_value(event.fencing_result))
    )

    deprecated_adapter_events = [
        _diagnostic_from_deprecated_adapter(event)
        for event in events
        if _event_type_value(event) == EventType.ADAPTER_DEPRECATED_PATH_USED.value
    ]

    return UiDiagnosticsProjection(
        projection_effects=effect_records,
        fencing_rejects=fencing_rejects,
        protocol_violations=protocol_records,
        deprecated_adapter_events=deprecated_adapter_events,
    )


def _diagnostic_from_protocol_violation(row: sqlite3.Row) -> UiDiagnosticRecord:
    return UiDiagnosticRecord(
        kind="protocol_violation",
        title=_row_text(row, "action") or "协议违规",
        detail=_row_text(row, "reason"),
        tone="bad",
        effect=_row_text(row, "projection_effect"),
        fencing_result=_row_text(row, "fencing_result"),
        attempted_event_id=_row_text(row, "attempted_event_id"),
        run_id=_row_text(row, "run_id") or None,
        task_id=_row_text(row, "task_id") or None,
        created_at=_row_text(row, "created_at") or None,
    )


def _diagnostic_from_projection_effect(row: sqlite3.Row) -> UiDiagnosticRecord:
    effect = _row_text(row, "effect")
    target = _row_text(row, "target_id") or _row_text(row, "attempted_event_id") or _row_text(row, "event_id")
    return UiDiagnosticRecord(
        kind="projection_effect",
        title=effect or "投影效果",
        detail=_row_text(row, "reason") or target,
        tone="bad" if effect == "REJECT" else "warn" if effect == "AUDIT_ONLY" else "good",
        effect=effect,
        event_id=_row_text(row, "event_id") or None,
        attempted_event_id=_row_text(row, "attempted_event_id") or None,
        run_id=_row_text(row, "run_id") or None,
        task_id=_row_text(row, "task_id") or None,
        created_at=_row_text(row, "created_at") or None,
    )


def _diagnostic_from_workflow(item: UiWorkflowDiagnostic) -> UiDiagnosticRecord:
    return UiDiagnosticRecord(
        kind=item.kind,
        title=item.title,
        detail=item.detail,
        tone=item.tone,
        event_id=item.event_id,
        run_id=item.run_id,
        task_id=item.task_id,
    )


def _diagnostic_from_fenced_event(event: BusEvent) -> UiDiagnosticRecord:
    return UiDiagnosticRecord(
        kind="fencing_reject",
        title=_event_type_value(event),
        detail=str((event.payload or {}).get("reason") or "fencing rejected event"),
        tone="bad",
        effect=_string_value(event.projection_effect),
        fencing_result=_string_value(event.fencing_result),
        event_id=event.event_id,
        run_id=event.run_id,
        task_id=event.task_id,
        created_at=event.ts,
    )


def _diagnostic_from_deprecated_adapter(event: BusEvent) -> UiDiagnosticRecord:
    payload = event.payload or {}
    path = str(payload.get("path") or payload.get("deprecated_path") or _event_type_value(event))
    replacement = str(payload.get("replacement") or payload.get("replacement_path") or "")
    detail = f"{path} -> {replacement}" if replacement else path
    return UiDiagnosticRecord(
        kind="deprecated_adapter",
        title="旧适配器路径",
        detail=detail,
        tone="warn",
        effect=_string_value(event.projection_effect),
        fencing_result=_string_value(event.fencing_result),
        event_id=event.event_id,
        run_id=event.run_id,
        task_id=event.task_id,
        created_at=event.ts,
    )


def _is_fencing_reject(value: str | None) -> bool:
    normalized = (value or "").upper()
    return normalized not in {"", "VALID", "NOT_REQUIRED"}


def _row_text(row: sqlite3.Row, key: str) -> str:
    if key not in row.keys():
        return ""
    value = row[key]
    return _string_value(value)


def _string_value(value: Any) -> str:
    if value is None:
        return ""
    if hasattr(value, "value"):
        return str(value.value)
    return str(value)


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
    relevance: RelevanceProjection,
) -> list[UiActionItem]:
    items: list[UiActionItem] = []

    task_by_id = {task.task_id: task for task in tasks}
    visible_agent_ids = {
        agent_id for agent_id, projection in relevance.agents.items() if projection.visible_in_main
    }
    responsible_agent_ids = {
        agent_id
        for agent_id, projection in relevance.agents.items()
        if projection.current_task_id or projection.current_gate_id or projection.queued_inbox
    }
    visible_or_responsible_agent_ids = visible_agent_ids | responsible_agent_ids
    for agent in agents:
        agent_id = agent.identity.agent_id
        if agent_id not in visible_or_responsible_agent_ids:
            continue
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
        task_relevance = relevance.tasks.get(task.task_id)
        if task_relevance is not None and not task_relevance.visible_in_home:
            continue
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
        gate_relevance = relevance.gates.get(gate.gate_id)
        if gate_relevance is not None and gate_relevance.visible_in_approval_center:
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
        if item.agent_id in relevance.agents and item.agent_id not in visible_agent_ids:
            continue
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

    visible_artifacts = [
        artifact
        for artifact in artifacts
        if relevance.artifacts.get(artifact.artifact_id) is not None
        and relevance.artifacts[artifact.artifact_id].visible_in_default_list
    ]
    latest_artifact = max(visible_artifacts, key=lambda item: (item.created_at, item.artifact_id), default=None)
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
            (
                task
                for task in tasks
                if task.run_id == active_run.run_id
                and _normalize_state(task.status) == "working"
                and relevance.tasks.get(task.task_id) is not None
                and relevance.tasks[task.task_id].visible_in_home
            ),
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
    relevance: RelevanceProjection,
) -> list[UiAgentSummary]:
    summaries: list[UiAgentSummary] = []
    tasks_by_id = {task.task_id: task for task in tasks}
    gates_by_id = {gate.gate_id: gate for gate in gates}
    for agent in agents:
        session = agent.active_session
        health = agent.health
        presence = relevance.agents.get(agent.identity.agent_id)
        runtime_state = _normalize_state(session.runtime_state) if session else "offline"
        task = tasks_by_id.get(presence.current_task_id) if presence else None
        if task is None:
            task = _active_task_for_agent(tasks, agent.identity.agent_id)
        gate = gates_by_id.get(presence.current_gate_id) if presence else None
        if gate is None and presence is None:
            gate = next(
                (
                    gate
                    for gate in gates
                    if (gate.owner_agent_id == agent.identity.agent_id or gate.requested_by == agent.identity.agent_id)
                    and _normalize_state(gate.state) in {"open", "escalated"}
                ),
                None,
            )
        queued = (
            presence.queued_inbox
            if presence is not None
            else sum(1 for item in inbox if item.agent_id == agent.identity.agent_id and item.status == "queued")
        )
        identity_lifecycle = presence.identity_state.value if presence is not None else ""
        presence_state = presence.presence_state.value if presence is not None else ""
        workload_state = presence.workload_state.value if presence is not None else ""
        ui_visibility_state = presence.ui_visibility_state.value if presence is not None else ""
        conditions = presence.conditions if presence is not None else agent.conditions
        hidden_reason = presence.hidden_reason or "" if presence is not None else ""
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
                identity_lifecycle=identity_lifecycle,
                presence_state=presence_state,
                workload_state=workload_state,
                ui_visibility_state=ui_visibility_state,
                conditions=conditions,
                hidden_reason=hidden_reason,
            )
        )
    return summaries


def _artifact_ids_for_visibility(relevance: RelevanceProjection, visibility: str) -> list[str]:
    return [
        artifact_id
        for artifact_id, projection in relevance.artifacts.items()
        if projection.visibility == visibility
    ]


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


def _agent_has_active_responsibility(
    agent_id: str,
    tasks: list[TaskRecord],
    gates: list[GateRecord],
    inbox: list[InboxItem],
) -> bool:
    if any(agent_id in {task.owner_agent_id, task.assignee_agent_id} and _normalize_state(task.status) in ACTIVE_TASK_STATES for task in tasks):
        return True
    if any(
        agent_id in {gate.owner_agent_id, gate.requested_by} and _normalize_state(gate.state) in {"open", "escalated"}
        for gate in gates
    ):
        return True
    return any(item.agent_id == agent_id and item.status in {"queued", "delivered"} for item in inbox)


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


def _has_table(conn: sqlite3.Connection, table: str) -> bool:
    row = conn.execute(
        "select 1 from sqlite_master where type = 'table' and name = ?",
        (table,),
    ).fetchone()
    return row is not None


def _configured_session_freshness_seconds() -> float:
    configured = os.environ.get(SESSION_FRESHNESS_ENV)
    if configured is None:
        return DEFAULT_SESSION_FRESHNESS_SECONDS
    try:
        value = float(configured)
    except ValueError:
        return DEFAULT_SESSION_FRESHNESS_SECONDS
    return value if value > 0 else DEFAULT_SESSION_FRESHNESS_SECONDS
