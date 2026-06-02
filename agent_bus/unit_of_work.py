from __future__ import annotations

import json
import os
import sqlite3
from pathlib import Path
from typing import Any, Iterable

from pydantic import BaseModel

from .db import connect, initialize_database
from .models import BusEvent, new_id
from .protocol_models import ProjectionEffect, ProjectionEffectRecord, ProtocolViolation, TaskClaimRecord


class UnitOfWork:
    """Atomic write boundary used by the protocol kernel."""

    def __init__(
        self,
        db_path: str | os.PathLike[str] | None = None,
        *,
        conn: sqlite3.Connection | None = None,
    ) -> None:
        self.db_path = Path(db_path) if db_path is not None else None
        self._provided_conn = conn
        self.conn: sqlite3.Connection | None = conn
        self._owns_connection = conn is None

    def __enter__(self) -> UnitOfWork:
        if self.conn is None:
            initialize_database(self.db_path)
            self.conn = connect(self.db_path)
        self.conn.execute("BEGIN")
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        if self.conn is None:
            return
        if exc_type is None:
            self.conn.commit()
        else:
            self.conn.rollback()
        if self._owns_connection:
            self.conn.close()
            self.conn = None

    def append_event(
        self,
        event: BusEvent,
        *,
        guard: bool = True,
        guard_targets: Iterable[tuple[str, str, str]] = (),
    ) -> BusEvent:
        conn = self._require_conn()
        event_type = _enum_value(event.type)
        projection_effect = _enum_value(event.projection_effect)
        fencing_result = _enum_value(event.fencing_result)
        if guard:
            self.add_kernel_guard(event_id=event.event_id, action=event_type)
            for target_table, target_id, action in guard_targets:
                self.add_kernel_guard(
                    event_id=event.event_id,
                    action=action,
                    target_table=target_table,
                    target_id=target_id,
                )
        cursor = conn.execute(
            """
            insert into event_log (
                event_id, type, ts, actor, run_id, task_id, agent_id,
                actor_role, session_id, session_epoch, context_packet_id, gate_id,
                artifact_id, correlation_id, causation_id, projection_effect,
                fencing_result, payload_json
            )
            values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                event.event_id,
                event_type,
                event.ts,
                event.actor,
                event.run_id,
                event.task_id,
                event.agent_id,
                event.actor_role,
                event.session_id,
                event.session_epoch,
                event.context_packet_id,
                event.gate_id,
                event.artifact_id,
                event.correlation_id,
                event.causation_id,
                projection_effect,
                fencing_result,
                _json(event.payload),
            ),
        )
        return event.model_copy(
            update={
                "seq": int(cursor.lastrowid),
                "type": event_type,
                "projection_effect": projection_effect,
                "fencing_result": fencing_result,
            }
        )

    def add_kernel_guard(
        self,
        *,
        event_id: str | None,
        action: str,
        target_table: str | None = None,
        target_id: str | None = None,
    ) -> str:
        guard_id = new_id("guard")
        self._require_conn().execute(
            """
            insert into kernel_write_guards (
                guard_id, event_id, target_table, target_id, action
            ) values (?, ?, ?, ?, ?)
            """,
            (guard_id, event_id, target_table, target_id, action),
        )
        return guard_id

    def record_protocol_violation(self, violation: ProtocolViolation) -> ProtocolViolation:
        self._require_conn().execute(
            """
            insert into protocol_violations (
                violation_id, attempted_event_id, actor, actor_role, action, reason,
                fencing_result, projection_effect, run_id, task_id, agent_id,
                session_id, context_packet_id, payload_json, created_at
            ) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                violation.violation_id,
                violation.attempted_event_id,
                violation.actor,
                violation.actor_role,
                violation.action,
                violation.reason,
                _enum_value(violation.fencing_result),
                _enum_value(violation.projection_effect),
                violation.run_id,
                violation.task_id,
                violation.agent_id,
                violation.session_id,
                violation.context_packet_id,
                _json(violation.payload),
                violation.created_at,
            ),
        )
        return violation

    def record_projection_effect(
        self,
        *,
        effect: ProjectionEffect,
        event_id: str | None = None,
        attempted_event_id: str | None = None,
        reason: str | None = None,
        target_table: str | None = None,
        target_id: str | None = None,
        run_id: str | None = None,
        task_id: str | None = None,
    ) -> ProjectionEffectRecord:
        record = ProjectionEffectRecord(
            event_id=event_id,
            attempted_event_id=attempted_event_id,
            effect=effect,
            reason=reason,
            target_table=target_table,
            target_id=target_id,
            run_id=run_id,
            task_id=task_id,
        )
        self._require_conn().execute(
            """
            insert into projection_effects (
                effect_id, event_id, attempted_event_id, effect, reason,
                target_table, target_id, run_id, task_id, created_at
            ) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                record.effect_id,
                record.event_id,
                record.attempted_event_id,
                record.effect.value,
                record.reason,
                record.target_table,
                record.target_id,
                record.run_id,
                record.task_id,
                record.created_at,
            ),
        )
        return record

    def record_task_claim(self, claim: TaskClaimRecord) -> TaskClaimRecord:
        self._require_conn().execute(
            """
            insert into task_claims (
                claim_id, claim_kind, task_id, run_id, agent_id, session_id,
                session_epoch, context_packet_id, status, payload_json,
                created_from_event_id, committed_by_event_id, created_at, updated_at
            ) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                claim.claim_id,
                _enum_value(claim.claim_kind),
                claim.task_id,
                claim.run_id,
                claim.agent_id,
                claim.session_id,
                claim.session_epoch,
                claim.context_packet_id,
                _enum_value(claim.status),
                _json(claim.payload),
                claim.created_from_event_id,
                claim.committed_by_event_id,
                claim.created_at,
                claim.updated_at,
            ),
        )
        return claim

    def update_task_claim(
        self,
        claim_id: str,
        *,
        status: str,
        payload: dict[str, Any],
        committed_by_event_id: str | None = None,
        updated_at: str,
    ) -> None:
        self._require_conn().execute(
            """
            update task_claims
            set status = ?,
                payload_json = ?,
                committed_by_event_id = coalesce(?, committed_by_event_id),
                updated_at = ?
            where claim_id = ?
            """,
            (status, _json(payload), committed_by_event_id, updated_at, claim_id),
        )

    def _require_conn(self) -> sqlite3.Connection:
        if self.conn is None:
            raise RuntimeError("UnitOfWork is not active")
        return self.conn


def _enum_value(value: object | None) -> str | None:
    if value is None:
        return None
    if hasattr(value, "value"):
        return str(value.value)
    return str(value)


def _json(value: Any) -> str:
    if isinstance(value, BaseModel):
        value = value.model_dump(mode="json")
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)
