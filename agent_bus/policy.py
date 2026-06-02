from __future__ import annotations

import os
import sqlite3
from pathlib import Path
from typing import Iterable

from .db import connect, initialize_database
from .protocol_models import BindingStatus, PolicyDecision


class PolicyService:
    """Context-sensitive protocol checks that sit after static authority."""

    def __init__(
        self,
        db_path: str | os.PathLike[str] | None = None,
        *,
        conn: sqlite3.Connection | None = None,
    ) -> None:
        self.db_path = Path(db_path) if db_path is not None else None
        self.conn = conn
        if self.conn is None:
            initialize_database(self.db_path)

    def evaluate(
        self,
        *,
        action: str,
        actor: str | None = None,
        agent_id: str | None = None,
        task_id: str | None = None,
        session_id: str | None = None,
        context_packet_id: str | None = None,
        required_artifact_ids: Iterable[str] = (),
        reviewer_agent_id: str | None = None,
        reviewed_agent_id: str | None = None,
    ) -> PolicyDecision:
        checks: list[str] = []
        if action not in {"context.created", "context.superseded"}:
            context = self.validate_context_active(context_packet_id, task_id=task_id, session_id=session_id)
            checks.extend(context.checks)
            if not context.allowed:
                return context

        review = self.validate_no_self_review(reviewer_agent_id, reviewed_agent_id)
        checks.extend(review.checks)
        if not review.allowed:
            return review

        artifacts = self.validate_required_artifacts(required_artifact_ids)
        checks.extend(artifacts.checks)
        if not artifacts.allowed:
            return artifacts

        return PolicyDecision(allowed=True, checks=checks or [f"policy accepted {action}"])

    def validate_context_active(
        self,
        context_packet_id: str | None,
        *,
        task_id: str | None = None,
        session_id: str | None = None,
    ) -> PolicyDecision:
        if context_packet_id is None:
            return PolicyDecision(allowed=True, checks=["no context packet required"])
        conn = self.conn or connect(self.db_path)
        try:
            if _has_table(conn, "task_context_bindings"):
                row = conn.execute(
                    """
                    select * from task_context_bindings
                    where context_packet_id = ?
                      and status = ?
                      and (? is null or task_id = ?)
                      and (? is null or session_id is null or session_id = ?)
                    order by created_at desc
                    limit 1
                    """,
                    (
                        context_packet_id,
                        BindingStatus.ACTIVE.value,
                        task_id,
                        task_id,
                        session_id,
                        session_id,
                    ),
                ).fetchone()
                if row is not None:
                    return PolicyDecision(allowed=True, checks=["active task context binding"])
            if _has_table(conn, "context_packets"):
                row = conn.execute(
                    "select status from context_packets where packet_id = ?",
                    (context_packet_id,),
                ).fetchone()
                if row is not None and row["status"] == "active":
                    return PolicyDecision(allowed=True, checks=["active context packet"])
        finally:
            if self.conn is None:
                conn.close()
        return PolicyDecision(
            allowed=False,
            reason=f"context packet is not active: {context_packet_id}",
            checks=["context active check failed"],
        )

    def validate_no_self_review(
        self,
        reviewer_agent_id: str | None,
        reviewed_agent_id: str | None,
    ) -> PolicyDecision:
        if reviewer_agent_id is None or reviewed_agent_id is None:
            return PolicyDecision(allowed=True, checks=["self-review check not applicable"])
        if reviewer_agent_id == reviewed_agent_id:
            return PolicyDecision(
                allowed=False,
                reason="reviewer cannot approve their own work",
                checks=["self-review rejected"],
            )
        return PolicyDecision(allowed=True, checks=["self-review check passed"])

    def validate_required_artifacts(self, artifact_ids: Iterable[str]) -> PolicyDecision:
        required = [artifact_id for artifact_id in artifact_ids if artifact_id]
        if not required:
            return PolicyDecision(allowed=True, checks=["no required artifacts"])
        conn = self.conn or connect(self.db_path)
        try:
            if not _has_table(conn, "artifacts"):
                return PolicyDecision(
                    allowed=False,
                    reason="artifact table does not exist",
                    checks=["required artifacts missing"],
                )
            found = {
                row["artifact_id"]
                for row in conn.execute(
                    f"select artifact_id from artifacts where artifact_id in ({','.join('?' for _ in required)})",
                    required,
                ).fetchall()
            }
        finally:
            if self.conn is None:
                conn.close()
        missing = sorted(set(required) - found)
        if missing:
            return PolicyDecision(
                allowed=False,
                reason=f"required artifacts missing: {', '.join(missing)}",
                checks=["required artifact check failed"],
            )
        return PolicyDecision(allowed=True, checks=["required artifacts present"])


def _has_table(conn: sqlite3.Connection, table: str) -> bool:
    row = conn.execute(
        "select 1 from sqlite_master where type = 'table' and name = ?",
        (table,),
    ).fetchone()
    return row is not None
