from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Iterable

from .db import connect, initialize_database
from .models import BusEvent


class EventStore:
    def __init__(self, db_path: str | Path | None = None) -> None:
        self.db_path = db_path
        initialize_database(db_path)

    def append_event(self, event: BusEvent) -> BusEvent:
        payload_json = json.dumps(event.payload, sort_keys=True, separators=(",", ":"))
        event_type = event.type.value if hasattr(event.type, "value") else str(event.type)

        with connect(self.db_path) as conn:
            cursor = conn.execute(
                """
                insert into event_log (
                    event_id, type, ts, actor, run_id, task_id, agent_id,
                    correlation_id, causation_id, payload_json
                )
                values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event.event_id,
                    event_type,
                    event.ts,
                    event.actor,
                    event.run_id,
                    event.task_id,
                    event.agent_id,
                    event.correlation_id,
                    event.causation_id,
                    payload_json,
                ),
            )
            seq = int(cursor.lastrowid)

        return event.model_copy(update={"seq": seq, "type": event_type})

    def get_event(self, event_id: str) -> BusEvent | None:
        with connect(self.db_path) as conn:
            row = conn.execute("select * from event_log where event_id = ?", (event_id,)).fetchone()
        return _row_to_event(row) if row else None

    def query_events(
        self,
        *,
        after_seq: int | None = None,
        event_type: str | None = None,
        run_id: str | None = None,
        task_id: str | None = None,
        agent_id: str | None = None,
        limit: int | None = None,
    ) -> list[BusEvent]:
        clauses: list[str] = []
        params: list[object] = []
        if after_seq is not None:
            clauses.append("seq > ?")
            params.append(after_seq)
        if event_type is not None:
            clauses.append("type = ?")
            params.append(event_type)
        if run_id is not None:
            clauses.append("run_id = ?")
            params.append(run_id)
        if task_id is not None:
            clauses.append("task_id = ?")
            params.append(task_id)
        if agent_id is not None:
            clauses.append("agent_id = ?")
            params.append(agent_id)

        sql = "select * from event_log"
        if clauses:
            sql += " where " + " and ".join(clauses)
        sql += " order by seq asc"
        if limit is not None:
            sql += " limit ?"
            params.append(limit)

        with connect(self.db_path) as conn:
            rows = conn.execute(sql, params).fetchall()
        return [_row_to_event(row) for row in rows]

    def replay_all(self) -> list[BusEvent]:
        return self.query_events()


def append_event(event: BusEvent, db_path: str | Path | None = None) -> BusEvent:
    return EventStore(db_path).append_event(event)


def get_event(event_id: str, db_path: str | Path | None = None) -> BusEvent | None:
    return EventStore(db_path).get_event(event_id)


def query_events(
    after_seq: int | None = None,
    event_type: str | None = None,
    run_id: str | None = None,
    task_id: str | None = None,
    agent_id: str | None = None,
    limit: int | None = None,
    db_path: str | Path | None = None,
) -> list[BusEvent]:
    return EventStore(db_path).query_events(
        after_seq=after_seq,
        event_type=event_type,
        run_id=run_id,
        task_id=task_id,
        agent_id=agent_id,
        limit=limit,
    )


def replay_all(db_path: str | Path | None = None) -> list[BusEvent]:
    return EventStore(db_path).replay_all()


def _row_to_event(row: sqlite3.Row) -> BusEvent:
    return BusEvent(
        seq=row["seq"],
        event_id=row["event_id"],
        type=row["type"],
        ts=row["ts"],
        actor=row["actor"],
        run_id=row["run_id"],
        task_id=row["task_id"],
        agent_id=row["agent_id"],
        correlation_id=row["correlation_id"],
        causation_id=row["causation_id"],
        payload=json.loads(row["payload_json"]),
    )

