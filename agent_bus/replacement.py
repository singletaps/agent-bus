from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol

from .agents import AgentDirectory
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
from .store import EventStore


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
    ) -> None:
        self.directory = directory or AgentDirectory(db_path=db_path)
        context_db_path = db_path
        if context_db_path is None and directory is not None:
            context_db_path = directory.db_path
        self.db_path = Path(context_db_path) if context_db_path is not None else None
        self.context_sink = context_sink or (ContextStore(context_db_path) if context_db_path is not None else InMemoryRehydrationContext())
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
                run_id=recommendation.run_id,
                task_id=task_id,
                agent_id=session.agent_id,
                payload={
                    "recommendation_id": recommendation.recommendation_id,
                    "old_session_id": session.session_id,
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

        old_session, replacement_session = self.directory.replace_with_session(
            old_session.session_id,
            replacement_session.session_id,
            reason=f"approved by {approved_by}: {recommendation.reason}",
            replacement_state=AgentRuntimeState.REHYDRATING,
        )
        self._reassign_task_to_replacement(recommendation, replacement_session, approved_by)
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
            invalidated_packet_ids=list(invalidated_packet_ids),
            actor=approved_by,
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
            )
        approval = ReplacementApproval(
            recommendation_id=recommendation.recommendation_id,
            task_id=recommendation.task_id,
            old_session=old_session,
            replacement_session=replacement_session,
            context_packet=packet,
            approved_by=approved_by,
        )
        self._record_event(
            BusEvent(
                type=EventType.REPLACEMENT_APPROVED,
                actor=approved_by,
                run_id=recommendation.run_id,
                task_id=recommendation.task_id,
                agent_id=replacement_session.agent_id,
                payload={
                    "recommendation_id": recommendation.recommendation_id,
                    "old_session_id": old_session.session_id,
                    "replacement_session_id": replacement_session.session_id,
                    "context_packet_id": packet.packet_id,
                },
            )
        )
        return approval

    def _reassign_task_to_replacement(
        self,
        recommendation: ReplacementRecommendation,
        replacement_session: AgentSession,
        approved_by: str,
    ) -> None:
        if self.db_path is None:
            return
        from .tasks import TaskBoard

        board = TaskBoard(
            db_path=self.db_path,
            agent_directory=self.directory,
            inbox_store=self.inbox,
        )
        try:
            task = board.get_task(recommendation.task_id)
            if task.status.value in {"completed", "failed", "superseded"}:
                return
            if task.assignee_agent_id == replacement_session.agent_id:
                return
            board.assign_task(
                recommendation.task_id,
                replacement_session.agent_id,
                actor=approved_by,
            )
        finally:
            board.close()

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

    def _record_event(self, event: BusEvent) -> None:
        if self.event_store is not None:
            self.event_store.append_event(event)


def _missing_capability() -> AgentCapability:
    return AgentCapability(agent_id="missing", name="missing", confidence=0.0)


def _age_seconds(value: str | None, *, now: datetime | None = None) -> float | None:
    if value is None:
        return None
    now = now or datetime.now(timezone.utc)
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return max(0.0, (now - parsed).total_seconds())
