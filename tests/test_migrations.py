from __future__ import annotations

import sqlite3

from agent_bus.db import initialize_database
from agent_bus.migrations import KERNEL_MIGRATION_ID


def test_kernel_migration_extends_old_event_log_without_reset(tmp_path):
    db_path = tmp_path / "old.sqlite3"
    with sqlite3.connect(db_path) as conn:
        conn.executescript(
            """
            create table schema_migrations (
                version integer primary key,
                applied_at text not null default (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
            );
            insert into schema_migrations(version) values (1);
            create table event_log (
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
            insert into event_log(event_id, type, ts, payload_json)
            values ('evt_old', 'custom.old', '2026-06-01T00:00:00Z', '{}');
            """
        )

    initialize_database(db_path)

    with sqlite3.connect(db_path) as conn:
        event_columns = _columns(conn, "event_log")
        old_event = conn.execute("select event_id from event_log").fetchone()[0]
        protocol_migration = conn.execute(
            "select migration_id from protocol_migrations where migration_id = ?",
            (KERNEL_MIGRATION_ID,),
        ).fetchone()
        tables = {row[0] for row in conn.execute("select name from sqlite_master where type = 'table'")}

    assert old_event == "evt_old"
    assert {
        "actor_role",
        "session_id",
        "session_epoch",
        "context_packet_id",
        "gate_id",
        "artifact_id",
        "projection_effect",
        "fencing_result",
    } <= event_columns
    assert protocol_migration is not None
    assert {
        "principals",
        "session_fences",
        "task_claims",
        "task_context_bindings",
        "protocol_violations",
        "projection_effects",
        "agent_session_epochs",
        "kernel_write_guards",
    } <= tables


def test_kernel_migration_is_idempotent(tmp_path):
    db_path = tmp_path / "agent-bus.sqlite3"

    initialize_database(db_path)
    initialize_database(db_path)

    with sqlite3.connect(db_path) as conn:
        event_columns = [row[1] for row in conn.execute("pragma table_info(event_log)")]
        migration_count = conn.execute(
            "select count(*) from protocol_migrations where migration_id = ?",
            (KERNEL_MIGRATION_ID,),
        ).fetchone()[0]

    assert event_columns.count("session_id") == 1
    assert event_columns.count("projection_effect") == 1
    assert migration_count == 1


def test_kernel_migration_extends_existing_domain_tables(tmp_path):
    db_path = tmp_path / "domain.sqlite3"
    with sqlite3.connect(db_path) as conn:
        conn.executescript(
            """
            create table schema_migrations (version integer primary key);
            create table event_log (
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
            create table agent_sessions (
                session_id text primary key,
                agent_id text not null,
                run_id text,
                active integer not null,
                runtime_state text not null,
                started_at text not null,
                last_seen_at text,
                ended_at text,
                replaced_by_session_id text
            );
            create table agent_identities (
                agent_id text primary key,
                display_name text,
                role text,
                capability_ids_json text not null,
                created_at text not null,
                updated_at text not null
            );
            create table context_packets (
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
            create table inbox_items (
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
            );
            create table artifacts (
                artifact_id text primary key,
                run_id text,
                task_id text,
                kind text not null,
                uri text not null,
                metadata_json text not null,
                created_by text,
                created_at text not null
            );
            """
        )

    initialize_database(db_path)

    with sqlite3.connect(db_path) as conn:
        assert {"session_epoch", "session_role", "fencing_token_hash", "accepts_new_work"} <= _columns(
            conn, "agent_sessions"
        )
        assert "session_end_reason" in _columns(conn, "agent_sessions")
        assert {
            "canonical",
            "identity_origin",
            "visibility_policy",
            "identity_lifecycle",
            "archive_reason",
        } <= _columns(conn, "agent_identities")
        assert {"packet_kind", "role_contract_json", "expected_outputs_json", "updated_at"} <= _columns(
            conn, "context_packets"
        )
        assert {"delivered_to_session_id", "delivery_epoch", "ack_fencing_result", "revoked_reason"} <= _columns(
            conn, "inbox_items"
        )
        assert {"agent_id", "session_id", "context_packet_id", "claim_id", "content_hash"} <= _columns(
            conn, "artifacts"
        )


def _columns(conn: sqlite3.Connection, table: str) -> set[str]:
    return {row[1] for row in conn.execute(f"pragma table_info({table})")}
