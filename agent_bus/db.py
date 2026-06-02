from __future__ import annotations

import os
import sqlite3
from pathlib import Path

from .migrations import MigrationRunner

DEFAULT_DB_PATH = Path.home() / ".codex-agent-bus" / "agent-bus.sqlite3"
SCHEMA_VERSION = 1


def resolve_db_path(db_path: str | os.PathLike[str] | None = None) -> Path:
    configured = db_path or os.environ.get("AGENT_BUS_DB")
    return Path(configured).expanduser() if configured else DEFAULT_DB_PATH


def connect(db_path: str | os.PathLike[str] | None = None) -> sqlite3.Connection:
    path = resolve_db_path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, timeout=30.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    return conn


def initialize_database(db_path: str | os.PathLike[str] | None = None, *, reset: bool = False) -> Path:
    path = resolve_db_path(db_path)
    if reset:
        _remove_sqlite_files(path)

    with connect(path) as conn:
        migrate(conn)
    return path


def migrate(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        create table if not exists schema_migrations (
            version integer primary key,
            applied_at text not null default (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
        );

        create table if not exists event_log (
            seq integer primary key autoincrement,
            event_id text unique not null,
            type text not null,
            ts text not null,
            actor text,
            run_id text,
            task_id text,
            agent_id text,
            correlation_id text,
            causation_id text,
            payload_json text not null
        );

        create index if not exists idx_event_log_type_seq on event_log(type, seq);
        create index if not exists idx_event_log_run_seq on event_log(run_id, seq);
        create index if not exists idx_event_log_task_seq on event_log(task_id, seq);
        create index if not exists idx_event_log_agent_seq on event_log(agent_id, seq);
        """
    )
    conn.execute(
        "insert or ignore into schema_migrations(version) values (?)",
        (SCHEMA_VERSION,),
    )
    MigrationRunner(conn).run()


def _remove_sqlite_files(path: Path) -> None:
    for candidate in (path, path.with_name(path.name + "-wal"), path.with_name(path.name + "-shm")):
        if candidate.exists():
            candidate.unlink()
