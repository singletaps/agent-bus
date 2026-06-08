from __future__ import annotations

import sqlite3

import pytest

from agent_bus.authority import controller_principal
from agent_bus.models import EventType, TaskState
from agent_bus.protocol import ProtocolKernel
from agent_bus.tasks import TaskBoard


def _count(conn: sqlite3.Connection, table: str, where: str = "1 = 1", params: tuple[object, ...] = ()) -> int:
    return int(conn.execute(f"select count(*) from {table} where {where}", params).fetchone()[0])


def test_protocol_assignment_rolls_back_task_context_and_inbox_on_contract_failure(tmp_path):
    db_path = tmp_path / "agent-bus.sqlite3"
    controller = controller_principal()
    board = TaskBoard(db_path=db_path, principal=controller)
    task = board.create_task("Atomic assignment", run_id="run-1", owner_agent_id="controller")

    def fail_after_task_update(conn: sqlite3.Connection) -> None:
        assert _count(conn, "tasks", "task_id = ? and status = ?", (task.task_id, TaskState.ASSIGNED.value)) == 1
        raise RuntimeError("injected contract failure")

    with pytest.raises(RuntimeError, match="injected contract failure"):
        ProtocolKernel(db_path).assign_task(
            task_id=task.task_id,
            assignee_agent_id="worker.backend",
            actor="controller",
            principal=controller,
            failure_hook=fail_after_task_update,
        )

    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        stored = conn.execute("select status, assignee_agent_id from tasks where task_id = ?", (task.task_id,)).fetchone()
        event_count = _count(conn, "event_log", "type = ?", (EventType.TASK_ASSIGNED.value,))
        binding_count = _count(conn, "task_context_bindings", "task_id = ?", (task.task_id,))
        inbox_count = _count(conn, "inbox_items", "payload_json like ?", (f"%{task.task_id}%",))

    assert stored["status"] == TaskState.CREATED.value
    assert stored["assignee_agent_id"] is None
    assert event_count == 0
    assert binding_count == 0
    assert inbox_count == 0


def test_taskboard_assignment_delegates_to_protocol_and_creates_contract_atomically(tmp_path):
    db_path = tmp_path / "agent-bus.sqlite3"
    controller = controller_principal()
    board = TaskBoard(db_path=db_path, principal=controller)
    task = board.create_task("Assignment contract", run_id="run-1", owner_agent_id="controller")

    assigned = board.assign_task(task.task_id, "worker.backend", actor="controller")

    assert assigned.status is TaskState.ASSIGNED
    assert assigned.assignee_agent_id == "worker.backend"
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        event = conn.execute("select * from event_log where type = ?", (EventType.TASK_ASSIGNED.value,)).fetchone()
        binding = conn.execute("select * from task_context_bindings where task_id = ?", (task.task_id,)).fetchone()
        inbox = conn.execute("select * from inbox_items where agent_id = ?", ("worker.backend",)).fetchone()
        effect = conn.execute("select * from projection_effects where event_id = ?", (event["event_id"],)).fetchone()

    assert event["projection_effect"] == "COMMIT"
    assert event["fencing_result"] == "NOT_REQUIRED"
    assert binding["context_packet_id"] == inbox["context_packet_id"]
    assert binding["agent_id"] == "worker.backend"
    assert inbox["kind"] == "task_assigned"
    assert effect["target_table"] == "tasks"
    assert effect["target_id"] == task.task_id
