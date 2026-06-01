from __future__ import annotations

import json
import os
import sqlite3
from pathlib import Path
from threading import RLock
from typing import Any

from .db import connect, initialize_database
from .models import BusEvent, ContextPacket, EventType, new_id, utc_now_iso
from .store import EventStore

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
            invalidated_at text
        );

        create index if not exists idx_context_agent_status
        on context_packets(agent_id, status, created_at);

        create index if not exists idx_context_task_status
        on context_packets(task_id, status, created_at);
        """
    )


class ContextStore:
    def __init__(
        self,
        db_path: str | os.PathLike[str] | None = None,
        conn: sqlite3.Connection | None = None,
    ) -> None:
        self.db_path = db_path
        initialize_database(db_path)
        self.conn = conn if conn is not None else connect(db_path)
        self._owns_connection = conn is None
        self._lock = RLock()
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
        task_id: str | None = None,
        run_id: str | None = None,
        instructions: list[str] | dict[str, Any] | None = None,
        artifact_refs: list[str] | None = None,
        created_from_event_id: str | None = None,
        supersedes_packet_id: str | None = None,
        packet_id: str | None = None,
        version: int = 1,
        actor: str | None = None,
    ) -> ContextPacket:
        packet = ContextPacket(
            packet_id=packet_id or new_id("ctx"),
            version=version,
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
            self.conn.execute(
                """
                insert into context_packets (
                    packet_id, version, agent_id, task_id, run_id, status, summary,
                    instructions_json, artifact_refs_json, created_from_event_id,
                    supersedes_packet_id, superseded_by_packet_id,
                    invalidated_by_event_id, created_at, invalidated_at
                ) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                packet_to_row(packet),
            )
            self.conn.commit()
        self._record_event(EventType.CONTEXT_CREATED, packet, actor=actor)
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
    ) -> ContextPacket:
        packet = self._load_packet(packet_id)
        if packet.status == INVALIDATED:
            return packet
        now = utc_now_iso()
        with self._lock:
            self.conn.execute(
                """
                update context_packets
                set status = ?, invalidated_by_event_id = ?, invalidated_at = ?
                where packet_id = ?
                """,
                (INVALIDATED, invalidated_by_event_id, now, packet_id),
            )
            self.conn.commit()
        invalidated = self._load_packet(packet_id)
        self._record_event(EventType.CONTEXT_INVALIDATED, invalidated, actor=actor)
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
    ) -> ContextPacket:
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
            self.conn.execute(
                """
                insert into context_packets (
                    packet_id, version, agent_id, task_id, run_id, status, summary,
                    instructions_json, artifact_refs_json, created_from_event_id,
                    supersedes_packet_id, superseded_by_packet_id,
                    invalidated_by_event_id, created_at, invalidated_at
                ) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                packet_to_row(replacement),
            )
            self.conn.execute(
                """
                update context_packets
                set status = ?, superseded_by_packet_id = ?
                where packet_id = ?
                """,
                (SUPERSEDED, replacement.packet_id, old.packet_id),
            )
            self.conn.commit()
        self._record_event(EventType.CONTEXT_SUPERSEDED, replacement, actor=actor)
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
            task_id=task_id,
            run_id=run_id,
            summary=f"Rehydration packet for {agent_id}",
            instructions=instructions,
            artifact_refs=required_artifacts or [],
            created_from_event_id=created_from_event_id,
            actor=actor,
        )

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
            BusEvent(
                type=event_type,
                actor=actor,
                run_id=packet.run_id,
                task_id=packet.task_id,
                agent_id=packet.agent_id,
                payload=packet.model_dump(mode="json"),
            )
        )


def create_packet(**kwargs: Any) -> ContextPacket:
    store = ContextStore(kwargs.pop("db_path", None))
    try:
        return store.create_packet(**kwargs)
    finally:
        store.close()


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
        packet.invalidated_at,
    )


def row_to_packet(row: sqlite3.Row) -> ContextPacket:
    return ContextPacket(
        packet_id=row["packet_id"],
        version=row["version"],
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
        invalidated_at=row["invalidated_at"],
    )
