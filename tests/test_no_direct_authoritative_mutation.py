from __future__ import annotations

import sqlite3

import pytest

from agent_bus.authority import DIRECT_AUTHORITATIVE_MUTATORS, controller_principal, is_direct_authoritative_mutator
from agent_bus.gates import GateBoard
from agent_bus.models import BusEvent, EventType, GateState, TaskState
from agent_bus.protocol import ProtocolKernel
from agent_bus.store import EventStore
from agent_bus.tasks import TaskBoard


def test_authoritative_mutator_registry_names_legacy_bypass_paths():
    assert is_direct_authoritative_mutator("agent_bus.tasks.TaskBoard.complete_task")
    assert is_direct_authoritative_mutator("agent_bus.gates.GateBoard.approve_gate")
    assert is_direct_authoritative_mutator("agent_bus.replacement.ReplacementCoordinator.approve")
    assert DIRECT_AUTHORITATIVE_MUTATORS["agent_bus.tasks.TaskBoard.complete_task"].replacement.startswith(
        "ProtocolKernel"
    )


def test_direct_authoritative_event_append_is_blocked_by_kernel_guard(tmp_path):
    store = EventStore(tmp_path / "agent-bus.sqlite3")

    with pytest.raises(sqlite3.IntegrityError, match="ProtocolKernel UnitOfWork"):
        store.append_event(BusEvent(type=EventType.TASK_COMPLETED, actor="worker.backend", task_id="task-1"))


def test_legacy_taskboard_complete_task_cannot_commit_authoritative_state(tmp_path):
    db_path = tmp_path / "agent-bus.sqlite3"
    board = TaskBoard(db_path=db_path, principal=controller_principal())
    try:
        task = board.create_task("Direct mutation test")
        board.assign_task(task.task_id, "worker.backend", actor="controller")
        board.start_task(task.task_id, actor="worker.backend")

        with pytest.raises(PermissionError, match="direct authoritative mutator is forbidden"):
            board.complete_task(task.task_id, actor="worker.backend")

        assert board.get_task(task.task_id).status is TaskState.WORKING
    finally:
        board.close()


def test_legacy_gateboard_approve_gate_cannot_commit_authoritative_state(tmp_path):
    db_path = tmp_path / "agent-bus.sqlite3"
    gates = GateBoard(db_path=db_path)
    try:
        gate = gates.create_gate("QA", task_id="task-1", requested_by="worker.backend")

        with pytest.raises(sqlite3.IntegrityError, match="ProtocolKernel UnitOfWork"):
            gates.approve_gate(gate.gate_id, actor="worker.backend")

        assert gates.get_gate(gate.gate_id).state is GateState.OPEN
    finally:
        gates.close()


def test_protocol_kernel_records_direct_mutation_attempt_as_reject(tmp_path):
    result = ProtocolKernel(tmp_path / "agent-bus.sqlite3").record_direct_mutation_attempt(
        "agent_bus.tasks.TaskBoard.complete_task",
        actor="worker.backend",
        actor_role="worker",
    )

    assert result.accepted is False
    assert result.projection_effect.value == "REJECT"
    with sqlite3.connect(tmp_path / "agent-bus.sqlite3") as conn:
        violation = conn.execute("select action, reason from protocol_violations").fetchone()
        effect = conn.execute("select effect from projection_effects").fetchone()[0]

    assert violation[0] == "direct_mutation:agent_bus.tasks.TaskBoard.complete_task"
    assert "direct authoritative mutator is forbidden" in violation[1]
    assert effect == "REJECT"
