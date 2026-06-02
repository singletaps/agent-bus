from __future__ import annotations

import json
import os
import sqlite3
from pathlib import Path
from typing import Any, Iterable

from .authority import actor_role_for_principal, controller_principal
from .db import connect, initialize_database
from .inbox import InboxStore
from .models import BusEvent, EventType, GateRecord, GateState, new_id, utc_now_iso
from .protocol_models import FencingResult, Principal
from .store import EventStore
from .tasks import RuntimeRecordError, StateTransitionError, migrate_runtime_schema


TERMINAL_GATE_STATES = {GateState.APPROVED, GateState.REJECTED, GateState.EXPIRED}


class GateBoard:
    def __init__(
        self,
        db_path: str | os.PathLike[str] | None = None,
        *,
        conn: sqlite3.Connection | None = None,
        event_store: EventStore | None = None,
        inbox_store: InboxStore | None = None,
        principal: Principal | None = None,
    ) -> None:
        self.db_path = Path(db_path) if db_path is not None else None
        if conn is None:
            initialize_database(self.db_path)
            self.conn = connect(self.db_path)
            self._owns_connection = True
        else:
            self.conn = conn
            self._owns_connection = False
        migrate_runtime_schema(self.conn)
        self._ensure_contract_columns()
        self.event_store = event_store or EventStore(self.db_path)
        self.inbox_store = inbox_store
        self.principal = principal

    def close(self) -> None:
        if self._owns_connection:
            self.conn.close()

    def create_gate(
        self,
        name: str,
        *,
        run_id: str | None = None,
        task_id: str | None = None,
        owner_agent_id: str | None = None,
        requested_by: str | None = None,
        risk: str = "normal",
        gate_id: str | None = None,
        gate_kind: str = "approval",
        checklist: Iterable[str] | None = None,
        required_evidence: Iterable[str] | None = None,
    ) -> GateRecord:
        gate = GateRecord(
            gate_id=gate_id or new_id("gate"),
            run_id=run_id,
            task_id=task_id,
            name=name,
            gate_kind=gate_kind,
            checklist=list(checklist or []),
            required_evidence=list(required_evidence or []),
            state=GateState.OPEN,
            risk=_normalize_risk(risk),
            owner_agent_id=owner_agent_id,
            requested_by=requested_by,
        )
        self._insert_or_update_gate(gate)
        self._append_event(EventType.GATE_OPENED, actor=requested_by, gate=gate)
        return gate

    def get_gate(self, gate_id: str) -> GateRecord:
        row = self.conn.execute("select * from gates where gate_id = ?", (gate_id,)).fetchone()
        if row is None:
            raise RuntimeRecordError(f"unknown gate: {gate_id}")
        return _row_to_gate(row)

    def approve_gate(
        self,
        gate_id: str,
        *,
        actor: str,
        reason: str | None = None,
        allow_high_risk: bool = False,
        action_agent_id: str = "controller",
        evidence_artifact_ids: Iterable[str] | None = None,
        principal: Principal | None = None,
    ) -> GateRecord:
        gate = self.get_gate(gate_id)
        if gate.risk == "high" and not allow_high_risk and actor not in {"controller", "user"}:
            gate = self.escalate_gate(
                gate_id,
                actor=actor,
                reason=reason or "high-risk gate requires controller or user approval",
                principal=principal,
            )
            self._enqueue_action_required(gate, action_agent_id)
            return gate
        return self._resolve_gate(
            gate,
            GateState.APPROVED,
            actor=actor,
            reason=reason,
            principal=principal,
            evidence_artifact_ids=evidence_artifact_ids,
        )

    def reject_gate(
        self,
        gate_id: str,
        *,
        actor: str,
        reason: str | None = None,
        principal: Principal | None = None,
    ) -> GateRecord:
        return self._resolve_gate(
            self.get_gate(gate_id),
            GateState.REJECTED,
            actor=actor,
            reason=reason,
            principal=principal,
            evidence_artifact_ids=(),
        )

    def expire_gate(self, gate_id: str, *, actor: str | None = None, reason: str | None = None) -> GateRecord:
        return self._resolve_gate(self.get_gate(gate_id), GateState.EXPIRED, actor=actor, reason=reason)

    def escalate_gate(
        self,
        gate_id: str,
        *,
        actor: str | None = None,
        reason: str | None = None,
        principal: Principal | None = None,
    ) -> GateRecord:
        gate = self.get_gate(gate_id)
        if gate.state in TERMINAL_GATE_STATES:
            raise StateTransitionError(f"cannot escalate terminal gate: {gate.state.value}")
        gate.state = GateState.ESCALATED
        gate.decision_by = actor
        gate.decision_actor = actor
        gate.reason = reason
        self._commit_gate_decision(
            gate,
            EventType.GATE_ESCALATED,
            action="gate.escalated",
            actor=actor,
            principal=principal,
            reason="high-risk gate escalated through ProtocolKernel",
        )
        return gate

    def list_gates(self, *, run_id: str | None = None) -> list[GateRecord]:
        if run_id is None:
            rows = self.conn.execute("select * from gates order by created_at asc, gate_id asc").fetchall()
        else:
            rows = self.conn.execute(
                "select * from gates where run_id = ? order by created_at asc, gate_id asc",
                (run_id,),
            ).fetchall()
        return [_row_to_gate(row) for row in rows]

    def _resolve_gate(
        self,
        gate: GateRecord,
        state: GateState,
        *,
        actor: str | None,
        reason: str | None,
        principal: Principal | None,
        evidence_artifact_ids: Iterable[str] | None,
    ) -> GateRecord:
        if gate.state in TERMINAL_GATE_STATES:
            raise StateTransitionError(f"gate already terminal: {gate.state.value}")
        evidence_ids = [artifact_id for artifact_id in (evidence_artifact_ids or []) if artifact_id]
        event_type = EventType.GATE_APPROVED if state is GateState.APPROVED else EventType.GATE_REJECTED
        active_principal = principal or self.principal
        if active_principal is not None:
            self._assert_decision_allowed(
                gate,
                state,
                actor=actor,
                principal=active_principal,
                evidence_artifact_ids=evidence_ids,
                action=event_type.value,
            )
        gate.state = state
        gate.decision_by = actor
        gate.decision_actor = actor
        gate.reason = reason
        gate.resolved_at = utc_now_iso()
        self._commit_gate_decision(
            gate,
            event_type,
            action=event_type.value,
            actor=actor,
            principal=active_principal,
            reason="gate decision committed through ProtocolKernel",
            evidence_artifact_ids=evidence_ids,
        )
        if gate.owner_agent_id:
            self._enqueue(
                gate.owner_agent_id,
                "gate_result",
                {"gate_id": gate.gate_id, "state": gate.state.value, "risk": gate.risk},
                priority=90,
                dedupe_key=f"gate_result:{gate.gate_id}:{gate.state.value}",
            )
        return gate

    def _enqueue_action_required(self, gate: GateRecord, agent_id: str) -> None:
        self._enqueue(
            agent_id,
            "gate_approval_required",
            {
                "gate_id": gate.gate_id,
                "run_id": gate.run_id,
                "task_id": gate.task_id,
                "risk": gate.risk,
                "reason": gate.reason,
            },
            priority=100,
            dedupe_key=f"gate_approval_required:{gate.gate_id}",
        )

    def _enqueue(
        self,
        agent_id: str,
        kind: str,
        payload: dict[str, Any],
        *,
        priority: int,
        dedupe_key: str,
    ) -> None:
        inbox = self.inbox_store or InboxStore(db_path=self.db_path, principal=self.principal)
        owns_inbox = self.inbox_store is None
        try:
            inbox.enqueue(
                agent_id,
                kind,
                payload,
                priority=priority,
                dedupe_key=dedupe_key,
                actor="gate-board",
                principal=self.principal,
            )
        finally:
            if owns_inbox:
                inbox.close()

    def _insert_or_update_gate(self, gate: GateRecord, *, commit: bool = True) -> None:
        try:
            self.conn.execute(
                """
                insert into gates (
                    gate_id, run_id, task_id, name, state, risk, owner_agent_id,
                    requested_by, decision_by, reason, created_at, resolved_at,
                    gate_kind, checklist_json, required_evidence_json, decision_actor
                ) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                on conflict(gate_id) do update set
                    gate_kind = excluded.gate_kind,
                    checklist_json = excluded.checklist_json,
                    required_evidence_json = excluded.required_evidence_json,
                    state = excluded.state,
                    risk = excluded.risk,
                    owner_agent_id = excluded.owner_agent_id,
                    decision_by = excluded.decision_by,
                    decision_actor = excluded.decision_actor,
                    reason = excluded.reason,
                    resolved_at = excluded.resolved_at
                """,
                (
                    gate.gate_id,
                    gate.run_id,
                    gate.task_id,
                    gate.name,
                    gate.state.value,
                    gate.risk,
                    gate.owner_agent_id,
                    gate.requested_by,
                    gate.decision_by,
                    gate.reason,
                    gate.created_at,
                    gate.resolved_at,
                    gate.gate_kind,
                    json.dumps(gate.checklist, sort_keys=True),
                    json.dumps(gate.required_evidence, sort_keys=True),
                    gate.decision_actor,
                ),
            )
        except sqlite3.IntegrityError:
            self.conn.rollback()
            raise
        if commit:
            self.conn.commit()

    def _commit_gate_decision(
        self,
        gate: GateRecord,
        event_type: EventType,
        *,
        action: str,
        actor: str | None,
        principal: Principal | None,
        reason: str,
        evidence_artifact_ids: Iterable[str] = (),
    ) -> None:
        principal = principal or self.principal
        if principal is None:
            self._insert_or_update_gate(gate)
            self._append_event(event_type, actor=actor, gate=gate)
            return
        event = BusEvent(
            type=event_type,
            actor=actor,
            actor_role=actor_role_for_principal(principal),
            run_id=gate.run_id,
            task_id=gate.task_id,
            agent_id=gate.owner_agent_id,
            gate_id=gate.gate_id,
            payload={
                **gate.model_dump(mode="json"),
                "evidence_artifact_ids": list(evidence_artifact_ids),
            },
        )
        from .protocol import ProtocolKernel

        is_review_decision = event_type in {EventType.GATE_APPROVED, EventType.GATE_REJECTED}
        result = ProtocolKernel(self.db_path, conn=self.conn).commit_event(
            event,
            action=action,
            principal=principal,
            required_fencing=False,
            required_artifact_ids=evidence_artifact_ids,
            reviewer_agent_id=actor if is_review_decision else None,
            reviewed_agent_id=gate.requested_by if is_review_decision else None,
            guard_targets=(("gates", gate.gate_id, action),),
            target_table="gates",
            target_id=gate.gate_id,
            mutation=lambda _conn, _event: self._insert_or_update_gate(gate, commit=False),
            reason=reason,
        )
        if not result.accepted:
            raise PermissionError(result.reason or "protocol rejected gate decision")

    def _assert_decision_allowed(
        self,
        gate: GateRecord,
        state: GateState,
        *,
        actor: str | None,
        principal: Principal | None,
        evidence_artifact_ids: list[str],
        action: str,
    ) -> None:
        if state is GateState.APPROVED and gate.risk == "high" and actor not in {"controller", "user"}:
            self._reject_decision(
                gate,
                action=action,
                actor=actor,
                principal=principal,
                reason="high-risk gate requires controller or user approval",
            )
        if actor is not None and gate.requested_by is not None and actor == gate.requested_by:
            self._reject_decision(
                gate,
                action=action,
                actor=actor,
                principal=principal,
                reason="reviewer cannot approve their own work",
            )
        if state is GateState.APPROVED:
            self._assert_required_evidence(gate, actor=actor, principal=principal, action=action, evidence_ids=evidence_artifact_ids)

    def _assert_required_evidence(
        self,
        gate: GateRecord,
        *,
        actor: str | None,
        principal: Principal | None,
        action: str,
        evidence_ids: list[str],
    ) -> None:
        required = [artifact_id for artifact_id in gate.required_evidence if artifact_id]
        missing = sorted(set(required) - set(evidence_ids))
        if missing:
            self._reject_decision(
                gate,
                action=action,
                actor=actor,
                principal=principal,
                reason=f"required evidence missing: {', '.join(missing)}",
            )
        if not evidence_ids:
            return
        rows = self.conn.execute(
            f"select artifact_id, run_id, task_id from artifacts where artifact_id in ({','.join('?' for _ in evidence_ids)})",
            evidence_ids,
        ).fetchall()
        found = {row["artifact_id"]: row for row in rows}
        unknown = sorted(set(evidence_ids) - set(found))
        if unknown:
            self._reject_decision(
                gate,
                action=action,
                actor=actor,
                principal=principal,
                reason=f"required evidence missing: {', '.join(unknown)}",
            )
        unrelated = []
        for artifact_id, row in found.items():
            if gate.task_id is not None and row["task_id"] != gate.task_id:
                unrelated.append(artifact_id)
            elif gate.task_id is None and gate.run_id is not None and row["run_id"] != gate.run_id:
                unrelated.append(artifact_id)
        if unrelated:
            self._reject_decision(
                gate,
                action=action,
                actor=actor,
                principal=principal,
                reason=f"required evidence is unrelated to gate: {', '.join(sorted(unrelated))}",
            )

    def _reject_decision(
        self,
        gate: GateRecord,
        *,
        action: str,
        actor: str | None,
        principal: Principal | None,
        reason: str,
    ) -> None:
        from .protocol import ProtocolKernel

        result = ProtocolKernel(self.db_path, conn=self.conn).reject_action(
            action=action,
            actor=actor,
            actor_role=actor_role_for_principal(principal or self.principal),
            reason=reason,
            fencing_result=FencingResult.NOT_REQUIRED,
            payload=gate.model_dump(mode="json"),
            run_id=gate.run_id,
            task_id=gate.task_id,
            agent_id=gate.owner_agent_id,
        )
        raise PermissionError(result.reason or reason)

    def _ensure_contract_columns(self) -> None:
        columns = {row["name"] for row in self.conn.execute("pragma table_info(gates)").fetchall()}
        additions = {
            "gate_kind": "text not null default 'approval'",
            "checklist_json": "text not null default '[]'",
            "required_evidence_json": "text not null default '[]'",
            "decision_actor": "text",
        }
        for column, ddl in additions.items():
            if column not in columns:
                self.conn.execute(f"alter table gates add column {column} {ddl}")
        self.conn.commit()

    def _append_event(self, event_type: EventType, *, actor: str | None, gate: GateRecord) -> BusEvent:
        return self.event_store.append_event(
            BusEvent(
                type=event_type,
                actor=actor,
                run_id=gate.run_id,
                task_id=gate.task_id,
                payload=gate.model_dump(mode="json"),
            )
        )


def _row_to_gate(row: sqlite3.Row) -> GateRecord:
    return GateRecord(
        gate_id=row["gate_id"],
        run_id=row["run_id"],
        task_id=row["task_id"],
        name=row["name"],
        gate_kind=_row_value(row, "gate_kind", "approval"),
        checklist=_json_list(_row_value(row, "checklist_json", "[]")),
        required_evidence=_json_list(_row_value(row, "required_evidence_json", "[]")),
        state=row["state"],
        risk=row["risk"],
        owner_agent_id=row["owner_agent_id"],
        requested_by=row["requested_by"],
        decision_by=row["decision_by"],
        decision_actor=_row_value(row, "decision_actor", row["decision_by"]),
        reason=row["reason"],
        created_at=row["created_at"],
        resolved_at=row["resolved_at"],
    )


def _row_value(row: sqlite3.Row, key: str, default: Any) -> Any:
    if key not in row.keys():
        return default
    return row[key]


def _json_list(value: str | None) -> list[str]:
    if not value:
        return []
    parsed = json.loads(value)
    return [str(item) for item in parsed]


def _normalize_risk(value: str) -> str:
    return (value or "normal").lower()
