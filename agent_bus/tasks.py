from __future__ import annotations

import json
import os
import sqlite3
from pathlib import Path
from typing import Any

from .agents import AgentDirectory, AgentDirectoryError
from .authority import actor_role_for_principal
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
from .protocol_models import (
    ClaimStatus,
    FencingResult,
    Principal,
    PrincipalType,
    ProjectionEffect,
    TaskClaimKind,
    TaskClaimRecord,
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
            agent_id text,
            session_id text,
            context_packet_id text,
            claim_id text,
            produced_by_event_id text,
            content_hash text,
            created_at text not null
        );

        create index if not exists idx_artifacts_task on artifacts(task_id);
        """
    )
    for definition in (
        "agent_id text",
        "session_id text",
        "context_packet_id text",
        "claim_id text",
        "produced_by_event_id text",
        "content_hash text",
    ):
        _add_column_if_missing(conn, "artifacts", definition)
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
        trusted_compatibility: bool = False,
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
        self.event_store = event_store or EventStore(self.db_path)
        self.inbox_store = inbox_store
        self.agent_directory = agent_directory
        self.trusted_compatibility = trusted_compatibility
        self.principal = principal

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
        principal: Principal | None = None,
        session_id: str | None = None,
        session_epoch: int | None = None,
        fencing_token: str | None = None,
    ) -> RunRecord:
        principal = principal or self.principal
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
        event = BusEvent(
            type=EventType.RUN_CREATED,
            actor=created_by,
            actor_role=actor_role_for_principal(principal),
            run_id=run.run_id,
            projection_effect=ProjectionEffect.COMMIT,
            fencing_result=FencingResult.NOT_REQUIRED,
            payload=run.model_dump(mode="json"),
        )
        from .protocol import ProtocolKernel

        result = ProtocolKernel(self.db_path, conn=self.conn).commit_event(
            event,
            principal=principal,
            session_id=session_id,
            session_epoch=session_epoch,
            fencing_token=fencing_token,
            guard_targets=(("runs", run.run_id, EventType.RUN_CREATED.value),),
            target_table="runs",
            target_id=run.run_id,
            reason="run created through ProtocolKernel command",
            mutation=lambda conn, _event: conn.execute(
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
            ),
        )
        if not result.accepted:
            raise PermissionError(result.reason or "protocol rejected run creation")
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
        principal: Principal | None = None,
        session_id: str | None = None,
        session_epoch: int | None = None,
        fencing_token: str | None = None,
    ) -> TaskRecord:
        principal = principal or self.principal
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
        event = BusEvent(
            type=EventType.TASK_CREATED,
            actor=owner_agent_id,
            actor_role=actor_role_for_principal(principal),
            run_id=run_id,
            task_id=task.task_id,
            projection_effect=ProjectionEffect.COMMIT,
            fencing_result=FencingResult.NOT_REQUIRED,
            payload=task.model_dump(mode="json"),
        )
        from .protocol import ProtocolKernel

        result = ProtocolKernel(self.db_path, conn=self.conn).commit_event(
            event,
            principal=principal,
            session_id=session_id,
            session_epoch=session_epoch,
            fencing_token=fencing_token,
            guard_targets=(("tasks", task.task_id, EventType.TASK_CREATED.value),),
            target_table="tasks",
            target_id=task.task_id,
            reason="task created through ProtocolKernel command",
            mutation=lambda _conn, _event: self._insert_or_update_task(task, commit=False),
        )
        if not result.accepted:
            raise PermissionError(result.reason or "protocol rejected task creation")
        if assignee_agent_id:
            task = self.assign_task(
                task.task_id,
                assignee_agent_id,
                actor=owner_agent_id,
                principal=principal,
                session_id=session_id,
                session_epoch=session_epoch,
                fencing_token=fencing_token,
            )
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

    def assign_task(
        self,
        task_id: str,
        assignee_agent_id: str,
        *,
        actor: str | None = None,
        principal: Principal | None = None,
        session_id: str | None = None,
        session_epoch: int | None = None,
        fencing_token: str | None = None,
    ) -> TaskRecord:
        principal = principal or self.principal
        from .protocol import ProtocolKernel

        assignment_session_id, assignment_session_epoch = self._active_session_for_agent(assignee_agent_id)
        result = ProtocolKernel(self.db_path, conn=self.conn).assign_task(
            task_id=task_id,
            assignee_agent_id=assignee_agent_id,
            actor=actor,
            principal=principal,
            session_id=session_id,
            session_epoch=session_epoch,
            fencing_token=fencing_token,
            assignment_session_id=assignment_session_id,
            assignment_session_epoch=assignment_session_epoch,
        )
        if not result.accepted:
            raise PermissionError(result.reason or "protocol rejected task assignment")
        return self.get_task(task_id)

    def acknowledge_task(
        self,
        task_id: str,
        *,
        actor: str | None = None,
        principal: Principal | None = None,
        session_id: str | None = None,
        session_epoch: int | None = None,
        fencing_token: str | None = None,
    ) -> TaskRecord:
        return self._runtime_transition_or_claim(
            task_id,
            TaskState.ACKNOWLEDGED,
            actor=actor,
            principal=principal,
            session_id=session_id,
            session_epoch=session_epoch,
            fencing_token=fencing_token,
            commit_event_type=EventType.TASK_ACKNOWLEDGED,
            claim_event_type=EventType.TASK_ACK_CLAIMED,
        )

    def start_task(
        self,
        task_id: str,
        *,
        actor: str | None = None,
        principal: Principal | None = None,
        session_id: str | None = None,
        session_epoch: int | None = None,
        fencing_token: str | None = None,
    ) -> TaskRecord:
        task = self._runtime_transition_or_claim(
            task_id,
            TaskState.WORKING,
            actor=actor,
            principal=principal,
            session_id=session_id,
            session_epoch=session_epoch,
            fencing_token=fencing_token,
            commit_event_type=EventType.TASK_PROGRESS,
            claim_event_type=EventType.TASK_PROGRESS_REPORTED,
        )
        if task.status is TaskState.WORKING:
            self._update_active_session(task.assignee_agent_id, AgentRuntimeState.WORKING, reason=f"task {task.task_id} working")
        return task

    def block_task(
        self,
        task_id: str,
        reason: str,
        *,
        actor: str | None = None,
        principal: Principal | None = None,
        session_id: str | None = None,
        session_epoch: int | None = None,
        fencing_token: str | None = None,
    ) -> TaskRecord:
        principal = principal or self.principal
        if principal is not None and principal.principal_type is PrincipalType.AGENT:
            task = self.get_task(task_id)
            return self._record_runtime_claim(
                task,
                actor=actor,
                principal=principal,
                session_id=session_id,
                session_epoch=session_epoch,
                fencing_token=fencing_token,
                event_type=EventType.TASK_BLOCKER_REPORTED,
                payload={"reason": reason, "requested_state": TaskState.BLOCKED.value},
            )
        task = self.get_task(task_id)
        self._assert_transition(task.status, TaskState.BLOCKED)
        task.status = TaskState.BLOCKED
        task.blocked_reason = reason
        task.updated_at = utc_now_iso()
        self._commit_runtime_transition(
            task,
            actor=actor,
            principal=principal,
            session_id=session_id,
            session_epoch=session_epoch,
            fencing_token=fencing_token,
            event_type=EventType.TASK_BLOCKED,
        )
        return task

    def complete_task(self, task_id: str, *, actor: str | None = None) -> TaskRecord:
        from .protocol import ProtocolKernel

        result = ProtocolKernel(self.db_path, conn=self.conn).record_direct_mutation_attempt(
            "agent_bus.tasks.TaskBoard.complete_task",
            actor=actor,
            actor_role=None,
            payload={"task_id": task_id},
        )
        raise PermissionError(result.reason or "direct task completion is forbidden")

    def fail_task(self, task_id: str, reason: str, *, actor: str | None = None) -> TaskRecord:
        from .protocol import ProtocolKernel

        result = ProtocolKernel(self.db_path, conn=self.conn).record_direct_mutation_attempt(
            "agent_bus.tasks.TaskBoard.fail_task",
            actor=actor,
            actor_role=None,
            payload={"task_id": task_id, "reason": reason},
        )
        raise PermissionError(result.reason or "direct task failure is forbidden")

    def supersede_task(
        self,
        task_id: str,
        superseded_by_task_id: str,
        *,
        actor: str | None = None,
        principal: Principal | None = None,
        session_id: str | None = None,
        session_epoch: int | None = None,
        fencing_token: str | None = None,
    ) -> TaskRecord:
        principal = principal or self.principal
        task = self.get_task(task_id)
        self._assert_transition(task.status, TaskState.SUPERSEDED)
        task.status = TaskState.SUPERSEDED
        task.supersedes_task_id = superseded_by_task_id
        task.updated_at = utc_now_iso()
        event = BusEvent(
            type=EventType.TASK_SUPERSEDED,
            actor=actor,
            run_id=task.run_id,
            task_id=task.task_id,
            agent_id=task.assignee_agent_id,
            actor_role=actor_role_for_principal(principal),
            projection_effect=ProjectionEffect.COMMIT,
            fencing_result=FencingResult.NOT_REQUIRED,
            payload=task.model_dump(mode="json"),
        )
        from .protocol import ProtocolKernel

        result = ProtocolKernel(self.db_path, conn=self.conn).commit_event(
            event,
            principal=principal,
            session_id=session_id,
            session_epoch=session_epoch,
            fencing_token=fencing_token,
            guard_targets=(("tasks", task.task_id, EventType.TASK_SUPERSEDED.value),),
            target_table="tasks",
            target_id=task.task_id,
            reason="task superseded through ProtocolKernel command",
            mutation=lambda _conn, _event: self._insert_or_update_task(task, commit=False),
        )
        if not result.accepted:
            raise PermissionError(result.reason or "protocol rejected task supersession")
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
        principal: Principal | None = None,
        actor: str | None = None,
        session_id: str | None = None,
        session_epoch: int | None = None,
        fencing_token: str | None = None,
    ) -> CoordinationRecord:
        principal = principal or self.principal
        record = CoordinationRecord(
            record_id=record_id or new_id("coord"),
            kind=kind,
            run_id=run_id,
            task_id=task_id,
            agent_id=agent_id,
            payload=payload or {},
            expires_at=expires_at,
        )
        event = BusEvent(
            type=EventType.COORDINATION_RECORDED,
            actor=actor or agent_id,
            actor_role=actor_role_for_principal(principal),
            run_id=run_id,
            task_id=task_id,
            agent_id=agent_id,
            projection_effect=ProjectionEffect.COMMIT,
            fencing_result=FencingResult.NOT_REQUIRED,
            payload=record.model_dump(mode="json"),
        )
        from .protocol import ProtocolKernel

        result = ProtocolKernel(self.db_path, conn=self.conn).commit_event(
            event,
            principal=principal,
            session_id=session_id,
            session_epoch=session_epoch,
            fencing_token=fencing_token,
            guard_targets=(("coordination_records", record.record_id, EventType.COORDINATION_RECORDED.value),),
            target_table="coordination_records",
            target_id=record.record_id,
            reason="coordination record committed through ProtocolKernel command",
            mutation=lambda conn, _event: conn.execute(
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
            ),
        )
        if not result.accepted:
            raise PermissionError(result.reason or "protocol rejected coordination record")
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
        principal: Principal | None = None,
        session_id: str | None = None,
        session_epoch: int | None = None,
        fencing_token: str | None = None,
    ) -> ArtifactRecord:
        principal = principal or self.principal
        artifact = ArtifactRecord(
            artifact_id=artifact_id or new_id("artifact"),
            run_id=run_id,
            task_id=task_id,
            kind=kind,
            uri=uri,
            metadata=metadata or {},
            created_by=created_by,
        )
        event = BusEvent(
            type=EventType.ARTIFACT_CREATED,
            actor=created_by,
            run_id=run_id,
            task_id=task_id,
            agent_id=created_by,
            actor_role=actor_role_for_principal(principal),
            artifact_id=artifact.artifact_id,
            projection_effect=ProjectionEffect.COMMIT,
            fencing_result=FencingResult.NOT_REQUIRED,
            payload=artifact.model_dump(mode="json"),
        )
        from .protocol import ProtocolKernel

        result = ProtocolKernel(self.db_path, conn=self.conn).commit_event(
            event,
            principal=principal,
            session_id=session_id,
            session_epoch=session_epoch,
            fencing_token=fencing_token,
            guard_targets=(("artifacts", artifact.artifact_id, EventType.ARTIFACT_CREATED.value),),
            target_table="artifacts",
            target_id=artifact.artifact_id,
            reason="artifact created through ProtocolKernel command",
            mutation=lambda conn, _event: conn.execute(
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
            ),
        )
        if not result.accepted:
            raise PermissionError(result.reason or "protocol rejected artifact creation")
        return artifact

    def produce_artifact_claim(
        self,
        kind: str,
        uri: str,
        *,
        task_id: str,
        run_id: str | None = None,
        metadata: dict[str, Any] | None = None,
        artifact_id: str | None = None,
        actor: str | None = None,
        principal: Principal | None = None,
        session_id: str | None = None,
        session_epoch: int | None = None,
        fencing_token: str | None = None,
        content_hash: str | None = None,
    ):
        principal = principal or self.principal
        task = self.get_task(task_id)
        claim_agent_id = principal.agent_id if principal is not None and principal.agent_id else actor
        context_packet_id = self._resolve_claim_context_packet_id(
            task,
            agent_id=claim_agent_id,
            session_id=session_id,
        )
        if context_packet_id is None:
            from .protocol import ProtocolKernel

            result = ProtocolKernel(self.db_path, conn=self.conn).reject_action(
                action=EventType.ARTIFACT_PRODUCED.value,
                actor=actor,
                actor_role=actor_role_for_principal(principal),
                reason="artifact production requires an active assignment context binding",
                payload={"task_id": task_id, "kind": kind, "uri": uri},
                run_id=run_id or task.run_id,
                task_id=task_id,
                agent_id=claim_agent_id,
                session_id=session_id,
            )
            raise PermissionError(result.reason or "protocol rejected artifact claim")

        artifact = ArtifactRecord(
            artifact_id=artifact_id or new_id("artifact"),
            run_id=run_id or task.run_id,
            task_id=task_id,
            kind=kind,
            uri=uri,
            metadata=metadata or {},
            created_by=claim_agent_id,
            agent_id=claim_agent_id,
            session_id=session_id,
            context_packet_id=context_packet_id,
            content_hash=content_hash,
        )
        event = BusEvent(
            type=EventType.ARTIFACT_PRODUCED,
            actor=actor,
            actor_role=actor_role_for_principal(principal),
            run_id=artifact.run_id,
            task_id=task_id,
            agent_id=claim_agent_id,
            session_id=session_id,
            session_epoch=session_epoch,
            context_packet_id=context_packet_id,
            artifact_id=artifact.artifact_id,
            projection_effect=ProjectionEffect.COMMIT,
            fencing_result=FencingResult.NOT_REQUIRED,
            payload={"artifact": artifact.model_dump(mode="json")},
        )
        claim = TaskClaimRecord(
            claim_kind=TaskClaimKind.ARTIFACT,
            task_id=task_id,
            run_id=artifact.run_id,
            agent_id=claim_agent_id,
            session_id=session_id,
            session_epoch=session_epoch,
            context_packet_id=context_packet_id,
            status=ClaimStatus.PENDING,
            payload={"artifact": artifact.model_dump(mode="json")},
            created_from_event_id=event.event_id,
        )
        from .protocol import ProtocolKernel

        result = ProtocolKernel(self.db_path, conn=self.conn).commit_event(
            event,
            principal=principal,
            session_id=session_id,
            session_epoch=session_epoch,
            fencing_token=fencing_token,
            required_fencing=True,
            guard_targets=(("task_claims", claim.claim_id, EventType.ARTIFACT_PRODUCED.value),),
            target_table="task_claims",
            target_id=claim.claim_id,
            task_claim=claim,
            reason="worker artifact evidence claim recorded through ProtocolKernel",
        )
        if not result.accepted:
            raise PermissionError(result.reason or "protocol rejected artifact claim")
        return result

    def commit_task_claim(
        self,
        claim_id: str,
        *,
        actor: str | None = None,
        principal: Principal | None = None,
        session_id: str | None = None,
        session_epoch: int | None = None,
        fencing_token: str | None = None,
    ) -> TaskRecord:
        principal = principal or self.principal
        claim = self._get_claim(claim_id)
        claim_kind = TaskClaimKind(claim["claim_kind"])
        if claim_kind is TaskClaimKind.ARTIFACT:
            raise ValueError("artifact claims must be accepted with commit_artifact_claim")
        task = self.get_task(claim["task_id"])
        next_state, event_type, timestamp_field = _claim_commit_transition(claim_kind)
        self._assert_transition(task.status, next_state)
        now = utc_now_iso()
        task.status = next_state
        task.updated_at = now
        if timestamp_field is not None:
            setattr(task, timestamp_field, now)
        if next_state is not TaskState.BLOCKED:
            task.blocked_reason = None
        if next_state is TaskState.BLOCKED:
            task.blocked_reason = _claim_payload(claim).get("reason")
        event = BusEvent(
            type=event_type,
            actor=actor,
            actor_role=actor_role_for_principal(principal),
            run_id=task.run_id,
            task_id=task.task_id,
            agent_id=task.assignee_agent_id,
            context_packet_id=claim["context_packet_id"],
            causation_id=claim["created_from_event_id"],
            projection_effect=ProjectionEffect.COMMIT,
            fencing_result=FencingResult.NOT_REQUIRED,
            payload={"claim_id": claim_id, "task": task.model_dump(mode="json")},
        )
        from .protocol import ProtocolKernel

        def mutate(_conn: sqlite3.Connection, appended: BusEvent) -> None:
            self._insert_or_update_task(task, commit=False)
            _update_claim_row(
                _conn,
                claim,
                status=ClaimStatus.COMMITTED,
                committed_by_event_id=appended.event_id,
            )

        result = ProtocolKernel(self.db_path, conn=self.conn).commit_event(
            event,
            action=event_type.value,
            principal=principal,
            session_id=session_id,
            session_epoch=session_epoch,
            fencing_token=fencing_token,
            guard_targets=(
                ("tasks", task.task_id, event_type.value),
                ("task_claims", claim_id, event_type.value),
            ),
            target_table="tasks",
            target_id=task.task_id,
            mutation=mutate,
            reason="controller committed worker task claim",
        )
        if not result.accepted:
            raise PermissionError(result.reason or "protocol rejected claim commit")
        return task

    def reject_task_claim(
        self,
        claim_id: str,
        *,
        reason: str,
        actor: str | None = None,
        principal: Principal | None = None,
        session_id: str | None = None,
        session_epoch: int | None = None,
        fencing_token: str | None = None,
    ) -> None:
        principal = principal or self.principal
        claim = self._get_claim(claim_id)
        payload = _claim_payload(claim)
        payload["rejection_reason"] = reason
        event = BusEvent(
            type="task.claim_rejected",
            actor=actor,
            actor_role=actor_role_for_principal(principal),
            run_id=claim["run_id"],
            task_id=claim["task_id"],
            agent_id=claim["agent_id"],
            session_id=claim["session_id"],
            session_epoch=claim["session_epoch"],
            context_packet_id=claim["context_packet_id"],
            causation_id=claim["created_from_event_id"],
            projection_effect=ProjectionEffect.COMMIT,
            fencing_result=FencingResult.NOT_REQUIRED,
            payload={"claim_id": claim_id, "reason": reason},
        )
        from .protocol import ProtocolKernel

        def mutate(conn: sqlite3.Connection, appended: BusEvent) -> None:
            _update_claim_row(
                conn,
                claim,
                status=ClaimStatus.REJECTED,
                payload=payload,
                committed_by_event_id=appended.event_id,
            )

        result = ProtocolKernel(self.db_path, conn=self.conn).commit_event(
            event,
            action="task.claim_rejected",
            principal=principal,
            session_id=session_id,
            session_epoch=session_epoch,
            fencing_token=fencing_token,
            guard_targets=(("task_claims", claim_id, "task.claim_rejected"),),
            target_table="task_claims",
            target_id=claim_id,
            mutation=mutate,
            reason="controller rejected worker task claim",
        )
        if not result.accepted:
            raise PermissionError(result.reason or "protocol rejected claim rejection")

    def commit_artifact_claim(
        self,
        claim_id: str | None,
        *,
        actor: str | None = None,
        principal: Principal | None = None,
        session_id: str | None = None,
        session_epoch: int | None = None,
        fencing_token: str | None = None,
    ) -> ArtifactRecord:
        if claim_id is None:
            raise ValueError("claim_id is required")
        principal = principal or self.principal
        claim = self._get_claim(claim_id)
        if TaskClaimKind(claim["claim_kind"]) is not TaskClaimKind.ARTIFACT:
            raise ValueError("claim is not an artifact claim")
        payload = _claim_payload(claim)
        artifact_payload = payload["artifact"]
        artifact = ArtifactRecord(**{**artifact_payload, "claim_id": claim_id})
        event = BusEvent(
            type=EventType.ARTIFACT_CREATED,
            actor=actor,
            actor_role=actor_role_for_principal(principal),
            run_id=artifact.run_id,
            task_id=artifact.task_id,
            agent_id=artifact.agent_id,
            session_id=artifact.session_id,
            context_packet_id=artifact.context_packet_id,
            artifact_id=artifact.artifact_id,
            causation_id=claim["created_from_event_id"],
            projection_effect=ProjectionEffect.COMMIT,
            fencing_result=FencingResult.NOT_REQUIRED,
            payload=artifact.model_dump(mode="json"),
        )
        from .protocol import ProtocolKernel

        def mutate(conn: sqlite3.Connection, appended: BusEvent) -> None:
            conn.execute(
                """
                insert into artifacts (
                    artifact_id, run_id, task_id, kind, uri, metadata_json, created_by,
                    agent_id, session_id, context_packet_id, claim_id, produced_by_event_id,
                    content_hash, created_at
                ) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    artifact.artifact_id,
                    artifact.run_id,
                    artifact.task_id,
                    artifact.kind,
                    artifact.uri,
                    json.dumps(artifact.metadata, sort_keys=True),
                    artifact.created_by,
                    artifact.agent_id,
                    artifact.session_id,
                    artifact.context_packet_id,
                    claim_id,
                    claim["created_from_event_id"],
                    artifact.content_hash,
                    artifact.created_at,
                ),
            )
            _update_claim_row(
                conn,
                claim,
                status=ClaimStatus.COMMITTED,
                committed_by_event_id=appended.event_id,
            )

        result = ProtocolKernel(self.db_path, conn=self.conn).commit_event(
            event,
            principal=principal,
            session_id=session_id,
            session_epoch=session_epoch,
            fencing_token=fencing_token,
            guard_targets=(
                ("artifacts", artifact.artifact_id, EventType.ARTIFACT_CREATED.value),
                ("task_claims", claim_id, EventType.ARTIFACT_CREATED.value),
            ),
            target_table="artifacts",
            target_id=artifact.artifact_id,
            mutation=mutate,
            reason="controller accepted worker artifact evidence claim",
        )
        if not result.accepted:
            raise PermissionError(result.reason or "protocol rejected artifact claim acceptance")
        return artifact

    def _transition_task(
        self,
        task_id: str,
        next_state: TaskState,
        *,
        actor: str | None,
        principal: Principal | None = None,
        session_id: str | None = None,
        session_epoch: int | None = None,
        fencing_token: str | None = None,
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
        if next_state in {TaskState.ACKNOWLEDGED, TaskState.WORKING, TaskState.BLOCKED}:
            self._commit_runtime_transition(
                task,
                actor=actor,
                principal=principal,
                session_id=session_id,
                session_epoch=session_epoch,
                fencing_token=fencing_token,
                event_type=event_type,
            )
            return task
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

    def _runtime_transition_or_claim(
        self,
        task_id: str,
        next_state: TaskState,
        *,
        actor: str | None,
        principal: Principal | None,
        session_id: str | None,
        session_epoch: int | None,
        fencing_token: str | None,
        commit_event_type: EventType,
        claim_event_type: EventType,
    ) -> TaskRecord:
        principal = principal or self.principal
        task = self.get_task(task_id)
        if principal is not None and principal.principal_type is PrincipalType.AGENT:
            return self._record_runtime_claim(
                task,
                actor=actor,
                principal=principal,
                session_id=session_id,
                session_epoch=session_epoch,
                fencing_token=fencing_token,
                event_type=claim_event_type,
                payload={"requested_state": next_state.value},
            )
        return self._transition_task(
            task_id,
            next_state,
            actor=actor,
            principal=principal,
            session_id=session_id,
            session_epoch=session_epoch,
            fencing_token=fencing_token,
            event_type=commit_event_type,
        )

    def _record_runtime_claim(
        self,
        task: TaskRecord,
        *,
        actor: str | None,
        principal: Principal | None,
        session_id: str | None,
        session_epoch: int | None,
        fencing_token: str | None,
        event_type: EventType,
        payload: dict[str, Any],
    ) -> TaskRecord:
        claim_kind = _claim_kind_for_event(event_type)
        claim_agent_id = principal.agent_id if principal is not None and principal.agent_id else task.assignee_agent_id
        context_packet_id = self._resolve_claim_context_packet_id(
            task,
            agent_id=claim_agent_id,
            session_id=session_id,
        )
        if context_packet_id is None:
            from .protocol import ProtocolKernel

            result = ProtocolKernel(self.db_path, conn=self.conn).reject_action(
                action=event_type.value,
                actor=actor,
                actor_role=actor_role_for_principal(principal),
                reason="worker claim requires an active assignment context binding",
                fencing_result=FencingResult.NOT_REQUIRED,
                payload={**payload, "task_id": task.task_id},
                run_id=task.run_id,
                task_id=task.task_id,
                agent_id=claim_agent_id,
                session_id=session_id,
            )
            raise PermissionError(result.reason or "protocol rejected worker runtime claim")
        event = BusEvent(
            type=event_type,
            actor=actor,
            actor_role=actor_role_for_principal(principal),
            run_id=task.run_id,
            task_id=task.task_id,
            agent_id=claim_agent_id,
            session_id=session_id,
            session_epoch=session_epoch,
            context_packet_id=context_packet_id,
            projection_effect=ProjectionEffect.COMMIT,
            fencing_result=FencingResult.NOT_REQUIRED,
            payload={**task.model_dump(mode="json"), **payload},
        )
        from .protocol import ProtocolKernel

        claim = TaskClaimRecord(
            claim_kind=claim_kind,
            task_id=task.task_id,
            run_id=task.run_id,
            agent_id=claim_agent_id,
            session_id=session_id,
            session_epoch=session_epoch,
            context_packet_id=context_packet_id,
            status=ClaimStatus.PENDING,
            payload={**payload, "task": task.model_dump(mode="json")},
            created_from_event_id=event.event_id,
        )
        result = ProtocolKernel(self.db_path, conn=self.conn).commit_event(
            event,
            principal=principal,
            session_id=session_id,
            session_epoch=session_epoch,
            fencing_token=fencing_token,
            required_fencing=True,
            guard_targets=(("task_claims", claim.claim_id, event_type.value),),
            target_table="task_claims",
            target_id=claim.claim_id,
            task_claim=claim,
            reason="worker runtime claim recorded through ProtocolKernel",
        )
        if not result.accepted:
            raise PermissionError(result.reason or "protocol rejected worker runtime claim")
        return task

    def _resolve_claim_context_packet_id(
        self,
        task: TaskRecord,
        *,
        agent_id: str | None,
        session_id: str | None,
    ) -> str | None:
        if task.task_id is None or agent_id is None:
            return None
        row = self.conn.execute(
            """
            select context_packet_id from task_context_bindings
            where task_id = ?
              and agent_id = ?
              and status = 'active'
              and (? is null or session_id is null or session_id = ?)
            order by created_at desc
            limit 1
            """,
            (task.task_id, agent_id, session_id, session_id),
        ).fetchone()
        if row is None:
            return None
        return row["context_packet_id"]

    def _commit_runtime_transition(
        self,
        task: TaskRecord,
        *,
        actor: str | None,
        principal: Principal | None,
        session_id: str | None,
        session_epoch: int | None,
        fencing_token: str | None,
        event_type: EventType,
    ) -> None:
        event = BusEvent(
            type=event_type,
            actor=actor,
            actor_role=actor_role_for_principal(principal),
            run_id=task.run_id,
            task_id=task.task_id,
            agent_id=task.assignee_agent_id,
            projection_effect=ProjectionEffect.COMMIT,
            fencing_result=FencingResult.NOT_REQUIRED,
            payload=task.model_dump(mode="json"),
        )
        from .protocol import ProtocolKernel

        result = ProtocolKernel(self.db_path, conn=self.conn).commit_event(
            event,
            principal=principal,
            session_id=session_id,
            session_epoch=session_epoch,
            fencing_token=fencing_token,
            guard_targets=(("tasks", task.task_id, event_type.value),),
            target_table="tasks",
            target_id=task.task_id,
            reason="task runtime transition through ProtocolKernel command",
            mutation=lambda _conn, _event: self._insert_or_update_task(task, commit=False),
        )
        if not result.accepted:
            raise PermissionError(result.reason or "protocol rejected task runtime transition")

    def _assert_transition(self, current: TaskState | str, next_state: TaskState) -> None:
        current_state = TaskState(current)
        if next_state not in TASK_TRANSITIONS[current_state]:
            raise StateTransitionError(f"invalid task transition: {current_state.value} -> {next_state.value}")

    def _insert_or_update_task(self, task: TaskRecord, *, commit: bool = True) -> None:
        try:
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
        except sqlite3.IntegrityError:
            if commit:
                self.conn.rollback()
            raise
        if commit:
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
        context_packet_id: str | None = None,
        dedupe_key: str,
        actor: str | None = None,
        principal: Principal | None = None,
        session_id: str | None = None,
        session_epoch: int | None = None,
        fencing_token: str | None = None,
    ) -> None:
        inbox = self.inbox_store or InboxStore(db_path=self.db_path, principal=principal or self.principal)
        owns_inbox = self.inbox_store is None
        try:
            inbox.enqueue(
                agent_id,
                kind,
                payload,
                priority=priority,
                context_packet_id=context_packet_id,
                dedupe_key=dedupe_key,
                actor=actor,
                principal=principal or self.principal,
                session_id=session_id,
                session_epoch=session_epoch,
                fencing_token=fencing_token,
            )
        finally:
            if owns_inbox:
                inbox.close()

    def _create_assignment_context(
        self,
        task: TaskRecord,
        *,
        actor: str | None,
        principal: Principal | None,
    ) -> str | None:
        if task.assignee_agent_id is None:
            return None
        from .context import ContextStore

        session_id, session_epoch = self._active_session_for_agent(task.assignee_agent_id)
        context = ContextStore(db_path=self.db_path, principal=principal or self.principal)
        try:
            packet = context.create_packet(
                agent_id=task.assignee_agent_id,
                task_id=task.task_id,
                run_id=task.run_id,
                summary=f"Assignment for {task.title}",
                instructions={
                    "kind": "assignment",
                    "task_id": task.task_id,
                    "run_id": task.run_id,
                    "title": task.title,
                    "next_action": "acknowledge_task",
                },
                actor=actor,
                principal=principal or self.principal,
                session_id=session_id,
                session_epoch=session_epoch,
            )
            return packet.packet_id
        finally:
            context.close()

    def _active_session_for_agent(self, agent_id: str) -> tuple[str | None, int | None]:
        directory = self.agent_directory
        owns_directory = False
        if directory is None and self.db_path is not None:
            directory = AgentDirectory(db_path=self.db_path)
            owns_directory = True
        if directory is None:
            return None, None
        try:
            session = directory.get_active_session(agent_id)
        except AgentDirectoryError:
            return None, None
        finally:
            if owns_directory:
                directory.close()
        if session is None:
            return None, None
        return session.session_id, session.session_epoch

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

    def _get_claim(self, claim_id: str) -> sqlite3.Row:
        row = self.conn.execute("select * from task_claims where claim_id = ?", (claim_id,)).fetchone()
        if row is None:
            raise RuntimeRecordError(f"unknown task claim: {claim_id}")
        if row["status"] != ClaimStatus.PENDING.value:
            raise StateTransitionError(f"claim is not pending: {claim_id}")
        return row


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


def _claim_kind_for_event(event_type: EventType) -> TaskClaimKind:
    mapping = {
        EventType.TASK_ACK_CLAIMED: TaskClaimKind.ACK,
        EventType.TASK_PROGRESS_REPORTED: TaskClaimKind.PROGRESS,
        EventType.TASK_BLOCKER_REPORTED: TaskClaimKind.BLOCKER,
        EventType.TASK_COMPLETION_CLAIMED: TaskClaimKind.COMPLETION,
        EventType.TASK_FAILURE_CLAIMED: TaskClaimKind.FAILURE,
        EventType.ARTIFACT_PRODUCED: TaskClaimKind.ARTIFACT,
        EventType.HANDOFF_PROPOSED: TaskClaimKind.HANDOFF,
    }
    try:
        return mapping[event_type]
    except KeyError as exc:
        raise ValueError(f"unsupported task claim event: {event_type}") from exc


def _claim_commit_transition(claim_kind: TaskClaimKind) -> tuple[TaskState, EventType, str | None]:
    mapping = {
        TaskClaimKind.ACK: (TaskState.ACKNOWLEDGED, EventType.TASK_ACKNOWLEDGED, None),
        TaskClaimKind.PROGRESS: (TaskState.WORKING, EventType.TASK_PROGRESS, None),
        TaskClaimKind.BLOCKER: (TaskState.BLOCKED, EventType.TASK_BLOCKED, None),
        TaskClaimKind.COMPLETION: (TaskState.COMPLETED, EventType.TASK_COMPLETED, "completed_at"),
        TaskClaimKind.FAILURE: (TaskState.FAILED, EventType.TASK_FAILED, "failed_at"),
    }
    try:
        return mapping[claim_kind]
    except KeyError as exc:
        raise ValueError(f"task claim cannot be committed as task state: {claim_kind}") from exc


def _claim_payload(row: sqlite3.Row) -> dict[str, Any]:
    return json.loads(row["payload_json"])


def _update_claim_row(
    conn: sqlite3.Connection,
    claim: sqlite3.Row,
    *,
    status: ClaimStatus,
    committed_by_event_id: str,
    payload: dict[str, Any] | None = None,
) -> None:
    conn.execute(
        """
        update task_claims
        set status = ?,
            payload_json = ?,
            committed_by_event_id = ?,
            updated_at = ?
        where claim_id = ?
        """,
        (
            status.value,
            json.dumps(payload if payload is not None else _claim_payload(claim), sort_keys=True),
            committed_by_event_id,
            utc_now_iso(),
            claim["claim_id"],
        ),
    )


def _add_column_if_missing(conn: sqlite3.Connection, table: str, column_definition: str) -> None:
    column = column_definition.split()[0]
    columns = {row[1] for row in conn.execute(f"pragma table_info({table})").fetchall()}
    if column not in columns:
        conn.execute(f"alter table {table} add column {column_definition}")
