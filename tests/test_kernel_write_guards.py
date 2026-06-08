from __future__ import annotations

import sqlite3

import pytest

from agent_bus.authority import controller_principal
from agent_bus.gates import GateBoard
from agent_bus.models import GateState
from agent_bus.tasks import TaskBoard


def _assigned_task(db_path) -> str:
    board = TaskBoard(db_path=db_path, principal=controller_principal())
    try:
        task = board.create_task("Guarded task")
        assigned = board.assign_task(task.task_id, "worker.backend", actor="controller")
        return assigned.task_id
    finally:
        board.close()


@pytest.mark.parametrize("status", ["completed", "failed", "reassigned"])
def test_stale_assignment_guard_does_not_authorize_direct_task_status_update(tmp_path, status):
    db_path = tmp_path / "agent-bus.sqlite3"
    task_id = _assigned_task(db_path)

    with sqlite3.connect(db_path) as conn:
        with pytest.raises(sqlite3.IntegrityError, match="active ProtocolKernel guard"):
            conn.execute("update tasks set status = ? where task_id = ?", (status, task_id))


def test_task_assigned_guard_does_not_authorize_task_completed_action(tmp_path):
    db_path = tmp_path / "agent-bus.sqlite3"
    task_id = _assigned_task(db_path)

    with sqlite3.connect(db_path) as conn:
        guard_action, consumed_at, expires_at = conn.execute(
            """
            select action, consumed_at, expires_at from kernel_write_guards
            where target_table = 'tasks' and target_id = ?
            order by created_at desc
            limit 1
            """,
            (task_id,),
        ).fetchone()

        assert guard_action == "task.assigned"
        assert consumed_at is not None
        assert expires_at is not None
        with pytest.raises(sqlite3.IntegrityError, match="active ProtocolKernel guard"):
            conn.execute("update tasks set status = 'completed' where task_id = ?", (task_id,))


def test_gate_open_without_decision_guard_does_not_allow_direct_approval(tmp_path):
    db_path = tmp_path / "agent-bus.sqlite3"
    gates = GateBoard(db_path=db_path, principal=controller_principal())
    try:
        gate = gates.create_gate("Guarded gate", task_id="task-1", requested_by="worker.backend")
        assert gates.get_gate(gate.gate_id).state is GateState.OPEN
    finally:
        gates.close()

    with sqlite3.connect(db_path) as conn:
        with pytest.raises(sqlite3.IntegrityError, match="active ProtocolKernel guard"):
            conn.execute("update gates set state = 'approved' where gate_id = ?", (gate.gate_id,))


def test_consumed_gate_approval_guard_does_not_authorize_later_direct_rejection(tmp_path):
    db_path = tmp_path / "agent-bus.sqlite3"
    gates = GateBoard(db_path=db_path, principal=controller_principal())
    try:
        gate = gates.create_gate("Guarded gate", task_id="task-1", requested_by="worker.backend")
        approved = gates.approve_gate(gate.gate_id, actor="controller")
        assert approved.state is GateState.APPROVED
    finally:
        gates.close()

    with sqlite3.connect(db_path) as conn:
        guard_action, consumed_at = conn.execute(
            """
            select action, consumed_at from kernel_write_guards
            where target_table = 'gates' and target_id = ?
            order by created_at desc
            limit 1
            """,
            (gate.gate_id,),
        ).fetchone()

        assert guard_action == "gate.approved"
        assert consumed_at is not None
        with pytest.raises(sqlite3.IntegrityError, match="active ProtocolKernel guard"):
            conn.execute("update gates set state = 'rejected' where gate_id = ?", (gate.gate_id,))
