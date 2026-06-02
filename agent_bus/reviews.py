from __future__ import annotations

import os
import sqlite3
from pathlib import Path
from typing import Any, Iterable

from .authority import actor_role_for_principal, controller_principal
from .db import connect, initialize_database
from .inbox import InboxStore
from .models import (
    BusEvent,
    EventType,
    ReviewFinding,
    ReviewFindingStatus,
    new_id,
    utc_now_iso,
)
from .protocol_models import FencingResult, Principal
from .store import EventStore
from .tasks import RuntimeRecordError, StateTransitionError, migrate_runtime_schema


class ReviewBoard:
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
        self.event_store = event_store or EventStore(self.db_path)
        self.inbox_store = inbox_store
        self.principal = principal or controller_principal("review-board")

    def close(self) -> None:
        if self._owns_connection:
            self.conn.close()

    def create_finding(
        self,
        *,
        severity: str,
        category: str,
        evidence: str,
        requested_change: str,
        file_path: str | None = None,
        blocking: bool = False,
        run_id: str | None = None,
        task_id: str | None = None,
        finding_id: str | None = None,
        actor: str | None = None,
    ) -> ReviewFinding:
        if not evidence.strip():
            raise ValueError("review finding evidence is required")
        if not requested_change.strip():
            raise ValueError("review finding requested_change is required")
        now = utc_now_iso()
        finding = ReviewFinding(
            finding_id=finding_id or new_id("finding"),
            severity=severity,
            category=category,
            file_path=file_path,
            evidence=evidence,
            requested_change=requested_change,
            blocking=blocking,
            status=ReviewFindingStatus.OPEN,
            run_id=run_id,
            task_id=task_id,
            created_at=now,
            updated_at=now,
        )
        self._insert_or_update_finding(finding)
        self._append_event(EventType.REVIEW_FINDING_CREATED, actor=actor, finding=finding)
        return finding

    def get_finding(self, finding_id: str) -> ReviewFinding:
        row = self.conn.execute(
            "select * from review_findings where finding_id = ?",
            (finding_id,),
        ).fetchone()
        if row is None:
            raise RuntimeRecordError(f"unknown review finding: {finding_id}")
        return _row_to_finding(row)

    def list_findings(
        self,
        *,
        task_id: str | None = None,
        status: ReviewFindingStatus | str | None = None,
    ) -> list[ReviewFinding]:
        clauses: list[str] = []
        params: list[object] = []
        if task_id is not None:
            clauses.append("task_id = ?")
            params.append(task_id)
        if status is not None:
            clauses.append("status = ?")
            params.append(ReviewFindingStatus(status).value)
        sql = "select * from review_findings"
        if clauses:
            sql += " where " + " and ".join(clauses)
        sql += " order by created_at asc, finding_id asc"
        rows = self.conn.execute(sql, params).fetchall()
        return [_row_to_finding(row) for row in rows]

    def request_changes(
        self,
        *,
        task_id: str,
        worker_agent_id: str,
        findings: Iterable[dict[str, Any]],
        run_id: str | None = None,
        reviewer_agent_id: str | None = None,
    ) -> list[ReviewFinding]:
        if reviewer_agent_id is not None and reviewer_agent_id == worker_agent_id:
            from .protocol import ProtocolKernel

            result = ProtocolKernel(self.db_path, conn=self.conn).reject_action(
                action=EventType.REVIEW_CHANGES_REQUESTED.value,
                actor=reviewer_agent_id,
                actor_role=actor_role_for_principal(self.principal),
                reason="reviewer cannot request changes on their own work",
                fencing_result=FencingResult.NOT_REQUIRED,
                payload={"task_id": task_id, "worker_agent_id": worker_agent_id},
                run_id=run_id,
                task_id=task_id,
                agent_id=worker_agent_id,
            )
            raise PermissionError(result.reason or "reviewer cannot request changes on their own work")
        created = [
            self.create_finding(
                run_id=run_id,
                task_id=task_id,
                actor=reviewer_agent_id,
                **finding,
            )
            for finding in findings
        ]
        payload = {
            "task_id": task_id,
            "run_id": run_id,
            "finding_ids": [finding.finding_id for finding in created],
            "blocking": any(finding.blocking for finding in created),
        }
        self._enqueue(
            worker_agent_id,
            "changes_requested",
            payload,
            priority=80 if payload["blocking"] else 55,
            dedupe_key=f"changes_requested:{task_id}:{','.join(payload['finding_ids'])}",
        )
        self.event_store.append_event(
            BusEvent(
                type=EventType.REVIEW_CHANGES_REQUESTED,
                actor=reviewer_agent_id,
                run_id=run_id,
                task_id=task_id,
                agent_id=worker_agent_id,
                payload=payload,
            )
        )
        return created

    def resolve_finding(
        self,
        finding_id: str,
        *,
        resolved_by: str,
        status: ReviewFindingStatus | str = ReviewFindingStatus.RESOLVED,
    ) -> ReviewFinding:
        finding = self.get_finding(finding_id)
        if finding.status is not ReviewFindingStatus.OPEN:
            raise StateTransitionError(f"finding already closed: {finding.status.value}")
        resolved_status = ReviewFindingStatus(status)
        if resolved_status is ReviewFindingStatus.OPEN:
            raise StateTransitionError("resolved finding cannot remain open")
        now = utc_now_iso()
        finding.status = resolved_status
        finding.resolved_by = resolved_by
        finding.resolved_at = now
        finding.updated_at = now
        self._insert_or_update_finding(finding)
        self._append_event(EventType.REVIEW_FINDING_RESOLVED, actor=resolved_by, finding=finding)
        return finding

    def _insert_or_update_finding(self, finding: ReviewFinding) -> None:
        self.conn.execute(
            """
            insert into review_findings (
                finding_id, run_id, task_id, severity, category, file_path,
                evidence, requested_change, blocking, resolved_by, status,
                created_at, updated_at, resolved_at
            ) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            on conflict(finding_id) do update set
                severity = excluded.severity,
                category = excluded.category,
                file_path = excluded.file_path,
                evidence = excluded.evidence,
                requested_change = excluded.requested_change,
                blocking = excluded.blocking,
                resolved_by = excluded.resolved_by,
                status = excluded.status,
                updated_at = excluded.updated_at,
                resolved_at = excluded.resolved_at
            """,
            (
                finding.finding_id,
                finding.run_id,
                finding.task_id,
                finding.severity,
                finding.category,
                finding.file_path,
                finding.evidence,
                finding.requested_change,
                int(finding.blocking),
                finding.resolved_by,
                finding.status.value,
                finding.created_at,
                finding.updated_at,
                finding.resolved_at,
            ),
        )
        self.conn.commit()

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
                actor="review-board",
                principal=self.principal,
            )
        finally:
            if owns_inbox:
                inbox.close()

    def _append_event(self, event_type: EventType, *, actor: str | None, finding: ReviewFinding) -> BusEvent:
        return self.event_store.append_event(
            BusEvent(
                type=event_type,
                actor=actor,
                run_id=finding.run_id,
                task_id=finding.task_id,
                payload=finding.model_dump(mode="json"),
            )
        )


def _row_to_finding(row: sqlite3.Row) -> ReviewFinding:
    return ReviewFinding(
        finding_id=row["finding_id"],
        run_id=row["run_id"],
        task_id=row["task_id"],
        severity=row["severity"],
        category=row["category"],
        file_path=row["file_path"],
        evidence=row["evidence"],
        requested_change=row["requested_change"],
        blocking=bool(row["blocking"]),
        resolved_by=row["resolved_by"],
        status=row["status"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        resolved_at=row["resolved_at"],
    )
