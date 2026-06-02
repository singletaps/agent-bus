from __future__ import annotations

import sqlite3

import pytest

from agent_bus.authority import controller_principal
from agent_bus.context import ContextStore
from agent_bus.inbox import InboxStore
from agent_bus.tasks import TaskBoard


def test_public_durable_write_paths_record_kernel_guards_and_projection_effects(tmp_path):
    db_path = tmp_path / "agent-bus.sqlite3"
    controller = controller_principal()
    board = TaskBoard(db_path=db_path, principal=controller)

    run = board.create_run("controller run", created_by="controller")
    task = board.create_task("controller task", run_id=run.run_id, owner_agent_id="controller")
    assigned = board.assign_task(task.task_id, "worker.backend", actor="controller")
    packet = ContextStore(db_path, principal=controller).create_packet(
        agent_id="worker.backend",
        task_id=assigned.task_id,
        run_id=run.run_id,
        summary="direct context",
        actor="controller",
    )
    item = InboxStore(db_path, principal=controller).enqueue(
        "worker.backend",
        "task_assigned",
        {"task_id": assigned.task_id},
        context_packet_id=packet.packet_id,
        actor="controller",
    )
    coordination = board.record_coordination(
        "intent",
        task_id=assigned.task_id,
        agent_id="worker.backend",
        payload={"action": "continue"},
        actor="controller",
    )
    artifact = board.create_artifact(
        "test-log",
        "coordination/test-output.txt",
        run_id=run.run_id,
        task_id=assigned.task_id,
        metadata={"passed": True},
        created_by="controller",
    )

    with sqlite3.connect(db_path) as conn:
        event_types = {
            row[0]
            for row in conn.execute(
                """
                select type from event_log
                where type in (
                    'run.created', 'task.created', 'task.assigned', 'context.created',
                    'inbox.enqueued', 'coordination.recorded', 'artifact.created'
                )
                """
            )
        }
        guarded_targets = {
            (row[0], row[1])
            for row in conn.execute(
                """
                select target_table, target_id from kernel_write_guards
                where target_id in (?, ?, ?, ?, ?, ?)
                """,
                (run.run_id, task.task_id, packet.packet_id, item.inbox_id, coordination.record_id, artifact.artifact_id),
            )
        }
        event_guard_count = conn.execute(
            """
            select count(*) from kernel_write_guards
            where event_id in (
                select event_id from event_log
                where type in (
                    'run.created', 'task.created', 'task.assigned', 'context.created',
                    'inbox.enqueued', 'coordination.recorded', 'artifact.created'
                )
            )
            """
        ).fetchone()[0]
        effect_targets = {
            (row[0], row[1])
            for row in conn.execute(
                """
                select target_table, target_id from projection_effects
                where target_id in (?, ?, ?, ?, ?, ?)
                """,
                (run.run_id, task.task_id, packet.packet_id, item.inbox_id, coordination.record_id, artifact.artifact_id),
            )
        }

    assert event_types == {
        "run.created",
        "task.created",
        "task.assigned",
        "context.created",
        "inbox.enqueued",
        "coordination.recorded",
        "artifact.created",
    }
    assert event_guard_count >= 7
    assert ("runs", run.run_id) in guarded_targets
    assert ("context_packets", packet.packet_id) in guarded_targets
    assert ("inbox_items", item.inbox_id) in guarded_targets
    assert ("runs", run.run_id) in effect_targets
    assert ("tasks", task.task_id) in effect_targets
    assert ("context_packets", packet.packet_id) in effect_targets
    assert ("inbox_items", item.inbox_id) in effect_targets
    assert ("coordination_records", coordination.record_id) in effect_targets
    assert ("artifacts", artifact.artifact_id) in effect_targets


def test_untrusted_control_plane_actors_reject_and_record_protocol_violations(tmp_path):
    db_path = tmp_path / "agent-bus.sqlite3"
    controller = controller_principal()
    setup_board = TaskBoard(db_path=db_path, principal=controller)
    run = setup_board.create_run("controller run", created_by="controller")
    task = setup_board.create_task("controller task", run_id=run.run_id, owner_agent_id="controller")
    board = TaskBoard(db_path=db_path)

    for actor in ("worker.freeform", "runtime-worker-1", "controller"):
        with pytest.raises(PermissionError):
            board.create_run(f"{actor} run", created_by=actor)
        with pytest.raises(PermissionError):
            board.create_task(f"{actor} task", run_id=run.run_id, owner_agent_id=actor)
        with pytest.raises(PermissionError):
            board.assign_task(task.task_id, actor, actor=actor)
        with pytest.raises(PermissionError):
            ContextStore(db_path).create_packet(
                agent_id=actor,
                task_id=task.task_id,
                run_id=run.run_id,
                summary=f"{actor} context",
                actor=actor,
            )
        with pytest.raises(PermissionError):
            InboxStore(db_path).enqueue(
                actor,
                "task_assigned",
                {"task_id": task.task_id},
                actor=actor,
            )
        with pytest.raises(PermissionError):
            board.supersede_task(task.task_id, f"{actor}-next", actor=actor)
        with pytest.raises(PermissionError):
            board.create_artifact(
                "test-log",
                f"{actor}.txt",
                run_id=run.run_id,
                task_id=task.task_id,
                created_by=actor,
            )
        with pytest.raises(PermissionError):
            board.record_coordination(
                "intent",
                run_id=run.run_id,
                task_id=task.task_id,
                agent_id=actor,
                actor=actor,
                payload={"action": "bypass"},
            )

    assert board.list_tasks(run_id=run.run_id) == [task]
    with sqlite3.connect(db_path) as conn:
        violations = conn.execute("select action, projection_effect from protocol_violations").fetchall()
        rejected_effects = conn.execute("select effect from projection_effects where effect = 'REJECT'").fetchall()

    assert {row[0] for row in violations} >= {
        "run.created",
        "task.created",
            "task.assigned",
            "context.created",
            "inbox.enqueued",
            "task.superseded",
            "artifact.created",
            "coordination.recorded",
        }
    assert len(rejected_effects) >= 24


def test_trusted_compatibility_flag_does_not_grant_authority_without_principal(tmp_path):
    db_path = tmp_path / "agent-bus.sqlite3"
    board = TaskBoard(db_path=db_path, trusted_compatibility=True)

    for actor in ("controller", "runtime-worker-1"):
        with pytest.raises(PermissionError):
            board.create_run(f"{actor} run", created_by=actor)
