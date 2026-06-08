from __future__ import annotations

import sqlite3

from agent_bus.authority import agent_principal, controller_principal
from agent_bus.context import ContextStore
from agent_bus.fencing import FencingService
from agent_bus.protocol import ProtocolKernel
from agent_bus.protocol_models import FencingResult, PacketKind, Principal, PrincipalType, ProjectionEffect, SessionRole
from agent_bus.store import EventStore


def test_worker_event_with_valid_fence_commits_event_and_projection(tmp_path):
    db_path = tmp_path / "agent-bus.sqlite3"
    registration = FencingService(db_path).register_session(
        "session-1",
        agent_id="worker.backend",
        session_epoch=1,
        token="secret-token",
    )
    kernel = ProtocolKernel(db_path)
    principal = agent_principal("worker.backend", session_id=registration.session_id)
    packet = ContextStore(db_path, principal=controller_principal()).create_packet(
        agent_id="worker.backend",
        task_id="task-1",
        summary="Worker assignment context",
        actor="controller",
        session_id=registration.session_id,
        session_epoch=registration.session_epoch,
        packet_kind=PacketKind.ASSIGNMENT,
    )

    result = kernel.record_event(
        event_type="task.progress_reported",
        action="task.progress_reported",
        actor="worker.backend",
        actor_role="worker",
        principal=principal,
        agent_id="worker.backend",
        task_id="task-1",
        session_id=registration.session_id,
        session_epoch=registration.session_epoch,
        context_packet_id=packet.packet_id,
        fencing_token=registration.raw_token,
        payload={"message": "halfway"},
    )

    assert result.accepted is True
    assert result.projection_effect is ProjectionEffect.COMMIT
    assert result.fencing_result is FencingResult.VALID

    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        event = conn.execute("select * from event_log where event_id = ?", (result.event_id,)).fetchone()
        effect = conn.execute("select * from projection_effects where event_id = ?", (result.event_id,)).fetchone()
        stored_fence = conn.execute("select token_hash from session_fences where session_id = 'session-1'").fetchone()
        dump = "\n".join(str(row) for row in conn.execute("select * from event_log").fetchall())

    assert event["session_id"] == "session-1"
    assert event["session_epoch"] == 1
    assert event["projection_effect"] == "COMMIT"
    assert event["fencing_result"] == "VALID"
    assert effect["effect"] == "COMMIT"
    assert stored_fence["token_hash"] != "secret-token"
    assert "secret-token" not in dump


def test_event_store_replays_protocol_envelope_fields(tmp_path):
    db_path = tmp_path / "agent-bus.sqlite3"
    registration = FencingService(db_path).register_session(
        "session-1",
        agent_id="worker.backend",
        token="secret-token",
    )
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            insert into task_context_bindings (
                binding_id, task_id, agent_id, session_id, session_epoch,
                context_packet_id, binding_kind, status, created_at
            ) values (
                'binding-1', 'task-1', 'worker.backend', 'session-1', 1,
                'ctx-1', 'assignment', 'active', '2026-06-01T00:00:00Z'
            )
            """
        )
    result = ProtocolKernel(db_path).record_event(
        event_type="task.progress_reported",
        action="task.progress_reported",
        actor="worker.backend",
        actor_role="worker",
        principal=agent_principal("worker.backend", session_id=registration.session_id),
        agent_id="worker.backend",
        task_id="task-1",
        context_packet_id="ctx-1",
        session_id=registration.session_id,
        session_epoch=registration.session_epoch,
        fencing_token=registration.raw_token,
        payload={"message": "with envelope"},
    )

    loaded = EventStore(db_path).get_event(result.event_id or "")

    assert loaded is not None
    assert loaded.actor_role == "worker"
    assert loaded.session_id == "session-1"
    assert loaded.session_epoch == 1
    assert loaded.context_packet_id == "ctx-1"
    assert loaded.projection_effect is ProjectionEffect.COMMIT
    assert loaded.fencing_result is FencingResult.VALID


def test_missing_worker_token_rejects_without_event_log_row(tmp_path):
    db_path = tmp_path / "agent-bus.sqlite3"
    FencingService(db_path).register_session("session-1", agent_id="worker.backend", token="secret-token")
    result = ProtocolKernel(db_path).record_event(
        event_type="task.completion_claimed",
        action="task.completion_claimed",
        actor="worker.backend",
        actor_role="worker",
        principal=agent_principal("worker.backend", session_id="session-1"),
        agent_id="worker.backend",
        task_id="task-1",
        session_id="session-1",
        session_epoch=1,
        fencing_token=None,
        payload={"done": True},
    )

    assert result.accepted is False
    assert result.projection_effect is ProjectionEffect.REJECT
    assert result.fencing_result is FencingResult.MISSING

    with sqlite3.connect(db_path) as conn:
        event_count = conn.execute("select count(*) from event_log").fetchone()[0]
        violation = conn.execute("select * from protocol_violations").fetchone()
        effect = conn.execute("select effect from projection_effects").fetchone()[0]

    assert event_count == 0
    assert violation is not None
    assert effect == "REJECT"


def test_stale_epoch_rejects_worker_write(tmp_path):
    db_path = tmp_path / "agent-bus.sqlite3"
    registration = FencingService(db_path).register_session(
        "session-1",
        agent_id="worker.backend",
        session_epoch=2,
        token="secret-token",
    )

    result = ProtocolKernel(db_path).record_event(
        event_type="task.progress_reported",
        action="task.progress_reported",
        actor="worker.backend",
        actor_role="worker",
        principal=agent_principal("worker.backend", session_id=registration.session_id),
        agent_id="worker.backend",
        task_id="task-1",
        session_id=registration.session_id,
        session_epoch=1,
        fencing_token=registration.raw_token,
        payload={},
    )

    assert result.accepted is False
    assert result.fencing_result is FencingResult.STALE_EPOCH


def test_replaced_and_quarantined_sessions_are_rejected(tmp_path):
    db_path = tmp_path / "agent-bus.sqlite3"
    replaced = FencingService(db_path).register_session(
        "old-session",
        agent_id="worker.backend",
        token="old-token",
        active=False,
        replaced_by_session_id="new-session",
    )
    quarantined = FencingService(db_path).register_session(
        "quarantined-session",
        agent_id="worker.backend",
        token="bad-token",
        session_role=SessionRole.QUARANTINED,
        quarantined=True,
    )
    kernel = ProtocolKernel(db_path)

    replaced_result = kernel.record_event(
        event_type="task.progress_reported",
        action="task.progress_reported",
        actor="worker.backend",
        actor_role="worker",
        principal=agent_principal("worker.backend", session_id=replaced.session_id),
        agent_id="worker.backend",
        session_id=replaced.session_id,
        session_epoch=1,
        fencing_token=replaced.raw_token,
        payload={},
    )
    quarantined_result = kernel.record_event(
        event_type="task.progress_reported",
        action="task.progress_reported",
        actor="worker.backend",
        actor_role="worker",
        principal=agent_principal("worker.backend", session_id=quarantined.session_id),
        agent_id="worker.backend",
        session_id=quarantined.session_id,
        session_epoch=1,
        fencing_token=quarantined.raw_token,
        payload={},
    )

    assert replaced_result.fencing_result is FencingResult.WRONG_SESSION
    assert quarantined_result.fencing_result is FencingResult.INVALID
    assert replaced_result.accepted is False
    assert quarantined_result.accepted is False


def test_controller_principal_can_commit_authoritative_event_without_worker_fence(tmp_path):
    db_path = tmp_path / "agent-bus.sqlite3"
    principal = Principal(
        principal_type=PrincipalType.CONTROLLER,
        roles=["controller"],
        permissions=["task.completed"],
    )

    result = ProtocolKernel(db_path).record_event(
        event_type="task.completed",
        action="task.completed",
        actor="controller-service",
        actor_role="controller",
        principal=principal,
        task_id="task-1",
        payload={"committed": True},
    )

    assert result.accepted is True
    assert result.fencing_result is FencingResult.NOT_REQUIRED
    with sqlite3.connect(db_path) as conn:
        event = conn.execute("select type, projection_effect from event_log").fetchone()
    assert event == ("task.completed", "COMMIT")


def test_free_form_controller_actor_string_does_not_grant_authority(tmp_path):
    result = ProtocolKernel(tmp_path / "agent-bus.sqlite3").record_event(
        event_type="task.completed",
        action="task.completed",
        actor="controller",
        actor_role=None,
        task_id="task-1",
        payload={},
    )

    assert result.accepted is False
    assert result.fencing_result is FencingResult.NOT_REQUIRED
    assert "authenticated principal" in (result.reason or "")
