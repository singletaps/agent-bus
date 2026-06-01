from __future__ import annotations

import json
import os
import sqlite3
from pathlib import Path
from typing import Any

from .agents import AgentDirectory, AgentDirectoryError
from .db import connect, initialize_database
from .inbox import InboxStore
from .models import (
    AgentRuntimeState,
    ArtifactRecord,
    BusEvent,
    CoordinationRecord,
    EventType,
    RunRecord,
    RunState,
    TaskRecord,
    TaskState,
    new_id,
    utc_now_iso,
)
from .store import EventStore


RUNTIME_SCHEMA_VERSION = 4

TASK_TRANSITIONS: dict[TaskState, set[TaskState]] = {
    TaskState.CREATED: {TaskState.ASSIGNED, TaskState.SUPERSEDED, TaskState.FAILED},
    TaskState.ASSIGNED: {
        TaskState.ACKNOWLEDGED,
        TaskState.WORKING,
        TaskState.BLOCKED,
        TaskState.REASSIGNED,
        TaskState.FAILED,
    },
    TaskState.ACKNOWLEDGED: {TaskState.WORKING, TaskState.BLOCKED, TaskState.FAILED},
    TaskState.WORKING: {TaskState.BLOCKED, TaskState.COMPLETED, TaskState.FAILED, TaskState.REASSIGNED},
    TaskState.BLOCKED: {TaskState.WORKING, TaskState.FAILED, TaskState.REASSIGNED},
    TaskState.REASSIGNED: {TaskState.ACKNOWLEDGED, TaskState.WORKING, TaskState.BLOCKED, TaskState.FAILED},
    TaskState.COMPLETED: set(),
    TaskState.FAILED: set(),
    TaskState.SUPERSEDED: set(),
}


class StateTransitionError(ValueError):
    """Raised when a runtime record state transition is invalid."""


class RuntimeRecordError(ValueError):
    """Raised when a runtime coordination record cannot be found."""


def migrate_runtime_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        create table if not exists runs (
            run_id text primary key,
            title text not null,
            objective text not null,
            status text not null,
            created_by text,
            created_at text not null,
            updated_at text not null
        );

        create table if not exists tasks (
            task_id text primary key,
            run_id text,
            title text not null,
            owner_agent_id text,
            assignee_agent_id text,
            status text not null,
            priority integer not null,
            parent_task_id text,
            supersedes_task_id text,
            blocked_reason text,
            created_at text not null,
            updated_at text not null,
            completed_at text,
            failed_at text
        );

        create index if not exists idx_tasks_run_status on tasks(run_id, status);
        create index if not exists idx_tasks_assignee_status on tasks(assignee_agent_id, status);

        create table if not exists coordination_records (
            record_id text primary key,
            kind text not null,
            run_id text,
            task_id text,
            agent_id text,
            payload_json text not null,
            created_at text not null,
            expires_at text
        );

        create index if not exists idx_coordination_task_kind on coordination_records(task_id, kind);

        create table if not exists gates (
            gate_id text primary key,
            run_id text,
            task_id text,
            name text not null,
            state text not null,
            risk text not null,
            owner_agent_id text,
            requested_by text,
            decision_by text,
            reason text,
            created_at text not null,
            resolved_at text
        );

        create index if not exists idx_gates_run_state on gates(run_id, state);

        create table if not exists review_findings (
            finding_id text primary key,
            run_id text,
            task_id text,
            severity text not null,
            category text not null,
            file_path text,
            evidence text not null,
            requested_change text not null,
            blocking integer not null,
            resolved_by text,
            status text not null,
            created_at text not null,
            updated_at text not null,
            resolved_at text
        );

        create index if not exists idx_review_findings_task_status
        on review_findings(task_id, status);

        create table if not exists artifacts (
            artifact_id text primary key,
            run_id text,
            task_id text,
            kind text not null,
            uri text not null,
            metadata_json text not null,
            created_by text,
            created_at text not null
        );

        create index if not exists idx_artifacts_task on artifacts(task_id);
        """
    )
    conn.execute(
        "insert or ignore into schema_migrations(version) values (?)",
        (RUNTIME_SCHEMA_VERSION,),
    )
    conn.commit()


class TaskBoard:
    def __init__(
        self,
        db_path: str | os.PathLike[str] | None = None,
        *,
        conn: sqlite3.Connection | None = None,
        event_store: EventStore | None = None,
        inbox_store: InboxStore | None = None,
        agent_directory: AgentDirectory | None = None,
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
        self.agent_directory = agent_directory

    def close(self) -> None:
        if self._owns_connection:
            self.conn.close()

    def create_run(
        self,
        title: str,
        *,
        objective: str = "",
        created_by: str | None = None,
        run_id: str | None = None,
    ) -> RunRecord:
        now = utc_now_iso()
        run = RunRecord(
            run_id=run_id or new_id("run"),
            title=title,
            objective=objective,
            status=RunState.CREATED,
            created_by=created_by,
            created_at=now,
            updated_at=now,
        )
        self.conn.execute(
            """
            insert into runs (run_id, title, objective, status, created_by, created_at, updated_at)
            values (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                run.run_id,
                run.title,
                run.objective,
                run.status.value,
                run.created_by,
                run.created_at,
                run.updated_at,
            ),
        )
        self.conn.commit()
        self._append_event(EventType.RUN_CREATED, actor=created_by, run_id=run.run_id, payload=run)
        return run

    def get_run(self, run_id: str) -> RunRecord:
        row = self.conn.execute("select * from runs where run_id = ?", (run_id,)).fetchone()
        if row is None:
            raise RuntimeRecordError(f"unknown run: {run_id}")
        return _row_to_run(row)

    def create_task(
        self,
        title: str,
        *,
        run_id: str | None = None,
        owner_agent_id: str | None = None,
        assignee_agent_id: str | None = None,
        priority: int = 0,
        parent_task_id: str | None = None,
        task_id: str | None = None,
    ) -> TaskRecord:
        now = utc_now_iso()
        task = TaskRecord(
            task_id=task_id or new_id("task"),
            run_id=run_id,
            title=title,
            owner_agent_id=owner_agent_id,
            assignee_agent_id=assignee_agent_id,
            status=TaskState.CREATED,
            priority=priority,
            parent_task_id=parent_task_id,
            created_at=now,
            updated_at=now,
        )
        self._insert_or_update_task(task)
        self._append_event(EventType.TASK_CREATED, actor=owner_agent_id, run_id=run_id, task_id=task.task_id, payload=task)
        if assignee_agent_id:
            task = self.assign_task(task.task_id, assignee_agent_id, actor=owner_agent_id)
        return task

    def get_task(self, task_id: str) -> TaskRecord:
        row = self.conn.execute("select * from tasks where task_id = ?", (task_id,)).fetchone()
        if row is None:
            raise RuntimeRecordError(f"unknown task: {task_id}")
        return _row_to_task(row)

    def list_tasks(self, *, run_id: str | None = None, assignee_agent_id: str | None = None) -> list[TaskRecord]:
        clauses: list[str] = []
        params: list[object] = []
        if run_id is not None:
            clauses.append("run_id = ?")
            params.append(run_id)
        if assignee_agent_id is not None:
            clauses.append("assignee_agent_id = ?")
            params.append(assignee_agent_id)
        sql = "select * from tasks"
        if clauses:
            sql += " where " + " and ".join(clauses)
        sql += " order by created_at asc, task_id asc"
        rows = self.conn.execute(sql, params).fetchall()
        return [_row_to_task(row) for row in rows]

    def assign_task(self, task_id: str, assignee_agent_id: str, *, actor: str | None = None) -> TaskRecord:
        task = self.get_task(task_id)
        next_state = TaskState.ASSIGNED if task.status is TaskState.CREATED else TaskState.REASSIGNED
        self._assert_transition(task.status, next_state)
        task.status = next_state
        task.assignee_agent_id = assignee_agent_id
        task.blocked_reason = None
        task.updated_at = utc_now_iso()
        self._insert_or_update_task(task)
        self._append_event(
            EventType.TASK_ASSIGNED if next_state is TaskState.ASSIGNED else EventType.TASK_REASSIGNED,
            actor=actor,
            run_id=task.run_id,
            task_id=task.task_id,
            agent_id=assignee_agent_id,
            payload=task,
        )
        self._enqueue(
            assignee_agent_id,
            "task_assigned",
            {"task_id": task.task_id, "run_id": task.run_id, "state": task.status.value},
            priority=max(50, task.priority),
            dedupe_key=f"task_assigned:{task.task_id}:{task.status.value}",
        )
        return task

    def acknowledge_task(self, task_id: str, *, actor: str | None = None) -> TaskRecord:
        return self._transition_task(task_id, TaskState.ACKNOWLEDGED, actor=actor, event_type=EventType.TASK_ACKNOWLEDGED)

    def start_task(self, task_id: str, *, actor: str | None = None) -> TaskRecord:
        task = self._transition_task(task_id, TaskState.WORKING, actor=actor, event_type=EventType.TASK_PROGRESS)
        self._update_active_session(task.assignee_agent_id, AgentRuntimeState.WORKING, reason=f"task {task.task_id} working")
        return task

    def block_task(self, task_id: str, reason: str, *, actor: str | None = None) -> TaskRecord:
        task = self.get_task(task_id)
        self._assert_transition(task.status, TaskState.BLOCKED)
        task.status = TaskState.BLOCKED
        task.blocked_reason = reason
        task.updated_at = utc_now_iso()
        self._insert_or_update_task(task)
        self._append_event(
            EventType.TASK_BLOCKED,
            actor=actor,
            run_id=task.run_id,
            task_id=task.task_id,
            agent_id=task.assignee_agent_id,
            payload=task,
        )
        return task

    def complete_task(self, task_id: str, *, actor: str | None = None) -> TaskRecord:
        task = self._transition_task(
            task_id,
            TaskState.COMPLETED,
            actor=actor,
            event_type=EventType.TASK_COMPLETED,
            timestamp_field="completed_at",
        )
        self._update_active_session(
            task.assignee_agent_id,
            AgentRuntimeState.STANDBY_READY,
            reason=f"task {task.task_id} completed",
        )
        return task

    def fail_task(self, task_id: str, reason: str, *, actor: str | None = None) -> TaskRecord:
        task = self.get_task(task_id)
        self._assert_transition(task.status, TaskState.FAILED)
        task.status = TaskState.FAILED
        task.blocked_reason = reason
        task.failed_at = utc_now_iso()
        task.updated_at = task.failed_at
        self._insert_or_update_task(task)
        self._append_event(
            EventType.TASK_FAILED,
            actor=actor,
            run_id=task.run_id,
            task_id=task.task_id,
            agent_id=task.assignee_agent_id,
            payload=task,
        )
        return task

    def supersede_task(self, task_id: str, superseded_by_task_id: str, *, actor: str | None = None) -> TaskRecord:
        task = self.get_task(task_id)
        self._assert_transition(task.status, TaskState.SUPERSEDED)
        task.status = TaskState.SUPERSEDED
        task.supersedes_task_id = superseded_by_task_id
        task.updated_at = utc_now_iso()
        self._insert_or_update_task(task)
        self._append_event(
            EventType.TASK_SUPERSEDED,
            actor=actor,
            run_id=task.run_id,
            task_id=task.task_id,
            payload=task,
        )
        return task

    def record_coordination(
        self,
        kind: str,
        *,
        run_id: str | None = None,
        task_id: str | None = None,
        agent_id: str | None = None,
        payload: dict[str, Any] | None = None,
        expires_at: str | None = None,
        record_id: str | None = None,
    ) -> CoordinationRecord:
        record = CoordinationRecord(
            record_id=record_id or new_id("coord"),
            kind=kind,
            run_id=run_id,
            task_id=task_id,
            agent_id=agent_id,
            payload=payload or {},
            expires_at=expires_at,
        )
        self.conn.execute(
            """
            insert into coordination_records (
                record_id, kind, run_id, task_id, agent_id, payload_json, created_at, expires_at
            ) values (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                record.record_id,
                record.kind,
                record.run_id,
                record.task_id,
                record.agent_id,
                json.dumps(record.payload, sort_keys=True),
                record.created_at,
                record.expires_at,
            ),
        )
        self.conn.commit()
        self._append_event(EventType.COORDINATION_RECORDED, actor=agent_id, run_id=run_id, task_id=task_id, payload=record)
        return record

    def list_coordination_records(self, task_id: str | None = None) -> list[CoordinationRecord]:
        if task_id is None:
            rows = self.conn.execute("select * from coordination_records order by created_at asc").fetchall()
        else:
            rows = self.conn.execute(
                "select * from coordination_records where task_id = ? order by created_at asc",
                (task_id,),
            ).fetchall()
        return [_row_to_coordination(row) for row in rows]

    def create_artifact(
        self,
        kind: str,
        uri: str,
        *,
        run_id: str | None = None,
        task_id: str | None = None,
        metadata: dict[str, Any] | None = None,
        created_by: str | None = None,
        artifact_id: str | None = None,
    ) -> ArtifactRecord:
        artifact = ArtifactRecord(
            artifact_id=artifact_id or new_id("artifact"),
            run_id=run_id,
            task_id=task_id,
            kind=kind,
            uri=uri,
            metadata=metadata or {},
            created_by=created_by,
        )
        self.conn.execute(
            """
            insert into artifacts (
                artifact_id, run_id, task_id, kind, uri, metadata_json, created_by, created_at
            ) values (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                artifact.artifact_id,
                artifact.run_id,
                artifact.task_id,
                artifact.kind,
                artifact.uri,
                json.dumps(artifact.metadata, sort_keys=True),
                artifact.created_by,
                artifact.created_at,
            ),
        )
        self.conn.commit()
        self._append_event(
            EventType.ARTIFACT_CREATED,
            actor=created_by,
            run_id=run_id,
            task_id=task_id,
            payload=artifact,
        )
        return artifact

    def _transition_task(
        self,
        task_id: str,
        next_state: TaskState,
        *,
        actor: str | None,
        event_type: EventType,
        timestamp_field: str | None = None,
    ) -> TaskRecord:
        task = self.get_task(task_id)
        self._assert_transition(task.status, next_state)
        now = utc_now_iso()
        task.status = next_state
        task.updated_at = now
        if timestamp_field is not None:
            setattr(task, timestamp_field, now)
        if next_state is not TaskState.BLOCKED:
            task.blocked_reason = None
        self._insert_or_update_task(task)
        self._append_event(
            event_type,
            actor=actor,
            run_id=task.run_id,
            task_id=task.task_id,
            agent_id=task.assignee_agent_id,
            payload=task,
        )
        return task

    def _assert_transition(self, current: TaskState | str, next_state: TaskState) -> None:
        current_state = TaskState(current)
        if next_state not in TASK_TRANSITIONS[current_state]:
            raise StateTransitionError(f"invalid task transition: {current_state.value} -> {next_state.value}")

    def _insert_or_update_task(self, task: TaskRecord) -> None:
        self.conn.execute(
            """
            insert into tasks (
                task_id, run_id, title, owner_agent_id, assignee_agent_id, status,
                priority, parent_task_id, supersedes_task_id, blocked_reason,
                created_at, updated_at, completed_at, failed_at
            ) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            on conflict(task_id) do update set
                run_id = excluded.run_id,
                title = excluded.title,
                owner_agent_id = excluded.owner_agent_id,
                assignee_agent_id = excluded.assignee_agent_id,
                status = excluded.status,
                priority = excluded.priority,
                parent_task_id = excluded.parent_task_id,
                supersedes_task_id = excluded.supersedes_task_id,
                blocked_reason = excluded.blocked_reason,
                updated_at = excluded.updated_at,
                completed_at = excluded.completed_at,
                failed_at = excluded.failed_at
            """,
            (
                task.task_id,
                task.run_id,
                task.title,
                task.owner_agent_id,
                task.assignee_agent_id,
                task.status.value,
                task.priority,
                task.parent_task_id,
                task.supersedes_task_id,
                task.blocked_reason,
                task.created_at,
                task.updated_at,
                task.completed_at,
                task.failed_at,
            ),
        )
        self.conn.commit()

    def _append_event(
        self,
        event_type: EventType,
        *,
        actor: str | None = None,
        run_id: str | None = None,
        task_id: str | None = None,
        agent_id: str | None = None,
        payload: RunRecord | TaskRecord | ArtifactRecord | CoordinationRecord | dict[str, Any],
    ) -> BusEvent:
        event_payload = payload.model_dump(mode="json") if hasattr(payload, "model_dump") else payload
        return self.event_store.append_event(
            BusEvent(
                type=event_type,
                actor=actor,
                run_id=run_id,
                task_id=task_id,
                agent_id=agent_id,
                payload=event_payload,
            )
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

    def _update_active_session(
        self,
        agent_id: str | None,
        runtime_state: AgentRuntimeState,
        *,
        reason: str,
    ) -> None:
        if agent_id is None:
            return
        directory = self.agent_directory
        owns_directory = False
        if directory is None and self.db_path is not None:
            directory = AgentDirectory(db_path=self.db_path)
            owns_directory = True
        if directory is None:
            return
        try:
            session = directory.get_active_session(agent_id)
            if session is not None:
                directory.update_session_state(session.session_id, runtime_state, reason=reason)
        except AgentDirectoryError:
            return
        finally:
            if owns_directory:
                directory.close()


def _row_to_run(row: sqlite3.Row) -> RunRecord:
    return RunRecord(
        run_id=row["run_id"],
        title=row["title"],
        objective=row["objective"],
        status=row["status"],
        created_by=row["created_by"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def _row_to_task(row: sqlite3.Row) -> TaskRecord:
    return TaskRecord(
        task_id=row["task_id"],
        run_id=row["run_id"],
        title=row["title"],
        owner_agent_id=row["owner_agent_id"],
        assignee_agent_id=row["assignee_agent_id"],
        status=row["status"],
        priority=row["priority"],
        parent_task_id=row["parent_task_id"],
        supersedes_task_id=row["supersedes_task_id"],
        blocked_reason=row["blocked_reason"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        completed_at=row["completed_at"],
        failed_at=row["failed_at"],
    )


def _row_to_coordination(row: sqlite3.Row) -> CoordinationRecord:
    return CoordinationRecord(
        record_id=row["record_id"],
        kind=row["kind"],
        run_id=row["run_id"],
        task_id=row["task_id"],
        agent_id=row["agent_id"],
        payload=json.loads(row["payload_json"]),
        created_at=row["created_at"],
        expires_at=row["expires_at"],
    )

