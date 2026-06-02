from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol

from .agents import AgentDirectory
from .authority import actor_role_for_principal, controller_principal
from .context import ContextStore
from .inbox import InboxStore
from .models import (
    AgentCapability,
    AgentHealth,
    AgentIdentity,
    AgentRuntimeState,
    AgentSession,
    BusEvent,
    ContextPacket,
    EventType,
    new_id,
    utc_now_iso,
)
from .protocol_models import FencingResult, PacketKind, Principal, ProjectionEffect, SessionRole
from .store import EventStore
from .unit_of_work import UnitOfWork


SUSPECT_STATES = {
    AgentRuntimeState.DELIVERED_NOT_ACKED,
    AgentRuntimeState.SUSPECTED_STUCK,
    AgentRuntimeState.INPUT_UNAVAILABLE,
    AgentRuntimeState.CONTEXT_LOST,
    AgentRuntimeState.NEEDS_REHYDRATION,
}

READY_STATES = {
    AgentRuntimeState.STANDBY_READY,
    AgentRuntimeState.WAITING_ON_BUS,
    AgentRuntimeState.WAIT_RETURNED_NOOP,
}


class RehydrationContextSink(Protocol):
    def create_rehydration_packet(self, **kwargs: Any) -> ContextPacket:
        ...


@dataclass(frozen=True)
class ReplacementTrigger:
    name: str
    reason: str
    weight: float


@dataclass(frozen=True)
class ReplacementCandidate:
    agent_id: str
    session_id: str | None
    score: float
    capability_score: float
    readiness_score: float
    role_score: float
    freshness_score: float
    failure_penalty: float


@dataclass(frozen=True)
class ReplacementRecommendation:
    recommendation_id: str
    task_id: str
    old_session_id: str
    old_agent_id: str
    candidate: ReplacementCandidate
    triggers: tuple[ReplacementTrigger, ...]
    run_id: str | None = None
    required_capabilities: tuple[str, ...] = ()
    role: str | None = None
    created_at: str = field(default_factory=utc_now_iso)

    @property
    def reason(self) -> str:
        return "; ".join(trigger.reason for trigger in self.triggers)


@dataclass(frozen=True)
class ReplacementApproval:
    recommendation_id: str
    task_id: str
    old_session: AgentSession
    replacement_session: AgentSession
    context_packet: ContextPacket
    approved_by: str
    approved_at: str = field(default_factory=utc_now_iso)


class InMemoryRehydrationContext:
    def __init__(self) -> None:
        self.packets: dict[str, ContextPacket] = {}
        self.rehydration_requests: list[dict[str, Any]] = []

    def create_rehydration_packet(self, **kwargs: Any) -> ContextPacket:
        packet = ContextPacket(
            packet_kind=PacketKind.REHYDRATION,
            agent_id=kwargs["agent_id"],
            task_id=kwargs.get("task_id"),
            run_id=kwargs.get("run_id"),
            status="active",
            summary=kwargs.get("summary", ""),
            instructions=kwargs.get("instructions", []),
            artifact_refs=kwargs.get("artifact_refs", []),
        )
        self.packets[packet.packet_id] = packet
        self.rehydration_requests.append({**kwargs, "packet_id": packet.packet_id})
        return packet

    def invalidate_active_binding_for_session(self, **_kwargs: Any) -> list[ContextPacket]:
        return []


class ReplacementCoordinator:
    def __init__(
        self,
        *,
        directory: AgentDirectory | None = None,
        context_sink: RehydrationContextSink | None = None,
        inbox: InboxStore | None = None,
        event_store: EventStore | None = None,
        db_path: str | Path | None = None,
        heartbeat_timeout_seconds: float = 300.0,
        principal: Principal | None = None,
    ) -> None:
        self.directory = directory or AgentDirectory(db_path=db_path)
        context_db_path = db_path
        if context_db_path is None and directory is not None:
            context_db_path = directory.db_path
        self.db_path = Path(context_db_path) if context_db_path is not None else None
        self.principal = principal or controller_principal("replacement-controller")
        self.context_sink = context_sink or (
            ContextStore(context_db_path, principal=self.principal)
            if context_db_path is not None
            else InMemoryRehydrationContext()
        )
        self.inbox = inbox
        self.event_store = event_store
        self.heartbeat_timeout_seconds = heartbeat_timeout_seconds

    def recommend_for_session(
        self,
        session_id: str,
        *,
        task_id: str,
        run_id: str | None = None,
        required_capabilities: tuple[str, ...] | list[str] = (),
        role: str | None = None,
        now: datetime | None = None,
    ) -> ReplacementRecommendation | None:
        session = self.directory.get_session(session_id)
        health = self.directory.get_health(session_id)
        triggers = self._triggers_for(session, health, now=now)
        if not triggers:
            return None

        candidates = self.score_candidates(
            old_session=session,
            required_capabilities=tuple(required_capabilities),
            role=role,
            now=now,
        )
        if not candidates:
            return None

        recommendation = ReplacementRecommendation(
            recommendation_id=new_id("replrec"),
            task_id=task_id,
            run_id=run_id or session.run_id,
            old_session_id=session.session_id,
            old_agent_id=session.agent_id,
            candidate=candidates[0],
            triggers=tuple(triggers),
            required_capabilities=tuple(required_capabilities),
            role=role,
        )
        self._record_event(
            BusEvent(
                type=EventType.REPLACEMENT_RECOMMENDED,
                actor="agent_bus.replacement",
                actor_role="system",
                run_id=recommendation.run_id,
                task_id=task_id,
                agent_id=session.agent_id,
                correlation_id=recommendation.recommendation_id,
                projection_effect=ProjectionEffect.AUDIT_ONLY,
                fencing_result=FencingResult.NOT_REQUIRED,
                payload={
                    "recommendation_id": recommendation.recommendation_id,
                    "task_id": task_id,
                    "old_session_id": session.session_id,
                    "old_agent_id": session.agent_id,
                    "candidate_agent_id": recommendation.candidate.agent_id,
                    "candidate_session_id": recommendation.candidate.session_id,
                    "triggers": [trigger.name for trigger in triggers],
                    "score": recommendation.candidate.score,
                },
            )
        )
        return recommendation

    def score_candidates(
        self,
        *,
        old_session: AgentSession,
        required_capabilities: tuple[str, ...] = (),
        role: str | None = None,
        now: datetime | None = None,
    ) -> list[ReplacementCandidate]:
        candidates: list[ReplacementCandidate] = []
        for identity in self.directory.list_identities():
            if identity.agent_id == old_session.agent_id:
                continue
            active_session = self.directory.get_active_session(identity.agent_id)
            sessions = self.directory.list_sessions(identity.agent_id)
            session = active_session or (sessions[-1] if sessions else None)
            capability_score = self._capability_score(identity, required_capabilities)
            readiness_score = self._readiness_score(session)
            role_score = self._role_score(identity, role)
            freshness_score = self._freshness_score(session, now=now)
            failure_penalty = self._failure_penalty(session)
            score = round(
                (capability_score * 0.40)
                + (readiness_score * 0.25)
                + (role_score * 0.15)
                + (freshness_score * 0.10)
                + ((1.0 - failure_penalty) * 0.10),
                4,
            )
            candidates.append(
                ReplacementCandidate(
                    agent_id=identity.agent_id,
                    session_id=session.session_id if session else None,
                    score=score,
                    capability_score=capability_score,
                    readiness_score=readiness_score,
                    role_score=role_score,
                    freshness_score=freshness_score,
                    failure_penalty=failure_penalty,
                )
            )
        return sorted(candidates, key=lambda candidate: (-candidate.score, candidate.agent_id))

    def approve(
        self,
        recommendation: ReplacementRecommendation,
        *,
        approved_by: str = "controller",
        next_action: str = "continue the same task from the rehydration packet",
        required_artifacts: tuple[str, ...] | list[str] = (),
        invalidated_packet_ids: tuple[str, ...] | list[str] = (),
    ) -> ReplacementApproval:
        old_session = self.directory.get_session(recommendation.old_session_id)
        replacement_session = self._ensure_replacement_session(recommendation)
        approval_request_event = self._record_approval_requested(
            recommendation,
            old_session=old_session,
            replacement_session=replacement_session,
            approved_by=approved_by,
        )
        scoped_invalidations = self._invalidate_old_task_session_bindings(
            recommendation,
            old_session=old_session,
            invalidated_by_event_id=approval_request_event.event_id,
            actor=approved_by,
        )
        invalidated_packet_id_list = _dedupe_preserving_order(
            [packet.packet_id for packet in scoped_invalidations] + list(invalidated_packet_ids)
        )

        old_session, replacement_session = self.directory.replace_with_session(
            old_session.session_id,
            replacement_session.session_id,
            reason=f"approved by {approved_by}: {recommendation.reason}",
            replacement_state=AgentRuntimeState.REHYDRATING,
        )
        self._mark_fence_replaced(old_session.session_id, replacement_session.session_id)
        packet = self.context_sink.create_rehydration_packet(
            agent_id=replacement_session.agent_id,
            task_id=recommendation.task_id,
            run_id=recommendation.run_id,
            role_contract=f"replacement for {recommendation.old_agent_id}",
            current_task=recommendation.task_id,
            last_known_summary=f"Replacement approved for {recommendation.old_agent_id}: {recommendation.reason}",
            open_inbox_item_ids=self._open_inbox_item_ids(old_session.agent_id),
            required_artifacts=list(required_artifacts),
            next_action=next_action,
            invalidated_packet_ids=invalidated_packet_id_list,
            created_from_event_id=approval_request_event.event_id,
            actor=approved_by,
            principal=self.principal,
            session_id=replacement_session.session_id,
            session_epoch=replacement_session.session_epoch,
        )
        if self.inbox is not None:
            self.inbox.enqueue(
                replacement_session.agent_id,
                "replacement_notice",
                {
                    "task_id": recommendation.task_id,
                    "old_agent_id": old_session.agent_id,
                    "old_session_id": old_session.session_id,
                    "replacement_session_id": replacement_session.session_id,
                    "recommendation_id": recommendation.recommendation_id,
                },
                priority=100,
                context_packet_id=packet.packet_id,
                dedupe_key=f"replacement:{recommendation.task_id}:{replacement_session.session_id}",
                actor=approved_by,
                principal=self.principal,
            )
        approval_event = self._record_event(
            BusEvent(
                type=EventType.REPLACEMENT_APPROVED,
                actor=approved_by,
                actor_role=actor_role_for_principal(self.principal, "controller"),
                run_id=recommendation.run_id,
                task_id=recommendation.task_id,
                agent_id=replacement_session.agent_id,
                context_packet_id=packet.packet_id,
                correlation_id=recommendation.recommendation_id,
                causation_id=approval_request_event.event_id,
                projection_effect=ProjectionEffect.COMMIT,
                fencing_result=FencingResult.NOT_REQUIRED,
                payload={
                    "recommendation_id": recommendation.recommendation_id,
                    "task_id": recommendation.task_id,
                    "old_agent_id": old_session.agent_id,
                    "old_session_id": old_session.session_id,
                    "replacement_agent_id": replacement_session.agent_id,
                    "replacement_session_id": replacement_session.session_id,
                    "context_packet_id": packet.packet_id,
                    "invalidated_packet_ids": invalidated_packet_id_list,
                },
            )
        )
        self._reassign_task_to_replacement(
            recommendation,
            replacement_session,
            approved_by,
            causation_id=approval_event.event_id,
            context_packet_id=packet.packet_id,
        )
        approval = ReplacementApproval(
            recommendation_id=recommendation.recommendation_id,
            task_id=recommendation.task_id,
            old_session=old_session,
            replacement_session=replacement_session,
            context_packet=packet,
            approved_by=approved_by,
        )
        return approval

    def _reassign_task_to_replacement(
        self,
        recommendation: ReplacementRecommendation,
        replacement_session: AgentSession,
        approved_by: str,
        *,
        causation_id: str,
        context_packet_id: str,
    ) -> None:
        if self.db_path is None:
            return
        from .protocol import ProtocolKernel

        with UnitOfWork(self.db_path) as probe:
            conn = probe.conn
            if conn is None:
                return
            row = conn.execute("select * from tasks where task_id = ?", (recommendation.task_id,)).fetchone()
        if row is None:
            return
        if row["status"] in {"completed", "failed", "superseded"}:
            return
        if row["assignee_agent_id"] == replacement_session.agent_id:
            return
        now = utc_now_iso()
        event = BusEvent(
            type=EventType.REPLACEMENT_REASSIGNMENT_COMMITTED,
            actor=approved_by,
            actor_role="controller",
            run_id=recommendation.run_id or row["run_id"],
            task_id=recommendation.task_id,
            agent_id=replacement_session.agent_id,
            context_packet_id=context_packet_id,
            correlation_id=recommendation.recommendation_id,
            causation_id=causation_id,
            projection_effect=ProjectionEffect.COMMIT,
            fencing_result=FencingResult.NOT_REQUIRED,
            payload={
                "task_id": recommendation.task_id,
                "original_task_id": recommendation.task_id,
                "old_agent_id": recommendation.old_agent_id,
                "old_session_id": recommendation.old_session_id,
                "replacement_agent_id": replacement_session.agent_id,
                "replacement_session_id": replacement_session.session_id,
                "recommendation_id": recommendation.recommendation_id,
                "previous_status": row["status"],
                "status": "reassigned",
            },
        )
        result = ProtocolKernel(self.db_path).commit_event(
            event,
            principal=self.principal,
            guard_targets=(("tasks", recommendation.task_id, EventType.REPLACEMENT_REASSIGNMENT_COMMITTED.value),),
            target_table="tasks",
            target_id=recommendation.task_id,
            reason="replacement reassignment approved",
            mutation=lambda conn, _event: conn.execute(
                """
                update tasks
                   set assignee_agent_id = ?,
                       status = 'reassigned',
                       blocked_reason = null,
                       updated_at = ?
                 where task_id = ?
                """,
                (replacement_session.agent_id, now, recommendation.task_id),
            ),
        )
        if not result.accepted:
            raise PermissionError(result.reason or "protocol rejected replacement reassignment")
        self._record_task_reassigned_projection(
            recommendation,
            replacement_session,
            approved_by,
            causation_id=result.event_id or event.event_id,
            context_packet_id=context_packet_id,
        )

    def _record_task_reassigned_projection(
        self,
        recommendation: ReplacementRecommendation,
        replacement_session: AgentSession,
        approved_by: str,
        *,
        causation_id: str,
        context_packet_id: str,
    ) -> None:
        if self.db_path is None:
            return
        from .protocol import ProtocolKernel

        event = BusEvent(
            type=EventType.TASK_REASSIGNED,
            actor=approved_by,
            actor_role="controller",
            run_id=recommendation.run_id,
            task_id=recommendation.task_id,
            agent_id=replacement_session.agent_id,
            context_packet_id=context_packet_id,
            correlation_id=recommendation.recommendation_id,
            causation_id=causation_id,
            projection_effect=ProjectionEffect.COMMIT,
            fencing_result=FencingResult.NOT_REQUIRED,
            payload={
                "task_id": recommendation.task_id,
                "original_task_id": recommendation.task_id,
                "old_agent_id": recommendation.old_agent_id,
                "old_session_id": recommendation.old_session_id,
                "replacement_agent_id": replacement_session.agent_id,
                "replacement_session_id": replacement_session.session_id,
                "recommendation_id": recommendation.recommendation_id,
                "source_event_type": EventType.REPLACEMENT_REASSIGNMENT_COMMITTED.value,
            },
        )
        result = ProtocolKernel(self.db_path).commit_event(
            event,
            principal=self.principal,
            guard_targets=(("tasks", recommendation.task_id, EventType.TASK_REASSIGNED.value),),
            target_table="tasks",
            target_id=recommendation.task_id,
            reason="task reassigned compatibility projection for replacement reassignment",
        )
        if not result.accepted:
            raise PermissionError(result.reason or "protocol rejected task reassignment projection")

    def _record_approval_requested(
        self,
        recommendation: ReplacementRecommendation,
        *,
        old_session: AgentSession,
        replacement_session: AgentSession,
        approved_by: str,
    ) -> BusEvent:
        return self._record_event(
            BusEvent(
                type=EventType.REPLACEMENT_APPROVAL_REQUESTED,
                actor=approved_by,
                actor_role=actor_role_for_principal(self.principal, "controller"),
                run_id=recommendation.run_id,
                task_id=recommendation.task_id,
                agent_id=replacement_session.agent_id,
                correlation_id=recommendation.recommendation_id,
                projection_effect=ProjectionEffect.AUDIT_ONLY,
                fencing_result=FencingResult.NOT_REQUIRED,
                payload={
                    "recommendation_id": recommendation.recommendation_id,
                    "task_id": recommendation.task_id,
                    "old_agent_id": old_session.agent_id,
                    "old_session_id": old_session.session_id,
                    "replacement_agent_id": replacement_session.agent_id,
                    "replacement_session_id": replacement_session.session_id,
                    "reason": recommendation.reason,
                },
            )
        )

    def _invalidate_old_task_session_bindings(
        self,
        recommendation: ReplacementRecommendation,
        *,
        old_session: AgentSession,
        invalidated_by_event_id: str,
        actor: str,
    ) -> list[ContextPacket]:
        invalidate = getattr(self.context_sink, "invalidate_active_binding_for_session", None)
        if invalidate is None:
            return []
        return list(
            invalidate(
                task_id=recommendation.task_id,
                agent_id=old_session.agent_id,
                session_id=old_session.session_id,
                invalidated_by_event_id=invalidated_by_event_id,
                actor=actor,
                principal=self.principal,
            )
        )

    def _mark_fence_replaced(self, old_session_id: str, replacement_session_id: str) -> None:
        if self.db_path is None:
            return
        with UnitOfWork(self.db_path) as uow:
            conn = uow.conn
            if conn is None:
                return
            conn.execute(
                """
                update session_fences
                   set active = 0,
                       session_role = ?,
                       replaced_by_session_id = ?,
                       updated_at = ?
                 where session_id = ?
                """,
                (SessionRole.REPLACED.value, replacement_session_id, utc_now_iso(), old_session_id),
            )

    def _ensure_replacement_session(self, recommendation: ReplacementRecommendation) -> AgentSession:
        if recommendation.candidate.session_id:
            session = self.directory.get_session(recommendation.candidate.session_id)
            if session.agent_id != recommendation.candidate.agent_id:
                raise ValueError("candidate session does not belong to candidate agent")
            return session
        return self.directory.start_session(
            recommendation.candidate.agent_id,
            run_id=recommendation.run_id,
            runtime_state=AgentRuntimeState.REHYDRATING,
            activate=False,
        )

    def _triggers_for(
        self,
        session: AgentSession,
        health: AgentHealth,
        *,
        now: datetime | None,
    ) -> list[ReplacementTrigger]:
        triggers: list[ReplacementTrigger] = []
        heartbeat_age = _age_seconds(session.last_seen_at, now=now)
        if heartbeat_age is None or heartbeat_age > self.heartbeat_timeout_seconds:
            triggers.append(
                ReplacementTrigger(
                    name="missing_heartbeat",
                    reason="missing heartbeat",
                    weight=0.8,
                )
            )
        if session.runtime_state is AgentRuntimeState.DELIVERED_NOT_ACKED:
            triggers.append(
                ReplacementTrigger(
                    name="delivered_not_acked",
                    reason="wait item delivered but not acked",
                    weight=0.7,
                )
            )
        if session.runtime_state is AgentRuntimeState.CONTEXT_LOST or not health.context_valid:
            triggers.append(
                ReplacementTrigger(
                    name="context_suspect",
                    reason="reported context loss",
                    weight=0.9,
                )
            )
        if session.runtime_state is AgentRuntimeState.INPUT_UNAVAILABLE or not health.input_available:
            triggers.append(
                ReplacementTrigger(
                    name="input_unavailable",
                    reason="input unavailable",
                    weight=0.9,
                )
            )
        if session.runtime_state is AgentRuntimeState.SUSPECTED_STUCK:
            triggers.append(
                ReplacementTrigger(
                    name="manual_controller_mark",
                    reason="manual controller mark",
                    weight=1.0,
                )
            )
        return triggers

    def _capability_score(
        self,
        identity: AgentIdentity,
        required_capabilities: tuple[str, ...],
    ) -> float:
        capabilities = self.directory.list_capabilities(identity.agent_id)
        if not capabilities:
            return 0.0 if required_capabilities else 0.5
        by_name = {capability.name: capability for capability in capabilities}
        if not required_capabilities:
            return round(max(capability.confidence for capability in capabilities), 4)
        scores = [by_name.get(name, _missing_capability()).confidence for name in required_capabilities]
        return round(sum(scores) / len(scores), 4)

    def _readiness_score(self, session: AgentSession | None) -> float:
        if session is None:
            return 0.45
        if session.runtime_state in READY_STATES:
            return 1.0
        if session.runtime_state is AgentRuntimeState.STANDBY_DEGRADED:
            return 0.45
        if session.runtime_state is AgentRuntimeState.WORKING:
            return 0.2
        if session.runtime_state is AgentRuntimeState.REPLACED:
            return 0.0
        return 0.25

    def _role_score(self, identity: AgentIdentity, role: str | None) -> float:
        if role is None:
            return 1.0
        if identity.role == role:
            return 1.0
        if identity.role is None:
            return 0.5
        return 0.2

    def _freshness_score(self, session: AgentSession | None, *, now: datetime | None) -> float:
        if session is None:
            return 0.3
        age = _age_seconds(session.last_seen_at, now=now)
        if age is None:
            return 0.3
        if age <= 60:
            return 1.0
        if age <= 300:
            return 0.8
        if age <= 900:
            return 0.5
        return 0.2

    def _failure_penalty(self, session: AgentSession | None) -> float:
        if session is None:
            return 0.2
        return 0.8 if session.runtime_state in SUSPECT_STATES else 0.0

    def _open_inbox_item_ids(self, agent_id: str) -> list[str]:
        if self.inbox is None:
            return []
        return [
            item.inbox_id
            for item in self.inbox.list_items(agent_id)
            if item.acked_at is None and item.status != "acked"
        ]

    def _record_event(self, event: BusEvent) -> BusEvent:
        if self.db_path is not None and _is_authoritative_replacement_event(event):
            event = event.model_copy(
                update={
                    "projection_effect": event.projection_effect or ProjectionEffect.COMMIT,
                    "fencing_result": event.fencing_result or FencingResult.NOT_REQUIRED,
                }
            )
            with UnitOfWork(self.db_path) as uow:
                appended = uow.append_event(event, guard=True)
                uow.record_projection_effect(
                    event_id=appended.event_id,
                    effect=ProjectionEffect.COMMIT,
                    reason="replacement coordinator authoritative event",
                    run_id=event.run_id,
                    task_id=event.task_id,
                )
            return appended
        if self.db_path is not None:
            return EventStore(self.db_path).append_event(event)
        if self.event_store is not None:
            return self.event_store.append_event(event)
        return event


def _missing_capability() -> AgentCapability:
    return AgentCapability(agent_id="missing", name="missing", confidence=0.0)


def _is_authoritative_replacement_event(event: BusEvent) -> bool:
    event_type = event.type.value if hasattr(event.type, "value") else str(event.type)
    return event_type in {
        EventType.REPLACEMENT_APPROVED.value,
        EventType.REPLACEMENT_REASSIGNMENT_COMMITTED.value,
    }


def _dedupe_preserving_order(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value not in seen:
            seen.add(value)
            result.append(value)
    return result


def _age_seconds(value: str | None, *, now: datetime | None = None) -> float | None:
    if value is None:
        return None
    now = now or datetime.now(timezone.utc)
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return max(0.0, (now - parsed).total_seconds())
