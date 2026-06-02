from __future__ import annotations

import json
import os
import sqlite3
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from threading import RLock
from typing import Any

from .authority import actor_role_for_principal
from .db import initialize_database
from .models import BusEvent, EventType, InboxItem, new_id, utc_now_iso
from .protocol_models import FencingResult, Principal, ProjectionEffect


DEFAULT_DB_PATH = Path.home() / ".codex-agent-bus" / "agent-bus.sqlite3"
QUEUED = "queued"
DELIVERED = "delivered"
ACKED = "acked"
BUSY_AGENT_DELIVERABLE_KINDS = {
    "user_interrupt",
    "context_invalidated",
    "agent_replan_required",
    "gate_result",
    "replacement_notice",
}
USER_INTERRUPT_PRIORITY = 1000
CONTEXT_INVALIDATED_PRIORITY = 990
AGENT_REPLAN_REQUIRED_PRIORITY = 980


@dataclass(frozen=True)
class InboxWaitResult:
    kind: str
    item: InboxItem | None = None
    noop: bool = False
    timed_out: bool = False

    @classmethod
    def timeout(cls) -> "InboxWaitResult":
        return cls(kind="noop", noop=True, timed_out=True)


def resolve_db_path(db_path: str | os.PathLike[str] | None = None) -> Path:
    if db_path is not None:
        return Path(db_path)
    return Path(os.environ.get("AGENT_BUS_DB", DEFAULT_DB_PATH))


def connect(db_path: str | os.PathLike[str] | None = None) -> sqlite3.Connection:
    path = resolve_db_path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), timeout=30, isolation_level=None, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    migrate(conn)
    return conn


def migrate(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        create table if not exists inbox_items (
            inbox_id text primary key,
            agent_id text not null,
            priority integer not null,
            kind text not null,
            status text not null,
            payload_json text not null,
            context_packet_id text,
            dedupe_key text,
            visible_at text not null,
            delivered_at text,
            delivered_to_session_id text,
            delivery_epoch integer,
            lease_expires_at text,
            delivery_attempts integer not null default 0,
            acked_at text,
            acked_by_session_id text,
            ack_fencing_result text,
            revoked_at text,
            revoked_reason text,
            expires_at text,
            created_at text not null
        )
        """
    )
    conn.execute(
        """
        create index if not exists idx_inbox_visible
        on inbox_items(agent_id, status, visible_at, priority)
        """
    )
    conn.execute(
        """
        create unique index if not exists idx_inbox_dedupe_active
        on inbox_items(agent_id, dedupe_key)
        where dedupe_key is not null and status != 'acked'
        """
    )
    for definition in (
        "delivered_to_session_id text",
        "delivery_epoch integer",
        "lease_expires_at text",
        "delivery_attempts integer not null default 0",
        "acked_by_session_id text",
        "ack_fencing_result text",
        "revoked_at text",
        "revoked_reason text",
    ):
        _add_column_if_missing(conn, "inbox_items", definition)


class InboxStore:
    def __init__(
        self,
        db_path: str | os.PathLike[str] | None = None,
        conn: sqlite3.Connection | None = None,
        trusted_compatibility: bool = False,
        principal: Principal | None = None,
    ) -> None:
        self.db_path = db_path
        if conn is None:
            initialize_database(db_path)
        self.conn = conn if conn is not None else connect(db_path)
        self._owns_connection = conn is None
        self._lock = RLock()
        self.trusted_compatibility = trusted_compatibility
        self.principal = principal
        migrate(self.conn)

    def close(self) -> None:
        if self._owns_connection:
            self.conn.close()

    def enqueue(
        self,
        agent_id: str,
        kind: str,
        payload: dict[str, Any] | None = None,
        *,
        priority: int = 0,
        context_packet_id: str | None = None,
        dedupe_key: str | None = None,
        visible_at: str | None = None,
        expires_at: str | None = None,
        inbox_id: str | None = None,
        actor: str | None = None,
        principal: Principal | None = None,
        session_id: str | None = None,
        session_epoch: int | None = None,
        fencing_token: str | None = None,
    ) -> InboxItem:
        principal = principal or self.principal
        item = InboxItem(
            inbox_id=inbox_id or new_id("inbox"),
            agent_id=agent_id,
            priority=priority,
            kind=kind,
            status=QUEUED,
            payload=payload or {},
            context_packet_id=context_packet_id,
            dedupe_key=dedupe_key,
            visible_at=visible_at or utc_now_iso(),
            expires_at=expires_at,
        )
        with self._lock:
            try:
                event = BusEvent(
                    type=EventType.INBOX_ENQUEUED,
                    actor=actor,
                    actor_role=actor_role_for_principal(principal),
                    agent_id=item.agent_id,
                    context_packet_id=item.context_packet_id,
                    projection_effect=ProjectionEffect.COMMIT,
                    fencing_result=FencingResult.NOT_REQUIRED,
                    payload=item.model_dump(mode="json"),
                )
                from .protocol import ProtocolKernel

                result = ProtocolKernel(self.db_path, conn=self.conn).commit_event(
                    event,
                    principal=principal,
                    session_id=session_id,
                    session_epoch=session_epoch,
                    fencing_token=fencing_token,
                    guard_targets=(("inbox_items", item.inbox_id, EventType.INBOX_ENQUEUED.value),),
                    target_table="inbox_items",
                    target_id=item.inbox_id,
                    reason="inbox item enqueued through ProtocolKernel command",
                    mutation=lambda conn, _event: conn.execute(
                        """
                        insert into inbox_items (
                            inbox_id, agent_id, priority, kind, status, payload_json,
                            context_packet_id, dedupe_key, visible_at, delivered_at,
                            acked_at, expires_at, created_at
                        ) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            item.inbox_id,
                            item.agent_id,
                            item.priority,
                            item.kind,
                            item.status,
                            json.dumps(item.payload, sort_keys=True),
                            item.context_packet_id,
                            item.dedupe_key,
                            item.visible_at,
                            item.delivered_at,
                            item.acked_at,
                            item.expires_at,
                            item.created_at,
                        ),
                    ),
                )
                if not result.accepted:
                    raise PermissionError(result.reason or "protocol rejected inbox enqueue")
            except sqlite3.IntegrityError:
                if dedupe_key is None:
                    raise
                existing = self.get_by_dedupe(agent_id, dedupe_key)
                if existing is None:
                    raise
                return existing
        return item

    def wait(
        self,
        agent_id: str,
        timeout: float,
        *,
        busy: bool = False,
        visibility_timeout: float = 30.0,
        poll_interval: float = 0.05,
        session_id: str | None = None,
        session_epoch: int | None = None,
        fencing_token: str | None = None,
        require_fence: bool = False,
    ) -> InboxWaitResult:
        if require_fence or session_id is not None or fencing_token is not None:
            allowed, reason = self._validate_session_fence(
                agent_id,
                action="inbox.wait",
                session_id=session_id,
                session_epoch=session_epoch,
                fencing_token=fencing_token,
            )
            if not allowed:
                raise PermissionError(reason)
        deadline = time.monotonic() + max(timeout, 0)
        while True:
            item = self._try_deliver(
                agent_id,
                busy=busy,
                visibility_timeout=visibility_timeout,
                session_id=session_id,
                session_epoch=session_epoch,
            )
            if item is not None:
                return InboxWaitResult(kind=item.kind, item=item)
            if time.monotonic() >= deadline:
                return InboxWaitResult.timeout()
            time.sleep(min(poll_interval, max(deadline - time.monotonic(), 0)))

    def ack(
        self,
        inbox_id: str,
        *,
        agent_id: str | None = None,
        session_id: str | None = None,
        session_epoch: int | None = None,
        fencing_token: str | None = None,
        require_fence: bool = False,
    ) -> bool:
        now = utc_now_iso()
        if require_fence or session_id is not None or fencing_token is not None:
            item = self.get(inbox_id)
            expected_agent = agent_id or (item.agent_id if item is not None else None)
            if expected_agent is None:
                return False
            allowed, _reason = self._validate_session_fence(
                expected_agent,
                action="inbox.acked",
                session_id=session_id,
                session_epoch=session_epoch,
                fencing_token=fencing_token,
            )
            if not allowed:
                return False
            if item.delivered_to_session_id is not None and item.delivered_to_session_id != session_id:
                self._record_inbox_reject(
                    action="inbox.acked",
                    actor=expected_agent,
                    reason="inbox item was delivered to a different fenced session",
                    session_id=session_id,
                    payload={"inbox_id": inbox_id, "delivered_to_session_id": item.delivered_to_session_id},
                )
                return False
        with self._lock:
            if agent_id is None:
                cursor = self.conn.execute(
                    """
                    update inbox_items
                    set status = ?, acked_at = ?, acked_by_session_id = coalesce(?, acked_by_session_id),
                        ack_fencing_result = coalesce(?, ack_fencing_result)
                    where inbox_id = ? and status != ?
                    """,
                    (
                        ACKED,
                        now,
                        session_id,
                        "VALID" if session_id is not None else None,
                        inbox_id,
                        ACKED,
                    ),
                )
            else:
                cursor = self.conn.execute(
                    """
                    update inbox_items
                    set status = ?, acked_at = ?, acked_by_session_id = coalesce(?, acked_by_session_id),
                        ack_fencing_result = coalesce(?, ack_fencing_result)
                    where inbox_id = ? and agent_id = ? and status != ?
                    """,
                    (
                        ACKED,
                        now,
                        session_id,
                        "VALID" if session_id is not None else None,
                        inbox_id,
                        agent_id,
                        ACKED,
                    ),
                )
        return cursor.rowcount > 0

    def get(self, inbox_id: str) -> InboxItem | None:
        row = self.conn.execute(
            "select * from inbox_items where inbox_id = ?",
            (inbox_id,),
        ).fetchone()
        return row_to_item(row) if row is not None else None

    def get_by_dedupe(self, agent_id: str, dedupe_key: str) -> InboxItem | None:
        row = self.conn.execute(
            """
            select * from inbox_items
            where agent_id = ? and dedupe_key = ? and status != ?
            order by created_at asc
            limit 1
            """,
            (agent_id, dedupe_key, ACKED),
        ).fetchone()
        return row_to_item(row) if row is not None else None

    def list_items(self, agent_id: str | None = None) -> list[InboxItem]:
        if agent_id is None:
            rows = self.conn.execute("select * from inbox_items order by created_at asc").fetchall()
        else:
            rows = self.conn.execute(
                "select * from inbox_items where agent_id = ? order by created_at asc",
                (agent_id,),
            ).fetchall()
        return [row_to_item(row) for row in rows]

    def _try_deliver(
        self,
        agent_id: str,
        *,
        busy: bool,
        visibility_timeout: float,
        session_id: str | None = None,
        session_epoch: int | None = None,
    ) -> InboxItem | None:
        now = utc_now_iso()
        now_dt = datetime.now(timezone.utc)
        cutoff = iso_from_datetime(now_dt - timedelta(seconds=visibility_timeout))
        lease_expires_at = iso_from_datetime(now_dt + timedelta(seconds=visibility_timeout))
        busy_filter = ""
        busy_kind_params: list[str] = []
        if busy:
            placeholders = ", ".join("?" for _ in BUSY_AGENT_DELIVERABLE_KINDS)
            busy_filter = f"and kind in ({placeholders})"
            busy_kind_params = sorted(BUSY_AGENT_DELIVERABLE_KINDS)
        with self._lock:
            self.conn.execute("begin immediate")
            try:
                self.conn.execute(
                    """
                    update inbox_items
                    set status = ?, delivered_at = null, visible_at = ?,
                        delivered_to_session_id = null, delivery_epoch = null, lease_expires_at = null
                    where agent_id = ?
                      and status = ?
                      and acked_at is null
                      and delivered_at <= ?
                    """,
                    (QUEUED, now, agent_id, DELIVERED, cutoff),
                )
                row = self.conn.execute(
                    f"""
                    select * from inbox_items
                    where agent_id = ?
                      and status = ?
                      and visible_at <= ?
                      and (expires_at is null or expires_at > ?)
                      {busy_filter}
                    order by priority desc, created_at asc, inbox_id asc
                    limit 1
                    """,
                    [agent_id, QUEUED, now, now, *busy_kind_params],
                ).fetchone()
                if row is None:
                    self.conn.execute("commit")
                    return None
                delivered_at = utc_now_iso()
                self.conn.execute(
                    """
                    update inbox_items
                    set status = ?, delivered_at = ?, delivered_to_session_id = ?,
                        delivery_epoch = ?, lease_expires_at = ?,
                        delivery_attempts = delivery_attempts + 1
                    where inbox_id = ?
                    """,
                    (DELIVERED, delivered_at, session_id, session_epoch, lease_expires_at, row["inbox_id"]),
                )
                self.conn.execute("commit")
            except Exception:
                self.conn.execute("rollback")
                raise
        delivered = self.get(row["inbox_id"])
        return delivered

    def enqueue_interrupt_wakeups(
        self,
        agent_id: str,
        payload: dict[str, Any],
        *,
        interrupt_id: str,
        context_packet_ids: list[str] | None = None,
    ) -> list[InboxItem]:
        packet_ids = context_packet_ids or []
        shared_payload = dict(payload)
        shared_payload["invalidated_packet_ids"] = packet_ids
        return [
            self.enqueue(
                agent_id,
                "user_interrupt",
                shared_payload,
                priority=USER_INTERRUPT_PRIORITY,
                dedupe_key=f"{interrupt_id}:{agent_id}:user_interrupt",
            ),
            self.enqueue(
                agent_id,
                "context_invalidated",
                shared_payload,
                priority=CONTEXT_INVALIDATED_PRIORITY,
                dedupe_key=f"{interrupt_id}:{agent_id}:context_invalidated",
            ),
            self.enqueue(
                agent_id,
                "agent_replan_required",
                shared_payload,
                priority=AGENT_REPLAN_REQUIRED_PRIORITY,
                dedupe_key=f"{interrupt_id}:{agent_id}:agent_replan_required",
            ),
        ]

    def _validate_session_fence(
        self,
        agent_id: str,
        *,
        action: str,
        session_id: str | None,
        session_epoch: int | None,
        fencing_token: str | None,
    ) -> tuple[bool, str | None]:
        from .fencing import FencingService

        check = FencingService(self.db_path, conn=self.conn).validate(
            session_id,
            session_epoch,
            fencing_token,
            required=True,
        )
        if not check.allowed:
            self._record_inbox_reject(
                action=action,
                actor=agent_id,
                reason=check.reason or "inbox fencing rejected",
                fencing_result=check.result,
                session_id=session_id,
                payload={"agent_id": agent_id},
            )
            return False, check.reason
        if check.agent_id != agent_id:
            reason = "fenced session does not belong to inbox agent"
            self._record_inbox_reject(
                action=action,
                actor=agent_id,
                reason=reason,
                fencing_result=FencingResult.WRONG_SESSION,
                session_id=session_id,
                payload={"agent_id": agent_id, "fenced_agent_id": check.agent_id},
            )
            return False, reason
        return True, None

    def _record_inbox_reject(
        self,
        *,
        action: str,
        actor: str | None,
        reason: str,
        fencing_result: FencingResult | str = FencingResult.NOT_REQUIRED,
        session_id: str | None,
        payload: dict[str, Any],
    ) -> None:
        from .protocol import ProtocolKernel

        ProtocolKernel(self.db_path, conn=self.conn).reject_action(
            action=action,
            actor=actor,
            actor_role="worker",
            reason=reason,
            fencing_result=fencing_result,
            payload=payload,
            agent_id=actor,
            session_id=session_id,
        )


def enqueue(
    agent_id: str,
    kind: str,
    payload: dict[str, Any] | None = None,
    *,
    db_path: str | os.PathLike[str] | None = None,
    **kwargs: Any,
) -> InboxItem:
    store = InboxStore(db_path=db_path)
    try:
        return store.enqueue(agent_id, kind, payload, **kwargs)
    finally:
        store.close()


def wait(
    agent_id: str,
    timeout: float,
    *,
    db_path: str | os.PathLike[str] | None = None,
    **kwargs: Any,
) -> InboxWaitResult:
    store = InboxStore(db_path=db_path)
    try:
        return store.wait(agent_id, timeout, **kwargs)
    finally:
        store.close()


def ack(
    inbox_id: str,
    *,
    agent_id: str | None = None,
    db_path: str | os.PathLike[str] | None = None,
    **kwargs: Any,
) -> bool:
    store = InboxStore(db_path=db_path)
    try:
        return store.ack(inbox_id, agent_id=agent_id, **kwargs)
    finally:
        store.close()


def enqueue_interrupt_wakeups(
    agent_id: str,
    payload: dict[str, Any],
    *,
    interrupt_id: str,
    context_packet_ids: list[str] | None = None,
    db_path: str | os.PathLike[str] | None = None,
) -> list[InboxItem]:
    store = InboxStore(db_path=db_path)
    try:
        return store.enqueue_interrupt_wakeups(
            agent_id,
            payload,
            interrupt_id=interrupt_id,
            context_packet_ids=context_packet_ids,
        )
    finally:
        store.close()


def row_to_item(row: sqlite3.Row) -> InboxItem:
    return InboxItem(
        inbox_id=row["inbox_id"],
        agent_id=row["agent_id"],
        priority=row["priority"],
        kind=row["kind"],
        status=row["status"],
        payload=json.loads(row["payload_json"]),
        context_packet_id=row["context_packet_id"],
        dedupe_key=row["dedupe_key"],
        visible_at=row["visible_at"],
        delivered_at=row["delivered_at"],
        delivered_to_session_id=row["delivered_to_session_id"],
        delivery_epoch=row["delivery_epoch"],
        lease_expires_at=row["lease_expires_at"],
        delivery_attempts=row["delivery_attempts"],
        acked_at=row["acked_at"],
        acked_by_session_id=row["acked_by_session_id"],
        ack_fencing_result=row["ack_fencing_result"],
        revoked_at=row["revoked_at"],
        revoked_reason=row["revoked_reason"],
        expires_at=row["expires_at"],
        created_at=row["created_at"],
    )


def iso_from_datetime(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _add_column_if_missing(conn: sqlite3.Connection, table: str, column_definition: str) -> None:
    column = column_definition.split()[0]
    columns = {row[1] for row in conn.execute(f"pragma table_info({table})").fetchall()}
    if column not in columns:
        conn.execute(f"alter table {table} add column {column_definition}")
