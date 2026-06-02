from __future__ import annotations

import sqlite3

KERNEL_MIGRATION_ID = "protocol_kernel_v2_001"


AUTHORITATIVE_EVENT_TYPES = (
    "task.completed",
    "task.failed",
    "task.reassigned",
    "gate.result",
    "gate.approved",
    "gate.rejected",
    "gate.escalated",
    "replacement.approved",
    "replacement.reassignment_committed",
)


class MigrationRunner:
    """Idempotent SQLite migrations for protocol-kernel tables and columns."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn

    def run(self) -> None:
        self.create_table_if_missing(
            """
            create table if not exists protocol_migrations (
                migration_id text primary key,
                applied_at text not null default (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
            )
            """
        )
        self._migrate_event_log()
        self._migrate_agent_sessions()
        self._migrate_context_packets()
        self._migrate_inbox_items()
        self._migrate_artifacts()
        self._create_protocol_tables()
        self._create_authority_triggers()
        self.record_schema_version(KERNEL_MIGRATION_ID)
        self.conn.commit()

    def has_table(self, table: str) -> bool:
        row = self.conn.execute(
            "select 1 from sqlite_master where type = 'table' and name = ?",
            (table,),
        ).fetchone()
        return row is not None

    def has_column(self, table: str, column: str) -> bool:
        if not self.has_table(table):
            return False
        rows = self.conn.execute(f"pragma table_info({table})").fetchall()
        return any(row[1] == column for row in rows)

    def add_column_if_missing(self, table: str, column_definition: str) -> None:
        column = column_definition.split()[0]
        if self.has_table(table) and not self.has_column(table, column):
            self.conn.execute(f"alter table {table} add column {column_definition}")

    def create_table_if_missing(self, sql: str) -> None:
        self.conn.execute(sql)

    def record_schema_version(self, migration_id: str) -> None:
        self.conn.execute(
            "insert or ignore into protocol_migrations(migration_id) values (?)",
            (migration_id,),
        )

    def _migrate_event_log(self) -> None:
        if not self.has_table("event_log"):
            return
        for definition in (
            "actor_role text",
            "session_id text",
            "session_epoch integer",
            "context_packet_id text",
            "gate_id text",
            "artifact_id text",
            "projection_effect text",
            "fencing_result text",
        ):
            self.add_column_if_missing("event_log", definition)
        self.conn.executescript(
            """
            create index if not exists idx_event_log_session_seq on event_log(session_id, session_epoch, seq);
            create index if not exists idx_event_log_context_seq on event_log(context_packet_id, seq);
            create index if not exists idx_event_log_gate_seq on event_log(gate_id, seq);
            create index if not exists idx_event_log_artifact_seq on event_log(artifact_id, seq);
            create index if not exists idx_event_log_projection_effect on event_log(projection_effect, seq);
            """
        )

    def _migrate_agent_sessions(self) -> None:
        if not self.has_table("agent_sessions"):
            return
        for definition in (
            "session_epoch integer not null default 1",
            "session_role text not null default 'primary'",
            "fencing_token_hash text",
            "max_concurrent_tasks integer not null default 1",
            "accepts_new_work integer not null default 1",
            "quarantined integer not null default 0",
        ):
            self.add_column_if_missing("agent_sessions", definition)

    def _migrate_context_packets(self) -> None:
        if not self.has_table("context_packets"):
            return
        for definition in (
            "packet_kind text not null default 'assignment'",
            "role_contract_json text",
            "objective text not null default ''",
            "constraints_json text not null default '[]'",
            "next_action text",
            "expected_outputs_json text not null default '[]'",
            "required_artifacts_json text not null default '[]'",
            "acceptance_gates_json text not null default '[]'",
            "updated_at text",
        ):
            self.add_column_if_missing("context_packets", definition)

    def _migrate_inbox_items(self) -> None:
        if not self.has_table("inbox_items"):
            return
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
            self.add_column_if_missing("inbox_items", definition)

    def _migrate_artifacts(self) -> None:
        if not self.has_table("artifacts"):
            return
        for definition in (
            "agent_id text",
            "session_id text",
            "context_packet_id text",
            "claim_id text",
            "produced_by_event_id text",
            "content_hash text",
        ):
            self.add_column_if_missing("artifacts", definition)

    def _create_protocol_tables(self) -> None:
        self.conn.executescript(
            """
            create table if not exists principals (
                principal_id text primary key,
                principal_type text not null,
                agent_id text,
                session_id text,
                roles_json text not null,
                permissions_json text not null,
                created_at text not null,
                updated_at text not null
            );

            create table if not exists actor_permissions (
                permission_id text primary key,
                principal_type text,
                role text,
                action text not null,
                effect text not null,
                created_at text not null default (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
                unique(principal_type, role, action)
            );

            create table if not exists agent_session_epochs (
                agent_id text primary key,
                current_epoch integer not null,
                updated_at text not null
            );

            create table if not exists session_fences (
                session_id text primary key,
                agent_id text,
                session_epoch integer not null,
                token_hash text not null,
                session_role text not null,
                active integer not null,
                quarantined integer not null default 0,
                replaced_by_session_id text,
                created_at text not null,
                updated_at text not null
            );

            create table if not exists task_claims (
                claim_id text primary key,
                claim_kind text not null,
                task_id text not null,
                run_id text,
                agent_id text,
                session_id text,
                session_epoch integer,
                context_packet_id text,
                status text not null,
                payload_json text not null,
                created_from_event_id text,
                committed_by_event_id text,
                created_at text not null,
                updated_at text not null
            );
            create index if not exists idx_task_claims_task_status on task_claims(task_id, status);
            create index if not exists idx_task_claims_session on task_claims(session_id, session_epoch);

            create table if not exists task_context_bindings (
                binding_id text primary key,
                task_id text not null,
                agent_id text,
                session_id text,
                session_epoch integer,
                context_packet_id text not null,
                binding_kind text not null,
                status text not null,
                created_from_event_id text,
                created_at text not null,
                ended_at text
            );
            create index if not exists idx_task_context_bindings_active
            on task_context_bindings(task_id, agent_id, session_id, status);

            create table if not exists protocol_violations (
                violation_id text primary key,
                attempted_event_id text,
                actor text,
                actor_role text,
                action text not null,
                reason text not null,
                fencing_result text,
                projection_effect text not null,
                run_id text,
                task_id text,
                agent_id text,
                session_id text,
                context_packet_id text,
                payload_json text not null,
                created_at text not null
            );
            create index if not exists idx_protocol_violations_task on protocol_violations(task_id, created_at);
            create index if not exists idx_protocol_violations_session on protocol_violations(session_id, created_at);

            create table if not exists projection_effects (
                effect_id text primary key,
                event_id text,
                attempted_event_id text,
                effect text not null,
                reason text,
                target_table text,
                target_id text,
                run_id text,
                task_id text,
                created_at text not null
            );
            create index if not exists idx_projection_effects_event on projection_effects(event_id);
            create index if not exists idx_projection_effects_task on projection_effects(task_id, created_at);

            create table if not exists agent_workload_snapshots (
                snapshot_id text primary key,
                agent_id text not null,
                session_id text,
                current_task_ids_json text not null,
                accepts_new_work integer not null,
                max_concurrent_tasks integer not null,
                created_at text not null
            );

            create table if not exists kernel_write_guards (
                guard_id text primary key,
                event_id text,
                target_table text,
                target_id text,
                action text not null,
                created_at text not null default (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
            );
            create index if not exists idx_kernel_write_guards_event on kernel_write_guards(event_id);
            create index if not exists idx_kernel_write_guards_target
            on kernel_write_guards(target_table, target_id, action);
            """
        )

    def _create_authority_triggers(self) -> None:
        if self.has_table("event_log"):
            quoted = ", ".join(f"'{event_type}'" for event_type in AUTHORITATIVE_EVENT_TYPES)
            self.conn.executescript(
                f"""
                create trigger if not exists trg_event_log_authoritative_kernel_guard
                before insert on event_log
                when new.type in ({quoted})
                     and not exists (
                         select 1 from kernel_write_guards
                         where event_id = new.event_id
                     )
                begin
                    select raise(abort, 'authoritative event requires ProtocolKernel UnitOfWork');
                end;
                """
            )
        if self.has_table("tasks"):
            self.conn.executescript(
                """
                create trigger if not exists trg_tasks_authoritative_status_guard
                before update of status on tasks
                when new.status in ('completed', 'failed', 'reassigned')
                     and old.status is not new.status
                     and not exists (
                         select 1 from kernel_write_guards
                         where target_table = 'tasks'
                           and target_id = new.task_id
                     )
                begin
                    select raise(abort, 'authoritative task mutation requires ProtocolKernel UnitOfWork');
                end;
                """
            )
        if self.has_table("gates"):
            self.conn.executescript(
                """
                create trigger if not exists trg_gates_authoritative_state_guard
                before update of state on gates
                when new.state in ('approved', 'rejected', 'escalated')
                     and old.state is not new.state
                     and not exists (
                         select 1 from kernel_write_guards
                         where target_table = 'gates'
                           and target_id = new.gate_id
                     )
                begin
                    select raise(abort, 'authoritative gate mutation requires ProtocolKernel UnitOfWork');
                end;
                """
            )
