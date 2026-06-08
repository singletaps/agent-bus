from __future__ import annotations

import json
import sqlite3

import pytest

from agent_bus.agents import AgentDirectory
from agent_bus.authority import controller_principal
from agent_bus.context import ContextStore
from agent_bus.fencing import FencingService
from agent_bus.inbox import InboxStore
from agent_bus.models import AgentRuntimeState, CapabilityEvidenceSource, TaskState
from agent_bus.protocol_models import BindingStatus, PacketKind, SessionRole
from agent_bus.replacement import ReplacementCoordinator, ReplacementRecommendation
from agent_bus.tasks import TaskBoard


def _replacement_case(tmp_path):
    db_path = tmp_path / "agent-bus.sqlite3"
    controller = controller_principal()
    directory = AgentDirectory(db_path=db_path)
    directory.register_identity("worker.frontend", role="worker", declared_capabilities=["react"])
    old_session = directory.start_session("worker.frontend", run_id="run-1", session_id="old-session")
    directory.register_identity("runtime-helper-2", role="worker", declared_capabilities=["react"])
    replacement_session = directory.start_session(
        "runtime-helper-2",
        run_id="run-1",
        session_id="replacement-session",
        runtime_state=AgentRuntimeState.STANDBY_READY,
    )
    directory.record_capability_evidence(
        "runtime-helper-2",
        "react",
        CapabilityEvidenceSource.USER_ASSIGNED,
        confidence=0.99,
    )
    old_fence = FencingService(db_path).register_session(
        old_session.session_id,
        agent_id=old_session.agent_id,
        token="old-token",
    )
    FencingService(db_path).register_session(
        replacement_session.session_id,
        agent_id=replacement_session.agent_id,
        token="replacement-token",
    )
    board = TaskBoard(db_path=db_path, agent_directory=directory, principal=controller)
    task = board.create_task("Continue same task", run_id="run-1", owner_agent_id="controller")
    assigned = board.assign_task(task.task_id, old_session.agent_id, actor="controller")
    directory.report_context_loss(old_session.session_id, reason="context compression failed")
    context = ContextStore(db_path, principal=controller)
    inbox = InboxStore(db_path, principal=controller)
    coordinator = ReplacementCoordinator(
        directory=directory,
        inbox=inbox,
        context_sink=context,
        principal=controller,
    )
    recommendation = coordinator.recommend_for_session(
        old_session.session_id,
        task_id=assigned.task_id,
        run_id="run-1",
        required_capabilities=("react",),
        role="worker",
    )
    assert isinstance(recommendation, ReplacementRecommendation)
    return {
        "db_path": db_path,
        "coordinator": coordinator,
        "recommendation": recommendation,
        "task_id": assigned.task_id,
        "old_session": old_session,
        "replacement_session": replacement_session,
        "old_fence": old_fence,
    }


def _has_table(conn: sqlite3.Connection, name: str) -> bool:
    row = conn.execute(
        "select 1 from sqlite_master where type = 'table' and name = ?",
        (name,),
    ).fetchone()
    return row is not None


def _has_failed_replacement_saga(conn: sqlite3.Connection, recommendation_id: str) -> bool:
    for table in ("replacement_approvals", "replacement_sagas"):
        if not _has_table(conn, table):
            continue
        columns = {row["name"] for row in conn.execute(f"pragma table_info({table})").fetchall()}
        if {"recommendation_id", "status"} - columns:
            continue
        row = conn.execute(
            f"select * from {table} where recommendation_id = ? and status = ?",
            (recommendation_id, "failed_needs_recovery"),
        ).fetchone()
        if row is not None:
            payload = dict(row)
            assert payload["recommendation_id"] == recommendation_id
            return True
    return False


def _assert_rolled_back_or_failed_saga(case) -> None:
    db_path = case["db_path"]
    recommendation = case["recommendation"]
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        if _has_failed_replacement_saga(conn, recommendation.recommendation_id):
            return

        task = conn.execute("select * from tasks where task_id = ?", (case["task_id"],)).fetchone()
        old_session = conn.execute(
            "select * from agent_sessions where session_id = ?",
            (case["old_session"].session_id,),
        ).fetchone()
        replacement_session = conn.execute(
            "select * from agent_sessions where session_id = ?",
            (case["replacement_session"].session_id,),
        ).fetchone()
        old_fence = conn.execute(
            "select * from session_fences where session_id = ?",
            (case["old_session"].session_id,),
        ).fetchone()
        replacement_notices = conn.execute(
            "select * from inbox_items where kind = ? and agent_id = ?",
            ("replacement_notice", case["replacement_session"].agent_id),
        ).fetchall()
        rehydration_packets = conn.execute(
            "select * from context_packets where packet_kind = ? and agent_id = ?",
            (PacketKind.REHYDRATION.value, case["replacement_session"].agent_id),
        ).fetchall()
        committed_events = conn.execute(
            """
            select type, payload_json from event_log
             where correlation_id = ?
               and type in ('replacement.approved', 'replacement.reassignment_committed', 'task.reassigned')
            """,
            (recommendation.recommendation_id,),
        ).fetchall()

    assert task["status"] == TaskState.ASSIGNED.value
    assert task["assignee_agent_id"] == case["old_session"].agent_id
    assert old_session["active"] == 1
    assert old_session["runtime_state"] == AgentRuntimeState.CONTEXT_LOST.value
    assert old_session["replaced_by_session_id"] is None
    assert replacement_session["runtime_state"] == AgentRuntimeState.STANDBY_READY.value
    assert old_fence["active"] == 1
    assert old_fence["session_role"] != SessionRole.REPLACED.value
    assert old_fence["replaced_by_session_id"] is None
    assert replacement_notices == []
    assert rehydration_packets == []
    assert committed_events == []


def _call_approve_with_injected_failure(case, monkeypatch, target: str) -> None:
    def fail(*_args, **_kwargs):
        raise RuntimeError(f"injected {target} failure")

    coordinator = case["coordinator"]
    if target == "rehydration":
        monkeypatch.setattr(coordinator.context_sink, "create_rehydration_packet", fail)
    elif target == "replacement_notice":
        monkeypatch.setattr(coordinator.inbox, "enqueue", fail)
    elif target == "compatibility_projection":
        monkeypatch.setattr(coordinator, "_record_task_reassigned_projection", fail)
    else:
        raise AssertionError(f"unknown failure target: {target}")

    with pytest.raises(RuntimeError, match=f"injected {target} failure"):
        coordinator.approve(case["recommendation"], approved_by="controller")


@pytest.mark.parametrize("target", ["rehydration", "replacement_notice", "compatibility_projection"])
def test_replacement_approval_failure_rolls_back_or_records_failed_saga(tmp_path, monkeypatch, target):
    case = _replacement_case(tmp_path)

    _call_approve_with_injected_failure(case, monkeypatch, target)

    _assert_rolled_back_or_failed_saga(case)
