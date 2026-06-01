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

from .models import InboxItem, new_id, utc_now_iso


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
            acked_at text,
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


class InboxStore:
    def __init__(
        self,
        db_path: str | os.PathLike[str] | None = None,
        conn: sqlite3.Connection | None = None,
    ) -> None:
        self.conn = conn if conn is not None else connect(db_path)
        self._owns_connection = conn is None
        self._lock = RLock()
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
    ) -> InboxItem:
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
                self.conn.execute(
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
                )
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
    ) -> InboxWaitResult:
        deadline = time.monotonic() + max(timeout, 0)
        while True:
            item = self._try_deliver(agent_id, busy=busy, visibility_timeout=visibility_timeout)
            if item is not None:
                return InboxWaitResult(kind=item.kind, item=item)
            if time.monotonic() >= deadline:
                return InboxWaitResult.timeout()
            time.sleep(min(poll_interval, max(deadline - time.monotonic(), 0)))

    def ack(self, inbox_id: str, *, agent_id: str | None = None) -> bool:
        now = utc_now_iso()
        with self._lock:
            if agent_id is None:
                cursor = self.conn.execute(
                    """
                    update inbox_items
                    set status = ?, acked_at = ?
                    where inbox_id = ? and status != ?
                    """,
                    (ACKED, now, inbox_id, ACKED),
                )
            else:
                cursor = self.conn.execute(
                    """
                    update inbox_items
                    set status = ?, acked_at = ?
                    where inbox_id = ? and agent_id = ? and status != ?
                    """,
                    (ACKED, now, inbox_id, agent_id, ACKED),
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
    ) -> InboxItem | None:
        now = utc_now_iso()
        cutoff = iso_from_datetime(datetime.now(timezone.utc) - timedelta(seconds=visibility_timeout))
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
                    set status = ?, delivered_at = null, visible_at = ?
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
                    set status = ?, delivered_at = ?
                    where inbox_id = ?
                    """,
                    (DELIVERED, delivered_at, row["inbox_id"]),
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
) -> bool:
    store = InboxStore(db_path=db_path)
    try:
        return store.ack(inbox_id, agent_id=agent_id)
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
        acked_at=row["acked_at"],
        expires_at=row["expires_at"],
        created_at=row["created_at"],
    )


def iso_from_datetime(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
