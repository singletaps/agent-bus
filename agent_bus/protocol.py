from __future__ import annotations

import os
import sqlite3
from pathlib import Path
from typing import Any, Callable, Iterable

from .authority import AuthorityService, DIRECT_AUTHORITATIVE_MUTATORS, actor_role_for_principal
from .fencing import FencingService
from .models import BusEvent, EventType, new_id
from .policy import PolicyService
from .protocol_models import (
    ClaimStatus,
    FencingResult,
    Principal,
    ProjectionEffect,
    ProtocolViolation,
    ProtocolWriteResult,
    TaskClaimKind,
    TaskClaimRecord,
)
from .unit_of_work import UnitOfWork


class ProtocolKernel:
    """Single public write path for fenced, authorized protocol events."""

    def __init__(
        self,
        db_path: str | os.PathLike[str] | None = None,
        *,
        authority: AuthorityService | None = None,
        fencing: FencingService | None = None,
        policy: PolicyService | None = None,
        conn: sqlite3.Connection | None = None,
    ) -> None:
        self.db_path = Path(db_path) if db_path is not None else None
        self.conn = conn
        self.authority = authority or AuthorityService()
        self.fencing = fencing or FencingService(self.db_path, conn=conn)
        self.policy = policy or PolicyService(self.db_path, conn=conn)

    def record_event(
        self,
        *,
        event_type: str,
        actor: str | None,
        actor_role: str | None,
        action: str | None = None,
        payload: dict[str, Any] | None = None,
        principal: Principal | None = None,
        session_id: str | None = None,
        session_epoch: int | None = None,
        fencing_token: str | None = None,
        required_fencing: bool | None = None,
        run_id: str | None = None,
        task_id: str | None = None,
        agent_id: str | None = None,
        context_packet_id: str | None = None,
        gate_id: str | None = None,
        artifact_id: str | None = None,
        correlation_id: str | None = None,
        causation_id: str | None = None,
        required_artifact_ids: Iterable[str] = (),
        reviewer_agent_id: str | None = None,
        reviewed_agent_id: str | None = None,
    ) -> ProtocolWriteResult:
        normalized_action = _normalize(action or event_type)
        event = BusEvent(
            type=event_type,
            actor=actor,
            actor_role=actor_role or actor_role_for_principal(principal),
            run_id=run_id,
            task_id=task_id,
            agent_id=agent_id,
            session_id=session_id,
            session_epoch=session_epoch,
            context_packet_id=context_packet_id,
            gate_id=gate_id,
            artifact_id=artifact_id,
            correlation_id=correlation_id,
            causation_id=causation_id,
            projection_effect=ProjectionEffect.COMMIT,
            fencing_result=FencingResult.NOT_REQUIRED,
            payload=payload or {},
        )
        return self.commit_event(
            event,
            action=normalized_action,
            principal=principal,
            session_id=session_id,
            session_epoch=session_epoch,
            fencing_token=fencing_token,
            required_fencing=required_fencing,
            required_artifact_ids=required_artifact_ids,
            reviewer_agent_id=reviewer_agent_id,
            reviewed_agent_id=reviewed_agent_id,
        )

    def commit_event(
        self,
        event: BusEvent,
        *,
        action: str | None = None,
        principal: Principal | None,
        session_id: str | None = None,
        session_epoch: int | None = None,
        fencing_token: str | None = None,
        required_fencing: bool | None = None,
        required_artifact_ids: Iterable[str] = (),
        reviewer_agent_id: str | None = None,
        reviewed_agent_id: str | None = None,
        guard_targets: Iterable[tuple[str, str, str]] = (),
        target_table: str | None = None,
        target_id: str | None = None,
        mutation: Callable[[sqlite3.Connection, BusEvent], None] | None = None,
        task_claim: TaskClaimRecord | None = None,
        reason: str = "protocol write accepted",
    ) -> ProtocolWriteResult:
        normalized_action = _normalize(action or event.type)
        event = event.model_copy(
            update={
                "actor_role": event.actor_role or actor_role_for_principal(principal),
                "session_id": event.session_id or session_id,
                "session_epoch": event.session_epoch if event.session_epoch is not None else session_epoch,
            }
        )
        attempted_event_id = event.event_id
        needs_fence = _requires_fencing(event.actor_role, required_fencing, principal)
        fencing = self.fencing.validate(
            session_id or event.session_id,
            session_epoch if session_epoch is not None else event.session_epoch,
            fencing_token,
            required=needs_fence,
        )
        if not fencing.allowed:
            return self._reject(
                attempted_event_id=attempted_event_id,
                action=normalized_action,
                actor=event.actor,
                actor_role=event.actor_role,
                reason=fencing.reason or "fencing rejected write",
                fencing_result=fencing.result,
                payload=event.payload,
                run_id=event.run_id,
                task_id=event.task_id,
                agent_id=event.agent_id,
                session_id=event.session_id,
                context_packet_id=event.context_packet_id,
            )
        if principal is not None and principal.agent_id and fencing.agent_id and principal.agent_id != fencing.agent_id:
            return self._reject(
                attempted_event_id=attempted_event_id,
                action=normalized_action,
                actor=event.actor,
                actor_role=event.actor_role,
                reason="fenced session does not belong to principal agent",
                fencing_result=FencingResult.WRONG_SESSION,
                payload=event.payload,
                run_id=event.run_id,
                task_id=event.task_id,
                agent_id=event.agent_id,
                session_id=event.session_id,
                context_packet_id=event.context_packet_id,
            )
        event = event.model_copy(update={"fencing_result": fencing.result})

        authority = self.authority.evaluate(
            actor=event.actor,
            actor_role=event.actor_role,
            action=normalized_action,
            principal=principal,
        )
        if not authority.allowed:
            return self._reject(
                attempted_event_id=attempted_event_id,
                action=normalized_action,
                actor=event.actor,
                actor_role=event.actor_role,
                reason=authority.reason or "authority denied write",
                fencing_result=fencing.result,
                payload=event.payload,
                run_id=event.run_id,
                task_id=event.task_id,
                agent_id=event.agent_id,
                session_id=event.session_id,
                context_packet_id=event.context_packet_id,
            )

        policy = self.policy.evaluate(
            action=normalized_action,
            actor=event.actor,
            agent_id=event.agent_id,
            task_id=event.task_id,
            session_id=event.session_id,
            context_packet_id=event.context_packet_id,
            required_artifact_ids=required_artifact_ids,
            reviewer_agent_id=reviewer_agent_id,
            reviewed_agent_id=reviewed_agent_id,
        )
        if not policy.allowed:
            return self._reject(
                attempted_event_id=attempted_event_id,
                action=normalized_action,
                actor=event.actor,
                actor_role=event.actor_role,
                reason=policy.reason or "policy denied write",
                fencing_result=fencing.result,
                payload=event.payload,
                run_id=event.run_id,
                task_id=event.task_id,
                agent_id=event.agent_id,
                session_id=event.session_id,
                context_packet_id=event.context_packet_id,
            )

        with UnitOfWork(self.db_path, conn=self.conn) as uow:
            appended = uow.append_event(event, guard=True, guard_targets=guard_targets)
            stored_claim: TaskClaimRecord | None = None
            if task_claim is not None:
                stored_claim = uow.record_task_claim(
                    task_claim.model_copy(update={"created_from_event_id": appended.event_id})
                )
            if mutation is not None:
                mutation(uow.conn, appended)
            effect = uow.record_projection_effect(
                event_id=appended.event_id,
                effect=ProjectionEffect.COMMIT,
                reason=reason,
                target_table=target_table,
                target_id=target_id,
                run_id=event.run_id,
                task_id=event.task_id,
            )
        return ProtocolWriteResult(
            accepted=True,
            event_id=appended.event_id,
            seq=appended.seq,
            effect_id=effect.effect_id,
            projection_effect=ProjectionEffect.COMMIT,
            fencing_result=fencing.result,
            claim_id=stored_claim.claim_id if stored_claim is not None else None,
            claim_status=stored_claim.status if stored_claim is not None else None,
        )

    def reject_action(
        self,
        *,
        attempted_event_id: str | None = None,
        action: str,
        actor: str | None,
        actor_role: str | None = None,
        reason: str,
        fencing_result: FencingResult | str = FencingResult.NOT_REQUIRED,
        payload: dict[str, Any] | None = None,
        run_id: str | None = None,
        task_id: str | None = None,
        agent_id: str | None = None,
        session_id: str | None = None,
        context_packet_id: str | None = None,
    ) -> ProtocolWriteResult:
        return self._reject(
            attempted_event_id=attempted_event_id or new_id("evt"),
            action=action,
            actor=actor,
            actor_role=actor_role,
            reason=reason,
            fencing_result=fencing_result,
            payload=payload or {},
            run_id=run_id,
            task_id=task_id,
            agent_id=agent_id,
            session_id=session_id,
            context_packet_id=context_packet_id,
        )

    def record_direct_mutation_attempt(
        self,
        path: str,
        *,
        actor: str | None,
        actor_role: str | None = None,
        payload: dict[str, Any] | None = None,
    ) -> ProtocolWriteResult:
        mutation = DIRECT_AUTHORITATIVE_MUTATORS.get(path)
        reason = (
            f"direct authoritative mutator is forbidden: {path}; use {mutation.replacement}"
            if mutation is not None
            else f"direct authoritative mutator is not registered: {path}"
        )
        return self._reject(
            attempted_event_id=new_id("evt"),
            action=f"direct_mutation:{path}",
            actor=actor,
            actor_role=actor_role,
            reason=reason,
            fencing_result=FencingResult.NOT_REQUIRED,
            payload=payload or {},
        )

    def record_task_completion_claim(
        self,
        task_id: str,
        *,
        actor: str | None,
        actor_role: str | None = "worker",
        run_id: str | None = None,
        agent_id: str | None = None,
        session_id: str | None = None,
        session_epoch: int | None = None,
        context_packet_id: str | None = None,
        payload: dict[str, Any] | None = None,
    ) -> ProtocolWriteResult:
        task_snapshot = self._task_snapshot(task_id)
        if task_snapshot is not None:
            run_id = run_id or task_snapshot.get("run_id")
            agent_id = agent_id or actor or task_snapshot.get("assignee_agent_id")
        else:
            agent_id = agent_id or actor

        reason = "deprecated worker completion requires fencing/controller commit"
        event = BusEvent(
            type=EventType.TASK_COMPLETION_CLAIMED,
            actor=actor,
            actor_role=actor_role,
            run_id=run_id,
            task_id=task_id,
            agent_id=agent_id,
            session_id=session_id,
            session_epoch=session_epoch,
            context_packet_id=context_packet_id,
            projection_effect=ProjectionEffect.AUDIT_ONLY,
            fencing_result=FencingResult.MISSING,
            payload={
                "claim_kind": TaskClaimKind.COMPLETION,
                "status": ClaimStatus.NEEDS_FENCING,
                "reason": reason,
                "task": task_snapshot,
                **(payload or {}),
            },
        )
        claim = TaskClaimRecord(
            claim_kind=TaskClaimKind.COMPLETION,
            task_id=task_id,
            run_id=run_id,
            agent_id=agent_id,
            session_id=session_id,
            session_epoch=session_epoch,
            context_packet_id=context_packet_id,
            status=ClaimStatus.NEEDS_FENCING,
            payload={"reason": reason, "task": task_snapshot, **(payload or {})},
            created_from_event_id=event.event_id,
        )
        with UnitOfWork(self.db_path, conn=self.conn) as uow:
            appended = uow.append_event(event, guard=False)
            uow.record_task_claim(claim)
            effect = uow.record_projection_effect(
                event_id=appended.event_id,
                effect=ProjectionEffect.AUDIT_ONLY,
                reason=reason,
                target_table="tasks",
                target_id=task_id,
                run_id=run_id,
                task_id=task_id,
            )
        return ProtocolWriteResult(
            accepted=True,
            event_id=appended.event_id,
            seq=appended.seq,
            effect_id=effect.effect_id,
            projection_effect=ProjectionEffect.AUDIT_ONLY,
            fencing_result=FencingResult.MISSING,
            reason=reason,
            claim_id=claim.claim_id,
            claim_status=ClaimStatus.NEEDS_FENCING,
        )

    def _task_snapshot(self, task_id: str) -> dict[str, Any] | None:
        if self.db_path is None:
            return None
        from .tasks import RuntimeRecordError, TaskBoard

        board = TaskBoard(db_path=self.db_path)
        try:
            return board.get_task(task_id).model_dump(mode="json")
        except RuntimeRecordError:
            return None
        finally:
            board.close()

    def _reject(
        self,
        *,
        attempted_event_id: str,
        action: str,
        actor: str | None,
        actor_role: str | None,
        reason: str,
        fencing_result: FencingResult | str,
        payload: dict[str, Any],
        run_id: str | None = None,
        task_id: str | None = None,
        agent_id: str | None = None,
        session_id: str | None = None,
        context_packet_id: str | None = None,
    ) -> ProtocolWriteResult:
        violation = ProtocolViolation(
            attempted_event_id=attempted_event_id,
            actor=actor,
            actor_role=actor_role,
            action=action,
            reason=reason,
            fencing_result=fencing_result,
            projection_effect=ProjectionEffect.REJECT,
            run_id=run_id,
            task_id=task_id,
            agent_id=agent_id,
            session_id=session_id,
            context_packet_id=context_packet_id,
            payload=payload,
        )
        with UnitOfWork(self.db_path, conn=self.conn) as uow:
            uow.record_protocol_violation(violation)
            effect = uow.record_projection_effect(
                attempted_event_id=attempted_event_id,
                effect=ProjectionEffect.REJECT,
                reason=reason,
                run_id=run_id,
                task_id=task_id,
            )
        return ProtocolWriteResult(
            accepted=False,
            event_id=None,
            violation_id=violation.violation_id,
            effect_id=effect.effect_id,
            projection_effect=ProjectionEffect.REJECT,
            fencing_result=FencingResult(fencing_result),
            reason=reason,
        )


def _normalize(value: str) -> str:
    return value.value if hasattr(value, "value") else str(value)


def _requires_fencing(actor_role: str | None, required_fencing: bool | None, principal: Principal | None = None) -> bool:
    if required_fencing is not None:
        return required_fencing
    if principal is not None and principal.principal_type.value in {"agent"}:
        return True
    return actor_role is not None and actor_role.lower() in {"worker", "agent", "qa"}
