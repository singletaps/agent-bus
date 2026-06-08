from __future__ import annotations

import hashlib
import hmac
import os
import secrets
import sqlite3
from pathlib import Path

from .db import connect, initialize_database
from .protocol_models import FencingCheck, FencingResult, SessionFenceRegistration, SessionRole
from .models import utc_now_iso


def hash_fencing_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


class FencingService:
    """Validates worker session leases without persisting raw tokens."""

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

    def register_session(
        self,
        session_id: str,
        *,
        agent_id: str | None = None,
        session_epoch: int = 1,
        token: str | None = None,
        session_role: SessionRole | str = SessionRole.PRIMARY,
        active: bool = True,
        quarantined: bool = False,
        replaced_by_session_id: str | None = None,
    ) -> SessionFenceRegistration:
        raw_token = token or secrets.token_urlsafe(32)
        token_hash = hash_fencing_token(raw_token)
        now = utc_now_iso()
        role = _enum_value(session_role)
        conn = self.conn or connect(self.db_path)
        try:
            conn.execute(
                """
                insert into session_fences (
                    session_id, agent_id, session_epoch, token_hash, session_role,
                    active, quarantined, replaced_by_session_id, created_at, updated_at
                ) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                on conflict(session_id) do update set
                    agent_id = excluded.agent_id,
                    session_epoch = excluded.session_epoch,
                    token_hash = excluded.token_hash,
                    session_role = excluded.session_role,
                    active = excluded.active,
                    quarantined = excluded.quarantined,
                    replaced_by_session_id = excluded.replaced_by_session_id,
                    updated_at = excluded.updated_at
                """,
                (
                    session_id,
                    agent_id,
                    session_epoch,
                    token_hash,
                    role,
                    int(active),
                    int(quarantined),
                    replaced_by_session_id,
                    now,
                    now,
                ),
            )
            if agent_id is not None:
                conn.execute(
                    """
                    insert into agent_session_epochs(agent_id, current_epoch, updated_at)
                    values (?, ?, ?)
                    on conflict(agent_id) do update set
                        current_epoch = max(current_epoch, excluded.current_epoch),
                        updated_at = excluded.updated_at
                    """,
                    (agent_id, session_epoch, now),
                )
            if self.conn is None:
                conn.commit()
        finally:
            if self.conn is None:
                conn.close()
        return SessionFenceRegistration(
            session_id=session_id,
            agent_id=agent_id,
            session_epoch=session_epoch,
            raw_token=raw_token,
            token_hash=token_hash,
            session_role=SessionRole(role),
        )

    def validate(
        self,
        session_id: str | None,
        session_epoch: int | None,
        token: str | None,
        *,
        required: bool = True,
    ) -> FencingCheck:
        if not required:
            return FencingCheck(
                allowed=True,
                result=FencingResult.NOT_REQUIRED,
                reason="fencing not required for this principal",
                session_id=session_id,
                session_epoch=session_epoch,
            )
        if not session_id or not token:
            return FencingCheck(
                allowed=False,
                result=FencingResult.MISSING,
                reason="missing session_id or fencing token",
                session_id=session_id,
                session_epoch=session_epoch,
            )

        conn = self.conn or connect(self.db_path)
        try:
            row = conn.execute(
                "select * from session_fences where session_id = ?",
                (session_id,),
            ).fetchone()
        finally:
            if self.conn is None:
                conn.close()

        if row is None:
            return FencingCheck(
                allowed=False,
                result=FencingResult.INVALID,
                reason="unknown fenced session",
                session_id=session_id,
                session_epoch=session_epoch,
            )
        stored_epoch = int(row["session_epoch"])
        if session_epoch != stored_epoch:
            return FencingCheck(
                allowed=False,
                result=FencingResult.STALE_EPOCH,
                reason=f"session epoch {session_epoch} does not match current epoch {stored_epoch}",
                session_id=session_id,
                session_epoch=session_epoch,
                agent_id=row["agent_id"],
            )
        if not bool(row["active"]) or row["replaced_by_session_id"]:
            return FencingCheck(
                allowed=False,
                result=FencingResult.WRONG_SESSION,
                reason="session is not the active fenced session",
                session_id=session_id,
                session_epoch=session_epoch,
                agent_id=row["agent_id"],
            )
        if bool(row["quarantined"]) or row["session_role"] in {SessionRole.QUARANTINED.value, SessionRole.RETIRED.value}:
            return FencingCheck(
                allowed=False,
                result=FencingResult.INVALID,
                reason="session is quarantined or retired",
                session_id=session_id,
                session_epoch=session_epoch,
                agent_id=row["agent_id"],
            )
        if row["session_role"] == SessionRole.REPLACED.value:
            return FencingCheck(
                allowed=False,
                result=FencingResult.WRONG_SESSION,
                reason="session has been replaced",
                session_id=session_id,
                session_epoch=session_epoch,
                agent_id=row["agent_id"],
            )
        if not hmac.compare_digest(hash_fencing_token(token), row["token_hash"]):
            return FencingCheck(
                allowed=False,
                result=FencingResult.INVALID,
                reason="fencing token does not match session lease",
                session_id=session_id,
                session_epoch=session_epoch,
                agent_id=row["agent_id"],
            )
        return FencingCheck(
            allowed=True,
            result=FencingResult.VALID,
            session_id=session_id,
            session_epoch=session_epoch,
            agent_id=row["agent_id"],
        )


def _enum_value(value: object) -> str:
    return value.value if hasattr(value, "value") else str(value)
