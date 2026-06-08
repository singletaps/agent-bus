from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone

from agent_bus.agents import AgentDirectory
from agent_bus.authority import controller_principal
from agent_bus.gates import GateBoard
from agent_bus.inbox import InboxStore
from agent_bus.models import AgentRuntimeState
from agent_bus.projections import build_operations_projection
from agent_bus.tasks import TaskBoard


def _old_iso(seconds: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(seconds=seconds)).isoformat().replace("+00:00", "Z")


def test_operations_projection_excludes_rejected_gate_from_pending_actions(tmp_path):
    db_path = tmp_path / "agent-bus.sqlite3"
    principal = controller_principal()
    tasks = TaskBoard(db_path=db_path, principal=principal)
    run = tasks.create_run("Relevance", created_by="controller")
    task = tasks.create_task("Review task", run_id=run.run_id, owner_agent_id="controller")
    gates = GateBoard(db_path=db_path, principal=principal)
    gate = gates.create_gate(
        "Worker2 CLI reject gate",
        run_id=run.run_id,
        task_id=task.task_id,
        requested_by="worker-2",
    )
    rejected_gate = gates.reject_gate(gate.gate_id, actor="controller", reason="not adoptable")

    projection = build_operations_projection(db_path)

    assert all(item.gate_id != rejected_gate.gate_id for item in projection.ui.action_items)
    assert all(item.gate_id != rejected_gate.gate_id for item in projection.ui.actionable_gates)
    assert any(item.gate_id == rejected_gate.gate_id for item in projection.ui.historical_gates)
    assert any(gate.gate_id == rejected_gate.gate_id for gate in projection.gates)


def test_operations_projection_hides_superseded_older_gate_from_actionable_gates(tmp_path):
    db_path = tmp_path / "agent-bus.sqlite3"
    principal = controller_principal()
    tasks = TaskBoard(db_path=db_path, principal=principal)
    run = tasks.create_run("Relevance", created_by="controller")
    task = tasks.create_task("Gate task", run_id=run.run_id, owner_agent_id="controller")
    gates = GateBoard(db_path=db_path, principal=principal)
    older_gate = gates.create_gate(
        "Old approval",
        gate_id="gate-a",
        run_id=run.run_id,
        task_id=task.task_id,
        gate_kind="qa",
        requested_by="worker",
    )
    newer_gate = gates.create_gate(
        "New approval",
        gate_id="gate-z",
        run_id=run.run_id,
        task_id=task.task_id,
        gate_kind="qa",
        requested_by="worker",
    )

    projection = build_operations_projection(db_path)

    assert any(item.gate_id == newer_gate.gate_id for item in projection.ui.actionable_gates)
    assert all(item.gate_id != older_gate.gate_id for item in projection.ui.actionable_gates)
    assert any(item.gate_id == older_gate.gate_id for item in projection.ui.historical_gates)
    assert any(gate.gate_id == older_gate.gate_id for gate in projection.gates)


def test_operations_projection_marks_terminal_task_open_gate_historical(tmp_path):
    db_path = tmp_path / "agent-bus.sqlite3"
    principal = controller_principal()
    tasks = TaskBoard(db_path=db_path, principal=principal)
    run = tasks.create_run("Relevance", created_by="controller")
    task = tasks.create_task("Old task", run_id=run.run_id, owner_agent_id="controller")
    replacement = tasks.create_task("Replacement task", run_id=run.run_id, owner_agent_id="controller")
    terminal_task = tasks.supersede_task(task.task_id, replacement.task_id, actor="controller")
    gate = GateBoard(db_path=db_path, principal=principal).create_gate(
        "Terminal task gate",
        run_id=run.run_id,
        task_id=terminal_task.task_id,
        requested_by="worker",
    )

    projection = build_operations_projection(db_path)

    assert all(item.gate_id != gate.gate_id for item in projection.ui.action_items)
    assert all(item.gate_id != gate.gate_id for item in projection.ui.actionable_gates)
    assert any(item.gate_id == gate.gate_id for item in projection.ui.historical_gates)
    assert any(raw_gate.gate_id == gate.gate_id for raw_gate in projection.gates)


def test_operations_projection_archives_stale_agent_without_current_responsibility(tmp_path):
    db_path = tmp_path / "agent-bus.sqlite3"
    directory = AgentDirectory(db_path=db_path)
    directory.register_identity("worker.historical", role="worker")
    session = directory.start_session("worker.historical", session_id="historical-session")
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            "update agent_sessions set last_seen_at = ? where session_id = ?",
            ("2026-05-28T00:00:00Z", session.session_id),
        )

    projection = build_operations_projection(db_path)

    assert all(agent.agent_id != "worker.historical" for agent in projection.ui.visible_agents)
    assert any(agent.agent_id == "worker.historical" for agent in projection.ui.archived_agents)


def test_temporary_sim2_agents_archive_or_attention_by_responsibility(tmp_path):
    db_path = tmp_path / "agent-bus.sqlite3"
    directory = AgentDirectory(db_path=db_path)
    directory.register_identity("sim2-controller", role="controller")
    directory.register_identity("sim2-qa", role="qa")
    directory.register_identity("sim2-backend", role="worker")
    directory.register_identity("sim2-frontend", role="worker")
    controller_session = directory.start_session("sim2-controller", session_id="sim2-controller-session")
    qa_session = directory.start_session("sim2-qa", session_id="sim2-qa-session")
    backend_session = directory.start_session(
        "sim2-backend",
        session_id="sim2-backend-session",
        runtime_state=AgentRuntimeState.REHYDRATING,
    )
    frontend_session = directory.start_session("sim2-frontend", session_id="sim2-frontend-session")
    directory.retire_session(frontend_session.session_id, end_reason="replaced", reason="replaced by backend")

    board = TaskBoard(db_path=db_path, principal=controller_principal())
    run = board.create_run("runtime target", objective="status lifecycle", created_by="controller")
    task = board.create_task(
        "stale backend work",
        run_id=run.run_id,
        owner_agent_id="sim2-controller",
    )
    task = board.assign_task(task.task_id, "sim2-backend", actor="controller")
    board.start_task(task.task_id, actor="sim2-backend")
    with sqlite3.connect(db_path) as conn:
        for session in (controller_session, qa_session, backend_session):
            conn.execute(
                "update agent_sessions set last_seen_at = ? where session_id = ?",
                (_old_iso(7200), session.session_id),
            )
        conn.execute(
            "update agent_sessions set runtime_state = ? where session_id = ?",
            (AgentRuntimeState.REHYDRATING.value, backend_session.session_id),
        )

    projection = build_operations_projection(db_path)
    visible_ids = {agent.agent_id for agent in projection.ui.visible_agents}
    archived_ids = {agent.agent_id for agent in projection.ui.archived_agents}
    backend = next(agent for agent in projection.ui.visible_agents if agent.agent_id == "sim2-backend")

    assert "sim2-controller" not in visible_ids
    assert "sim2-qa" not in visible_ids
    assert {"sim2-controller", "sim2-qa", "sim2-frontend"} <= archived_ids
    assert backend.presence_state == "stale"
    assert backend.runtime_state == "suspected_stuck"
    assert backend.ui_visibility_state == "needs_attention"


def test_operations_projection_invalid_owner_inbox_is_not_action_item(tmp_path):
    db_path = tmp_path / "agent-bus.sqlite3"
    directory = AgentDirectory(db_path=db_path)
    directory.register_identity("sim2-frontend", role="worker")
    directory.start_session(
        "sim2-frontend",
        session_id="sim2-frontend-session",
        runtime_state=AgentRuntimeState.REPLACED,
    )
    InboxStore(db_path=db_path, principal=controller_principal()).enqueue(
        "sim2-frontend",
        "replacement_notice",
        {"task_id": "task-old"},
        actor="controller",
    )

    projection = build_operations_projection(db_path)

    assert all(agent.agent_id != "sim2-frontend" for agent in projection.ui.visible_agents)
    assert any(agent.agent_id == "sim2-frontend" for agent in projection.ui.archived_agents)
    assert all(item.agent_id != "sim2-frontend" for item in projection.ui.action_items)


def test_operations_projection_waiting_owner_gate_is_not_actionable(tmp_path):
    db_path = tmp_path / "agent-bus.sqlite3"
    principal = controller_principal()
    directory = AgentDirectory(db_path=db_path)
    directory.register_identity("runtime-qa", role="qa")
    directory.start_session(
        "runtime-qa",
        session_id="runtime-qa-session",
        runtime_state=AgentRuntimeState.STANDBY_DEGRADED,
    )
    tasks = TaskBoard(db_path=db_path, principal=principal)
    run = tasks.create_run("Relevance", created_by="controller")
    task = tasks.create_task("Gate task", run_id=run.run_id, owner_agent_id="controller")
    gate = GateBoard(db_path=db_path, principal=principal).create_gate(
        "QA unavailable",
        run_id=run.run_id,
        task_id=task.task_id,
        owner_agent_id="runtime-qa",
    )

    projection = build_operations_projection(db_path)

    assert all(item.gate_id != gate.gate_id for item in projection.ui.action_items)
    assert all(item.gate_id != gate.gate_id for item in projection.ui.actionable_gates)
    assert any(item.gate_id == gate.gate_id for item in projection.ui.historical_gates)
