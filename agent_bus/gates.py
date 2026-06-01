from __future__ import annotations

import os
import sqlite3
from pathlib import Path
from typing import Any

from .db import connect, initialize_database
from .inbox import InboxStore
from .models import BusEvent, EventType, GateRecord, GateState, new_id, utc_now_iso
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
        self.event_store = event_store or EventStore(self.db_path)
        self.inbox_store = inbox_store

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
    ) -> GateRecord:
        gate = GateRecord(
            gate_id=gate_id or new_id("gate"),
            run_id=run_id,
            task_id=task_id,
            name=name,
            state=GateState.OPEN,
            risk=risk,
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
    ) -> GateRecord:
        gate = self.get_gate(gate_id)
        if gate.risk == "high" and not allow_high_risk and actor not in {"controller", "user"}:
            gate = self.escalate_gate(
                gate_id,
                actor=actor,
                reason=reason or "high-risk gate requires controller or user approval",
            )
            self._enqueue_action_required(gate, action_agent_id)
            return gate
        return self._resolve_gate(gate, GateState.APPROVED, actor=actor, reason=reason)

    def reject_gate(self, gate_id: str, *, actor: str, reason: str | None = None) -> GateRecord:
        return self._resolve_gate(self.get_gate(gate_id), GateState.REJECTED, actor=actor, reason=reason)

    def expire_gate(self, gate_id: str, *, actor: str | None = None, reason: str | None = None) -> GateRecord:
        return self._resolve_gate(self.get_gate(gate_id), GateState.EXPIRED, actor=actor, reason=reason)

    def escalate_gate(self, gate_id: str, *, actor: str | None = None, reason: str | None = None) -> GateRecord:
        gate = self.get_gate(gate_id)
        if gate.state in TERMINAL_GATE_STATES:
            raise StateTransitionError(f"cannot escalate terminal gate: {gate.state.value}")
        gate.state = GateState.ESCALATED
        gate.decision_by = actor
        gate.reason = reason
        self._insert_or_update_gate(gate)
        self._append_event(EventType.GATE_ESCALATED, actor=actor, gate=gate)
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
    ) -> GateRecord:
        if gate.state in TERMINAL_GATE_STATES:
            raise StateTransitionError(f"gate already terminal: {gate.state.value}")
        gate.state = state
        gate.decision_by = actor
        gate.reason = reason
        gate.resolved_at = utc_now_iso()
        self._insert_or_update_gate(gate)
        self._append_event(EventType.GATE_RESULT, actor=actor, gate=gate)
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
        inbox = self.inbox_store or InboxStore(db_path=self.db_path)
        owns_inbox = self.inbox_store is None
        try:
            inbox.enqueue(agent_id, kind, payload, priority=priority, dedupe_key=dedupe_key)
        finally:
            if owns_inbox:
                inbox.close()

    def _insert_or_update_gate(self, gate: GateRecord) -> None:
        self.conn.execute(
            """
            insert into gates (
                gate_id, run_id, task_id, name, state, risk, owner_agent_id,
                requested_by, decision_by, reason, created_at, resolved_at
            ) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            on conflict(gate_id) do update set
                state = excluded.state,
                risk = excluded.risk,
                owner_agent_id = excluded.owner_agent_id,
                decision_by = excluded.decision_by,
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
            ),
        )
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
        state=row["state"],
        risk=row["risk"],
        owner_agent_id=row["owner_agent_id"],
        requested_by=row["requested_by"],
        decision_by=row["decision_by"],
        reason=row["reason"],
        created_at=row["created_at"],
        resolved_at=row["resolved_at"],
    )
