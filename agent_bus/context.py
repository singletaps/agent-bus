from __future__ import annotations

import json
import os
import sqlite3
from pathlib import Path
from threading import RLock
from typing import Any

from .authority import actor_role_for_principal
from .db import connect, initialize_database
from .models import BusEvent, ContextPacket, EventType, new_id, utc_now_iso
from .protocol_models import BindingStatus, FencingResult, PacketKind, Principal, ProjectionEffect
from .store import EventStore
from .unit_of_work import UnitOfWork

ACTIVE = "active"
INVALIDATED = "invalidated"
SUPERSEDED = "superseded"


class ContextPacketError(ValueError):
    """Base error for context packet operations."""


class ContextPacketNotFound(ContextPacketError):
    """Raised when a context packet does not exist."""


class ContextPacketInvalidated(ContextPacketError):
    def __init__(self, packet: ContextPacket) -> None:
        super().__init__(f"context packet invalidated: {packet.packet_id}")
        self.packet = packet

    def to_payload(self) -> dict[str, Any]:
        return {
            "error": "context_packet_invalidated",
            "packet_id": self.packet.packet_id,
            "invalidated_by_event_id": self.packet.invalidated_by_event_id,
            "invalidated_at": self.packet.invalidated_at,
            "superseded_by_packet_id": self.packet.superseded_by_packet_id,
        }


def migrate(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        create table if not exists context_packets (
            packet_id text primary key,
            version integer not null,
            packet_kind text not null default 'assignment',
            agent_id text not null,
            task_id text,
            run_id text,
            status text not null,
            summary text not null,
            instructions_json text not null,
            artifact_refs_json text not null,
            created_from_event_id text,
            supersedes_packet_id text,
            superseded_by_packet_id text,
            invalidated_by_event_id text,
            created_at text not null,
            updated_at text,
            invalidated_at text
        );

        create index if not exists idx_context_agent_status
        on context_packets(agent_id, status, created_at);

        create index if not exists idx_context_task_status
        on context_packets(task_id, status, created_at);
        """
    )
    for definition in (
        "packet_kind text not null default 'assignment'",
        "role_contract_json text",
        "objective text not null default ''",
        "constraints_json text not null default '[]'",
        "next_action text",
        "expected_outputs_json text not null default '[]'",
        "required_artifacts_json text not null default '[]'",
        "acceptance_gates_json text not null default '[]'",
        "updated_at text",
    ):
        _add_column_if_missing(conn, "context_packets", definition)


class ContextStore:
    def __init__(
        self,
        db_path: str | os.PathLike[str] | None = None,
        conn: sqlite3.Connection | None = None,
        trusted_compatibility: bool = False,
        principal: Principal | None = None,
    ) -> None:
        self.db_path = db_path
        initialize_database(db_path)
        self.conn = conn if conn is not None else connect(db_path)
        self._owns_connection = conn is None
        self._lock = RLock()
        self.trusted_compatibility = trusted_compatibility
        self.principal = principal
        migrate(self.conn)
        self.conn.commit()
        self.events = EventStore(db_path)

    def close(self) -> None:
        if self._owns_connection:
            self.conn.close()

    def create_packet(
        self,
        *,
        agent_id: str,
        summary: str,
        packet_kind: PacketKind | str = PacketKind.ASSIGNMENT,
        task_id: str | None = None,
        run_id: str | None = None,
        instructions: list[str] | dict[str, Any] | None = None,
        artifact_refs: list[str] | None = None,
        created_from_event_id: str | None = None,
        supersedes_packet_id: str | None = None,
        packet_id: str | None = None,
        version: int = 1,
        actor: str | None = None,
        principal: Principal | None = None,
        session_id: str | None = None,
        session_epoch: int | None = None,
        fencing_token: str | None = None,
    ) -> ContextPacket:
        principal = principal or self.principal
        packet = ContextPacket(
            packet_id=packet_id or new_id("ctx"),
            version=version,
            packet_kind=packet_kind,
            agent_id=agent_id,
            task_id=task_id,
            run_id=run_id,
            status=ACTIVE,
            summary=summary,
            instructions=instructions if instructions is not None else [],
            artifact_refs=artifact_refs or [],
            created_from_event_id=created_from_event_id,
            supersedes_packet_id=supersedes_packet_id,
        )
        with self._lock:
            from .protocol import ProtocolKernel

            def mutate(conn: sqlite3.Connection, event: BusEvent) -> None:
                _insert_packet_and_binding(
                    conn,
                    packet,
                    event,
                    session_id=session_id,
                    session_epoch=session_epoch,
                )

            result = ProtocolKernel(self.db_path, conn=self.conn).commit_event(
                _packet_event(EventType.CONTEXT_CREATED, packet, actor=actor, principal=principal),
                principal=principal,
                session_id=session_id,
                session_epoch=session_epoch,
                fencing_token=fencing_token,
                guard_targets=(("context_packets", packet.packet_id, EventType.CONTEXT_CREATED.value),),
                target_table="context_packets",
                target_id=packet.packet_id,
                reason="context packet created through ProtocolKernel command",
                mutation=mutate,
            )
            if not result.accepted:
                raise PermissionError(result.reason or "protocol rejected context packet creation")
        return packet

    def get_packet(self, packet_id: str, *, include_inactive: bool = False) -> ContextPacket:
        packet = self._load_packet(packet_id)
        if packet.status == INVALIDATED and not include_inactive:
            raise ContextPacketInvalidated(packet)
        return packet

    def invalidate_packet(
        self,
        packet_id: str,
        *,
        invalidated_by_event_id: str,
        actor: str | None = None,
        principal: Principal | None = None,
        session_id: str | None = None,
        session_epoch: int | None = None,
        fencing_token: str | None = None,
    ) -> ContextPacket:
        principal = principal or self.principal
        packet = self._load_packet(packet_id)
        if packet.status == INVALIDATED:
            return packet
        now = utc_now_iso()
        invalidated = packet.model_copy(update={"status": INVALIDATED, "invalidated_by_event_id": invalidated_by_event_id, "invalidated_at": now})
        with self._lock:
            from .protocol import ProtocolKernel

            result = ProtocolKernel(self.db_path, conn=self.conn).commit_event(
                _packet_event(EventType.CONTEXT_INVALIDATED, invalidated, actor=actor, principal=principal),
                principal=principal,
                session_id=session_id,
                session_epoch=session_epoch,
                fencing_token=fencing_token,
                guard_targets=(("context_packets", packet_id, EventType.CONTEXT_INVALIDATED.value),),
                target_table="context_packets",
                target_id=packet_id,
                reason="context packet invalidated through ProtocolKernel command",
                mutation=lambda conn, _event: conn.execute(
                    """
                    update context_packets
                    set status = ?, invalidated_by_event_id = ?, invalidated_at = ?
                    where packet_id = ?
                    """,
                    (INVALIDATED, invalidated_by_event_id, now, packet_id),
                ) and conn.execute(
                    """
                    update task_context_bindings
                    set status = ?, ended_at = ?
                    where context_packet_id = ? and status = ?
                    """,
                    (BindingStatus.INVALIDATED.value, now, packet_id, BindingStatus.ACTIVE.value),
                ),
            )
            if not result.accepted:
                raise PermissionError(result.reason or "protocol rejected context invalidation")
        return invalidated

    def supersede_packet(
        self,
        packet_id: str,
        *,
        summary: str,
        instructions: list[str] | dict[str, Any] | None = None,
        artifact_refs: list[str] | None = None,
        created_from_event_id: str | None = None,
        actor: str | None = None,
        principal: Principal | None = None,
        session_id: str | None = None,
        session_epoch: int | None = None,
        fencing_token: str | None = None,
    ) -> ContextPacket:
        principal = principal or self.principal
        old = self._load_packet(packet_id)
        if old.status == INVALIDATED:
            raise ContextPacketInvalidated(old)

        replacement = ContextPacket(
            packet_id=new_id("ctx"),
            version=old.version + 1,
            agent_id=old.agent_id,
            task_id=old.task_id,
            run_id=old.run_id,
            status=ACTIVE,
            summary=summary,
            instructions=instructions if instructions is not None else old.instructions,
            artifact_refs=artifact_refs if artifact_refs is not None else old.artifact_refs,
            created_from_event_id=created_from_event_id,
            supersedes_packet_id=old.packet_id,
        )
        with self._lock:
            from .protocol import ProtocolKernel

            def mutate(conn: sqlite3.Connection, _event: BusEvent) -> None:
                binding = conn.execute(
                    """
                    select session_id, session_epoch, binding_kind from task_context_bindings
                    where context_packet_id = ? and status = ?
                    order by created_at desc
                    limit 1
                    """,
                    (old.packet_id, BindingStatus.ACTIVE.value),
                ).fetchone()
                conn.execute(
                    _insert_packet_sql(),
                    packet_to_row(replacement),
                )
                if replacement.task_id:
                    conn.execute(
                        """
                        insert into task_context_bindings (
                            binding_id, task_id, agent_id, session_id, session_epoch,
                            context_packet_id, binding_kind, status, created_from_event_id, created_at, ended_at
                        ) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            new_id("bind"),
                            replacement.task_id,
                            replacement.agent_id,
                            binding["session_id"] if binding is not None else session_id,
                            binding["session_epoch"] if binding is not None else session_epoch,
                            replacement.packet_id,
                            binding["binding_kind"] if binding is not None else PacketKind.ASSIGNMENT.value,
                            BindingStatus.ACTIVE.value,
                            _event.event_id,
                            replacement.created_at,
                            None,
                        ),
                    )
                conn.execute(
                    """
                    update context_packets
                    set status = ?, superseded_by_packet_id = ?
                    where packet_id = ?
                    """,
                    (SUPERSEDED, replacement.packet_id, old.packet_id),
                )
                conn.execute(
                    """
                    update task_context_bindings
                    set status = ?, ended_at = ?
                    where context_packet_id = ? and status = ?
                    """,
                    (BindingStatus.SUPERSEDED.value, utc_now_iso(), old.packet_id, BindingStatus.ACTIVE.value),
                )

            result = ProtocolKernel(self.db_path, conn=self.conn).commit_event(
                _packet_event(EventType.CONTEXT_SUPERSEDED, replacement, actor=actor, principal=principal),
                principal=principal,
                session_id=session_id,
                session_epoch=session_epoch,
                fencing_token=fencing_token,
                guard_targets=(
                    ("context_packets", replacement.packet_id, EventType.CONTEXT_SUPERSEDED.value),
                    ("context_packets", old.packet_id, EventType.CONTEXT_SUPERSEDED.value),
                ),
                target_table="context_packets",
                target_id=replacement.packet_id,
                reason="context packet superseded through ProtocolKernel command",
                mutation=mutate,
            )
            if not result.accepted:
                raise PermissionError(result.reason or "protocol rejected context supersession")
        return replacement

    def create_rehydration_packet(
        self,
        *,
        agent_id: str,
        role_contract: str,
        current_task: str,
        last_known_summary: str,
        next_action: str,
        task_id: str | None = None,
        run_id: str | None = None,
        open_inbox_item_ids: list[str] | None = None,
        required_artifacts: list[str] | None = None,
        invalidated_packet_ids: list[str] | None = None,
        created_from_event_id: str | None = None,
        actor: str | None = None,
        principal: Principal | None = None,
        session_id: str | None = None,
        session_epoch: int | None = None,
        fencing_token: str | None = None,
    ) -> ContextPacket:
        instructions = {
            "kind": "rehydration",
            "role_contract": role_contract,
            "current_task": current_task,
            "last_known_summary": last_known_summary,
            "open_inbox_item_ids": open_inbox_item_ids
            if open_inbox_item_ids is not None
            else self._open_inbox_item_ids(agent_id),
            "required_artifacts": required_artifacts or [],
            "next_action": next_action,
            "invalidated_packet_ids": invalidated_packet_ids or [],
        }
        return self.create_packet(
            agent_id=agent_id,
            packet_kind=PacketKind.REHYDRATION,
            task_id=task_id,
            run_id=run_id,
            summary=f"Rehydration packet for {agent_id}",
            instructions=instructions,
            artifact_refs=required_artifacts or [],
            created_from_event_id=created_from_event_id,
            actor=actor,
            principal=principal,
            session_id=session_id,
            session_epoch=session_epoch,
            fencing_token=fencing_token,
        )

    def invalidate_active_binding_for_session(
        self,
        *,
        task_id: str,
        agent_id: str,
        session_id: str,
        invalidated_by_event_id: str,
        actor: str | None = None,
        principal: Principal | None = None,
    ) -> list[ContextPacket]:
        rows = self.conn.execute(
            """
            select distinct context_packet_id from task_context_bindings
            where task_id = ?
              and agent_id = ?
              and session_id = ?
              and status = ?
            order by created_at asc, context_packet_id asc
            """,
            (task_id, agent_id, session_id, BindingStatus.ACTIVE.value),
        ).fetchall()
        invalidated: list[ContextPacket] = []
        for row in rows:
            invalidated.append(
                self.invalidate_packet(
                    row["context_packet_id"],
                    invalidated_by_event_id=invalidated_by_event_id,
                    actor=actor,
                    principal=principal,
                )
            )
        return invalidated

    def list_packets(
        self,
        *,
        agent_id: str | None = None,
        task_id: str | None = None,
        run_id: str | None = None,
        status: str | None = None,
    ) -> list[ContextPacket]:
        clauses: list[str] = []
        params: list[str] = []
        if agent_id is not None:
            clauses.append("agent_id = ?")
            params.append(agent_id)
        if task_id is not None:
            clauses.append("task_id = ?")
            params.append(task_id)
        if run_id is not None:
            clauses.append("run_id = ?")
            params.append(run_id)
        if status is not None:
            clauses.append("status = ?")
            params.append(status)
        sql = "select * from context_packets"
        if clauses:
            sql += " where " + " and ".join(clauses)
        sql += " order by created_at asc, packet_id asc"
        rows = self.conn.execute(sql, params).fetchall()
        return [row_to_packet(row) for row in rows]

    def list_active_packets(
        self,
        *,
        agent_id: str | None = None,
        task_id: str | None = None,
        run_id: str | None = None,
    ) -> list[ContextPacket]:
        return self.list_packets(agent_id=agent_id, task_id=task_id, run_id=run_id, status=ACTIVE)

    def invalidate_agent_contexts(
        self,
        agent_id: str,
        *,
        invalidated_by_event_id: str,
        task_id: str | None = None,
        run_id: str | None = None,
        actor: str | None = None,
    ) -> list[ContextPacket]:
        invalidated: list[ContextPacket] = []
        for packet in self.list_active_packets(agent_id=agent_id, task_id=task_id, run_id=run_id):
            invalidated.append(
                self.invalidate_packet(
                    packet.packet_id,
                    invalidated_by_event_id=invalidated_by_event_id,
                    actor=actor,
                )
            )
        return invalidated

    def _load_packet(self, packet_id: str) -> ContextPacket:
        row = self.conn.execute("select * from context_packets where packet_id = ?", (packet_id,)).fetchone()
        if row is None:
            raise ContextPacketNotFound(f"unknown context packet: {packet_id}")
        return row_to_packet(row)

    def _open_inbox_item_ids(self, agent_id: str) -> list[str]:
        try:
            row_ids = self.conn.execute(
                """
                select inbox_id from inbox_items
                where agent_id = ? and status != 'acked'
                order by priority desc, created_at asc, inbox_id asc
                """,
                (agent_id,),
            ).fetchall()
        except sqlite3.OperationalError as exc:
            if "no such table" not in str(exc):
                raise
            return []
        return [row["inbox_id"] for row in row_ids]

    def _record_event(self, event_type: EventType, packet: ContextPacket, *, actor: str | None) -> None:
        self.events.append_event(
            _packet_event(event_type, packet, actor=actor)
        )


def create_packet(**kwargs: Any) -> ContextPacket:
    store = ContextStore(kwargs.pop("db_path", None))
    try:
        return store.create_packet(**kwargs)
    finally:
        store.close()


def _packet_event(
    event_type: EventType,
    packet: ContextPacket,
    *,
    actor: str | None,
    principal: Principal | None = None,
) -> BusEvent:
    return BusEvent(
        type=event_type,
        actor=actor,
        actor_role=actor_role_for_principal(principal),
        run_id=packet.run_id,
        task_id=packet.task_id,
        agent_id=packet.agent_id,
        context_packet_id=packet.packet_id,
        projection_effect=ProjectionEffect.COMMIT,
        fencing_result=FencingResult.NOT_REQUIRED,
        payload=packet.model_dump(mode="json"),
    )


def get_packet(packet_id: str, *, db_path: str | os.PathLike[str] | None = None, include_inactive: bool = False) -> ContextPacket:
    store = ContextStore(db_path)
    try:
        return store.get_packet(packet_id, include_inactive=include_inactive)
    finally:
        store.close()


def invalidate_packet(packet_id: str, *, db_path: str | os.PathLike[str] | None = None, **kwargs: Any) -> ContextPacket:
    store = ContextStore(db_path)
    try:
        return store.invalidate_packet(packet_id, **kwargs)
    finally:
        store.close()


def supersede_packet(packet_id: str, *, db_path: str | os.PathLike[str] | None = None, **kwargs: Any) -> ContextPacket:
    store = ContextStore(db_path)
    try:
        return store.supersede_packet(packet_id, **kwargs)
    finally:
        store.close()


def create_rehydration_packet(**kwargs: Any) -> ContextPacket:
    store = ContextStore(kwargs.pop("db_path", None))
    try:
        return store.create_rehydration_packet(**kwargs)
    finally:
        store.close()


def list_active_packets(
    *,
    db_path: str | os.PathLike[str] | None = None,
    agent_id: str | None = None,
    task_id: str | None = None,
    run_id: str | None = None,
) -> list[ContextPacket]:
    store = ContextStore(db_path)
    try:
        return store.list_active_packets(agent_id=agent_id, task_id=task_id, run_id=run_id)
    finally:
        store.close()


def invalidate_agent_contexts(
    agent_id: str,
    *,
    db_path: str | os.PathLike[str] | None = None,
    **kwargs: Any,
) -> list[ContextPacket]:
    store = ContextStore(db_path)
    try:
        return store.invalidate_agent_contexts(agent_id, **kwargs)
    finally:
        store.close()


def packet_to_row(packet: ContextPacket) -> tuple[Any, ...]:
    return (
        packet.packet_id,
        packet.version,
        _enum_value(packet.packet_kind),
        packet.agent_id,
        packet.task_id,
        packet.run_id,
        packet.status,
        packet.summary,
        json.dumps(packet.instructions, sort_keys=True),
        json.dumps(packet.artifact_refs, sort_keys=True),
        packet.created_from_event_id,
        packet.supersedes_packet_id,
        packet.superseded_by_packet_id,
        packet.invalidated_by_event_id,
        packet.created_at,
        packet.updated_at,
        packet.invalidated_at,
    )


def row_to_packet(row: sqlite3.Row) -> ContextPacket:
    return ContextPacket(
        packet_id=row["packet_id"],
        version=row["version"],
        packet_kind=row["packet_kind"],
        agent_id=row["agent_id"],
        task_id=row["task_id"],
        run_id=row["run_id"],
        status=row["status"],
        summary=row["summary"],
        instructions=json.loads(row["instructions_json"]),
        artifact_refs=json.loads(row["artifact_refs_json"]),
        created_from_event_id=row["created_from_event_id"],
        supersedes_packet_id=row["supersedes_packet_id"],
        superseded_by_packet_id=row["superseded_by_packet_id"],
        invalidated_by_event_id=row["invalidated_by_event_id"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        invalidated_at=row["invalidated_at"],
    )


def _insert_packet_sql() -> str:
    return """
    insert into context_packets (
        packet_id, version, packet_kind, agent_id, task_id, run_id, status, summary,
        instructions_json, artifact_refs_json, created_from_event_id,
        supersedes_packet_id, superseded_by_packet_id,
        invalidated_by_event_id, created_at, updated_at, invalidated_at
    ) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """


def _insert_packet_and_binding(
    conn: sqlite3.Connection,
    packet: ContextPacket,
    event: BusEvent,
    *,
    session_id: str | None,
    session_epoch: int | None,
) -> None:
    conn.execute(_insert_packet_sql(), packet_to_row(packet))
    if packet.task_id is None:
        return
    conn.execute(
        """
        insert into task_context_bindings (
            binding_id, task_id, agent_id, session_id, session_epoch,
            context_packet_id, binding_kind, status, created_from_event_id, created_at, ended_at
        ) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            new_id("bind"),
            packet.task_id,
            packet.agent_id,
            session_id,
            session_epoch,
            packet.packet_id,
            _enum_value(packet.packet_kind),
            BindingStatus.ACTIVE.value,
            event.event_id,
            packet.created_at,
            None,
        ),
    )


def _add_column_if_missing(conn: sqlite3.Connection, table: str, column_definition: str) -> None:
    column = column_definition.split()[0]
    columns = {row[1] for row in conn.execute(f"pragma table_info({table})").fetchall()}
    if column not in columns:
        conn.execute(f"alter table {table} add column {column_definition}")


def _enum_value(value: object | None) -> str | None:
    if value is None:
        return None
    if hasattr(value, "value"):
        return str(value.value)
    return str(value)
